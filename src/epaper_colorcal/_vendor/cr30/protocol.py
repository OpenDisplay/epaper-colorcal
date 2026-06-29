"""
CR30 Protocol Implementation

Handles CR30 commands, handshake, and measurement sequencing.
"""

import asyncio
import struct
from typing import List, Dict, Callable, Optional, Tuple
from .device import CR30Device


class CR30Protocol(CR30Device):
    """Handles CR30 commands, handshake, and measurement sequencing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._response_callbacks: List[Callable[[Dict], None]] = []
        self._raw_measurement_callbacks: List[Callable[[Dict], None]] = []
        self.wavelengths = list(range(400, 701, 10))  # 31 bands

    def register_response_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for measurement responses."""
        self._response_callbacks.append(callback)

    def register_raw_measurement_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for raw measurement data."""
        self._raw_measurement_callbacks.append(callback)
        
    async def calibrate(self, white: bool = False, timeout: float = 5.0) -> Dict:
        """
        Perform black/white calibration.
        Place device on appropriate calibration tile and call this method.
        """
        if self._verbose:
            print(f"Starting {'white' if white else 'black'} calibration...")
        response = await self.send_recv(0xBB, 0x11 if white else 0x10, 0x00, 0x00, timeout=timeout)
        
        if not response:
            raise asyncio.TimeoutError("No response from calibration command")
        
        try:
            payload = self._packet_parser.extract_payload(response)
            status = payload[1] if len(payload) > 1 else 0
        except ValueError as e:
            raise ValueError(f"Invalid calibration response packet: {e}") from e
        
        result = {
            "success": status == 0x01,
            "status_byte": status,
            "raw_response": response.hex()
        }
        
        if result["success"]:
            if self._verbose:
                print(f"{'White' if white else 'Black'} calibration successful!")
        else:
            if self._verbose:
                print(f"{'White' if white else 'Black'} calibration failed (status: 0x{status:02X})")
        
        return result

    async def wait_measurement(self, timeout: float = 15, timeout_per_step: float = 1.5) -> Dict:
        """Wait for a button press and initiate the reading process."""
        response = await self.recv(timeout)
        if not response:
            raise asyncio.TimeoutError("No button press detected")
        return await self._read_measurement(response, timeout_per_step=timeout_per_step)

    async def measure(self, timeout_per_step: float = 1.5) -> Dict:
        """Trigger PC-initiated measurement and read data."""
        header_packet = await self.send_recv(0xBB, 0x01, 0x00, 0x00, timeout=timeout_per_step)
        if not header_packet:
            raise asyncio.TimeoutError("No header response after trigger (BB 01 00).")
        return await self._read_measurement(header_packet, timeout_per_step)

    async def _read_measurement(self, initial_response: bytes, timeout_per_step: float = 1.5) -> Dict:
        """Main measurement reading orchestrator."""
        await self.flush_recv()

        result = {
            "header": None,
            "chunks": [],
            "spd": [],
            "raw": {}
        }

        # Parse header
        try:
            header_pkt = self._packet_parser.parse_packet(initial_response)
            result["header"] = {
                "cmd": header_pkt.cmd,
                "subcmd": header_pkt.subcmd,
                "param": header_pkt.param,
                "payload": header_pkt.payload.hex(),
            }
            result["raw"]["header"] = initial_response.hex()
        except ValueError as e:
            raise ValueError(f"Invalid measurement header packet: {e}") from e

        # Read and parse all data chunks
        spd_bytes = await self._read_all_chunks(result, timeout_per_step)

        result["spd_bytes"] = spd_bytes.hex()

        # Convert accumulated SPD bytes to float values
        self._parse_spd_data(result, spd_bytes)

        # Fire callbacks
        self._trigger_callbacks(result)

        return result

    async def _read_all_chunks(self, result: Dict, timeout: float) -> bytearray:
        """Read all measurement data chunks (0x10, 0x11, 0x12, 0x13)."""
        # Reset parser state for new measurement
        self._packet_parser.reset_spd_collection()
        
        chunk_subcmds = [0x10, 0x11, 0x12, 0x13]

        for subcmd in chunk_subcmds:
            packet = await self.send_recv(0xBB, 0x01, subcmd, 0x00, timeout=timeout)
            if not packet:
                if self._verbose:
                    print(f"Warning: No response for chunk 0x{subcmd:02X}")
                break

            try:
                chunk_info = self._packet_parser.parse_spd_chunk(packet)
                result["raw"][f"0x{subcmd:02X}"] = chunk_info["payload"]
                result["chunks"].append(chunk_info)
            except ValueError as e:
                if self._verbose:
                    print(f"Warning: Failed to parse chunk 0x{subcmd:02X}: {e}")
                chunk_info = {"subcmd": subcmd, "error": str(e)}
                result["chunks"].append(chunk_info)

        # Get accumulated SPD bytes
        return bytearray(self._packet_parser.get_accumulated_spd())


    def _parse_spd_data(self, result: Dict, spd_bytes: bytearray):
        """Convert accumulated SPD bytes to float values."""
        if len(spd_bytes) < 124:
            if self._verbose:
                print(f"Warning: Insufficient SPD data ({len(spd_bytes)} bytes, need 124)")
            return
        
        try:
            spd = list(struct.unpack("<31f", bytes(spd_bytes[:124])))
            result["spd"] = spd
            
            # Create wavelength->reflectance mapping
            result["spd_data"] = dict(zip(self.wavelengths, spd))
            
        except Exception as e:
            if self._verbose:
                print(f"Error parsing SPD data: {e}")


    def _trigger_callbacks(self, result: Dict):
        """Fire all registered callbacks with measurement result."""
        for cb in self._raw_measurement_callbacks:
            try: 
                cb(result)
            except Exception as e:
                if self._verbose:
                    print(f"Raw callback error: {e}")
                
        for cb in self._response_callbacks:
            try: 
                cb(result)
            except Exception as e:
                if self._verbose:
                    print(f"Response callback error: {e}")

