"""
app.py — PolyWollyWin system tray app
ROG Strix Flare II Animate custom matrix controller.

Usage:
    python app.py

Requires: PySide6, hidapi, pillow, numpy, sounddevice (optional)
"""

from __future__ import annotations

# Detach console when launched via double-click or `py app.py` on Windows
import ctypes, sys
if sys.platform == "win32":
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.kernel32.FreeConsole()

import sys
import time
import json
import threading
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QObject
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QFileDialog,
    QFrame, QTabWidget, QScrollArea, QSizePolicy,
    QGroupBox, QCheckBox, QMessageBox,
)

from version   import VERSION
from transport import Transport
from renderer  import (
    GifPlayer, render_image, auto_fit_gif,
    blank_frame, logical_to_physical,
    ROWS, COLS, PHYSICAL_LED_COUNT,
)
from effects   import make_effect, EFFECT_NAMES, AudioVisualizer, BaseEffect
from paint     import PaintEditor
from preview   import MatrixPreview

APP_NAME     = f"PolyWollyWin v{VERSION}"
AUTHOR_NAME  = "Mike Opitz"
REPO_URL     = "https://github.com/MikeOpitz99/PolyWollyWin"
RELEASES_URL = f"{REPO_URL}/releases"
LATEST_RELEASE_API = (
    "https://api.github.com/repos/"
    "MikeOpitz99/PolyWollyWin/releases/latest"
)

TICK_HZ = 30
TICK_MS = 1000 // TICK_HZ


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _make_icon(color="#e8001d") -> QIcon:
    """Load assets/pww.ico if available, fall back to drawn icon."""
    ico_path = Path("assets/pww.ico")
    if ico_path.exists():
        return QIcon(str(ico_path))
    px = QPixmap(22, 22)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color)); p.setPen(Qt.NoPen)
    for x, y in [(2,4),(2,8),(2,12),(2,16),(5,16),(8,12),
                 (11,16),(14,16),(17,4),(17,8),(17,12),(17,16)]:
        p.drawEllipse(x, y, 3, 3)
    p.end()
    return QIcon(px)


def _sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color:#222;"); return f


def _sep_v() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setFixedHeight(18); f.setStyleSheet("color:#333;"); return f


def _label(text, color="#888", size=11) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"color:{color}; font-size:{size}px;")
    return l


def _uniform_grid(buttons: list[QPushButton], cols: int = 3) -> QGridLayout:
    grid = QGridLayout()
    grid.setSpacing(6)
    for i, btn in enumerate(buttons):
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(30)
        grid.addWidget(btn, i // cols, i % cols)
    for c in range(cols):
        grid.setColumnStretch(c, 1)
    return grid


# ─────────────────────────────────────────────────────────────────────
# Update checker
# ─────────────────────────────────────────────────────────────────────

def check_for_updates(parent=None, silent=False):
    try:
        with urlopen(LATEST_RELEASE_API, timeout=5) as response:
            data = json.loads(response.read().decode())

        latest  = data["tag_name"].replace("v", "").strip()
        current = VERSION.strip()

        if latest != current:
            msg = QMessageBox(parent)
            msg.setWindowTitle("Update Available")
            msg.setText(
                f"A newer version is available.\n\n"
                f"Current: v{current}\n"
                f"Latest:  v{latest}"
            )
            dl_btn = msg.addButton("Open Releases", QMessageBox.AcceptRole)
            msg.addButton(QMessageBox.Close)
            msg.exec()
            if msg.clickedButton() == dl_btn:
                QDesktopServices.openUrl(QUrl(RELEASES_URL))

        elif not silent:
            QMessageBox.information(
                parent, "No Updates",
                f"You are running the latest version:\n\nv{current}"
            )

    except Exception as e:
        if not silent:
            msg = str(e)
            if "404" in msg:
                msg = "No GitHub releases exist yet.\n\nPublish a release first."
            QMessageBox.warning(parent, "Update Check Failed", msg)


# ─────────────────────────────────────────────────────────────────────
# Brightness + Contrast bar
# ─────────────────────────────────────────────────────────────────────

class BCBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(_label("☀"))
        self.bri = QSlider(Qt.Horizontal)
        self.bri.setRange(0, 100); self.bri.setValue(100)
        self._bri_val = QLabel("100%"); self._bri_val.setFixedWidth(34)
        self._bri_val.setStyleSheet("color:#aaa; font-size:11px;")
        self.bri.valueChanged.connect(lambda v: self._bri_val.setText(f"{v}%"))
        layout.addWidget(self.bri); layout.addWidget(self._bri_val)

        layout.addWidget(_sep_v())

        layout.addWidget(_label("◑"))
        self.con = QSlider(Qt.Horizontal)
        self.con.setRange(10, 300); self.con.setValue(100)
        self._con_val = QLabel("1.0×"); self._con_val.setFixedWidth(34)
        self._con_val.setStyleSheet("color:#aaa; font-size:11px;")
        self.con.valueChanged.connect(lambda v: self._con_val.setText(f"{v/100:.1f}×"))
        layout.addWidget(self.con); layout.addWidget(self._con_val)


# ─────────────────────────────────────────────────────────────────────
# Quick Controls popup
# ─────────────────────────────────────────────────────────────────────

class QuickControls(QWidget):
    def __init__(self, driver: "MatrixDriver", parent=None):
        super().__init__(parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._driver = driver
        self.setStyleSheet(_STYLE)
        self.setFixedWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        title = QLabel("PolyWollyWin  Quick Controls")
        title.setStyleSheet("color:#e8001d; font-size:12px; font-weight:bold;")
        layout.addWidget(title)
        layout.addWidget(_sep())

        self._bc = BCBar()
        self._bc.bri.valueChanged.connect(lambda v: driver.set_brightness(v / 100.0))
        self._bc.con.valueChanged.connect(lambda v: driver.set_contrast(v / 100.0))
        layout.addWidget(self._bc)
        layout.addWidget(_sep())

        layout.addWidget(_label("Effects", "#888"))
        blank_btn = QPushButton("⬛  Blank")
        blank_btn.clicked.connect(driver.set_mode_blank)
        btns = [blank_btn]
        for name in EFFECT_NAMES:
            b = QPushButton(f"▶  {name}"); _n = name
            b.clicked.connect(lambda _, n=_n: driver.set_mode_effect(n))
            btns.append(b)
        layout.addLayout(_uniform_grid(btns, cols=2))

    def show_near_tray(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 8,
                  screen.bottom() - self.height() - 8)
        self.show(); self.raise_(); self.activateWindow()

    def sync(self, bri: float, con: float):
        self._bc.bri.setValue(int(bri * 100))
        self._bc.con.setValue(int(con * 100))

    def focusOutEvent(self, event):
        self.hide()


# ─────────────────────────────────────────────────────────────────────
# Matrix driver
# ─────────────────────────────────────────────────────────────────────

class MatrixDriver(QObject):
    status_changed = Signal(str)
    frame_rendered = Signal(list)

    MODE_BLANK  = "blank"
    MODE_EFFECT = "effect"
    MODE_GIF    = "gif"
    MODE_IMAGE  = "image"
    MODE_PAINT  = "paint"

    def __init__(self):
        super().__init__()
        self._transport  = Transport()
        self._lock       = threading.Lock()
        self.mode        = self.MODE_BLANK
        self._effect: BaseEffect | None = None
        self._gif: GifPlayer | None     = None
        self._static: list[int]         = [0] * PHYSICAL_LED_COUNT
        self._brightness = 1.0
        self._contrast   = 1.0
        self._gif_timer  = 0.0

    def connect(self) -> str | None:
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

    @property
    def connected(self): return self._transport.connected

    def set_brightness(self, v: float):
        with self._lock: self._brightness = max(0.0, min(1.0, v))

    def set_contrast(self, v: float):
        with self._lock: self._contrast = max(0.1, min(3.0, v))

    def set_mode_blank(self):
        with self._lock: self.mode = self.MODE_BLANK; self._effect = None

    def set_mode_effect(self, name: str):
        with self._lock:
            if isinstance(self._effect, AudioVisualizer): self._effect.stop()
            self._effect = make_effect(name); self.mode = self.MODE_EFFECT

    def set_mode_gif(self, player: GifPlayer):
        with self._lock:
            self._gif = player; self._gif_timer = 0.0; self.mode = self.MODE_GIF

    def set_mode_image(self, frame: list[int]):
        with self._lock: self._static = frame; self.mode = self.MODE_IMAGE

    def set_mode_paint(self, frame: list[int]):
        with self._lock: self._static = frame; self.mode = self.MODE_PAINT

    def update_paint(self, frame: list[int]):
        with self._lock:
            if self.mode == self.MODE_PAINT: self._static = frame

    def tick(self, dt: float):
        if not self._transport.connected: return
        with self._lock:
            mode = self.mode; bri = self._brightness; con = self._contrast
            if   mode == self.MODE_BLANK:  raw = [0] * PHYSICAL_LED_COUNT
            elif mode == self.MODE_EFFECT and self._effect: raw = list(self._effect.tick(dt))
            elif mode == self.MODE_GIF and self._gif:
                raw = list(self._gif.current_frame())
                self._gif_timer += dt
                if self._gif_timer >= self._gif.current_duration():
                    self._gif_timer = 0.0; self._gif.advance()
            elif mode in (self.MODE_IMAGE, self.MODE_PAINT): raw = list(self._static)
            else: raw = [0] * PHYSICAL_LED_COUNT

        if con != 1.0:
            raw = [max(0, min(255, int((v - 128) * con + 128))) for v in raw]
        if bri < 1.0:
            raw = [int(v * bri) for v in raw]

        try: self._transport.send_frame(raw)
        except Exception: pass

        self.frame_rendered.emit(raw)

    def cleanup(self):
        with self._lock:
            if isinstance(self._effect, AudioVisualizer): self._effect.stop()
        try: self._transport.send_blank(); self._transport.disconnect()
        except Exception: pass


# ─────────────────────────────────────────────────────────────────────
# GIF tab with live preview
# ─────────────────────────────────────────────────────────────────────

class GifTab(QWidget):
    def __init__(self, driver: MatrixDriver):
        super().__init__()
        self._driver   = driver
        self._gif_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._file_label = QLabel("(no file selected)")
        self._file_label.setStyleSheet("color:#666; font-size:11px;")

        browse_btn  = QPushButton("Browse GIF…")
        play_btn    = QPushButton("▶  Play")
        autofit_btn = QPushButton("Auto-fit")
        stop_btn    = QPushButton("⬛  Blank")
        browse_btn.clicked.connect(self._browse)
        play_btn.clicked.connect(self._play)
        autofit_btn.clicked.connect(self._autofit)
        stop_btn.clicked.connect(driver.set_mode_blank)

        file_row = QHBoxLayout(); file_row.setSpacing(6)
        for btn in (browse_btn, play_btn, autofit_btn, stop_btn):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(30)
            file_row.addWidget(btn)

        pos_group = QGroupBox("Position & Scale")
        pg = QGridLayout(pos_group); pg.setSpacing(6)

        def _row(label, lo, hi, default, scale=1):
            lbl = _label(label)
            sld = QSlider(Qt.Horizontal)
            sld.setRange(lo, hi); sld.setValue(default)
            val = QLabel(str(default if scale == 1 else f"{default/scale:.1f}"))
            val.setFixedWidth(40); val.setStyleSheet("color:#ccc; font-size:11px;")
            if scale != 1:
                sld.valueChanged.connect(lambda v, l=val, s=scale: l.setText(f"{v/s:.1f}"))
            else:
                sld.valueChanged.connect(lambda v, l=val: l.setText(str(v)))
            sld.valueChanged.connect(self._preview_update)
            return lbl, sld, val

        lbl_x, self._ox, val_x = _row("Offset X", -500, 500, -49)
        lbl_y, self._oy, val_y = _row("Offset Y", -200, 200, -18)
        lbl_s, self._sc, val_s = _row("Scale",      1,  500,  41, scale=10)

        for i, (l, s, v) in enumerate([(lbl_x, self._ox, val_x),
                                        (lbl_y, self._oy, val_y),
                                        (lbl_s, self._sc, val_s)]):
            pg.addWidget(l, i, 0); pg.addWidget(s, i, 1); pg.addWidget(v, i, 2)
        pg.setColumnStretch(1, 1)

        preview_group = QGroupBox("Preview  (frame 0 — updates with sliders)")
        pvl = QVBoxLayout(preview_group); pvl.setContentsMargins(6, 8, 6, 6)
        self._preview = MatrixPreview()
        pvl.addWidget(self._preview, alignment=Qt.AlignHCenter)
        pvl.addWidget(_label("Adjust sliders above — preview updates automatically", "#555", 10),
                      alignment=Qt.AlignHCenter)

        img_group = QGroupBox("Static Image")
        il = QHBoxLayout(img_group)
        img_btn = QPushButton("Browse & Send Image…")
        img_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        img_btn.setMinimumHeight(30)
        img_btn.clicked.connect(self._browse_image)
        il.addWidget(img_btn)

        layout.addWidget(self._file_label)
        layout.addLayout(file_row)
        layout.addWidget(pos_group)
        layout.addWidget(preview_group)
        layout.addWidget(img_group)
        layout.addStretch()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open GIF", "", "GIF files (*.gif)")
        if path:
            self._gif_path = path
            self._file_label.setText(Path(path).name)
            self._file_label.setStyleSheet("color:#aaa; font-size:11px;")
            self._preview_update()

    def _preview_update(self):
        if not self._gif_path: return
        try:
            player = GifPlayer(self._gif_path,
                               offset_x=self._ox.value(),
                               offset_y=self._oy.value(),
                               scale=self._sc.value() / 10.0)
            self._preview.update_physical(player.frames[0])
        except Exception:
            pass

    def _play(self):
        if not self._gif_path: return
        try:
            player = GifPlayer(self._gif_path,
                               offset_x=self._ox.value(),
                               offset_y=self._oy.value(),
                               scale=self._sc.value() / 10.0)
            self._driver.set_mode_gif(player)
        except Exception as e:
            self._file_label.setText(f"Error: {e}")

    def _autofit(self):
        if not self._gif_path: return
        try:
            from PIL import Image
            img = Image.open(self._gif_path); w, h = img.size
            scale = min(w / COLS, h / ROWS)
            self._ox.setValue(int(-(scale * COLS - w) / 2))
            self._oy.setValue(int(-(scale * ROWS - h) / 2))
            self._sc.setValue(int(scale * 10))
        except Exception as e:
            self._file_label.setText(f"Error: {e}")

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path: return
        try:
            frame = render_image(path)
            phys  = logical_to_physical(frame)
            self._driver.set_mode_image(phys)
            self._preview.update_physical(phys)
        except Exception as e:
            print(f"Image error: {e}")


# ─────────────────────────────────────────────────────────────────────
# Control window
# ─────────────────────────────────────────────────────────────────────

class ControlWindow(QWidget):
    def __init__(self, driver: MatrixDriver):
        super().__init__()
        self._driver = driver
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_make_icon())
        self.setMinimumWidth(620)
        self.setStyleSheet(_STYLE)

        # Status row
        self._status = QLabel("⬤  Disconnected")
        self._status.setStyleSheet("color:#555;")
        conn_btn = QPushButton("Connect")
        conn_btn.setFixedWidth(80); conn_btn.setMinimumHeight(30)
        conn_btn.clicked.connect(self._connect)

        status_row = QHBoxLayout()
        status_row.addWidget(self._status); status_row.addStretch()
        status_row.addWidget(conn_btn)

        # Global BC bar
        self._bc = BCBar()
        self._bc.bri.valueChanged.connect(lambda v: driver.set_brightness(v / 100.0))
        self._bc.con.valueChanged.connect(lambda v: driver.set_contrast(v / 100.0))

        # Tabs
        self._gif_tab = GifTab(driver)
        tabs = QTabWidget()
        tabs.addTab(self._effects_tab(), "Effects")
        tabs.addTab(self._gif_tab,       "GIF / Image")
        tabs.addTab(self._paint_tab(),   "Paint")

        # Footer
        self._debug_label = QLabel()
        self._debug_label.setStyleSheet("color:#555; font-size:10px;")

        self._close_to_tray = QCheckBox("Close to tray")
        self._close_to_tray.setChecked(True)
        self._close_to_tray.setStyleSheet("color:#666; font-size:10px;")

        self._startup = QCheckBox("Run at startup")
        self._startup.setStyleSheet("color:#666; font-size:10px;")
        self._startup.setChecked(self._get_startup())
        self._startup.stateChanged.connect(self._set_startup)

        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("color:#555; font-size:10px;")

        author_label = QLabel(f"by {AUTHOR_NAME}")
        author_label.setStyleSheet("color:#444; font-size:10px;")

        github_btn = QPushButton("GitHub")
        github_btn.setFixedHeight(22)
        github_btn.setFixedWidth(60)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))

        update_btn = QPushButton("Check Updates")
        update_btn.setFixedHeight(22)
        update_btn.setFixedWidth(100)
        update_btn.clicked.connect(lambda: check_for_updates(self))

        footer = QHBoxLayout()
        footer.addWidget(self._close_to_tray)
        footer.addSpacing(8)
        footer.addWidget(self._startup)
        footer.addSpacing(8)
        footer.addWidget(version_label)
        footer.addSpacing(6)
        footer.addWidget(author_label)
        footer.addSpacing(10)
        footer.addWidget(self._debug_label)
        footer.addStretch()
        footer.addWidget(github_btn)
        footer.addWidget(update_btn)

        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.addLayout(status_row)
        root.addWidget(_sep())
        root.addWidget(self._bc)
        root.addWidget(_sep())
        root.addWidget(tabs)
        root.addWidget(_sep())
        root.addLayout(footer)

        driver.status_changed.connect(self._on_status)

    # ── tabs ─────────────────────────────────────────────────────────

    def _effects_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        blank_btn = QPushButton("⬛  Blank")
        blank_btn.clicked.connect(self._driver.set_mode_blank)
        btns = [blank_btn]
        for name in EFFECT_NAMES:
            b = QPushButton(f"▶  {name}"); _n = name
            b.clicked.connect(lambda _, n=_n: self._driver.set_mode_effect(n))
            btns.append(b)
        layout.addLayout(_uniform_grid(btns, cols=3))
        layout.addStretch()
        return w

    def _paint_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._paint = PaintEditor()
        self._paint.frame_ready.connect(self._driver.update_paint)
        scroll.setWidget(self._paint)
        send_btn = QPushButton("▶  Send to Matrix")
        send_btn.setMinimumHeight(30)
        send_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        send_btn.clicked.connect(lambda: self._driver.set_mode_paint(
            self._paint.canvas.get_physical()
        ))
        layout.addWidget(scroll)
        layout.addWidget(send_btn)
        return w

    # ── slots ─────────────────────────────────────────────────────────

    def _connect(self):
        path = self._driver.connect()
        if path:
            self._status.setText(f"⬤  {path}")
            self._status.setStyleSheet("color:#e8001d;")

    def _on_status(self, s: str):
        if s == "connected": pass
        elif s == "disconnected":
            self._status.setText("⬤  Disconnected")
            self._status.setStyleSheet("color:#555;")
        else:
            self._status.setText(f"⚠  {s}")
            self._status.setStyleSheet("color:#f80;")

    def update_debug_info(self, dt: float):
        fps  = int(1.0 / dt) if dt > 0 else 0
        mode = self._driver.mode.upper()
        conn = "Connected" if self._driver.connected else "Disconnected"
        self._debug_label.setText(
            f"Device: {conn}   FPS: {fps}   Mode: {mode}"
        )

    def _get_startup(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            winreg.QueryValueEx(key, "PolyWollyWin")
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def _set_startup(self, state: int):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            if state:
                import sys
                exe = sys.executable if not getattr(sys, "frozen", False) \
                    else sys.executable
                winreg.SetValueEx(key, "PolyWollyWin", 0,
                                  winreg.REG_SZ, f'"{exe}" "{__file__}"')
            else:
                try:
                    winreg.DeleteValue(key, "PolyWollyWin")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Startup registry error: {e}")

    def sync_quick_controls(self, qc: QuickControls):
        self._bc.bri.valueChanged.connect(
            lambda v: qc.sync(v / 100.0, self._bc.con.value() / 100.0))
        self._bc.con.valueChanged.connect(
            lambda v: qc.sync(self._bc.bri.value() / 100.0, v / 100.0))

    def closeEvent(self, event):
        if self._close_to_tray.isChecked():
            event.ignore(); self.hide()
        else:
            self._driver.cleanup(); QApplication.quit()


# ─────────────────────────────────────────────────────────────────────
# System tray
# ─────────────────────────────────────────────────────────────────────

class TrayApp(QSystemTrayIcon):
    def __init__(self, driver: MatrixDriver, qc: QuickControls, window: ControlWindow):
        super().__init__(_make_icon())
        self._driver = driver
        self._qc     = qc
        self._window = window
        self.setToolTip(APP_NAME)
        self._build_menu()

    def _build_menu(self):
        menu = QMenu(); menu.setStyleSheet(_MENU_STYLE)

        open_act = QAction(f"⚙  Open {APP_NAME}", menu)
        open_act.triggered.connect(self._show_window)
        menu.addAction(open_act)

        qc_act = QAction("🎛  Quick Controls", menu)
        qc_act.triggered.connect(self._qc.show_near_tray)
        menu.addAction(qc_act)

        menu.addSeparator()

        blank_act = QAction("⬛  Blank", menu)
        blank_act.triggered.connect(self._driver.set_mode_blank)
        menu.addAction(blank_act)

        fx_menu = menu.addMenu("▶  Effects")
        fx_menu.setStyleSheet(_MENU_STYLE)
        for name in EFFECT_NAMES:
            act = QAction(name, fx_menu); _n = name
            act.triggered.connect(lambda _, n=_n: self._driver.set_mode_effect(n))
            fx_menu.addAction(act)

        menu.addSeparator()

        gh_act = QAction("GitHub", menu)
        gh_act.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        menu.addAction(gh_act)

        menu.addSeparator()

        quit_act = QAction("✕  Quit", menu)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

        self.setContextMenu(menu)
        self.activated.connect(self._activated)

    def _show_window(self):
        self._window.show(); self._window.raise_(); self._window.activateWindow()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger: self._show_window()

    def _quit(self):
        self._driver.cleanup(); QApplication.quit()


# ─────────────────────────────────────────────────────────────────────
# Style
# ─────────────────────────────────────────────────────────────────────

_STYLE = """
QWidget {
    background: #111;
    color: #ddd;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #252525;
    border-radius: 5px;
    margin-top: 8px;
    padding-top: 8px;
    color: #555;
    font-size: 11px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #666; }
QTabWidget::pane { border: 1px solid #222; border-radius: 4px; }
QTabBar::tab {
    background: #181818; color: #666;
    padding: 6px 18px;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
}
QTabBar::tab:selected { background: #1e1e1e; color: #e8001d; border-bottom: 2px solid #e8001d; }
QTabBar::tab:hover    { color: #bbb; }
QPushButton {
    background: #1c1c1c; color: #ccc;
    border: 1px solid #2c2c2c; border-radius: 4px;
    padding: 5px 10px; text-align: center;
}
QPushButton:hover  { background: #262626; border-color: #e8001d; color: #fff; }
QPushButton:pressed { background: #e8001d; color: #fff; border-color: #e8001d; }
QCheckBox { color: #666; font-size: 10px; }
QCheckBox::indicator { width: 12px; height: 12px; border: 1px solid #444; border-radius: 2px; background: #1a1a1a; }
QCheckBox::indicator:checked { background: #e8001d; border-color: #e8001d; }
QSlider::groove:horizontal { height: 3px; background: #252525; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #e8001d; width: 11px; height: 11px;
    margin: -4px 0; border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #e8001d; border-radius: 2px; }
QLabel  { color: #bbb; }
QScrollArea { border: none; background: transparent; }
QScrollBar:horizontal { height: 8px; background: #181818; }
QScrollBar::handle:horizontal { background: #2e2e2e; border-radius: 4px; min-width: 20px; }
"""

_MENU_STYLE = """
QMenu {
    background: #111; color: #ccc;
    border: 1px solid #252525;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    padding: 4px 0;
}
QMenu::item { padding: 5px 20px; }
QMenu::item:selected { background: #e8001d; color: #fff; }
QMenu::separator { height: 1px; background: #222; margin: 3px 0; }
"""


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(_make_icon())
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray not available"); sys.exit(1)

    driver  = MatrixDriver()
    qc      = QuickControls(driver)
    window  = ControlWindow(driver)
    window.sync_quick_controls(qc)
    tray    = TrayApp(driver, qc, window)
    tray.show()

    _last = [time.perf_counter()]
    timer = QTimer()
    timer.setInterval(TICK_MS)
    def _tick():
        now = time.perf_counter(); dt = now - _last[0]; _last[0] = now
        driver.tick(dt)
        window.update_debug_info(dt)
    timer.timeout.connect(_tick)
    timer.start()

    driver.connect()
    window.show()

    # Silent update check 3s after launch
    QTimer.singleShot(3000, lambda: check_for_updates(window, silent=True))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
