"""Vendored CR30 serial-protocol slice from itohio/color-science (MIT).

See NOTICE and LICENSE-itohio in this directory. Only the protocol layer needed
to connect, calibrate, and read the raw 31-band SPD is kept; epaper-colorcal
does its own colorimetry.

``device`` imports ``serial_asyncio`` lazily, so importing ``CR30Packet`` /
``PacketBuilder`` / ``PacketParser`` (pure-Python, used by the dry-run path and
tests) does not require pyserial-asyncio to be installed.
"""

from .packets import CR30Packet, PacketBuilder, PacketParser

__all__ = ["CR30Packet", "PacketBuilder", "PacketParser", "CR30Protocol", "CR30Device"]


def __getattr__(name: str) -> object:
    # Lazy import: only pull in device/protocol (which need serial_asyncio) on demand.
    if name in ("CR30Protocol", "CR30Device"):
        from .device import CR30Device
        from .protocol import CR30Protocol

        return {"CR30Protocol": CR30Protocol, "CR30Device": CR30Device}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
