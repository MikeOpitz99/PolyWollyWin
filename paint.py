"""
paint.py — Enhanced 37×12 LED paint editor.
Features: multi-brightness palette, contrast slider, brush size, fill tools.
"""

from __future__ import annotations
import numpy as np
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QSizePolicy, QFrame, QSpinBox,
)
from renderer import ROWS, COLS, MASK_NP, logical_to_physical, apply_mask, blank_frame

CELL_W = 14
CELL_H = 20
GAP    = 2

# Brightness palette swatches (label, value, display color)
PALETTE = [
    ("0",   0,   "#0d0d0d"),
    ("32",  32,  "#2a1a00"),
    ("64",  64,  "#3d2500"),
    ("96",  96,  "#5c3800"),
    ("128", 128, "#7a4b00"),
    ("160", 160, "#9e6200"),
    ("192", 192, "#c47a00"),
    ("224", 224, "#e89400"),
    ("255", 255, "#ffb400"),
]


class PaletteButton(QPushButton):
    def __init__(self, label, value, color, parent=None):
        super().__init__(parent)
        self.value = value
        self.setFixedSize(28, 28)
        self.setToolTip(f"Brightness {value}")
        self.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                border: 1px solid #444;
                border-radius: 3px;
            }}
            QPushButton:checked {{
                border: 2px solid #e8001d;
            }}
            QPushButton:hover {{
                border: 1px solid #aaa;
            }}
        """)
        self.setCheckable(True)


class PaintCanvas(QWidget):
    frame_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame    = blank_frame().copy().astype(np.uint8)
        self._painting = False
        self._erase    = False
        self._brush_v  = 255
        self._contrast = 1.0

        w = COLS * (CELL_W + GAP) + GAP
        h = ROWS * (CELL_H + GAP) + GAP
        self.setFixedSize(w, h)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_brush(self, value: int):
        self._brush_v = max(0, min(255, value))

    def set_contrast(self, value: float):
        """Apply contrast to entire canvas (1.0 = unchanged)."""
        self._contrast = value
        # Apply contrast relative to midpoint
        f = self._frame.astype(np.float32)
        f = (f - 128.0) * value + 128.0
        self._frame = np.clip(f, 0, 255).astype(np.uint8)
        self.update()
        self._emit()

    def clear(self):
        self._frame[:] = 0
        self.update(); self._emit()

    def fill(self):
        for r in range(ROWS):
            for c in range(COLS):
                if MASK_NP[r, c]: self._frame[r, c] = self._brush_v
        self.update(); self._emit()

    def invert(self):
        for r in range(ROWS):
            for c in range(COLS):
                if MASK_NP[r, c]: self._frame[r, c] = 255 - self._frame[r, c]
        self.update(); self._emit()

    def get_physical(self) -> list[int]:
        return logical_to_physical(apply_mask(self._frame))

    def load_frame(self, logical: np.ndarray):
        self._frame = logical.copy(); self.update(); self._emit()

    def _emit(self):
        self.frame_changed.emit(self.get_physical())

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
            self.update(); self._emit()

    def mousePressEvent(self, event: QMouseEvent):
        self._erase    = event.button() == Qt.RightButton
        self._painting = True
        self._paint_at(event.position().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._painting: self._paint_at(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._painting = False

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(14, 14, 14))

        for r in range(ROWS):
            for c in range(COLS):
                x = c * (CELL_W + GAP) + GAP
                y = r * (CELL_H + GAP) + GAP
                if not MASK_NP[r, c]:
                    painter.fillRect(x, y, CELL_W, CELL_H, QColor(8, 8, 8))
                    continue
                v = int(self._frame[r, c])
                if v == 0:
                    color = QColor(22, 22, 22)
                else:
                    # Warm amber-orange gradient like real LEDs
                    r_ch = min(255, int(v))
                    g_ch = int(v * 0.44)
                    b_ch = 0
                    color = QColor(r_ch, g_ch, b_ch)
                painter.fillRect(x, y, CELL_W, CELL_H, color)
                painter.setPen(QPen(QColor(38, 38, 38), 1))
                painter.drawRect(x, y, CELL_W - 1, CELL_H - 1)


class PaintEditor(QWidget):
    frame_ready = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = PaintCanvas()
        self.canvas.frame_changed.connect(self.frame_ready)

        # ── Palette row ───────────────────────────────────────────── #
        palette_label = QLabel("Brightness:")
        palette_label.setStyleSheet("color:#888; font-size:10px;")
        palette_row = QHBoxLayout()
        palette_row.setSpacing(3)
        palette_row.addWidget(palette_label)

        self._palette_btns: list[PaletteButton] = []
        for label, value, color in PALETTE:
            btn = PaletteButton(label, value, color)
            btn.clicked.connect(lambda _, b=btn: self._select_palette(b))
            palette_row.addWidget(btn)
            self._palette_btns.append(btn)
        self._palette_btns[-1].setChecked(True)  # default = full white

        palette_row.addSpacing(8)

        # Custom brush slider
        brush_label = QLabel("Custom:")
        brush_label.setStyleSheet("color:#888; font-size:10px;")
        self._brush_slider = QSlider(Qt.Horizontal)
        self._brush_slider.setRange(0, 255)
        self._brush_slider.setValue(255)
        self._brush_slider.setFixedWidth(80)
        self._brush_slider.valueChanged.connect(self._on_brush_slider)
        palette_row.addWidget(brush_label)
        palette_row.addWidget(self._brush_slider)
        palette_row.addStretch()

        # ── Contrast + tools row ──────────────────────────────────── #
        contrast_label = QLabel("Contrast:")
        contrast_label.setStyleSheet("color:#888; font-size:10px;")
        self._contrast_slider = QSlider(Qt.Horizontal)
        self._contrast_slider.setRange(10, 300)  # 0.1x to 3.0x
        self._contrast_slider.setValue(100)
        self._contrast_slider.setFixedWidth(100)
        self._contrast_val_label = QLabel("1.0×")
        self._contrast_val_label.setFixedWidth(30)
        self._contrast_val_label.setStyleSheet("color:#aaa; font-size:10px;")
        apply_contrast_btn = QPushButton("Apply")
        apply_contrast_btn.setFixedWidth(50)
        apply_contrast_btn.setStyleSheet("font-size:10px; padding:2px 6px;")
        apply_contrast_btn.clicked.connect(self._apply_contrast)
        self._contrast_slider.valueChanged.connect(
            lambda v: self._contrast_val_label.setText(f"{v/100:.1f}×")
        )

        clear_btn  = QPushButton("Clear")
        fill_btn   = QPushButton("Fill")
        invert_btn = QPushButton("Invert")
        for btn in (clear_btn, fill_btn, invert_btn):
            btn.setFixedWidth(52)
            btn.setStyleSheet("font-size:10px; padding:2px 6px;")
        clear_btn.clicked.connect(self.canvas.clear)
        fill_btn.clicked.connect(self.canvas.fill)
        invert_btn.clicked.connect(self.canvas.invert)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(4)
        tools_row.addWidget(contrast_label)
        tools_row.addWidget(self._contrast_slider)
        tools_row.addWidget(self._contrast_val_label)
        tools_row.addWidget(apply_contrast_btn)
        tools_row.addSpacing(12)
        tools_row.addWidget(clear_btn)
        tools_row.addWidget(fill_btn)
        tools_row.addWidget(invert_btn)
        tools_row.addStretch()

        # ── Hint ─────────────────────────────────────────────────── #
        hint = QLabel("Left-click: paint  ·  Right-click: erase  ·  Drag to draw")
        hint.setStyleSheet("color:#555; font-size:10px;")

        # ── Frame animation row ───────────────────────────────────── #
        # Up to 3 paint frames for simple animations.
        # Clicking a frame button switches the canvas to that frame.
        self._frames: list[np.ndarray] = [
            blank_frame().copy().astype(np.uint8) for _ in range(3)
        ]
        self._current_frame_idx = 0
        self._anim_timer = None   # QTimer, set when animating

        frame_row = QHBoxLayout(); frame_row.setSpacing(4)
        frame_row.addWidget(QLabel("Frames:"))
        self._frame_btns: list[QPushButton] = []
        for i in range(3):
            b = QPushButton(f"F{i+1}")
            b.setFixedWidth(32); b.setFixedHeight(22)
            b.setCheckable(True)
            b.setStyleSheet("font-size:10px; padding:1px 3px;")
            b.clicked.connect(lambda _, idx=i: self._switch_frame(idx))
            self._frame_btns.append(b)
            frame_row.addWidget(b)
        self._frame_btns[0].setChecked(True)

        frame_row.addSpacing(8)

        self._anim_btn = QPushButton("▶ Animate")
        self._anim_btn.setFixedHeight(22)
        self._anim_btn.setStyleSheet("font-size:10px; padding:1px 6px;")
        self._anim_btn.clicked.connect(self._toggle_animate)
        frame_row.addWidget(self._anim_btn)

        fps_label = QLabel("FPS:")
        fps_label.setStyleSheet("color:#888; font-size:10px;")
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 30); self._fps_spin.setValue(4)
        self._fps_spin.setFixedWidth(46); self._fps_spin.setFixedHeight(22)
        self._fps_spin.setStyleSheet(
            "QSpinBox{background:#1a1a1a;color:#ccc;border:1px solid #333;"
            "font-size:10px;padding:1px 2px;}"
        )
        frame_row.addWidget(fps_label)
        frame_row.addWidget(self._fps_spin)
        frame_row.addStretch()

        # ── File I/O row ──────────────────────────────────────────── #
        io_row = QHBoxLayout(); io_row.setSpacing(4)
        save_btn  = QPushButton("⬆ Export PNG")
        load_btn  = QPushButton("⬇ Import PNG")
        save_btn.setFixedHeight(22); load_btn.setFixedHeight(22)
        for btn in (save_btn, load_btn):
            btn.setStyleSheet("font-size:10px; padding:1px 6px;")
        save_btn.clicked.connect(self._export_png)
        load_btn.clicked.connect(self._import_png)
        io_row.addWidget(save_btn)
        io_row.addWidget(load_btn)
        io_row.addStretch()

        # ── Layout ───────────────────────────────────────────────── #
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addLayout(palette_row)
        layout.addLayout(tools_row)
        layout.addWidget(hint)
        layout.addLayout(frame_row)
        layout.addLayout(io_row)
        layout.addWidget(self.canvas)

    # ── Frame management ──────────────────────────────────────────── #

    def _switch_frame(self, idx: int):
        # Save current canvas state to the current frame slot
        self._frames[self._current_frame_idx] = self.canvas._frame.copy()
        # Load the new frame
        self._current_frame_idx = idx
        self.canvas.load_frame(self._frames[idx])
        for i, btn in enumerate(self._frame_btns):
            btn.setChecked(i == idx)

    def _toggle_animate(self):
        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()
            self._anim_btn.setText("▶ Animate")
        else:
            # Save current frame before animating
            self._frames[self._current_frame_idx] = self.canvas._frame.copy()
            if self._anim_timer is None:
                from PySide6.QtCore import QTimer as _QTimer
                self._anim_timer = _QTimer()
                self._anim_timer.timeout.connect(self._anim_tick)
            interval = max(33, int(1000 / max(1, self._fps_spin.value())))
            self._anim_timer.setInterval(interval)
            self._anim_timer.start()
            self._anim_btn.setText("⏹ Stop")

    def _anim_tick(self):
        next_idx = (self._current_frame_idx + 1) % 3
        self._switch_frame(next_idx)
        # Emit so the driver can pick it up if the Paint tab is live
        self.frame_ready.emit(self.canvas.get_physical())

    # ── PNG export / import ───────────────────────────────────────── #

    def _export_png(self):
        from PySide6.QtWidgets import QFileDialog as _FD
        path, _ = _FD.getSaveFileName(self, "Export paint frame as PNG", "frame.png",
                                       "PNG images (*.png)")
        if not path:
            return
        try:
            from PIL import Image
            frame = apply_mask(self.canvas._frame)
            from renderer import physical_to_logical, PHYSICAL_LED_COUNT
            # Scale up by a factor for a visible PNG (each LED = 8×8 px block)
            SCALE = 8
            img_arr = np.zeros((ROWS * SCALE, COLS * SCALE), dtype=np.uint8)
            for r in range(ROWS):
                for c in range(COLS):
                    v = int(frame[r, c])
                    img_arr[r*SCALE:(r+1)*SCALE, c*SCALE:(c+1)*SCALE] = v
            Image.fromarray(img_arr, mode="L").save(path)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox as _MB
            _MB.warning(self, "Export failed", str(e))

    def _import_png(self):
        from PySide6.QtWidgets import QFileDialog as _FD
        path, _ = _FD.getOpenFileName(self, "Import PNG as paint frame", "",
                                       "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            from PIL import Image
            img = Image.open(path).convert("L").resize((COLS, ROWS), Image.LANCZOS)
            arr = np.array(img, dtype=np.uint8)
            self.canvas.load_frame(apply_mask(arr))
            self._frames[self._current_frame_idx] = self.canvas._frame.copy()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox as _MB
            _MB.warning(self, "Import failed", str(e))

    def _select_palette(self, selected: PaletteButton):
        for btn in self._palette_btns:
            btn.setChecked(btn is selected)
        self._brush_slider.setValue(selected.value)
        self.canvas.set_brush(selected.value)

    def _on_brush_slider(self, v: int):
        self.canvas.set_brush(v)
        for btn in self._palette_btns:
            btn.setChecked(False)

    def _apply_contrast(self):
        factor = self._contrast_slider.value() / 100.0
        self.canvas.set_contrast(factor)
        self._contrast_slider.setValue(100)
        self._contrast_val_label.setText("1.0×")
