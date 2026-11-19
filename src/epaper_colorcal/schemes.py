"""Inks and schemes: which colours a panel can show, in which order.

A :class:`Scheme` is an ordered list of :class:`Ink`. The order is the index order the
panel's firmware uses, and each ink has a *nominal* colour: what you draw to get that ink
solid, and what requests it in an ``epaper-palette`` file.

The presets match OpenDisplay's ``ColorScheme`` (firmware ids) and the ink names and order
of ``epaper-dithering``'s palette files. Any other panel can be described with
:func:`parse_inks` (``--inks black,white,orange=#ff8000``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME = re.compile(r"[a-z][a-z0-9_]*")
_HEX = re.compile(r"#[0-9a-f]{6}")


@dataclass(frozen=True)
class Ink:
    """One colour a panel can show solid."""

    name: str
    nominal: str
    """The colour that requests this ink, as ``#rrggbb``."""

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ValueError(f"ink name {self.name!r} must be lowercase letters, digits or _")
        if not _HEX.fullmatch(self.nominal):
            raise ValueError(f"ink {self.name!r}: nominal {self.nominal!r} must be #rrggbb")

    @property
    def rgb(self) -> tuple[int, int, int]:
        value = int(self.nominal[1:], 16)
        return (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF


@dataclass(frozen=True)
class Scheme:
    """An ordered set of inks: what to measure, in firmware index order."""

    name: str
    inks: tuple[Ink, ...]
    firmware_id: int | None = None
    """OpenDisplay ``ColorScheme`` value, for presets that have one."""

    def __post_init__(self) -> None:
        if len(self.inks) < 2:
            raise ValueError(f"scheme {self.name} needs at least two inks")
        names = [ink.name for ink in self.inks]
        if len(set(names)) != len(names):
            raise ValueError(f"scheme {self.name} repeats an ink: {names}")

    @property
    def colors(self) -> tuple[str, ...]:
        """Ink names in order."""
        return tuple(ink.name for ink in self.inks)

    @property
    def count(self) -> int:
        return len(self.inks)

    def ink(self, name: str) -> Ink:
        return self.inks[self.colors.index(name)]


# Nominal colours of named inks, so --inks can name them without a hex value.
KNOWN_NOMINALS: dict[str, str] = {
    "black": "#000000",
    "white": "#ffffff",
    "yellow": "#ffff00",
    "red": "#ff0000",
    "blue": "#0000ff",
    "green": "#00ff00",
    "orange": "#ff8000",
}


def _inks(*names: str) -> tuple[Ink, ...]:
    return tuple(Ink(name, KNOWN_NOMINALS[name]) for name in names)


def _grays(levels: int) -> tuple[Ink, ...]:
    """black, gray1 … gray(n-2), white, evenly spaced (as epaper-dithering's ideal palettes)."""
    step = 255 // (levels - 1)
    middle = tuple(Ink(f"gray{i}", f"#{i * step:02x}{i * step:02x}{i * step:02x}") for i in range(1, levels - 1))
    return (Ink("black", "#000000"), *middle, Ink("white", "#ffffff"))


SCHEMES: dict[str, Scheme] = {
    "MONO": Scheme("MONO", _inks("black", "white"), 0),
    "BWR": Scheme("BWR", _inks("black", "white", "red"), 1),
    "BWY": Scheme("BWY", _inks("black", "white", "yellow"), 2),
    "BWRY": Scheme("BWRY", _inks("black", "white", "yellow", "red"), 3),
    "BWGBRY": Scheme("BWGBRY", _inks("black", "white", "yellow", "red", "blue", "green"), 4),
    "GRAY4": Scheme("GRAY4", _grays(4), 5),
    "GRAY16": Scheme("GRAY16", _grays(16), 6),
    "SEVEN_COLOR": Scheme("SEVEN_COLOR", _inks("black", "white", "yellow", "red", "blue", "green", "orange"), 7),
}
_ALIASES = {"GRAYSCALE_4": "GRAY4", "GRAYSCALE_16": "GRAY16", "ACEP": "SEVEN_COLOR", "BW": "MONO"}


def get_scheme(name: str) -> Scheme:
    """A preset by name (case-insensitive). ``COLORCHECKER24`` is the 24-patch reference chart."""
    key = _ALIASES.get(name.upper(), name.upper())
    if key in ("COLORCHECKER24", "COLORCHECKER"):
        from .references import colorchecker24_scheme  # pylint: disable=import-outside-toplevel,cyclic-import

        return colorchecker24_scheme()
    if key not in SCHEMES:
        raise ValueError(f"unknown scheme {name!r}; choose one of: {', '.join(SCHEMES)}, COLORCHECKER24")
    return SCHEMES[key]


def scheme_for_firmware_id(firmware_id: int) -> Scheme | None:
    """The preset for an OpenDisplay ``ColorScheme`` value, or None if there isn't one."""
    return next((s for s in SCHEMES.values() if s.firmware_id == firmware_id), None)


def parse_inks(spec: str) -> Scheme:
    """A custom scheme from ``"black,white,orange=#ff8000"``, in the order given.

    Inks in :data:`KNOWN_NOMINALS` may omit the colour; any other ink needs ``=#rrggbb``.
    """
    inks = []
    for item in (part.strip() for part in spec.split(",")):
        name, _, nominal = (s.strip().lower() for s in item.partition("="))
        if not nominal:
            if name not in KNOWN_NOMINALS:
                raise ValueError(f"ink {name!r} needs a colour, e.g. {name}=#rrggbb")
            nominal = KNOWN_NOMINALS[name]
        inks.append(Ink(name, nominal))
    return Scheme("CUSTOM", tuple(inks))
