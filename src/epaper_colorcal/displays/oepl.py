"""OpenEPaperLink tag, through its access point, via ``py-oepl`` (the ``oepl`` extra).

Each ink is uploaded as a solid image with the AP's dithering off. The tag fetches it at its
next check-in, so showing one ink takes up to a check-in interval. py-oepl returns once the
transfer is complete; the tag refreshes after that, so the measurement loop then waits until
the instrument reads a stable colour.

The refresh waveform ("LUT") changes the colours, red especially: a fast waveform drives the
particles less. The tag is measured with the full refresh by default and its stored LUT is
restored afterwards. Uploading also sets the tag's content mode to "external image"; that is
restored too.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from .base import Display

if TYPE_CHECKING:
    from ..schemes import Ink, Scheme

# --oepl-lut values -> py-oepl's LUT member names (whose names read backwards; see py-oepl).
LUTS = {"full": "NO_REPEAT", "adaptive": "DEFAULT", "fast-no-reds": "FAST_NO_REDS", "fast": "FAST"}

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


def _ink_name_for(tag_type: Any, ink_name: str) -> str:
    """The tag's colour-table name for an ink name (they match unless the table name needed cleaning)."""
    return next((n for n in tag_type.color_table if _ink_name(n) == ink_name), ink_name)


def _ink_name(name: str) -> str:
    """A colour-table name as an ink name (lowercase letters, digits, _)."""
    cleaned = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")
    return cleaned if cleaned and cleaned[0].isalpha() else f"c_{cleaned}"


class OEPLDisplay(Display):  # pylint: disable=too-many-instance-attributes  # settings + connection state
    def __init__(
        self,
        ap_host: str,
        mac: str,
        *,
        lut: str = "full",
        wait_timeout: float = 300.0,
        settle_seconds: float = 0.0,
    ) -> None:
        if lut not in LUTS:
            raise ValueError(f"unknown LUT {lut!r}; choose one of: {', '.join(LUTS)}")
        self._host = ap_host
        self._mac = mac.upper().replace(":", "")
        self._lut = lut
        self._wait_timeout = wait_timeout
        self._settle = settle_seconds
        self._client: Any = None
        self._tag_type: Any = None
        self._restore: dict[str, Any] = {}  # the tag's stored settings this measurement changes

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
            self._restore = {"lut": tag.lut, "content_mode": tag.content_mode}
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
        if await self._already_shows(ink):
            # The AP only waits for a *new* image: re-sending the one the tag already shows would
            # never complete. Show another of the tag's colours first.
            other = next(name for name in self._tag_type.color_table if name != ink.name)
            await self._upload(other, tuple(self._tag_type.color_table[other]))
        await self._upload(ink.name, ink.rgb)
        await asyncio.sleep(self._settle)

    async def _already_shows(self, ink: Ink) -> bool:
        """True if the tag's stored image is solid ``ink`` already."""
        try:
            image = await self._client.get_image(self._mac)
        except Exception:  # pylint: disable=broad-exception-caught  # can't tell: assume it doesn't
            return False
        if image is None:
            return False
        colors = image.convert("RGB").getcolors(maxcolors=1)
        if not colors:
            return False
        shown = tuple(colors[0][1])
        name = _ink_name_for(self._tag_type, ink.name)
        candidates = {tuple(self._tag_type.color_table.get(name, ink.rgb)), tuple(ink.rgb)}
        candidates.add(tuple(self._tag_type.display_colors.get(name, ink.rgb)))
        return shown in candidates

    async def _upload(self, name: str, rgb: tuple[int, ...]) -> None:
        from oepl import LUT, OEPLTimeoutError  # pylint: disable=import-outside-toplevel,import-error
        from PIL import Image  # pylint: disable=import-outside-toplevel

        image = Image.new("RGB", (self._tag_type.width, self._tag_type.height), tuple(rgb))
        # dither=0: the AP maps each pixel to the nearest colour of the tag, so the solid nominal
        # colour stays one ink. wait=True returns once the tag has received the image; it then
        # refreshes, which the measurement loop waits out with the instrument.
        try:
            await self._client.tag(self._mac).upload_image(
                image,
                fit="cover",
                dither=0,
                lut=LUT[LUTS[self._lut]],
                wait=True,
                wait_timeout=self._wait_timeout,
            )
        except OEPLTimeoutError as exc:
            raise TimeoutError(
                f"The tag {self._mac} did not finish showing {name} within {self._wait_timeout:g} s. "
                "Is it checking in, and is something else (e.g. Home Assistant) sending it images at the "
                "same time? --oepl-timeout raises the limit."
            ) from exc

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            if self._restore:  # put back the LUT and content mode the uploads changed
                await self._client.save_tag_config(self._mac, **self._restore)
        finally:
            await self._client.disconnect()
            self._client = None
