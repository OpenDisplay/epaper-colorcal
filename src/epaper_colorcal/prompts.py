"""Asking the person at the instrument, on stderr so stdout stays the measurement's output."""

from __future__ import annotations

import asyncio
import sys


def ask_sync(prompt: str) -> str:
    """Show ``prompt`` on stderr and return the line typed (``input()`` would print it to stdout)."""
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


async def ask(prompt: str) -> str:
    """:func:`ask_sync` without blocking the event loop."""
    return await asyncio.to_thread(ask_sync, prompt)
