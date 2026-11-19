"""Simulated display for ``--dry-run``: prints what it would show."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink


class SimDisplay(Display):
    async def show(self, index: int, ink: Ink) -> None:
        print(f"[sim] would show ink {index} ({ink.name}, {ink.nominal})", file=sys.stderr)
