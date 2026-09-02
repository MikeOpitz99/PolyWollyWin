"""
transport.py — ROG Strix Flare II Animate HID transport
Protocol confirmed from live USBPcap capture (USBPcap.pcap).

Wire format (1024-byte payload, hidapi prepends 0x00 report-ID):
  [0x60, 0x81, 0x00, 0x00, <312 LED bytes>, <zero padding to 1024>]
"""

import hid

VID        = 0x0B05
PID        = 0x19FC
USAGE_PAGE = 0xFF02

PAYLOAD_SIZE       = 1024
PHYSICAL_LED_COUNT = 312
CMD_FRAME          = [0x60, 0x81, 0x00, 0x00]
CMD_BRIGHTNESS     = [0x60, 0xa8, 0x81]   # + [level_byte, 0xff]


class Transport:

    def __init__(self):
        self._dev  = None
        self._path = None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    def connect(self) -> str:
        # Never reuse a handle that may have survived a USB power-cycle in
        # Python but is no longer valid in Windows/hidapi.
        self.disconnect()

        devs   = hid.enumerate(VID, PID)
        target = next(
            (d for d in devs if d.get("usage_page", 0) == USAGE_PAGE),
            None,
        )
        if not target:
            raise RuntimeError(
                "ROG Strix Flare II Animate matrix interface not found.\n"
                "Is the keyboard plugged in? (VID=0x0B05 PID=0x19FC usage_page=0xFF02)"
            )
        path = target["path"]
        dev = hid.device()
        try:
            dev.open_path(path)
        except Exception:
            try:
                dev.close()
            except Exception:
                pass
            raise

        # Publish the new connection only after open_path succeeds.
        self._path = path
        self._dev = dev
        return self._path.decode(errors="replace") if isinstance(self._path, bytes) else str(self._path)

    def disconnect(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
        self._dev  = None
        self._path = None

    @property
    def connected(self) -> bool:
        return self._dev is not None

    # ------------------------------------------------------------------ #
    # Low-level write
    # ------------------------------------------------------------------ #

    def _write(self, payload: list[int]) -> int:
        if not self._dev:
            raise RuntimeError("Not connected")
        buf = payload[:PAYLOAD_SIZE]
        buf += [0x00] * (PAYLOAD_SIZE - len(buf))
        try:
            written = self._dev.write([0x00] + buf)  # hidapi report-ID prefix
        except Exception as exc:
            # A HID object can remain non-None after sleep, a USB controller
            # reset, or unplug/replug even though its OS handle is dead.
            self.disconnect()
            raise RuntimeError("HID write failed; connection was invalidated") from exc

        if written <= 0:
            self.disconnect()
            raise RuntimeError("HID write returned no data; connection was invalidated")
        return written

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def send_frame(self, led_bytes: bytes | list[int]) -> int:
        """
        Push one frame to the matrix.
        led_bytes must be exactly 312 values (0-255), physical LED order.
        """
        data = list(led_bytes)
        assert len(data) == PHYSICAL_LED_COUNT, \
            f"Expected {PHYSICAL_LED_COUNT} LED bytes, got {len(data)}"
        return self._write(CMD_FRAME + data)

    def send_blank(self) -> int:
        return self.send_frame([0] * PHYSICAL_LED_COUNT)

    def send_brightness(self, level: int):
        """level 0-3 (matches Armoury Crate scale)."""
        level = max(0, min(3, level))
        self._write(CMD_BRIGHTNESS + [level, 0xFF])

    def enumerate_interfaces(self) -> list[str]:
        """Debug helper — print all interfaces for this VID/PID."""
        lines = []
        for d in hid.enumerate(VID, PID):
            iface = d.get("interface_number", -1)
            usage = d.get("usage_page", 0)
            lines.append(f"  iface={iface}  usage_page=0x{usage:04X}  path={d['path']}")
        return lines
