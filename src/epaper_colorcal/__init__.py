"""epaper-colorcal.

Drive a spectrophotometer (the CHNSpec CR30) to produce measured e-paper colour
palettes (``epaper-palette`` JSON) for OpenDisplay's epaper-dithering.
"""

from .colorimetry import ColorReading, average_spds, reading_from_spd, reading_from_spectrum
from .emit import MeasuredColor, build_palette, render_palette, spectra_sidecar
from .instruments import Instrument
from .measure_palette import build_colors, main, measure_color
from .schemes import SCHEMES, Ink, Scheme, get_scheme, parse_inks
from .spectrum import Spectrum
from .synthetic import synthetic_spd

__version__ = "0.6.1"

__all__ = [
    "SCHEMES",
    "ColorReading",
    "Ink",
    "Instrument",
    "MeasuredColor",
    "Scheme",
    "Spectrum",
    "__version__",
    "average_spds",
    "build_colors",
    "build_palette",
    "get_scheme",
    "main",
    "measure_color",
    "parse_inks",
    "reading_from_spd",
    "reading_from_spectrum",
    "render_palette",
    "spectra_sidecar",
    "synthetic_spd",
]
