"""ArgyllCMS instruments through spotread, against a fake spotread."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from epaper_colorcal.argyll import SpotreadInstrument, read_sp
from epaper_colorcal.chart import main as chart_main
from epaper_colorcal.measure_palette import main

SP = """SPECT

DESCRIPTOR "test"
KEYWORD "SPECTRAL_BANDS"
SPECTRAL_BANDS "4"
KEYWORD "SPECTRAL_START_NM"
SPECTRAL_START_NM "380.000000"
KEYWORD "SPECTRAL_END_NM"
SPECTRAL_END_NM "410.000000"
KEYWORD "SPECTRAL_NORM"
SPECTRAL_NORM "{norm}"

NUMBER_OF_FIELDS 4
BEGIN_DATA_FORMAT
SPEC_380 SPEC_390 SPEC_400 SPEC_410
END_DATA_FORMAT

NUMBER_OF_SETS 1
BEGIN_DATA
{values}
END_DATA
"""


@pytest.mark.parametrize(("norm", "values"), [("1.0", "0.1 0.2 0.3 0.4"), ("100.0", "10 20 30 40")])
def test_read_sp_gives_percent_whatever_the_norm(tmp_path, norm: str, values: str) -> None:
    path = tmp_path / "x.sp"
    path.write_text(SP.format(norm=norm, values=values))
    spectrum = read_sp(path)
    assert spectrum.wavelengths == (380.0, 390.0, 400.0, 410.0)
    assert spectrum.values == pytest.approx((10.0, 20.0, 30.0, 40.0))


def test_read_sp_reads_argylls_own_files() -> None:
    ref = Path("/opt/homebrew/Cellar/argyll-cms/3.5.0/ref/CIE_C.sp")
    if not ref.exists():
        pytest.skip("ArgyllCMS reference files not installed")
    assert read_sp(ref).wavelengths[0] == 320.0


def _fake_spotread(tmp_path: Path, *, write: bool = True, exit_code: int = 0) -> Path:
    """A spotread that records its arguments and writes a 50 % flat spectrum to -O's file."""
    script = tmp_path / "spotread"
    script.write_text(
        f"""#!{sys.executable}
import json, sys
log = {str(tmp_path / "calls.jsonl")!r}
with open(log, "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
print("Instrument Type: i1 Pro 2")
if {exit_code!r}:
    print("Diagnostic: Unknown, inappropriate or no instrument detected")
    print("usage: spotread [-options] [logfile]")
args = sys.argv[1:]
if {write!r} and "-O" in args:
    open(args[args.index("-O") + 1], "w").write({SP.format(norm="1.0", values="0.5 0.5 0.5 0.5")!r})
sys.exit({exit_code})
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _calls(tmp_path: Path) -> list[list[str]]:
    return [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]


async def test_connect_calibrates_then_each_measure_is_one_call(tmp_path) -> None:
    instrument = SpotreadInstrument(
        executable=str(_fake_spotread(tmp_path)), port=2, filter_mode="m1", high_resolution=True
    )
    await instrument.connect()
    spectrum = await instrument.measure()
    assert spectrum.values == pytest.approx((50.0,) * 4)
    calls = _calls(tmp_path)
    assert len(calls) == 2  # one at connect (calibration), one reading
    assert calls[1][:2] == ["-v", "-O"] and calls[1][3:] == ["-c", "2", "-F", "5", "-H"]
    assert instrument.description == "i1 Pro 2 (ArgyllCMS)"


async def test_a_call_that_only_calibrates_is_explained(tmp_path) -> None:
    instrument = SpotreadInstrument(executable=str(_fake_spotread(tmp_path, write=False)))
    await instrument.connect()
    with pytest.raises(RuntimeError, match="calibrated instead"):
        await instrument.measure()


async def test_spotread_failing_is_reported(tmp_path) -> None:
    instrument = SpotreadInstrument(executable=str(_fake_spotread(tmp_path, exit_code=1)))
    with pytest.raises(RuntimeError, match="exit 1\\): Unknown, inappropriate or no instrument detected$"):
        await instrument.connect()


async def test_missing_argyll_is_explained() -> None:
    with pytest.raises(SystemExit, match="Install ArgyllCMS"):
        await SpotreadInstrument(executable="no-such-spotread-here").connect()


def test_unknown_filter_is_rejected() -> None:
    with pytest.raises(ValueError, match="M0, M1, M2"):
        SpotreadInstrument(filter_mode="M3")


def test_cli_rejects_calibrate_with_argyll(capsys) -> None:
    assert main(["--scheme", "MONO", "--id", "S", "--argyll", "--calibrate"]) == 2
    assert "calibrates when it connects" in capsys.readouterr().err


def test_chart_needs_an_instrument_or_dry_run(capsys) -> None:
    ti2 = str(Path(__file__).parent / "fixtures" / "small_rgb.ti2")
    assert chart_main([ti2]) == 2
    assert "--argyll" in capsys.readouterr().err
