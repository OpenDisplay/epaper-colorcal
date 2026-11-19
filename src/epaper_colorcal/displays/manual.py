"""Manual display: a person shows each ink, then presses Enter."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink


class ManualDisplay(Display):
    """Works with any panel: you show the ink full-screen, undithered, and seat the CR30.

    With ``static=True`` the samples don't change by themselves (a printed chart, paper): each
    is read as soon as Enter is pressed, with no waiting for a refresh to settle.
    """

    automatic = False

    def __init__(self, *, static: bool = False) -> None:
        self.static = static
        self.settled_after_show = static

    async def show(self, index: int, ink: Ink) -> None:
        if self.static:
            prompt = f"[{index + 1}] Seat the CR30 on {ink.name.replace('_', ' ').upper()}, press Enter… "
        else:
            prompt = f"Show {ink.name.upper()} ({ink.nominal}, undithered) full-screen, seat the CR30, press Enter… "
        await asyncio.to_thread(input, prompt)
