"""Thin async wrapper over the vendored CR30 protocol slice.

Keeps the ``serial_asyncio`` import lazy (it only happens when you actually
construct a reader), so the dry-run path and tests never need pyserial-asyncio.
"""

from __future__ import annotations


class CR30Reader:
    """Connect to a CR30, calibrate, and pull raw 31-band SPD reads."""

    def __init__(self, port: str, baudrate: int = 19200, verbose: bool = False) -> None:
        # Imported here so importing this module doesn't require serial_asyncio.
        from ._vendor.cr30.protocol import CR30Protocol

        self._dev = CR30Protocol(port=port, baudrate=baudrate, verbose=verbose)

    async def connect(self) -> None:
        await self._dev.connect()

    async def disconnect(self) -> None:
        await self._dev.disconnect()

    @property
    def serial_number(self) -> str:
        return str(self._dev.serial_number)

    @property
    def model(self) -> str:
        return str(self._dev.model)

    async def calibrate_black(self) -> bool:
        result = await self._dev.calibrate(white=False)
        return bool(result.get("success"))

    async def calibrate_white(self) -> bool:
        result = await self._dev.calibrate(white=True)
        return bool(result.get("success"))

    async def read_spd(self) -> list[float]:
        """Trigger one measurement and return its 31-band SPD."""
        result = await self._dev.measure()
        spd = result.get("spd") or []
        if len(spd) != 31:
            raise RuntimeError(f"expected 31 SPD bands, got {len(spd)} — measurement may have failed")
        return [float(v) for v in spd]
