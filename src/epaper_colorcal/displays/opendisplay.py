"""OpenDisplay board over Bluetooth, via ``py-opendisplay`` (the ``opendisplay`` extra).

Validated on a Spectra 6 7.3" (BWGBRY) board with a CR30.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from .base import Display

if TYPE_CHECKING:
    from PIL.Image import Image

    from ..schemes import Ink, Scheme

# Advertised chip temperatures outside this range are treated as "no reading" (some boards
# advertise -40 °C, the encoding's floor, when they have no valid value).
PLAUSIBLE_BOARD_TEMP_C = (-20.0, 60.0)

_MAC_OR_UUID = re.compile(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}|[0-9A-Fa-f-]{36}")


async def read_board_temperature(address: str, timeout: float = 8.0) -> float | None:
    """The board's advertised MCU temperature, read from a scan without connecting.

    The chip temperature tracks room temperature while the board is idle, so it approximates
    the panel's temperature. Read it before connecting: BLE activity warms the chip.
    Returns None if the board isn't seen or reports an implausible value.
    """
    from opendisplay.discovery import (  # pylint: disable=import-outside-toplevel,import-error  # optional extra
        discover_devices_with_adv,
    )

    wanted = address.lower()
    for name, (mac, adv) in (await discover_devices_with_adv(timeout=timeout)).items():
        if wanted in {name.lower(), str(mac).lower()} and adv is not None:
            low, high = PLAUSIBLE_BOARD_TEMP_C
            return float(adv.temperature_c) if low <= adv.temperature_c <= high else None
    return None


def solid_image(ink: Ink, size: tuple[int, int]) -> Image:
    """A full-screen image of the ink's nominal colour.

    epaper-dithering always maps a nominal colour to its own ink, so the panel shows the
    pure ink whatever palette the board already uses (the measurement isn't circular).
    """
    from PIL import Image as PILImage  # pylint: disable=import-outside-toplevel

    return PILImage.new("RGB", size, ink.rgb)


class OpenDisplayDisplay(Display):
    def __init__(self, address: str, key: bytes | None = None, settle_seconds: float = 3.0) -> None:
        self._address = address  # a MAC (Linux/Windows), a macOS UUID or the advertised name
        self._key = key
        self._settle = settle_seconds
        self._device: Any = None

    async def temperature(self) -> float | None:
        return await read_board_temperature(self._address)

    async def connect(self) -> None:
        try:
            from opendisplay import OpenDisplayDevice  # pylint: disable=import-outside-toplevel
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise SystemExit(
                "Driving an OpenDisplay board needs py-opendisplay (Python 3.13+):\n"
                "    pip install 'epaper-colorcal[opendisplay]'"
            ) from exc

        from opendisplay.exceptions import (  # pylint: disable=import-outside-toplevel,import-error
            BLEConnectionError,
        )

        # A board on battery sleeps between advertising bursts, so one scan can miss it: retry once.
        for attempt in range(2):
            if _MAC_OR_UUID.fullmatch(self._address):
                device = OpenDisplayDevice(mac_address=self._address)
            else:
                device = OpenDisplayDevice(device_name=self._address)
            try:
                # The device must stay open between connect() and close(); its only open
                # mechanism is the async context manager.
                await device.__aenter__()  # pylint: disable=unnecessary-dunder-call
                break
            except BLEConnectionError as exc:
                if attempt:
                    raise SystemExit(
                        f"Could not connect to the OpenDisplay board {self._address!r} ({exc}). Is it in range "
                        "and awake? A board on battery may be asleep: press its button or wait a moment."
                    ) from exc
        if self._key is not None:
            await device.authenticate(self._key)
        await device.interrogate()
        self._device = device

    async def scheme(self) -> Scheme | None:
        from ..schemes import scheme_for_firmware_id  # pylint: disable=import-outside-toplevel

        return scheme_for_firmware_id(int(self._device.color_scheme))

    async def show(self, index: int, ink: Ink) -> None:
        if self._device is None:
            raise RuntimeError("connect() must be called before show()")

        from epaper_dithering import DitherMode  # pylint: disable=import-outside-toplevel
        from opendisplay import prepare_image  # pylint: disable=import-outside-toplevel,import-error

        device = self._device
        prepared = prepare_image(
            solid_image(ink, (device.width, device.height)),
            config=device.config,
            dither_mode=DitherMode.NONE,
            compress=self._supports_zip(),
        )
        n_colors = len(prepared[2].convert("RGB").getcolors(maxcolors=2) or [None, None])
        if n_colors != 1:
            raise RuntimeError(f"solid {ink.name} did not quantize to a single ink (got {n_colors}+ colours)")

        # upload_prepared_image returns only after the device reports refresh complete
        # (DIRECT_WRITE_REFRESH_COMPLETE), so `settle` is just a small safety margin.
        await device.upload_prepared_image(prepared)
        await asyncio.sleep(self._settle)

    def _supports_zip(self) -> bool:
        config = self._device.config
        return bool(config.displays[0].supports_zip) if config and config.displays else True

    async def close(self) -> None:
        if self._device is not None:
            await self._device.__aexit__(None, None, None)
            self._device = None
