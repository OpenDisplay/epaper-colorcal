"""Output adapters: one measurement, several documents."""

from __future__ import annotations

import json
from datetime import date

import pytest
from epaper_dithering import Palette

from epaper_colorcal.measure import measure_color
from epaper_colorcal.measure_palette import main
from epaper_colorcal.outputs import OUTPUTS, Measurement, get_output
from epaper_colorcal.schemes import Scheme, get_scheme, parse_inks
from epaper_colorcal.synthetic import IDEAL_SRGB, synthetic_spd


def _measurement(scheme: Scheme) -> Measurement:
    colors = [measure_color(n, [synthetic_spd(IDEAL_SRGB.get(n, (128, 128, 128)))]) for n in scheme.colors]
    return Measurement(
        "T", scheme, colors, instrument="CHNSpec CR30", serial="S1", temperature_c=21, measured_on=date(2026, 11, 19)
    )


def test_formats_are_registered() -> None:
    assert set(OUTPUTS) == {"epaper-palette", "oepl", "spectra"}
    with pytest.raises(ValueError, match="choose one of"):
        get_output("csv")


def test_epaper_palette_output_loads_in_epaper_dithering() -> None:
    palette = Palette.from_json(get_output("epaper-palette").render(_measurement(get_scheme("BWRY"))))
    assert len(palette) == 4
    assert palette.source.endswith("measured 2026-11-19, D65/2°, panel at 21°C")


def test_oepl_output_is_white_relative_srgb_for_every_colour_in_order() -> None:
    # OEPL's tag-type order is white, black, red, yellow; the block must follow the scheme's order.
    scheme = parse_inks("white,black,red,yellow")
    text = get_output("oepl").render(_measurement(scheme))
    perceptual = json.loads(text)["perceptual"]

    assert list(perceptual) == ["white", "black", "red", "yellow"]  # every colour, none missing
    assert perceptual["white"] == [255, 255, 255]
    assert all(len(v) == 3 and all(0 <= c <= 255 for c in v) for v in perceptual.values())
    assert perceptual["black"][0] < 100 and perceptual["red"][0] > perceptual["red"][2]
    assert '"yellow": [' in text  # colours inline, as in the tag-type files


def test_oepl_output_uses_oepl_order_whatever_the_scheme_order() -> None:
    # e.g. measured over ATC BLE, where the scheme comes in OpenDisplay order
    text = get_output("oepl").render(_measurement(get_scheme("BWRY")))  # black, white, yellow, red
    assert list(json.loads(text)["perceptual"]) == ["white", "black", "red", "yellow"]


def test_spectra_output_has_the_raw_reads() -> None:
    data = json.loads(get_output("spectra").render(_measurement(get_scheme("MONO"))))
    assert data["instrument"] == "CHNSpec CR30" and len(data["wavelengths_nm"]) == 31
    assert [c["name"] for c in data["colors"]] == ["black", "white"]


def test_cli_format_oepl(capsys) -> None:
    assert main(["--inks", "white,black,red", "--id", "S", "--temp", "20", "--dry-run", "--format", "oepl"]) == 0
    assert list(json.loads(capsys.readouterr().out)["perceptual"]) == ["white", "black", "red"]
