"""Command-line options for choosing an instrument, shared by the commands that read one."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instruments import Instrument


def add_instrument_options(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    group = parser.add_argument_group("the instrument")
    which = group.add_mutually_exclusive_group(required=required)
    which.add_argument("--port", help="the CR30 on this USB serial port (e.g. /dev/tty.wchusbserial120)")
    which.add_argument(
        "--cr30-ble",
        nargs="?",
        const="auto",
        metavar="NAME",
        help="the CR30 over Bluetooth: its name/address, or no value to find it by scanning",
    )
    which.add_argument(
        "--argyll",
        action="store_true",
        help="an instrument ArgyllCMS supports (e.g. an X-Rite i1Pro), through its spotread tool",
    )
    group.add_argument("--argyll-port", type=int, metavar="N", help="spotread's instrument port number (-c)")
    group.add_argument(
        "--argyll-filter", choices=["M0", "M1", "M2"], help="measurement condition, if the instrument has filters"
    )
    group.add_argument("--argyll-hires", action="store_true", help="high-resolution spectrum, if available")


def chosen(args: argparse.Namespace) -> bool:
    return bool(args.port or args.cr30_ble or args.argyll)


def describe_connection(args: argparse.Namespace) -> str:
    if args.argyll:
        return "ArgyllCMS"
    return f"USB {args.port}" if args.port else "Bluetooth"


def open_instrument(args: argparse.Namespace) -> Instrument:
    """The instrument the options choose (not yet connected)."""
    if args.argyll:
        from .argyll import SpotreadInstrument  # pylint: disable=import-outside-toplevel

        return SpotreadInstrument(
            port=args.argyll_port, filter_mode=args.argyll_filter, high_resolution=args.argyll_hires
        )
    from .cr30 import open_cr30  # pylint: disable=import-outside-toplevel

    return open_cr30(port=args.port, ble=args.cr30_ble)
