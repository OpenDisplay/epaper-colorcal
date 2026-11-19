"""The display port; see the package docstring for the adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemes import Ink, Scheme


class Display(ABC):
    """Shows one ink at a time, solid, on the panel being measured."""

    automatic = True
    """False if a person shows each ink (then nobody needs to be told to seat the instrument first)."""

    settled_after_show = False
    """True if :meth:`show` returns only once the panel has finished refreshing. Otherwise the
    measurement reads until the panel is stable before taking its readings."""

    async def temperature(self) -> float | None:
        """The panel's temperature in °C if the display knows it. Called before :meth:`connect`."""
        return None

    async def connect(self) -> None:  # noqa: B027 - optional hook
        """Open the connection, if any."""

    async def scheme(self) -> Scheme | None:
        """The inks the panel declares, if the display knows them. Called after :meth:`connect`."""
        return None

    @abstractmethod
    async def show(self, index: int, ink: Ink) -> None:
        """Show ``ink`` (at firmware index ``index``) and return once the panel has settled."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Release the connection, if any."""
