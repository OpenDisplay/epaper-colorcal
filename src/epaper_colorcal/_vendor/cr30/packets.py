"""
CR30 Packet Builder and Parser

Handles building and parsing of CR30 protocol packets.
Based on reverse engineering analysis of the CR30 colorimeter protocol.
"""

from typing import Optional, Dict, Any, Tuple, List
import struct


class CR30Packet:
    """
    Represents a CR30 protocol packet (60 bytes).
    
    Packet structure:
    - Byte 0: Start byte (0xAA or 0xBB)
    - Byte 1: Command
    - Byte 2: Subcommand
    - Byte 3: Parameter
    - Bytes 4-55: Payload (52 bytes)
    - Byte 58: Marker (0xFF for 0xAA, 0x00/0xFF for 0xBB)
    - Byte 59: Checksum
    """
    
    PACKET_SIZE = 60
    PAYLOAD_START = 4
    PAYLOAD_END = 56
    PAYLOAD_SIZE = 52
    
    def __init__(self, data: Optional[bytes] = None):
        """
        Initialize packet from bytes or create empty packet.
        
        Args:
            data: 60-byte packet data, or None to create empty packet
        """
        if data is None:
            self._data = bytearray(self.PACKET_SIZE)
            self._data[58] = 0xFF  # Default marker
        else:
            if len(data) != self.PACKET_SIZE:
                raise ValueError(f"Packet must be exactly {self.PACKET_SIZE} bytes, got {len(data)}")
            self._data = bytearray(data)
    
    @property
    def start(self) -> int:
        """Get or set the start byte (0xAA or 0xBB)."""
        return self._data[0]
    
    @start.setter
    def start(self, value: int):
        if value not in (0xAA, 0xBB):
            raise ValueError("Start byte must be 0xAA or 0xBB")
        self._data[0] = value
        # Update marker based on start byte
        if value == 0xAA:
            self._data[58] = 0xFF
        # For 0xBB, marker can be 0x00 or 0xFF, default to 0xFF
        elif self._data[58] not in (0x00, 0xFF):
            self._data[58] = 0xFF
    
    @property
    def cmd(self) -> int:
        """Get or set the command byte."""
        return self._data[1]
    
    @cmd.setter
    def cmd(self, value: int):
        self._data[1] = value & 0xFF
    
    @property
    def subcmd(self) -> int:
        """Get or set the subcommand byte."""
        return self._data[2]
    
    @subcmd.setter
    def subcmd(self, value: int):
        self._data[2] = value & 0xFF
    
    @property
    def param(self) -> int:
        """Get or set the parameter byte."""
        return self._data[3]
    
    @param.setter
    def param(self, value: int):
        self._data[3] = value & 0xFF
    
    @property
    def payload(self) -> bytes:
        """Get or set the payload bytes (52 bytes, bytes 4-55)."""
        return bytes(self._data[self.PAYLOAD_START:self.PAYLOAD_END])
    
    @payload.setter
    def payload(self, value: bytes):
        if len(value) > self.PAYLOAD_SIZE:
            raise ValueError(f"Payload must be at most {self.PAYLOAD_SIZE} bytes, got {len(value)}")
        # Clear payload area first
        self._data[self.PAYLOAD_START:self.PAYLOAD_END] = b'\x00' * self.PAYLOAD_SIZE
        # Set new payload
        self._data[self.PAYLOAD_START:self.PAYLOAD_START + len(value)] = value
    
    @property
    def marker(self) -> int:
        """Get or set the marker byte (byte 58)."""
        return self._data[58]
    
    @marker.setter
    def marker(self, value: int):
        if self.start == 0xAA and value != 0xFF:
            raise ValueError("Marker must be 0xFF for 0xAA packets")
        if self.start == 0xBB and value not in (0x00, 0xFF):
            raise ValueError("Marker must be 0x00 or 0xFF for 0xBB packets")
        self._data[58] = value
    
    @property
    def checksum(self) -> int:
        """Get the checksum byte (byte 59)."""
        return self._data[59]
    
    def calculate_checksum(self) -> int:
        """Calculate and update the checksum."""
        checksum = sum(self._data[:58]) % 256
        if self.start == 0xBB:
            checksum = (checksum - 1) % 256
        self._data[59] = checksum
        return checksum
    
    def verify_checksum(self) -> bool:
        """Verify the packet checksum."""
        calculated = self.calculate_checksum()
        return calculated == self._data[59]
    
    def is_valid(self) -> bool:
        """Check if packet has valid structure."""
        if len(self._data) != self.PACKET_SIZE:
            return False
        
        # Check start byte
        if self.start not in (0xAA, 0xBB):
            return False
        
        # Check end marker
        if self.start == 0xAA and self.marker != 0xFF:
            return False
        if self.start == 0xBB and self.marker not in (0x00, 0xFF):
            return False
        
        return True
    
    def to_bytes(self) -> bytes:
        """Convert packet to bytes."""
        # Ensure checksum is calculated
        self.calculate_checksum()
        return bytes(self._data)
    
    def to_hex(self, separator: str = ' ') -> str:
        """Convert packet to hex string."""
        return self.to_bytes().hex(separator).upper()
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'CR30Packet':
        """Create packet from bytes."""
        return cls(data)


class PacketBuilder:
    """Builds CR30 protocol packets."""
    
    def build_packet(self, start: int, cmd: int, subcmd: int = 0, 
                     param: int = 0, data: Optional[bytes] = None) -> bytes:
        """
        Build a CR30 protocol packet.
        
        Args:
            start: Start byte (0xAA or 0xBB)
            cmd: Command byte
            subcmd: Sub-command byte
            param: Parameter byte
            data: Optional data payload (max 52 bytes)
            
        Returns:
            60-byte packet with checksum
        """
        packet = CR30Packet()
        packet.start = start
        packet.cmd = cmd
        packet.subcmd = subcmd
        packet.param = param
        
        if data:
            packet.payload = data
        
        return packet.to_bytes()
    
    def build_handshake_packet(self, cmd: int, subcmd: int = 0, param: int = 0, 
                              data: Optional[bytes] = None) -> bytes:
        """Build a handshake packet (0xAA start)."""
        return self.build_packet(0xAA, cmd, subcmd, param, data)
    
    def build_command_packet(self, cmd: int, subcmd: int = 0, param: int = 0, 
                            data: Optional[bytes] = None) -> bytes:
        """Build a command packet (0xBB start)."""
        return self.build_packet(0xBB, cmd, subcmd, param, data)


class PacketParser:
    """Parses CR30 protocol packets. Can maintain state for multi-packet operations (e.g., SPD reconstruction)."""
    
    def __init__(self):
        """Initialize the packet parser."""
        self._spd_bytes = bytearray()
        self._chunks_received = set()
        self._chunk_info_list = []
    
    def reset_spd_collection(self):
        """Reset SPD chunk collection state."""
        self._spd_bytes = bytearray()
        self._chunks_received = set()
        self._chunk_info_list = []
    
    def is_valid_packet(self, packet: bytes) -> bool:
        """Check if packet has valid structure."""
        try:
            pkt = CR30Packet(packet)
            return pkt.is_valid()
        except (ValueError, IndexError):
            return False
    
    def extract_payload(self, packet: bytes) -> bytes:
        """
        Extract payload bytes from packet (bytes 4-55).
        
        Args:
            packet: 60-byte packet
            
        Returns:
            Payload bytes
            
        Raises:
            ValueError: If packet is invalid
        """
        pkt = self.parse_packet(packet)
        return pkt.payload
    
    def parse_header(self, packet: bytes) -> CR30Packet:
        """
        Parse packet header information.
        
        Args:
            packet: 60-byte packet
            
        Returns:
            CR30Packet object
            
        Raises:
            ValueError: If packet is invalid
        """
        return self.parse_packet(packet)
    
    def parse_device_info(self, packet: bytes) -> Dict[str, str]:
        """
        Parse device information from handshake packets.
        
        Args:
            packet: 60-byte packet from handshake
            
        Returns:
            Dictionary with device information (includes packet fields and parsed strings)
            
        Raises:
            ValueError: If packet is invalid
        """
        pkt = self.parse_packet(packet)
        payload = pkt.payload
        
        result = {
            "cmd": pkt.cmd,
            "subcmd": pkt.subcmd,
            "param": pkt.param
        }
        
        # Parse different types of device info based on command
        if pkt.cmd == 0x0A:  # Device info commands
            if pkt.subcmd == 0x00:  # Device name
                name = payload[5:30].decode('ascii', errors='ignore').strip('\x00')
                model = payload[35:45].decode('ascii', errors='ignore').strip('\x00')
                result.update({"name": name, "model": model})
            
            elif pkt.subcmd == 0x01:  # Serial number
                serial = payload[5:25].decode('ascii', errors='ignore').strip('\x00')
                result["serial"] = serial
            
            elif pkt.subcmd == 0x02:  # Firmware version
                firmware = payload[5:25].decode('ascii', errors='ignore').strip('\x00')
                result["firmware"] = firmware
            
            elif pkt.subcmd == 0x03:  # Build info
                build = payload[5:25].decode('ascii', errors='ignore').strip('\x00')
                result["build"] = build
        
        return result
    
    def parse_measurement_header(self, packet: bytes) -> CR30Packet:
        """
        Parse measurement header packet (subcmd 0x09).
        
        Args:
            packet: 60-byte measurement header packet
            
        Returns:
            CR30Packet object
            
        Raises:
            ValueError: If packet is invalid or not a measurement header
        """
        pkt = self.parse_packet(packet)
        if pkt.subcmd != 0x09:
            raise ValueError(f"Not a measurement header packet: subcmd=0x{pkt.subcmd:02X}, expected 0x09")
        return pkt
    
    def parse_spd_chunk(self, packet: bytes) -> Dict[str, Any]:
        """
        Parse SPD (Spectral Power Distribution) chunk packet and accumulate data.
        Handles chunks 0x10, 0x11, 0x12, 0x13 internally.
        
        Args:
            packet: 60-byte SPD chunk packet
            
        Returns:
            Dictionary with chunk information including:
            - subcmd: Subcommand byte
            - payload: Payload hex string
            - spd_bytes_count: Number of SPD bytes extracted
            - spd_raw: SPD data hex string
            - spd: Parsed SPD float values
            
        Raises:
            ValueError: If packet is invalid
        """
        pkt = self.parse_packet(packet)
        payload = pkt.payload
        subcmd = pkt.subcmd
        
        # Check if this chunk was already processed
        if subcmd in self._chunks_received:
            raise ValueError(f"Chunk 0x{subcmd:02X} already received")
        
        chunk_info = {
            "subcmd": subcmd,
            "payload": payload.hex(),
        }
        
        # Parse based on chunk type
        if subcmd == 0x10:
            # Chunk 0x10: Contains first SPD bytes (starts at offset 2)
            spd_data = payload[2:50]
            self._spd_bytes.extend(spd_data)
            floats = list(struct.unpack(f"<{len(spd_data)//4}f", spd_data))
            
            chunk_info.update({
                "spd_bytes_start": 2,
                "spd_bytes_count": len(spd_data),
                "spd_raw": spd_data.hex(),
                "spd": floats,
            })
            
        elif subcmd in (0x11, 0x12):
            # Chunk 0x11, 0x12: Pure SPD data (starts at offset 2)
            spd_data = payload[2:50]
            self._spd_bytes.extend(spd_data)
            floats = list(struct.unpack(f"<{len(spd_data)//4}f", spd_data))
            
            chunk_info.update({
                "spd_bytes_count": len(spd_data),
                "spd_raw": spd_data.hex(),
                "spd": floats,
            })
            
        elif subcmd == 0x13:
            # Chunk 0x13: Final chunk (may have some SPD data at different offset)
            # Based on the code, it seems this might be the last chunk
            chunk_info.update({
                "spd_bytes_count": 0,
            })
        else:
            raise ValueError(f"Unknown SPD chunk subcmd: 0x{subcmd:02X}")
        
        # Mark chunk as received
        self._chunks_received.add(subcmd)
        self._chunk_info_list.append(chunk_info)
        
        return chunk_info
    
    def get_accumulated_spd(self) -> bytes:
        """
        Get accumulated SPD bytes from all chunks.
        
        Returns:
            Accumulated SPD bytes as bytes object
        """
        return bytes(self._spd_bytes)
    
    def get_chunks_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all received chunks.
        
        Returns:
            List of chunk info dictionaries
        """
        return self._chunk_info_list.copy()
    
    def is_spd_complete(self) -> bool:
        """
        Check if all expected SPD chunks have been received.
        
        Returns:
            True if all chunks (0x10, 0x11, 0x12, 0x13) have been received
        """
        expected_chunks = {0x10, 0x11, 0x12, 0x13}
        return expected_chunks.issubset(self._chunks_received)
    
    def verify_checksum(self, packet: bytes) -> bool:
        """
        Verify packet checksum.
        
        Args:
            packet: 60-byte packet
            
        Returns:
            True if checksum is valid
            
        Raises:
            ValueError: If packet is invalid
        """
        pkt = self.parse_packet(packet)
        return pkt.verify_checksum()
    
    def parse_packet(self, packet: bytes) -> CR30Packet:
        """
        Parse bytes into a CR30Packet object.
        
        Args:
            packet: 60-byte packet data
            
        Returns:
            CR30Packet object
            
        Raises:
            ValueError: If packet is invalid or malformed
        """
        try:
            pkt = CR30Packet(packet)
            if not pkt.is_valid():
                raise ValueError(f"Invalid packet structure: start=0x{pkt.start:02X}, marker=0x{pkt.marker:02X}")
            return pkt
        except ValueError as e:
            raise ValueError(f"Failed to parse packet: {e}") from e
        except (IndexError, TypeError) as e:
            raise ValueError(f"Invalid packet format: {e}") from e

