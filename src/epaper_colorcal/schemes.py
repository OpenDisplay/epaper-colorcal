"""Color-scheme definitions — the firmware contract.

Color *order* is the index order the firmware expects, and the names are the ink
names ``epaper-dithering`` palettes use. Both MUST match ``py-opendisplay``'s
palette files (``src/opendisplay/palettes/``), which the emitted palette joins.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scheme:
    name: str
    """Our CLI / firmware name, e.g. "BWGBRY"."""
    firmware_id: int
    """Integer value of the scheme in OpenDisplay firmware (``ColorScheme``)."""
    colors: tuple[str, ...]
    """Color names in measurement / firmware order."""

    @property
    def count(self) -> int:
        return len(self.colors)


# Order as in py-opendisplay's palette files.
SCHEMES: dict[str, Scheme] = {
    "MONO": Scheme("MONO", 0, ("black", "white")),
    "BWR": Scheme("BWR", 1, ("black", "white", "red")),
    "BWY": Scheme("BWY", 2, ("black", "white", "yellow")),
    "BWRY": Scheme("BWRY", 3, ("black", "white", "yellow", "red")),
    "BWGBRY": Scheme("BWGBRY", 4, ("black", "white", "yellow", "red", "blue", "green")),
}


def get_scheme(name: str) -> Scheme:
    key = name.upper()
    if key not in SCHEMES:
        valid = ", ".join(SCHEMES)
        raise ValueError(f"unknown scheme {name!r}; choose one of: {valid}")
    return SCHEMES[key]
