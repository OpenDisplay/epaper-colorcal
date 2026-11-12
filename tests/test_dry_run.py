"""Dry-run pipeline tests — no CR30 hardware required."""

from __future__ import annotations

import json
from datetime import date

import pytest
from epaper_dithering import Palette

from epaper_colorcal.colorimetry import average_spds, reading_from_spd
from epaper_colorcal.emit import MeasuredColor, render_palette, spectra_sidecar
from epaper_colorcal.measure_palette import _dry_run_provider, build_colors, main, measure_color
from epaper_colorcal.schemes import Scheme, get_scheme
from epaper_colorcal.synthetic import IDEAL_SRGB, synthetic_spd


def test_vendored_packets_import_without_serial() -> None:
    # The pure-Python packet layer must be importable without pyserial-asyncio.
    from epaper_colorcal._vendor.cr30 import CR30Packet, PacketParser

    assert CR30Packet is not None and PacketParser is not None


def test_synthetic_spd_shape_and_range() -> None:
    spd = synthetic_spd((128, 128, 128))
    assert len(spd) == 31
    assert all(0.0 <= v <= 1.0 for v in spd)


def test_white_is_lighter_than_black() -> None:
    black = reading_from_spd(synthetic_spd(IDEAL_SRGB["black"]))
    white = reading_from_spd(synthetic_spd(IDEAL_SRGB["white"]))
    assert white.lab_d50[0] > black.lab_d50[0]
    assert sum(white.srgb) > sum(black.srgb)


def test_hue_directions() -> None:
    red = reading_from_spd(synthetic_spd(IDEAL_SRGB["red"]))
    blue = reading_from_spd(synthetic_spd(IDEAL_SRGB["blue"]))
    yellow = reading_from_spd(synthetic_spd(IDEAL_SRGB["yellow"]))
    green = reading_from_spd(synthetic_spd(IDEAL_SRGB["green"]))
    assert red.lab_d50[1] > 0  # a* positive → red
    assert blue.lab_d50[2] < 0  # b* negative → blue
    assert yellow.lab_d50[2] > 0  # b* positive → yellow
    assert green.lab_d50[1] < 0  # a* negative → green


def test_average_spds() -> None:
    avg = average_spds([[0.0] * 31, [1.0] * 31])
    assert avg == [0.5] * 31


def test_build_colors_order_and_count() -> None:
    scheme = get_scheme("BWGBRY")
    colors = build_colors(scheme, _dry_run_provider(count=3))
    assert [c.name for c in colors] == list(scheme.colors)
    assert all(len(c.spds) == 3 for c in colors)
    for c in colors:
        assert all(0 <= ch <= 255 for ch in c.reading.srgb)


def _dry_colors(scheme_name: str, count: int = 2) -> tuple[Scheme, list[MeasuredColor]]:
    scheme = get_scheme(scheme_name)
    return scheme, build_colors(scheme, _dry_run_provider(count=count))


def test_palette_has_the_scheme_inks_in_firmware_order_with_white_normalised() -> None:
    scheme, colors = _dry_colors("BWGBRY")
    doc = json.loads(render_palette(scheme, colors, serial="S1", temperature_c=23))

    assert doc["format"] == "epaper-palette"
    assert doc["measured"] is True
    assert [(e["name"], e["nominal"]) for e in doc["entries"]] == [
        ("black", "#000000"),
        ("white", "#ffffff"),
        ("yellow", "#ffff00"),
        ("red", "#ff0000"),
        ("blue", "#0000ff"),
        ("green", "#00ff00"),
    ]
    assert doc["entries"][1]["appearance"] == [100.0, 0.0, 0.0]
    Palette.from_json(json.dumps(doc))  # epaper-dithering accepts it


def test_palette_keeps_out_of_gamut_colours_unclamped() -> None:
    # A perfect white tile, so normalising to white changes nothing, and a narrow-band
    # green far outside sRGB: the palette must carry its measured Lab, not the clamped sRGB.
    scheme = get_scheme("MONO")
    white = measure_color("white", [[1.0] * 31])
    green_spd = [1.0 if 510 <= 400 + 10 * i <= 540 else 0.0 for i in range(31)]
    black = measure_color("black", [green_spd])
    assert black.reading.clipped

    doc = json.loads(render_palette(scheme, [black, white], serial="S1", temperature_c=23))

    assert doc["entries"][0]["appearance"] == pytest.approx(list(black.reading.lab_d65), abs=0.5)


def test_palette_source_records_instrument_date_and_temperature() -> None:
    scheme, colors = _dry_colors("MONO", count=1)
    on = date(2026, 11, 12)
    measured = json.loads(render_palette(scheme, colors, serial="S1", measured_on=on, temperature_c=23))
    unrecorded = json.loads(render_palette(scheme, colors, serial="S1", measured_on=on, note="Solum 2.9"))

    assert measured["source"] == "CHNSpec CR30 s/n S1, measured 2026-11-12, D65/2°, panel at 23°C"
    assert unrecorded["source"] == (
        "Solum 2.9; CHNSpec CR30 s/n S1, measured 2026-11-12, D65/2°, panel temperature unrecorded"
    )


def test_spectra_sidecar_payload() -> None:
    scheme = get_scheme("BWR")
    colors = build_colors(scheme, _dry_run_provider(count=2))
    payload = spectra_sidecar("SOLUM_TEST", scheme, colors, serial="S9", temperature_c=20.5)
    assert payload["temperature_c"] == 20.5
    assert len(payload["wavelengths_nm"]) == 31
    assert len(payload["colors"]) == scheme.count
    assert len(payload["colors"][0]["spd_reads"]) == 2
    # Must be JSON-serialisable.
    json.dumps(payload)


def test_cli_dry_run_prints_palette_and_writes_sidecar(tmp_path, capsys) -> None:
    out = tmp_path / "spectra.json"
    rc = main(["--scheme", "BWRY", "--id", "BWRY_TEST", "--temp", "23", "--dry-run", "--out", str(out)])
    assert rc == 0
    palette = Palette.from_json(capsys.readouterr().out)
    assert len(palette) == 4
    assert json.loads(out.read_text())["id"] == "BWRY_TEST"
