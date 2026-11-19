"""Interactive mode: drive an OpenDisplay panel + CR30 to auto-measure a palette.

The operator seats the CR30 on the panel once; the software then cycles the panel
through each solid ink while the scanner stays put, reading after each. This removes
the manual image-sending and scanner repositioning, and makes measurements repeatable
(same panel spot, same scanner seating for every color).

Two halves:

* a :class:`PanelDriver` that shows a given ink full-screen, and
* an SPD source (one reflectance read for a color).

:func:`measure_interactive` orchestrates them and reuses the same averaging +
colorimetry as the manual path. A :class:`SimPanel` + synthetic SPD source make the
orchestration testable with no hardware.

The BLE panel path was validated on a Spectra 6 7.3\" (BWGBRY) with a CR30.
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .colorimetry import average_spds, reading_from_spd
from .emit import MeasuredColor
from .schemes import Scheme

# One reflectance read for a color (async because the real source talks to the CR30).
SpdSource = Callable[[str], Awaitable[list[float]]]


class PanelDriver(Protocol):
    """Shows a solid ink full-screen on the panel and waits for it to settle."""

    async def show_color(self, index: int, name: str) -> None: ...

    async def close(self) -> None: ...


async def measure_interactive(
    scheme: Scheme,
    panel: PanelDriver,
    spd_source: SpdSource,
    count: int,
) -> list[MeasuredColor]:
    """Cycle the panel through each scheme color, averaging ``count`` CR30 reads each."""
    colors: list[MeasuredColor] = []
    for index, name in enumerate(scheme.colors):
        await panel.show_color(index, name)
        reads = [await spd_source(name) for _ in range(count)]
        colors.append(MeasuredColor(name=name, reading=reading_from_spd(average_spds(reads)), spds=reads))
    return colors


# Advertised chip temperatures outside this range are treated as "no reading" (some boards
# advertise -40 °C, the encoding's floor, when they have no valid value).
PLAUSIBLE_BOARD_TEMP_C = (-20.0, 60.0)


async def read_board_temperature(address: str, timeout: float = 8.0) -> float | None:
    """The OpenDisplay board's advertised MCU temperature, read from a scan without connecting.

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


# ── Simulated panel (no hardware) ─────────────────────────────────────────────


class SimPanel:
    """Stand-in panel for ``--dry-run --interactive``: logs what it would show."""

    def __init__(self, settle_seconds: float = 0.0) -> None:
        self._settle = settle_seconds

    async def show_color(self, index: int, name: str) -> None:
        print(f"[sim] would display solid ink {index} ({name}); settle {self._settle:g}s", file=sys.stderr)
        await asyncio.sleep(0)

    async def close(self) -> None:
        await asyncio.sleep(0)


# ── Real OpenDisplay panel over BLE ───────────────────────────────────────────


class OpenDisplayPanel:
    """Drive a real OpenDisplay device over BLE via ``py-opendisplay``.

    Requires the ``opendisplay`` extra (``pip install 'epaper-colorcal[opendisplay]'``).
    """

    def __init__(
        self,
        address: str,
        scheme: Scheme,
        key: bytes | None = None,
        settle_seconds: float = 3.0,
    ) -> None:
        self._address = address
        self._scheme = scheme
        self._key = key
        self._settle = settle_seconds
        self._device: Any = None

    async def connect(self) -> None:
        try:
            from opendisplay import OpenDisplayDevice
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise SystemExit(
                "Interactive mode needs py-opendisplay. Install it with:\n"
                "    pip install 'epaper-colorcal[opendisplay]'"
            ) from exc

        # Accept a MAC (Linux/Windows), a CoreBluetooth UUID (macOS), or an advertised name.
        if re.fullmatch(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}|[0-9A-Fa-f-]{36}", self._address):
            device = OpenDisplayDevice(mac_address=self._address)
        else:
            device = OpenDisplayDevice(device_name=self._address)
        # Manual context-manager lifecycle: the device must stay open between connect()
        # and close(), and its only open mechanism is the async context manager.
        await device.__aenter__()  # pylint: disable=unnecessary-dunder-call
        if self._key is not None:
            await device.authenticate(self._key)
        await device.interrogate()
        if device.color_scheme.name != self._scheme.name:
            await device.__aexit__(None, None, None)
            raise SystemExit(
                f"panel reports color scheme {device.color_scheme.name}, but --scheme is {self._scheme.name}"
            )
        self._device = device

    async def show_color(self, index: int, name: str) -> None:
        if self._device is None:
            raise RuntimeError("connect() must be called before show_color()")

        from epaper_dithering import DitherMode  # provided transitively by py-opendisplay
        from opendisplay import prepare_image  # pylint: disable=import-error  # extra; connect() checked it

        device = self._device
        image = self._solid_ink_image(index, (device.width, device.height))
        prepared = prepare_image(
            image, config=device.config, dither_mode=DitherMode.NONE, compress=self._supports_zip()
        )
        n_colors = len(prepared[2].convert("RGB").getcolors(maxcolors=2) or [None, None])
        if n_colors != 1:
            raise RuntimeError(f"solid {name} did not quantize to a single ink (got {n_colors}+ colours)")

        # upload_prepared_image returns only after the device reports refresh complete
        # (DIRECT_WRITE_REFRESH_COMPLETE), so `settle` is just a small safety margin.
        await device.upload_prepared_image(prepared)
        await asyncio.sleep(self._settle)

    def _solid_ink_image(self, index: int, size: tuple[int, int] = (800, 480)):  # type: ignore[no-untyped-def]
        """Full-screen image of the nominal colour of the scheme's ink at ``index``.

        The nominal colour is what epaper-dithering always maps to that ink, so the panel
        shows the pure ink whatever palette the device is using (no circular measurement).
        """
        from PIL import Image

        from .emit import NOMINALS

        return Image.new("RGB", size, NOMINALS[self._scheme.colors[index]])

    def _supports_zip(self) -> bool:
        config = self._device.config
        return bool(config.displays[0].supports_zip) if config and config.displays else True

    async def close(self) -> None:
        if self._device is not None:
            await self._device.__aexit__(None, None, None)
            self._device = None

    @property
    def serial(self) -> str:
        name = getattr(self._device, "device_name", None)
        return str(name) if name else self._address
