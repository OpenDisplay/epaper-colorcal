"""Reading a printed ArgyllCMS chart: CGATS, the patch loop with redo/quit/resume, and .ti3."""

from __future__ import annotations

from pathlib import Path

import pytest

from epaper_colorcal import cgats
from epaper_colorcal.chart import Progress, load_chart, main, read_patches, ti3
from epaper_colorcal.spectrum import Spectrum

TI2 = Path(__file__).parent / "fixtures" / "small_rgb.ti2"
PRINTTARG = Path(__file__).parent / "fixtures" / "argyll_printtarg_rgb.ti2"  # made by targen + printtarg


def test_cgats_reads_an_argyll_ti2() -> None:
    table = cgats.read(TI2)
    assert table.file_type == "CTI2" and table.keyword("COLOR_REP") == "RGB"
    assert table.fields[:5] == ["SAMPLE_ID", "SAMPLE_LOC", "RGB_R", "RGB_G", "RGB_B"]
    assert table.column("SAMPLE_LOC") == ["A1", "A2", "A3", "A4"]


def test_cgats_round_trips() -> None:
    table = cgats.CGATS(
        "CTI3", {"DESCRIPTOR": '"x"', "COLOR_REP": '"RGB_LAB"'}, ["SAMPLE_ID", "LAB_L"], [["1", "50.0"]]
    )
    text = cgats.dumps(table)
    assert 'KEYWORD "COLOR_REP"' in text and 'KEYWORD "DESCRIPTOR"' not in text  # standard keywords aren't declared
    again = cgats.parse(text)
    assert (again.file_type, again.keyword("COLOR_REP"), again.fields, again.rows) == (
        "CTI3",
        "RGB_LAB",
        ["SAMPLE_ID", "LAB_L"],
        [["1", "50.0"]],
    )


def test_cgats_rejects_ragged_rows() -> None:
    with pytest.raises(ValueError, match="values for 2 fields"):
        cgats.parse("CTI2\nBEGIN_DATA_FORMAT\nA B\nEND_DATA_FORMAT\nBEGIN_DATA\n1\nEND_DATA\n")


def test_load_chart_keeps_device_fields_and_drops_expected_values() -> None:
    chart = load_chart(TI2)
    assert chart.color_rep == "RGB" and chart.device_fields == ["RGB_R", "RGB_G", "RGB_B"]
    assert chart.patches[2].location == "A3" and chart.patches[2].rgb == (255, 0, 0)


class _Instrument:
    def __init__(self) -> None:
        self.reads = 0

    async def measure(self) -> Spectrum:
        self.reads += 1
        return Spectrum.cr30([10.0 * self.reads % 100] * 31)


def _answers(*replies: str):
    queue = list(replies)
    asked: list[str] = []

    async def ask(patch, prompt: str) -> str:
        asked.append(patch.location)
        return queue.pop(0) if queue else ""

    return ask, asked


async def test_quit_saves_and_a_new_session_resumes(tmp_path) -> None:
    chart = load_chart(TI2)
    progress = Progress(tmp_path / "p.json", chart)
    ask, asked = _answers("", "", "q")
    assert not await read_patches(chart, _Instrument(), progress, ask)
    assert asked == ["A1", "A2", "A3"] and set(progress.reads) == {"1", "2"}

    resumed = Progress(tmp_path / "p.json", chart)  # a new session, from the file
    ask, asked = _answers()
    assert await read_patches(chart, _Instrument(), resumed, ask)
    assert asked == ["A3", "A4"] and resumed.complete


async def test_r_redoes_the_previous_patch(tmp_path) -> None:
    chart = load_chart(TI2)
    progress = Progress(tmp_path / "p.json", chart)
    ask, asked = _answers("r", "", "r", "", "", "", "")
    assert await read_patches(chart, _Instrument(), progress, ask)
    # r with nothing read yet is ignored; after A1, r goes back to A1
    assert asked == ["A1", "A1", "A2", "A1", "A2", "A3", "A4"]


def test_progress_refuses_another_chart(tmp_path) -> None:
    chart = load_chart(TI2)
    (tmp_path / "p.json").write_text('{"ids": ["x"], "wavelengths": [], "reads": {}}')
    with pytest.raises(SystemExit, match="different chart"):
        Progress(tmp_path / "p.json", chart)


async def test_ti3_has_device_values_lab_and_spectra(tmp_path) -> None:
    chart = load_chart(TI2)
    progress = Progress(tmp_path / "p.json", chart)
    ask, _ = _answers()
    await read_patches(chart, _Instrument(), progress, ask, count=2)
    table = cgats.parse(ti3(chart, progress, instrument="CHNSpec CR30", serial="S1", note="test printer"))
    assert table.file_type == "CTI3" and table.keyword("COLOR_REP") == "RGB_LAB"
    assert table.keyword("DEVICE_CLASS") == "OUTPUT" and table.keyword("SPECTRAL_BANDS") == "31"
    assert table.fields[:7] == ["SAMPLE_ID", "RGB_R", "RGB_G", "RGB_B", "LAB_L", "LAB_A", "LAB_B"]
    assert table.fields[7] == "SPEC_400" and table.fields[-1] == "SPEC_700"
    first = table.records()[0]
    assert first["RGB_R"] == "100.00" and float(first["SPEC_400"]) == pytest.approx(15.0)  # mean of 10 and 20


def test_cli_dry_run_writes_a_ti3(tmp_path, capsys) -> None:
    out = tmp_path / "small.ti3"
    assert main([str(TI2), "--dry-run", "--out", str(out)]) == 0
    assert len(cgats.read(out).rows) == 4
    assert "colprof" in capsys.readouterr().err


def test_a_real_printtarg_chart_loads() -> None:
    chart = load_chart(PRINTTARG)
    assert chart.color_rep == "RGB" and len(chart.patches) == 105
    assert chart.patches[0].sample_id == "1" and chart.patches[0].location == "A10"


def test_patches_are_read_in_paper_order_not_sample_order() -> None:
    order = [p.location for p in load_chart(PRINTTARG).reading_order]
    assert order[:3] == ["A1", "A2", "A3"]
    strips = [loc.rstrip("0123456789") for loc in order]
    assert strips == sorted(strips, key=lambda s: (len(s), s))  # strip by strip
    assert order.index("A10") < order.index("B1")  # A10 is in strip A, before B1


def test_cli_dry_run_on_a_real_chart_keeps_sample_order_in_the_ti3(tmp_path) -> None:
    out = tmp_path / "t.ti3"
    assert main([str(PRINTTARG), "--dry-run", "--out", str(out)]) == 0
    table = cgats.read(out)
    assert table.column("SAMPLE_ID")[:3] == ["1", "2", "3"] and len(table.rows) == 105
