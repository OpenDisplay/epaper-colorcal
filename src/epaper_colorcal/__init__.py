"""epaper-colorcal.

Drive a CHNSpec CR30 spectral colorimeter to produce measured e-paper color
palettes (``epaper-palette`` JSON) for OpenDisplay's epaper-dithering.
"""

from .colorimetry import ColorReading, average_spds, reading_from_spd
from .emit import MeasuredColor, build_palette, render_palette, spectra_sidecar
from .measure_palette import build_colors, main, measure_color
from .schemes import SCHEMES, Scheme, get_scheme
from .synthetic import synthetic_spd

__version__ = "0.1.0"

__all__ = [
    "SCHEMES",
    "ColorReading",
    "MeasuredColor",
    "Scheme",
    "__version__",
    "average_spds",
    "build_colors",
    "build_palette",
    "get_scheme",
    "main",
    "measure_color",
    "reading_from_spd",
    "render_palette",
    "spectra_sidecar",
    "synthetic_spd",
]
