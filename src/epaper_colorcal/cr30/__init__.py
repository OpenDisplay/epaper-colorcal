"""CHNSpec CR30 spectrocolorimeter over USB serial or Bluetooth LE.

Our own implementation, verified against a real device. Protocol credit: the USB
serial protocol was reverse-engineered by itohio
(https://itohi.com/colorimetry/reverse-engineering-cr30/); the BLE framing was read
out of CHNSpec's official app. See ``docs/cr30-protocol.md``.
"""

from .device import CR30, BleCR30, UsbCR30, find_ble_cr30, open_cr30
from .frames import WAVELENGTHS, DeviceInfo, FrameError

__all__ = [
    "CR30",
    "WAVELENGTHS",
    "BleCR30",
    "DeviceInfo",
    "FrameError",
    "UsbCR30",
    "find_ble_cr30",
    "open_cr30",
]
