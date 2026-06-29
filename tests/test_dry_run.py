"""Dry-run pipeline tests — no CR30 hardware required."""

from __future__ import annotations

import json

from epaper_colorcal.colorimetry import average_spds, reading_from_spd
from epaper_colorcal.emit_rust import (
    render_catalog_entry,
    render_full_output,
    render_rust_palette,
    spectra_sidecar,
)
from epaper_colorcal.measure_palette import _dry_run_provider, build_colors, main
from epaper_colorcal.schemes import get_scheme
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


def test_render_rust_palette_format() -> None:
    scheme = get_scheme("BWRY")
    colors = build_colors(scheme, _dry_run_provider(count=2))
    block = render_rust_palette("EP_TEST_BWRY", scheme, colors, serial="S123", temperature_c=23)
    assert "pub static EP_TEST_BWRY: Palette = Palette {" in block
    assert "Cow::Borrowed(&[" in block
    assert "accent_idx: 3, // red" in block
    assert "panel @ 23°C" in block
    # One color row per scheme color.
    assert block.count("// ") >= scheme.count


def test_unrecorded_temperature_warns_in_comment() -> None:
    scheme = get_scheme("MONO")
    colors = build_colors(scheme, _dry_run_provider(count=1))
    block = render_rust_palette("EP_TEST_MONO", scheme, colors)
    assert "UNRECORDED" in block


def test_catalog_entry() -> None:
    scheme = get_scheme("BWGBRY")
    entry = render_catalog_entry("SPECTRA_TEST", scheme)
    assert 'id: "SPECTRA_TEST"' in entry
    assert "scheme: ColorScheme::Bwgbry" in entry
    assert '"black", "white", "yellow", "red", "blue", "green"' in entry


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


def test_full_output_has_all_sections() -> None:
    scheme = get_scheme("BWGBRY")
    colors = build_colors(scheme, _dry_run_provider(count=2))
    out = render_full_output("SPECTRA_13_3_6COLOR", scheme, colors, serial="S1", temperature_c=23)
    assert "measured_palettes.rs" in out
    assert "CATALOG" in out
    assert "palettes.py" in out


def test_cli_dry_run_writes_sidecar(tmp_path, capsys) -> None:
    out = tmp_path / "spectra.json"
    rc = main(["--scheme", "BWRY", "--id", "BWRY_TEST", "--temp", "23", "--dry-run", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr()
    assert "pub static BWRY_TEST: Palette" in captured.out
    data = json.loads(out.read_text())
    assert data["id"] == "BWRY_TEST"
