"""CLI: measure a panel's colors with a CR30 and emit a measured palette.

Walks each color of a scheme in firmware order, averages several SPD reads, and
prints the measured palette as an ``epaper-palette`` JSON document on stdout (all
prompts and notes go to stderr). ``--dry-run`` synthesises spectra so the whole
pipeline runs with no hardware.

Example (no hardware):
    epaper-colorcal --scheme BWGBRY --id spectra6_13in3 --temp 23 --dry-run > spectra6_13in3.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from .colorimetry import average_spds, reading_from_spd
from .emit import MeasuredColor, render_palette, spectra_sidecar, write_sidecar
from .schemes import Scheme, get_scheme
from .synthetic import IDEAL_SRGB, synthetic_spd

if TYPE_CHECKING:
    from .cr30 import CR30

# Function that, given a color name, returns a list of raw SPD reads for it.
SpdProvider = Callable[[str], list[list[float]]]


def measure_color(name: str, spds: list[list[float]]) -> MeasuredColor:
    """Average the SPD reads for one color and resolve it to sRGB/Lab."""
    reading = reading_from_spd(average_spds(spds))
    return MeasuredColor(name=name, reading=reading, spds=spds)


def build_colors(scheme: Scheme, provider: SpdProvider) -> list[MeasuredColor]:
    """Build the ordered list of measured colors for a scheme."""
    return [measure_color(name, provider(name)) for name in scheme.colors]


def _dry_run_provider(count: int) -> SpdProvider:
    def provide(name: str) -> list[list[float]]:
        target = IDEAL_SRGB.get(name, (128, 128, 128))
        # Distinct seeds per read so averaging is meaningful.
        return [synthetic_spd(target, jitter=0.01, seed=i) for i in range(count)]

    return provide


async def _open_cr30(args: argparse.Namespace) -> CR30:
    """Connect to the CR30 on USB (--port) or BLE (--cr30-ble), optionally calibrating it."""
    from .cr30 import open_cr30

    cr30 = open_cr30(port=args.port, ble=args.cr30_ble)
    await cr30.connect()
    via = f"USB {args.port}" if args.port else "BLE"
    print(f"Connected to {cr30.model} (s/n {cr30.serial_number}) over {via}.", file=sys.stderr)

    if args.calibrate:
        input("Close the CR30 cap fully (black calibration), then press Enter… ")
        if not await cr30.calibrate_black():
            raise SystemExit("Black calibration failed.")
        input("Keep the cap closed (white calibration), then press Enter… ")
        if not await cr30.calibrate_white():
            raise SystemExit("White calibration failed.")
    return cr30


def _hardware_provider(args: argparse.Namespace) -> tuple[SpdProvider, Callable[[], str]]:
    """Build a provider that prompts the operator and reads the CR30.

    Returns the provider plus a callable to fetch the device serial after connect.
    """
    loop = asyncio.new_event_loop()
    cr30 = loop.run_until_complete(_open_cr30(args))

    def provide(name: str) -> list[list[float]]:
        input(f"Fill the panel with solid {name.upper()}, seat the CR30 against it, then press Enter… ")
        reads: list[list[float]] = []
        for i in range(args.count):
            reads.append(loop.run_until_complete(cr30.measure()))
            print(f"  read {i + 1}/{args.count} ok", file=sys.stderr)
        return reads

    return provide, (lambda: cr30.serial_number)


async def _run_interactive(args: argparse.Namespace, scheme: Scheme) -> tuple[list[MeasuredColor], str]:
    """Drive the panel + CR30 (or simulated stand-ins) to measure every color."""
    from .interactive import OpenDisplayPanel, SimPanel, measure_interactive

    if args.dry_run:
        panel: object = SimPanel(settle_seconds=args.settle)

        async def sim_source(name: str) -> list[float]:
            return synthetic_spd(IDEAL_SRGB.get(name, (128, 128, 128)), jitter=0.01)

        colors = await measure_interactive(scheme, panel, sim_source, args.count)  # type: ignore[arg-type]
        await panel.close()  # type: ignore[attr-defined]
        return colors, args.serial or "DRYRUN"

    if not args.address:
        raise SystemExit("--address is required for interactive mode (or add --dry-run)")
    if not (args.port or args.cr30_ble):
        raise SystemExit("--port or --cr30-ble (the CR30) is required for interactive mode (or add --dry-run)")

    cr30 = await _open_cr30(args)
    if sys.stdin.isatty():
        input("Seat the CR30 flat against the panel and press Enter to start the sweep… ")

    key = bytes.fromhex(args.key) if args.key else None
    ble_panel = OpenDisplayPanel(args.address, scheme, key=key, settle_seconds=args.settle)
    await ble_panel.connect()
    try:

        async def cr30_source(name: str) -> list[float]:
            return await cr30.measure()

        colors = await measure_interactive(scheme, ble_panel, cr30_source, args.count)
    finally:
        await ble_panel.close()
        await cr30.close()

    return colors, args.serial or cr30.serial_number


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="epaper-colorcal", description=__doc__)
    p.add_argument("--scheme", required=True, help="Color scheme: MONO, BWR, BWY, BWRY, BWGBRY")
    p.add_argument(
        "--id",
        required=True,
        dest="palette_id",
        help="Name for this measurement, e.g. spectra6_13in3 (recorded in the sidecar)",
    )
    cr30 = p.add_mutually_exclusive_group()
    cr30.add_argument("--port", help="USB serial port of the CR30 (e.g. /dev/tty.wchusbserial120)")
    cr30.add_argument(
        "--cr30-ble",
        nargs="?",
        const="auto",
        metavar="NAME",
        help="Use the CR30 over Bluetooth: its name/address, or no value to find it by scanning",
    )
    p.add_argument("--count", type=int, default=3, help="SPD reads to average per color (default 3)")
    p.add_argument("--temp", type=float, default=None, help="Panel temperature in °C (strongly recommended)")
    p.add_argument("--note", default="", help="Free-text note, e.g. the panel model, prepended to the palette's source")
    p.add_argument("--serial", default=None, help="Override the recorded instrument serial")
    p.add_argument(
        "--calibrate",
        action="store_true",
        help="Run explicit black/white calibration first. The CR30 auto-calibrates against its "
        "cap, so this is normally not needed.",
    )
    p.add_argument("--out", default=None, help="Path to write the raw-spectra JSON sidecar")
    p.add_argument("--dry-run", action="store_true", help="Synthesise spectra; no hardware needed")

    ble = p.add_argument_group("interactive mode (drive an OpenDisplay panel over BLE)")
    ble.add_argument(
        "--interactive",
        action="store_true",
        help="Panel cycles colors automatically while the CR30 stays put (needs the opendisplay extra)",
    )
    ble.add_argument("--address", help="BLE address/name of the OpenDisplay device")
    ble.add_argument("--key", help="Device encryption key as hex, if auth is required")
    ble.add_argument(
        "--settle",
        type=float,
        default=3.0,
        help="Extra seconds to wait after the panel reports refresh complete, before reading",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scheme = get_scheme(args.scheme)

    if args.temp is None:
        print(
            "WARNING: no --temp given. e-paper color is temperature-dependent; "
            "this palette will be recorded as UNRECORDED temperature.",
            file=sys.stderr,
        )

    if args.interactive:
        colors, serial = asyncio.run(_run_interactive(args, scheme))
    elif args.dry_run:
        provider = _dry_run_provider(args.count)
        serial = args.serial or "DRYRUN"
        colors = build_colors(scheme, provider)
    else:
        if not (args.port or args.cr30_ble):
            print("error: --port or --cr30-ble is required unless --dry-run is set", file=sys.stderr)
            return 2
        provider, get_serial = _hardware_provider(args)
        colors = build_colors(scheme, provider)
        serial = args.serial or get_serial()

    print(render_palette(scheme, colors, serial=serial, note=args.note, temperature_c=args.temp))

    if any(c.reading.clipped for c in colors):
        print(
            "NOTE: one or more colors are outside sRGB. The palette keeps their measured "
            "Lab; only the sRGB values in the sidecar are clamped.",
            file=sys.stderr,
        )

    if args.out:
        payload = spectra_sidecar(args.palette_id, scheme, colors, serial=serial, temperature_c=args.temp)
        write_sidecar(args.out, payload)
        print(f"Wrote raw spectra to {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
