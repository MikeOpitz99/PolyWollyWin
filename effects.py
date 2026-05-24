"""
effects.py — Built-in generative effects for the 37×12 matrix.

Each effect is a class with:
  .tick(dt: float) -> list[int]   — returns 312 physical LED bytes
  .reset()                        — restart the effect
  .name: str

AudioVisualizer requires sounddevice — it will silently degrade
if the library or audio device is unavailable.
"""

from __future__ import annotations

import math
import random
import time
import numpy as np
from renderer import (
    ROWS, COLS, PHYSICAL_LED_COUNT,
    MASK_NP, PHYSICAL_INDICES,
    blank_frame, logical_to_physical, apply_mask,
)


# ------------------------------------------------------------------ #
# Base
# ------------------------------------------------------------------ #

class BaseEffect:
    name = "base"

    def tick(self, dt: float) -> list[int]:
        raise NotImplementedError

    def reset(self):
        pass

    def _emit(self, frame: np.ndarray) -> list[int]:
        return logical_to_physical(apply_mask(frame))


# ------------------------------------------------------------------ #
# Pulse — whole display breathes in and out
# ------------------------------------------------------------------ #

class PulseEffect(BaseEffect):
    name = "Pulse"

    def __init__(self, speed: float = 1.0, peak: int = 255):
        self.speed = speed
        self.peak  = peak
        self._t    = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        v = int((math.sin(self._t * math.pi) ** 2) * self.peak)
        frame = np.full((ROWS, COLS), v, dtype=np.uint8)
        return self._emit(frame)

    def reset(self):
        self._t = 0.0


# ------------------------------------------------------------------ #
# Rain — random bright drops fall down columns
# ------------------------------------------------------------------ #

class RainEffect(BaseEffect):
    name = "Rain"

    def __init__(self, density: float = 0.2, speed: float = 8.0, trail: float = 0.7):
        self.density = density
        self.speed   = speed
        self.trail   = trail
        self._buf    = np.zeros((ROWS, COLS), dtype=np.float32)
        self._heads  = {}   # col → float row position

    def reset(self):
        self._buf[:] = 0
        self._heads.clear()

    def tick(self, dt: float) -> list[int]:
        # Spawn new drops
        for c in range(COLS):
            if c not in self._heads and random.random() < self.density * dt:
                self._heads[c] = 0.0

        # Move drops
        done = []
        for c, pos in self._heads.items():
            r = int(pos)
            if 0 <= r < ROWS and MASK_NP[r, c]:
                self._buf[r, c] = 255.0
            pos += self.speed * dt
            if pos >= ROWS:
                done.append(c)
            else:
                self._heads[c] = pos
        for c in done:
            del self._heads[c]

        # Fade trail
        self._buf *= self.trail ** dt if self.trail < 1.0 else (1.0 - (1.0 - self.trail) * dt * 10)
        self._buf = np.clip(self._buf, 0, 255)

        frame = self._buf.astype(np.uint8)
        return self._emit(frame)


# ------------------------------------------------------------------ #
# Wipe — horizontal bar sweeps back and forth
# ------------------------------------------------------------------ #

class WipeEffect(BaseEffect):
    name = "Wipe"

    def __init__(self, speed: float = 10.0, width: int = 3):
        self.speed = speed
        self.width = width
        self._pos  = 0.0
        self._dir  = 1

    def reset(self):
        self._pos = 0.0
        self._dir = 1

    def tick(self, dt: float) -> list[int]:
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        pos = int(self._pos)
        for offset in range(-(self.width // 2), self.width // 2 + 1):
            c = pos + offset
            if 0 <= c < COLS:
                dist = abs(offset) / max(1, self.width // 2)
                brightness = int(255 * (1 - dist))
                frame[:, c] = brightness

        self._pos += self.speed * self._dir * dt
        if self._pos >= COLS - 1:
            self._dir = -1
        elif self._pos <= 0:
            self._dir = 1

        return self._emit(frame)


# ------------------------------------------------------------------ #
# Plasma — smooth animated sine-wave interference pattern
# ------------------------------------------------------------------ #

class PlasmaEffect(BaseEffect):
    name = "Plasma"

    def __init__(self, speed: float = 1.0):
        self.speed = speed
        self._t    = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        t = self._t
        for r in range(ROWS):
            for c in range(COLS):
                v = (
                    math.sin(c / 4.0 + t)
                    + math.sin(r / 2.0 + t * 1.3)
                    + math.sin((c + r) / 5.0 + t * 0.7)
                    + math.sin(math.sqrt(c * c + r * r) / 4.0 + t * 0.9)
                )
                frame[r, c] = (v + 4) / 8 * 255

        frame = np.clip(frame, 0, 255).astype(np.uint8)
        return self._emit(frame)


# ------------------------------------------------------------------ #
# Noise — random pixel sparkle
# ------------------------------------------------------------------ #

class NoiseEffect(BaseEffect):
    name = "Noise"

    def __init__(self, density: float = 0.3, smoothing: float = 0.6):
        self.density   = density
        self.smoothing = smoothing
        self._buf      = np.zeros((ROWS, COLS), dtype=np.float32)

    def reset(self):
        self._buf[:] = 0

    def tick(self, dt: float) -> list[int]:
        target = np.zeros((ROWS, COLS), dtype=np.float32)
        mask   = np.random.random((ROWS, COLS)) < self.density
        target[mask] = np.random.uniform(128, 255, mask.sum())
        s = self.smoothing ** (dt * 30)
        self._buf = self._buf * s + target * (1 - s)
        frame = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(frame)


# ------------------------------------------------------------------ #
# Scan — row-by-row diagnostic sweep
# ------------------------------------------------------------------ #

class ScanEffect(BaseEffect):
    name = "Scan"

    def __init__(self, speed: float = 4.0):
        self.speed = speed
        self._pos  = 0.0

    def reset(self):
        self._pos = 0.0

    def tick(self, dt: float) -> list[int]:
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        r = int(self._pos) % ROWS
        frame[r, :] = 255
        self._pos = (self._pos + self.speed * dt) % ROWS
        return self._emit(frame)


# ------------------------------------------------------------------ #
# Audio Visualizer — FFT bar graph across columns
# ------------------------------------------------------------------ #

class AudioVisualizer(BaseEffect):
    name = "Audio"

    def __init__(self, sample_rate: int = 22050, chunk: int = 1024):
        self._sr       = sample_rate
        self._chunk    = chunk
        self._bars     = np.zeros(COLS, dtype=np.float32)
        self._peak     = np.zeros(COLS, dtype=np.float32)
        self._stream   = None
        self._buf      = np.zeros(chunk, dtype=np.float32)
        self._available = False
        self._start()

    def _start(self):
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self._sr,
                channels=1,
                blocksize=self._chunk,
                callback=self._callback,
                dtype="float32",
            )
            self._stream.start()
            self._available = True
        except Exception as e:
            print(f"AudioVisualizer: audio unavailable ({e})")
            self._available = False

    def _callback(self, indata, frames, time_info, status):
        self._buf = indata[:, 0].copy()

    def reset(self):
        self._bars[:] = 0
        self._peak[:] = 0

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def tick(self, dt: float) -> list[int]:
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        if self._available:
            fft     = np.abs(np.fft.rfft(self._buf * np.hanning(len(self._buf))))
            freqs   = len(fft)
            bars    = np.zeros(COLS, dtype=np.float32)

            for i in range(COLS):
                lo = int(freqs * i / COLS)
                hi = int(freqs * (i + 1) / COLS)
                hi = max(lo + 1, hi)
                bars[i] = np.mean(fft[lo:hi])

            # Normalize
            mx = bars.max()
            if mx > 0:
                bars = bars / mx

            # Smooth
            self._bars = self._bars * 0.6 + bars * 0.4

            # Peak hold
            self._peak = np.maximum(self._peak * (1 - dt * 1.5), self._bars)

            for c in range(COLS):
                height = int(self._bars[c] * ROWS)
                peak_r = int(self._peak[c] * (ROWS - 1))
                for r in range(ROWS):
                    display_r = ROWS - 1 - r
                    if MASK_NP[display_r, c]:
                        if r < height:
                            frame[display_r, c] = max(40, int(255 * r / max(1, height)))
                        elif r == peak_r:
                            frame[display_r, c] = 255
        else:
            # Fallback: plasma if no audio
            self._t = getattr(self, "_t", 0.0) + dt
            for r in range(ROWS):
                for c in range(COLS):
                    v = math.sin(c / 4.0 + self._t) * math.cos(r / 2.0 + self._t * 0.7)
                    frame[r, c] = int((v + 1) / 2 * 255)

        return self._emit(frame)


# ------------------------------------------------------------------ #
# Registry
# ------------------------------------------------------------------ #

ALL_EFFECTS: list[type[BaseEffect]] = [
    PulseEffect,
    RainEffect,
    WipeEffect,
    PlasmaEffect,
    NoiseEffect,
    ScanEffect,
    AudioVisualizer,
]

EFFECT_NAMES = [e.name for e in ALL_EFFECTS]


def make_effect(name: str) -> BaseEffect:
    for cls in ALL_EFFECTS:
        if cls.name == name:
            return cls()
    raise ValueError(f"Unknown effect: {name!r}")
