"""CR30 protocol tests against frames captured from a real device (no hardware needed).

``fixtures/cr30_frames.json`` holds one scan read over both transports: triggered and
fetched over BLE, then the same scan's pages read over USB without a new trigger.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from epaper_colorcal.cr30 import BleCR30, DeviceInfo, FrameError, UsbCR30, open_cr30
from epaper_colorcal.cr30 import frames as f

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "cr30_frames.json").read_text())
USB = {name: {k: bytes.fromhex(v) for k, v in x.items()} for name, x in FIXTURES["usb"].items()}
BLE = {name: {k: bytes.fromhex(v) for k, v in x.items()} for name, x in FIXTURES["ble"].items()}
EXPECTED_INFO = DeviceInfo(model="CR30", serial="CM454M1246", software="V11.3.0.0.20231219", hardware="V10.0.0.0")


# ── frames ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("frame", [x["reply"] for x in (*USB.values(), *BLE.values())])
def test_every_device_reply_uses_the_single_checksum_rule(frame: bytes) -> None:
    assert f.is_valid(frame)


def test_usb_frames_match_what_the_device_accepted() -> None:
    assert f.usb_frame(f.START_QUERY, f.CMD_INFO, 1) == USB["info_1"]["request"]
    assert f.usb_frame(f.START_COMMAND, f.CMD_MEASURE, 0x10) == USB["chunk_10"]["request"]
    assert len(f.usb_frame(f.START_COMMAND, f.CMD_MEASURE)) == f.USB_FRAME_LEN


def test_ble_frames_match_what_the_device_accepted() -> None:
    assert f.ble_frame(f.CMD_DEVICE_INFO, 1, 0, 0, 0, 0, 0) == BLE["device_info"]["request"]
    assert f.ble_frame(f.CMD_MEASURE_DATA, 16, 0, 0, 0, 0, 0) == BLE["measure_data"]["request"]


def test_device_info_is_the_same_record_on_both_transports() -> None:
    usb = f.info_from_usb_pages([USB[f"info_{p}"]["reply"] for p in f.USB_INFO_PAGES])
    assert usb == f.info_from_ble(BLE["device_info"]["reply"]) == EXPECTED_INFO


def test_the_same_scan_decodes_identically_over_usb_and_ble() -> None:
    usb = f.spd_from_usb_pages([USB[f"chunk_{s:02x}"]["reply"] for s in f.USB_SPD_PAGES])
    ble = f.spd_from_ble(BLE["measure_data"]["reply"])
    assert usb == ble
    assert len(usb) == len(f.WAVELENGTHS) == 31
    assert all(0.0 <= v <= 100.0 for v in usb)  # percent


def test_measure_ack_and_header_carry_the_wavelength_grid() -> None:
    ack = BLE["measure_ack"]["reply"]
    assert (ack[3], (ack[4] << 8) | ack[5], ack[6], ack[7]) == (0, 400, 10, 31)
    header = USB["measure_header"]["reply"]
    assert (header[4] * 10, header[5], header[6]) == (400, 31, 10)


def test_check_reply_rejects_corruption_and_wrong_command() -> None:
    reply = bytearray(USB["chunk_10"]["reply"])
    assert f.check_reply(bytes(reply), f.CMD_MEASURE, length=60)
    with pytest.raises(FrameError, match="0x0a"):
        f.check_reply(bytes(reply), f.CMD_INFO)
    with pytest.raises(FrameError, match="expected 59"):
        f.check_reply(bytes(reply), f.CMD_MEASURE, length=59)
    reply[10] ^= 0xFF
    with pytest.raises(FrameError, match="checksum"):
        f.check_reply(bytes(reply), f.CMD_MEASURE)


def test_spd_from_ble_rejects_lab_data_and_short_spectra() -> None:
    reply = bytearray(BLE["measure_data"]["reply"])
    reply[3] = 1
    with pytest.raises(FrameError, match="data type"):
        f.spd_from_ble(bytes(reply))
    with pytest.raises(FrameError, match="124 bytes"):
        f.decode_spd(b"\x00" * 10)


# ── devices against fake transports replaying the captured frames ────────────


class _FakeSerial:
    """A (reader, writer) pair that answers each 60-byte request with its captured reply."""

    def __init__(self) -> None:
        self.replies = {x["request"]: x["reply"] for x in USB.values()}
        self.inbox = asyncio.Queue[bytes]()
        self.closed = False

    # writer
    def write(self, data: bytes) -> None:
        self.inbox.put_nowait(self.replies[data])

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass

    # reader
    async def read(self, _n: int) -> bytes:
        return b""  # nothing buffered at connect

    async def readexactly(self, n: int) -> bytes:
        reply = await self.inbox.get()
        assert len(reply) == n
        return reply


class _FakeBleak:
    """A BleakClient stand-in that answers each BLE request with its captured reply, in 20-byte notifications."""

    def __init__(self) -> None:
        self.replies = {x["request"]: x["reply"] for x in BLE.values()}
        self.pending = bytearray()
        self.callback: Any = None
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def start_notify(self, _char: str, callback: Any) -> None:
        self.callback = callback

    async def write_gatt_char(self, _char: str, data: bytes, response: bool = False) -> None:
        assert response is False
        if data == b"\x01":  # wake
            self.pending.clear()
            return
        self.pending.extend(data)
        request = bytes(self.pending)
        if request[1] == f.CMD_MEASURE and len(request) == 10:  # the nonce differs per scan
            request = BLE["measure_ack"]["request"]
        if request in self.replies:
            reply = self.replies[request]
            for i in range(0, len(reply), 20):
                self.callback(None, bytearray(reply[i : i + 20]))


async def test_usb_cr30_connects_and_measures() -> None:
    fake = _FakeSerial()
    async with UsbCR30("/dev/null", streams=(fake, fake)) as cr30:
        assert cr30.info == EXPECTED_INFO
        assert (cr30.model, cr30.serial_number) == ("CR30", "CM454M1246")
        spd = await cr30.measure()
    assert list(spd.values) == f.spd_from_ble(BLE["measure_data"]["reply"])
    assert spd.wavelengths == tuple(range(400, 701, 10))
    assert fake.closed


async def test_ble_cr30_connects_and_measures(monkeypatch) -> None:
    monkeypatch.setattr("epaper_colorcal.cr30.device.BLE_SETTLE", 0)
    monkeypatch.setattr("epaper_colorcal.cr30.device.BLE_CHUNK_DELAY", 0)
    fake = _FakeBleak()
    async with BleCR30(client=fake) as cr30:
        assert cr30.info == EXPECTED_INFO
        spd = await cr30.measure()
        with pytest.raises(NotImplementedError):
            await cr30.calibrate_black()
    assert list(spd.values) == f.spd_from_usb_pages([USB[f"chunk_{s:02x}"]["reply"] for s in f.USB_SPD_PAGES])
    assert not fake.connected


async def test_ble_cr30_times_out_when_the_device_is_silent(monkeypatch) -> None:
    monkeypatch.setattr("epaper_colorcal.cr30.device.BLE_SETTLE", 0)
    monkeypatch.setattr("epaper_colorcal.cr30.device.TIMEOUT", 0.05)
    fake = _FakeBleak()
    fake.replies = {}
    with pytest.raises(TimeoutError, match="0x12"):
        await BleCR30(client=fake).connect()


async def test_ble_cr30_retries_a_dropped_first_command(monkeypatch) -> None:
    monkeypatch.setattr("epaper_colorcal.cr30.device.BLE_SETTLE", 0)
    monkeypatch.setattr("epaper_colorcal.cr30.device.TIMEOUT", 0.05)
    fake = _FakeBleak()
    real_write = fake.write_gatt_char
    dropped: list[bytes] = []

    async def drop_first_command(char: str, data: bytes, response: bool = False) -> None:
        if data != b"\x01" and not dropped:
            dropped.append(data)
            return
        await real_write(char, data, response)

    fake.write_gatt_char = drop_first_command  # type: ignore[method-assign]
    cr30 = BleCR30(client=fake)
    await cr30.connect()
    assert dropped and cr30.info == EXPECTED_INFO


async def test_usb_cr30_names_the_port_when_the_device_is_silent(monkeypatch) -> None:
    monkeypatch.setattr("epaper_colorcal.cr30.device.TIMEOUT", 0.05)

    class _Silent(_FakeSerial):
        def write(self, data: bytes) -> None:
            pass  # a CR30 that is switched off: the USB chip is there, nothing answers

    fake = _Silent()
    with pytest.raises(TimeoutError, match="on /dev/ttyUSB9"):
        await UsbCR30("/dev/ttyUSB9", streams=(fake, fake)).connect()


def test_open_cr30_picks_the_transport() -> None:
    assert isinstance(open_cr30(port="/dev/ttyUSB0"), UsbCR30)
    assert isinstance(open_cr30(ble="auto"), BleCR30)
    with pytest.raises(ValueError):
        open_cr30()
    with pytest.raises(ValueError):
        open_cr30(port="/dev/ttyUSB0", ble="auto")
