"""Read a printed ArgyllCMS chart patch by patch, for an ICC printer profile.

    epaper-colorcal chart CHART.ti2 (--port PORT | --cr30-ble [NAME] | --dry-run) [--out CHART.ti3]

The ArgyllCMS workflow around it::

    targen -v -d3 -f250 mychart          # patch values  -> mychart.ti1
    printtarg -v -i CR -p A4 mychart     # chart layout  -> mychart.ti2 + mychart.tif (print it with
                                         #                  colour management off)
    epaper-colorcal chart mychart.ti2 --cr30-ble        # this tool -> mychart.ti3
    colprof -v -D "My printer, paper" mychart            # -> mychart.icc

Each patch is read when you press Enter; ``r`` redoes the previous patch, ``q`` saves and quits.
Progress is saved after every patch (``CHART.progress.json``), so a stopped session resumes
where it left off. The ``.ti3`` holds each patch's device values, its D50 Lab and its spectrum.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from . import cgats

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .instruments import Instrument
    from .spectrum import Spectrum

_NOT_DEVICE = ("SAMPLE_ID", "SAMPLE_LOC")
_EXPECTED = ("XYZ_", "LAB_")


@dataclass(frozen=True)
class Patch:
    sample_id: str
    location: str
    device: dict[str, str]
    """The chart's device values for this patch (e.g. RGB_R, RGB_G, RGB_B on 0-100)."""

    @property
    def rgb(self) -> tuple[int, int, int] | None:
        """The patch's RGB on 0-255, for RGB charts."""
        try:
            return tuple(round(float(self.device[f"RGB_{c}"]) * 2.55) for c in "RGB")  # type: ignore[return-value]
        except KeyError:
            return None


@dataclass(frozen=True)
class Chart:
    patches: list[Patch]
    """In SAMPLE_ID order, as the .ti3 lists them."""
    device_fields: list[str]
    color_rep: str
    """The device colour space, e.g. ``RGB`` or ``CMYK``."""

    @property
    def reading_order(self) -> list[Patch]:
        """The patches as they're laid out on paper: strip A top to bottom, then B, and so on.

        printtarg places patches in random order, so SAMPLE_ID order jumps around the page.
        """
        return sorted(self.patches, key=lambda p: _location_key(p.location))


def _location_key(location: str) -> tuple[int, str, int, str]:
    """'A10' -> strip A, patch 10; 'AB3' sorts after 'Z9'."""
    match = re.fullmatch(r"([A-Za-z]+)(\d+)", location)
    if not match:
        return (99, location, 0, location)
    letters, number = match.groups()
    return (len(letters), letters.upper(), int(number), location)


def load_chart(path: str | Path) -> Chart:
    table = cgats.read(path)
    if "SAMPLE_ID" not in table.fields:
        raise ValueError(f"{path}: no SAMPLE_ID field; is it an ArgyllCMS .ti2?")
    device_fields = [f for f in table.fields if f not in _NOT_DEVICE and not f.startswith(_EXPECTED)]
    if not device_fields:
        raise ValueError(f"{path}: no device values (RGB_*, CMYK_*, ...)")
    rep = (table.keyword("COLOR_REP") or "").split("_")[0] or device_fields[0].split("_")[0]
    patches = [
        Patch(r["SAMPLE_ID"], r.get("SAMPLE_LOC", r["SAMPLE_ID"]), {f: r[f] for f in device_fields})
        for r in table.records()
    ]
    return Chart(patches, device_fields, rep)


# ── progress ────────────────────────────────────────────────────────────────


class Progress:
    """Raw reads per patch, saved after every patch so a session can resume."""

    def __init__(self, path: Path, chart: Chart) -> None:
        self.path = path
        self.ids = [p.sample_id for p in chart.patches]
        self.reads: dict[str, list[list[float]]] = {}
        self.wavelengths: list[float] = []
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("ids") != self.ids:
                raise SystemExit(f"{path} belongs to a different chart; move it away to start again.")
            self.reads, self.wavelengths = data["reads"], data["wavelengths"]

    def add(self, sample_id: str, spectra: list[Spectrum]) -> None:
        self.wavelengths = list(spectra[0].wavelengths)
        self.reads[sample_id] = [list(s.values) for s in spectra]
        self.save()

    def drop(self, sample_id: str) -> None:
        self.reads.pop(sample_id, None)
        self.save()

    def save(self) -> None:
        payload = {"ids": self.ids, "wavelengths": self.wavelengths, "reads": self.reads}
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    @property
    def complete(self) -> bool:
        return all(i in self.reads for i in self.ids)


# ── reading ─────────────────────────────────────────────────────────────────


async def read_patches(
    chart: Chart,
    instrument: Instrument,
    progress: Progress,
    ask: Callable[[Patch, str], Awaitable[str]],
    *,
    count: int = 1,
) -> bool:
    """Read every patch not yet in ``progress``; return True when all are done, False on quit.

    ``ask(patch, prompt)`` asks the operator to seat the instrument and returns their answer.
    """
    from .colorimetry import exact_lab_d50  # pylint: disable=import-outside-toplevel

    patches = chart.reading_order
    history: list[int] = []  # indexes read in this session, for "r"
    i = _next_unread(patches, progress, 0)
    while i < len(patches):
        done = sum(p.sample_id in progress.reads for p in patches)
        prompt = f"[{done + 1}/{len(patches)}] {patches[i].location}: seat the instrument, Enter (r = redo, q = quit) "
        answer = (await ask(patches[i], prompt)).strip().lower()
        if answer == "q":
            return False
        if answer == "r":
            if history:
                i = history.pop()
                progress.drop(patches[i].sample_id)
            else:
                print("  nothing to redo yet", file=sys.stderr)
            continue
        spectra = [await instrument.measure() for _ in range(count)]
        progress.add(patches[i].sample_id, spectra)
        lab = exact_lab_d50(spectra[0])
        print(f"  {patches[i].location}: L* {lab[0]:.1f} a* {lab[1]:.1f} b* {lab[2]:.1f}", file=sys.stderr)
        history.append(i)
        i = _next_unread(patches, progress, i + 1)
    return True


def _next_unread(patches: list[Patch], progress: Progress, start: int) -> int:
    return next((k for k in range(start, len(patches)) if patches[k].sample_id not in progress.reads), len(patches))


# ── .ti3 ────────────────────────────────────────────────────────────────────


def _ti3_row(chart: Chart, patch: Patch, progress: Progress, wavelengths: list[float]) -> list[str]:
    from .colorimetry import exact_lab_d50  # pylint: disable=import-outside-toplevel
    from .spectrum import Spectrum, average_spectra  # pylint: disable=import-outside-toplevel

    mean = average_spectra([Spectrum(tuple(wavelengths), tuple(v)) for v in progress.reads[patch.sample_id]])
    return (
        [patch.sample_id, *(patch.device[f] for f in chart.device_fields)]
        + [f"{v:.6f}" for v in exact_lab_d50(mean)]
        + [f"{v:.6f}" for v in mean.values]
    )


def ti3(chart: Chart, progress: Progress, *, instrument: str, serial: str, note: str = "") -> str:
    """The measurements as an ArgyllCMS ``.ti3`` (CTI3) for ``colprof``."""
    wavelengths = [float(w) for w in progress.wavelengths]
    spec_fields = [f"SPEC_{round(w)}" for w in wavelengths]
    rows = [_ti3_row(chart, patch, progress, wavelengths) for patch in chart.patches]
    keywords = {
        "DESCRIPTOR": cgats.quoted(f"Argyll Calibration Target chart information 3{'; ' + note if note else ''}"),
        "ORIGINATOR": cgats.quoted(f"epaper-colorcal, {instrument} s/n {serial}"),
        "CREATED": cgats.quoted(date.today().isoformat()),
        "DEVICE_CLASS": '"OUTPUT"',
        "COLOR_REP": cgats.quoted(f"{chart.color_rep}_LAB"),
        "SPECTRAL_BANDS": cgats.quoted(str(len(wavelengths))),
        "SPECTRAL_START_NM": cgats.quoted(f"{wavelengths[0]:.6f}"),
        "SPECTRAL_END_NM": cgats.quoted(f"{wavelengths[-1]:.6f}"),
    }
    fields = ["SAMPLE_ID", *chart.device_fields, "LAB_L", "LAB_A", "LAB_B", *spec_fields]
    return cgats.dumps(cgats.CGATS("CTI3", keywords, fields, rows))


# ── CLI ─────────────────────────────────────────────────────────────────────


class _SyntheticChart:
    """A dry-run instrument: plausible spectra of the patch being read (RGB charts)."""

    def __init__(self) -> None:
        self.patch: Patch | None = None
        self.reads = 0

    async def measure(self) -> Spectrum:
        from .spectrum import Spectrum  # pylint: disable=import-outside-toplevel
        from .synthetic import synthetic_spd  # pylint: disable=import-outside-toplevel

        assert self.patch is not None and self.patch.rgb is not None
        self.reads += 1
        return Spectrum.cr30(synthetic_spd(self.patch.rgb, jitter=0.005, seed=self.reads))


async def _run(args: argparse.Namespace, chart: Chart, progress: Progress) -> tuple[bool, str, str]:
    if args.dry_run:
        if chart.patches[0].rgb is None:
            raise SystemExit("--dry-run needs an RGB chart")
        synthetic = _SyntheticChart()

        async def auto(patch: Patch, _prompt: str) -> str:
            synthetic.patch = patch
            return ""

        done = await read_patches(chart, synthetic, progress, auto, count=args.count)  # type: ignore[arg-type]
        return done, "synthetic", "DRYRUN"

    from .cr30 import open_cr30  # pylint: disable=import-outside-toplevel

    instrument = open_cr30(port=args.port, ble=args.cr30_ble)
    await instrument.connect()
    try:
        print(f"Connected to {instrument.description} (s/n {instrument.serial_number}).", file=sys.stderr)

        async def ask(_patch: Patch, prompt: str) -> str:
            return await asyncio.to_thread(input, prompt)

        done = await read_patches(chart, instrument, progress, ask, count=args.count)
        return done, instrument.description, instrument.serial_number
    finally:
        await instrument.close()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="epaper-colorcal chart", description=__doc__.split("\n\n", maxsplit=1)[0])
    p.add_argument("chart", help="the ArgyllCMS chart (.ti2) that was printed")
    p.add_argument("--out", help="the .ti3 to write (default: next to the chart)")
    cr30 = p.add_mutually_exclusive_group(required=True)
    cr30.add_argument("--port", help="USB serial port of the CR30")
    cr30.add_argument("--cr30-ble", nargs="?", const="auto", metavar="NAME", help="the CR30 over Bluetooth")
    cr30.add_argument("--dry-run", action="store_true", help="synthetic readings, no hardware (RGB charts)")
    p.add_argument("--count", type=int, default=1, help="reads averaged per patch (default 1)")
    p.add_argument("--note", default="", help="free text for the .ti3's description, e.g. printer and paper")
    args = p.parse_args(argv)

    try:
        chart = load_chart(args.chart)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path(args.chart).with_suffix(".ti3")
    progress = Progress(out.with_suffix(".progress.json"), chart)
    if progress.reads:
        print(f"Resuming: {len(progress.reads)} of {len(chart.patches)} patches already read.", file=sys.stderr)

    try:
        done, instrument, serial = asyncio.run(_run(args, chart, progress))
    except TimeoutError as exc:
        print(f"error: {exc}\nProgress is saved; run the same command again to continue.", file=sys.stderr)
        return 1
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("Stopped. Progress is saved; run the same command again to continue.", file=sys.stderr)
        return 130
    if not done:
        print(f"Saved {len(progress.reads)} of {len(chart.patches)} patches; run again to continue.", file=sys.stderr)
        return 0
    out.write_text(ti3(chart, progress, instrument=instrument, serial=serial, note=args.note), encoding="utf-8")
    print(
        f'Wrote {out} ({len(chart.patches)} patches). Next: colprof -v -D "..." {out.with_suffix("")}', file=sys.stderr
    )
    return 0
