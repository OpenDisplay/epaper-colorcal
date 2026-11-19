"""Manual display: a person shows each ink, then presses Enter."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink


class ManualDisplay(Display):
    """Works with any panel: you show the ink full-screen, undithered, and seat the CR30."""

    automatic = False

    async def show(self, index: int, ink: Ink) -> None:
        prompt = f"Show {ink.name.upper()} ({ink.nominal}, undithered) full-screen, seat the CR30, press Enter… "
        await asyncio.to_thread(input, prompt)
