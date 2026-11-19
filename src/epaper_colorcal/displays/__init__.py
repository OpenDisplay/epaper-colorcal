"""Displays: how each ink gets onto the panel before the instrument reads it.

:class:`Display` is the port; the adapters are

* :class:`ManualDisplay`: asks you to show the ink and press Enter (any panel),
* :class:`CommandDisplay`: runs a command you give (``--show-command``),
* :class:`OpenDisplayDisplay`: an OpenDisplay board over Bluetooth (``--address``),
* :class:`OEPLDisplay`: an OpenEPaperLink tag through its access point (``--oepl-ap``),
* :class:`ATCDisplay`: a tag with ATC BLE OEPL firmware, directly over Bluetooth (``--atc``),
* :class:`SimDisplay`: prints what it would show (``--dry-run``).

A display may also know things about the panel: the inks it can show
(:meth:`Display.scheme`) and its temperature (:meth:`Display.temperature`).
"""

from .atc import ATCDisplay
from .base import Display
from .command import CommandDisplay
from .manual import ManualDisplay
from .oepl import OEPLDisplay
from .opendisplay import OpenDisplayDisplay
from .sim import SimDisplay

__all__ = [
    "ATCDisplay",
    "CommandDisplay",
    "Display",
    "ManualDisplay",
    "OEPLDisplay",
    "OpenDisplayDisplay",
    "SimDisplay",
]
