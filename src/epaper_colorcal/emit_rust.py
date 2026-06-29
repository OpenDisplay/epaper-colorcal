"""Emit a ready-to-paste Rust ``Palette`` block + CATALOG entry for measured_palettes.rs.

Also produces a JSON sidecar with the raw spectra so a measurement can be
re-processed later (e.g. for kepstin's "define the gamut as a volume in XYZ"
idea) without re-measuring the panel.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from .colorimetry import CR30_WAVELENGTHS, ColorReading
from .schemes import Scheme


@dataclass(frozen=True)
class MeasuredColor:
    """One measured color: its reading plus the raw spectra it came from."""

    name: str
    reading: ColorReading
    spds: list[list[float]]
    """The individual SPD reads (before averaging) for this color."""


def _color_row(name: str, reading: ColorReading) -> str:
    r, g, b = reading.srgb
    lab = ", ".join(f"{v:g}" for v in reading.lab_d50)
    flag = "  ⚠ out-of-gamut (clamped)" if reading.clipped else ""
    # Right-align channels to width 3 to match the existing measured_palettes.rs style.
    return f"        [{r:>3}, {g:>3}, {b:>3}],  // {name:<7} L*a*b* D50 [{lab}]{flag}"


def _temp_phrase(temperature_c: float | None) -> str:
    """Panel temperature clause for the Rust comment.

    e-paper color is temperature-dependent (see OpenDisplay #color-calibration:
    cold panels shift color noticeably and even select a different LUT), so a
    measured palette is only valid near the temperature it was captured at.
    """
    if temperature_c is None:
        return "panel temperature UNRECORDED — re-measure with --temp"
    return f"panel @ {temperature_c:g}°C"


def render_rust_palette(
    palette_id: str,
    scheme: Scheme,
    colors: list[MeasuredColor],
    *,
    serial: str = "unknown",
    note: str = "",
    measured_on: date | None = None,
    temperature_c: float | None = None,
) -> str:
    """Render the ``pub static <ID>: Palette { ... }`` block."""
    if len(colors) != scheme.count:
        raise ValueError(f"scheme {scheme.name} needs {scheme.count} colors, got {len(colors)}")

    on = (measured_on or date.today()).isoformat()
    accent_name = scheme.colors[scheme.accent_idx]
    rows = "\n".join(_color_row(c.name, c.reading) for c in colors)
    doc = f"/// {note}\n" if note else ""

    return (
        f"{doc}"
        f"/// Measured {on}, CHNSpec CR30 (s/n {serial}), sRGB under D65/2°, {_temp_phrase(temperature_c)}.\n"
        f"pub static {palette_id}: Palette = Palette {{\n"
        f"    colors: Cow::Borrowed(&[\n"
        f"{rows}\n"
        f"    ]),\n"
        f"    accent_idx: {scheme.accent_idx}, // {accent_name}\n"
        f"}};"
    )


def render_catalog_entry(palette_id: str, scheme: Scheme) -> str:
    """Render the matching ``MeasuredPaletteEntry`` for the CATALOG slice."""
    names = ", ".join(f'"{n}"' for n in scheme.colors)
    return (
        f"    MeasuredPaletteEntry {{\n"
        f'        id: "{palette_id}",\n'
        f"        palette: &{palette_id},\n"
        f"        scheme: ColorScheme::{scheme.rust_variant},\n"
        f"        color_names: &[{names}],\n"
        f"    }},"
    )


def render_python_reminder(palette_id: str) -> str:
    """The two Python edits needed in epaper-dithering after pasting the Rust."""
    return (
        f"# In packages/python/src/epaper_dithering/palettes.py:\n"
        f'{palette_id}: ColorPalette = _MEASURED["{palette_id}"]\n'
        f"# ...and export {palette_id} from packages/python/src/epaper_dithering/__init__.py"
    )


def spectra_sidecar(
    palette_id: str,
    scheme: Scheme,
    colors: list[MeasuredColor],
    *,
    serial: str = "unknown",
    measured_on: date | None = None,
    temperature_c: float | None = None,
) -> dict[str, Any]:
    """Build the raw-spectra JSON sidecar payload."""
    return {
        "id": palette_id,
        "scheme": scheme.name,
        "firmware_id": scheme.firmware_id,
        "instrument": "CHNSpec CR30",
        "serial": serial,
        "measured_on": (measured_on or date.today()).isoformat(),
        "temperature_c": temperature_c,
        "wavelengths_nm": CR30_WAVELENGTHS,
        "colors": [
            {
                "name": c.name,
                "srgb_d65": list(c.reading.srgb),
                "lab_d50": list(c.reading.lab_d50),
                "xyz_d65": list(c.reading.xyz_d65),
                "out_of_gamut": c.reading.clipped,
                "spd_reads": c.spds,
            }
            for c in colors
        ],
    }


def render_full_output(
    palette_id: str,
    scheme: Scheme,
    colors: list[MeasuredColor],
    *,
    serial: str = "unknown",
    note: str = "",
    measured_on: date | None = None,
    temperature_c: float | None = None,
) -> str:
    """Assemble the human-facing console output (Rust + CATALOG + Python reminder)."""
    palette = render_rust_palette(
        palette_id,
        scheme,
        colors,
        serial=serial,
        note=note,
        measured_on=measured_on,
        temperature_c=temperature_c,
    )
    catalog = render_catalog_entry(palette_id, scheme)
    reminder = render_python_reminder(palette_id)
    return (
        "// ── Paste into packages/rust/core/src/measured_palettes.rs ──\n\n"
        f"{palette}\n\n"
        "// ── Add to the CATALOG slice in the same file ──\n\n"
        f"{catalog}\n\n"
        f"{reminder}\n"
    )


def write_sidecar(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
