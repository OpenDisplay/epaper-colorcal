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

from .colorimetry import average_spds, reading_from_spd
from .emit import MeasuredColor, render_palette, spectra_sidecar, write_sidecar
from .schemes import Scheme, get_scheme
from .synthetic import IDEAL_SRGB, synthetic_spd

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


def _hardware_provider(port: str, count: int, verbose: bool) -> tuple[SpdProvider, Callable[[], str]]:
    """Build a provider that prompts the operator and reads the CR30.

    Returns the provider plus a callable to fetch the device serial after connect.
    Importing/handshaking happens on first use so --dry-run never touches serial.
    """
    from .reader import CR30Reader

    reader = CR30Reader(port=port, verbose=verbose)
    loop = asyncio.new_event_loop()

    loop.run_until_complete(reader.connect())
    print(f"Connected to {reader.model} (s/n {reader.serial_number}).", file=sys.stderr)

    input("Place the CR30 on the BLACK calibration tile, then press Enter… ")
    if not loop.run_until_complete(reader.calibrate_black()):
        raise SystemExit("Black calibration failed.")
    input("Place the CR30 on the WHITE calibration tile, then press Enter… ")
    if not loop.run_until_complete(reader.calibrate_white()):
        raise SystemExit("White calibration failed.")

    def provide(name: str) -> list[list[float]]:
        input(f"Fill the panel with solid {name.upper()}, seat the CR30 against it, then press Enter… ")
        reads: list[list[float]] = []
        for i in range(count):
            reads.append(loop.run_until_complete(reader.read_spd()))
            print(f"  read {i + 1}/{count} ok", file=sys.stderr)
        return reads

    return provide, (lambda: reader.serial_number)


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
    if not args.port:
        raise SystemExit("--port (the CR30) is required for interactive mode (or add --dry-run)")

    from .reader import CR30Reader

    reader = CR30Reader(port=args.port, verbose=args.verbose)
    await reader.connect()
    print(f"Connected to {reader.model} (s/n {reader.serial_number}).", file=sys.stderr)

    input("Place the CR30 on the BLACK calibration tile, then press Enter… ")
    if not await reader.calibrate_black():
        raise SystemExit("Black calibration failed.")
    input("Place the CR30 on the WHITE calibration tile, then press Enter… ")
    if not await reader.calibrate_white():
        raise SystemExit("White calibration failed.")
    input("Now seat the CR30 flat against the panel and press Enter to start the sweep… ")

    key = bytes.fromhex(args.key) if args.key else None
    ble_panel = OpenDisplayPanel(args.address, scheme, key=key, settle_seconds=args.settle)
    await ble_panel.connect()
    try:

        async def cr30_source(name: str) -> list[float]:
            return await reader.read_spd()

        colors = await measure_interactive(scheme, ble_panel, cr30_source, args.count)
    finally:
        await ble_panel.close()
        await reader.disconnect()

    return colors, args.serial or reader.serial_number


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="epaper-colorcal", description=__doc__)
    p.add_argument("--scheme", required=True, help="Color scheme: MONO, BWR, BWY, BWRY, BWGBRY")
    p.add_argument(
        "--id",
        required=True,
        dest="palette_id",
        help="Name for this measurement, e.g. spectra6_13in3 (recorded in the sidecar)",
    )
    p.add_argument("--port", help="Serial port of the CR30 (e.g. /dev/tty.usbserial-XXXX)")
    p.add_argument("--count", type=int, default=3, help="SPD reads to average per color (default 3)")
    p.add_argument("--temp", type=float, default=None, help="Panel temperature in °C (strongly recommended)")
    p.add_argument("--note", default="", help="Free-text note, e.g. the panel model, prepended to the palette's source")
    p.add_argument("--serial", default=None, help="Override the recorded instrument serial")
    p.add_argument("--out", default=None, help="Path to write the raw-spectra JSON sidecar")
    p.add_argument("--dry-run", action="store_true", help="Synthesise spectra; no hardware needed")
    p.add_argument("--verbose", action="store_true", help="Verbose CR30 protocol logging")

    ble = p.add_argument_group("interactive mode (drive an OpenDisplay panel over BLE)")
    ble.add_argument(
        "--interactive",
        action="store_true",
        help="Panel cycles colors automatically while the CR30 stays put (needs the opendisplay extra)",
    )
    ble.add_argument("--address", help="BLE address/name of the OpenDisplay device")
    ble.add_argument("--key", help="Device encryption key as hex, if auth is required")
    ble.add_argument("--settle", type=float, default=25.0, help="Seconds to wait for e-paper refresh before each read")
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
        if not args.port:
            print("error: --port is required unless --dry-run is set", file=sys.stderr)
            return 2
        provider, get_serial = _hardware_provider(args.port, args.count, args.verbose)
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
