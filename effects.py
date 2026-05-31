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


# ── Base class all effects inherit from ───────────────────────────────
class BaseEffect:
    name = "base"
    def tick(self, dt: float) -> list[int]: raise NotImplementedError  # subclasses must implement; dt = seconds since last frame
    def reset(self): pass                                               # optional: called when effect is restarted
    def _emit(self, frame: np.ndarray) -> list[int]:
        return logical_to_physical(apply_mask(frame))                  # apply the LED mask, then remap logical grid → physical LED indices


# ── Pulse ──────────────────────────────────────────────────────────────

class PulseEffect(BaseEffect):
    name = "Pulse"
    def __init__(self, speed=1.0, peak=255):
        self.speed = speed   # how fast the pulse cycles (multiplier on time)
        self.peak  = peak    # maximum brightness (0-255)
        self._t    = 0.0     # accumulated time in seconds

    def tick(self, dt):
        self._t += dt * self.speed                              # advance time, scaled by speed
        v = int((math.sin(self._t * math.pi) ** 2) * self.peak)# sin² gives a smooth 0→peak→0 pulse (always positive)
        return self._emit(np.full((ROWS, COLS), v, dtype=np.uint8))  # fill the entire grid with that brightness

    def reset(self): self._t = 0.0


# ── The Matrix (digital rain) ─────────────────────────────────────────

class MatrixRainEffect(BaseEffect):
    name = "The Matrix"

    def __init__(self, speed=1.0):
        self.speed  = speed                                      # NEW: global speed multiplier
        self._buf   = np.zeros((ROWS, COLS), dtype=np.float32)  # persistent brightness buffer so trails fade over time
        self._drops = {}                                         # active drops keyed by column: {pos, speed, brightness}
        self._t     = 0.0

    def reset(self):
        self._buf[:] = 0      # clear the brightness buffer
        self._drops.clear()   # remove all active drops

    def tick(self, dt):
        self._t += dt

        # Each column has a ~6% chance per second of spawning a new drop (if not already active)
        for c in range(COLS):
            if c not in self._drops and random.random() < 0.06 * dt * 30:
                self._drops[c] = {
                    "pos":       0.0,                           # current row position (float, for smooth movement)
                    "speed":     random.uniform(4, 18) * self.speed,  # rows per second (varied per drop)
                    "head_bri":  random.randint(180, 255),      # brightness of the leading pixel
                    "trail_bri": random.uniform(0.55, 0.82),    # fade factor for the trailing glow
                }

        self._buf *= 0.82  # decay all pixels each frame, creating the fading trail effect

        # Move each active drop and paint its head pixels
        done = []
        for c, d in self._drops.items():
            r = int(d["pos"])
            # Paint a 3-pixel head: full brightness at tip, dimming with each offset
            for offset in range(3):
                pr = r - offset
                if 0 <= pr < ROWS and MASK_NP[pr, c]:          # bounds check + mask check
                    bri = d["head_bri"] * (1 - offset * 0.35)  # each step is 35% dimmer
                    self._buf[pr, c] = max(self._buf[pr, c], bri)  # don't overwrite brighter pixels

            d["pos"] += d["speed"] * dt                         # advance drop position this frame
            if d["pos"] >= ROWS + 2:                            # drop has exited the grid (+2 buffer so trail clears)
                done.append(c)

        for c in done:
            del self._drops[c]   # remove finished drops

        frame = np.clip(self._buf, 0, 255).astype(np.uint8)    # clamp to valid uint8 range
        return self._emit(frame)


# ── Rain (simple) ─────────────────────────────────────────────────────

class RainEffect(BaseEffect):
    name = "Rain"
    def __init__(self, density=0.18, speed=8.0, trail=0.75):
        self.density = density  # probability per column per second of a new drop spawning
        self.speed   = speed    # how fast drops fall (rows per second)
        self.trail   = trail    # per-frame fade factor for the trail (lower = shorter trail)
        self._buf    = np.zeros((ROWS, COLS), dtype=np.float32)  # brightness buffer
        self._heads  = {}       # active drop positions keyed by column

    def reset(self): self._buf[:] = 0; self._heads.clear()

    def tick(self, dt):
        # Possibly spawn a new drop in each column that has none
        for c in range(COLS):
            if c not in self._heads and random.random() < self.density * dt:
                self._heads[c] = 0.0   # start at the top of the column

        done = []
        for c, pos in self._heads.items():
            r = int(pos)
            if 0 <= r < ROWS and MASK_NP[r, c]:
                self._buf[r, c] = 255.0            # paint the drop head at full brightness
            pos += self.speed * dt                 # advance drop down the column
            if pos >= ROWS: done.append(c)         # drop has left the grid
            else: self._heads[c] = pos
        for c in done: del self._heads[c]

        # Decay the trail: exponent keeps the fade rate consistent regardless of dt
        self._buf *= self.trail ** (dt * 30 / 10)
        self._buf  = np.clip(self._buf, 0, 255)
        return self._emit(self._buf.astype(np.uint8))


# ── Wipe ───────────────────────────────────────────────────────────────

class WipeEffect(BaseEffect):
    name = "Wipe"
    def __init__(self, speed=10.0, width=3):
        self.speed = speed   # columns per second the bar moves
        self.width = width   # how many columns wide the bright bar is
        self._pos  = 0.0     # current column position of the bar centre
        self._dir  = 1       # +1 = moving right, -1 = moving left

    def reset(self): self._pos = 0.0; self._dir = 1

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        pos = int(self._pos)
        # Paint each column within the bar width, dimming toward the edges
        for offset in range(-(self.width // 2), self.width // 2 + 1):
            c = pos + offset
            if 0 <= c < COLS:
                dist = abs(offset) / max(1, self.width // 2)   # 0.0 at center, 1.0 at edges
                frame[:, c] = int(255 * (1 - dist))             # full column gets the same brightness
        self._pos += self.speed * self._dir * dt                # advance the bar position
        if self._pos >= COLS - 1: self._dir = -1                # hit the right edge, reverse
        elif self._pos <= 0:      self._dir = 1                 # hit the left edge, reverse
        return self._emit(frame)


# ── Plasma ─────────────────────────────────────────────────────────────

class PlasmaEffect(BaseEffect):
    name = "Plasma"
    def __init__(self, speed=1.0): self.speed = speed; self._t = 0.0
    def reset(self): self._t = 0.0

    def tick(self, dt):
        self._t += dt * self.speed   # advance time at speed-scaled rate
        t = self._t
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        for r in range(ROWS):
            for c in range(COLS):
                # Sum four overlapping sine waves with different frequencies and phases
                v = (math.sin(c / 4.0 + t)                              # horizontal wave
                     + math.sin(r / 2.0 + t * 1.3)                     # vertical wave (faster)
                     + math.sin((c + r) / 5.0 + t * 0.7)               # diagonal wave (slower)
                     + math.sin(math.sqrt(c * c + r * r) / 4.0 + t * 0.9))  # radial wave from top-left
                frame[r, c] = (v + 4) / 8 * 255  # v is in [-4, 4]; shift+scale to [0, 255]
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Noise ──────────────────────────────────────────────────────────────

class NoiseEffect(BaseEffect):
    name = "Noise"
    def __init__(self, density=0.3, smoothing=0.6):
        self.density   = density    # fraction of pixels that get a new random value each frame
        self.smoothing = smoothing  # how much of the old value to keep (0=instant, 1=no change)
        self._buf = np.zeros((ROWS, COLS), dtype=np.float32)

    def reset(self): self._buf[:] = 0

    def tick(self, dt):
        target = np.zeros((ROWS, COLS), dtype=np.float32)
        mask = np.random.random((ROWS, COLS)) < self.density  # pick random pixels to light up
        target[mask] = np.random.uniform(128, 255, mask.sum())  # assign random brightness to chosen pixels
        s = self.smoothing ** (dt * 30)               # time-normalise the blend factor
        self._buf = self._buf * s + target * (1 - s)  # exponential moving average toward target
        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ── Scan ───────────────────────────────────────────────────────────────

class ScanEffect(BaseEffect):
    name = "Scan"
    def __init__(self, speed=4.0): self.speed = speed; self._pos = 0.0
    def reset(self): self._pos = 0.0

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        frame[int(self._pos) % ROWS, :] = 255              # light the entire current row at full brightness
        self._pos = (self._pos + self.speed * dt) % ROWS   # advance and wrap around when it hits the bottom
        return self._emit(frame)


# ── Starfield ──────────────────────────────────────────────────────────
# BUG FIX: original had no "y" coordinate, so proj_r always landed in the
# bottom half of the matrix (ROWS/2 + something positive). Added "y" so
# stars spread across the full vertical range.

class StarfieldEffect(BaseEffect):
    name = "Starfield"
    def __init__(self, count=40, speed=1.0):
        self._count = count
        self.speed  = speed   # NEW: global speed multiplier
        self._stars = []
        self._spawn_all()

    def _spawn_all(self):
        self._stars = [self._new_star() for _ in range(self._count)]

    def _new_star(self):
        return {
            "x":  random.uniform(0, COLS),      # horizontal start position
            "y":  random.uniform(0, ROWS),       # FIX: vertical start position (was missing)
            "z":  random.uniform(0.1, 1.0),      # depth: 1.0 = far away, 0.0 = right in front
            "vz": random.uniform(0.3, 1.2),      # speed toward the viewer (decrease z per second)
            "bri": random.randint(80, 255),       # base brightness
        }

    def reset(self): self._spawn_all()

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)
        for s in self._stars:
            s["z"] -= s["vz"] * dt * self.speed   # move star closer (z approaches 0)
            if s["z"] <= 0:                        # star has passed the viewer — respawn it far away
                s.update(self._new_star())
                s["z"] = 1.0
                continue
            # Perspective projection: as z→0 the star spreads outward from centre
            proj_c = int(s["x"] + (s["x"] - COLS / 2) * (1 - s["z"]) * 0.5)  # horizontal divergence
            proj_r = int(s["y"] + (s["y"] - ROWS / 2) * (1 - s["z"]) * 0.5)  # FIX: vertical divergence
            bri    = int(s["bri"] * (1 - s["z"]))  # brighter as it gets closer
            if 0 <= proj_r < ROWS and 0 <= proj_c < COLS and MASK_NP[proj_r, proj_c]:
                frame[proj_r, proj_c] = min(255, frame[proj_r, proj_c] + bri)
        return self._emit(frame)


# ── Comet ─────────────────────────────────────────────────────────────

class CometEffect(BaseEffect):
    name = "Comet"
    def __init__(self, speed=1.0):
        self.speed   = speed   # NEW: global speed multiplier
        self._comets = []
        self._t      = 0.0

    def reset(self): self._comets.clear(); self._t = 0.0

    def _new_comet(self):
        return {
            "x":  random.uniform(0, COLS),
            "y":  random.uniform(0, ROWS),
            "vx": random.choice([-1, 1]) * random.uniform(8, 20) * self.speed,  # horizontal velocity (direction randomised)
            "vy": random.uniform(-3, 3) * self.speed,                            # slight vertical drift
            "tail": 10,      # number of historical positions to keep for the tail
            "bri": random.randint(180, 255),
            "history": [],   # list of (x, y) positions for drawing the tail
        }

    def tick(self, dt):
        self._t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        if random.random() < 0.4 * dt:            # ~40% chance per second of a new comet
            self._comets.append(self._new_comet())

        done = []
        for i, c in enumerate(self._comets):
            c["history"].append((c["x"], c["y"]))  # record current position for tail rendering
            if len(c["history"]) > c["tail"]:
                c["history"].pop(0)                 # trim oldest position once tail is full length

            # Draw the tail: iterate history in reverse so index 0 = most recent (brightest)
            for j, (hx, hy) in enumerate(reversed(c["history"])):
                alpha = (j + 1) / len(c["history"])          # 1.0 = head, near 0 = oldest tail pixel
                bri   = int(c["bri"] * alpha ** 1.5)         # power curve makes tail fade quickly
                r, col = int(hy), int(hx)
                if 0 <= r < ROWS and 0 <= col < COLS and MASK_NP[r, col]:
                    frame[r, col] = max(frame[r, col], bri)  # don't overwrite brighter overlapping comets

            c["x"] += c["vx"] * dt   # advance comet position
            c["y"] += c["vy"] * dt
            if c["x"] < -5 or c["x"] > COLS + 5:  # comet has left the screen
                done.append(i)

        for i in reversed(done): self._comets.pop(i)  # remove off-screen comets (reversed to keep indices valid)
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Ripple ────────────────────────────────────────────────────────────

class RippleEffect(BaseEffect):
    name = "Ripple"
    def __init__(self, speed=1.0):
        self.speed  = speed   # NEW: global speed multiplier
        self._rings = []
        self._t     = 0.0

    def reset(self): self._rings.clear(); self._t = 0.0

    def tick(self, dt):
        self._t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        # ~60% chance per second of a new ripple at a random valid position
        if random.random() < 0.6 * dt:
            valid_cols = [c for c in range(COLS) if any(MASK_NP[:, c])]  # only columns with lit LEDs
            cx = random.choice(valid_cols)
            cy = random.randint(0, ROWS - 1)
            self._rings.append({"cx": cx, "cy": cy, "r": 0.0, "bri": 220})  # start radius at 0

        done = []
        for i, ring in enumerate(self._rings):
            ring["r"]   += 8 * dt * self.speed  # expand the ring radius outward
            ring["bri"] *= 0.94                  # fade brightness each frame
            if ring["bri"] < 4: done.append(i); continue  # ring has faded out — remove it

            for r in range(ROWS):
                for c in range(COLS):
                    if not MASK_NP[r, c]: continue
                    dist = math.sqrt((c - ring["cx"]) ** 2 + (r - ring["cy"]) ** 2)  # distance from ring centre
                    diff = abs(dist - ring["r"])   # how close this pixel is to the ring circumference
                    if diff < 1.2:                 # pixels within 1.2 units of the ring edge get lit
                        bri = ring["bri"] * (1 - diff / 1.2)  # brighter at the ring edge, falls off outward
                        frame[r, c] = max(frame[r, c], bri)

        for i in reversed(done): self._rings.pop(i)
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Helix ────────────────────────────────────────────────────────────

class HelixEffect(BaseEffect):
    name = "Helix"
    def __init__(self, speed=2.0): self.speed = speed; self._t = 0.0
    def reset(self): self._t = 0.0

    def tick(self, dt):
        self._t += dt * self.speed   # advance the helix phase
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        for c in range(COLS):
            phase = c / COLS * math.pi * 4 + self._t  # phase varies across columns, creating the spiral look
            ra = int((math.sin(phase) + 1) / 2 * (ROWS - 1))              # strand A row (sin mapped to 0..ROWS-1)
            rb = int((math.sin(phase + math.pi) + 1) / 2 * (ROWS - 1))   # strand B is π out of phase (opposite side)

            if MASK_NP[ra, c]:
                frame[ra, c] = max(frame[ra, c], 255)   # strand A is fully bright
            if MASK_NP[rb, c]:
                frame[rb, c] = max(frame[rb, c], 180)   # strand B is slightly dimmer

            # Draw connecting rungs between the two strands
            lo, hi = min(ra, rb), max(ra, rb)
            for r in range(lo + 1, hi):
                if MASK_NP[r, c]:
                    frame[r, c] = max(frame[r, c], 60)  # rungs are dim (just a structural hint)

        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Fireworks ────────────────────────────────────────────────────────

class FireworksEffect(BaseEffect):
    name = "Fireworks"

    def __init__(self, speed=1.0):
        self.speed      = speed   # NEW: global speed multiplier
        self._particles = []
        self._t         = 0.0

    def reset(self): self._particles.clear(); self._t = 0.0

    def _explode(self):
        cx    = random.randint(8, COLS - 8)   # burst centre (avoid edges)
        cy    = random.randint(1, ROWS - 2)
        count = random.randint(8, 16)         # number of particles per burst
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)   # random outward direction
            speed = random.uniform(3, 12) * self.speed
            self._particles.append({
                "x": float(cx), "y": float(cy),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed * 0.4,  # compressed vertically (matrix is wide, not tall)
                "bri":   255,
                "decay": random.uniform(0.5, 0.85),   # how quickly this particle fades
            })

    def tick(self, dt):
        self._t += dt
        frame = np.zeros((ROWS, COLS), dtype=np.float32)

        if random.random() < 0.8 * dt:   # ~80% chance per second of a new burst
            self._explode()

        done = []
        for i, p in enumerate(self._particles):
            p["x"]  += p["vx"] * dt               # move particle
            p["y"]  += p["vy"] * dt
            p["vy"] += 4 * dt                      # gravity pulls particle downward
            p["bri"] *= p["decay"] ** (dt * 8)    # exponential brightness decay
            if p["bri"] < 6: done.append(i); continue  # particle has faded out
            r, c = int(p["y"]), int(p["x"])
            if 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]:
                frame[r, c] = max(frame[r, c], p["bri"])

        for i in reversed(done): self._particles.pop(i)  # remove faded particles safely
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Bounce ────────────────────────────────────────────────────────────

class BounceEffect(BaseEffect):
    name = "Bounce"

    def __init__(self, speed=1.0):
        self.speed = speed                                               # NEW: global speed multiplier
        self._x    = float(COLS // 2)                                   # ball starts at grid centre
        self._y    = float(ROWS // 2)
        self._vx   = random.choice([-1, 1]) * random.uniform(8, 16) * speed   # random horizontal velocity
        self._vy   = random.choice([-1, 1]) * random.uniform(3, 7)  * speed   # random vertical velocity
        self._buf  = np.zeros((ROWS, COLS), dtype=np.float32)          # persistent buffer for the glow trail

    def reset(self):
        self._x = float(COLS // 2)
        self._y = float(ROWS // 2)
        self._buf[:] = 0

    def tick(self, dt):
        self._x += self._vx * dt   # advance ball position
        self._y += self._vy * dt
        if self._x <= 0 or self._x >= COLS - 1: self._vx *= -1   # bounce off left/right walls
        if self._y <= 0 or self._y >= ROWS - 1: self._vy *= -1   # bounce off top/bottom walls
        self._x = max(0, min(COLS - 1, self._x))                  # clamp to grid bounds
        self._y = max(0, min(ROWS - 1, self._y))

        self._buf *= 0.75   # fade the trail each frame
        # Paint a soft glow blob around the ball position
        for dr in range(-1, 2):
            for dc in range(-2, 3):
                r = int(self._y) + dr
                c = int(self._x) + dc
                if 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]:
                    dist = math.sqrt(dr*dr + dc*dc*0.4)                          # elliptical distance (wider than tall)
                    self._buf[r, c] = max(self._buf[r, c], 255 * max(0, 1 - dist * 0.5))  # brighter at centre

        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ── Wave ─────────────────────────────────────────────────────────────

class WaveEffect(BaseEffect):
    name = "Wave"

    def __init__(self, speed=2.0, waves=3):
        self.speed = speed   # how fast the wave scrolls horizontally
        self.waves = waves   # number of wave crests across the width
        self._t    = 0.0

    def reset(self): self._t = 0.0

    def tick(self, dt):
        self._t += dt * self.speed
        frame = np.zeros((ROWS, COLS), dtype=np.float32)
        for c in range(COLS):
            # Sine wave across columns, mapped to a row position
            center = (math.sin(c / COLS * math.pi * 2 * self.waves + self._t) + 1) / 2 * (ROWS - 1)
            for r in range(ROWS):
                if not MASK_NP[r, c]: continue
                dist = abs(r - center)          # distance from this pixel to the wave centre
                if dist < 2:
                    frame[r, c] = 255 * (1 - dist / 2) ** 2  # smooth falloff within 2 pixels of the wave
        return self._emit(np.clip(frame, 0, 255).astype(np.uint8))


# ── Audio Visualizer ─────────────────────────────────────────────────
# BUG FIX 1 (low response): smoothing was heavily biased toward old values
#   (0.6 * old + 0.4 * new). Now uses a faster attack (0.3 old / 0.7 new).
# BUG FIX 2 (low response): raw linear FFT magnitude compresses quiet
#   frequencies. Now applies a sqrt boost before normalising so quiet
#   audio shows visible bars.
# BUG FIX 3 (low response): peak decay was very slow (1.5×dt). Increased
#   to 3.0×dt so peaks fall faster and the display is more dynamic.

class AudioVisualizer(BaseEffect):
    name = "Audio"

    def __init__(self, sample_rate=22050, chunk=1024, sensitivity=1.0):
        self._sr          = sample_rate   # audio sample rate (Hz)
        self._chunk       = chunk         # number of samples per FFT window
        self._sensitivity = sensitivity   # NEW: boost quiet audio (multiplier before normalise)
        self._bars        = np.zeros(COLS, dtype=np.float32)   # smoothed bar heights (0-1 per column)
        self._peak        = np.zeros(COLS, dtype=np.float32)   # peak hold values per column
        self._stream      = None
        self._buf         = np.zeros(chunk, dtype=np.float32)  # latest audio chunk from callback
        self._available   = False
        self._t           = 0.0
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
        self._buf = indata[:, 0].copy()   # grab mono channel from the latest audio block

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
            # Apply Hanning window to reduce spectral leakage, then FFT
            fft = np.abs(np.fft.rfft(self._buf * np.hanning(len(self._buf))))

            # FIX: sqrt compression boosts quiet signals so they register visually
            fft = np.sqrt(fft)

            nf = len(fft)
            # Average FFT bins into COLS bars (linear frequency mapping)
            bars = np.array([
                np.mean(fft[max(0, int(nf * i / COLS)):max(1, int(nf * (i + 1) / COLS))])
                for i in range(COLS)
            ], dtype=np.float32)

            # Apply sensitivity multiplier before normalising
            bars *= self._sensitivity

            mx = bars.max()
            if mx > 0: bars /= mx   # normalise to 0-1

            # FIX: faster attack (was 0.6/0.4, now 0.3/0.7) so bars respond immediately
            self._bars = self._bars * 0.3 + bars * 0.7

            # FIX: faster peak decay (was 1.5, now 3.0) for a more dynamic display
            self._peak = np.maximum(self._peak * (1 - dt * 3.0), self._bars)

            for c in range(COLS):
                height   = int(self._bars[c] * ROWS)          # bar height in rows
                peak_row = int(self._peak[c] * (ROWS - 1))    # row index for the peak dot
                for r in range(ROWS):
                    dr = ROWS - 1 - r   # flip: r=0 is bottom of display
                    if not MASK_NP[dr, c]: continue
                    if r < height:
                        frame[dr, c] = max(40, int(200 * r / max(1, height)))  # dim at base, bright at top
                    elif r == peak_row:
                        frame[dr, c] = 255   # peak dot is always full brightness
        else:
            # Fallback plasma animation when no audio device is available
            for r in range(ROWS):
                for c in range(COLS):
                    if not MASK_NP[r, c]: continue
                    v = math.sin(c / 4 + self._t) * math.cos(r / 2 + self._t * 0.7)
                    frame[r, c] = int((v + 1) / 2 * 255)

        return logical_to_physical(apply_mask(frame))   # note: calls directly (bypass _emit) to match original


# ── Snake ─────────────────────────────────────────────────────────────
# Auto-playing AI snake that navigates the LED matrix.
# Uses a simple "follow the food, avoid walls and self" heuristic.

class SnakeEffect(BaseEffect):
    name = "Snake"

    def __init__(self, speed=1.0):
        self.speed  = speed   # moves per second multiplier
        self._acc   = 0.0
        self._reset_state()

    def _reset_state(self):
        mid_r = ROWS // 2
        mid_c = COLS // 2
        self._body  = [(mid_r, mid_c), (mid_r, mid_c - 1), (mid_r, mid_c - 2)]
        self._dir   = (0, 1)   # (dr, dc)
        self._food  = self._place_food()
        self._dead  = False
        self._dead_t = 0.0

    def reset(self):
        self._acc = 0.0
        self._reset_state()

    def _valid(self, r, c):
        return 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]

    def _place_food(self):
        body_set = set(self._body)
        candidates = [(r, c) for r in range(ROWS) for c in range(COLS)
                      if MASK_NP[r, c] and (r, c) not in body_set]
        return random.choice(candidates) if candidates else (0, COLS - 1)

    def _choose_dir(self):
        hr, hc = self._body[0]
        fr, fc = self._food
        body_set = set(self._body)

        # Try directions in order of preference: toward food first
        dr_goal = 0 if fr == hr else (1 if fr > hr else -1)
        dc_goal = 0 if fc == hc else (1 if fc > hc else -1)

        candidates = []
        if dr_goal != 0: candidates.append((dr_goal, 0))
        if dc_goal != 0: candidates.append((0, dc_goal))
        # add remaining cardinal directions as fallbacks
        for d in [(0,1),(0,-1),(1,0),(-1,0)]:
            if d not in candidates: candidates.append(d)

        # Avoid reversing into ourselves
        reverse = (-self._dir[0], -self._dir[1])

        for d in candidates:
            if d == reverse: continue
            nr, nc = hr + d[0], hc + d[1]
            if self._valid(nr, nc) and (nr, nc) not in body_set:
                return d

        # No safe move — pick anything that isn't instant self-collision
        for d in [(0,1),(0,-1),(1,0),(-1,0)]:
            if d == reverse: continue
            nr, nc = hr + d[0], hc + d[1]
            if self._valid(nr, nc):
                return d

        return self._dir  # give up, die gracefully

    def tick(self, dt):
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        if self._dead:
            # Flash then restart
            self._dead_t += dt
            if self._dead_t > 1.5:
                self._reset_state()
            else:
                # Blink body on/off
                if int(self._dead_t * 6) % 2 == 0:
                    for r, c in self._body:
                        if MASK_NP[r, c]: frame[r, c] = 80
            return self._emit(frame)

        # Accumulate time; move when threshold crossed
        moves_per_sec = 8 * self.speed
        self._acc += dt
        step = 1.0 / moves_per_sec

        while self._acc >= step:
            self._acc -= step
            self._dir = self._choose_dir()
            hr, hc = self._body[0]
            nr, nc = hr + self._dir[0], hc + self._dir[1]

            if not self._valid(nr, nc) or (nr, nc) in set(self._body[:-1]):
                self._dead   = True
                self._dead_t = 0.0
                break

            self._body.insert(0, (nr, nc))
            if (nr, nc) == self._food:
                self._food = self._place_food()   # ate food — don't shrink
            else:
                self._body.pop()                  # normal move — remove tail

        # Draw food (bright)
        fr, fc = self._food
        if MASK_NP[fr, fc]: frame[fr, fc] = 255

        # Draw body: head bright, tail dims
        n = len(self._body)
        for i, (r, c) in enumerate(self._body):
            if MASK_NP[r, c]:
                bri = 255 if i == 0 else max(40, int(200 * (1 - i / n)))
                frame[r, c] = bri

        return self._emit(frame)


# ── Clock ─────────────────────────────────────────────────────────────
# Displays current local time (HH:MM) in a minimal pixel font.
# Each digit is 3×5, colon is 1×5, with 1-pixel gaps.

class ClockEffect(BaseEffect):
    name = "Clock"

    # 3-wide × 5-tall pixel font for digits 0-9 and colon (:)
    _FONT: dict[str, list[str]] = {
        "0": ["111","101","101","101","111"],
        "1": ["010","110","010","010","111"],
        "2": ["111","001","111","100","111"],
        "3": ["111","001","011","001","111"],
        "4": ["101","101","111","001","001"],
        "5": ["111","100","111","001","111"],
        "6": ["111","100","111","101","111"],
        "7": ["111","001","001","001","001"],
        "8": ["111","101","111","101","111"],
        "9": ["111","101","111","001","111"],
        ":": ["0","1","0","1","0"],   # 1-wide
    }

    def __init__(self):
        self._pulse = 0.0   # for colon blink

    def reset(self): self._pulse = 0.0

    def tick(self, dt):
        import time as _time
        self._pulse += dt
        frame = np.zeros((ROWS, COLS), dtype=np.uint8)

        now   = _time.localtime()
        text  = f"{now.tm_hour:02d}:{now.tm_min:02d}"

        # Measure total width
        def char_w(ch): return 1 if ch == ":" else 3

        total_w = sum(char_w(ch) for ch in text) + len(text) - 1  # chars + gaps
        start_c = max(0, (COLS - total_w) // 2)
        start_r = (ROWS - 5) // 2

        col = start_c
        for ch in text:
            rows_data = self._FONT[ch]
            w = char_w(ch)
            bri = 255
            if ch == ":":
                bri = 255 if int(self._pulse * 2) % 2 == 0 else 60  # blink colon

            for dr, row_str in enumerate(rows_data):
                r = start_r + dr
                if r < 0 or r >= ROWS: continue
                for dc, px in enumerate(row_str):
                    c = col + dc
                    if c < 0 or c >= COLS: continue
                    if px == "1" and MASK_NP[r, c]:
                        frame[r, c] = bri
            col += w + 1  # advance by char width + 1-pixel gap

        return self._emit(frame)


# ── Typing Visualizer ─────────────────────────────────────────────────
# Lights up a column burst on each keypress, rippling outward.
# Uses pynput for global key listening (optional — degrades gracefully).

class TypingEffect(BaseEffect):
    name = "Typing"

    def __init__(self):
        self._buf      = np.zeros((ROWS, COLS), dtype=np.float32)
        self._listener = None
        self._lock_t   = __import__("threading").Lock()
        self._pending  = []   # list of column indices to burst
        self._available = False
        self._start()

    def _start(self):
        try:
            from pynput import keyboard as _kb

            def on_press(key):
                # Map key to a column (spread across COLS)
                try:
                    ch = key.char
                    if ch:
                        idx = ord(ch.lower()) % COLS
                    else:
                        idx = random.randint(0, COLS - 1)
                except AttributeError:
                    idx = random.randint(0, COLS - 1)
                with self._lock_t:
                    self._pending.append(idx)

            self._listener = _kb.Listener(on_press=on_press)
            self._listener.start()
            self._available = True
        except Exception as e:
            print(f"TypingEffect: pynput unavailable ({e}) — falling back to demo mode")

    def reset(self):
        self._buf[:] = 0
        with self._lock_t: self._pending.clear()

    def stop(self):
        if self._listener:
            try: self._listener.stop()
            except: pass
            self._listener = None

    def tick(self, dt):
        # In demo mode (no pynput), fire random bursts occasionally
        if not self._available:
            if random.random() < 3.0 * dt:
                with self._lock_t:
                    self._pending.append(random.randint(0, COLS - 1))

        with self._lock_t:
            bursts, self._pending = self._pending[:], []

        for c in bursts:
            # Vertical burst: full column bright
            for r in range(ROWS):
                if MASK_NP[r, c]:
                    self._buf[r, c] = min(255.0, self._buf[r, c] + 255.0)
            # Spread to neighbours
            for nc in (c - 1, c + 1):
                if 0 <= nc < COLS:
                    for r in range(ROWS):
                        if MASK_NP[r, nc]:
                            self._buf[r, nc] = min(255.0, self._buf[r, nc] + 140.0)

        # Decay
        self._buf *= max(0.0, 1.0 - dt * 4.5)
        return self._emit(np.clip(self._buf, 0, 255).astype(np.uint8))


# ── Registry ─────────────────────────────────────────────────────────

# Master list of all available effect classes
ALL_EFFECTS: list[type[BaseEffect]] = [
    PulseEffect, MatrixRainEffect, RainEffect,
    WipeEffect, PlasmaEffect, NoiseEffect, ScanEffect,
    StarfieldEffect, CometEffect, RippleEffect,
    HelixEffect, FireworksEffect, BounceEffect, WaveEffect,
    SnakeEffect, ClockEffect, TypingEffect,
    AudioVisualizer,
]

EFFECT_NAMES = [e.name for e in ALL_EFFECTS]   # flat list of name strings for UI dropdowns etc.

def make_effect(name: str) -> BaseEffect:
    """Instantiate an effect by name. Raises ValueError if not found."""
    for cls in ALL_EFFECTS:
        if cls.name == name: return cls()
    raise ValueError(f"Unknown effect: {name!r}")
