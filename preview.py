"""
preview.py — Read-only 37×12 matrix preview widget.
Same visual style as the paint canvas but just displays — no interaction.
Used in the GIF tab to show the result of offset/scale adjustments live.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy

from renderer import ROWS, COLS, MASK_NP, physical_to_logical

CELL_W = 11
CELL_H = 16
GAP    = 2


class MatrixPreview(QWidget):
    """
    Read-only display of the 37×12 LED grid.
    Call update_frame(physical_bytes) to refresh.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logical = np.zeros((ROWS, COLS), dtype=np.uint8)

        w = COLS * (CELL_W + GAP) + GAP
        h = ROWS * (CELL_H + GAP) + GAP
        self.setFixedSize(w, h)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip("Live matrix preview — reflects current offset/scale settings")

    def update_physical(self, led_bytes: list[int]):
        """Accepts 312-byte physical LED list and repaints."""
        self._logical = physical_to_logical(led_bytes)
        self.update()

    def update_logical(self, frame: np.ndarray):
        """Accepts (12, 37) numpy array directly."""
        self._logical = frame.astype(np.uint8)
        self.update()

    def clear(self):
        self._logical[:] = 0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(10, 10, 10))

        for r in range(ROWS):
            for c in range(COLS):
                x = c * (CELL_W + GAP) + GAP
                y = r * (CELL_H + GAP) + GAP

                if not MASK_NP[r, c]:
                    painter.fillRect(x, y, CELL_W, CELL_H, QColor(6, 6, 6))
                    continue

                v = int(self._logical[r, c])
                if v == 0:
                    color = QColor(20, 20, 20)
                else:
                    # Warm amber-orange — matches real LED colour temperature
                    color = QColor(min(255, v), int(v * 0.44), 0)

                painter.fillRect(x, y, CELL_W, CELL_H, color)

                # Subtle cell border
                painter.setPen(QPen(QColor(30, 30, 30), 1))
                painter.drawRect(x, y, CELL_W - 1, CELL_H - 1)
