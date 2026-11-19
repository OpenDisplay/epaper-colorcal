"""Compare two measurements of the same samples, e.g. two instruments on one ColorChecker.

    epaper-colorcal compare A B [--unit-a DEVICE] [--unit-b DEVICE]

A and B are each one of:

* ``colorchecker``: the ColorChecker Classic's reference values (``colorchecker-pre2014`` for
  charts made before November 2014),
* a spectra file from this tool (``--out``, or ``--format spectra``),
* a multi-device file (``units``, each with a ``device`` and ``entries`` of ``name`` and
  ``lab``): pick the device with ``--unit-a`` / ``--unit-b``,
* a CSV with columns ``name,L,a,b`` (CIELAB, D50/2°), e.g. exported from another instrument.

Samples are matched by name. Everything is compared as CIELAB under D50/2°; the table shows
B minus A per sample, with ΔE00 (CIEDE2000).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Lab = tuple[float, float, float]


@dataclass(frozen=True)
class Row:
    name: str
    a: Lab
    b: Lab
    de00: float

    @property
    def delta(self) -> Lab:
        return (self.b[0] - self.a[0], self.b[1] - self.a[1], self.b[2] - self.a[2])


def load(source: str, unit: str | None = None) -> dict[str, Lab]:
    """Samples (name -> D50 Lab) from a reference name or a file; see the module docstring."""
    if source.lower() in ("colorchecker", "colorchecker24", "colorchecker-pre2014"):
        from .references import colorchecker24_lab  # pylint: disable=import-outside-toplevel

        return colorchecker24_lab(before_2014=source.lower().endswith("pre2014"))
    path = Path(source)
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if "units" in data:
        return _load_units(data, unit, path)
    if "colors" in data and "wavelengths_nm" in data:
        return {c["name"]: _lab(c["lab_d50"]) for c in data["colors"]}
    raise ValueError(f"{source}: not a spectra file, a multi-device file or a CSV")


def _lab(values: list[float] | tuple[float, ...]) -> Lab:
    return (float(values[0]), float(values[1]), float(values[2]))


def _load_csv(path: Path) -> dict[str, Lab]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path}: no rows")
    keys = {k.strip().lower().rstrip("*"): k for k in rows[0]}
    missing = [k for k in ("name", "l", "a", "b") if k not in keys]
    if missing:
        raise ValueError(f"{path}: needs columns name,L,a,b (missing {', '.join(missing)})")
    return {r[keys["name"]].strip(): (float(r[keys["l"]]), float(r[keys["a"]]), float(r[keys["b"]])) for r in rows}


def _load_units(data: dict[str, Any], unit: str | None, path: Path) -> dict[str, Lab]:
    devices = [u["device"] for u in data["units"]]
    if unit is None:
        raise ValueError(f"{path}: several devices; pick one with --unit-a/--unit-b ({', '.join(devices)})")
    for u in data["units"]:
        if u["device"].lower() == unit.lower():
            return {e["name"]: _lab(e["lab"]) for e in u["entries"]}
    raise ValueError(f"{path}: no device {unit!r} ({', '.join(devices)})")


def compare(a: dict[str, Lab], b: dict[str, Lab]) -> list[Row]:
    """B against A for every sample both have, in A's order."""
    import colour  # pylint: disable=import-outside-toplevel

    common = [name for name in a if name in b]
    return [Row(n, a[n], b[n], float(colour.delta_E(a[n], b[n], method="CIE 2000"))) for n in common]


def report(rows: list[Row], label_a: str, label_b: str) -> str:
    if not rows:
        return "No samples in common (they're matched by name)."
    width = max(len(r.name) for r in rows)
    lines = [
        f"B = {label_b}",
        f"A = {label_a}",
        "",
        f"{'sample':{width}}  {'A  L*    a*    b*':>20}  {'B  L*    a*    b*':>20}   ΔE00     ΔL     Δa     Δb",
    ]
    for r in rows:
        a = " ".join(f"{v:6.1f}" for v in r.a)
        b = " ".join(f"{v:6.1f}" for v in r.b)
        d = " ".join(f"{v:6.2f}" for v in r.delta)
        lines.append(f"{r.name:{width}}  {a}  {b}  {r.de00:5.2f}  {d}")
    de = [r.de00 for r in rows]
    mean_d = tuple(statistics.fmean(r.delta[i] for r in rows) for i in range(3))
    lines += [
        "",
        f"{len(rows)} samples: ΔE00 mean {statistics.fmean(de):.2f}, median {statistics.median(de):.2f}, "
        f"max {max(de):.2f} ({max(rows, key=lambda r: r.de00).name})",
        f"mean offset B - A: ΔL* {mean_d[0]:+.2f}, Δa* {mean_d[1]:+.2f}, Δb* {mean_d[2]:+.2f}",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="epaper-colorcal compare", description=__doc__.split("\n\n", maxsplit=1)[0])
    p.add_argument("a", help="colorchecker, a spectra JSON, a multi-device JSON or a name,L,a,b CSV")
    p.add_argument("b", help="the same kinds as A")
    p.add_argument("--unit-a", help="the device to take from A, if A has several")
    p.add_argument("--unit-b", help="the device to take from B, if B has several")
    args = p.parse_args(argv)
    try:
        a, b = load(args.a, args.unit_a), load(args.b, args.unit_b)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    label_a = f"{args.a} ({args.unit_a})" if args.unit_a else args.a
    label_b = f"{args.b} ({args.unit_b})" if args.unit_b else args.b
    print(report(compare(a, b), label_a, label_b))
    return 0
