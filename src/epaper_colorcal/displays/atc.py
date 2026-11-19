"""A tag running ATC BLE OEPL firmware, directly over Bluetooth, via ``py-atc-ble-oepl``.

Each ink is uploaded as a solid image, quantised against the tag's ideal palette with no
dithering, so it stays one ink. The upload returns once the tag has the image and has been
told to refresh; the measurement loop then waits for the refresh with the instrument.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink, Scheme

DISCOVERY_TIMEOUT = 90.0  # tags advertise irregularly, sometimes 30 s apart; the scan stops when found
PLAUSIBLE_TAG_TEMP_C = (-20.0, 60.0)


def _library() -> Any:
    try:
        import py_atc_ble_oepl  # pylint: disable=import-outside-toplevel,import-error
    except ImportError as exc:  # pragma: no cover - only without the extra
        raise SystemExit(
            "Driving an ATC BLE tag needs py-atc-ble-oepl:\n    pip install 'epaper-colorcal[atc]'"
        ) from exc
    return py_atc_ble_oepl


class ATCDisplay(Display):
    """``name`` is the tag's advertised name (``ATC_05D611``, or just ``05D611``) or its address."""

    def __init__(self, name: str, settle_seconds: float = 0.0) -> None:
        self._wanted = name.upper().removeprefix("ATC_")
        self._settle = settle_seconds
        self._found: Any = None  # the DiscoveredDevice
        self._device: Any = None

    async def _discover(self) -> Any:
        """The tag's BLEDevice and advertising data, from the first advertisement that names it.

        Every packet is checked as it arrives: the tags alternate advertisements with and
        without their manufacturer data, so looking only at the last one per device can miss
        them.
        """
        if self._found is not None:
            return self._found
        import asyncio  # pylint: disable=import-outside-toplevel

        from bleak import BleakScanner  # pylint: disable=import-outside-toplevel,import-error

        lib = _library()
        found: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

        def check(device: Any, adv: Any) -> None:
            data = adv.manufacturer_data.get(lib.MANUFACTURER_ID)
            name = (adv.local_name or device.name or "").upper().removeprefix("ATC_")
            if data is None or found.done() or self._wanted not in (name, str(device.address).upper()):
                return
            try:
                parsed = lib.ATCProtocol().parse_advertising_data(data)
            except ValueError:
                parsed = None
            found.set_result(lib.DiscoveredDevice(device.address, name, adv.rssi, device, parsed))

        async with BleakScanner(check):
            try:
                self._found = await asyncio.wait_for(found, DISCOVERY_TIMEOUT)
            except asyncio.TimeoutError as exc:
                raise SystemExit(
                    f"No ATC BLE tag {self._wanted!r} found in {DISCOVERY_TIMEOUT:g} s. Is it in range? "
                    "Tags advertise irregularly; a busy or sleeping tag may not advertise at all."
                ) from exc
        return self._found

    async def temperature(self) -> float | None:
        adv = (await self._discover()).advertising_data
        if adv is None or adv.temperature is None:
            return None
        low, high = PLAUSIBLE_TAG_TEMP_C
        return float(adv.temperature) if low <= adv.temperature <= high else None

    async def connect(self) -> None:
        found = await self._discover()
        device = _library().ATCDevice(found.mac_address, ble_device=found.device)
        await device.__aenter__()  # pylint: disable=unnecessary-dunder-call  # held open until close()
        self._device = device

    async def scheme(self) -> Scheme | None:
        from ..schemes import scheme_for_firmware_id  # pylint: disable=import-outside-toplevel

        # ATC colour schemes (0 MONO, 1 BWR, 2 BWY, 3 BWRY) use OpenDisplay's numbering.
        return scheme_for_firmware_id(int(self._device.color_scheme))

    async def show(self, index: int, ink: Ink) -> None:
        if self._device is None:
            raise RuntimeError("connect() must be called before show()")
        import asyncio  # pylint: disable=import-outside-toplevel

        from PIL import Image  # pylint: disable=import-outside-toplevel

        lib = _library()
        image = Image.new("RGB", (self._device.width, self._device.height), ink.rgb)
        if not await self._device.upload_image(image, dither_mode=lib.DitherMode.NONE, fit=lib.FitMode.STRETCH):
            raise RuntimeError(f"The tag {self._wanted} did not accept the {ink.name} image.")
        await asyncio.sleep(self._settle)

    async def close(self) -> None:
        if self._device is not None:
            await self._device.__aexit__(None, None, None)
            self._device = None
