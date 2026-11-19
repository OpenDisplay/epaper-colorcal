"""The ColorChecker reference, --static measurement and the compare command."""

from __future__ import annotations

import json

import pytest

from epaper_colorcal.compare import compare, load, report
from epaper_colorcal.displays import ManualDisplay
from epaper_colorcal.measure_palette import main
from epaper_colorcal.references import colorchecker24_lab
from epaper_colorcal.schemes import Ink, get_scheme


def test_colorchecker_reference_is_the_current_formulation_in_chart_order() -> None:
    ref = colorchecker24_lab()
    assert len(ref) == 24 and list(ref)[0] == "dark_skin" and list(ref)[-1] == "black_2"
    assert ref["white_9_5"][0] > 95 and ref["black_2"][0] == pytest.approx(20.6, abs=0.1)
    assert colorchecker24_lab(before_2014=True) != ref


def test_colorchecker_preset_has_24_patches_with_reference_srgb() -> None:
    scheme = get_scheme("ColorChecker24")
    assert scheme.count == 24 and scheme.inks[0] == Ink("dark_skin", "#744f41")


def test_ciede2000_matches_a_published_test_pair() -> None:
    # Sharma, Wu & Dalal (2005), pair 1
    (row,) = compare({"x": (50.0, 2.6772, -79.7751)}, {"x": (50.0, 0.0, -82.7485)})
    assert row.de00 == pytest.approx(2.0425, abs=1e-4)


def test_compare_matches_by_name_in_a_s_order() -> None:
    rows = compare({"red": (40, 50, 30), "white": (95, 0, 0)}, {"white": (94, 0, 1), "green": (50, -40, 20)})
    assert [r.name for r in rows] == ["white"]
    assert rows[0].delta == (-1, 0, 1)


def test_load_csv_spectra_and_multi_device(tmp_path) -> None:
    csv_path = tmp_path / "i1.csv"
    csv_path.write_text("Name,L*,a*,b*\ndark_skin,37.5,14.4,14.9\n", encoding="utf-8")
    assert load(str(csv_path)) == {"dark_skin": (37.5, 14.4, 14.9)}

    spectra = tmp_path / "s.json"
    spectra.write_text(json.dumps({"wavelengths_nm": [400], "colors": [{"name": "red", "lab_d50": [25, 37, 24]}]}))
    assert load(str(spectra)) == {"red": (25.0, 37.0, 24.0)}

    units = tmp_path / "u.json"
    entry = {"name": "red", "lab": [22.8, 34.8, 20.2]}
    units.write_text(json.dumps({"units": [{"device": "OD000001", "entries": [entry]}]}))
    assert load(str(units), "od000001") == {"red": (22.8, 34.8, 20.2)}
    with pytest.raises(ValueError, match="OD000001"):
        load(str(units))


def test_report_summarises_the_offset() -> None:
    text = report(compare({"a": (50, 0, 0), "b": (60, 0, 0)}, {"a": (51, 0, 1), "b": (61, 0, 1)}), "A", "B")
    assert "2 samples" in text and "ΔL* +1.00" in text and "Δb* +1.00" in text


def test_cli_compare_reference_against_itself(capsys) -> None:
    assert main(["compare", "colorchecker", "colorchecker"]) == 0
    assert "ΔE00 mean 0.00" in capsys.readouterr().out


def test_cli_static_measurement_of_the_chart(capsys, monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "")
    argv = ["--scheme", "COLORCHECKER24", "--id", "cc", "--temp", "21", "--dry-run", "--format", "spectra"]
    assert main(argv) == 0  # dry run: simulated display, so no prompts
    assert len(json.loads(capsys.readouterr().out)["colors"]) == 24


async def test_static_manual_display_reads_right_away(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or "")
    display = ManualDisplay(static=True)
    await display.show(0, Ink("dark_skin", "#744f41"))
    assert display.settled_after_show and "DARK SKIN" in prompts[0]
    assert not ManualDisplay().settled_after_show


def test_static_needs_a_manual_display(capsys) -> None:
    assert main(["--id", "S", "--dry-run", "--static", "--show-command", "true"]) == 2
    assert "--static is for samples shown by hand" in capsys.readouterr().err
