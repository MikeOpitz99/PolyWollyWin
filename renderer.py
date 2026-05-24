"""
renderer.py — Frame rendering for the 37×12 AniMe Matrix display.

Physical geometry (from mask.csv + config.ini):
  Logical grid : 37 cols × 12 rows = 444 cells
  Active LEDs  : 312 (diagonal cut — row r starts at col r×2)
  LED order    : row-major scan of active cells only

Armoury Crate render parameters (from fire.json / fire.xml):
  scale    = 4.1   (source pixels per logical LED)
  offset_x = -49
  offset_y = -18
  brightness (0-10 AC scale → 0.0-1.0 multiplier)
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageSequence

ROWS = 12
COLS = 37
PHYSICAL_LED_COUNT = 312

# Mask: MASK[r][c] = 1 if that cell has a physical LED
MASK: list[list[int]] = []
for _r in range(ROWS):
    row = [0] * COLS
    for _c in range(_r * 2, COLS):
        row[_c] = 1
    MASK.append(row)

MASK_NP = np.array(MASK, dtype=bool)   # (12, 37)

# Pre-compute flat index list for physical → logical mapping
PHYSICAL_INDICES: list[tuple[int, int]] = [
    (r, c)
    for r in range(ROWS)
    for c in range(COLS)
    if MASK[r][c]
]
assert len(PHYSICAL_INDICES) == PHYSICAL_LED_COUNT


# ------------------------------------------------------------------ #
# Core helpers
# ------------------------------------------------------------------ #

def logical_to_physical(frame: np.ndarray) -> list[int]:
    """
    Convert a (12, 37) uint8 numpy array to 312 physical LED bytes.
    Cells not in MASK are ignored.
    """
    return [int(frame[r, c]) for r, c in PHYSICAL_INDICES]


def physical_to_logical(led_bytes: list[int]) -> np.ndarray:
    """Reverse — 312 bytes → (12, 37) array (holes = 0)."""
    out = np.zeros((ROWS, COLS), dtype=np.uint8)
    for val, (r, c) in zip(led_bytes, PHYSICAL_INDICES):
        out[r, c] = val
    return out


def apply_mask(frame: np.ndarray) -> np.ndarray:
    """Zero out cells that have no physical LED."""
    out = frame.copy()
    out[~MASK_NP] = 0
    return out


def blank_frame() -> np.ndarray:
    return np.zeros((ROWS, COLS), dtype=np.uint8)


def full_frame(brightness: int = 255) -> np.ndarray:
    f = np.full((ROWS, COLS), brightness, dtype=np.uint8)
    return apply_mask(f)


# ------------------------------------------------------------------ #
# Image / GIF rendering
# ------------------------------------------------------------------ #

def _sample_image(
    arr: np.ndarray,
    offset_x: float,
    offset_y: float,
    scale: float,
) -> np.ndarray:
    """Bilinearly sample a grayscale image onto the 37×12 LED grid."""
    h, w = arr.shape
    frame = np.zeros((ROWS, COLS), dtype=np.float32)

    for r in range(ROWS):
        for c in range(COLS):
            sx = c * scale + offset_x
            sy = r * scale + offset_y
            x0 = int(sx);  x1 = x0 + 1
            y0 = int(sy);  y1 = y0 + 1
            x0 = max(0, min(w - 1, x0));  x1 = max(0, min(w - 1, x1))
            y0 = max(0, min(h - 1, y0));  y1 = max(0, min(h - 1, y1))
            fx = sx - int(sx);  fy = sy - int(sy)
            v = (
                arr[y0, x0] * (1 - fx) * (1 - fy)
                + arr[y0, x1] * fx * (1 - fy)
                + arr[y1, x0] * (1 - fx) * fy
                + arr[y1, x1] * fx * fy
            )
            frame[r, c] = v

    return frame


def render_image(
    path: str,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    scale: float | None = None,
    brightness: float = 1.0,
) -> np.ndarray:
    """
    Render a static image (PNG/JPEG/etc.) to a (12, 37) uint8 frame.
    If scale is None it auto-fits the image to fill the grid.
    """
    img = Image.open(path).convert("L")
    w, h = img.size

    if scale is None:
        scale = min(w / COLS, h / ROWS)

    arr = np.array(img, dtype=np.float32)
    frame = _sample_image(arr, offset_x, offset_y, scale)
    frame = np.clip(frame * brightness, 0, 255).astype(np.uint8)
    return apply_mask(frame)


class GifPlayer:
    """
    Pre-renders all frames of a GIF into physical LED byte lists.
    Call next_frame() on each tick.
    """

    def __init__(
        self,
        path: str,
        offset_x: float = -49.0,
        offset_y: float = -18.0,
        scale: float = 4.1,
        brightness: float = 1.0,
    ):
        self.path       = path
        self.frames:    list[list[int]] = []
        self.durations: list[float]    = []   # seconds
        self._idx = 0
        self._load(path, offset_x, offset_y, scale, brightness)

    def _load(self, path, offset_x, offset_y, scale, brightness):
        img = Image.open(path)
        for frame in ImageSequence.Iterator(img):
            arr = np.array(frame.convert("L"), dtype=np.float32)
            logical = _sample_image(arr, offset_x, offset_y, scale)
            logical = np.clip(logical * brightness, 0, 255).astype(np.uint8)
            logical = apply_mask(logical)
            self.frames.append(logical_to_physical(logical))
            self.durations.append(frame.info.get("duration", 40) / 1000.0)

    def current_frame(self) -> list[int]:
        return self.frames[self._idx]

    def current_duration(self) -> float:
        return self.durations[self._idx]

    def advance(self):
        self._idx = (self._idx + 1) % len(self.frames)

    def reset(self):
        self._idx = 0

    def __len__(self):
        return len(self.frames)


def auto_fit_gif(path: str, brightness: float = 1.0) -> GifPlayer:
    """
    Load a GIF and auto-fit it to fill the display.
    Used for drag-and-drop where AC parameters aren't known.
    """
    img = Image.open(path)
    w, h = img.size
    scale = min(w / COLS, h / ROWS)
    offset_x = -(scale * COLS - w) / 2
    offset_y = -(scale * ROWS - h) / 2
    return GifPlayer(path, offset_x=offset_x, offset_y=offset_y, scale=scale, brightness=brightness)
