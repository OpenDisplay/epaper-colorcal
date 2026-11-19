"""OpenEPaperLink tag, through its access point, via ``py-oepl`` (the ``oepl`` extra).

Each ink is uploaded as a solid image with the AP's dithering off. The tag fetches it at its
next check-in, so showing one ink takes up to a check-in interval; py-oepl waits until the
tag reports the new image drawn (its hash changed and nothing pending).

Uploading changes the tag's content mode to "external image", like any image upload.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink, Scheme

# A tag without a temperature sensor reports 0; outside this range is no reading either.
PLAUSIBLE_TAG_TEMP_C = (-20.0, 60.0)
WS_CONNECT_TIMEOUT = 15.0


def _client(host: str) -> Any:
    try:
        from oepl import OEPLClient  # pylint: disable=import-outside-toplevel,import-error
    except ImportError as exc:  # pragma: no cover - only without the extra
        raise SystemExit(
            "Driving an OpenEPaperLink tag needs py-oepl (Python 3.12+):\n    pip install 'epaper-colorcal[oepl]'"
        ) from exc
    return OEPLClient(host)


def _ink_name(name: str) -> str:
    """A colour-table name as an ink name (lowercase letters, digits, _)."""
    cleaned = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")
    return cleaned if cleaned and cleaned[0].isalpha() else f"c_{cleaned}"


class OEPLDisplay(Display):
    def __init__(self, ap_host: str, mac: str, *, wait_timeout: float = 300.0, settle_seconds: float = 0.0) -> None:
        self._host = ap_host
        self._mac = mac.upper().replace(":", "")
        self._wait_timeout = wait_timeout
        self._settle = settle_seconds
        self._client: Any = None
        self._tag_type: Any = None

    async def temperature(self) -> float | None:
        client = _client(self._host)
        try:
            tag = await client.get_tag(self._mac)
        finally:
            await client.disconnect()
        if tag is None or tag.temperature == 0:
            return None
        low, high = PLAUSIBLE_TAG_TEMP_C
        return float(tag.temperature) if low <= tag.temperature <= high else None

    async def connect(self) -> None:
        client = _client(self._host)
        await client.connect()  # starts the WebSocket, which waiting for the redraw needs
        try:
            tag = await client.get_tag(self._mac)
            if tag is None:
                raise SystemExit(f"The access point {self._host} doesn't know a tag {self._mac}.")
            self._tag_type = await client.get_tag_type(tag.hw_type)
            if self._tag_type is None:
                raise SystemExit(f"The access point has no definition of tag type 0x{tag.hw_type:02X}.")
            loop = asyncio.get_running_loop()
            deadline = loop.time() + WS_CONNECT_TIMEOUT
            while not client.connected:
                if loop.time() > deadline:
                    raise SystemExit(f"Could not open the access point's WebSocket at {self._host}.")
                await asyncio.sleep(0.1)
        except BaseException:
            await client.disconnect()
            raise
        self._client = client

    async def scheme(self) -> Scheme | None:
        """The tag's colour table, in its own order (white first on OEPL)."""
        from ..schemes import Ink, Scheme  # pylint: disable=import-outside-toplevel

        inks = tuple(
            Ink(_ink_name(name), f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
            for name, rgb in self._tag_type.color_table.items()
        )
        return Scheme(f"OEPL {self._tag_type.name}".strip(), inks)

    async def show(self, index: int, ink: Ink) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before show()")
        from PIL import Image  # pylint: disable=import-outside-toplevel

        image = Image.new("RGB", (self._tag_type.width, self._tag_type.height), ink.rgb)
        # dither=0: the AP maps each pixel to the nearest colour of the tag, so the solid nominal
        # colour stays one ink. wait=True returns once the tag reports the image drawn.
        await self._client.tag(self._mac).upload_image(
            image, fit="cover", dither=0, wait=True, wait_timeout=self._wait_timeout
        )
        await asyncio.sleep(self._settle)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
