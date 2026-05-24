from __future__ import annotations

from version import VERSION

"""
app.py — PolyWollyWin system tray app
ROG Strix Flare II Animate custom matrix controller.

Usage:
    python app.py

Requires: PySide6, hidapi, pillow, numpy, sounddevice (optional)
"""

import sys
import time
import threading
from PySide6.QtGui import QIcon
from pathlib import Path

APP_NAME = f"PolyWollyWin v{VERSION}"

import numpy as np
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QObject, QSettings,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QAction,
)
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QComboBox,
    QFileDialog, QFrame, QTabWidget, QScrollArea,
    QSizePolicy, QCheckBox,
)

from transport import Transport
from renderer  import GifPlayer, render_image, auto_fit_gif, blank_frame, logical_to_physical
from effects   import make_effect, EFFECT_NAMES, AudioVisualizer, BaseEffect
from paint     import PaintEditor

APP_NAME    = "PolyWollyWin"
TICK_HZ     = 30          # target frame rate
TICK_MS     = 1000 // TICK_HZ
SETTINGS_ORG = "PolyWollyWin"


# ─────────────────────────────────────────────────────────────────────
# Tray icon — drawn programmatically (no external image needed)
# ─────────────────────────────────────────────────────────────────────

def _make_tray_icon(color: str = "#e8001d") -> QIcon:
    """Draw a small ROG-ish dot-matrix 'W' as the tray icon."""
    px = QPixmap(22, 22)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    # Simple stylised dots
    dots = [
        (2,4),(2,8),(2,12),(2,16),
        (5,16),(8,12),(11,16),(14,16),
        (17,4),(17,8),(17,12),(17,16),
    ]
    for x, y in dots:
        p.drawEllipse(x, y, 3, 3)
    p.end()
    return QIcon(px)


# ─────────────────────────────────────────────────────────────────────
# Driver thread — owns the HID connection, drives the matrix
# ─────────────────────────────────────────────────────────────────────

class MatrixDriver(QObject):
    status_changed = Signal(str)   # "connected" | "disconnected" | "error: ..."

    MODE_BLANK   = "blank"
    MODE_EFFECT  = "effect"
    MODE_GIF     = "gif"
    MODE_IMAGE   = "image"
    MODE_PAINT   = "paint"

    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("assets/pww.ico"))
        self._transport = Transport()
        self._lock      = threading.Lock()
        self._running   = False

        self.mode       = self.MODE_BLANK
        self._effect: BaseEffect | None = None
        self._gif:    GifPlayer  | None = None
        self._static_frame: list[int]   = [0] * 312
        self._brightness = 1.0           # 0.0-1.0 software multiplier
        self._gif_timer  = 0.0

    # ── public API (thread-safe) ──────────────────────────────────── #

    def connect(self):
        try:
            path = self._transport.connect()
            self.status_changed.emit("connected")
            return path
        except Exception as e:
            self.status_changed.emit(f"error: {e}")
            return None

    def disconnect(self):
        self._transport.disconnect()
        self.status_changed.emit("disconnected")

    def set_brightness(self, value: float):
        with self._lock:
            self._brightness = max(0.0, min(1.0, value))

    def set_mode_blank(self):
        with self._lock:
            self.mode = self.MODE_BLANK
            self._effect = None

    def set_mode_effect(self, name: str):
        with self._lock:
            if self._effect and isinstance(self._effect, AudioVisualizer):
                self._effect.stop()
            self._effect = make_effect(name)
            self.mode    = self.MODE_EFFECT

    def set_mode_gif(self, player: GifPlayer):
        with self._lock:
            self._gif      = player
            self._gif_timer = 0.0
            self.mode      = self.MODE_GIF

    def set_mode_image(self, frame: list[int]):
        with self._lock:
            self._static_frame = frame
            self.mode          = self.MODE_IMAGE

    def set_mode_paint(self, frame: list[int]):
        with self._lock:
            self._static_frame = frame
            self.mode          = self.MODE_PAINT

    def update_paint_frame(self, frame: list[int]):
        with self._lock:
            if self.mode == self.MODE_PAINT:
                self._static_frame = frame

    # ── tick (called by QTimer on the main thread) ────────────────── #

    def tick(self, dt: float):
        if not self._transport.connected:
            return

        with self._lock:
            mode = self.mode
            brightness = self._brightness

            if mode == self.MODE_BLANK:
                raw = [0] * 312

            elif mode == self.MODE_EFFECT and self._effect:
                raw = self._effect.tick(dt)

            elif mode == self.MODE_GIF and self._gif:
                raw = self._gif.current_frame()
                self._gif_timer += dt
                if self._gif_timer >= self._gif.current_duration():
                    self._gif_timer = 0.0
                    self._gif.advance()

            elif mode in (self.MODE_IMAGE, self.MODE_PAINT):
                raw = self._static_frame

            else:
                raw = [0] * 312

        # Apply software brightness
        if brightness < 1.0:
            raw = [int(v * brightness) for v in raw]

        try:
            self._transport.send_frame(raw)
        except Exception:
            pass   # silently drop frames on hiccup

    def cleanup(self):
        with self._lock:
            if self._effect and isinstance(self._effect, AudioVisualizer):
                self._effect.stop()
        try:
            self._transport.send_blank()
            self._transport.disconnect()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────
# Control window
# ─────────────────────────────────────────────────────────────────────

class ControlWindow(QWidget):

    def __init__(self, driver: MatrixDriver):
        super().__init__()
        self._driver = driver
        self._last_gif_path = ""

        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setMinimumWidth(560)
        self.setStyleSheet(_DARK_STYLE)

        # Status bar at top
        self._status_label = QLabel("⬤  Disconnected")
        self._status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")

        connect_btn = QPushButton("Connect")
        connect_btn.setFixedWidth(90)
        connect_btn.clicked.connect(self._on_connect)

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        status_row.addWidget(connect_btn)

        # Brightness
        self._brightness_slider = QSlider(Qt.Horizontal)
        self._brightness_slider.setRange(0, 100)
        self._brightness_slider.setValue(100)
        self._brightness_slider.valueChanged.connect(
            lambda v: driver.set_brightness(v / 100.0)
        )
        brightness_row = QHBoxLayout()
        brightness_row.addWidget(QLabel("Brightness"))
        brightness_row.addWidget(self._brightness_slider)
        brightness_row.addWidget(QLabel("100%", objectName="pct_label"))
        self._brightness_slider.valueChanged.connect(
            lambda v: self.findChild(QLabel, "pct_label").setText(f"{v}%")
        )

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._make_effects_tab(), "Effects")
        tabs.addTab(self._make_gif_tab(),     "GIF / Image")
        tabs.addTab(self._make_paint_tab(),   "Paint")

        # Main layout
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addLayout(status_row)
        root.addWidget(_hline())
        root.addLayout(brightness_row)
        root.addWidget(_hline())
        root.addWidget(tabs)

        driver.status_changed.connect(self._on_status)

    # ── tabs ─────────────────────────────────────────────────────── #

    def _make_effects_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Built-in effects:"))

        grid = QGridLayout()
        grid.setSpacing(6)

        # Blank
        blank_btn = QPushButton("⬛  Blank")
        blank_btn.clicked.connect(lambda: self._driver.set_mode_blank())
        grid.addWidget(blank_btn, 0, 0)

        col = 1
        row = 0
        for name in EFFECT_NAMES:
            btn = QPushButton(f"▶  {name}")
            _name = name  # capture
            btn.clicked.connect(lambda _, n=_name: self._driver.set_mode_effect(n))
            grid.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        layout.addLayout(grid)
        layout.addStretch()
        return w

    def _make_gif_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # GIF section
        gif_label = QLabel("GIF file:")
        self._gif_path_label = QLabel("(none)")
        self._gif_path_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self._gif_path_label.setWordWrap(True)

        browse_gif = QPushButton("Browse…")
        browse_gif.setFixedWidth(80)
        browse_gif.clicked.connect(self._browse_gif)

        play_gif = QPushButton("▶ Play")
        play_gif.setFixedWidth(80)
        play_gif.clicked.connect(self._play_gif)

        gif_row = QHBoxLayout()
        gif_row.addWidget(browse_gif)
        gif_row.addWidget(play_gif)
        gif_row.addStretch()

        # Image section
        img_label    = QLabel("Static image:")
        browse_image = QPushButton("Browse…")
        browse_image.setFixedWidth(80)
        browse_image.clicked.connect(self._browse_image)

        layout.addWidget(gif_label)
        layout.addWidget(self._gif_path_label)
        layout.addLayout(gif_row)
        layout.addWidget(_hline())
        layout.addWidget(img_label)
        layout.addWidget(browse_image)
        layout.addStretch()
        return w

    def _make_paint_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        hint = QLabel("Left-click = paint  |  Right-click = erase")
        hint.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._paint_editor = PaintEditor()
        self._paint_editor.frame_ready.connect(self._on_paint_frame)
        scroll.setWidget(self._paint_editor)

        push_btn = QPushButton("▶ Send to Matrix")
        push_btn.clicked.connect(self._push_paint)

        layout.addWidget(scroll)
        layout.addWidget(push_btn)
        return w

    # ── slots ────────────────────────────────────────────────────── #

    def _on_connect(self):
        path = self._driver.connect()
        if path:
            self._status_label.setText(f"⬤  Connected — {path}")
            self._status_label.setStyleSheet("color: #e8001d; font-size: 11px; padding: 4px;")

    def _on_status(self, status: str):
        if status == "connected":
            pass   # handled in _on_connect
        elif status == "disconnected":
            self._status_label.setText("⬤  Disconnected")
            self._status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        else:
            self._status_label.setText(f"⬤  {status}")
            self._status_label.setStyleSheet("color: #f80; font-size: 11px; padding: 4px;")

    def _browse_gif(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GIF", "", "GIF files (*.gif)"
        )
        if path:
            self._last_gif_path = path
            name = Path(path).name
            self._gif_path_label.setText(name)

    def _play_gif(self):
        if not self._last_gif_path:
            return
        try:
            player = auto_fit_gif(self._last_gif_path)
            self._driver.set_mode_gif(player)
        except Exception as e:
            self._gif_path_label.setText(f"Error: {e}")

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        try:
            frame = render_image(path)
            self._driver.set_mode_image(logical_to_physical(frame))
        except Exception as e:
            print(f"Image load error: {e}")

    def _on_paint_frame(self, frame: list[int]):
        # Live-update if already in paint mode
        self._driver.update_paint_frame(frame)

    def _push_paint(self):
        frame = self._paint_editor.canvas.get_physical()
        self._driver.set_mode_paint(frame)

    # ── window close = hide to tray ──────────────────────────────── #

    def closeEvent(self, event):
        event.ignore()
        self.hide()


# ─────────────────────────────────────────────────────────────────────
# System tray
# ─────────────────────────────────────────────────────────────────────

class TrayApp(QSystemTrayIcon):

    def __init__(self, driver: MatrixDriver, window: ControlWindow):
        super().__init__(_make_tray_icon())
        self._driver = driver
        self._window = window

        self.setToolTip(APP_NAME)
        menu = QMenu()

        show_act = QAction("Open PolyWollyWin", menu)
        show_act.triggered.connect(window.show)
        menu.addAction(show_act)

        menu.addSeparator()

        blank_act = QAction("⬛ Blank", menu)
        blank_act.triggered.connect(driver.set_mode_blank)
        menu.addAction(blank_act)

        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activate)

    def _on_activate(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self._window.isVisible():
                self._window.hide()
            else:
                self._window.show()
                self._window.raise_()

    def _quit(self):
        self._driver.cleanup()
        QApplication.quit()


# ─────────────────────────────────────────────────────────────────────
# Style
# ─────────────────────────────────────────────────────────────────────

_DARK_STYLE = """
QWidget {
    background: #1a1a1a;
    color: #e0e0e0;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
}
QTabWidget::pane {
    border: 1px solid #333;
    border-radius: 4px;
}
QTabBar::tab {
    background: #242424;
    color: #aaa;
    padding: 6px 14px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #2d2d2d;
    color: #e8001d;
    border-bottom: 2px solid #e8001d;
}
QPushButton {
    background: #2a2a2a;
    color: #ddd;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 5px 12px;
}
QPushButton:hover  { background: #333; border-color: #e8001d; color: #fff; }
QPushButton:pressed { background: #e8001d; color: #fff; }
QSlider::groove:horizontal {
    height: 4px;
    background: #333;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #e8001d;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #e8001d; border-radius: 2px; }
QLabel { color: #ccc; }
QScrollArea { border: none; background: transparent; }
"""


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #333;")
    return line


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("assets/pww.ico"))
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray not available")
        sys.exit(1)

    driver = MatrixDriver()
    window = ControlWindow(driver)
    tray   = TrayApp(driver, window)
    tray.show()

    # Drive the matrix at TICK_HZ
    _last  = [time.perf_counter()]
    timer  = QTimer()
    timer.setInterval(TICK_MS)

    def _tick():
        now = time.perf_counter()
        dt  = now - _last[0]
        _last[0] = now
        driver.tick(dt)

    timer.timeout.connect(_tick)
    timer.start()

    # Auto-connect on startup
    driver.connect()

    # Show window on first launch
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
