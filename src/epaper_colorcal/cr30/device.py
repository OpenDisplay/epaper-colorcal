"""Talk to a CR30 over USB serial or BLE through one async interface.

The transport libraries (pyserial-asyncio, bleak) are imported lazily, so the rest of
the package and the tests work without either installed.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from abc import abstractmethod
from typing import Any

from ..instruments import Instrument
from ..spectrum import Spectrum
from . import frames as f
from .frames import DeviceInfo, FrameError

BLE_SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
BLE_CHAR = "0000ffe1-0000-1000-8000-00805f9b34fb"
BLE_WAKE = b"\x01"  # written before every command to wake the BLE module
BLE_CHUNK = 20
BLE_CHUNK_DELAY = 0.01
BLE_SETTLE = 0.5  # after enabling notifications, as the vendor app does

TIMEOUT = 3.0
MEASURE_TIMEOUT = 6.0
CALIBRATE_TIMEOUT = 13.0

SILENT_HINT = (
    "Is the CR30 switched on and in range? It turns itself off when idle or when its battery runs low: "
    "press its button (and plug in USB to charge), then try again."
)


class CR30(Instrument):
    """A CHNSpec CR30. Use as ``async with`` or call :meth:`connect`/:meth:`close`."""

    info: DeviceInfo | None = None

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def measure(self) -> Spectrum:
        """Trigger one scan; return its 31-band reflectance (percent, 400-700 nm).

        On a steady sample, consecutive scans can be bit-identical: the device's output is
        quantised. That is a real reading, not a stale one.
        """
        return Spectrum(tuple(float(w) for w in f.WAVELENGTHS), tuple(await self._read_spd()))

    @abstractmethod
    async def _read_spd(self) -> list[float]:
        """Trigger one scan and read its 31 reflectance values over this transport."""

    @property
    def model(self) -> str:
        return self.info.model if self.info else "unknown"

    @property
    def serial_number(self) -> str:
        return self.info.serial if self.info else "unknown"

    @property
    def description(self) -> str:
        return "CHNSpec CR30"


class UsbCR30(CR30):
    """CR30 on its USB serial port (19200 8N1, 60-byte frames)."""

    def __init__(self, port: str, *, baudrate: int = 19200, streams: tuple[Any, Any] | None = None) -> None:
        self._port = port
        self._baudrate = baudrate
        self._reader: Any = None
        self._writer: Any = None
        if streams is not None:  # injected (reader, writer), for tests
            self._reader, self._writer = streams

    async def connect(self) -> None:
        if self._reader is None:
            import serial_asyncio  # pylint: disable=import-outside-toplevel,import-error  # optional extra

            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self._port, baudrate=self._baudrate
            )
        await self._drain()
        pages = [await self._exchange(f.START_QUERY, f.CMD_INFO, page) for page in f.USB_INFO_PAGES]
        self.info = f.info_from_usb_pages(pages)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
        self._reader = self._writer = None

    async def _read_spd(self) -> list[float]:
        await self._exchange(f.START_COMMAND, f.CMD_MEASURE, 0, timeout=MEASURE_TIMEOUT)
        pages = [await self._exchange(f.START_COMMAND, f.CMD_MEASURE, sub) for sub in f.USB_SPD_PAGES]
        await self._exchange(f.START_COMMAND, f.CMD_MEASURE, f.USB_SPD_END)
        return f.spd_from_usb_pages(pages)

    async def calibrate_black(self) -> bool:
        return await self._calibrate(f.CMD_CALIBRATE_BLACK)

    async def calibrate_white(self) -> bool:
        return await self._calibrate(f.CMD_CALIBRATE_WHITE)

    async def _calibrate(self, cmd: int) -> bool:
        reply = await self._exchange(f.START_COMMAND, cmd, 0, timeout=CALIBRATE_TIMEOUT)
        return reply[6] == 1  # payload[2]; verified on hardware (see docs/cr30-protocol.md)

    async def _drain(self) -> None:
        """Discard anything already buffered (e.g. a button-press frame)."""
        with contextlib.suppress(asyncio.TimeoutError):
            while await asyncio.wait_for(self._reader.read(4096), 0.2):
                pass

    async def _exchange(self, start: int, cmd: int, sub: int, *, timeout: float | None = None) -> bytes:
        self._writer.write(f.usb_frame(start, cmd, sub))
        await self._writer.drain()
        try:
            reply = await asyncio.wait_for(self._reader.readexactly(f.USB_FRAME_LEN), timeout or TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"The CR30 did not answer (command 0x{cmd:02x}) on {self._port}. {SILENT_HINT}") from exc
        return f.check_reply(reply, cmd, length=f.USB_FRAME_LEN)


class BleCR30(CR30):
    """CR30 over Bluetooth LE (service FFE0, characteristic FFE1)."""

    def __init__(self, address: str | None = None, *, client: Any = None) -> None:
        self._address = address
        self._client: Any = client  # injected for tests
        self._buffer = bytearray()
        self._expected = 0
        self._reply: asyncio.Future[bytes] | None = None

    async def connect(self) -> None:
        if self._client is None:
            from bleak import BleakClient  # pylint: disable=import-outside-toplevel,import-error  # optional extra

            self._client = BleakClient(await find_ble_cr30(self._address))
        await self._client.connect()
        await self._client.start_notify(BLE_CHAR, self._on_notify)
        await asyncio.sleep(BLE_SETTLE)
        self.info = f.info_from_ble(await self._command(f.CMD_DEVICE_INFO, (1, 0, 0, 0, 0, 0), 200))

    async def close(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.disconnect()

    async def _read_spd(self) -> list[float]:
        nonce = tuple(os.urandom(4))
        ack = await self._command(f.CMD_MEASURE, (0, *nonce, 0), 10, timeout=MEASURE_TIMEOUT)
        if ack[3] != 0:
            raise FrameError(f"measurement failed with status {ack[3]}")
        reply = await self._command(f.CMD_MEASURE_DATA, (f.BLE_MODE_ECHO, 0, 0, 0, 0, 0), 200)
        return f.spd_from_ble(reply)

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        self._buffer.extend(data)
        if self._reply is not None and not self._reply.done() and len(self._buffer) >= self._expected:
            self._reply.set_result(bytes(self._buffer))

    async def _command(self, op: int, params: tuple[int, ...], length: int, *, timeout: float | None = None) -> bytes:
        """Send one command and return its reply, retrying once.

        A command is occasionally not answered at all (0 bytes), seen on hardware right after
        connecting and as the first command after a minute without traffic; the module seems to
        doze and miss the wake byte. A second attempt, with a fresh wake byte, has worked each
        time. (Repeating a measurement trigger only takes one more scan.)
        """
        try:
            return await self._attempt(op, params, length, timeout=timeout)
        except TimeoutError:
            return await self._attempt(op, params, length, timeout=timeout)

    async def _attempt(self, op: int, params: tuple[int, ...], length: int, *, timeout: float | None = None) -> bytes:
        self._buffer = bytearray()
        self._expected = length
        self._reply = asyncio.get_running_loop().create_future()
        await self._client.write_gatt_char(BLE_CHAR, BLE_WAKE, response=False)
        frame = f.ble_frame(op, *params)
        for i in range(0, len(frame), BLE_CHUNK):
            await self._client.write_gatt_char(BLE_CHAR, frame[i : i + BLE_CHUNK], response=False)
            await asyncio.sleep(BLE_CHUNK_DELAY)
        try:
            reply = await asyncio.wait_for(self._reply, timeout or TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"The CR30 did not answer (command 0x{op:02x}) over Bluetooth. {SILENT_HINT}") from exc
        return f.check_reply(reply, op, length=length)


async def find_ble_cr30(name_or_address: str | None = None, timeout: float = 10.0) -> Any:
    """Find a CR30 by advertised name or address, or the first device advertising FFE0."""
    from bleak import BleakScanner  # pylint: disable=import-outside-toplevel,import-error  # optional extra

    wanted = name_or_address.lower() if name_or_address else None

    def match(device: Any, adv: Any) -> bool:
        if wanted is not None:
            return wanted in {str(device.address).lower(), str(adv.local_name or device.name or "").lower()}
        return BLE_SERVICE in [u.lower() for u in adv.service_uuids or []]

    device = await BleakScanner.find_device_by_filter(match, timeout=timeout)
    if device is None:
        what = f"'{name_or_address}'" if name_or_address else "a CR30 (BLE service FFE0)"
        raise SystemExit(f"No BLE device found for {what}. Is the CR30 switched on and in range?")
    return device


def open_cr30(*, port: str | None = None, ble: str | None = None) -> CR30:
    """A CR30 on a USB serial ``port``, or over BLE (``ble`` = name, address or "auto")."""
    if port and ble:
        raise ValueError("pass either port or ble, not both")
    if port:
        return UsbCR30(port)
    if ble:
        return BleCR30(None if ble == "auto" else ble)
    raise ValueError("pass a USB serial port or a BLE name/address")
