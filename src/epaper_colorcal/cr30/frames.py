"""CR30 wire frames: build, validate and decode. Pure functions, no I/O.

The CR30 speaks one command set over two transports with two framings:

* **USB serial**: every frame, both ways, is exactly 60 bytes:
  ``[start, cmd, sub, param, payload(54)..., 0xFF, checksum]``.
* **BLE** (HM-10 style bridge, characteristic ``FFE1``): short, variable-length frames
  ``[0xBB, op, *params, 0xFF, checksum]``. The device ignores 60-byte frames here.

Both use one checksum rule in both directions: the low byte of the sum of every
preceding byte, the ``0xFF`` marker included. Verified on a CR30 (fw 0.0.20231219).

Protocol knowledge: USB from itohio's reverse engineering
(https://itohi.com/colorimetry/reverse-engineering-cr30/), BLE from the vendor app.
Every layout here was confirmed against captured frames (``tests/fixtures/cr30_frames.json``).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

WAVELENGTHS: tuple[int, ...] = tuple(range(400, 701, 10))
"""The CR30's 31 bands, 400-700 nm in 10 nm steps."""

USB_FRAME_LEN = 60
START_QUERY = 0xAA
START_COMMAND = 0xBB
MARKER = 0xFF

# Command bytes (shared by both transports).
CMD_MEASURE = 0x01
CMD_INFO = 0x0A  # USB only, with START_QUERY; sub = page 0..2
CMD_MEASURE_DATA = 0x02  # BLE fetch of the last scan
CMD_CALIBRATE_BLACK = 0x10
CMD_CALIBRATE_WHITE = 0x11
CMD_DEVICE_INFO = 0x12  # BLE

# USB measurement: the spectrum is read in pages after the trigger.
USB_SPD_PAGES = (0x10, 0x11, 0x12)
USB_SPD_END = 0x13
USB_PAGE_DATA = slice(6, 54)  # 48 bytes = 12 float32 per page

USB_INFO_PAGES = (0, 1, 2)
USB_INFO_DATA = slice(5, 55)  # 50 bytes of the device-info record per page
USB_INFO_RECORD_OFFSET = 3  # page 0 starts at record byte 3

BLE_SPD_OFFSET = 8
BLE_MODE_ECHO = 16  # the fetch's mode parameter is mode + 16

# Device-info record (BLE reply layout; USB pages rebuild the same record).
_INFO_FIELDS = {"model": 37, "serial": 67, "software": 97, "hardware": 127}
_INFO_FIELD_LEN = 30


class FrameError(ValueError):
    """A frame was malformed, failed its checksum, or answered a different command."""


@dataclass(frozen=True)
class DeviceInfo:
    model: str
    serial: str
    software: str
    hardware: str


def checksum(data: bytes | bytearray) -> int:
    """Low byte of the sum of ``data``."""
    return sum(data) & 0xFF


def is_valid(frame: bytes | bytearray) -> bool:
    """True if the last byte is the checksum of the rest."""
    return len(frame) >= 2 and frame[-1] == checksum(frame[:-1])


def usb_frame(start: int, cmd: int, sub: int = 0, param: int = 0) -> bytes:
    """A 60-byte USB command frame with an empty payload."""
    frame = bytearray(USB_FRAME_LEN)
    frame[0:4] = bytes([start, cmd, sub, param])
    frame[-2] = MARKER
    frame[-1] = checksum(frame[:-1])
    return bytes(frame)


def ble_frame(op: int, *params: int) -> bytes:
    """A short BLE command frame."""
    body = bytes([START_COMMAND, op, *params, MARKER])
    return body + bytes([checksum(body)])


def check_reply(reply: bytes, cmd: int, *, length: int | None = None) -> bytes:
    """Validate a reply's length, checksum and command byte; return it unchanged."""
    if length is not None and len(reply) != length:
        raise FrameError(f"expected {length} bytes, got {len(reply)}: {reply.hex(' ')}")
    if not is_valid(reply):
        raise FrameError(f"bad checksum: {reply.hex(' ')}")
    if reply[1] != cmd:
        raise FrameError(f"expected a reply to 0x{cmd:02x}, got 0x{reply[1]:02x}: {reply.hex(' ')}")
    return reply


def decode_spd(data: bytes) -> list[float]:
    """31 little-endian float32 reflectances (percent)."""
    n = len(WAVELENGTHS)
    if len(data) < 4 * n:
        raise FrameError(f"need {4 * n} bytes of spectrum, got {len(data)}")
    return list(struct.unpack_from(f"<{n}f", data))


def spd_from_usb_pages(pages: list[bytes]) -> list[float]:
    """Spectrum from the three USB data pages (replies to sub 0x10, 0x11, 0x12)."""
    return decode_spd(b"".join(page[USB_PAGE_DATA] for page in pages))


def spd_from_ble(reply: bytes) -> list[float]:
    """Spectrum from a BLE measure-data reply (200 bytes)."""
    data_type, bands = reply[3], reply[7]
    if data_type != 0:
        raise FrameError(f"device returned data type {data_type}, not a spectrum")
    if bands != len(WAVELENGTHS):
        raise FrameError(f"device reports {bands} bands, expected {len(WAVELENGTHS)}")
    return decode_spd(reply[BLE_SPD_OFFSET:])


def _info_from_record(record: bytes) -> DeviceInfo:
    def text(offset: int) -> str:
        field = record[offset : offset + _INFO_FIELD_LEN]
        return field.split(b"\x00", 1)[0].decode("ascii", errors="replace")

    return DeviceInfo(**{name: text(offset) for name, offset in _INFO_FIELDS.items()})


def info_from_ble(reply: bytes) -> DeviceInfo:
    """Device info from the BLE ``0x12`` reply."""
    return _info_from_record(reply)


def info_from_usb_pages(pages: list[bytes]) -> DeviceInfo:
    """Device info from the USB ``AA 0A 00/01/02`` replies (the same record, paged)."""
    record = bytes(USB_INFO_RECORD_OFFSET) + b"".join(page[USB_INFO_DATA] for page in pages)
    return _info_from_record(record)
