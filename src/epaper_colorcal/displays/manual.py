"""Manual display: a person shows each ink, then presses Enter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..prompts import ask
from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink


class ManualDisplay(Display):
    """Works with any panel: you show the ink full-screen, undithered, and seat the instrument.

    With ``static=True`` the samples don't change by themselves (a printed chart, paper): each
    is read as soon as Enter is pressed, with no waiting for a refresh to settle.
    """

    automatic = False

    def __init__(self, *, static: bool = False) -> None:
        self.static = static
        self.settled_after_show = static

    async def show(self, index: int, ink: Ink) -> None:
        if self.static:
            prompt = f"[{index + 1}] Seat the instrument on {ink.name.replace('_', ' ').upper()}, press Enter… "
        else:
            prompt = (
                f"Show {ink.name.upper()} ({ink.nominal}, undithered) full-screen, seat the instrument, press Enter… "
            )
        await ask(prompt)
