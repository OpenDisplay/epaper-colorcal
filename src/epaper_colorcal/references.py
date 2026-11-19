"""Reference charts with published values, for checking an instrument.

The X-Rite / Calibrite ColorChecker Classic (24 patches) comes from colour-science, which ships
the manufacturer's reference values. Charts made since November 2014 use a new formulation;
``before_2014`` selects the older one.
"""

from __future__ import annotations

import re

from .schemes import Ink, Scheme


def _patch_name(name: str) -> str:
    """'white 9.5 (.05 D)' -> 'white_9_5', 'dark skin' -> 'dark_skin'."""
    name = re.sub(r"\(.*?\)", "", name).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def colorchecker24_lab(*, before_2014: bool = False) -> dict[str, tuple[float, float, float]]:
    """The 24 patches' reference CIELAB (D50, 2°), in chart order (dark skin ... black 2)."""
    import colour  # pylint: disable=import-outside-toplevel  # heavy; only when a chart is used

    key = "ColorChecker24 - Before November 2014" if before_2014 else "ColorChecker24 - After November 2014"
    chart = colour.CCS_COLOURCHECKERS[key]
    out = {}
    for name, xyy in chart.data.items():
        lab = colour.XYZ_to_Lab(colour.xyY_to_XYZ(xyy), chart.illuminant)
        out[_patch_name(name)] = (float(lab[0]), float(lab[1]), float(lab[2]))
    return out


def colorchecker24_scheme(*, before_2014: bool = False) -> Scheme:
    """The chart's patches as inks (for --static manual measurement), nominal = reference sRGB."""
    import colour  # pylint: disable=import-outside-toplevel
    import numpy as np  # pylint: disable=import-outside-toplevel

    d50 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
    inks = []
    for name, lab in colorchecker24_lab(before_2014=before_2014).items():
        xyz = colour.Lab_to_XYZ(lab, d50)
        rgb = colour.XYZ_to_sRGB(xyz, illuminant=d50, chromatic_adaptation_transform="Bradford")
        r, g, b = (int(round(float(c) * 255)) for c in np.clip(rgb, 0, 1))
        inks.append(Ink(name, f"#{r:02x}{g:02x}{b:02x}"))
    return Scheme("COLORCHECKER24", tuple(inks))
