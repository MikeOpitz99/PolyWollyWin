"""
paint.py — 37×12 LED paint editor widget (PySide6).
Click to toggle pixels, drag to paint. Brightness slider per cell.
Emits frame_changed(list[int]) signal when the frame is updated.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QSizePolicy,
)
from renderer import ROWS, COLS, MASK_NP, logical_to_physical, apply_mask, blank_frame


CELL_W = 14
CELL_H = 20
GAP    = 2


class PaintCanvas(QWidget):
    frame_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame    = blank_frame().copy().astype(np.uint8)
        self._painting = False
        self._erase    = False
        self._brush_v  = 255

        w = COLS * (CELL_W + GAP) + GAP
        h = ROWS * (CELL_H + GAP) + GAP
        self.setFixedSize(w, h)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # ---------------------------------------------------------------- #

    def set_brush(self, value: int):
        self._brush_v = max(0, min(255, value))

    def clear(self):
        self._frame[:] = 0
        self.update()
        self._emit()

    def fill(self):
        for r in range(ROWS):
            for c in range(COLS):
                if MASK_NP[r, c]:
                    self._frame[r, c] = self._brush_v
        self.update()
        self._emit()

    def invert(self):
        for r in range(ROWS):
            for c in range(COLS):
                if MASK_NP[r, c]:
                    self._frame[r, c] = 255 - self._frame[r, c]
        self.update()
        self._emit()

    def get_physical(self) -> list[int]:
        return logical_to_physical(apply_mask(self._frame))

    def load_frame(self, logical: np.ndarray):
        self._frame = logical.copy()
        self.update()
        self._emit()

    def _emit(self):
        self.frame_changed.emit(self.get_physical())

    # ---------------------------------------------------------------- #

    def _cell_at(self, pos: QPoint) -> tuple[int, int] | None:
        c = pos.x() // (CELL_W + GAP)
        r = pos.y() // (CELL_H + GAP)
        if 0 <= r < ROWS and 0 <= c < COLS and MASK_NP[r, c]:
            return r, c
        return None

    def _paint_at(self, pos: QPoint):
        cell = self._cell_at(pos)
        if cell:
            r, c = cell
            self._frame[r, c] = 0 if self._erase else self._brush_v
            self.update()
            self._emit()

    def mousePressEvent(self, event: QMouseEvent):
        self._erase    = event.button() == Qt.RightButton
        self._painting = True
        self._paint_at(event.position().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._painting:
            self._paint_at(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._painting = False

    # ---------------------------------------------------------------- #

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        bg = QColor(18, 18, 18)
        painter.fillRect(self.rect(), bg)

        for r in range(ROWS):
            for c in range(COLS):
                x = c * (CELL_W + GAP) + GAP
                y = r * (CELL_H + GAP) + GAP

                if not MASK_NP[r, c]:
                    # Hole — draw dimmer indicator
                    painter.fillRect(x, y, CELL_W, CELL_H, QColor(10, 10, 10))
                    continue

                v = int(self._frame[r, c])
                if v == 0:
                    color = QColor(30, 30, 30)
                else:
                    color = QColor(v, v // 2, 0)   # orange-ish like the real LEDs

                painter.fillRect(x, y, CELL_W, CELL_H, color)

                # Border
                painter.setPen(QPen(QColor(50, 50, 50), 1))
                painter.drawRect(x, y, CELL_W - 1, CELL_H - 1)


class PaintEditor(QWidget):
    frame_ready = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = PaintCanvas()
        self.canvas.frame_changed.connect(self.frame_ready)

        # Controls
        brush_label = QLabel("Brush:")
        self.brush_slider = QSlider(Qt.Horizontal)
        self.brush_slider.setRange(0, 255)
        self.brush_slider.setValue(255)
        self.brush_slider.setFixedWidth(120)
        self.brush_slider.valueChanged.connect(self.canvas.set_brush)

        clear_btn  = QPushButton("Clear")
        fill_btn   = QPushButton("Fill")
        invert_btn = QPushButton("Invert")
        clear_btn.clicked.connect(self.canvas.clear)
        fill_btn.clicked.connect(self.canvas.fill)
        invert_btn.clicked.connect(self.canvas.invert)

        for btn in (clear_btn, fill_btn, invert_btn):
            btn.setFixedWidth(60)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(brush_label)
        toolbar.addWidget(self.brush_slider)
        toolbar.addSpacing(8)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(fill_btn)
        toolbar.addWidget(invert_btn)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(toolbar)
        layout.addWidget(self.canvas)
