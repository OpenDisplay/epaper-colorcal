"""Simulated display for ``--dry-run``: prints what it would show."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink


class SimDisplay(Display):
    settled_after_show = True  # nothing to wait for

    def __init__(self) -> None:
        self.current: Ink | None = None
        """The ink on the simulated panel, for a :class:`~epaper_colorcal.instruments.SyntheticInstrument`."""

    async def show(self, index: int, ink: Ink) -> None:
        self.current = ink
        print(f"[sim] would show ink {index} ({ink.name}, {ink.nominal})", file=sys.stderr)
