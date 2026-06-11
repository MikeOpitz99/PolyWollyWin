"""
preview.py — Read-only 37×12 matrix preview widget.

Column-offset circular preview for the ROG Strix Flare II Animate matrix.

Important:
- Columns are vertically staggered.
- Odd columns are shifted down by _HALF pixels.
- This is a visual preview/hit-layout fix only. It does not change the
  physical LED byte mapping handled by renderer.py.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy

from renderer import ROWS, COLS, MASK_NP, physical_to_logical

CELL_W = 12
CELL_H = 12
GAP    = 2
_HALF  = 6


def _col_y_offset(c: int) -> int:
    """Vertical stagger for physical-looking preview."""
    return _HALF if (c % 2 == 1) else 0


class MatrixPreview(QWidget):
    """
    Read-only display of the 37×12 LED grid.
    Call update_physical(physical_bytes) to refresh.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logical = np.zeros((ROWS, COLS), dtype=np.uint8)

        w = COLS * (CELL_W + GAP) + GAP
        h = ROWS * (CELL_H + GAP) + GAP + _HALF
        self.setFixedSize(w, h)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip("Live matrix preview — columns are vertically offset")

    def update_physical(self, led_bytes: list[int]):
        """Accepts physical LED list and repaints."""
        self._logical = physical_to_logical(led_bytes)
        self.update()

    def update_logical(self, frame: np.ndarray):
        """Accepts a (ROWS, COLS) numpy array directly."""
        self._logical = frame.astype(np.uint8)
        self.update()

    def clear(self):
        self._logical[:] = 0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(10, 10, 10))

        for r in range(ROWS):
            for c in range(COLS):
                x = c * (CELL_W + GAP) + GAP
                y = r * (CELL_H + GAP) + GAP + _col_y_offset(c)

                if not MASK_NP[r, c]:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(6, 6, 6))
                    painter.drawEllipse(x, y, CELL_W, CELL_H)
                    continue

                v = int(self._logical[r, c])
                if v == 0:
                    color = QColor(20, 20, 20)
                else:
                    color = QColor(min(255, v), int(v * 0.44), 0)

                painter.setPen(QPen(QColor(34, 34, 34), 1))
                painter.setBrush(color)
                painter.drawEllipse(x, y, CELL_W, CELL_H)
