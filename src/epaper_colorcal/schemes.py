"""Color-scheme definitions — the firmware contract shared with epaper-dithering.

Color *order*, names, accent index and the firmware scheme id MUST match
``epaper-dithering``'s ``measured_palettes.rs`` (CATALOG ``color_names`` and
``accent_idx``) and ``palettes.py`` (``ColorScheme`` enum values), because the
emitted palette is pasted straight into that crate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scheme:
    name: str
    """Our CLI / firmware name, e.g. "BWGBRY"."""
    rust_variant: str
    """Rust ``ColorScheme`` variant, e.g. "Bwgbry"."""
    firmware_id: int
    """Integer value used by OpenDisplay firmware + palettes.py ColorScheme."""
    colors: tuple[str, ...]
    """Color names in measurement / firmware order."""
    accent_idx: int
    """Index into ``colors`` of the accent color."""

    @property
    def count(self) -> int:
        return len(self.colors)


# Order and accents copied verbatim from measured_palettes.rs CATALOG.
SCHEMES: dict[str, Scheme] = {
    "MONO": Scheme("MONO", "Mono", 0, ("black", "white"), 0),
    "BWR": Scheme("BWR", "Bwr", 1, ("black", "white", "red"), 2),
    "BWY": Scheme("BWY", "Bwy", 2, ("black", "white", "yellow"), 2),
    "BWRY": Scheme("BWRY", "Bwry", 3, ("black", "white", "yellow", "red"), 3),
    "BWGBRY": Scheme("BWGBRY", "Bwgbry", 4, ("black", "white", "yellow", "red", "blue", "green"), 3),
}


def get_scheme(name: str) -> Scheme:
    key = name.upper()
    if key not in SCHEMES:
        valid = ", ".join(SCHEMES)
        raise ValueError(f"unknown scheme {name!r}; choose one of: {valid}")
    return SCHEMES[key]
