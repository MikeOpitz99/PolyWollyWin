"""
effects.py — LED matrix visual effects for PolyWollyWin

Each effect subclasses BaseEffect and implements:
  tick(dt: float) -> list[int]   # returns physical LED frame

PARAMS (class variable) drives the per-effect parameter UI in app.py.
Format per entry:
    "attr_name": {
        "label":   str,    # display label
        "min":     int,    # slider minimum (integer)
        "max":     int,    # slider maximum
        "default": int,    # slider default  (= __init__ default * scale)
        "scale":   float,  # divide slider int by scale to get float attr value
    }
"""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Optional

import numpy as np

from renderer import (
    ROWS, COLS, PHYSICAL_LED_COUNT,
    logical_to_physical,
    MASK_NP,           # bool/uint8 (ROWS, COLS) – True where an LED exists
)

# ─────────────────────────────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────────────────────────────

class BaseEffect:
    name: str = ""
    PARAMS: dict[str, dict] = {}   # override in subclasses

    def tick(self, dt: float) -> list[int]:
        raise NotImplementedError

    def reset(self):
        """Optional: called when the effect should restart from scratch."""
        pass

    def stop(self):
        """Optional: called when the effect is being torn down (e.g. audio streams)."""
        pass

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _emit(frame: np.ndarray) -> list[int]:
        """
        Convert a (ROWS, COLS) uint8 numpy array to a physical LED list.
        Applies the mask so off-grid positions are always 0.
        """
        masked = (frame.astype(np.uint8) * MASK_NP).astype(np.uint8)
        return logical_to_physical(masked)

    @staticmethod
    def _blank() -> list[int]:
        return [0] * PHYSICAL_LED_COUNT


# ─────────────────────────────────────────────────────────────────────
# Pulse
# ─────────────────────────────────────────────────────────────────────

class PulseEffect(BaseEffect):
    name = "Pulse"
    PARAMS = {
        "speed": {"label": "Speed",  "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "peak":  {"label": "Peak",   "min": 10, "max": 255, "default": 255, "scale": 1.0},
    }

    def __init__(self, speed: float = 1.0, peak: int = 255):
        self.speed = speed
        self.peak  = peak
        self._t    = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        v = int((math.sin(self._t) * 0.5 + 0.5) * self.peak)
        frame = np.full((ROWS, COLS), v, dtype=np.uint8)
        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Matrix Rain
# ─────────────────────────────────────────────────────────────────────

class MatrixRainEffect(BaseEffect):
    """
    Classic Matrix rain: independent streams per column, each with its own
    speed and gap delay.  The head of each stream is fully bright; the trail
    decays naturally through the shared fade buffer.
    """
    name = "Matrix Rain"
    PARAMS = {
        "speed":   {"label": "Speed",   "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "density": {"label": "Density", "min": 5,  "max": 80,  "default": 30,  "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0, density: float = 0.30):
        self.speed   = speed
        self.density = density
        self._buf    = np.zeros((ROWS, COLS), dtype=np.float32)
        self._pos    = [0.0]   * COLS
        self._spd    = [1.0]   * COLS
        self._delay  = [0.0]   * COLS
        self._active = [False] * COLS
        self._spawn_all()

    def _spawn_all(self):
        for c in range(COLS):
            self._delay[c]  = random.uniform(0.0, 2.5)
            self._active[c] = False
            self._spd[c]    = random.uniform(0.6, 2.2)

    def reset(self):
        self._buf[:] = 0.0
        self._spawn_all()

    def tick(self, dt: float) -> list[int]:
        eff_dt = dt * self.speed
        self._buf *= 0.80          # trail fade every frame

        for c in range(COLS):
            if not self._active[c]:
                self._delay[c] -= eff_dt
                if self._delay[c] <= 0 and random.random() < self.density:
                    self._active[c] = True
                    self._pos[c]    = 0.0
                    self._spd[c]    = random.uniform(0.6, 2.2)
            else:
                self._pos[c] += self._spd[c] * eff_dt * 10.0
                r = int(self._pos[c])
                if r < ROWS:
                    self._buf[r, c] = 255.0
                else:
                    self._active[c] = False
                    self._delay[c]  = random.uniform(0.2, 2.0)

        out = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(out)
   


# ─────────────────────────────────────────────────────────────────────
# Matrix Rain V2  —  8 directions (paste before ALL_EFFECTS, then add to it)
# ─────────────────────────────────────────────────────────────────────

class MatrixRainEffectV2(BaseEffect):
    """
    Digital rain with 8 travel directions, controlled by the Direction
    slider (0-7):

        0 = ↓   top → bottom       (default)
        1 = ↙   diagonal top-right → bottom-left
        2 = ←   right → left
        3 = ↖   diagonal bottom-right → top-left
        4 = ↑   bottom → top
        5 = ↗   diagonal bottom-left → top-right
        6 = →   left → right
        7 = ↘   diagonal top-left → bottom-right

    Cardinal directions produce column/row streams.
    Diagonal directions produce COLS + ROWS - 1 diagonal streams,
    so the full matrix is covered even though individual streams are short.
    """
    # (dr, dc) travel vector for each index
    _VECTORS = [
        ( 1,  0),   # 0 ↓
        ( 1, -1),   # 1 ↙
        ( 0, -1),   # 2 ←
        (-1, -1),   # 3 ↖
        (-1,  0),   # 4 ↑
        (-1,  1),   # 5 ↗
        ( 0,  1),   # 6 →
        ( 1,  1),   # 7 ↘
    ]
    name = "Matrix Rain V2"
    PARAMS = {
        "speed":     {"label": "Speed",         "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "density":   {"label": "Density",        "min":  5, "max":  80, "default":  30, "scale": 100.0},
        "direction": {"label": "Direction", "min": 0, "max": 7, "default": 0, "scale": 1.0,
                      "display": {0: "↓", 1: "↙", 2: "←", 3: "↖", 4: "↑", 5: "↗", 6: "→", 7: "↘"}},
    }

    def __init__(self, speed: float = 1.0, density: float = 0.30, direction: int = 0):
        self.speed     = speed
        self.density   = density
        self.direction = direction
        self._buf      = np.zeros((ROWS, COLS), dtype=np.float32)
        self._drops:  dict = {}   # stream_idx -> {pos, spd, head_bri}
        self._cool:   dict = {}   # stream_idx -> cooldown timer (seconds)
        self._streams: list = []  # (start_r, start_c) per stream
        self._dir_cache = -1
        self._rebuild_streams()

    @staticmethod
    def _entry_cells(dr: int, dc: int) -> list:
        """All grid cells on the entry edge(s) for direction (dr, dc)."""
        if   dr > 0 and dc == 0:   return [(0,        c) for c in range(COLS)]
        elif dr < 0 and dc == 0:   return [(ROWS-1,   c) for c in range(COLS)]
        elif dr == 0 and dc > 0:   return [(r,        0) for r in range(ROWS)]
        elif dr == 0 and dc < 0:   return [(r,  COLS-1) for r in range(ROWS)]
        elif dr > 0 and dc < 0:    # ↙ — top row + right col (no shared corner)
            return [(0, c) for c in range(COLS)] + [(r, COLS-1) for r in range(1, ROWS)]
        elif dr < 0 and dc < 0:    # ↖ — bottom row + right col
            return [(ROWS-1, c) for c in range(COLS)] + [(r, COLS-1) for r in range(0, ROWS-1)]
        elif dr < 0 and dc > 0:    # ↗ — bottom row + left col
            return [(ROWS-1, c) for c in range(COLS)] + [(r, 0) for r in range(0, ROWS-1)]
        elif dr > 0 and dc > 0:    # ↘ — top row + left col
            return [(0, c) for c in range(COLS)] + [(r, 0) for r in range(1, ROWS)]
        return []

    def _rebuild_streams(self):
        idx             = int(self.direction) % 8
        dr, dc          = self._VECTORS[idx]
        self._streams   = self._entry_cells(dr, dc)
        self._dir_cache = idx
        self._drops.clear()
        self._cool.clear()
        self._buf[:] = 0

    def reset(self):
        self._buf[:] = 0
        self._drops.clear()
        self._cool.clear()

    def tick(self, dt: float) -> list[int]:
        # Rebuild geometry if the Direction slider changed
        if int(self.direction) % 8 != self._dir_cache:
            self._rebuild_streams()

        eff_dt = dt * self.speed
        dr, dc = self._VECTORS[self._dir_cache]
        n      = len(self._streams)

        # Fade all trails
        self._buf *= 0.82

        # Tick cooldowns and try to spawn a new drop per free stream
        spawn_p = min(1.0, self.density * eff_dt * 5.0)
        for idx in range(n):
            if idx in self._drops:
                continue
            if idx in self._cool:
                self._cool[idx] -= eff_dt
                if self._cool[idx] > 0:
                    continue
                del self._cool[idx]
            if random.random() < spawn_p:
                self._drops[idx] = {
                    "pos":      0.0,
                    "spd":      random.uniform(4, 18),
                    "head_bri": random.randint(180, 255),
                }

        # Advance drops; paint bright head + 2-step trailing glow
        done = []
        for idx, d in self._drops.items():
            sr, sc = self._streams[idx]
            step   = int(d["pos"])

            for offset in range(3):
                s = step - offset
                if s < 0:
                    continue
                r = sr + dr * s
                c = sc + dc * s
                if 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]:
                    bri = d["head_bri"] * (1.0 - offset * 0.35)
                    self._buf[r, c] = max(self._buf[r, c], bri)

            d["pos"] += d["spd"] * eff_dt

            # Remove when head exits the grid
            head_r = sr + dr * int(d["pos"])
            head_c = sc + dc * int(d["pos"])
            if not (0 <= head_r < ROWS and 0 <= head_c < COLS):
                done.append(idx)

        for idx in done:
            del self._drops[idx]
            self._cool[idx] = random.uniform(0.1, 1.2)

        frame = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(frame)
# ─────────────────────────────────────────────────────────────────────
# Rain
# ─────────────────────────────────────────────────────────────────────

class RainEffect(BaseEffect):
    name = "Rain"
    PARAMS = {
        "speed":   {"label": "Speed",   "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "density": {"label": "Density", "min": 5,  "max": 80,  "default": 25,  "scale": 100.0},
        "trail":   {"label": "Trail",   "min": 50, "max": 95,  "default": 80,  "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0, density: float = 0.25, trail: float = 0.80):
        self.speed   = speed
        self.density = density
        self.trail   = trail
        self._buf    = np.zeros((ROWS, COLS), dtype=np.float32)
        self._t      = 0.0

    def reset(self):
        self._buf[:] = 0
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        if self._t >= 1.0 / 12.0:
            self._t = 0.0
            self._buf[1:] = self._buf[:-1] * self.trail
            self._buf[0]  = 0
            for c in range(COLS):
                if MASK_NP[0, c] and random.random() < self.density:
                    self._buf[0, c] = 255.0
        out = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(out)


# ─────────────────────────────────────────────────────────────────────
# Wipe
# ─────────────────────────────────────────────────────────────────────

class WipeEffect(BaseEffect):
    name = "Wipe"
    PARAMS = {
        "speed":     {"label": "Speed",     "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "width":     {"label": "Width",     "min": 1,  "max": 20,  "default": 5,   "scale": 1.0},
        "direction": {"label": "Direction", "min": 0,  "max": 3,   "default": 1,   "scale": 1.0,
                      "display": {0: "\u2190", 1: "\u2192", 2: "\u2191", 3: "\u2193"}},
    }

    def __init__(self, speed: float = 1.0, width: int = 5, direction: int = 1):
        self.speed     = speed
        self.width     = width
        self.direction = direction
        self._t        = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        d = int(self.direction) % 4
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        if d in (0, 1):
            length = COLS
            pos = (self._t * 0.5 * length) % (length * 2)
            if d == 0:
                pos = (length * 2) - pos
            for c in range(COLS):
                dist = min(abs(c - pos), abs(c - (pos - length * 2)))
                if dist < self.width:
                    frame[:, c] = int(255 * (1 - dist / max(1, self.width)))
        else:
            length = ROWS
            pos = (self._t * 0.5 * length) % (length * 2)
            if d == 2:
                pos = (length * 2) - pos
            for r in range(ROWS):
                dist = min(abs(r - pos), abs(r - (pos - length * 2)))
                if dist < self.width:
                    frame[r, :] = int(255 * (1 - dist / max(1, self.width)))

        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Plasma
# ─────────────────────────────────────────────────────────────────────

class PlasmaEffect(BaseEffect):
    name = "Plasma"
    PARAMS = {
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0):
        self.speed = speed
        self._t    = 0.0
        r_idx = np.arange(ROWS).reshape(ROWS, 1)
        c_idx = np.arange(COLS).reshape(1, COLS)
        self._r = r_idx
        self._c = c_idx

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        v  = (np.sin(self._c * 0.4 + self._t)
            + np.sin(self._r * 0.8 + self._t * 1.3)
            + np.sin((self._c + self._r) * 0.35 + self._t * 0.7))
        v  = ((v / 3.0) * 0.5 + 0.5) * 255
        frame = np.clip(v, 0, 255).astype(np.uint8)
        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Noise
# ─────────────────────────────────────────────────────────────────────

class NoiseEffect(BaseEffect):
    name = "Noise"
    PARAMS = {
        "density": {"label": "Density", "min": 10, "max": 100, "default": 60, "scale": 100.0},
        "speed":   {"label": "Speed",   "min": 10, "max": 500, "default": 100, "scale": 100.0},
    }

    def __init__(self, density: float = 0.60, speed: float = 1.0):
        self.density = density
        self.speed   = speed
        self._t      = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        mask  = np.random.random((ROWS, COLS)) < self.density
        vals  = np.random.randint(50, 256, (ROWS, COLS), dtype=np.uint8)
        frame[mask] = vals[mask]
        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Scan
# ─────────────────────────────────────────────────────────────────────

class ScanEffect(BaseEffect):
    name = "Scan"
    PARAMS = {
        "speed":     {"label": "Speed",     "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "direction": {"label": "Direction", "min": 0,  "max": 3,   "default": 1,   "scale": 1.0,
                      "display": {0: "\u2190", 1: "\u2192", 2: "\u2191", 3: "\u2193"}},
    }

    def __init__(self, speed: float = 1.0, direction: int = 1):
        self.speed     = speed
        self.direction = direction
        self._t        = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        d = int(self.direction) % 4
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        if d in (0, 1):
            col = int(self._t * 10) % COLS
            if d == 0:
                col = COLS - 1 - col
            for dc, bri in ((0, 255), (-1, 120), (1, 120)):
                c = col + dc
                if 0 <= c < COLS:
                    frame[:, c] = bri
        else:
            row = int(self._t * 6) % ROWS
            if d == 2:
                row = ROWS - 1 - row
            for dr, bri in ((0, 255), (-1, 120), (1, 120)):
                r = row + dr
                if 0 <= r < ROWS:
                    frame[r, :] = bri

        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Starfield
# ─────────────────────────────────────────────────────────────────────

class StarfieldEffect(BaseEffect):
    name = "Starfield"
    PARAMS = {
        "count": {"label": "Stars", "min": 5,  "max": 80,  "default": 40,  "scale": 1.0},
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "trail": {"label": "Trail", "min": 50, "max": 98,  "default": 86,  "scale": 100.0},
    }

    def __init__(self, count: int = 40, speed: float = 1.0, trail: float = 0.86):
        self.count = count
        self.speed = speed
        self.trail = trail
        self._stars: list[dict] = []
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)
        self._cx = (COLS - 1) / 2.0
        self._cy = (ROWS - 1) / 2.0
        self._spawn_all()

    def _new_star(self, far: bool = True) -> dict:
        # Pseudo-3D point. x/y are centered-space coordinates, z is depth.
        # Small z means close to camera, large z means far away.
        angle = random.uniform(0.0, math.tau)
        radius = random.uniform(0.15, 1.6)
        z = random.uniform(7.0, 18.0) if far else random.uniform(2.5, 18.0)
        return {
            "x": math.cos(angle) * radius,
            "y": math.sin(angle) * radius * 0.42,
            "z": z,
            "bri": random.uniform(120, 255),
            "tw": random.uniform(0.85, 1.15),
        }

    def _spawn_all(self):
        self._buf[:] = 0
        self._stars = [self._new_star(far=False) for _ in range(int(self.count))]

    def reset(self):
        self._spawn_all()

    def _paint_star(self, x: float, y: float, bri: float):
        r, c = int(round(y)), int(round(x))
        if 0 <= r < ROWS and 0 <= c < COLS:
            self._buf[r, c] = max(self._buf[r, c], bri)
            # Close/bright stars get a tiny glow, which sells the forward-flight feel.
            if bri > 185:
                glow = bri * 0.22
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < ROWS and 0 <= cc < COLS:
                        self._buf[rr, cc] = max(self._buf[rr, cc], glow)

    def tick(self, dt: float) -> list[int]:
        target = int(max(1, self.count))
        while len(self._stars) < target:
            self._stars.append(self._new_star())
        while len(self._stars) > target:
            self._stars.pop()

        eff_dt = dt * self.speed
        self._buf *= max(0.50, min(0.98, self.trail))

        for i, s in enumerate(self._stars):
            # Move toward camera. As z shrinks, projected x/y move outward from center.
            s["z"] -= eff_dt * 5.0
            if s["z"] <= 0.35:
                self._stars[i] = self._new_star(far=True)
                continue

            scale = 9.5 / s["z"]
            px = self._cx + s["x"] * scale * COLS * 0.42
            py = self._cy + s["y"] * scale * ROWS * 0.90

            if px < -2 or px > COLS + 1 or py < -2 or py > ROWS + 1:
                self._stars[i] = self._new_star(far=True)
                continue

            closeness = max(0.0, min(1.0, (18.0 - s["z"]) / 18.0))
            bri = (45 + closeness * 220) * s["tw"]
            self._paint_star(px, py, bri)

        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))

# ─────────────────────────────────────────────────────────────────────
# Comet
# ─────────────────────────────────────────────────────────────────────

class CometEffect(BaseEffect):
    name = "Comet"
    PARAMS = {
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "trail": {"label": "Trail", "min": 50, "max": 99,  "default": 85,  "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0, trail: float = 0.85):
        self.speed  = speed
        self.trail  = trail
        self._buf   = np.zeros((ROWS, COLS), dtype=np.float32)
        self._x     = 0.0
        self._y     = float(random.randint(0, ROWS - 1))
        self._vy    = random.uniform(-2, 2)
        self._t     = 0.0

    def reset(self):
        self._buf[:] = 0
        self._x = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        self._x = (self._t * 15) % COLS
        self._y = (self._y + self._vy * dt * self.speed) % ROWS
        if self._y < 0:
            self._y += ROWS
        self._buf *= self.trail
        r, c = int(self._y), int(self._x)
        if 0 <= r < ROWS and 0 <= c < COLS:
            self._buf[r, c] = 255.0
        out = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(out)


# ─────────────────────────────────────────────────────────────────────
# Ripple
# ─────────────────────────────────────────────────────────────────────

class RippleEffect(BaseEffect):
    name = "Ripple"
    PARAMS = {
        "speed":    {"label": "Speed",  "min": 10,  "max": 500, "default": 100, "scale": 100.0},
        "x_offset": {"label": "Move X", "min": -18, "max": 18,  "default": 0,   "scale": 1.0},
    }

    def __init__(self, speed: float = 1.0, x_offset: int = 0):
        self.speed    = speed
        self.x_offset = x_offset
        self._t       = 0.0
        self._cy      = ROWS / 2
        self._r_idx   = np.arange(ROWS).reshape(ROWS, 1)
        self._c_idx   = np.arange(COLS).reshape(1, COLS)

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        cx = (COLS / 2) + float(self.x_offset)
        dist = np.sqrt((self._r_idx - self._cy) ** 2 + (self._c_idx - cx) ** 2)
        v = np.sin(dist * 1.2 - self._t * 6.0) * 0.5 + 0.5
        frame = np.clip(v * 255, 0, 255).astype(np.uint8)
        return self._emit(frame)

# ─────────────────────────────────────────────────────────────────────
# Helix
# ─────────────────────────────────────────────────────────────────────

class HelixEffect(BaseEffect):
    name = "Helix"
    PARAMS = {
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0):
        self.speed = speed
        self._t    = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        for c in range(COLS):
            y1 = int((math.sin(c * 0.4 + self._t * 3) * 0.5 + 0.5) * (ROWS - 1))
            y2 = int((math.sin(c * 0.4 + self._t * 3 + math.pi) * 0.5 + 0.5) * (ROWS - 1))
            if 0 <= y1 < ROWS:
                frame[y1, c] = 255
            if 0 <= y2 < ROWS:
                frame[y2, c] = 180
        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Fireworks
# ─────────────────────────────────────────────────────────────────────

class FireworksEffect(BaseEffect):
    name = "Fireworks"
    PARAMS = {
        "speed": {"label": "Speed",  "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "count": {"label": "Bursts", "min": 1,  "max": 8,   "default": 3,   "scale": 1.0},
        "trail": {"label": "Trail",  "min": 50, "max": 98,  "default": 88,  "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0, count: int = 3, trail: float = 0.88):
        self.speed = speed
        self.count = count
        self.trail = trail
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)
        self._rockets: list[dict] = []
        self._bursts: list[dict] = []
        self._t = 0.0
        self._next = 0.0

    def reset(self):
        self._buf[:] = 0
        self._rockets.clear()
        self._bursts.clear()
        self._t = 0.0
        self._next = 0.0

    def _spawn_rocket(self):
        x = random.uniform(4, COLS - 5)
        target_y = random.uniform(1.0, ROWS * 0.45)
        self._rockets.append({
            "x": x,
            "y": float(ROWS - 1),
            "vx": random.uniform(-0.8, 0.8),
            "vy": random.uniform(-8.5, -5.5),
            "target_y": target_y,
            "bri": 255.0,
        })

    def _burst(self, x: float, y: float):
        particles = []
        n = random.randint(18, 34)
        for i in range(n):
            angle = (math.pi * 2 * i / n) + random.uniform(-0.18, 0.18)
            spd = random.uniform(2.5, 8.0)
            particles.append({
                "x": x, "y": y,
                "vx": math.cos(angle) * spd,
                "vy": math.sin(angle) * spd * 0.55,
                "bri": random.uniform(180, 255),
                "tw": random.uniform(0.75, 1.15),
            })
        self._bursts.append({"particles": particles})

    def _paint_dot(self, frame: np.ndarray, x: float, y: float, bri: float):
        r, c = int(round(y)), int(round(x))
        if 0 <= r < ROWS and 0 <= c < COLS:
            frame[r, c] = max(frame[r, c], bri)
        # tiny glow
        for dr, dc, scale in ((-1,0,0.35),(1,0,0.25),(0,-1,0.25),(0,1,0.25)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < ROWS and 0 <= cc < COLS:
                frame[rr, cc] = max(frame[rr, cc], bri * scale)

    def tick(self, dt: float) -> list[int]:
        eff_dt = dt * self.speed
        self._t += eff_dt
        self._buf *= max(0.50, min(0.98, self.trail))

        active = len(self._rockets) + len(self._bursts)
        if self._t >= self._next and active < self.count:
            self._spawn_rocket()
            self._next = self._t + random.uniform(0.35, 1.2)

        dead_rockets = []
        for i, rkt in enumerate(self._rockets):
            rkt["x"] += rkt["vx"] * eff_dt
            rkt["y"] += rkt["vy"] * eff_dt
            rkt["vy"] += 3.0 * eff_dt
            self._paint_dot(self._buf, rkt["x"], rkt["y"], rkt["bri"])
            self._paint_dot(self._buf, rkt["x"] - rkt["vx"] * 0.4, rkt["y"] + 1, 90)
            if rkt["y"] <= rkt["target_y"] or rkt["vy"] >= -0.5:
                self._burst(rkt["x"], rkt["y"])
                dead_rockets.append(i)
        for i in reversed(dead_rockets):
            self._rockets.pop(i)

        dead_bursts = []
        for i, burst in enumerate(self._bursts):
            alive = False
            for p in burst["particles"]:
                p["x"] += p["vx"] * eff_dt
                p["y"] += p["vy"] * eff_dt
                p["vy"] += 2.5 * eff_dt
                p["bri"] *= 0.94
                if random.random() < 0.12:
                    p["bri"] *= p["tw"]
                if p["bri"] > 5:
                    alive = True
                self._paint_dot(self._buf, p["x"], p["y"], p["bri"])
            if not alive:
                dead_bursts.append(i)
        for i in reversed(dead_bursts):
            self._bursts.pop(i)

        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ─────────────────────────────────────────────────────────────────────
# Bounce
# ─────────────────────────────────────────────────────────────────────

class BounceEffect(BaseEffect):
    name = "Bounce"
    PARAMS = {
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0):
        self.speed = speed
        self._x    = float(COLS // 2)
        self._y    = float(ROWS // 2)
        self._vx   = random.choice([-6, 6])
        self._vy   = random.choice([-3, 3])
        self._buf  = np.zeros((ROWS, COLS), dtype=np.float32)

    def reset(self):
        self._buf[:] = 0

    def tick(self, dt: float) -> list[int]:
        self._x += self._vx * dt * self.speed
        self._y += self._vy * dt * self.speed
        if self._x <= 0 or self._x >= COLS - 1:
            self._vx *= -1
            self._x = max(0.0, min(float(COLS - 1), self._x))
        if self._y <= 0 or self._y >= ROWS - 1:
            self._vy *= -1
            self._y = max(0.0, min(float(ROWS - 1), self._y))
        self._buf *= 0.80
        r, c = int(self._y), int(self._x)
        if 0 <= r < ROWS and 0 <= c < COLS:
            self._buf[r, c] = 255.0
        out = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(out)


# ─────────────────────────────────────────────────────────────────────
# Wave
# ─────────────────────────────────────────────────────────────────────

class WaveEffect(BaseEffect):
    name = "Wave"
    PARAMS = {
        "speed":     {"label": "Speed",     "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "waves":     {"label": "Waves",     "min": 1,  "max": 10,  "default": 3,   "scale": 1.0},
        "direction": {"label": "Direction", "min": 0,  "max": 3,   "default": 1,   "scale": 1.0,
                      "display": {0: "\u2190", 1: "\u2192", 2: "\u2191", 3: "\u2193"}},
    }

    def __init__(self, speed: float = 1.0, waves: int = 3, direction: int = 1):
        self.speed     = speed
        self.waves     = waves
        self.direction = direction
        self._t        = 0.0
        self._r        = np.arange(ROWS).reshape(ROWS, 1)
        self._c        = np.arange(COLS).reshape(1, COLS)

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        d = int(self.direction) % 4
        phase = self._t * 4
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        if d in (0, 1):
            freq = self.waves * 2 * math.pi / COLS
            sign = 1 if d == 1 else -1
            y_wave = (np.sin(self._c * freq - sign * phase) * 0.5 + 0.5) * (ROWS - 1)
            for c in range(COLS):
                y = int(y_wave[0, c])
                for off, bri in ((0, 255), (-1, 120), (1, 120)):
                    r = y + off
                    if 0 <= r < ROWS:
                        frame[r, c] = max(frame[r, c], bri)
        else:
            freq = self.waves * 2 * math.pi / ROWS
            sign = 1 if d == 3 else -1
            x_wave = (np.sin(self._r * freq - sign * phase) * 0.5 + 0.5) * (COLS - 1)
            for r in range(ROWS):
                x = int(x_wave[r, 0])
                for off, bri in ((0, 255), (-1, 120), (1, 120)):
                    c = x + off
                    if 0 <= c < COLS:
                        frame[r, c] = max(frame[r, c], bri)

        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ─────────────────────────────────────────────────────────────────────
# Snake (with simple AI auto-play)
# ─────────────────────────────────────────────────────────────────────

class SnakeEffect(BaseEffect):
    name = "Snake"
    PARAMS = {
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
    }

    def __init__(self, speed: float = 1.0):
        self.speed   = speed
        self._t      = 0.0
        self._reset_game()

    def _reset_game(self):
        mid_r, mid_c = ROWS // 2, COLS // 2
        self._snake  = [(mid_r, mid_c), (mid_r, mid_c - 1), (mid_r, mid_c - 2)]
        self._dir    = (0, 1)
        self._food   = self._spawn_food()
        self._buf    = np.zeros((ROWS, COLS), dtype=np.float32)

    def _valid_cells(self) -> set[tuple[int, int]]:
        return {(r, c) for r in range(ROWS) for c in range(COLS) if MASK_NP[r, c]}

    def _spawn_food(self) -> tuple[int, int]:
        occupied = set(self._snake)
        options  = list(self._valid_cells() - occupied)
        return random.choice(options) if options else (0, 0)

    def _ai_move(self):
        """Simple greedy AI toward food."""
        head = self._snake[0]
        fr, fc = self._food
        occupied = set(self._snake)
        candidates = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = head[0] + dr, head[1] + dc
            if (nr, nc) in self._valid_cells() and (nr, nc) not in occupied:
                dist = abs(nr - fr) + abs(nc - fc)
                candidates.append((dist, dr, dc))
        if candidates:
            candidates.sort()
            _, dr, dc = candidates[0]
            self._dir = (dr, dc)

    def reset(self):
        self._reset_game()
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        if self._t >= 1.0 / 8.0:
            self._t = 0.0
            self._ai_move()
            head = self._snake[0]
            new_head = (head[0] + self._dir[0], head[1] + self._dir[1])
            if new_head not in self._valid_cells() or new_head in set(self._snake):
                self._reset_game()
            else:
                self._snake.insert(0, new_head)
                if new_head == self._food:
                    self._food = self._spawn_food()
                else:
                    self._snake.pop()

        self._buf *= 0.88
        for i, (r, c) in enumerate(self._snake):
            self._buf[r, c] = 255 if i == 0 else 160
        fr, fc = self._food
        if 0 <= fr < ROWS and 0 <= fc < COLS:
            self._buf[fr, fc] = 200

        out = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(out)


# ─────────────────────────────────────────────────────────────────────
# Clock (3×5 pixel font)
# ─────────────────────────────────────────────────────────────────────

_DIGITS = {
    "0": [0b111, 0b101, 0b101, 0b101, 0b111],
    "1": [0b010, 0b110, 0b010, 0b010, 0b111],
    "2": [0b111, 0b001, 0b111, 0b100, 0b111],
    "3": [0b111, 0b001, 0b111, 0b001, 0b111],
    "4": [0b101, 0b101, 0b111, 0b001, 0b001],
    "5": [0b111, 0b100, 0b111, 0b001, 0b111],
    "6": [0b111, 0b100, 0b111, 0b101, 0b111],
    "7": [0b111, 0b001, 0b001, 0b001, 0b001],
    "8": [0b111, 0b101, 0b111, 0b101, 0b111],
    "9": [0b111, 0b101, 0b111, 0b001, 0b111],
    ":": [0b000, 0b010, 0b000, 0b010, 0b000],
}

class ClockEffect(BaseEffect):
    name = "Clock"
    PARAMS = {
        "x_offset": {"label": "Move X", "min": -18, "max": 18, "default": 0, "scale": 1.0},
    }

    def __init__(self, x_offset: int = 0):
        self.x_offset = x_offset

    def tick(self, dt: float) -> list[int]:
        t   = time.localtime()
        txt = f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        x = 1 + int(self.x_offset)
        for ch in txt:
            glyph = _DIGITS.get(ch)
            if glyph is None:
                x += 4; continue
            for row_i, bits in enumerate(glyph):
                r = row_i + (ROWS // 2 - 3)
                if 0 <= r < ROWS:
                    for bit_i in range(3):
                        c = x + (2 - bit_i)
                        if 0 <= c < COLS and (bits >> bit_i) & 1:
                            frame[r, c] = 255
            x += 4
        return self._emit(frame)



# ─────────────────────────────────────────────────────────────────────
# Typing Visualizer
# ─────────────────────────────────────────────────────────────────────

class TypingEffect(BaseEffect):
    name = "Typing"
    PARAMS = {}

    def __init__(self):
        self._buf    = np.zeros((ROWS, COLS), dtype=np.float32)
        self._lock   = threading.Lock()
        self._demo_t = 0.0
        self._demo   = False
        self._listener = None
        try:
            from pynput import keyboard
            self._listener = keyboard.Listener(on_press=self._on_press)
            self._listener.start()
        except Exception:
            self._demo = True

    def _on_press(self, key):
        col = random.randint(0, COLS - 1)
        with self._lock:
            self._buf[:, col] = 255.0

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def tick(self, dt: float) -> list[int]:
        if self._demo:
            self._demo_t += dt
            if self._demo_t >= 0.18:
                self._demo_t = 0.0
                col = random.randint(0, COLS - 1)
                with self._lock:
                    self._buf[:, col] = 255.0
        with self._lock:
            self._buf *= 0.87
            out = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(out)


# ─────────────────────────────────────────────────────────────────────
# Audio Visualizer
# ─────────────────────────────────────────────────────────────────────


class AudioVisualizer(BaseEffect):
    name = "Audio"
    PARAMS = {
        "sensitivity": {"label": "Sensitivity", "min": 100, "max": 3000, "default": 900,  "scale": 100.0},
        "boost":       {"label": "Boost",       "min": 100, "max": 5000, "default": 1800, "scale": 100.0},
        "falloff":     {"label": "Falloff",     "min": 50,  "max": 98,   "default": 80,   "scale": 100.0},
        "floor":       {"label": "Noise Floor", "min": 1,   "max": 100,  "default": 8,    "scale": 10000.0},
    }

    def __init__(self, sensitivity: float = 9.0, boost: float = 18.0,
                 falloff: float = 0.80, floor: float = 0.0008):
        self.sensitivity = sensitivity
        self.boost = boost
        self.falloff = falloff
        self.floor = floor
        self._bars  = np.zeros(COLS, dtype=np.float32)
        self._peaks = np.zeros(COLS, dtype=np.float32)
        self._stream = None
        self._lock   = threading.Lock()
        self._buf: Optional[np.ndarray] = None
        self._last_audio_t = 0.0
        self._demo_t = 0.0
        self._mode = "demo"
        self._samplerate = 48000
        self._agc = 0.05

        # Draw only on physical LEDs.  The keyboard has a diagonal-cut mask,
        # so ordinary bottom-up bars disappear on the low-left side.
        self._col_rows = [
            [r for r in range(ROWS - 1, -1, -1) if MASK_NP[r, c]]
            for c in range(COLS)
        ]

        self._open_stream()

    def _open_stream(self):
        """Prefer Windows WASAPI loopback, fall back to microphone, then demo."""
        try:
            import sounddevice as sd
        except Exception:
            self._mode = "demo"
            return

        # Windows system-output capture.
        try:
            import sys as _sys
            if _sys.platform == "win32":
                devices = sd.query_devices()
                hostapis = sd.query_hostapis()
                candidates: list[int] = []
                try:
                    default_out = sd.default.device[1]
                    if default_out is not None and int(default_out) >= 0:
                        candidates.append(int(default_out))
                except Exception:
                    pass

                for idx, dev in enumerate(devices):
                    try:
                        host_name = hostapis[dev["hostapi"]].get("name", "")
                        if "WASAPI" in host_name.upper() and int(dev.get("max_output_channels", 0) or 0) > 0:
                            if idx not in candidates:
                                candidates.append(idx)
                    except Exception:
                        pass

                for idx in candidates:
                    try:
                        dev = devices[idx]
                        host_name = hostapis[dev["hostapi"]].get("name", "")
                        if "WASAPI" not in host_name.upper():
                            continue
                        channels = max(1, min(2, int(dev.get("max_output_channels", 2) or 2)))
                        samplerate = int(dev.get("default_samplerate", 48000) or 48000)
                        extra = sd.WasapiSettings(loopback=True)
                        self._samplerate = samplerate
                        self._stream = sd.InputStream(
                            device=idx,
                            channels=channels,
                            samplerate=samplerate,
                            blocksize=2048,
                            dtype="float32",
                            extra_settings=extra,
                            callback=self._audio_cb,
                        )
                        self._stream.start()
                        self._mode = "loopback"
                        return
                    except Exception:
                        self._stream = None
        except Exception:
            self._stream = None

        # Mic/input fallback.
        try:
            self._samplerate = 44100
            self._stream = sd.InputStream(
                channels=1,
                samplerate=self._samplerate,
                blocksize=2048,
                dtype="float32",
                callback=self._audio_cb,
            )
            self._stream.start()
            self._mode = "input"
            return
        except Exception:
            self._stream = None
            self._mode = "demo"

    def _audio_cb(self, indata, frames, time_info, status):
        try:
            data = np.asarray(indata, dtype=np.float32)
            if data.ndim == 2:
                data = data.mean(axis=1)
            else:
                data = data.reshape(-1)
            data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
            with self._lock:
                self._buf = data.copy()
                if float(np.sqrt(np.mean(data * data))) > max(0.00002, self.floor * 0.35):
                    self._last_audio_t = time.monotonic()
        except Exception:
            pass

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _paint_bar(self, frame: np.ndarray, col: int, height: float, peak: float = 0.0):
        rows = self._col_rows[col]
        if not rows:
            return
        h = int(round(max(0.0, min(float(len(rows)), height))))
        for i, r in enumerate(rows[:h]):
            bri = int(110 + 145 * (1.0 - i / max(1, len(rows))))
            frame[r, col] = max(frame[r, col], bri)

        pr = int(round(max(0.0, min(float(len(rows) - 1), peak))))
        if 0 <= pr < len(rows):
            frame[rows[pr], col] = max(frame[rows[pr], col], 235)

    def _demo_frame(self, dt: float) -> list[int]:
        self._demo_t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        for c in range(COLS):
            rows = self._col_rows[c]
            if not rows:
                continue
            wave = math.sin(self._demo_t * 4.0 + c * 0.36) * 0.5 + 0.5
            pulse = math.sin(self._demo_t * 1.7 + c * 0.11) * 0.5 + 0.5
            h = 1 + wave * max(1, len(rows) - 1) * (0.35 + pulse * 0.55)
            self._paint_bar(frame, c, h)
        return self._emit(frame)

    def tick(self, dt: float) -> list[int]:
        with self._lock:
            raw = None if self._buf is None else self._buf.copy()

        if raw is None or len(raw) < 64:
            return self._demo_frame(dt)

        raw = np.nan_to_num(raw.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        raw -= float(np.mean(raw))
        rms = float(np.sqrt(np.mean(raw * raw)))
        floor = max(0.00001, float(self.floor))

        if rms < floor and (time.monotonic() - self._last_audio_t) > 0.50:
            return self._demo_frame(dt)

        # Normalize gently, not accurately.  This is a keyboard visualizer,
        # not a meter.  It must move visibly at normal desktop volume.
        active = max(0.0, rms - floor)
        self._agc = max(self._agc * 0.96, active * 6.0, 0.003)
        norm = np.clip(raw / self._agc, -1.0, 1.0)

        window = np.hanning(len(norm)).astype(np.float32)
        fft = np.abs(np.fft.rfft(norm * window))
        freqs = np.fft.rfftfreq(len(norm), d=1.0 / max(8000, self._samplerate))
        if len(fft) < 16:
            return self._demo_frame(dt)

        fft[:2] = 0
        low = 45.0
        high = min(16000.0, self._samplerate / 2.0)
        edges = np.geomspace(low, high, COLS + 1)
        vals = np.zeros(COLS, dtype=np.float32)
        for c in range(COLS):
            mask = (freqs >= edges[c]) & (freqs < edges[c + 1])
            if np.any(mask):
                vals[c] = float(np.mean(fft[mask]))

        # Bass kick raises the whole display slightly so beats feel like hits.
        bass_mask = (freqs >= 45) & (freqs <= 180)
        bass = float(np.mean(fft[bass_mask])) if np.any(bass_mask) else 0.0

        vals = np.log1p(vals * max(0.1, self.boost) * max(0.1, self.sensitivity))
        vals += math.log1p(bass * max(0.1, self.boost) * 0.25)
        mx = float(np.percentile(vals, 92)) if np.any(vals) else 0.0
        if mx <= 0.0001:
            return self._demo_frame(dt)
        vals = np.clip(vals / mx, 0.0, 1.0)
        vals = vals ** 0.55

        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        decay = max(0.50, min(0.98, float(self.falloff)))
        for c, val in enumerate(vals):
            rows = self._col_rows[c]
            if not rows:
                continue
            target_h = val * len(rows)
            self._bars[c] = max(self._bars[c] * decay, target_h)
            self._peaks[c] = max(self._peaks[c] * 0.955, self._bars[c])
            self._paint_bar(frame, c, self._bars[c], self._peaks[c])

        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Fire  (demoscene cellular-automaton flame)
# ─────────────────────────────────────────────────────────────────────

class FireEffect(BaseEffect):
    """Spiky cellular flame with LRUD flow control."""
    name = "Fire"
    PARAMS = {
        "intensity": {"label": "Intensity", "min": 10, "max": 100, "default": 85, "scale": 100.0},
        "cooling":   {"label": "Cooling",   "min":  1, "max":  60, "default": 20, "scale":   1.0},
        "speed":     {"label": "Speed",     "min": 10, "max": 300, "default": 100, "scale": 100.0},
        "flow":      {"label": "Flow",      "min":  0, "max":   3, "default":  2, "scale":   1.0,
                      "display": {0: "\u2190", 1: "\u2192", 2: "\u2191", 3: "\u2193"}},
    }

    def __init__(self, intensity: float = 0.85, cooling: float = 20.0, speed: float = 1.0, flow: int = 2):
        self.intensity = intensity
        self.cooling = cooling
        self.speed = speed
        self.flow = flow
        self._heat = np.zeros((ROWS, COLS), dtype=np.float32)
        self._acc = 0.0

    def reset(self):
        self._heat[:] = 0
        self._acc = 0.0

    def _source_mask(self, d: int):
        src = np.zeros((ROWS, COLS), dtype=bool)
        if d == 0:      # left flowing flame, source on right
            src[:, COLS-3:COLS] = True
        elif d == 1:    # right flowing flame, source on left
            src[:, 0:3] = True
        elif d == 2:    # up flowing flame, source on bottom
            src[ROWS-3:ROWS, :] = True
        else:           # down flowing flame, source on top
            src[0:3, :] = True
        return src

    def _shift(self, arr, dr, dc):
        out = np.zeros_like(arr)
        r_src0 = max(0, -dr); r_src1 = ROWS - max(0, dr)
        c_src0 = max(0, -dc); c_src1 = COLS - max(0, dc)
        r_dst0 = max(0, dr);  r_dst1 = ROWS - max(0, -dr)
        c_dst0 = max(0, dc);  c_dst1 = COLS - max(0, -dc)
        out[r_dst0:r_dst1, c_dst0:c_dst1] = arr[r_src0:r_src1, c_src0:c_src1]
        return out

    def _advance(self):
        d = int(self.flow) % 4
        vectors = {0: (0, -1), 1: (0, 1), 2: (-1, 0), 3: (1, 0)}
        dr, dc = vectors[d]
        src = self._source_mask(d)

        # hot, uneven source with bursty tips
        seed = np.random.uniform(160, 255, (ROWS, COLS)).astype(np.float32)
        hot = (np.random.random((ROWS, COLS)) < self.intensity) & src
        self._heat[hot] = np.maximum(self._heat[hot], seed[hot])
        self._heat[src & ~hot] *= 0.72

        forward = self._shift(self._heat, dr, dc)
        leftish = self._shift(self._heat, dr + (1 if dc else 0), dc + (1 if dr else 0))
        rightish = self._shift(self._heat, dr - (1 if dc else 0), dc - (1 if dr else 0))
        back2 = self._shift(self._heat, dr * 2, dc * 2)
        avg = forward * 0.48 + leftish * 0.18 + rightish * 0.18 + back2 * 0.16

        # Random cold bites carve flame into sharper tongues.
        cool = np.random.uniform(0.5, 1.55, (ROWS, COLS)) * self.cooling
        bites = np.random.random((ROWS, COLS)) < 0.08
        cool[bites] *= np.random.uniform(2.2, 4.0, np.count_nonzero(bites))
        self._heat = np.maximum(0.0, avg - cool)

        # Occasional spiky hot flecks travelling with the flow.
        flecks = np.random.random((ROWS, COLS)) < 0.025
        self._heat[flecks] = np.maximum(self._heat[flecks], np.random.uniform(130, 240, np.count_nonzero(flecks)))

    def tick(self, dt: float) -> list[int]:
        self._acc += dt * self.speed
        step = 1.0 / 30.0
        while self._acc >= step:
            self._acc -= step
            self._advance()
        return self._emit(np.clip(self._heat, 0, 255).astype(np.uint8))


# ─────────────────────────────────────────────────────────────────────
# Metaballs / Lava Lamp
# ─────────────────────────────────────────────────────────────────────

class MetaballsEffect(BaseEffect):
    """
    Lava-lamp metaballs. Each blob follows a sinusoidal Lissajous path
    anchored near a random home position. The field at each pixel is the
    sum of Gaussian contributions from every blob; overlapping blobs
    create bright hot spots.
    """
    name = "Metaballs"
    PARAMS = {
        "count":  {"label": "Blobs",  "min": 2, "max":  8,  "default":  4,  "scale":   1.0},
        "radius": {"label": "Radius", "min": 5, "max": 50,  "default": 25,  "scale":  10.0},
        "speed":  {"label": "Speed",  "min": 10, "max": 300, "default": 100, "scale": 100.0},
    }

    def __init__(self, count: int = 4, radius: float = 2.5, speed: float = 1.0):
        self.count  = count   # number of blobs
        self.radius = radius  # Gaussian σ in grid units
        self.speed  = speed
        self._blobs: list[dict] = []
        self._t     = 0.0
        # pre-build pixel coordinate grids
        self._rr = np.arange(ROWS, dtype=np.float32).reshape(ROWS, 1)
        self._cc = np.arange(COLS, dtype=np.float32).reshape(1, COLS)
        self._spawn()

    def _spawn(self):
        self._blobs = []
        for _ in range(self.count):
            self._blobs.append({
                "ox": random.uniform(4,      COLS - 4),
                "oy": random.uniform(1,      ROWS - 1),
                "ax": random.uniform(3.0,    8.0),
                "ay": random.uniform(1.5,    3.5),
                "fx": random.uniform(0.25,   0.9),
                "fy": random.uniform(0.30,   1.0),
                "px": random.uniform(0,      math.pi * 2),
                "py": random.uniform(0,      math.pi * 2),
            })

    def reset(self):
        self._spawn()
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        # Respawn if blob count changed
        if len(self._blobs) != self.count:
            self._spawn()

        self._t  += dt * self.speed
        sigma2    = max(0.01, self.radius ** 2) * 2.0
        field     = np.zeros((ROWS, COLS), dtype=np.float32)

        for b in self._blobs:
            bx = b["ox"] + math.sin(self._t * b["fx"] + b["px"]) * b["ax"]
            by = b["oy"] + math.sin(self._t * b["fy"] + b["py"]) * b["ay"]
            d2 = (self._rr - by) ** 2 + (self._cc - bx) ** 2
            field += np.exp(-d2 / sigma2)

        # Normalise: a single blob at its center contributes exp(0)=1;
        # scale so that value 1.5 maps to 255 (slight clipping when blobs merge).
        out = np.clip(field * (255.0 / 1.5), 0, 255).astype(np.uint8)
        return self._emit(out)


# ─────────────────────────────────────────────────────────────────────
# Game of Life
# ─────────────────────────────────────────────────────────────────────

class GameOfLifeEffect(BaseEffect):
    """
    Conway's Game of Life on the LED mask.

    Features:
    • Trail: dead cells fade gracefully instead of snapping to black.
    • Auto-reseed on extinction or stagnation (identical generation for
      3+ consecutive steps).
    """
    name = "Game of Life"
    PARAMS = {
        "density": {"label": "Density", "min": 10, "max": 80,  "default": 35,  "scale": 100.0},
        "speed":   {"label": "Speed",   "min": 10, "max": 500, "default": 150, "scale": 100.0},
        "trail":   {"label": "Trail",   "min":  0, "max":  95, "default":  70, "scale": 100.0},
    }

    def __init__(self, density: float = 0.35, speed: float = 1.5, trail: float = 0.70):
        self.density = density   # initial live fraction
        self.speed   = speed     # generations per second
        self.trail   = trail     # brightness retained by dead cells per generation
        self._grid   = np.zeros((ROWS, COLS), dtype=np.uint8)
        self._glow   = np.zeros((ROWS, COLS), dtype=np.float32)
        self._acc    = 0.0
        self._prev   = None
        self._stag   = 0
        self._seed()

    def _seed(self):
        rng            = np.random.random((ROWS, COLS)) < self.density
        self._grid     = (rng & (MASK_NP > 0)).astype(np.uint8)
        self._glow[:]  = self._grid.astype(np.float32) * 255.0
        self._prev     = None
        self._stag     = 0

    def reset(self):
        self._seed()
        self._acc = 0.0

    @staticmethod
    def _count_neighbors(g: np.ndarray) -> np.ndarray:
        n = np.zeros_like(g, dtype=np.int32)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                n += np.roll(np.roll(g, dr, axis=0), dc, axis=1)
        return n

    def _step(self):
        n    = self._count_neighbors(self._grid.astype(np.int32))
        live = self._grid == 1
        born     = (~live) & (n == 3)
        survive  = live    & ((n == 2) | (n == 3))
        new_grid = (born | survive).astype(np.uint8)
        new_grid &= (MASK_NP > 0).astype(np.uint8)  # kill off-mask cells

        # Stagnation detection
        if self._prev is not None and np.array_equal(new_grid, self._prev):
            self._stag += 1
        else:
            self._stag = 0
        self._prev = self._grid.copy()

        if new_grid.sum() == 0 or self._stag >= 3:
            self._seed()
            return

        self._grid = new_grid
        # Update glow
        self._glow[new_grid == 1] = 255.0
        self._glow[new_grid == 0] *= self.trail

    def tick(self, dt: float) -> list[int]:
        self._acc += dt * self.speed
        step = 1.0   # one generation per "speed" second-unit
        while self._acc >= step:
            self._acc -= step
            self._step()
        out = np.clip(self._glow, 0, 255).astype(np.uint8)
        return self._emit(out)



# ─────────────────────────────────────────────────────────────────────
# Lightning / Storm
# ─────────────────────────────────────────────────────────────────────

class LightningEffect(BaseEffect):
    name = "Lightning"
    PARAMS = {
        "bolts": {"label": "Bolts", "min": 1,  "max": 5,   "default": 2,   "scale": 1.0},
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 120, "scale": 100.0},
        "fade":  {"label": "Fade",  "min": 40, "max": 98,  "default": 76,  "scale": 100.0},
    }

    def __init__(self, bolts: int = 2, speed: float = 1.2, fade: float = 0.76):
        self.bolts = bolts
        self.speed = speed
        self.fade = fade
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)
        self._active: list[dict] = []
        self._cooldown = 0.0

    def reset(self):
        self._buf[:] = 0
        self._active.clear()
        self._cooldown = 0.0

    def _make_path(self):
        x = random.randint(2, COLS - 3)
        path = []
        for r in range(ROWS):
            if random.random() < 0.72:
                x += random.choice([-1, 0, 0, 1])
            if random.random() < 0.18:
                x += random.choice([-2, 2])
            x = max(0, min(COLS - 1, x))
            path.append((r, x))
        branches = []
        for r, c in path[2:-2]:
            if random.random() < 0.22:
                length = random.randint(2, 5)
                side = random.choice([-1, 1])
                b = []
                rr, cc = r, c
                for _ in range(length):
                    rr += random.choice([0, 1])
                    cc += side * random.choice([1, 1, 2])
                    if 0 <= rr < ROWS and 0 <= cc < COLS:
                        b.append((rr, cc))
                if b:
                    branches.append(b)
        return path, branches

    def _spawn_strike(self):
        for _ in range(max(1, int(self.bolts))):
            path, branches = self._make_path()
            self._active.append({
                "path": path,
                "branches": branches,
                "phase": "pre",
                "t": 0.0,
                "reveal": 0,
                "echoes": 0,
            })

    def _paint_cell(self, frame, r, c, bri):
        if 0 <= r < ROWS and 0 <= c < COLS:
            frame[r, c] = max(frame[r, c], bri)
        for dr, dc, scale in ((-1,0,0.28),(1,0,0.35),(0,-1,0.22),(0,1,0.22)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < ROWS and 0 <= cc < COLS:
                frame[rr, cc] = max(frame[rr, cc], bri * scale)

    def tick(self, dt: float) -> list[int]:
        eff_dt = dt * self.speed
        self._buf *= max(0.40, min(0.98, self.fade))

        if not self._active:
            self._cooldown -= eff_dt
            if self._cooldown <= 0:
                self._spawn_strike()
                self._cooldown = random.uniform(0.7, 2.4)

        dead = []
        for i, st in enumerate(self._active):
            st["t"] += eff_dt
            path = st["path"]

            # Top-to-bottom strike build: reveal more rows every tick.
            if st["phase"] == "pre":
                # dim sky pulse before the bolt
                self._buf += np.random.uniform(0, 10, (ROWS, COLS))
                if st["t"] >= 0.10:
                    st["phase"] = "strike"
                    st["t"] = 0.0
                    st["reveal"] = 0

            elif st["phase"] == "strike":
                st["reveal"] = min(ROWS, st["reveal"] + max(1, int(3 * self.speed)))
                for r, c in path[:st["reveal"]]:
                    self._paint_cell(self._buf, r, c, 255)
                # branches lag behind the main strike so it crawls down, not just appears
                for b in st["branches"]:
                    if b and b[0][0] < st["reveal"]:
                        for r, c in b:
                            self._paint_cell(self._buf, r, c, 150)
                if st["reveal"] >= ROWS:
                    st["phase"] = "echo"
                    st["t"] = 0.0
                    st["echoes"] = 0

            elif st["phase"] == "echo":
                # ba BOOM ba ba ba: short dim re-strikes after the main hit
                if st["t"] >= 0.08:
                    st["t"] = 0.0
                    st["echoes"] += 1
                    bri = 150 if st["echoes"] == 1 else 85
                    for r, c in path:
                        if random.random() < 0.72:
                            self._paint_cell(self._buf, r, c, bri)
                    for b in st["branches"]:
                        for r, c in b:
                            if random.random() < 0.45:
                                self._paint_cell(self._buf, r, c, bri * 0.55)
                    if st["echoes"] >= 3:
                        dead.append(i)

        for i in reversed(dead):
            self._active.pop(i)

        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))

# ═════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════
# Comment out any effects here that you would like to hide from the main select list
# This will allow the view to stay functional and clean. Ex. "PotatoEffect," --> "#     PotatoEffect,"

ALL_EFFECTS: list[type[BaseEffect]] = [
#    PulseEffect,
    MatrixRainEffect,
    MatrixRainEffectV2, 
    RainEffect,
    WipeEffect,
    PlasmaEffect,
#    NoiseEffect,
    ScanEffect,
    StarfieldEffect,
    CometEffect,
    RippleEffect,
    HelixEffect,
    FireworksEffect,
    LightningEffect,
    BounceEffect,
    WaveEffect,
    SnakeEffect,
    ClockEffect,
#    TypingEffect,
#    AudioVisualizer,  # moved to dedicated Audio tab
    FireEffect,
    MetaballsEffect,
#    GameOfLifeEffect,
]

EFFECT_NAMES: list[str] = [e.name for e in ALL_EFFECTS]


def make_effect(name: str) -> BaseEffect:
    for cls in ALL_EFFECTS:
        if cls.name == name:
            return cls()
    raise ValueError(f"Unknown effect: {name!r}")