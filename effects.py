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
# Matrix Rain V2  —  8 directions 
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
        "bounce":    {"label": "Bounce",    "min": 0,  "max": 1,   "default": 0,   "scale": 1.0,
                      "display": {0: "Wrap", 1: "Bounce"}},
    }

    def __init__(self, speed: float = 1.0, width: int = 5, direction: int = 1, bounce: int = 0):
        self.speed     = speed
        self.width     = width
        self.direction = direction
        self.bounce    = bounce
        self._t        = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        d     = int(self.direction) % 4
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        if d in (0, 1):
            length = COLS
            raw    = self._t * 0.5 * length
            if int(self.bounce):
                t_mod = raw % (2 * length)
                pos   = t_mod if t_mod <= length else 2 * length - t_mod
            else:
                pos = raw % (length * 2)
            if d == 0:
                pos = (length * 2) - pos
            for c in range(COLS):
                dist = min(abs(c - pos), abs(c - (pos - length * 2)))
                if dist < self.width:
                    frame[:, c] = int(255 * (1 - dist / max(1, self.width)))
        else:
            length = ROWS
            raw    = self._t * 0.5 * length
            if int(self.bounce):
                t_mod = raw % (2 * length)
                pos   = t_mod if t_mod <= length else 2 * length - t_mod
            else:
                pos = raw % (length * 2)
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
        "bounce":    {"label": "Bounce",    "min": 0,  "max": 1,   "default": 0,   "scale": 1.0,
                      "display": {0: "Wrap", 1: "Bounce"}},
    }

    def __init__(self, speed: float = 1.0, direction: int = 1, bounce: int = 0):
        self.speed     = speed
        self.direction = direction
        self.bounce    = bounce
        self._t        = 0.0

    def reset(self):
        self._t = 0.0

    @staticmethod
    def _tri(t: float, length: int) -> int:
        """Triangle wave: 0 → length-1 → 0 → …"""
        m = length - 1
        if m <= 0:
            return 0
        t_mod = t % (2 * m)
        return int(t_mod) if t_mod <= m else int(2 * m - t_mod)

    def tick(self, dt: float) -> list[int]:
        self._t += dt * self.speed
        d     = int(self.direction) % 4
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        if d in (0, 1):
            raw = self._t * 10
            col = self._tri(raw, COLS) if int(self.bounce) else int(raw) % COLS
            if d == 0:
                col = COLS - 1 - col
            for dc, bri in ((0, 255), (-1, 120), (1, 120)):
                c = col + dc
                if 0 <= c < COLS:
                    frame[:, c] = bri
        else:
            raw = self._t * 6
            row = self._tri(raw, ROWS) if int(self.bounce) else int(raw) % ROWS
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

# 4-wide × 7-tall pixel font.  Bit 3 = leftmost column of the glyph.
_CLOCK_FONT = {
    "0": [0b0110, 0b1001, 0b1001, 0b1001, 0b1001, 0b1001, 0b0110],
    "1": [0b0100, 0b1100, 0b0100, 0b0100, 0b0100, 0b0100, 0b1110],
    "2": [0b0110, 0b1001, 0b0001, 0b0010, 0b0100, 0b1000, 0b1111],
    "3": [0b0111, 0b0001, 0b0001, 0b0111, 0b0001, 0b0001, 0b0111],
    "4": [0b1001, 0b1001, 0b1001, 0b1111, 0b0001, 0b0001, 0b0001],
    "5": [0b1111, 0b1000, 0b1000, 0b1110, 0b0001, 0b0001, 0b1111],
    "6": [0b0110, 0b1000, 0b1000, 0b1110, 0b1001, 0b1001, 0b0110],
    "7": [0b1111, 0b0001, 0b0001, 0b0010, 0b0010, 0b0100, 0b0100],
    "8": [0b0110, 0b1001, 0b1001, 0b0110, 0b1001, 0b1001, 0b0110],
    "9": [0b0110, 0b1001, 0b1001, 0b0111, 0b0001, 0b1001, 0b0110],
}
# 2-wide colon glyph (bit 1 = left dot column)
_CLOCK_COLON = [0b00, 0b00, 0b10, 0b00, 0b10, 0b00, 0b00]

# ── Extended glyph set for ScrollTextEffect ──────────────────────────
# Same 4-wide × 7-tall format.  Lowercase is mapped to uppercase at render time.
_CLOCK_FONT.update({
    # ── Letters ──────────────────────────────────────────────────────
    "A": [0b0110, 0b1001, 0b1001, 0b1111, 0b1001, 0b1001, 0b1001],
    "B": [0b1110, 0b1001, 0b1001, 0b1110, 0b1001, 0b1001, 0b1110],
    "C": [0b0110, 0b1000, 0b1000, 0b1000, 0b1000, 0b1000, 0b0110],
    "D": [0b1110, 0b1001, 0b1001, 0b1001, 0b1001, 0b1001, 0b1110],
    "E": [0b1111, 0b1000, 0b1000, 0b1110, 0b1000, 0b1000, 0b1111],
    "F": [0b1111, 0b1000, 0b1000, 0b1110, 0b1000, 0b1000, 0b1000],
    "G": [0b0110, 0b1000, 0b1000, 0b1011, 0b1001, 0b1001, 0b0110],
    "H": [0b1001, 0b1001, 0b1001, 0b1111, 0b1001, 0b1001, 0b1001],
    "I": [0b0110, 0b0010, 0b0010, 0b0010, 0b0010, 0b0010, 0b0110],
    "J": [0b0011, 0b0001, 0b0001, 0b0001, 0b1001, 0b1001, 0b0110],
    "K": [0b1001, 0b1010, 0b1100, 0b1000, 0b1100, 0b1010, 0b1001],
    "L": [0b1000, 0b1000, 0b1000, 0b1000, 0b1000, 0b1000, 0b1111],
    "M": [0b1001, 0b1101, 0b1011, 0b1001, 0b1001, 0b1001, 0b1001],
    "N": [0b1001, 0b1101, 0b1011, 0b1001, 0b1001, 0b1001, 0b1001],  # same as M at 4px, acceptable
    "O": [0b0110, 0b1001, 0b1001, 0b1001, 0b1001, 0b1001, 0b0110],
    "P": [0b1110, 0b1001, 0b1001, 0b1110, 0b1000, 0b1000, 0b1000],
    "Q": [0b0110, 0b1001, 0b1001, 0b1001, 0b1011, 0b1010, 0b0111],
    "R": [0b1110, 0b1001, 0b1001, 0b1110, 0b1100, 0b1010, 0b1001],
    "S": [0b0111, 0b1000, 0b1000, 0b0110, 0b0001, 0b0001, 0b1110],
    "T": [0b1111, 0b0100, 0b0100, 0b0100, 0b0100, 0b0100, 0b0100],
    "U": [0b1001, 0b1001, 0b1001, 0b1001, 0b1001, 0b1001, 0b0110],
    "V": [0b1001, 0b1001, 0b1001, 0b0110, 0b0110, 0b0010, 0b0010],
    "W": [0b1001, 0b1001, 0b1001, 0b1001, 0b1111, 0b1011, 0b1101],
    "X": [0b1001, 0b1001, 0b0110, 0b0100, 0b0110, 0b1001, 0b1001],
    "Y": [0b1001, 0b1001, 0b0110, 0b0100, 0b0100, 0b0100, 0b0100],
    "Z": [0b1111, 0b0001, 0b0010, 0b0100, 0b1000, 0b1000, 0b1111],
    # ── Punctuation ───────────────────────────────────────────────────
    " ": [0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b0000],
    "!": [0b0100, 0b0100, 0b0100, 0b0100, 0b0100, 0b0000, 0b0100],
    ".": [0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b0100],
    ",": [0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b0100, 0b0010],
    "-": [0b0000, 0b0000, 0b0000, 0b1110, 0b0000, 0b0000, 0b0000],
    "_": [0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b0000, 0b1111],
    "?": [0b0110, 0b1001, 0b0001, 0b0010, 0b0100, 0b0000, 0b0100],
    "*": [0b0000, 0b1010, 0b0100, 0b1110, 0b0100, 0b1010, 0b0000],
    "#": [0b1010, 0b1111, 0b1010, 0b1010, 0b1111, 0b1010, 0b0000],
    "/": [0b0001, 0b0001, 0b0010, 0b0100, 0b1000, 0b1000, 0b0000],
    "<": [0b0010, 0b0100, 0b1000, 0b0100, 0b0010, 0b0001, 0b0000],
    ">": [0b1000, 0b0100, 0b0010, 0b0100, 0b1000, 0b0000, 0b0000],
})


class ClockEffect(BaseEffect):
    """
    HH:MM clock with a 4×7 pixel font.

    The diagonal LED mask means the left edge of the display is cut off on
    lower rows.  Default x_offset=0 positions the clock so all pixels at
    rows 1-7 are valid on the ROG Strix Flare II Animate.  Move X to taste.

    Layout at default:
      x_start = 14  →  rightmost pixel at col 35  (within COLS=37)
      row_start = 1  →  font occupies rows 1-7  (bottom row needs col ≥14 ✓)
    """
    name = "Clock"
    PARAMS = {
        "hour_24":  {"label": "Format",  "min": 0, "max": 1,   "default": 1, "scale": 1.0,
                     "display": {0: "12h", 1: "24h"}},
        "blink":    {"label": "Blink :", "min": 0, "max": 1,   "default": 1, "scale": 1.0,
                     "display": {0: "Off", 1: "On"}},
        "x_offset": {"label": "Move X",  "min": -14, "max": 20, "default": 0, "scale": 1.0},
    }

    _CHAR_W   = 4
    _COLON_W  = 2
    _GAP      = 1
    _H        = 7
    _X_BASE   = 14   # ensures row 7 (needs col≥14) is fully unmasked at default

    def __init__(self, hour_24: int = 1, blink: int = 1, x_offset: int = 0):
        self.hour_24  = hour_24
        self.blink    = blink
        self.x_offset = x_offset
        self._t       = 0.0

    def reset(self):
        self._t = 0.0

    def tick(self, dt: float) -> list[int]:
        self._t += dt
        colon_lit = (not int(self.blink)) or (int(self._t * 2) % 2 == 0)

        now = time.localtime()
        if int(self.hour_24):
            h = now.tm_hour
        else:
            h = now.tm_hour % 12 or 12

        h_str = f"{h:02d}"
        m_str = f"{now.tm_min:02d}"

        x_start   = self._X_BASE + int(self.x_offset)
        row_start = (ROWS - self._H) // 2 - 1   # rows 1-7 on a 12-row display
        row_start = max(0, row_start)
        frame     = np.zeros((ROWS, COLS), dtype=np.uint8)

        def _draw_char(glyph: list[int], x: int, width: int):
            for ri, bits in enumerate(glyph):
                r = row_start + ri
                if not (0 <= r < ROWS):
                    continue
                for bi in range(width):
                    c = x + bi
                    if 0 <= c < COLS and (bits >> (width - 1 - bi)) & 1:
                        frame[r, c] = 255
            return x + width + self._GAP

        x = x_start
        x = _draw_char(_CLOCK_FONT[h_str[0]], x, self._CHAR_W)
        x = _draw_char(_CLOCK_FONT[h_str[1]], x, self._CHAR_W)
        x = _draw_char(_CLOCK_COLON if colon_lit else [0]*self._H, x, self._COLON_W)
        x = _draw_char(_CLOCK_FONT[m_str[0]], x, self._CHAR_W)
        x = _draw_char(_CLOCK_FONT[m_str[1]], x, self._CHAR_W)

        return self._emit(frame)



# ─────────────────────────────────────────────────────────────────────
# Scrolling Text Marquee
# ─────────────────────────────────────────────────────────────────────

class ScrollTextEffect(BaseEffect):
    """
    Scrolls a text message across the display using the 4×7 clock font.
    Lowercase is automatically uppercased; unknown characters become spaces.
    The 'message' attr is a plain string — set it live via set_effect_param.
    """
    name = "Scroll Text"
    PARAMS = {
        "message":  {"label": "Message",  "type": "text",  "default": "POLYWOLLYWIN"},
        "speed":    {"label": "Speed",    "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "loop_gap": {"label": "Gap",      "min": 5,  "max": 80,  "default": 20,  "scale": 1.0},
    }

    _CHAR_W = 4
    _GAP    = 1
    _H      = 7

    def __init__(self, message: str = "POLYWOLLYWIN", speed: float = 1.0, loop_gap: int = 20):
        self.message  = message
        self.speed    = speed
        self.loop_gap = loop_gap
        self._x       = float(COLS)   # current scroll position (pixels, left edge of text)
        self._row_start = max(0, (ROWS - self._H) // 2 - 1)  # vertically centred, rows 1-7

    def reset(self):
        self._x = float(COLS)

    def _text_width(self, text: str) -> int:
        if not text:
            return 0
        return len(text) * (self._CHAR_W + self._GAP) - self._GAP

    def tick(self, dt: float) -> list[int]:
        text = str(self.message).upper()
        if not text:
            text = " "

        tw   = self._text_width(text)
        wrap = tw + int(self.loop_gap)

        self._x -= dt * self.speed * 20.0   # 20 px/s at speed=1.0
        if self._x < -tw:
            self._x += wrap + COLS

        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        rs    = self._row_start

        for i, ch in enumerate(text):
            glyph = _CLOCK_FONT.get(ch, _CLOCK_FONT.get(" ", [0] * self._H))
            char_x_start = int(self._x) + i * (self._CHAR_W + self._GAP)
            for bi in range(self._CHAR_W):
                c = char_x_start + bi
                if c < 0 or c >= COLS:
                    continue
                for ri, bits in enumerate(glyph):
                    r = rs + ri
                    if 0 <= r < ROWS and (bits >> (self._CHAR_W - 1 - bi)) & 1:
                        frame[r, c] = 255

        return self._emit(frame)


# ─────────────────────────────────────────────────────────────────────
# Keyboard React  (per-key LED flash mapped to keyboard layout)
# ─────────────────────────────────────────────────────────────────────

# Maps each key character to (matrix_row, matrix_col).
# Positions chosen so every cell satisfies MASK: col >= row*2.
#   Numbers  → matrix row 2  (mask: col >= 4)
#   QWERTY   → matrix row 4  (mask: col >= 8)
#   ASDF     → matrix row 6  (mask: col >= 12)
#   ZXCV     → matrix row 8  (mask: col >= 16)
_KEY_POS: dict[str, tuple[int, int]] = {
    # Numbers
    "1": (2,  4), "2": (2,  7), "3": (2, 10), "4": (2, 13),
    "5": (2, 16), "6": (2, 19), "7": (2, 22), "8": (2, 25),
    "9": (2, 28), "0": (2, 31),
    # QWERTY
    "q": (4,  8), "w": (4, 11), "e": (4, 14), "r": (4, 17),
    "t": (4, 20), "y": (4, 23), "u": (4, 26), "i": (4, 29),
    "o": (4, 32), "p": (4, 35),
    # ASDF
    "a": (6, 12), "s": (6, 15), "d": (6, 18), "f": (6, 21),
    "g": (6, 24), "h": (6, 26), "j": (6, 28), "k": (6, 31), "l": (6, 33),
    # ZXCV
    "z": (8, 16), "x": (8, 19), "c": (8, 22), "v": (8, 24),
    "b": (8, 26), "n": (8, 29), "m": (8, 32),
}


class KeyboardReactEffect(BaseEffect):
    """
    Each key press lights the LED at that key's approximate physical position
    on the matrix, then fades out.

    • Normal key  → 180 brightness, 2-pixel glow radius
    • Capital (Shift held / Caps) → 255 brightness, 4-pixel glow radius, slower decay
    • Space  → full-width horizontal flash on row 10
    • Enter  → column burst on the far right
    • Backspace → column burst on the number-row far right

    Falls back to randomised column flashes (TypingEffect style) if pynput
    is unavailable.
    """
    name = "Keyboard React"
    PARAMS = {
        "decay":  {"label": "Decay",   "min": 60, "max": 97, "default": 82, "scale": 100.0},
        "glow":   {"label": "Glow",    "min": 1,  "max": 6,  "default": 2,  "scale": 1.0},
    }

    def __init__(self, decay: float = 0.82, glow: int = 2):
        self.decay = decay
        self.glow  = glow

        self._buf      = np.zeros((ROWS, COLS), dtype=np.float32)
        self._lock     = threading.Lock()
        self._listener = None
        self._demo     = False
        self._demo_t   = 0.0
        self._caps     = False   # track Caps Lock / Shift state

        try:
            from pynput import keyboard
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.start()
        except Exception:
            self._demo = True

    # ── key handling ──────────────────────────────────────────────────

    def _on_press(self, key):
        try:
            from pynput.keyboard import Key
            # Track shift/caps for brightness decision
            if key in (Key.shift, Key.shift_r, Key.caps_lock):
                self._caps = True
                return

            bri   = 255 if self._caps else 180
            glow  = int(self.glow) + (2 if self._caps else 0)

            if key == Key.space:
                self._flash_row(10, 28, bri, glow)
                return
            if key == Key.enter:
                self._flash_col(6, 35, bri, glow)
                return
            if key in (Key.backspace,):
                self._flash_col(2, 34, bri, glow)
                return

            ch = getattr(key, "char", None)
            if ch is None:
                return
            pos = _KEY_POS.get(ch.lower())
            if pos:
                r, c = pos
                # Uppercase = brighter + wider glow
                if ch.isupper():
                    bri  = 255
                    glow = int(self.glow) + 2
                self._flash_point(r, c, bri, glow)
        except Exception:
            pass

    def _on_release(self, key):
        try:
            from pynput.keyboard import Key
            if key in (Key.shift, Key.shift_r, Key.caps_lock):
                self._caps = False
        except Exception:
            pass

    def _flash_point(self, r: int, c: int, bri: float, radius: int):
        with self._lock:
            for dr in range(-radius, radius + 1):
                for dc in range(-radius * 2, radius * 2 + 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < ROWS and 0 <= cc < COLS and MASK_NP[rr, cc]:
                        dist = math.sqrt(dr ** 2 + (dc * 0.55) ** 2)
                        b    = bri * max(0.0, 1.0 - dist / max(1.0, radius))
                        self._buf[rr, cc] = max(self._buf[rr, cc], b)

    def _flash_row(self, r: int, center_c: int, bri: float, radius: int):
        """Horizontal flash — used for spacebar."""
        with self._lock:
            for cc in range(COLS):
                if MASK_NP[r, cc]:
                    dist = abs(cc - center_c) / max(1, COLS // 2)
                    b    = bri * max(0.0, 1.0 - dist)
                    self._buf[r, cc] = max(self._buf[r, cc], b)

    def _flash_col(self, r: int, c: int, bri: float, radius: int):
        """Vertical column burst — used for Enter / Backspace."""
        with self._lock:
            for rr in range(ROWS):
                if MASK_NP[rr, c]:
                    dist = abs(rr - r) / max(1, ROWS)
                    b    = bri * max(0.0, 1.0 - dist)
                    self._buf[rr, c] = max(self._buf[rr, c], b)

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    # ── tick ──────────────────────────────────────────────────────────

    def tick(self, dt: float) -> list[int]:
        if self._demo:
            self._demo_t += dt
            if self._demo_t >= 0.22:
                self._demo_t = 0.0
                ch = random.choice(list(_KEY_POS.keys()))
                r, c = _KEY_POS[ch]
                bri  = random.choice([180, 255])
                self._flash_point(r, c, bri, int(self.glow))

        with self._lock:
            self._buf *= max(0.50, min(0.98, float(self.decay)))
            out = np.clip(self._buf, 0, 255).astype(np.uint8)

        return self._emit(out)
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


class _SharedAudioCapture:
    """One shared desktop-audio capture engine for all audio effects.

    Important: PolyWollyWin creates effect objects for previews/UI work. If each
    object opens Stereo Mix, Realtek/PortAudio can click, reject the device, or
    return invalid-device errors. This singleton opens the selected input once
    and every Audio/KITT Audio effect reads the same buffer.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._buf: Optional[np.ndarray] = None
        self._last_audio_t = 0.0
        self._samplerate = 44100
        self._stream = None
        self._started = False
        self._failed = False
        self._mode = "demo"
        self._debug_last = 0.0

    def log(self, msg: str):
        line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            with open("polywolly_audio_debug.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def start(self):
        if self._started or self._failed:
            return
        self._started = True

        try:
            import os
            import sounddevice as sd
        except Exception as e:
            self._failed = True
            self._mode = "demo"
            self.log(f"Audio unavailable, sounddevice import failed: {e!r}")
            return

        try:
            devices = list(sd.query_devices())
        except Exception as e:
            self._failed = True
            self._mode = "demo"
            self.log(f"Audio unavailable, query_devices failed: {e!r}")
            return

        candidates: list[int] = []

        # Manual override wins. Examples:
        #   set POLYWOLLY_AUDIO_DEVICE=17
        #   set POLYWOLLY_AUDIO_DEVICE=Stereo Mix
        forced = os.environ.get("POLYWOLLY_AUDIO_DEVICE", "").strip()
        if forced:
            try:
                idx = int(forced)
                if idx not in candidates:
                    candidates.append(idx)
            except Exception:
                needle = forced.lower()
                for idx, dev in enumerate(devices):
                    if needle in str(dev.get("name", "")).lower() and idx not in candidates:
                        candidates.append(idx)

        preferred_names = ("stereo mix", "what u hear", "what you hear", "wave out mix")
        for idx, dev in enumerate(devices):
            try:
                name = str(dev.get("name", "")).lower()
                max_in = int(dev.get("max_input_channels", 0) or 0)
                if max_in > 0 and any(x in name for x in preferred_names) and idx not in candidates:
                    candidates.append(idx)
            except Exception:
                pass

        try:
            default_in = int(sd.default.device[0])
            if default_in >= 0 and default_in not in candidates:
                candidates.append(default_in)
        except Exception:
            pass

        if not candidates:
            self._failed = True
            self._mode = "demo"
            self.log("Audio unavailable, no input candidates found")
            return

        last_error = None
        for idx in candidates:
            try:
                if idx < 0 or idx >= len(devices):
                    self.log(f"Audio skip device {idx}: index outside current device list")
                    continue
                dev = devices[idx]
                name = str(dev.get("name", ""))
                max_in = int(dev.get("max_input_channels", 0) or 0)
                if max_in <= 0:
                    self.log(f"Audio skip device {idx}: no input channels, name={name}")
                    continue

                channels = max(1, min(2, max_in))
                # Your working command used 44100 against Stereo Mix, so keep
                # Stereo Mix at 44100 instead of trusting flaky driver metadata.
                samplerate = 44100 if "stereo mix" in name.lower() else int(float(dev.get("default_samplerate", 44100) or 44100))
                blocksize = 2048
                self._samplerate = samplerate

                def _callback(indata, frames, time_info, status):
                    try:
                        data = np.asarray(indata, dtype=np.float32)
                        if data.ndim == 2:
                            data = data.mean(axis=1)
                        else:
                            data = data.reshape(-1)
                        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
                        rms = float(np.sqrt(np.mean(data * data))) if data.size else 0.0
                        now = time.monotonic()
                        with self._lock:
                            self._buf = data.copy()
                            if rms > 0.00002:
                                self._last_audio_t = now
                            if now - self._debug_last > 2.0:
                                self._debug_last = now
                                self.log(f"Audio rms={rms:.6f}, mode={self._mode}")
                    except Exception as e:
                        self.log(f"Audio callback error: {e!r}")

                self._stream = sd.InputStream(
                    device=idx,
                    channels=channels,
                    samplerate=samplerate,
                    blocksize=blocksize,
                    latency="high",
                    dtype="float32",
                    callback=_callback,
                )
                self._stream.start()
                self._mode = "stereo_mix" if "stereo mix" in name.lower() else "input"
                self.log(f"Audio opened: mode={self._mode}, device={idx}, name={name}, rate={samplerate}, channels={channels}, blocksize={blocksize}")
                return
            except Exception as e:
                last_error = e
                self.log(f"Audio failed device {idx}: {e!r}")
                try:
                    if self._stream is not None:
                        self._stream.stop()
                        self._stream.close()
                except Exception:
                    pass
                self._stream = None

        self._failed = True
        self._mode = "demo"
        self.log(f"Audio failed, no usable device opened. Last error: {last_error!r}")

    def get(self):
        self.start()
        with self._lock:
            raw = None if self._buf is None else self._buf.copy()
            last = self._last_audio_t
            sr = self._samplerate
            mode = self._mode
        return raw, last, sr, mode


_SHARED_AUDIO_CAPTURE = _SharedAudioCapture()


class AudioVisualizer(BaseEffect):
    name = "Audio"
    PARAMS = {
        "sensitivity": {"label": "Sensitivity", "min": 100, "max": 3000, "default": 550,  "scale": 100.0},
        "boost":       {"label": "Boost",       "min": 100, "max": 5000, "default": 850,  "scale": 100.0},
        "falloff":     {"label": "Falloff",     "min": 50,  "max": 98,   "default": 88,   "scale": 100.0},
        "floor":       {"label": "Noise Floor", "min": 1,   "max": 100,  "default": 12,   "scale": 10000.0},
    }

    def __init__(self, sensitivity: float = 5.5, boost: float = 8.5,
                 falloff: float = 0.88, floor: float = 0.0012):
        self.sensitivity = sensitivity
        self.boost = boost
        self.falloff = falloff
        self.floor = floor
        self._bars  = np.zeros(COLS, dtype=np.float32)
        self._peaks = np.zeros(COLS, dtype=np.float32)
        self._lock   = threading.Lock()
        self._buf: Optional[np.ndarray] = None
        self._last_audio_t = 0.0
        self._demo_t = 0.0
        self._mode = "demo"
        self._samplerate = 44100
        self._agc = 0.03
        self._spec_agc = np.full(COLS, 0.02, dtype=np.float32)

        self._col_rows = [
            [r for r in range(ROWS - 1, -1, -1) if MASK_NP[r, c]]
            for c in range(COLS)
        ]

    def stop(self):
        pass

    def _paint_bar(self, frame: np.ndarray, col: int, height: float, peak: float = 0.0):
        rows = self._col_rows[col]
        if not rows:
            return

        h = int(round(max(0.0, min(float(len(rows)), height))))
        for i, r in enumerate(rows[:h]):
            # Dimmer than before, so tiny spectral movement does not look maxed out.
            bri = int(65 + 150 * (1.0 - i / max(1, len(rows))))
            frame[r, col] = max(frame[r, col], bri)

        pr = int(round(max(0.0, min(float(len(rows) - 1), peak))))
        if 0 <= pr < len(rows) and height > 0.25:
            frame[rows[pr], col] = max(frame[rows[pr], col], 225)

    def _demo_frame(self, dt: float) -> list[int]:
        self._demo_t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        for c in range(COLS):
            rows = self._col_rows[c]
            if not rows:
                continue
            wave = math.sin(self._demo_t * 3.0 + c * 0.30) * 0.5 + 0.5
            h = 1 + wave * max(1, len(rows) - 1) * 0.45
            self._paint_bar(frame, c, h)
        return self._emit(frame)

    def tick(self, dt: float) -> list[int]:
        raw, last_audio_t, samplerate, mode = _SHARED_AUDIO_CAPTURE.get()
        self._last_audio_t = last_audio_t
        self._samplerate = samplerate
        self._mode = mode

        if raw is None or len(raw) < 128:
            return self._demo_frame(dt)

        raw = np.nan_to_num(raw.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        raw -= float(np.mean(raw))
        rms = float(np.sqrt(np.mean(raw * raw)))
        floor = max(0.00001, float(self.floor))

        if rms < floor and (time.monotonic() - self._last_audio_t) > 0.50:
            decay = max(0.50, min(0.98, float(self.falloff)))
            self._bars *= decay
            self._peaks *= 0.94
            frame = np.zeros((ROWS, COLS), dtype=np.uint8)
            for c in range(COLS):
                self._paint_bar(frame, c, self._bars[c], self._peaks[c])
            return self._emit(frame)

        active = max(0.0, rms - floor)
        self._agc = max(self._agc * 0.985, active * 3.0, 0.006)
        norm = np.clip(raw / self._agc, -1.0, 1.0)

        window = np.hanning(len(norm)).astype(np.float32)
        fft = np.abs(np.fft.rfft(norm * window))
        freqs = np.fft.rfftfreq(len(norm), d=1.0 / max(8000, self._samplerate))
        if len(fft) < 16:
            return self._demo_frame(dt)

        fft[:3] = 0

        # Deliberately skip sub-bass. The old version added bass back into
        # every column, which made the whole matrix look full all the time.
        low = 180.0
        high = min(12000.0, self._samplerate / 2.0)
        edges = np.geomspace(low, high, COLS + 1)

        vals = np.zeros(COLS, dtype=np.float32)
        for c in range(COLS):
            mask = (freqs >= edges[c]) & (freqs < edges[c + 1])
            if np.any(mask):
                vals[c] = float(np.sqrt(np.mean(fft[mask] * fft[mask])))

        self._spec_agc = np.maximum(self._spec_agc * 0.992, vals * 2.5 + 0.0005)
        vals = vals / np.maximum(self._spec_agc, 0.0005)
        vals = vals * max(0.1, self.boost) * max(0.1, self.sensitivity) * 0.018
        vals = np.clip(np.log1p(vals * 1.8) / 1.8, 0.0, 1.0)

        # Gate tiny changes. This keeps the top few rows from flickering from
        # microscopic noise.
        vals[vals < 0.08] = 0.0
        vals = vals ** 1.35

        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        decay = max(0.50, min(0.98, float(self.falloff)))
        for c, val in enumerate(vals):
            rows = self._col_rows[c]
            if not rows:
                continue
            target_h = val * len(rows) * 0.86
            self._bars[c] = max(self._bars[c] * decay, target_h)
            self._peaks[c] = max(self._peaks[c] * 0.945, self._bars[c])
            self._paint_bar(frame, c, self._bars[c], self._peaks[c])

        return self._emit(frame)

# ─────────────────────────────────────────────────────────────────────
# Additional shared-capture audio visualizers
# ─────────────────────────────────────────────────────────────────────

class _AudioReactiveBase(AudioVisualizer):
    """
    Broadband audio analysis.

    Low, low-mid, high-mid, and treble bands are normalized independently and
    averaged so bass-heavy instrumentals and high soprano vocals both register.
    """

    def __init__(self, sensitivity: float = 1.0,
                 falloff: float = 0.84, x_pos: float = 50.0,
                 y_pos: float = 50.0, **_kwargs):
        super().__init__(
            sensitivity=sensitivity,
            boost=1.0,
            falloff=falloff,
            floor=0.0,
        )
        self.x_pos = x_pos
        self.y_pos = y_pos
        self._level = 0.0
        self._beat = 0.0
        self._phase = 0.0
        self._last_raw = None
        self._beat_gate = False

        self._band_agc = np.full(4, 0.0025, dtype=np.float32)
        self._wave_agc = 0.0035
        self._broad_avg = 0.08
        self._prev_bands = np.zeros(4, dtype=np.float32)
        self._activity = 0.0

    def apply_controls(self, sensitivity: float, falloff: float, **extra):
        self.sensitivity = float(sensitivity)
        self.falloff = float(falloff)
        for attr, value in extra.items():
            if hasattr(self, attr):
                setattr(self, attr, value)

    @staticmethod
    def _band_rms(fft: np.ndarray, freqs: np.ndarray,
                  lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            return 0.0
        vals = fft[mask]
        return float(np.sqrt(np.mean(vals * vals)))

    def _audio_metrics(self, dt: float) -> tuple[float, float]:
        """
        Return continuous activity and transient emphasis.

        The continuous activity follows the same normalized waveform behavior
        that makes Oscilloscope responsive, while the FFT bands ensure bass,
        instruments, vocals, soprano, and treble all contribute equally.
        """
        raw, last_audio_t, samplerate, mode = _SHARED_AUDIO_CAPTURE.get()
        self._last_audio_t = last_audio_t
        self._samplerate = samplerate
        self._mode = mode
        self._phase += dt
        self._last_raw = raw

        decay = max(0.50, min(0.985, float(self.falloff)))

        if raw is None or len(raw) < 256:
            self._activity *= decay
            self._level = self._activity
            self._beat *= 0.58
            return self._level, self._beat

        data = np.nan_to_num(
            raw.astype(np.float32), nan=0.0,
            posinf=0.0, neginf=0.0,
        )
        data -= float(np.mean(data))

        # Oscilloscope-style waveform activity. The rolling AGC makes normal
        # program material strongly visible at sensitivity 1.0.
        wave_peak = float(np.percentile(np.abs(data), 90))
        self._wave_agc = max(self._wave_agc * 0.997, wave_peak * 1.35)
        wave_norm = float(np.clip(
            wave_peak / max(0.00035, self._wave_agc), 0.0, 1.25
        ))

        window = np.hanning(len(data)).astype(np.float32)
        fft = np.abs(np.fft.rfft(data * window))
        freqs = np.fft.rfftfreq(
            len(data), d=1.0 / max(8000, int(samplerate))
        )
        nyquist = max(4000.0, samplerate / 2.0)

        bands = np.array([
            self._band_rms(fft, freqs, 35.0, 250.0),
            self._band_rms(fft, freqs, 250.0, 1600.0),
            self._band_rms(fft, freqs, 1600.0, 5000.0),
            self._band_rms(fft, freqs, 5000.0, min(16000.0, nyquist)),
        ], dtype=np.float32)

        self._band_agc = np.maximum(
            self._band_agc * 0.997,
            bands * 1.45,
        )
        normalized = np.clip(
            bands / np.maximum(self._band_agc, 0.00020),
            0.0, 1.30,
        )

        broadband = float(np.mean(normalized))
        sensitivity = max(0.20, min(4.0, float(self.sensitivity)))

        # Waveform carries the same response feel as Oscilloscope. Broadband
        # energy fills in material concentrated in any frequency range.
        raw_activity = max(
            wave_norm * 0.88,
            broadband * 0.82,
            (wave_norm * 0.58 + broadband * 0.42),
        )
        target = float(np.clip(raw_activity * sensitivity, 0.0, 1.0))

        positive_flux = np.maximum(0.0, normalized - self._prev_bands)
        flux = float(np.mean(positive_flux))
        self._prev_bands = normalized

        self._broad_avg = self._broad_avg * 0.965 + raw_activity * 0.035
        relative = raw_activity / max(0.035, self._broad_avg)
        transient = max(
            0.0,
            (relative - 1.015) / 0.62,
            flux * 2.1,
        )
        pulse = float(np.clip(transient * sensitivity, 0.0, 1.0))

        # Fast rise, controlled fall. Continuous activity never waits for a beat.
        self._activity = max(target, self._activity * decay)
        self._level = self._activity
        self._beat = max(pulse, self._beat * 0.54)
        return self._level, self._beat

    def _new_beat(self, beat: float, threshold: float = 0.22) -> bool:
        active = beat >= threshold
        fired = active and not self._beat_gate
        if not active and beat < threshold * 0.55:
            self._beat_gate = False
        elif active:
            self._beat_gate = True
        return fired


class SpectrumAudioVisualizer(_AudioReactiveBase):
    """Broadband spectrum with bright leaders and dim falling trails."""
    name = "Spectrum Bars"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bars = np.zeros(COLS, dtype=np.float32)
        self._leaders = np.zeros(COLS, dtype=np.float32)
        self._bar_agc = np.full(COLS, 0.0025, dtype=np.float32)

    def tick(self, dt: float) -> list[int]:
        level, _pulse = self._audio_metrics(dt)
        raw = self._last_raw
        targets = np.zeros(COLS, dtype=np.float32)

        if raw is not None and len(raw) >= 256:
            data = np.nan_to_num(
                raw.astype(np.float32), nan=0.0,
                posinf=0.0, neginf=0.0,
            )
            data -= float(np.mean(data))
            window = np.hanning(len(data)).astype(np.float32)
            fft = np.abs(np.fft.rfft(data * window))
            freqs = np.fft.rfftfreq(
                len(data), d=1.0 / max(8000, int(self._samplerate))
            )

            lo = 35.0
            hi = min(16000.0, max(4000.0, self._samplerate / 2.0))
            edges = np.geomspace(lo, hi, COLS + 1)
            bands = np.zeros(COLS, dtype=np.float32)
            for i in range(COLS):
                mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
                if np.any(mask):
                    vals = fft[mask]
                    bands[i] = float(np.sqrt(np.mean(vals * vals)))

            self._bar_agc = np.maximum(
                self._bar_agc * 0.997,
                bands * 1.42,
            )
            normalized = np.clip(
                bands / np.maximum(self._bar_agc, 0.00020),
                0.0, 1.25,
            )
            targets = np.clip(
                normalized * max(0.20, float(self.sensitivity))
                * max(0.55, level),
                0.0, 1.0,
            )

        # Bars drop at normal falloff speed.
        bar_decay = max(0.35, min(0.965, float(self.falloff)))
        self._bars = np.maximum(targets, self._bars * bar_decay)

        # Leader rises immediately, but falls at roughly half the bar drop speed.
        leader_drop_per_second = 5.5 + (1.0 - float(self.falloff)) * 18.0
        falling = np.maximum(0.0, self._leaders - leader_drop_per_second * dt / ROWS)
        self._leaders = np.maximum(self._bars, falling)

        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        for c in range(COLS):
            height = int(round(self._bars[c] * (ROWS - 1)))
            if height > 0:
                top_row = ROWS - 1 - height
                # Dim trail/body below the bright active top.
                for r in range(top_row + 1, ROWS):
                    if MASK_NP[r, c]:
                        frame[r, c] = 105
                if 0 <= top_row < ROWS and MASK_NP[top_row, c]:
                    frame[top_row, c] = 225

            lead_row = ROWS - 1 - int(round(self._leaders[c] * (ROWS - 1)))
            if 0 <= lead_row < ROWS and MASK_NP[lead_row, c]:
                frame[lead_row, c] = 255

            # Two dim points behind the leader as it falls downward.
            for offset, bri in ((1, 105), (2, 55)):
                trail_row = lead_row - offset
                if 0 <= trail_row < ROWS and MASK_NP[trail_row, c]:
                    frame[trail_row, c] = max(frame[trail_row, c], bri)

        return self._emit(frame)


class AudioStarburstEffect(_AudioReactiveBase):
    """Beat-driven starbursts with adjustable origin."""
    name = "Center Starburst"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rr, self._cc = np.indices((ROWS, COLS), dtype=np.float32)
        self._bursts: list[dict] = []
        self._trail = np.zeros((ROWS, COLS), dtype=np.float32)
        self._event_timer = 0.0

    def _spawn(self, strength: float):
        cr = np.clip(float(self.y_pos), 0, 100) / 100.0 * (ROWS - 1)
        cc = np.clip(float(self.x_pos), 0, 100) / 100.0 * (COLS - 1)
        self._bursts.append({
            "radius": 0.0,
            "strength": max(0.25, strength),
            "cr": cr,
            "cc": cc,
            "rays": int(np.random.choice([6, 8, 10, 12])),
            "phase": float(np.random.uniform(0, math.tau)),
        })

    def tick(self, dt: float) -> list[int]:
        level, beat = self._audio_metrics(dt)
        self._event_timer += dt
        interval = max(0.045, 0.22 - level * 0.16)
        if beat > 0.16 or (level > 0.08 and self._event_timer >= interval):
            self._spawn(max(0.28, level, beat))
            self._event_timer = 0.0

        self._trail *= max(0.42, min(0.975, float(self.falloff)))
        keep = []

        for burst in self._bursts:
            burst["radius"] += dt * (5.0 + 15.0 * burst["strength"])
            dr = self._rr - burst["cr"]
            dc = (self._cc - burst["cc"]) * (ROWS / max(1.0, COLS))
            dist = np.sqrt(dr * dr + dc * dc)
            angle = np.arctan2(dr, dc)

            ring = np.exp(
                -((dist - burst["radius"]) ** 2) /
                max(0.18, 0.50 - burst["strength"] * 0.18)
            )
            rays = (
                0.18 +
                0.82 * np.maximum(
                    0.0,
                    np.cos(
                        angle * burst["rays"] + burst["phase"]
                    )
                ) ** 10
            )

            self._trail = np.maximum(
                self._trail,
                ring * rays * 255.0 * burst["strength"],
            )
            if burst["radius"] < ROWS * 1.8:
                keep.append(burst)

        self._bursts = keep
        return self._emit(np.clip(self._trail, 0, 255).astype(np.uint8))


class AudioCornerConvergenceEffect(_AudioReactiveBase):
    """
    Thin beat-triggered flame streams from all four corners toward an X/Y target.
    """
    name = "Corner Convergence"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._streams: list[dict] = []
        self._trail = np.zeros((ROWS, COLS), dtype=np.float32)
        self._event_timer = 0.0
        self._corners = [
            (0.0, 0.0),
            (0.0, float(COLS - 1)),
            (float(ROWS - 1), 0.0),
            (float(ROWS - 1), float(COLS - 1)),
        ]

    def _spawn(self, strength: float):
        target_r = (
            np.clip(float(self.y_pos), 0, 100) / 100.0 * (ROWS - 1)
        )
        target_c = (
            np.clip(float(self.x_pos), 0, 100) / 100.0 * (COLS - 1)
        )
        for corner_r, corner_c in self._corners:
            self._streams.append({
                "p": 0.0,
                "strength": max(0.30, strength),
                "r0": corner_r,
                "c0": corner_c,
                "r1": target_r,
                "c1": target_c,
                "phase": float(np.random.uniform(0, math.tau)),
            })

    def tick(self, dt: float) -> list[int]:
        level, beat = self._audio_metrics(dt)
        self._event_timer += dt
        interval = max(0.050, 0.20 - level * 0.145)
        if beat > 0.14 or (level > 0.08 and self._event_timer >= interval):
            self._spawn(max(0.30, level, beat))
            self._event_timer = 0.0

        self._trail *= max(0.40, min(0.97, float(self.falloff)))
        keep = []

        for stream in self._streams:
            stream["p"] += dt * (0.75 + 2.7 * stream["strength"])
            p = stream["p"]
            if p > 1.12:
                continue

            # Small flame-like sideways flicker while preserving convergence.
            flicker = math.sin(
                p * 18.0 + stream["phase"]
            ) * (0.45 + 0.55 * (1.0 - min(1.0, p)))

            r = stream["r0"] + (stream["r1"] - stream["r0"]) * min(1.0, p)
            c = stream["c0"] + (stream["c1"] - stream["c0"]) * min(1.0, p)

            dr = stream["r1"] - stream["r0"]
            dc = stream["c1"] - stream["c0"]
            length = max(1.0, math.hypot(dr, dc))
            # Perpendicular offset gives thin flames instead of a rigid X.
            r += (-dc / length) * flicker
            c += (dr / length) * flicker

            rr = int(round(r))
            cc = int(round(c))
            bri = 255.0 * stream["strength"] * max(0.25, 1.0 - abs(p - 0.82) * 0.45)

            for drr, dcc, scale in (
                (0, 0, 1.0),
                (-1, 0, 0.28),
                (1, 0, 0.28),
                (0, -1, 0.22),
                (0, 1, 0.22),
            ):
                r2, c2 = rr + drr, cc + dcc
                if (
                    0 <= r2 < ROWS and 0 <= c2 < COLS
                    and MASK_NP[r2, c2]
                ):
                    self._trail[r2, c2] = max(
                        self._trail[r2, c2], bri * scale
                    )

            keep.append(stream)

        self._streams = keep
        return self._emit(np.clip(self._trail, 0, 255).astype(np.uint8))


class AudioCenterWaveEffect(_AudioReactiveBase):
    """Signed oscilloscope trace across one horizontal baseline."""
    name = "Oscilloscope"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._points = np.zeros(COLS, dtype=np.float32)

    def tick(self, dt: float) -> list[int]:
        level, _beat = self._audio_metrics(dt)
        raw = self._last_raw

        target = np.zeros(COLS, dtype=np.float32)
        if raw is not None and len(raw) >= COLS:
            data = np.nan_to_num(
                raw.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0
            )
            data -= float(np.mean(data))

            # Average samples into columns while retaining signed waveform.
            chunks = np.array_split(data, COLS)
            target = np.array(
                [float(np.mean(chunk)) if len(chunk) else 0.0
                 for chunk in chunks],
                dtype=np.float32,
            )
            scale = max(
                0.0004,
                float(np.percentile(np.abs(target), 90)),
            )
            target = np.clip(target / scale, -1.0, 1.0)
            target *= min(1.0, level * 1.5)

        decay = max(0.30, min(0.94, float(self.falloff)))
        self._points = target * (1.0 - decay * 0.45) + self._points * decay

        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        mid = int(round(
            np.clip(float(self.y_pos), 0, 100) / 100.0 * (ROWS - 1)
        ))
        amplitude = max(1.0, (ROWS - 2) * 0.48)

        previous_r = mid
        for c in range(COLS):
            r = int(round(mid - self._points[c] * amplitude))
            r = max(0, min(ROWS - 1, r))

            # Connect adjacent samples so it reads as one oscilloscope line.
            r0, r1 = sorted((previous_r, r))
            for rr in range(r0, r1 + 1):
                if MASK_NP[rr, c]:
                    frame[rr, c] = 255
            previous_r = r

        # Straight dim baseline when audio is quiet.
        if level < 0.10:
            for c in range(COLS):
                if MASK_NP[mid, c]:
                    frame[mid, c] = max(frame[mid, c], 85)

        return self._emit(frame)


class AudioRandomStarsEffect(_AudioReactiveBase):
    """Beat-triggered stars that twinkle and fade."""
    name = "Random Stars"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stars: list[dict] = []
        self._valid = np.argwhere(MASK_NP)
        self._spawn_cooldown = 0.0

    def _spawn(self, strength: float):
        count = max(1, int(round(1 + strength * 6)))
        for _ in range(count):
            r, c = self._valid[
                np.random.randint(0, len(self._valid))
            ]
            self._stars.append({
                "r": int(r),
                "c": int(c),
                "life": 1.0,
                "phase": float(np.random.uniform(0, math.tau)),
                "speed": float(np.random.uniform(8.0, 15.0)),
            })

    def tick(self, dt: float) -> list[int]:
        level, beat = self._audio_metrics(dt)
        self._spawn_cooldown = max(0.0, self._spawn_cooldown - dt)

        # React to all audible activity, with transients creating denser bursts.
        should_spawn = beat > 0.11
        if level > 0.07 and self._spawn_cooldown <= 0.0:
            should_spawn = True

        if should_spawn:
            self._spawn(max(0.24, level, beat))
            self._spawn_cooldown = max(0.035, 0.18 - level * 0.12)

        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        keep = []
        fade_rate = (
            0.75 +
            (1.0 - max(0.50, min(0.98, float(self.falloff)))) * 7.5
        )

        for star in self._stars:
            star["life"] -= dt * fade_rate
            star["phase"] += dt * star["speed"]
            if star["life"] <= 0:
                continue

            twinkle = 0.45 + 0.55 * (
                math.sin(star["phase"]) * 0.5 + 0.5
            )
            bri = 255.0 * star["life"] * twinkle
            r, c = star["r"], star["c"]
            frame[r, c] = max(frame[r, c], bri)

            if bri > 120:
                for dr, dc in (
                    (-1, 0), (1, 0), (0, -1), (0, 1)
                ):
                    rr, cc = r + dr, c + dc
                    if (
                        0 <= rr < ROWS and 0 <= cc < COLS
                        and MASK_NP[rr, cc]
                    ):
                        frame[rr, cc] = max(
                            frame[rr, cc], bri * 0.32
                        )
            keep.append(star)

        self._stars = keep
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


class AudioFireEffect(_AudioReactiveBase):
    """Existing good fire visualizer using broadband response."""
    name = "Audio Fire"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._heat = np.zeros((ROWS, COLS), dtype=np.float32)
        self._acc = 0.0

    @staticmethod
    def _shift(arr, dr, dc):
        out = np.zeros_like(arr)
        r_src0 = max(0, -dr); r_src1 = ROWS - max(0, dr)
        c_src0 = max(0, -dc); c_src1 = COLS - max(0, dc)
        r_dst0 = max(0, dr); r_dst1 = ROWS - max(0, -dr)
        c_dst0 = max(0, dc); c_dst1 = COLS - max(0, -dc)
        out[r_dst0:r_dst1, c_dst0:c_dst1] = arr[
            r_src0:r_src1, c_src0:c_src1
        ]
        return out

    def _advance(self, level: float, beat: float):
        src = np.zeros((ROWS, COLS), dtype=bool)
        src[max(0, ROWS - 3):ROWS, :] = True
        ignition = np.clip(
            0.04 + level * 0.92 + beat * 0.28, 0.0, 0.98
        )
        hot = (np.random.random((ROWS, COLS)) < ignition) & src
        seed = np.random.uniform(
            110, 255, (ROWS, COLS)
        ).astype(np.float32)
        self._heat[hot] = np.maximum(self._heat[hot], seed[hot])
        self._heat[src & ~hot] *= 0.72

        up = self._shift(self._heat, -1, 0)
        up_l = self._shift(self._heat, -1, -1)
        up_r = self._shift(self._heat, -1, 1)
        up2 = self._shift(self._heat, -2, 0)
        mixed = (
            up * 0.48 + up_l * 0.18 +
            up_r * 0.18 + up2 * 0.16
        )
        cooling = 10.0 + (1.0 - level) * 22.0
        cool = np.random.uniform(
            0.55, 1.45, (ROWS, COLS)
        ) * cooling
        self._heat = np.maximum(0.0, mixed - cool)

    def tick(self, dt: float) -> list[int]:
        level, beat = self._audio_metrics(dt)
        self._acc += dt
        while self._acc >= 1.0 / 30.0:
            self._acc -= 1.0 / 30.0
            self._advance(level, beat)
        return self._emit(
            np.clip(self._heat, 0, 255).astype(np.uint8)
        )



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
# Chase  (KITT / Larson scanner)
# ═════════════════════════════════════════════════════════════════════

class ChaseEffect(BaseEffect):
    """
    Knight Rider-style Larson scanner: a bright glow bounces left-right
    across the matrix with a soft trailing tail.

    Width   — half-width of the glow envelope in columns.
    Rows    — how many rows the beam occupies (centred vertically).
    """
    name = "Chase"
    PARAMS = {
        "speed": {"label": "Speed", "min": 10, "max": 500, "default": 100, "scale": 100.0},
        "width": {"label": "Width", "min": 2,  "max": 15,  "default": 5,   "scale": 1.0},
        "rows":  {"label": "Rows",  "min": 1,  "max": 12,  "default": 4,   "scale": 1.0},
    }

    def __init__(self, speed: float = 1.0, width: int = 5, rows: int = 4):
        self.speed = speed
        self.width = width
        self.rows  = rows
        self._pos  = 0.0
        self._dir  = 1.0
        self._buf  = np.zeros((ROWS, COLS), dtype=np.float32)

    def reset(self):
        self._buf[:] = 0.0
        self._pos = 0.0
        self._dir = 1.0

    def tick(self, dt: float) -> list[int]:
        eff_dt = dt * self.speed
        rate   = 20.0   # columns per second at speed=1.0

        self._pos += self._dir * rate * eff_dt
        if self._pos >= COLS - 1:
            self._pos = float(COLS - 1)
            self._dir = -1.0
        elif self._pos <= 0:
            self._pos = 0.0
            self._dir = 1.0

        self._buf *= 0.82   # trail decay

        n  = max(1, int(self.rows))
        mid = ROWS // 2
        r0  = max(0, mid - n // 2)
        r1  = min(ROWS, r0 + n)
        w   = max(1.0, float(self.width))

        for c in range(COLS):
            dist = abs(c - self._pos)
            if dist < w * 2.5:
                bri = 255.0 * max(0.0, 1.0 - (dist / w) ** 1.5)
                for r in range(r0, r1):
                    self._buf[r, c] = max(self._buf[r, c], bri)

        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ═════════════════════════════════════════════════════════════════════
# KITT Audio  (scanner speed & brightness driven by audio level)
# ═════════════════════════════════════════════════════════════════════

class KITTAudioEffect(_AudioReactiveBase):
    """
    KITT/KARR discrete dot-fade voice display.

    Shared behavior:
    - no sound = off
    - voice/high-mid driven, not bass driven
    - Sensitivity/Boost are fine-tuning trims over a stronger fixed base gain
    - fixed bar width = 3
    - fixed falloff = 0.70
    - no Noise Floor slider
    - LEDs fade per-dot with a slower stepped trail

    Style 0 = KITT
    - first sound lights the middle band on all three bars
    - center bar grows from middle outward
    - side bars respond at the same time, capped two levels below center

    Style 1 = KARR
    - center bar still grows from the middle band outward, same as KITT
    - side bars start at the top/bottom edges and grow inward toward center
    - same timing and dot-fade behavior as KITT
    """
    name = "KITT Audio"
    PARAMS = {
        "style":       {"label": "Style 0=KITT 1=KARR", "min": 0,    "max": 1,    "default": 0,   "scale": 1.0},
        "sensitivity": {"label": "Sensitivity Trim",    "min": 50,   "max": 150,  "default": 100, "scale": 100.0},
        "boost":       {"label": "Boost Trim",          "min": 50,   "max": 150,  "default": 100, "scale": 100.0},
        "x_pos":       {"label": "X Position",          "min": 0,    "max": 100,  "default": 66,  "scale": 1.0},
        "y_pos":       {"label": "Y Position",          "min": 0,    "max": 100,  "default": 45,  "scale": 1.0},
    }

    def __init__(self, style: float = 0.0, sensitivity: float = 1.0, boost: float = 1.0,
                 x_pos: float = 66.0, y_pos: float = 45.0):
        super().__init__(
            sensitivity=sensitivity,
            falloff=0.70,
            x_pos=x_pos,
            y_pos=y_pos,
        )
        self.boost = boost
        self.style = style
        self.x_pos = x_pos
        self.y_pos = y_pos

        # Locked geometry values.
        self.width = 3.0
        self.floor = 0.0

        # Strong internal gain. UI sliders now trim around this.
        self._base_sensitivity = 17.5
        self._base_boost = 50.0

        self._vu_agc = 0.025
        self._band_agc = np.full(4, 0.0025, dtype=np.float32)
        self._smooth_level = 0.0
        self._kitt_debug_last = 0.0
        self._geom_key = None
        self._groups = [[], [], []]

        # 0 off, 64 = 25%, 128 = 50%, 230 = on
        self._dot_state = np.zeros((ROWS, COLS), dtype=np.uint8)

    def _current_style(self) -> int:
        return 1 if int(round(float(getattr(self, "style", 0.0)))) >= 1 else 0

    def _style_name(self) -> str:
        return "KARR" if self._current_style() == 1 else "KITT"

    def _visual_mid_row(self) -> int:
        y = np.clip(float(getattr(self, "y_pos", 50.0)), 0.0, 100.0) / 100.0
        return int(round(y * (ROWS - 1)))

    def _rebuild_geometry_if_needed(self):
        bar_w = 3
        style = self._current_style()

        key = (
            int(round(float(self.x_pos))),
            int(round(float(getattr(self, "y_pos", 50.0)))),
            bar_w,
            style,
            ROWS,
            COLS,
        )
        if key == self._geom_key:
            return
        self._geom_key = key

        x = np.clip(float(self.x_pos), 0.0, 100.0) / 100.0
        center = int(round(x * (COLS - 1)))

        # Keep the locked width/spacing logic from the tuned KITT version.
        spread = max(bar_w + 3, int(round(COLS * (0.16 if style == 1 else 0.15))))
        positions = [
            center - spread,
            center,
            center + spread,
        ]

        self._groups = []
        for pos in positions:
            c0 = max(0, int(pos) - bar_w // 2)
            c1 = min(COLS, c0 + bar_w)
            if c1 - c0 < bar_w:
                c0 = max(0, c1 - bar_w)
            cols = [c for c in range(c0, c1) if np.any(MASK_NP[:, c])]
            self._groups.append(cols)

    def _voice_high_level(self, dt: float = 1.0 / 60.0):
        level, pulse = self._audio_metrics(dt)
        return level, level, pulse, self._mode

    def _quantize_level(self, level: float) -> int:
        if level <= 0.0:
            return 0
        thresholds = [0.06, 0.16, 0.28, 0.42, 0.58, 0.76]
        out = 0
        for t in thresholds:
            if level >= t:
                out += 1
        return max(0, min(6, out))

    def _valid_rows_for_group(self, group_index: int):
        cols = self._groups[group_index]
        if not cols:
            return []
        return [r for r in range(ROWS) if any(MASK_NP[r, c] for c in cols)]

    def _row_order_kitt(self, group_index: int):
        valid = self._valid_rows_for_group(group_index)
        if not valid:
            return []

        mid = self._visual_mid_row()
        rows = []
        for r in [mid - 1, mid, mid + 1]:
            if r in valid and r not in rows:
                rows.append(r)

        for step in range(2, ROWS + 1):
            above = mid - step
            below = mid + step
            if above in valid and above not in rows:
                rows.append(above)
            if below in valid and below not in rows:
                rows.append(below)
        return rows

    def _row_order_karr_center(self):
        # Keep the center column KARR response close to KITT, so the style shift
        # mainly comes from the bracketed side bars.
        return self._row_order_kitt(1)

    def _row_order_karr_side(self, group_index: int):
        """
        KARR side bars are the inverse of the center bar.

        Think of the vertical center as 0:
          +6 = top edge
          -6 = bottom edge

        Side bars:
          - upper side stack starts at the top edge and grows downward
          - lower side stack starts at the bottom edge and grows upward
          - both grow together toward center
          - max stops one row away from center, leaving the center gap clear
        """
        valid = self._valid_rows_for_group(group_index)
        if not valid:
            return []

        mid = self._visual_mid_row()

        # Leave a clear center gap around the KITT/KARR mouth center.
        upper_limit = max(0, mid - 1)
        lower_limit = min(ROWS - 1, mid + 1)

        top_rows = [r for r in valid if r <= upper_limit]
        bottom_rows = [r for r in valid if r >= lower_limit]

        # Top grows down from physical top toward center.
        top_rows.sort()

        # Bottom grows up from physical bottom toward center.
        bottom_rows.sort(reverse=True)

        rows = []
        max_len = max(len(top_rows), len(bottom_rows))
        for i in range(max_len):
            if i < len(top_rows):
                rows.append(top_rows[i])
            if i < len(bottom_rows):
                rows.append(bottom_rows[i])

        return rows

    def _rows_for_level_kitt(self, group_index: int, level: int):
        if level <= 0:
            return []
        order = self._row_order_kitt(group_index)
        if not order:
            return []
        if level >= 6:
            count = len(order)
        else:
            count = min(len(order), 3 + (level - 1) * 2)
        return order[:count]

    def _rows_for_level_karr(self, group_index: int, level: int):
        if level <= 0:
            return []

        if group_index == 1:
            order = self._row_order_karr_center()
            if not order:
                return []
            if level >= 6:
                count = len(order)
            else:
                count = min(len(order), 3 + (level - 1) * 2)
            return order[:count]

        # Side brackets: level 1 starts at the top and bottom edges.
        # Higher levels grow inward toward the center. Level 6 reaches one row
        # away from center.
        order = self._row_order_karr_side(group_index)
        if not order:
            return []

        if level >= 6:
            count = len(order)
        else:
            # Use proportional growth so low levels are edge-only, high levels
            # approach the center gap.
            count = max(2, int(round((level / 6.0) * len(order))))
            count = min(len(order), count)

        return order[:count]

    def _rows_for_level(self, group_index: int, level: int):
        if self._current_style() == 1:
            return self._rows_for_level_karr(group_index, level)
        return self._rows_for_level_kitt(group_index, level)

    def _paint_target_rows(self, target: np.ndarray, group_index: int, level: int):
        cols = self._groups[group_index]
        rows = self._rows_for_level(group_index, level)
        if not cols or not rows:
            return

        mid = self._visual_mid_row()
        style = self._current_style()

        for r in rows:
            dist = abs(r - mid)
            if style == 1:
                bri = max(150, 225 - dist * 6)
            else:
                bri = max(145, 230 - dist * 7)
            for c in cols:
                if MASK_NP[r, c]:
                    target[r, c] = max(target[r, c], int(bri))

    def _apply_dot_fade(self, target: np.ndarray):
        """
        Slower dot-by-dot fade for both KITT and KARR.

        Old fade was:
          100% -> 50% -> 25% -> off

        That was too sharp. This version adds intermediate steps:
          100% -> 75% -> 50% -> 37% -> 25% -> 12% -> off
        """
        new_state = self._dot_state.copy()

        on = target > 0
        new_state[on] = target[on].astype(np.uint8)

        off = ~on
        old = self._dot_state

        # Full-ish to 75%
        mask = off & (old > 180)
        new_state[mask] = 180

        # 75% to 50%
        mask = off & (old <= 180) & (old > 128)
        new_state[mask] = 128

        # 50% to 37%
        mask = off & (old <= 128) & (old > 96)
        new_state[mask] = 96

        # 37% to 25%
        mask = off & (old <= 96) & (old > 64)
        new_state[mask] = 64

        # 25% to 12%
        mask = off & (old <= 64) & (old > 32)
        new_state[mask] = 32

        # 12% to off
        mask = off & (old <= 32)
        new_state[mask] = 0

        self._dot_state = new_state

    def tick(self, dt: float) -> list[int]:
        self._rebuild_geometry_if_needed()

        level, rms, voice, mode = self._voice_high_level(dt)

        if level > self._smooth_level:
            self._smooth_level += (level - self._smooth_level) * 0.62
        else:
            self._smooth_level *= 0.76

        center_level = self._quantize_level(self._smooth_level)

        if level <= 0.0 and self._smooth_level < 0.075:
            center_level = 0
            self._smooth_level = 0.0

        if self._current_style() == 1:
            # KARR sides use the same master response as the center, but draw
            # from the outer edges inward.
            side_level = center_level
        else:
            # KITT sides move in sync but cap two levels below center.
            if center_level <= 1:
                side_level = center_level
            else:
                side_level = min(center_level, max(1, center_level - 2))

        target = np.zeros((ROWS, COLS), dtype=np.uint8)

        self._paint_target_rows(target, 0, side_level)
        self._paint_target_rows(target, 1, center_level)
        self._paint_target_rows(target, 2, side_level)

        self._apply_dot_fade(target)

        try:
            now = time.monotonic()
            if now - self._kitt_debug_last > 2.0:
                self._kitt_debug_last = now
                _SHARED_AUDIO_CAPTURE.log(
                    f"{self._style_name()} locked level={center_level}, side={side_level}, "
                    f"smooth={self._smooth_level:.3f}, rms={rms:.6f}, "
                    f"voice={voice:.6f}, sens_trim={self.sensitivity:.2f}, "
                    f"boost_trim={self.boost:.2f}, x={self.x_pos:.1f}, "
                    f"y={self.y_pos:.1f}, fixed_bar_width=3, mode={mode}"
                )
        except Exception:
            pass

        return self._emit(self._dot_state.astype(np.uint8))


# Dedicated Audio-tab visualizer registry.
# This must remain below every referenced class definition.
AUDIO_VISUALIZERS: dict[str, type[AudioVisualizer]] = {
    "Spectrum Bars": SpectrumAudioVisualizer,
    "KITT / KARR": KITTAudioEffect,
    "Center Starburst": AudioStarburstEffect,
    "Corner Convergence": AudioCornerConvergenceEffect,
    "Oscilloscope": AudioCenterWaveEffect,
    "Random Stars": AudioRandomStarsEffect,
    "Audio Fire": AudioFireEffect,
}


# ═════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════
# Comment out any effects here that you would like to hide from the main select list
# This will allow the view to stay functional and clean. Ex. "PotatoEffect," --> "#     PotatoEffect,"

ALL_EFFECTS: list[type[BaseEffect]] = [
#    PulseEffect,
#    MatrixRainEffect,
    MatrixRainEffectV2, 
    RainEffect,
#    WipeEffect,
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
    ScrollTextEffect,
#    TypingEffect,
    KeyboardReactEffect,
#    AudioVisualizer,  # moved to dedicated Audio tab
    FireEffect,
    MetaballsEffect,
#    GameOfLifeEffect,
    ChaseEffect,
#    KITTAudioEffect,  # moved to dedicated Audio tab
]

EFFECT_NAMES: list[str] = [e.name for e in ALL_EFFECTS]

def make_effect(name: str) -> BaseEffect:
    for cls in ALL_EFFECTS:
        if cls.name == name:
            return cls()
    raise ValueError(f"Unknown effect: {name!r}")
