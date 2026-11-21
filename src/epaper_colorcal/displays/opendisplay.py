"""OpenDisplay board over Bluetooth, via ``py-opendisplay`` (the ``opendisplay`` extra).

With a drive mode (firmware 3.0, e.g. ``colour16``), the colours to measure are the mode's
display_calibration (0xB0) entries: each entry's per-pass panel codes are shown solid, so the
measurement gives every entry's colour on this unit, mixed colours included.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import sys
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


WHITE = 1
"""The logical index of white in OpenDisplay's BWRY order (black, white, yellow, red)."""


def entry_names(codes: list[tuple[int, ...]], white_code: int | None) -> list[str]:
    """Ink names for drive-mode entries: ``white`` for the paper white, else the per-pass codes.

    The paper white is the entry whose code in every pass is the panel's white code.
    """
    names = []
    for entry in codes:
        is_white = white_code is not None and all(c == white_code for c in entry) and "white" not in names
        names.append("white" if is_white else "codes_" + "".join(str(c) for c in entry))
    return names


class OpenDisplayDisplay(Display):  # pylint: disable=too-many-instance-attributes
    settled_after_show = True  # the upload returns after the board reports refresh complete

    def __init__(
        self, address: str, key: bytes | None = None, settle_seconds: float = 3.0, mode: str | None = None
    ) -> None:
        self._address = address  # a MAC (Linux/Windows), a macOS UUID or the advertised name
        self._key = key
        self._settle = settle_seconds
        self._mode_name = mode
        self._device: Any = None
        self._drive: Any = None  # the firmware 3.0 Device, when a drive mode is used
        self._mode: Any = None
        self._calibration: Any = None

    async def temperature(self) -> float | None:
        return await read_board_temperature(self._address)

    async def connect(self) -> None:
        if self._mode_name is not None:
            await self._connect_drive_mode(self._mode_name)
            return
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

    async def _connect_drive_mode(self, name: str) -> None:
        import opendisplay  # pylint: disable=import-outside-toplevel,import-error

        connect: Any = getattr(opendisplay, "connect", None)  # py-opendisplay with firmware 3.0 support
        if connect is None:
            raise SystemExit(
                "Drive modes need a py-opendisplay with firmware 3.0 support (opendisplay.connect); "
                f"the installed {getattr(opendisplay, '__version__', 'version')} has none."
            )
        from opendisplay.exceptions import (  # pylint: disable=import-outside-toplevel,import-error
            BLEConnectionError,
        )

        # A board on battery sleeps between advertising bursts, so one scan can miss it: retry once.
        for attempt in range(2):
            if _MAC_OR_UUID.fullmatch(self._address):
                device = connect(self._address, encryption_key=self._key)  # pylint: disable=not-callable
            else:
                device = connect(name=self._address, encryption_key=self._key)  # pylint: disable=not-callable
            try:
                await device.__aenter__()  # pylint: disable=unnecessary-dunder-call
                break
            except BLEConnectionError as exc:
                if attempt:
                    raise SystemExit(
                        f"Could not connect to the OpenDisplay board {self._address!r} ({exc}). Is it in range "
                        "and awake? A board on battery may be asleep: press its button or wait a moment."
                    ) from exc
        try:
            mode = device.display.drive_mode(name)
            config = device.config.cached
            calibration = next(
                (
                    c
                    for c in config.display_calibrations
                    if c.mode_index == mode.mode_index and c.instance_number == mode.instance_number
                ),
                None,
            )
            if calibration is None or not calibration.entries:
                raise SystemExit(f"Drive mode {mode.name!r} has no display_calibration (0xB0) entries to measure.")
        except BaseException:
            await device.__aexit__(None, None, None)
            raise
        self._drive, self._mode, self._calibration = device, mode, calibration

    def _white_code(self) -> int | None:
        instance = self._mode.instance_number
        panels = [p for p in self._drive.config.cached.display_panels if p.instance_number == instance]
        return int(panels[0].code_map[WHITE]) if panels else None

    async def scheme(self) -> Scheme | None:
        from ..schemes import Ink, Scheme, scheme_for_firmware_id  # pylint: disable=import-outside-toplevel

        if self._calibration is None:
            return scheme_for_firmware_id(int(self._device.color_scheme))

        from opendisplay.encoding.multipass import (  # pylint: disable=import-outside-toplevel,import-error,no-name-in-module
            mode_palette,
        )

        passes = self._mode.passes
        codes = [tuple(e.code_for_pass(p) for p in range(passes)) for e in self._calibration.entries]
        names = entry_names(codes, self._white_code())
        preview = mode_palette(self._calibration).preview_rgb()
        inks = tuple(Ink(n, f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}") for n, rgb in zip(names, preview, strict=True))
        return Scheme(self._mode.name.lower(), inks)

    async def _show_entry(self, index: int, ink: Ink) -> None:
        import numpy as np  # pylint: disable=import-outside-toplevel
        from epaper_dithering import DitherMode  # pylint: disable=import-outside-toplevel
        from opendisplay.device.imaging import (  # pylint: disable=import-outside-toplevel,import-error,no-name-in-module
            prepare_multipass,
        )

        profile = self._drive.profile
        size = (profile.width, profile.height)
        image = solid_image(ink, size)
        config = self._drive.config.cached
        # The entry's own (white-relative) colour, undithered, must encode as that entry alone.
        _, preview = await asyncio.to_thread(prepare_multipass, image, config, self._mode, dither_mode=DitherMode.NONE)
        used = np.unique(np.asarray(preview))
        if used.tolist() != [index]:
            raise RuntimeError(f"solid {ink.name} did not encode as entry {index} alone (got entries {used.tolist()})")
        temp_c = await self._upload_with_retry(image)
        if temp_c is not None:
            print(f"  panel at {temp_c} °C", file=sys.stderr)
        await asyncio.sleep(self._settle)

    async def _upload_with_retry(self, image: Image) -> Any:
        """Upload in the drive mode; if the link stalls, reconnect and upload once more."""
        from epaper_dithering import DitherMode  # pylint: disable=import-outside-toplevel
        from opendisplay.exceptions import (  # pylint: disable=import-outside-toplevel,import-error
            BLEConnectionError,
            BLETimeoutError,
        )

        for attempt in range(2):
            try:
                return await self._drive.display.show(image, mode=self._mode.name, dither_mode=DitherMode.NONE)
            except (BLETimeoutError, BLEConnectionError) as exc:
                if attempt:
                    raise
                print(f"  upload stalled ({exc}); reconnecting and trying again", file=sys.stderr)
                with contextlib.suppress(Exception):  # the stalled link may already be gone
                    await self._drive.__aexit__(None, None, None)
                self._drive = None
                await self._connect_drive_mode(self._mode.name)
        return None

    async def show(self, index: int, ink: Ink) -> None:
        if self._calibration is not None:
            await self._show_entry(index, ink)
            return
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
        if self._drive is not None:
            await self._drive.__aexit__(None, None, None)
            self._drive = None
        if self._device is not None:
            await self._device.__aexit__(None, None, None)
            self._device = None
