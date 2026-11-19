"""CLI: measure a panel's inks with a CR30 and print a measured palette.

Shows each ink on the panel (you, a command, or an OpenDisplay board), reads it with the
CR30 over USB or Bluetooth, and prints an ``epaper-palette`` JSON document on stdout.
Prompts and notes go to stderr. ``--dry-run`` needs no hardware.

Example (no hardware):
    epaper-colorcal --scheme BWGBRY --id spectra6_13in3 --temp 23 --dry-run > spectra6_13in3.json
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import pathlib
import signal
import sys
from typing import TYPE_CHECKING

from .emit import MeasuredColor
from .measure import measure_all, measure_color
from .outputs import OUTPUTS, Measurement, get_output
from .schemes import SCHEMES, Scheme, get_scheme, parse_inks

if TYPE_CHECKING:
    from collections.abc import Callable

    from .displays import Display
    from .instruments import Instrument

__all__ = ["build_colors", "build_parser", "main", "measure_color"]


def build_colors(scheme: Scheme, provider: Callable[[str], list[list[float]]]) -> list[MeasuredColor]:
    """Measured colours from a synchronous provider of reads per ink name (library helper)."""
    return [measure_color(name, provider(name)) for name in scheme.colors]


def _display(args: argparse.Namespace) -> Display:
    from .displays import CommandDisplay, ManualDisplay, OEPLDisplay, OpenDisplayDisplay, SimDisplay

    if args.dry_run:
        return SimDisplay()
    if args.address:
        key = bytes.fromhex(args.key) if args.key else None
        return OpenDisplayDisplay(args.address, key=key, settle_seconds=args.settle)
    if args.oepl_ap:
        return OEPLDisplay(
            args.oepl_ap, args.oepl_tag, lut=args.oepl_lut, wait_timeout=args.oepl_timeout, settle_seconds=args.settle
        )
    if args.show_command:
        return CommandDisplay(args.show_command, settle_seconds=args.settle)
    return ManualDisplay()


def _instrument(args: argparse.Namespace, display: Display) -> Instrument:
    from .displays import SimDisplay
    from .instruments import SyntheticInstrument

    if args.dry_run:
        assert isinstance(display, SimDisplay)
        return SyntheticInstrument(display)
    from .cr30 import open_cr30

    return open_cr30(port=args.port, ble=args.cr30_ble)


async def _connect_instrument(args: argparse.Namespace, instrument: Instrument) -> None:
    """Connect the instrument, optionally calibrating it."""
    await instrument.connect()
    if args.dry_run:
        return
    via = f"USB {args.port}" if args.port else "BLE"
    print(f"Connected to {instrument.description} (s/n {instrument.serial_number}) over {via}.", file=sys.stderr)

    if args.calibrate:
        await asyncio.to_thread(input, "Close the CR30 cap fully (black calibration), then press Enter… ")
        if not await instrument.calibrate_black():
            raise SystemExit("Black calibration failed.")
        await asyncio.to_thread(input, "Keep the cap closed (white calibration), then press Enter… ")
        if not await instrument.calibrate_white():
            raise SystemExit("White calibration failed.")


def _resolve_scheme(requested: Scheme | None, declared: Scheme | None) -> Scheme:
    """The inks to measure: what was asked for, else what the display declares."""
    if requested is None:
        if declared is None:
            raise SystemExit("error: pass --scheme or --inks (this display doesn't report its inks)")
        print(f"Panel reports {declared.name}: {', '.join(declared.colors)}.", file=sys.stderr)
        return declared
    if declared is not None and requested.firmware_id is not None and requested.firmware_id != declared.firmware_id:
        raise SystemExit(f"error: the panel reports {declared.name}, but --scheme is {requested.name}")
    return requested


async def _measure(
    args: argparse.Namespace, requested: Scheme | None
) -> tuple[Scheme, list[MeasuredColor], Instrument]:
    # Stopping the tool (SIGTERM, like Ctrl-C) cancels the measurement, so the finally blocks
    # below still run and e.g. an OEPL tag gets its settings back.
    task = asyncio.current_task()
    if task is not None:
        with contextlib.suppress(NotImplementedError, RuntimeError):  # not on Windows
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)

    display = _display(args)
    if args.temp is None:
        args.temp = await display.temperature()
        if args.temp is not None:
            print(f"Panel temperature: {args.temp:g} °C, reported by the display (--temp overrides).", file=sys.stderr)

    instrument = _instrument(args, display)
    await _connect_instrument(args, instrument)
    try:
        if display.automatic and not args.dry_run and sys.stdin.isatty():
            await asyncio.to_thread(input, "Seat the CR30 flat on the panel, then press Enter to start… ")
        await display.connect()
        try:
            scheme = _resolve_scheme(requested, await display.scheme())
            colors = await measure_all(scheme, display, instrument, args.count)
        finally:
            await display.close()
    finally:
        await instrument.close()
    return scheme, colors, instrument


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="epaper-colorcal", description=__doc__)
    inks = p.add_mutually_exclusive_group()
    inks.add_argument("--scheme", help=f"Preset ink set: {', '.join(SCHEMES)}")
    inks.add_argument(
        "--inks",
        help="Custom ink list in firmware order, e.g. black,white,orange=#ff8000 "
        "(black, white, red, yellow, blue, green, orange need no colour)",
    )
    p.add_argument("--id", required=True, dest="palette_id", help="Name for this measurement (stored in the sidecar)")
    p.add_argument("--count", type=int, default=3, help="Reads averaged per ink (default 3)")
    p.add_argument("--temp", type=float, default=None, help="Panel temperature in °C (default: from the display)")
    p.add_argument("--note", default="", help="Free text put at the start of the palette's source, e.g. the panel")
    p.add_argument("--serial", default=None, help="Override the recorded instrument serial")
    p.add_argument(
        "--format",
        choices=list(OUTPUTS),
        default="epaper-palette",
        help="What to print: epaper-palette (default; epaper-dithering, py-opendisplay), "
        "oepl (a perceptual block for an OpenEPaperLink tag type) or spectra",
    )
    p.add_argument("--out", default=None, help="Also write the raw spectra (JSON) to this file")
    p.add_argument("--dry-run", action="store_true", help="Synthetic spectra and a simulated panel; no hardware")

    cr30 = p.add_argument_group("the CR30").add_mutually_exclusive_group()
    cr30.add_argument("--port", help="USB serial port of the CR30 (e.g. /dev/tty.wchusbserial120)")
    cr30.add_argument(
        "--cr30-ble",
        nargs="?",
        const="auto",
        metavar="NAME",
        help="Use the CR30 over Bluetooth: its name/address, or no value to find it by scanning",
    )
    p.add_argument(
        "--calibrate",
        action="store_true",
        help="Explicit black/white calibration first (USB). The CR30 calibrates itself against its cap.",
    )

    show = p.add_argument_group("showing the inks (default: you show each one and press Enter)")
    show.add_argument("--address", help="Drive this OpenDisplay board over Bluetooth (name, MAC or macOS UUID)")
    show.add_argument("--key", help="The OpenDisplay board's encryption key as hex, if it has one")
    show.add_argument("--oepl-ap", metavar="HOST", help="Show the inks on an OpenEPaperLink tag through this AP")
    show.add_argument("--oepl-tag", metavar="MAC", help="The OpenEPaperLink tag's MAC (with --oepl-ap)")
    show.add_argument(
        "--oepl-lut",
        choices=["full", "adaptive", "fast-no-reds", "fast"],
        default="full",
        help="Refresh waveform for the OpenEPaperLink tag while measuring (default full; restored afterwards)",
    )
    show.add_argument(
        "--oepl-timeout",
        type=float,
        default=300.0,
        help="Seconds to wait for the tag to check in and redraw each ink (default 300)",
    )
    show.add_argument(
        "--show-command",
        metavar="CMD",
        help="Run CMD to show each ink; fields {name} {hex} {r} {g} {b} {index}, e.g. "
        "'curl -fsS http://frame.local/fill?color={hex}'",
    )
    show.add_argument(
        "--settle", type=float, default=3.0, help="Seconds to wait after the ink is shown, before reading (default 3)"
    )
    show.add_argument("--interactive", action="store_true", help=argparse.SUPPRESS)  # pre-0.3 flag; now implied
    return p


def _check_args(args: argparse.Namespace) -> str | None:
    """What's wrong with the arguments, if anything."""
    if sum(bool(x) for x in (args.address, args.oepl_ap, args.show_command)) > 1:
        return "--address, --oepl-ap and --show-command all show the inks; pick one"
    if bool(args.oepl_ap) != bool(args.oepl_tag):
        return "--oepl-ap and --oepl-tag go together"
    if not args.dry_run and not (args.port or args.cr30_ble):
        return "connect the CR30 with --port or --cr30-ble (or use --dry-run)"
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = _check_args(args)
    try:
        requested = get_scheme(args.scheme) if args.scheme else parse_inks(args.inks) if args.inks else None
    except ValueError as exc:
        problem = problem or str(exc)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    try:
        scheme, colors, instrument = asyncio.run(_measure(args, requested))
    except TimeoutError as exc:  # the display's and instrument's cleanup has already run
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("Stopped. The display and instrument were closed (an OEPL tag got its settings back).", file=sys.stderr)
        return 130
    serial = args.serial or instrument.serial_number

    if args.temp is None:
        print(
            "WARNING: no panel temperature (--temp). e-paper colour is temperature-dependent; "
            "this palette is recorded with the temperature UNRECORDED.",
            file=sys.stderr,
        )
    measurement = Measurement(
        palette_id=args.palette_id,
        scheme=scheme,
        colors=colors,
        instrument=instrument.description,
        serial=serial,
        temperature_c=args.temp,
        note=args.note,
    )
    print(get_output(args.format).render(measurement))

    if any(c.reading.clipped for c in colors):
        print(
            "NOTE: one or more colours are outside sRGB. Palettes keep their measured Lab; "
            "sRGB values (the oepl format, the spectra file) are clamped.",
            file=sys.stderr,
        )
    if args.out:
        pathlib.Path(args.out).write_text(get_output("spectra").render(measurement) + "\n", encoding="utf-8")
        print(f"Wrote raw spectra to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
