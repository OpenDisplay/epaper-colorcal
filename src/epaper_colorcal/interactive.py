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

Hardware-dependent parts are flagged ``HARDWARE TODO`` — they need a real panel + CR30
to validate and must not be trusted until then.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .colorimetry import average_spds, reading_from_spd
from .emit_rust import MeasuredColor
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
        settle_seconds: float = 25.0,
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

        device = OpenDisplayDevice(self._address)
        # Manual context-manager lifecycle: the device must stay open between connect()
        # and close(), and its only open mechanism is the async context manager.
        await device.__aenter__()  # pylint: disable=unnecessary-dunder-call
        if self._key is not None:
            await device.authenticate(self._key)
        await device.interrogate()
        self._device = device

    async def show_color(self, index: int, name: str) -> None:
        if self._device is None:
            raise RuntimeError("connect() must be called before show_color()")

        image = self._solid_ink_image(index)
        # HARDWARE TODO: this currently sends a solid RGB image and lets the library
        # quantize it. To measure ink `index` cleanly we must push the *palette index*
        # directly (no measured-palette remapping), otherwise the result is circular —
        # we'd be measuring through the palette we're trying to measure. Verify the
        # right py-opendisplay path (upload_prepared_image / a NONE-dither index image)
        # against real hardware.
        from epaper_dithering import DitherMode  # provided transitively by py-opendisplay

        await self._device.upload_image(image, dither_mode=DitherMode.NONE)

        # HARDWARE TODO: upload_image returns when data is sent, not when the e-paper has
        # physically settled (color refresh is ~15-30s and flashes mid-refresh). Tune this
        # settle delay against a real panel; consider reading twice and comparing ΔE.
        await asyncio.sleep(self._settle)

    def _solid_ink_image(self, index: int):  # type: ignore[no-untyped-def]
        """Build a full-screen solid image of the scheme's color at ``index``.

        Placeholder geometry until the device reports real dimensions; sized large
        enough to exceed the CR30's reading window after fit/scale.
        """
        from PIL import Image

        from .synthetic import IDEAL_SRGB

        rgb = IDEAL_SRGB.get(self._scheme.colors[index], (128, 128, 128))
        # HARDWARE TODO: use self._device.width/height once connected.
        return Image.new("RGB", (800, 480), rgb)

    async def close(self) -> None:
        if self._device is not None:
            await self._device.__aexit__(None, None, None)
            self._device = None

    @property
    def serial(self) -> str:
        name = getattr(self._device, "device_name", None)
        return str(name) if name else self._address
