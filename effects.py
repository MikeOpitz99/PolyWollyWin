"""
effects.py — Built-in generative effects for the 37×12 matrix.

Each effect: .tick(dt) -> list[int], .reset(), .name
"""

from __future__ import annotations
import math, random
import numpy as np
from renderer import (
    ROWS, COLS, PHYSICAL_LED_COUNT,
    MASK_NP, logical_to_physical, apply_mask, blank_frame,
)


class BaseEffect:
    name = "base"
    def tick(self, dt: float) -> list[int]: raise NotImplementedError
    def reset(self): pass
    def _emit(self, frame: np.ndarray) -> list[int]:
        return logical_to_physical(apply_mask(frame))


# ── Pulse ──────────────────────────────────────────────────────────────

class PulseEffect(BaseEffect):
    name = "Pulse"
    def __init__(self, speed=1.0, peak=255):
        self.speed = speed; self.peak = peak; self._t = 0.0
    def tick(self, dt):
        self._t += dt * self.speed
        v = int((math.sin(self._t * math.pi) ** 2) * self.peak)
        return self._emit(np.full((ROWS, COLS), v, dtype=np.uint8))
    def reset(self): self._t = 0.0


# ── The Matrix (proper digital rain) ──────────────────────────────────

class MatrixRainEffect(BaseEffect):
    name = "The Matrix"

    def __init__(self):
        self._buf   = np.zeros((ROWS, COLS), dtype=np.float32)
        self._drops = {}   # col -> {pos, speed, brightness}
        self._t     = 0.0

    def reset(self):
        self._buf[:] = 0
        self._drops.clear()

    def tick(self, dt):
        self._t += dt

        # Spawn new drops with random speeds + brightnesses
        for c in range(COLS):
            if c not in self._drops and random.random() < 0.06 * dt * 30:
                self._drops[c] = {
                    "pos":        0.0,
                    "speed":      random.uniform(4, 18),
                    "head_bri":   random.randint(180, 255),
                    "trail_bri":  random.uniform(0.55, 0.82),
                }

        # Fade everything
        self._buf *= 0.82

        # Move drops and paint head + immediate trail
        done = []
        for c, d in self._drops.items():
            r = int(d["pos"])
            # Paint a short bright head segment
            for offset in range(3):
                pr = r - offset
                if 0 <= pr < ROWS and MASK_NP[pr, c]:
                    bri = d["head_bri"] * (1 - offset * 0.35)
                    self._buf[pr, c] = max(self._buf[pr, c], bri)

            d["pos"] += d["speed"] * dt
            if d["pos"] >= ROWS + 2:
                done.append(c)

        for c in done:
            del self._drops[c]

        frame = np.clip(self._buf, 0, 255).astype(np.uint8)
        return self._emit(frame)


# ── Rain (simple) ─────────────────────────────────────────────────────

class RainEffect(BaseEffect):
    name = "Rain"
    def __init__(self, density=0.18, speed=8.0, trail=0.75):
        self.density = density; self.speed = speed; self.trail = trail
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)
        self._heads = {}

    def reset(self): self._buf[:] = 0; self._heads.clear()

    def tick(self, dt):
        for c in range(COLS):
            if c not in self._heads and random.random() < self.density * dt:
                self._heads[c] = 0.0
        done = []
        for c, pos in self._heads.items():
            r = int(pos)
            if 0 <= r < ROWS and MASK_NP[r, c]:
                self._buf[r, c] = 255.0
            pos += self.speed * dt
            if pos >= ROWS: done.append(c)
            else: self._heads[c] = pos
        for c in done: del self._heads[c]
        self._buf *= self.trail ** (dt * 30 / 10)
        self._buf = np.clip(self._buf, 0, 255)
        return self._emit(self._buf.astype(np.uint8))


# ── Wipe ───────────────────────────────────────────────────────────────

class WipeEffect(BaseEffect):
    name = "Wipe"
    def __init__(self, speed=10.0, width=3):
        self.speed = speed; self.width = width
        self._pos = 0.0; self._dir = 1

    def reset(self): self._pos = 0.0; self._dir = 1

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        pos = int(self._pos)
        for offset in range(-(self.width // 2), self.width // 2 + 1):
            c = pos + offset
            if 0 <= c < COLS:
                dist = abs(offset) / max(1, self.width // 2)
                frame[:, c] = int(255 * (1 - dist))
        self._pos += self.speed * self._dir * dt
        if self._pos >= COLS - 1: self._dir = -1
        elif self._pos <= 0: self._dir = 1
        return self._emit(frame)


# ── Plasma ─────────────────────────────────────────────────────────────

class PlasmaEffect(BaseEffect):
    name = "Plasma"
    def __init__(self, speed=1.0): self.speed = speed; self._t = 0.0
    def reset(self): self._t = 0.0
    def tick(self, dt):
        self._t += dt * self.speed
        t = self._t
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        for r in range(ROWS):
            for c in range(COLS):
                v = (math.sin(c / 4.0 + t)
                     + math.sin(r / 2.0 + t * 1.3)
                     + math.sin((c + r) / 5.0 + t * 0.7)
                     + math.sin(math.sqrt(c * c + r * r) / 4.0 + t * 0.9))
                frame[r, c] = (v + 4) / 8 * 255
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Noise ──────────────────────────────────────────────────────────────

class NoiseEffect(BaseEffect):
    name = "Noise"
    def __init__(self, density=0.3, smoothing=0.6):
        self.density = density; self.smoothing = smoothing
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)

    def reset(self): self._buf[:] = 0

    def tick(self, dt):
        target = np.zeros((ROWS, COLS), dtype=np.float32)
        mask = np.random.random((ROWS, COLS)) < self.density
        target[mask] = np.random.uniform(128, 255, mask.sum())
        s = self.smoothing ** (dt * 30)
        self._buf = self._buf * s + target * (1 - s)
        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ── Scan ───────────────────────────────────────────────────────────────

class ScanEffect(BaseEffect):
    name = "Scan"
    def __init__(self, speed=4.0): self.speed = speed; self._pos = 0.0
    def reset(self): self._pos = 0.0
    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        frame[int(self._pos) % ROWS, :] = 255
        self._pos = (self._pos + self.speed * dt) % ROWS
        return self._emit(frame)


# ── Starfield ──────────────────────────────────────────────────────────

class StarfieldEffect(BaseEffect):
    name = "Starfield"
    def __init__(self, count=40):
        self._stars = []
        self._count = count
        self._spawn_all()

    def _spawn_all(self):
        self._stars = [self._new_star() for _ in range(self._count)]

    def _new_star(self):
        return {
            "x":    random.uniform(0, COLS),
            "z":    random.uniform(0.1, 1.0),   # depth
            "vz":   random.uniform(0.3, 1.2),   # speed toward viewer
            "bri":  random.randint(80, 255),
        }

    def reset(self): self._spawn_all()

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        for s in self._stars:
            s["z"] -= s["vz"] * dt
            if s["z"] <= 0:
                s.update(self._new_star())
                s["z"] = 1.0
                continue
            # Project: closer = bigger x spread, row from depth
            proj_c = int(s["x"] + (s["x"] - COLS / 2) * (1 - s["z"]) * 0.5)
            proj_r = int(ROWS / 2 + (ROWS / 2) * (1 - s["z"]))
            bri    = int(s["bri"] * (1 - s["z"]))
            if 0 <= proj_r < ROWS and 0 <= proj_c < COLS and MASK_NP[proj_r, proj_c]:
                frame[proj_r, proj_c] = min(255, frame[proj_r, proj_c] + bri)
        return self._emit(frame)


# ── Comet ─────────────────────────────────────────────────────────────

class CometEffect(BaseEffect):
    name = "Comet"
    def __init__(self):
        self._comets = []
        self._t = 0.0

    def reset(self): self._comets.clear(); self._t = 0.0

    def _new_comet(self):
        return {
            "x":    random.uniform(0, COLS),
            "y":    random.uniform(0, ROWS),
            "vx":   random.choice([-1, 1]) * random.uniform(8, 20),
            "vy":   random.uniform(-3, 3),
            "tail": 10,
            "bri":  random.randint(180, 255),
            "history": [],
        }

    def tick(self, dt):
        self._t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        # Spawn
        if random.random() < 0.4 * dt:
            self._comets.append(self._new_comet())

        done = []
        for i, c in enumerate(self._comets):
            c["history"].append((c["x"], c["y"]))
            if len(c["history"]) > c["tail"]:
                c["history"].pop(0)

            for j, (hx, hy) in enumerate(reversed(c["history"])):
                alpha = (j + 1) / len(c["history"])
                bri = int(c["bri"] * alpha ** 1.5)
                r, col = int(hy), int(hx)
                if 0 <= r < ROWS and 0 <= col < COLS and MASK_NP[r, col]:
                    frame[r, col] = max(frame[r, col], bri)

            c["x"] += c["vx"] * dt
            c["y"] += c["vy"] * dt
            if c["x"] < -5 or c["x"] > COLS + 5:
                done.append(i)

        for i in reversed(done): self._comets.pop(i)
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Ripple ────────────────────────────────────────────────────────────

class RippleEffect(BaseEffect):
    name = "Ripple"
    def __init__(self):
        self._rings = []
        self._t = 0.0

    def reset(self): self._rings.clear(); self._t = 0.0

    def tick(self, dt):
        self._t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        if random.random() < 0.6 * dt:
            valid_cols = [c for c in range(COLS) if any(MASK_NP[:, c])]
            cx = random.choice(valid_cols)
            cy = random.randint(0, ROWS - 1)
            self._rings.append({"cx": cx, "cy": cy, "r": 0.0, "bri": 220})

        done = []
        for i, ring in enumerate(self._rings):
            ring["r"] += 8 * dt
            ring["bri"] *= 0.94
            if ring["bri"] < 4: done.append(i); continue

            for r in range(ROWS):
                for c in range(COLS):
                    if not MASK_NP[r, c]: continue
                    dist = math.sqrt((c - ring["cx"]) ** 2 + (r - ring["cy"]) ** 2)
                    diff = abs(dist - ring["r"])
                    if diff < 1.2:
                        bri = ring["bri"] * (1 - diff / 1.2)
                        frame[r, c] = max(frame[r, c], bri)

        for i in reversed(done): self._rings.pop(i)
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Helix ────────────────────────────────────────────────────────────

class HelixEffect(BaseEffect):
    name = "Helix"
    def __init__(self, speed=2.0): self.speed = speed; self._t = 0.0
    def reset(self): self._t = 0.0

    def tick(self, dt):
        self._t += dt * self.speed
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        for c in range(COLS):
            phase = c / COLS * math.pi * 4 + self._t
            # Strand A
            ra = int((math.sin(phase) + 1) / 2 * (ROWS - 1))
            # Strand B (offset by pi)
            rb = int((math.sin(phase + math.pi) + 1) / 2 * (ROWS - 1))

            if MASK_NP[ra, c]:
                frame[ra, c] = max(frame[ra, c], 255)
            if MASK_NP[rb, c]:
                frame[rb, c] = max(frame[rb, c], 180)

            # Connecting rungs
            lo, hi = min(ra, rb), max(ra, rb)
            for r in range(lo + 1, hi):
                if MASK_NP[r, c]:
                    frame[r, c] = max(frame[r, c], 60)

        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Fireworks ────────────────────────────────────────────────────────

class FireworksEffect(BaseEffect):
    name = "Fireworks"

    def __init__(self):
        self._particles = []
        self._t = 0.0

    def reset(self): self._particles.clear(); self._t = 0.0

    def _explode(self):
        cx = random.randint(8, COLS - 8)
        cy = random.randint(1, ROWS - 2)
        count = random.randint(8, 16)
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(3, 12)
            self._particles.append({
                "x": float(cx), "y": float(cy),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed * 0.4,
                "bri": 255,
                "decay": random.uniform(0.5, 0.85),
            })

    def tick(self, dt):
        self._t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        if random.random() < 0.8 * dt:
            self._explode()

        done = []
        for i, p in enumerate(self._particles):
            p["x"]  += p["vx"] * dt
            p["y"]  += p["vy"] * dt
            p["vy"] += 4 * dt   # gravity
            p["bri"] *= p["decay"] ** (dt * 8)
            if p["bri"] < 6: done.append(i); continue
            r, c = int(p["y"]), int(p["x"])
            if 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]:
                frame[r, c] = max(frame[r, c], p["bri"])

        for i in reversed(done): self._particles.pop(i)
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Bounce ────────────────────────────────────────────────────────────

class BounceEffect(BaseEffect):
    name = "Bounce"

    def __init__(self):
        self._x = float(COLS // 2)
        self._y = float(ROWS // 2)
        self._vx = random.choice([-1, 1]) * random.uniform(8, 16)
        self._vy = random.choice([-1, 1]) * random.uniform(3, 7)
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)

    def reset(self):
        self._x = float(COLS // 2)
        self._y = float(ROWS // 2)
        self._buf[:] = 0

    def tick(self, dt):
        self._x += self._vx * dt
        self._y += self._vy * dt
        if self._x <= 0 or self._x >= COLS - 1: self._vx *= -1
        if self._y <= 0 or self._y >= ROWS - 1: self._vy *= -1
        self._x = max(0, min(COLS - 1, self._x))
        self._y = max(0, min(ROWS - 1, self._y))

        self._buf *= 0.75
        for dr in range(-1, 2):
            for dc in range(-2, 3):
                r = int(self._y) + dr
                c = int(self._x) + dc
                if 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]:
                    dist = math.sqrt(dr*dr + dc*dc*0.4)
                    self._buf[r, c] = max(self._buf[r, c], 255 * max(0, 1 - dist * 0.5))

        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ── Wave ─────────────────────────────────────────────────────────────

class WaveEffect(BaseEffect):
    name = "Wave"

    def __init__(self, speed=2.0, waves=3): self.speed = speed; self.waves = waves; self._t = 0.0
    def reset(self): self._t = 0.0

    def tick(self, dt):
        self._t += dt * self.speed
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        for c in range(COLS):
            center = (math.sin(c / COLS * math.pi * 2 * self.waves + self._t) + 1) / 2 * (ROWS - 1)
            for r in range(ROWS):
                if not MASK_NP[r, c]: continue
                dist = abs(r - center)
                if dist < 2:
                    frame[r, c] = 255 * (1 - dist / 2) ** 2
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Audio Visualizer ─────────────────────────────────────────────────

class AudioVisualizer(BaseEffect):
    name = "Audio"

    def __init__(self, sample_rate=22050, chunk=1024):
        self._sr      = sample_rate
        self._chunk   = chunk
        self._bars    = np.zeros(COLS, dtype=np.float32)
        self._peak    = np.zeros(COLS, dtype=np.float32)
        self._stream  = None
        self._buf     = np.zeros(chunk, dtype=np.float32)
        self._available = False
        self._t       = 0.0
        self._start()

    def _start(self):
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self._sr, channels=1,
                blocksize=self._chunk, callback=self._callback, dtype="float32",
            )
            self._stream.start()
            self._available = True
        except Exception as e:
            print(f"AudioVisualizer: unavailable ({e})")

    def _callback(self, indata, frames, time_info, status):
        self._buf = indata[:, 0].copy()

    def reset(self): self._bars[:] = 0; self._peak[:] = 0

    def stop(self):
        if self._stream:
            try: self._stream.stop(); self._stream.close()
            except: pass
            self._stream = None

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        self._t += dt

        if self._available:
            fft  = np.abs(np.fft.rfft(self._buf * np.hanning(len(self._buf))))
            nf   = len(fft)
            bars = np.array([np.mean(fft[max(0,int(nf*i/COLS)):max(1,int(nf*(i+1)/COLS))]) for i in range(COLS)], dtype=np.float32)
            mx = bars.max()
            if mx > 0: bars /= mx
            self._bars = self._bars * 0.6 + bars * 0.4
            self._peak = np.maximum(self._peak * (1 - dt * 1.5), self._bars)

            for c in range(COLS):
                height   = int(self._bars[c] * ROWS)
                peak_row = int(self._peak[c] * (ROWS - 1))
                for r in range(ROWS):
                    dr = ROWS - 1 - r
                    if not MASK_NP[dr, c]: continue
                    if r < height:
                        frame[dr, c] = max(40, int(200 * r / max(1, height)))
                    elif r == peak_row:
                        frame[dr, c] = 255
        else:
            # Plasma fallback
            for r in range(ROWS):
                for c in range(COLS):
                    if not MASK_NP[r, c]: continue
                    v = math.sin(c/4 + self._t)*math.cos(r/2 + self._t*0.7)
                    frame[r, c] = int((v+1)/2*255)

        return logical_to_physical(apply_mask(frame))


# ── Registry ─────────────────────────────────────────────────────────

ALL_EFFECTS: list[type[BaseEffect]] = [
    PulseEffect, MatrixRainEffect, RainEffect,
    WipeEffect, PlasmaEffect, NoiseEffect, ScanEffect,
    StarfieldEffect, CometEffect, RippleEffect,
    HelixEffect, FireworksEffect, BounceEffect, WaveEffect,
    AudioVisualizer,
]
EFFECT_NAMES = [e.name for e in ALL_EFFECTS]

def make_effect(name: str) -> BaseEffect:
    for cls in ALL_EFFECTS:
        if cls.name == name: return cls()
    raise ValueError(f"Unknown effect: {name!r}")
