"""Displays: how each ink gets onto the panel before the CR30 reads it.

:class:`Display` is the port; the adapters are

* :class:`ManualDisplay`: asks you to show the ink and press Enter (any panel),
* :class:`CommandDisplay`: runs a command you give (``--show-command``),
* :class:`OpenDisplayDisplay`: an OpenDisplay board over Bluetooth (``--address``),
* :class:`SimDisplay`: prints what it would show (``--dry-run``).

A display may also know things about the panel: the inks it can show
(:meth:`Display.scheme`) and its temperature (:meth:`Display.temperature`).
"""

from .base import Display
from .command import CommandDisplay
from .manual import ManualDisplay
from .opendisplay import OpenDisplayDisplay
from .sim import SimDisplay

__all__ = ["CommandDisplay", "Display", "ManualDisplay", "OpenDisplayDisplay", "SimDisplay"]
