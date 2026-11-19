"""Command display: run a command that puts the ink on the panel (``--show-command``).

The command is a template with these fields:

``{name}``   the ink name, e.g. ``red``
``{hex}``    its nominal colour without ``#``, e.g. ``ff0000``
``{r}`` ``{g}`` ``{b}``   the nominal colour's channels, 0-255
``{index}``  the ink's firmware index

It runs through the shell once per ink. It should return once the panel shows the ink;
``settle`` seconds are waited after it exits. A non-zero exit stops the measurement.
The command's output goes to stderr, so it never mixes with the palette on stdout.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink

FIELDS = ("name", "hex", "r", "g", "b", "index")


def render(template: str, index: int, ink: Ink) -> str:
    """The command for one ink. Ink names and colours are validated, so they are shell-safe."""
    r, g, b = ink.rgb
    return template.format(name=ink.name, hex=ink.nominal[1:], r=r, g=g, b=b, index=index)


class CommandDisplay(Display):
    def __init__(self, template: str, settle_seconds: float = 0.0) -> None:
        from ..schemes import Ink  # pylint: disable=import-outside-toplevel

        try:  # fail now, not after the CR30 is connected, if the template is malformed
            render(template, 0, Ink("white", "#ffffff"))
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"--show-command: bad template ({exc}); fields are {', '.join(FIELDS)}") from exc
        self._template = template
        self._settle = settle_seconds

    async def show(self, index: int, ink: Ink) -> None:
        command = render(self._template, index, ink)
        print(f"$ {command}", file=sys.stderr)
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        output, _ = await proc.communicate()
        if output:
            sys.stderr.write(output.decode(errors="replace"))
        if proc.returncode:
            raise RuntimeError(f"--show-command failed for {ink.name} (exit {proc.returncode}): {command}")
        await asyncio.sleep(self._settle)
