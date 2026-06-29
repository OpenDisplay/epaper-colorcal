"""
CR30 Device Communication

Handles raw byte-level communication with CR30 colorimeter using asyncio.
"""

import asyncio
import serial_asyncio
from typing import List, Callable, Optional, Dict, Any
import struct
from enum import Enum
from .packets import PacketBuilder, PacketParser


class CR30Device:
    """Handles raw byte-level communication with CR30 asynchronously using asyncio.Queue."""

    def __init__(self, port='COM3', baudrate=19200, verbose=True):
        self.port = port
        self.baudrate = baudrate
        self.reader = None
        self.writer = None

        self._raw_callbacks: List[Callable[[bytes], None]] = []

        # Async FIFO for frames
        self._frames: asyncio.Queue[bytes] = asyncio.Queue()
        self._receive_task: Optional[asyncio.Task] = None
        self._running = False
        self._device_name = None
        self._device_model = None
        self._device_serial = None
        self._device_firmware = None
        self._device_build = None
        self._verbose = verbose
        
        # Packet building and parsing instances
        self._packet_builder = PacketBuilder()
        self._packet_parser = PacketParser()

    @property
    def name(self) -> str:
        return self._device_name or "Unknown"
    
    @property
    def model(self) -> str:
        return self._device_model or "Unknown"
    
    @property
    def serial_number(self) -> str:
        return self._device_serial or "Unknown"
    
    @property
    def fw_version(self) -> str:
        return self._device_firmware or "Unknown"
    
    @property
    def fw_build(self) -> str:
        return self._device_build or "Unknown"

    @property
    def verbose(self) -> bool:
        return self._verbose
    
    @verbose.setter
    def verbose(self, v: bool):
        self._verbose = v

    async def connect(self):
        """Connect to the CR30 device and start the receive loop."""
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=self.baudrate
        )
        if self._verbose:
            print(f"Connected to {self.port} at {self.baudrate} baud")
        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())
        await asyncio.sleep(1)
        await self.handshake()

    async def disconnect(self):
        """Disconnect from the device and clean up resources."""
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        if self._verbose:
            print("Disconnected")

    async def handshake(self):
        """Perform full CR30 handshake and populate device info."""
        # Device information queries
        aa_commands = [
            (0x00, self._parse_name),
            (0x01, self._parse_serial_number),
            (0x02, self._parse_firmware),
            (0x03, None)  # status / build info, optional
        ]
        
        await self.flush_recv()
        for subcmd, parse in aa_commands:
            response = await self.send_recv(0xAA, 0x0A, subcmd, 0x00, timeout=1.0)
            if not response or len(response) < 60:
                if self._verbose:
                    print(f"AA 0A {subcmd:02X} failed or incomplete response")
                continue
            
            payload = self._extract_payload_bytes(response)
            
            if parse:
                parse(payload)
                info_str = payload.decode('ascii', errors='ignore').strip('\x00')
                if self._verbose:
                    print(f"{parse.__name__.replace('_',' ').title()}: {info_str}")
        
        # Initialize device
        response = await self.send_recv(0xBB, 0x17, 0x00, 0x00, timeout=1.0)
        
        # Simple 'Check' command
        response = await self.send_recv(0xBB, 0x13, 0x00, 0x00, data=b'Check' + b'\x00'*7, timeout=1.0)
        
        # Query parameters
        for idx in [0x00, 0x01, 0x02, 0x03, 0xFF]:
            response = await self.send_recv(0xBB, 0x28, 0x00, idx, timeout=1.0)
        
        if self._verbose:
            print("Handshake complete!")

    def _parse_name(self, data):
        """Parse device name from AA 0A 00 response."""
        self._device_name = data[5:30].decode('ascii', errors='ignore').strip('\x00')
        self._device_model = data[35:45].decode('ascii', errors='ignore').strip('\x00')

    def _parse_serial_number(self, data):
        """Parse serial number from AA 0A 01 response."""
        self._device_serial = data[16:30].decode('ascii', errors='ignore').strip('\x00')
        self._device_serial += " - " + data[-7:].decode('ascii', errors='ignore').strip('\x00')

    def _parse_firmware(self, data):
        """Parse firmware version from AA 0A 02 response."""
        self._device_build = data[1:20].decode('ascii', errors='ignore').strip('\x00')
        self._device_firmware = data[20:30].decode('ascii', errors='ignore').strip('\x00')

    async def flush_recv(self):
        """Empty all items from the async queue."""
        try:
            while True:
                self._frames.get_nowait()
        except asyncio.QueueEmpty:
            pass

    async def _receive_loop(self):
        """Continuously read 60-byte chunks and put valid frames in the async queue."""
        try:
            while self._running:
                data = await self.reader.readexactly(60)
                if self._packet_parser.is_valid_packet(data):
                    if self._verbose:
                        print(f"+R: {data.hex(' ').upper()}...")
                    await self._frames.put(data)
                    for cb in self._raw_callbacks:
                        cb(data)
                else:
                    if self._verbose:
                        print(f"-R: {data.hex(' ').upper()}...")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Receive loop error: {e}")

    async def recv(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Get a frame from the async FIFO queue. Waits up to timeout seconds."""
        try:
            return await asyncio.wait_for(self._frames.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def _extract_payload_bytes(self, packet: bytes) -> bytes:
        """Return the payload bytes area (bytes 4..55 inclusive) — 52 bytes"""
        return self._packet_parser.extract_payload(packet)

    def build_packet(self, start: int, cmd: int, subcmd: int = 0,
                     param: int = 0, data: bytes = None) -> bytes:
        """Build a complete packet with checksum."""
        return self._packet_builder.build_packet(start, cmd, subcmd, param, data)

    async def send_raw(self, packet: bytes):
        """Send a raw packet to the device."""
        if self._verbose:
            print(f"Send: {packet.hex(' ').upper()}...")
        self.writer.write(packet)
        await self.writer.drain()

    async def send(self, start: int, cmd: int, subcmd: int = 0,
                   param: int = 0, data: bytes = None):
        """Send a command to the device."""
        packet = self.build_packet(start, cmd, subcmd, param, data)
        await self.send_raw(packet)

    async def send_recv(self, start: int, cmd: int, subcmd: int = 0,
                        param: int = 0, data: bytes = None, timeout: float = 1.0) -> Optional[bytes]:
        """Send a command and wait for response."""
        await self.send(start, cmd, subcmd, param, data)
        return await self.recv(timeout=timeout)

    def register_raw_callback(self, callback: Callable[[bytes], None]):
        """Register a callback for raw packet reception."""
        self._raw_callbacks.append(callback)

