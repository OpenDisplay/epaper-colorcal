"""Instruments that ArgyllCMS supports (e.g. X-Rite i1Pro), through its ``spotread`` tool.

``spotread -O FILE.sp`` takes one reading and saves the spectrum. ArgyllCMS talks to the
instrument; this adapter runs it once per reading and reads the ``.sp`` (CGATS) file it writes,
so any reflective spectrophotometer ArgyllCMS supports works without its own adapter. ArgyllCMS
must be installed (e.g. ``brew install argyll-cms``); it runs as a separate program.

An instrument that needs a white calibration does it on the first call: ``connect()`` asks for
the instrument to be put on its calibration tile and runs one call there. If a later call
calibrates instead of measuring, the reading fails with a message to calibrate again.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import cgats
from .instruments import Instrument
from .prompts import ask
from .spectrum import Spectrum

FILTERS = {"M0": "n", "M1": "5", "M2": "u"}
"""Measurement conditions (ISO 13655) -> spotread ``-F`` values."""

RUN_TIMEOUT = 60.0


def read_sp(path: str | Path) -> Spectrum:
    """A reflectance spectrum (percent) from an ArgyllCMS ``.sp`` file."""
    table = cgats.read(path)
    start, end, bands = (table.keyword(k) for k in ("SPECTRAL_START_NM", "SPECTRAL_END_NM", "SPECTRAL_BANDS"))
    if start is None or end is None or bands is None or not table.rows:
        raise ValueError(f"{path}: not a spectral (.sp) file")
    n = int(bands)
    step = (float(end) - float(start)) / (n - 1)
    wavelengths = tuple(float(start) + i * step for i in range(n))
    norm = float(table.keyword("SPECTRAL_NORM") or 100.0)  # the value that means 100 %
    values = tuple(float(v) * 100.0 / norm for v in table.rows[0][-n:])
    return Spectrum(wavelengths, values)


def _diagnostic(output: str) -> str:
    """spotread's own error line(s), without the usage text it prints after them."""
    lines = [line.split(":", 1)[1].strip() for line in output.splitlines() if line.startswith("Diagnostic:")]
    return "; ".join(lines) or output.strip()[-300:]


class SpotreadInstrument(Instrument):
    """A reflective instrument driven by ArgyllCMS's ``spotread``."""

    def __init__(
        self,
        *,
        port: int | None = None,
        filter_mode: str | None = None,
        high_resolution: bool = False,
        executable: str = "spotread",
        ask_to_calibrate: bool = True,
    ) -> None:
        if filter_mode is not None and filter_mode.upper() not in FILTERS:
            raise ValueError(f"unknown measurement condition {filter_mode!r}; choose one of: {', '.join(FILTERS)}")
        self._port = port
        self._filter = filter_mode.upper() if filter_mode else None
        self._high_resolution = high_resolution
        self._executable = executable
        self._ask_to_calibrate = ask_to_calibrate
        self._path: str | None = None
        self._name = "unknown"

    @property
    def model(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} (ArgyllCMS)" if self._name != "unknown" else "ArgyllCMS instrument"

    async def connect(self) -> None:
        self._path = shutil.which(self._executable)
        if self._path is None:
            raise SystemExit(
                f"{self._executable} not found. Install ArgyllCMS (e.g. brew install argyll-cms or "
                "https://www.argyllcms.com), which talks to the instrument."
            )
        if self._ask_to_calibrate and sys.stdin.isatty():
            await ask("Put the instrument on its white calibration tile, then press Enter… ")
        # The first call calibrates if the instrument needs it (or takes a reading, which is discarded).
        await self._run()

    async def measure(self) -> Spectrum:
        spectrum, output = await self._run()
        if spectrum is None:
            raise RuntimeError(
                "spotread did not take a reading; the instrument may have calibrated instead. Put it on its "
                f"calibration tile, run again, then back on the sample.\n{output[-400:]}"
            )
        return spectrum

    def _arguments(self, out: Path) -> list[str]:
        args = [self._path or self._executable, "-v", "-O", str(out)]
        if self._port is not None:
            args += ["-c", str(self._port)]
        if self._filter is not None:
            args += ["-F", FILTERS[self._filter]]
        if self._high_resolution:
            args.append("-H")
        return args

    async def _run(self) -> tuple[Spectrum | None, str]:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "reading.sp"
            proc = await asyncio.create_subprocess_exec(
                *self._arguments(out),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                # Answer any "press a key" prompt; spotread -O otherwise needs no input.
                raw, _ = await asyncio.wait_for(proc.communicate(b"\n" * 4), RUN_TIMEOUT)
            except asyncio.TimeoutError as exc:
                proc.kill()
                raise TimeoutError(f"spotread did not finish within {RUN_TIMEOUT:g} s") from exc
            output = raw.decode(errors="replace")
            self._remember_name(output)
            if proc.returncode:
                raise RuntimeError(f"spotread failed (exit {proc.returncode}): {_diagnostic(output)}")
            return (read_sp(out) if out.exists() else None), output

    def _remember_name(self, output: str) -> None:
        match = re.search(r"(?im)^\s*(?:instrument(?: type)?|device)\s*[:=]\s*'?([^'\n]+?)'?\s*$", output)
        if match and self._name == "unknown":
            self._name = match.group(1).strip()
