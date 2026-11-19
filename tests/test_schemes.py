"""Inks, presets and custom ink lists."""

from __future__ import annotations

import pytest

from epaper_colorcal.emit import MeasuredColor, build_palette, paper_white_index
from epaper_colorcal.measure import measure_color
from epaper_colorcal.schemes import SCHEMES, Ink, get_scheme, parse_inks, scheme_for_firmware_id
from epaper_colorcal.synthetic import synthetic_spd


def test_presets_keep_firmware_order_and_ids() -> None:
    # Order and ids must match OpenDisplay's ColorScheme and epaper-dithering's palette files.
    assert get_scheme("BWGBRY").colors == ("black", "white", "yellow", "red", "blue", "green")
    assert get_scheme("BWRY").colors == ("black", "white", "yellow", "red")
    assert get_scheme("SEVEN_COLOR").colors[-1] == "orange"
    assert {name: s.firmware_id for name, s in SCHEMES.items()} == {
        "MONO": 0, "BWR": 1, "BWY": 2, "BWRY": 3, "BWGBRY": 4, "GRAY4": 5, "GRAY16": 6, "SEVEN_COLOR": 7,
    }  # fmt: skip


def test_gray_presets_are_evenly_spaced_like_the_ideal_palettes() -> None:
    assert [i.nominal for i in get_scheme("GRAY4").inks] == ["#000000", "#555555", "#aaaaaa", "#ffffff"]
    gray16 = get_scheme("GRAY16").inks
    assert len(gray16) == 16
    assert (gray16[1].name, gray16[1].nominal, gray16[14].nominal) == ("gray1", "#111111", "#eeeeee")


@pytest.mark.parametrize(("alias", "name"), [("grayscale_4", "GRAY4"), ("acep", "SEVEN_COLOR"), ("bwgbry", "BWGBRY")])
def test_scheme_names_are_case_insensitive_with_aliases(alias: str, name: str) -> None:
    assert get_scheme(alias).name == name


def test_scheme_for_firmware_id() -> None:
    assert scheme_for_firmware_id(4) == get_scheme("BWGBRY")
    assert scheme_for_firmware_id(100) is None  # e.g. RGB565: no ink set


def test_parse_inks_fills_known_colours_and_keeps_order() -> None:
    scheme = parse_inks(" Black , white,orange=#FF8000,teal=#008080")
    assert scheme.name == "CUSTOM" and scheme.firmware_id is None
    assert [(i.name, i.nominal) for i in scheme.inks] == [
        ("black", "#000000"),
        ("white", "#ffffff"),
        ("orange", "#ff8000"),
        ("teal", "#008080"),
    ]


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("black,white,teal", "teal=#rrggbb"),
        ("black,white,red=#f00", "#rrggbb"),
        ("black,white,black", "repeats"),
        ("white", "at least two"),
        ("black,white,deep red=#800000", "lowercase"),
    ],
)
def test_parse_inks_rejects_bad_specs(spec: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_inks(spec)


def test_ink_rgb() -> None:
    assert Ink("orange", "#ff8000").rgb == (255, 128, 0)


def _measured(name: str, rgb: tuple[int, int, int]) -> MeasuredColor:
    return measure_color(name, [synthetic_spd(rgb)])


def test_paper_white_is_the_white_ink_or_else_the_lightest() -> None:
    named = [_measured("black", (20, 20, 20)), _measured("paper", (250, 250, 250)), _measured("white", (180, 180, 180))]
    assert paper_white_index(named) == 2
    unnamed = [_measured("dark", (20, 20, 20)), _measured("paper", (240, 240, 240)), _measured("mid", (128, 128, 128))]
    assert paper_white_index(unnamed) == 1


def test_a_custom_palette_without_white_normalises_to_the_lightest_ink() -> None:
    scheme = parse_inks("black,paper=#f0f0f0")
    palette = build_palette(scheme, [_measured("black", (20, 20, 20)), _measured("paper", (240, 240, 240))])
    paper = next(e for e in palette.entries if e.name == "paper")
    assert paper.appearance == pytest.approx((100.0, 0.0, 0.0), abs=1e-6)
