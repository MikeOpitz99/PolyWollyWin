"""
flare2_matrix_test.py - ROG Strix Flare II Animate matrix diagnostic
Protocol confirmed from a reference USBPcap capture.

CONFIRMED WIRE FORMAT:
  Endpoint: 7 OUT (usage_page=0xFF02, MI_04)
  Packet size: 1024 bytes
  
  Byte 0:   0x60  — command byte (constant)
  Byte 1:   0x81  — sub-command (frame data)
  Byte 2:   0x00  — always 0
  Byte 3:   0x00  — always 0 for frame data
              (0xa8 = brightness/mode command)
  Bytes 4-315: 312 bytes of LED brightness (0x00-0xFF)
               Physical LED order: row-major, mask applied
               Row 0: cols 0-36  (37 LEDs)
               Row 1: cols 2-36  (35 LEDs)
               Row 2: cols 4-36  (33 LEDs)
               ... etc (each row starts 2 cols right)
  Bytes 316-1023: zero padding
"""

import sys
import time
import hid

VID        = 0x0B05
PID        = 0x19FC
USAGE_PAGE = 0xFF02

ROWS = 12
COLS = 37

# Physical LED mask — row r starts at col r*2
MASK = []
for r in range(ROWS):
    row = [0] * COLS
    for c in range(r * 2, COLS):
        row[c] = 1
    MASK.append(row)

PHYSICAL_LED_COUNT = sum(sum(r) for r in MASK)  # 312


# ──────────────────────────────────────────────
# Transport
# ──────────────────────────────────────────────

def connect():
    devs = hid.enumerate(VID, PID)
    target = next((d for d in devs if d.get("usage_page", 0) == USAGE_PAGE), None)
    if not target:
        raise RuntimeError("Keyboard matrix interface not found (usage_page=0xFF02)")
    dev = hid.device()
    dev.open_path(target["path"])
    return dev


def send_frame(dev, led_bytes: bytes | list[int]):
    """
    Send one frame to the matrix.
    led_bytes: exactly 312 bytes, physical LED order.
    """
    assert len(led_bytes) == PHYSICAL_LED_COUNT, \
        f"Expected {PHYSICAL_LED_COUNT} bytes, got {len(led_bytes)}"

    pkt = [0x00] * 1025          # hidapi report-ID prefix + 1024 payload
    pkt[1] = 0x60                # command
    pkt[2] = 0x81                # sub-command: frame data
    pkt[3] = 0x00
    pkt[4] = 0x00
    for i, v in enumerate(led_bytes):
        pkt[5 + i] = int(v)      # bytes 4..315 in payload = pkt[5..316]

    return dev.write(pkt)


# ──────────────────────────────────────────────
# Frame builders
# ──────────────────────────────────────────────

def frame_blank() -> list[int]:
    return [0] * PHYSICAL_LED_COUNT


def frame_all(brightness: int = 0xFF) -> list[int]:
    return [brightness] * PHYSICAL_LED_COUNT


def logical_to_physical(logical: list[list[int]]) -> list[int]:
    """
    Convert a 12×37 logical grid to 312 physical LED bytes.
    Cells where MASK[r][c]==0 are skipped.
    """
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            if MASK[r][c]:
                out.append(int(logical[r][c]))
    return out


# ──────────────────────────────────────────────
# GIF playback
# ──────────────────────────────────────────────

def play_gif(dev, gif_path: str, loops: int = 0,
             offset_x: float = -49.0, offset_y: float = -18.0,
             scale: float = 4.1, brightness: float = 10.0):
    """
    Play a GIF on the matrix using Armoury Crate render parameters.
    loops=0 means loop forever (Ctrl-C to stop).
    """
    from PIL import Image, ImageSequence
    import numpy as np

    img = Image.open(gif_path)
    frames = []
    durations = []

    for frame in ImageSequence.Iterator(img):
        grey = np.array(frame.convert("L"), dtype=np.float32)

        led = np.zeros((ROWS, COLS), dtype=np.float32)
        for r in range(ROWS):
            for c in range(COLS):
                sx = c * scale + offset_x
                sy = r * scale + offset_y
                x0 = max(0, min(grey.shape[1] - 1, int(sx)))
                y0 = max(0, min(grey.shape[0] - 1, int(sy)))
                x1 = max(0, min(grey.shape[1] - 1, x0 + 1))
                y1 = max(0, min(grey.shape[0] - 1, y0 + 1))
                fx, fy = sx - int(sx), sy - int(sy)
                v = (grey[y0,x0]*(1-fx)*(1-fy) + grey[y0,x1]*fx*(1-fy) +
                     grey[y1,x0]*(1-fx)*fy     + grey[y1,x1]*fx*fy)
                led[r, c] = v

        led = np.clip(led * (brightness / 10.0), 0, 255).astype(np.uint8)
        frames.append(logical_to_physical(led.tolist()))

        dur = frame.info.get("duration", 40)
        durations.append(dur / 1000.0)

    print(f"Loaded {len(frames)} frames from {gif_path}")

    loop = 0
    try:
        while loops == 0 or loop < loops:
            for phys, dur in zip(frames, durations):
                t0 = time.perf_counter()
                send_frame(dev, phys)
                elapsed = time.perf_counter() - t0
                sleep = dur - elapsed
                if sleep > 0:
                    time.sleep(sleep)
            loop += 1
    except KeyboardInterrupt:
        pass

    send_frame(dev, frame_blank())
    print("Stopped.")


# ──────────────────────────────────────────────
# Quick test
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("Connecting...")
    dev = connect()
    print("Connected.")

    if len(sys.argv) > 1:
        # Play a GIF passed as argument
        play_gif(dev, sys.argv[1])
    else:
        # Diagnostic: ramp all LEDs 0→255→0
        print("Running brightness ramp (Ctrl-C to stop)...")
        try:
            while True:
                for v in list(range(0, 256, 4)) + list(range(255, -1, -4)):
                    send_frame(dev, frame_all(v))
                    time.sleep(0.01)
        except KeyboardInterrupt:
            send_frame(dev, frame_blank())
            print("Done.")

    dev.close()
