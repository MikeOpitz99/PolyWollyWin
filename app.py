"""
app.py — PolyWollyWin system tray app
ROG Strix Flare II Animate custom matrix controller.

Usage:
    python app.py

Requires: PySide6, hidapi, pillow, numpy, sounddevice (optional), pynput (optional)
"""

from __future__ import annotations

# Detach console when launched via double-click or `py app.py` on Windows
import ctypes, sys
if sys.platform == "win32":
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.kernel32.FreeConsole()

import sys
import os
import re
import time
import json
import threading
import traceback
from pathlib import Path

import numpy as np

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QObject, QSettings, QSize
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QDesktopServices, QMovie
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QFileDialog,
    QFrame, QTabWidget, QScrollArea, QSizePolicy,
    QGroupBox, QCheckBox, QMessageBox, QListWidget,
    QComboBox, QDoubleSpinBox, QLineEdit, QInputDialog,
    QProgressBar,
)

from version import VERSION
from transport import Transport
from renderer import (
    GifPlayer, render_image, auto_fit_gif,
    blank_frame, logical_to_physical,
    ROWS, COLS, PHYSICAL_LED_COUNT,
)
from effects import (
    make_effect, EFFECT_NAMES, ALL_EFFECTS, AudioVisualizer,
    SpectrumAudioVisualizer, TypingEffect, BaseEffect,
    AUDIO_VISUALIZERS,
)
from paint import PaintEditor
from preview import MatrixPreview

APP_NAME   = f"PolyWollyWin v{VERSION}"
AUTHOR_NAME = "Mike Opitz"
REPO_URL    = "https://github.com/MikeOpitz99/PolyWollyWin"
RELEASES_URL = f"{REPO_URL}/releases"
LATEST_RELEASE_API = (
    "https://api.github.com/repos/"
    "MikeOpitz99/PolyWollyWin/releases/latest"
)

TICK_HZ = 30
TICK_MS  = 1000 // TICK_HZ

PRESET_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PolyWollyWin" / "presets"
PRESET_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PolyWollyWin" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STARTUP_CRASH_LOG = LOG_DIR / "startup_crash.log"


def _write_startup_crash_log(exc_type, exc_value, exc_tb) -> str:
    """Write a full startup traceback and return the log path."""
    details = "".join(
        traceback.format_exception(exc_type, exc_value, exc_tb)
    )
    try:
        STARTUP_CRASH_LOG.write_text(details, encoding="utf-8")
    except Exception:
        pass
    return str(STARTUP_CRASH_LOG)

# ─────────────────────────────────────────────────────────────────────
# Preset manager  (JSON files, not registry)
# ─────────────────────────────────────────────────────────────────────

class PresetManager:
    """
    Saves and loads named effect presets as individual JSON files in
    %LOCALAPPDATA%/PolyWollyWin/presets/.

    Preset schema:
      { "name": str, "effect": str, "params": {attr: value},
        "blend_effect": str, "blend_params": {attr: value}, "blend_alpha": int,
        "brightness": int, "contrast": int }
    """

    def __init__(self, directory: Path = PRESET_DIR):
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_') or "preset"
        return self._dir / f"{safe}.json"

    def save(self, preset: dict):
        """Write preset dict to disk.  Overwrites if name already exists."""
        path = self._path(preset["name"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(preset, f, indent=2)

    def load_all(self) -> list[dict]:
        """Return all presets sorted by name."""
        out = []
        for p in sorted(self._dir.glob("*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception:
                pass
        return out

    def delete(self, name: str):
        p = self._path(name)
        if p.exists():
            p.unlink()

    def export_to_file(self, dest: str):
        """Export all presets as a single JSON array file."""
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(self.load_all(), f, indent=2)

    def import_from_file(self, src: str):
        """Import presets from a single JSON array file (merges, overwrites on name collision)."""
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        for p in data:
            if isinstance(p, dict) and "name" in p:
                self.save(p)


# ─────────────────────────────────────────────────────────────────────
# Startup splash
# ─────────────────────────────────────────────────────────────────────

class StartupSplash(QWidget):
    """Simple startup splash with logo and fake progress."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setObjectName("StartupSplash")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #101010;
                border: 1px solid #2a2a2a;
                border-radius: 16px;
            }
            QLabel#SplashTitle {
                color: #f2f2f2;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#SplashSubtitle {
                color: #999;
                font-size: 11px;
            }
            QProgressBar {
                min-height: 14px;
                max-height: 14px;
                border: 1px solid #2a2a2a;
                border-radius: 7px;
                background: #171717;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #e8001d;
                border-radius: 6px;
            }
        """)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)

        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setFixedSize(273, 204)

        self._movie = None
        movie_path = _resource_path("assets/pwwAnim.gif")
        if movie_path.exists():
            movie = QMovie(str(movie_path))
            if movie.isValid():
                movie.setScaledSize(self.logo.size())
                self.logo.setMovie(movie)
                self._movie = movie
                movie.start()

        # Static fallback only if the GIF is unavailable or invalid.
        if self._movie is None:
            logo_path = _resource_path("assets/pww.png")
            if logo_path.exists():
                pm = QPixmap(str(logo_path))
                if not pm.isNull():
                    self.logo.setPixmap(
                        pm.scaled(
                            self.logo.size(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    )

        lay.addWidget(self.logo, 0, Qt.AlignCenter)

        self.title = QLabel("Starting PolyWollyWin")
        self.title.setObjectName("SplashTitle")
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title)

        self.subtitle = QLabel("Initializing...")
        self.subtitle.setObjectName("SplashSubtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.subtitle)

        self.error_details = QLabel("")
        self.error_details.setWordWrap(True)
        self.error_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error_details.setStyleSheet(
            "color:#ff8a8a; font-family:Consolas; font-size:10px; "
            "background:#180608; border:1px solid #4a1118; "
            "border-radius:6px; padding:8px;"
        )
        self.error_details.hide()
        lay.addWidget(self.error_details)

        self.error_buttons = QHBoxLayout()
        self.copy_error_btn = QPushButton("Copy Error")
        self.exit_btn = QPushButton("Exit")
        self.copy_error_btn.clicked.connect(self._copy_error)
        self.exit_btn.clicked.connect(QApplication.quit)
        self.copy_error_btn.hide()
        self.exit_btn.hide()
        self.error_buttons.addStretch()
        self.error_buttons.addWidget(self.copy_error_btn)
        self.error_buttons.addWidget(self.exit_btn)
        lay.addLayout(self.error_buttons)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        lay.addWidget(self.bar)

        self.resize(380, 370)

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.left() + (geo.width() - self.width()) // 2,
            geo.top() + (geo.height() - self.height()) // 2,
        )

    def set_status(self, text: str, value: int):
        self.subtitle.setText(text)
        self.bar.setValue(max(0, min(100, int(value))))
        QApplication.processEvents()

    def finish_later(self, ms: int = 250):
        self.bar.setValue(100)
        QApplication.processEvents()
        QTimer.singleShot(ms, self._finish)

    def show_error(self, exc: BaseException, log_path: str):
        """Turn the splash into a persistent startup error screen."""
        if self._movie is not None:
            self._movie.stop()

        self.title.setText("PolyWollyWin Failed to Start")
        self.title.setStyleSheet(
            "color:#ff5f6d; font-size:20px; font-weight:700;"
        )

        error_code = type(exc).__name__
        error_message = str(exc).strip() or "No error message was provided."
        summary = f"{error_code}: {error_message}"

        self.subtitle.setText(
            "Startup stopped before PolyWollyWin was ready."
        )
        self.error_details.setText(
            f"{summary}\n\nFull traceback:\n{log_path}"
        )
        self.error_details.show()

        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.bar.setStyleSheet("""
            QProgressBar {
                min-height:14px;
                max-height:14px;
                border:1px solid #4a1118;
                border-radius:7px;
                background:#171717;
            }
            QProgressBar::chunk {
                background:#b00020;
                border-radius:6px;
            }
        """)

        self.copy_error_btn.show()
        self.exit_btn.show()
        self.resize(500, 500)
        self.center_on_screen()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()

    def _copy_error(self):
        QApplication.clipboard().setText(
            self.error_details.text()
        )

    def _finish(self):
        if self._movie is not None:
            self._movie.stop()
        self.close()


# ─────────────────────────────────────────────────────────────────────
# Settings persistence
# ─────────────────────────────────────────────────────────────────────

class Settings:
    """Persists PolyWollyWin state to registry (Windows) / ini (other)."""
    _ORG = "PolyWollyWin"
    _APP = "PolyWollyWin"

    def __init__(self):
        self._s = QSettings(self._ORG, self._APP)

    def get_effect_speed(self)  -> float: return float(self._s.value("effect_speed", 1.0))
    def get_brightness(self)    -> int:   return int(self._s.value("brightness", 100))
    def get_contrast(self)      -> int:   return int(self._s.value("contrast", 100))
    def get_last_effect(self)   -> str:   return str(self._s.value("last_effect", ""))
    def get_last_gif(self)      -> str:   return str(self._s.value("last_gif", ""))
    def get_gif_ox(self)        -> int:   return int(self._s.value("gif_ox", -49))
    def get_gif_oy(self)        -> int:   return int(self._s.value("gif_oy", -18))
    def get_gif_scale(self)     -> int:   return int(self._s.value("gif_scale", 41))
    def get_close_to_tray(self) -> bool:  return self._s.value("close_to_tray", "true").lower() == "true"
    def get_start_minimized(self) -> bool: return self._s.value("start_minimized", "false").lower() == "true"
    def get_persist_enabled(self) -> bool: return self._s.value("persist_enabled", "false").lower() == "true"
    def get_last_mode(self)     -> str:   return str(self._s.value("last_mode", ""))
    def get_blend_effect(self)  -> str:   return str(self._s.value("blend_effect", ""))
    def get_blend_alpha(self)   -> int:   return int(self._s.value("blend_alpha", 0))
    def get_audio_sensitivity(self) -> int: return int(self._s.value("audio_sensitivity", 900))
    def get_audio_boost(self)       -> int: return int(self._s.value("audio_boost", 1800))
    def get_audio_falloff(self)     -> int: return int(self._s.value("audio_falloff", 80))
    def get_audio_floor(self)       -> int: return int(self._s.value("audio_floor", 8))
    def get_audio_visualizer(self) -> str:
        return str(self._s.value("audio_visualizer", "Oscilloscope"))

    def get_audio_defaults(self) -> dict:
        try:
            raw = str(self._s.value("audio_defaults", "{}"))
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_audio_mode_defaults(self, name: str) -> dict:
        data = self.get_audio_defaults().get(name, {})
        return data if isinstance(data, dict) else {}

    def get_effect_defaults(self) -> dict:
        try:
            raw = str(self._s.value("effect_defaults", "{}"))
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_effect_default(self, name: str) -> dict:
        data = self.get_effect_defaults().get(name, {})
        return data if isinstance(data, dict) else {}

    def set_effect_speed(self, v: float): self._s.setValue("effect_speed", v)
    def set_brightness(self, v: int):     self._s.setValue("brightness", v)
    def set_contrast(self, v: int):       self._s.setValue("contrast", v)
    def set_last_effect(self, v: str):    self._s.setValue("last_effect", v)
    def set_last_gif(self, v: str):       self._s.setValue("last_gif", v)
    def set_gif_ox(self, v: int):         self._s.setValue("gif_ox", v)
    def set_gif_oy(self, v: int):         self._s.setValue("gif_oy", v)
    def set_gif_scale(self, v: int):      self._s.setValue("gif_scale", v)
    def set_close_to_tray(self, v: bool): self._s.setValue("close_to_tray", str(v).lower())
    def set_start_minimized(self, v: bool):
        self._s.setValue("start_minimized", str(v).lower())
        self._s.sync()
    def set_persist_enabled(self, v: bool): self._s.setValue("persist_enabled", str(v).lower())
    def set_last_mode(self, v: str):      self._s.setValue("last_mode", v)
    def set_blend_effect(self, v: str):   self._s.setValue("blend_effect", v)
    def set_blend_alpha(self, v: int):    self._s.setValue("blend_alpha", v)
    def set_audio_sensitivity(self, v: int): self._s.setValue("audio_sensitivity", v)
    def set_audio_boost(self, v: int):       self._s.setValue("audio_boost", v)
    def set_audio_falloff(self, v: int):     self._s.setValue("audio_falloff", v)
    def set_audio_floor(self, v: int):       self._s.setValue("audio_floor", v)
    def set_audio_visualizer(self, name: str):
        self._s.setValue("audio_visualizer", name)

    def set_audio_mode_defaults(self, name: str, values: dict):
        data = self.get_audio_defaults()
        data[name] = dict(values)
        self._s.setValue("audio_defaults", json.dumps(data))
        self._s.sync()

    def set_effect_default(self, name: str, values: dict):
        data = self.get_effect_defaults()
        data[name] = dict(values)
        self._s.setValue("effect_defaults", json.dumps(data))
        self._s.sync()

    def clear_effect_default(self, name: str):
        data = self.get_effect_defaults()
        data.pop(name, None)
        self._s.setValue("effect_defaults", json.dumps(data))
        self._s.sync()

    def save_all(self): self._s.sync()
    def clear(self):    self._s.clear(); self._s.sync()


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _effect_class(name: str):
    for cls in ALL_EFFECTS:
        if cls.name == name:
            return cls
    return None


def _runtime_effect_values(name: str, raw_values: dict | None) -> dict:
    """Convert ParamPanel raw slider values into effect constructor values."""
    cls = _effect_class(name)
    if cls is None or not raw_values:
        return {}

    params = dict(getattr(cls, "PARAMS", {}) or {})
    out = {}
    for attr, raw in raw_values.items():
        spec = params.get(attr)
        if spec is None:
            continue
        if spec.get("type") == "text":
            out[attr] = str(raw)
        else:
            scale = float(spec.get("scale", 1.0))
            out[attr] = float(raw) / scale
    return out


def _resource_path(relative: str) -> Path:
    """Resolve an asset in source and PyInstaller one-file builds."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def _make_icon() -> QIcon:
    """
    Load the real PolyWollyWin icon.

    Prefer the Windows ICO for the tray/taskbar and fall back to the PNG.
    """
    for relative in ("assets/pww.ico", "assets/pww.png"):
        path = _resource_path(relative)
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon

    fallback = QPixmap(64, 64)
    fallback.fill(Qt.transparent)
    painter = QPainter(fallback)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#e8001d"))
    painter.drawEllipse(8, 8, 48, 48)
    painter.end()
    return QIcon(fallback)


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

def _version_key(version: str) -> tuple[int, ...]:
    """Return a comparable numeric version tuple, e.g. v2.5.0 -> (2, 5, 0)."""
    cleaned = str(version).strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts: list[int] = []
    for part in cleaned.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)

# Keep active update requests alive until Qt reports completion.
_ACTIVE_UPDATE_CHECKS: set[QNetworkAccessManager] = set()


def check_for_updates(parent=None, silent=False):
    """
    Check GitHub releases using Qt's network stack.

    Using QNetworkAccessManager avoids urllib's lazy imports from PyInstaller's
    temporary base_library.zip, which can disappear during one-file lifecycle
    transitions and produce misleading _MEI... errors.
    """
    owner = parent if isinstance(parent, QObject) else QApplication.instance()
    manager = QNetworkAccessManager(owner)
    _ACTIVE_UPDATE_CHECKS.add(manager)

    request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
    request.setRawHeader(b"Accept", b"application/vnd.github+json")
    request.setRawHeader(
        b"User-Agent",
        f"PolyWollyWin/{VERSION}".encode("ascii", errors="ignore"),
    )

    reply = manager.get(request)

    timeout = QTimer(manager)
    timeout.setSingleShot(True)
    timeout.setInterval(8000)

    def cleanup():
        timeout.stop()
        _ACTIVE_UPDATE_CHECKS.discard(manager)
        reply.deleteLater()
        manager.deleteLater()

    def show_failure(message: str):
        if not silent:
            QMessageBox.warning(
                parent,
                "Update Check Failed",
                f"Could not check for updates.\n\n{message}",
            )

    def on_timeout():
        if reply.isRunning():
            reply.abort()
        show_failure("The request timed out.")
        cleanup()

    def on_finished():
        if manager not in _ACTIVE_UPDATE_CHECKS:
            return

        try:
            if reply.error() != QNetworkReply.NoError:
                status = reply.attribute(
                    QNetworkRequest.HttpStatusCodeAttribute
                )
                if status == 404:
                    show_failure(
                        "No published GitHub release was found yet."
                    )
                else:
                    detail = reply.errorString().strip()
                    show_failure(detail or "Network request failed.")
                return

            raw = bytes(reply.readAll())
            data = json.loads(raw.decode("utf-8"))
            latest = str(data["tag_name"]).replace("v", "").strip()
            current = VERSION.strip().replace("v", "")

            latest_key = _version_key(latest)
            current_key = _version_key(current)

            if latest_key > current_key:
                msg = QMessageBox(parent)
                msg.setWindowTitle("Update Available")
                msg.setText(
                    f"A newer version is available.\n\n"
                    f"Current: v{current}\n"
                    f"Latest:  v{latest}"
                )
                dl_btn = msg.addButton(
                    "Open Releases", QMessageBox.AcceptRole
                )
                msg.addButton(QMessageBox.Close)
                msg.exec()
                if msg.clickedButton() == dl_btn:
                    QDesktopServices.openUrl(QUrl(RELEASES_URL))
            elif not silent:
                if current_key > latest_key:
                    message = (
                        f"No update needed.\n\n"
                        f"Current local build: v{current}\n"
                        f"Latest GitHub release: v{latest}"
                    )
                else:
                    message = (
                        "You are running the latest version:"
                        f"\n\nv{current}"
                    )
                QMessageBox.information(
                    parent, "No Updates", message
                )

        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            show_failure("GitHub returned an unexpected response.")
        except Exception:
            # Do not expose internal PyInstaller paths or implementation details.
            show_failure("An unexpected error occurred.")
        finally:
            cleanup()

    timeout.timeout.connect(on_timeout)
    reply.finished.connect(on_finished)
    timeout.start()


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
# Per-effect parameter panel
# ─────────────────────────────────────────────────────────────────────

class KittKarrSwitch(QWidget):
    """
    iOS-style KITT/KARR switch using asset wordmark PNGs.

    Expected assets:
      assets/kitt.png
      assets/karr.png

    value 0 = KITT, knob left/red
    value 1 = KARR, knob right/orange
    """

    valueChanged = Signal(int)

    def __init__(self, value: int = 0, parent=None):
        super().__init__(parent)
        self._value = 1 if int(value) else 0
        self.setFixedSize(156, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("KITT / KARR")

        self._kitt_pix = self._load_asset("kitt.png")
        self._karr_pix = self._load_asset("karr.png")

    def _load_asset(self, filename: str) -> QPixmap:
        candidates = [
            Path("assets") / filename,
            Path(__file__).resolve().parent / "assets" / filename,
        ]
        for path in candidates:
            try:
                if path.exists():
                    pm = QPixmap(str(path))
                    if not pm.isNull():
                        return pm
            except Exception:
                pass
        return QPixmap()

    def value(self) -> int:
        return self._value

    def setValue(self, value: int, emit: bool = True):
        value = 1 if int(value) else 0
        if value == self._value:
            self.update()
            return
        self._value = value
        self.update()
        if emit:
            self.valueChanged.emit(self._value)

    def mousePressEvent(self, event):
        self.setValue(0 if self._value else 1)

    def _draw_wordmark_or_text(self, painter: QPainter, pixmap: QPixmap, text: str,
                               lane_left: int, lane_right: int, color: QColor):
        avail_w = max(20, lane_right - lane_left)
        avail_h = max(12, self.height() - 8)

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                avail_w,
                avail_h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            tx = lane_left + max(0, (avail_w - scaled.width()) // 2)
            ty = (self.height() - scaled.height()) // 2
            painter.drawPixmap(tx, ty, scaled)
            return

        # Fallback if asset is missing.
        painter.setPen(color)
        painter.drawText(lane_left, 0, avail_w, self.height(), Qt.AlignCenter, text)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h // 2

        # Track: black like the app background.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#000000"))
        p.drawRoundedRect(0, 0, w, h, radius, radius)

        # Subtle outline.
        p.setPen(QColor("#2b2b2b"))
        p.drawRoundedRect(0, 0, w - 1, h - 1, radius, radius)

        knob_d = h - 6
        left_x = 3
        right_x = w - knob_d - 3
        x = left_x if self._value == 0 else right_x
        knob_color = QColor("#ff232b") if self._value == 0 else QColor("#ff8a22")

        if self._value == 0:
            # KITT selected: red knob left, KITT wordmark on right.
            self._draw_wordmark_or_text(
                p,
                self._kitt_pix,
                "KITT",
                left_x + knob_d + 8,
                w - 8,
                QColor("#ff232b"),
            )
        else:
            # KARR selected: KARR wordmark on left, orange knob right.
            self._draw_wordmark_or_text(
                p,
                self._karr_pix,
                "KARR",
                8,
                right_x - 8,
                QColor("#ff8a22"),
            )

        # Knob
        p.setPen(Qt.NoPen)
        p.setBrush(knob_color)
        p.drawEllipse(x, 3, knob_d, knob_d)

        p.end()

class ParamPanel(QGroupBox):
    """
    Icon-pill parameter panel.

    Model:
    - KITT/KARR uses an iOS-style switch.
    - Numeric parameters use flat single-color circular icon buttons.
    - Clicking a numeric icon selects that parameter and shows its slider below.
    - Presets still save the same raw values as before.
    """

    def __init__(self, driver: "MatrixDriver", settings: "Settings", parent=None):
        super().__init__("Effect Parameters", parent)
        self._driver = driver
        self._settings = settings
        self._outer = QVBoxLayout(self)
        self._outer.setSpacing(8)
        self._outer.setContentsMargins(8, 8, 8, 8)

        self._slider_map: dict[str, tuple] = {}  # attr -> (widget/state, scale, kind)
        self._effect_cls: type[BaseEffect] | None = None
        self._params: dict = {}
        self._active_attr: str | None = None
        self._buttons: dict[str, QPushButton] = {}

        self._slider_host: QWidget | None = None
        self._active_label: QLabel | None = None
        self._active_value: QLabel | None = None
        self._active_slider: QSlider | None = None

        self._show_empty()

    def _clear(self):
        self._slider_map.clear()
        self._effect_cls = None
        self._params = {}
        self._active_attr = None
        self._buttons = {}
        self._slider_host = None
        self._active_label = None
        self._active_value = None
        self._active_slider = None

        while self._outer.count():
            item = self._outer.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._delete_layout(item.layout())

    def _delete_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._delete_layout(item.layout())

    def _show_empty(self):
        self._clear()
        lbl = QLabel("(no adjustable parameters)")
        lbl.setStyleSheet("color:#555; font-size:11px;")
        self._outer.addWidget(lbl)

    _PARAM_ICON_MAP = {
        "speed": "speed.svg",
        "peak": "peak.svg",
        "density": "density.svg",
        "direction": "direction.svg",
        "trail": "trail.svg",
        "width": "width.svg",
        "bounce": "bounce.svg",
        "stars": "stars.svg",
        "move x": "move_x.svg",
        "bursts": "bursts.svg",
        "waves": "waves.svg",
        "format": "format_12_24h.svg",
        "blink": "blink.svg",
        "message": "message.svg",
        "gap": "gap.svg",
        "decay": "decay.svg",
        "glow": "glow.svg",
        "sensitivity": "sensitivity.svg",
        "sensitivity trim": "sensitivity.svg",
        "boost": "boost.svg",
        "boost trim": "boost.svg",
        "falloff": "falloff.svg",
        "noise floor": "noise_floor.svg",
        "intensity": "intensity.svg",
        "cooling": "cooling.svg",
        "flow": "flow.svg",
        "blobs": "blobs.svg",
        "radius": "radius.svg",
        "bolts": "bolts.svg",
        "fade": "fade.svg",
        "rows": "rows.svg",
        "x position": "move_x.svg",
        "y position": "move_y.svg",
    }

    def _icon_path_for(self, attr: str, label: str) -> Path | None:
        """Return the canonical SVG asset for a numeric parameter."""
        clean_label = label.strip().rstrip(":").strip().lower()
        clean_attr = attr.strip().lower()

        # Labels distinguish shared attrs such as count = Stars/Bursts/Blobs.
        filename = self._PARAM_ICON_MAP.get(clean_label)

        if filename is None:
            attr_fallbacks = {
                "speed": "speed.svg",
                "peak": "peak.svg",
                "density": "density.svg",
                "direction": "direction.svg",
                "trail": "trail.svg",
                "width": "width.svg",
                "bounce": "bounce.svg",
                "waves": "waves.svg",
                "hour_24": "format_12_24h.svg",
                "blink": "blink.svg",
                "message": "message.svg",
                "loop_gap": "gap.svg",
                "decay": "decay.svg",
                "glow": "glow.svg",
                "sensitivity": "sensitivity.svg",
                "boost": "boost.svg",
                "falloff": "falloff.svg",
                "floor": "noise_floor.svg",
                "intensity": "intensity.svg",
                "cooling": "cooling.svg",
                "flow": "flow.svg",
                "radius": "radius.svg",
                "bolts": "bolts.svg",
                "fade": "fade.svg",
                "rows": "rows.svg",
                "x_offset": "move_x.svg",
                "x_pos": "move_x.svg",
                "y_pos": "move_y.svg",
            }
            filename = attr_fallbacks.get(clean_attr)

        if filename is None:
            return None

        path = _resource_path(f"assets/parameter_icons/{filename}")
        return path if path.exists() else None


    def _fmt_value(self, raw_value: int, scale: float, display: dict | None = None) -> str:
        if display:
            return display.get(int(raw_value), str(int(raw_value)))
        fv = raw_value / scale
        return f"{fv:.0f}" if scale == 1.0 else f"{fv:.2f}".rstrip("0").rstrip(".")

    def _circle_style(self) -> str:
        return (
            "QPushButton{"
            "min-width:34px;max-width:34px;min-height:34px;max-height:34px;"
            "border-radius:17px;"
            "background:#202020;"
            "border:1px solid #444;"
            "color:#f2f2f2;"
            "font-size:16px;"
            "font-weight:bold;"
            "padding:0;"
            "}"
            "QPushButton:hover{border-color:#e8001d;background:#2a2a2a;color:#fff;}"
            "QPushButton:checked{background:#e8001d;border-color:#e8001d;color:#fff;}"
        )

    def _refresh_button_states(self):
        for attr, btn in self._buttons.items():
            btn.setChecked(attr == self._active_attr)

    def _make_pill(self) -> tuple[QFrame, QHBoxLayout]:
        pill = QFrame()
        pill.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pill.setStyleSheet(
            "QFrame{background:#101010;border:1px solid #2b2b2b;"
            "border-radius:24px;padding:4px;}"
        )
        row = QHBoxLayout(pill)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        return pill, row

    def _make_slider_host(self) -> QWidget:
        host = QWidget()
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        host.setVisible(False)
        host.setStyleSheet(
            "QWidget{background:#101010;border:1px solid #252525;"
            "border-radius:10px;}"
        )

        root = QVBoxLayout(host)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)

        self._active_label = QLabel("")
        self._active_label.setStyleSheet("color:#aaa;font-size:11px;font-weight:bold;")

        self._active_value = QLabel("")
        self._active_value.setFixedWidth(54)
        self._active_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._active_value.setStyleSheet("color:#fff;font-size:11px;")

        top.addWidget(self._active_label)
        top.addStretch()
        top.addWidget(self._active_value)
        root.addLayout(top)

        self._active_slider = QSlider(Qt.Horizontal)
        self._active_slider.setMinimumHeight(26)
        self._active_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:5px;background:#2b2b2b;border-radius:2px;}"
            "QSlider::sub-page:horizontal{background:#e8001d;border-radius:2px;}"
            "QSlider::add-page:horizontal{background:#3a3a3a;border-radius:2px;}"
            "QSlider::handle:horizontal{background:#7a0010;border:2px solid #e8001d;"
            "width:18px;height:18px;margin:-8px 0;border-radius:9px;}"
        )
        self._active_slider.valueChanged.connect(self._active_slider_changed)
        root.addWidget(self._active_slider)

        return host

    def _set_style_switch_value(self, attr: str, raw_value: int):
        entry = self._slider_map.get(attr)
        if not entry:
            return
        widget, _scale, kind = entry
        if kind != "style":
            return
        value = 1 if int(raw_value) >= 1 else 0
        widget.setValue(value, emit=False)
        self._driver.set_effect_param(attr, float(value))

    def _style_changed(self, attr: str, value: int):
        self._driver.set_effect_param(attr, float(value))

    def _select_numeric(self, attr: str):
        self._active_attr = attr
        self._refresh_button_states()

        entry = self._slider_map.get(attr)
        if not entry or not self._active_slider or not self._active_label or not self._active_value or not self._slider_host:
            return

        state, scale, kind = entry
        if kind != "slider":
            return

        p = state["param"]
        display = p.get("display")
        value = int(state["value"])

        self._active_label.setText(p["label"])
        self._active_value.setText(self._fmt_value(value, scale, display))

        self._active_slider.blockSignals(True)
        self._active_slider.setRange(int(p["min"]), int(p["max"]))
        self._active_slider.setValue(value)
        self._active_slider.blockSignals(False)

        self._slider_host.setVisible(True)

    def _active_slider_changed(self, raw_value: int):
        attr = self._active_attr
        if not attr:
            return

        entry = self._slider_map.get(attr)
        if not entry:
            return

        state, scale, kind = entry
        if kind != "slider":
            return

        state["value"] = int(raw_value)

        display = state["param"].get("display")
        if self._active_value:
            self._active_value.setText(self._fmt_value(raw_value, scale, display))

        self._driver.set_effect_param(attr, raw_value / scale)

    def _reset_current(self):
        if not self._params:
            return

        for attr, p in self._params.items():
            entry = self._slider_map.get(attr)
            if not entry:
                continue

            state, scale, kind = entry
            default = p.get("default", "")

            if kind == "text":
                widget = state["widget"]
                widget.blockSignals(True)
                widget.setText(str(default))
                widget.blockSignals(False)
                self._driver.set_effect_param(attr, str(default))

            elif kind == "style":
                self._set_style_switch_value(attr, int(default))

            elif kind == "slider":
                lo, hi = int(p["min"]), int(p["max"])
                raw = max(lo, min(hi, int(default)))
                state["value"] = raw
                self._driver.set_effect_param(attr, raw / scale)

                if attr == self._active_attr:
                    self._select_numeric(attr)

    def _save_current_default(self):
        if self._effect_cls is None:
            return
        self._settings.set_effect_default(
            self._effect_cls.name, self.get_values()
        )

    def _clear_current_default(self):
        if self._effect_cls is None:
            return
        self._settings.clear_effect_default(self._effect_cls.name)
        self._reset_current()

    def load(self, effect_cls: type[BaseEffect], saved_vals: dict | None = None):
        self._clear()
        self._effect_cls = effect_cls
        self._params = dict(getattr(effect_cls, "PARAMS", {}) or {})
        if saved_vals is None:
            saved_vals = self._settings.get_effect_default(effect_cls.name)

        params = self._params
        if not params:
            self._show_empty()
            return

        header = QHBoxLayout()
        title = QLabel(effect_cls.name)
        title.setStyleSheet("color:#e8001d;font-size:12px;font-weight:bold;")

        save_btn = QPushButton("✓")
        save_btn.setToolTip("Save these values as this effect's default")
        save_btn.setFixedSize(28, 28)
        save_btn.setStyleSheet(
            "QPushButton{background:#191919;color:#8fd694;border:1px solid #333;"
            "border-radius:14px;font-size:14px;padding:0;}"
            "QPushButton:hover{color:#fff;border-color:#47b45a;}"
        )
        save_btn.clicked.connect(self._save_current_default)

        reset_btn = QPushButton("↺")
        reset_btn.setToolTip("Restore factory defaults and clear saved default")
        reset_btn.setFixedSize(28, 28)
        reset_btn.setStyleSheet(
            "QPushButton{background:#191919;color:#888;border:1px solid #333;"
            "border-radius:14px;font-size:15px;padding:0;}"
            "QPushButton:hover{color:#fff;border-color:#e8001d;}"
        )
        reset_btn.clicked.connect(self._clear_current_default)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(save_btn)
        header.addWidget(reset_btn)
        self._outer.addLayout(header)

        pill, pill_row = self._make_pill()
        first_numeric_attr = None

        for attr, p in params.items():
            label = p["label"]
            saved_has_attr = saved_vals is not None and attr in saved_vals

            if p.get("type") == "text":
                init_text = str(saved_vals.get(attr, p.get("default", ""))) if saved_has_attr else str(p.get("default", ""))
                edit = QLineEdit(init_text)
                edit.setPlaceholderText(label)
                edit.setStyleSheet(
                    "QLineEdit{background:#191919;color:#ccc;border:1px solid #333;"
                    "padding:6px 10px;border-radius:14px;font-size:11px;}"
                    "QLineEdit:focus{border-color:#e8001d;}"
                )
                _attr = attr
                edit.textChanged.connect(lambda txt, a=_attr: self._driver.set_effect_param(a, txt))
                pill_row.addWidget(edit, 1)
                self._slider_map[attr] = ({"widget": edit, "label": label}, 1.0, "text")
                continue

            lo, hi = int(p["min"]), int(p["max"])
            default = int(p["default"])
            init = max(lo, min(hi, int(saved_vals[attr]))) if saved_has_attr else default

            is_binary_style = attr.lower() == "style" and lo == 0 and hi == 1

            if is_binary_style:
                switch = KittKarrSwitch(init)
                switch.valueChanged.connect(lambda value, a=attr: self._style_changed(a, value))
                pill_row.addWidget(switch)
                self._slider_map[attr] = (switch, 1.0, "style")
                self._set_style_switch_value(attr, init)
                continue

            btn = QPushButton()
            btn.setCheckable(True)
            btn.setStyleSheet(self._circle_style())

            icon_path = self._icon_path_for(attr, label)
            if icon_path is not None:
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(24, 24))
                btn.setText("")
            else:
                # Last-resort fallback for future parameters without an asset.
                btn.setText("•")

            btn.setToolTip(label)
            self._buttons[attr] = btn

            scale = float(p["scale"])
            self._slider_map[attr] = (
                {"value": init, "param": p},
                scale,
                "slider",
            )
            if first_numeric_attr is None:
                first_numeric_attr = attr
            btn.clicked.connect(lambda _=False, a=attr: self._select_numeric(a))
            pill_row.addWidget(btn)

        pill_row.addStretch()
        self._outer.addWidget(pill)

        self._slider_host = self._make_slider_host()
        self._outer.addWidget(self._slider_host)

        if first_numeric_attr:
            self._select_numeric(first_numeric_attr)

    def get_values(self) -> dict:
        out = {}
        for attr, (state, scale, kind) in self._slider_map.items():
            if kind == "text":
                out[attr] = state["widget"].text()
            elif kind == "style":
                out[attr] = int(state.value())
            else:
                out[attr] = int(state.get("value", 0))
        return out

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

        title_row = QHBoxLayout()
        title = QLabel("PolyWollyWin Quick Controls")
        title.setStyleSheet("color:#e8001d; font-size:12px; font-weight:bold;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setObjectName("qc_close_btn")
        close_btn.setStyleSheet(
            "QPushButton#qc_close_btn{background:#1a1a1a;color:#555;"
            "border:none;font-size:11px;border-radius:3px;padding:0;}"
            "QPushButton#qc_close_btn:hover{color:#fff;background:#e8001d;}"
        )
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)
        layout.addWidget(_sep())

        self._bc = BCBar()
        self._bc.bri.valueChanged.connect(lambda v: driver.set_brightness(v / 100.0))
        self._bc.con.valueChanged.connect(lambda v: driver.set_contrast(v / 100.0))
        layout.addWidget(self._bc)
        layout.addWidget(_sep())

        layout.addWidget(_label("Effects", "#888"))
        blank_btn = QPushButton("⬛ Blank")
        blank_btn.clicked.connect(driver.set_mode_blank)
        btns = [blank_btn]
        for name in EFFECT_NAMES:
            b = QPushButton(f"▶ {name}"); _n = name
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
        if not self.isAncestorOf(QApplication.focusWidget() or self):
            self.hide()
        super().focusOutEvent(event)


# ─────────────────────────────────────────────────────────────────────
# Matrix driver
# ─────────────────────────────────────────────────────────────────────

class MatrixDriver(QObject):
    status_changed = Signal(str)
    frame_rendered  = Signal(list)

    MODE_BLANK  = "blank"
    MODE_EFFECT = "effect"
    MODE_GIF    = "gif"
    MODE_IMAGE  = "image"
    MODE_PAINT  = "paint"
    MODE_AUDIO  = "audio"

    def __init__(self):
        super().__init__()
        self._transport  = Transport()
        self._lock       = threading.Lock()
        self.mode        = self.MODE_BLANK
        self._effect:  BaseEffect | None = None
        self._gif:     GifPlayer  | None = None
        self._static:  list[int]  = [0] * PHYSICAL_LED_COUNT
        self._brightness  = 1.0
        self._contrast    = 1.0
        self._gif_timer   = 0.0
        self._effect_speed = 1.0
        self._gif_speed   = 1.0
        self._effect2: BaseEffect | None = None   # blend layer B
        self._blend_alpha = 0.0                   # 0=all A, 1=all B
        self._audio: AudioVisualizer | None = None

        # ── Crossfade state ──────────────────────────────────────────
        self._xfade_enabled = True
        self._xfade_dur     = 0.5                 # seconds
        self._xfade_t       = 0.0
        self._xfade_from:   list[int] | None = None
        self._last_raw:     list[int] = [0] * PHYSICAL_LED_COUNT

        # ── Screen-react state ───────────────────────────────────────
        self._screen_react    = False
        self._screen_level    = 1.0
        self._screen_timer    = 0.0
        self._screen_interval = 0.12   # sample every ~120 ms

    # ── connection ────────────────────────────────────────────────────

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

    # ── setters ───────────────────────────────────────────────────────

    def set_effect_speed(self, v: float):
        with self._lock: self._effect_speed = max(0.1, min(5.0, v))

    def set_gif_speed(self, v: float):
        with self._lock: self._gif_speed = max(0.1, min(10.0, v))

    def set_blend_effect(self, name: str | None, params: dict | None = None):
        with self._lock:
            if isinstance(self._effect2, (AudioVisualizer, TypingEffect)):
                self._effect2.stop()
            self._effect2 = make_effect(name) if name else None
            if self._effect2:
                for attr, value in (params or {}).items():
                    if hasattr(self._effect2, attr):
                        setattr(self._effect2, attr, value)

    def set_blend_alpha(self, v: float):
        with self._lock: self._blend_alpha = max(0.0, min(1.0, v))

    def set_brightness(self, v: float):
        with self._lock: self._brightness = max(0.0, min(1.0, v))

    def set_contrast(self, v: float):
        with self._lock: self._contrast = max(0.1, min(3.0, v))

    def set_crossfade_enabled(self, v: bool):
        with self._lock: self._xfade_enabled = v

    def set_screen_react(self, v: bool):
        with self._lock: self._screen_react = v

    def set_crossfade_dur(self, v: float):
        with self._lock: self._xfade_dur = max(0.0, v)

    def set_audio_param(self, attr: str, value: float):
        with self._lock:
            if self._audio and hasattr(self._audio, attr):
                setattr(self._audio, attr, value)

    def set_effect_param(self, attr: str, value: float):
        """Live-update a parameter on the running effect instance."""
        with self._lock:
            if self._effect and hasattr(self._effect, attr):
                setattr(self._effect, attr, value)

    # ── mode switches ─────────────────────────────────────────────────

    def set_mode_blank(self):
        with self._lock:
            self._maybe_start_xfade()
            if isinstance(self._effect, (AudioVisualizer, TypingEffect)):
                self._effect.stop()
            if self._audio:
                self._audio.stop()
                self._audio = None
            self.mode = self.MODE_BLANK
            self._effect = None
            self._effect2 = None

    def set_mode_effect(self, name: str, params: dict | None = None):
        with self._lock:
            if isinstance(self._effect, (AudioVisualizer, TypingEffect)):
                self._effect.stop()
            if self._audio:
                self._audio.stop()
                self._audio = None
            self._maybe_start_xfade()
            self._effect = make_effect(name)
            for attr, value in (params or {}).items():
                if hasattr(self._effect, attr):
                    setattr(self._effect, attr, value)
            self.mode = self.MODE_EFFECT

    def set_mode_audio(self, visualizer: str = "Spectrum Bars",
                       sensitivity: float = 1.0,
                       falloff: float = 0.82,
                       extra: dict | None = None):
        with self._lock:
            if isinstance(self._effect, (AudioVisualizer, TypingEffect)):
                self._effect.stop()
            self._effect = None
            self._effect2 = None

            cls = AUDIO_VISUALIZERS.get(
                visualizer, SpectrumAudioVisualizer
            )
            needs_new = (
                self._audio is None or type(self._audio) is not cls
            )

            if needs_new:
                if self._audio:
                    self._audio.stop()

                if cls.__name__ == "KITTAudioEffect":
                    self._audio = cls(
                        sensitivity=sensitivity,
                        boost=1.0,
                        x_pos=(extra or {}).get("x_pos", 66.0),
                        y_pos=(extra or {}).get("y_pos", 45.0),
                        style=(extra or {}).get("style", 0.0),
                    )
                    self._audio.falloff = falloff
                else:
                    self._audio = cls(
                        sensitivity=sensitivity,
                        falloff=falloff,
                        **(extra or {}),
                    )
            else:
                if hasattr(self._audio, "apply_controls"):
                    self._audio.apply_controls(
                        sensitivity=sensitivity,
                        falloff=falloff,
                        **(extra or {}),
                    )
                else:
                    self._audio.sensitivity = sensitivity
                    self._audio.falloff = falloff
                    for attr, value in (extra or {}).items():
                        if hasattr(self._audio, attr):
                            setattr(self._audio, attr, value)

            self._maybe_start_xfade()
            self.mode = self.MODE_AUDIO

    def set_mode_gif(self, player: GifPlayer):
        with self._lock:
            if self._audio:
                self._audio.stop(); self._audio = None
            self._gif = player; self._gif_timer = 0.0
            self.mode = self.MODE_GIF

    def set_mode_image(self, frame: list[int]):
        with self._lock:
            if self._audio:
                self._audio.stop(); self._audio = None
            self._static = frame; self.mode = self.MODE_IMAGE

    def set_mode_paint(self, frame: list[int]):
        with self._lock:
            if self._audio:
                self._audio.stop(); self._audio = None
            self._static = frame; self.mode = self.MODE_PAINT

    def _maybe_start_xfade(self):
        """Call *inside* the lock before switching mode/effect."""
        if self._xfade_enabled and self._last_raw:
            self._xfade_from = list(self._last_raw)
            self._xfade_t    = 0.0

    # ── queries ───────────────────────────────────────────────────────

    def current_effect_name(self) -> str:
        with self._lock:
            return self._effect.name if self._effect else ""

    def update_paint(self, frame: list[int]):
        with self._lock:
            if self.mode == self.MODE_PAINT:
                self._static = frame

    # ── tick (called at TICK_HZ) ──────────────────────────────────────

    def tick(self, dt: float):
        if not self._transport.connected:
            return

        with self._lock:
            mode    = self.mode
            bri     = self._brightness
            con     = self._contrast
            eff_dt  = dt * self._effect_speed

            # ── render primary frame ─────────────────────────────────
            if mode == self.MODE_BLANK:
                raw = [0] * PHYSICAL_LED_COUNT

            elif mode == self.MODE_EFFECT and self._effect:
                raw = list(self._effect.tick(eff_dt))
                if self._effect2 and self._blend_alpha > 0.0:
                    raw2 = list(self._effect2.tick(eff_dt))
                    a    = self._blend_alpha
                    raw  = [int(v1 * (1 - a) + v2 * a) for v1, v2 in zip(raw, raw2)]

            elif mode == self.MODE_GIF and self._gif:
                raw = list(self._gif.current_frame())
                self._gif_timer += dt
                if self._gif_timer >= self._gif.current_duration() / self._gif_speed:
                    self._gif_timer = 0.0
                    self._gif.advance()

            elif mode == self.MODE_AUDIO and self._audio:
                raw = list(self._audio.tick(dt))

            elif mode in (self.MODE_IMAGE, self.MODE_PAINT):
                raw = list(self._static)

            else:
                raw = [0] * PHYSICAL_LED_COUNT

            # ── contrast / brightness ────────────────────────────────
            if con != 1.0:
                raw = [max(0, min(255, int((v - 128) * con + 128))) for v in raw]
            if bri < 1.0:
                raw = [int(v * bri) for v in raw]

            # ── screen-react multiplier ───────────────────────────────
            if self._screen_react:
                self._screen_timer += dt
                if self._screen_timer >= self._screen_interval:
                    self._screen_timer = 0.0
                    self._screen_level = self._sample_screen()
                if self._screen_level < 0.999:
                    raw = [int(v * self._screen_level) for v in raw]

            # ── crossfade overlay ────────────────────────────────────
            if self._xfade_from is not None:
                self._xfade_t += dt
                if self._xfade_t >= self._xfade_dur:
                    self._xfade_from = None
                else:
                    alpha = self._xfade_t / max(0.001, self._xfade_dur)
                    raw   = [int(f * (1.0 - alpha) + r * alpha)
                             for f, r in zip(self._xfade_from, raw)]

            # ── store for next crossfade ─────────────────────────────
            self._last_raw = raw

        try:
            self._transport.send_frame(raw)
        except Exception:
            pass
        self.frame_rendered.emit(raw)

    @staticmethod
    def _sample_screen() -> float:
        """Return 0.1–1.0 average screen brightness via Pillow ImageGrab."""
        try:
            from PIL import ImageGrab
            import numpy as _np
            img = ImageGrab.grab(bbox=None)
            img = img.resize((64, 36))
            arr = _np.asarray(img.convert("L"), dtype=_np.float32)
            return max(0.10, float(_np.mean(arr)) / 255.0)
        except Exception:
            return 1.0

    def cleanup(self):
        with self._lock:
            if isinstance(self._effect,  (AudioVisualizer, TypingEffect)): self._effect.stop()
            if isinstance(self._effect2, (AudioVisualizer, TypingEffect)): self._effect2.stop()
            if self._audio: self._audio.stop()
        try:
            self._transport.send_blank()
            self._transport.disconnect()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────
# Sequencer tab
# ─────────────────────────────────────────────────────────────────────

class SequencerTab(QWidget):
    """
    Effect playlist: build a list of (effect_name, dwell_seconds) entries,
    hit Play, and the driver auto-cycles through them with optional crossfade.
    """

    def __init__(self, driver: MatrixDriver, param_panel: ParamPanel, parent=None):
        super().__init__(parent)
        self._driver      = driver
        self._param_panel = param_panel
        self._playlist:   list[tuple[str, float]] = []   # (name, dwell_s)
        self._current_idx = 0
        self._playing     = False
        self._step_start  = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Playlist ──────────────────────────────────────────────────
        layout.addWidget(_label("Playlist", "#888"))
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:#111;color:#ccc;border:1px solid #2a2a2a;font-size:11px;}"
            "QListWidget::item:selected{background:#2a0005;color:#fff;}"
        )
        self._list.setMinimumHeight(120)
        layout.addWidget(self._list)

        # ── Add row ───────────────────────────────────────────────────
        add_row = QHBoxLayout(); add_row.setSpacing(6)
        self._combo = QComboBox()
        self._combo.addItems(EFFECT_NAMES)
        self._combo.setStyleSheet(
            "QComboBox{background:#1a1a1a;color:#ccc;border:1px solid #333;padding:2px 6px;}"
            "QComboBox QAbstractItemView{background:#1a1a1a;color:#ccc;}"
        )
        self._dwell = QDoubleSpinBox()
        self._dwell.setRange(1.0, 3600.0)
        self._dwell.setValue(15.0)
        self._dwell.setSuffix(" s")
        self._dwell.setFixedWidth(70)
        self._dwell.setStyleSheet(
            "QDoubleSpinBox{background:#1a1a1a;color:#ccc;border:1px solid #333;padding:2px 4px;}"
        )
        add_btn = QPushButton("+ Add")
        add_btn.setFixedWidth(60)
        add_btn.setMinimumHeight(26)
        add_btn.clicked.connect(self._add_item)
        add_row.addWidget(self._combo, 2)
        add_row.addWidget(self._dwell, 0)
        add_row.addWidget(add_btn, 0)
        layout.addLayout(add_row)

        # ── Edit row ──────────────────────────────────────────────────
        edit_row = QHBoxLayout(); edit_row.setSpacing(4)
        rm_btn = QPushButton("✕ Remove"); rm_btn.setMinimumHeight(26)
        up_btn = QPushButton("▲"); up_btn.setFixedWidth(32); up_btn.setMinimumHeight(26)
        dn_btn = QPushButton("▼"); dn_btn.setFixedWidth(32); dn_btn.setMinimumHeight(26)
        rm_btn.clicked.connect(self._remove_item)
        up_btn.clicked.connect(self._move_up)
        dn_btn.clicked.connect(self._move_down)
        edit_row.addWidget(rm_btn); edit_row.addWidget(up_btn); edit_row.addWidget(dn_btn)
        edit_row.addStretch()
        layout.addLayout(edit_row)

        layout.addWidget(_sep())

        # ── Play controls ─────────────────────────────────────────────
        ctrl_row = QHBoxLayout(); ctrl_row.setSpacing(8)
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setMinimumHeight(32)
        self._play_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._play_btn.clicked.connect(self._toggle_play)

        self._loop_cb   = QCheckBox("Loop")
        self._loop_cb.setChecked(True)
        self._loop_cb.setStyleSheet("color:#888; font-size:11px;")

        self._xfade_cb  = QCheckBox("Crossfade")
        self._xfade_cb.setChecked(True)
        self._xfade_cb.setStyleSheet("color:#888; font-size:11px;")
        self._xfade_cb.stateChanged.connect(
            lambda v: driver.set_crossfade_enabled(bool(v))
        )

        ctrl_row.addWidget(self._play_btn)
        ctrl_row.addWidget(self._loop_cb)
        ctrl_row.addWidget(self._xfade_cb)
        layout.addLayout(ctrl_row)

        # ── Status ────────────────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        # Timer — fires 4× per second to update the countdown display
        self._timer = QTimer()
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)

    # ── playlist management ───────────────────────────────────────────

    def _add_item(self):
        name  = self._combo.currentText()
        dwell = self._dwell.value()
        self._playlist.append((name, dwell))
        self._list.addItem(f"{name}   —   {dwell:.0f} s")

    def _remove_item(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._playlist):
            self._playlist.pop(row)
            self._list.takeItem(row)

    def _move_up(self):
        row = self._list.currentRow()
        if row > 0:
            self._playlist[row - 1], self._playlist[row] = (
                self._playlist[row], self._playlist[row - 1]
            )
            text = self._list.takeItem(row)
            self._list.insertItem(row - 1, text)
            self._list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._playlist) - 1:
            self._playlist[row], self._playlist[row + 1] = (
                self._playlist[row + 1], self._playlist[row]
            )
            text = self._list.takeItem(row)
            self._list.insertItem(row + 1, text)
            self._list.setCurrentRow(row + 1)

    # ── playback ──────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._playing:
            self._stop()
        else:
            self._play()

    def _play(self):
        if not self._playlist:
            return
        self._playing     = True
        self._current_idx = 0
        self._play_btn.setText("⏹ Stop")
        self._launch_current()
        self._timer.start()

    def _stop(self):
        self._playing = False
        self._timer.stop()
        self._play_btn.setText("▶ Play")
        self._status_lbl.setText("")
        self._list.setCurrentRow(-1)

    def _launch_current(self):
        if not self._playlist:
            return
        name, _dwell = self._playlist[self._current_idx]
        self._driver.set_mode_effect(name)
        self._step_start = time.monotonic()
        self._list.setCurrentRow(self._current_idx)

        # Update param panel to reflect new effect
        for cls in ALL_EFFECTS:
            if cls.name == name:
                self._param_panel.load(cls)
                break

    def _tick(self):
        if not self._playing or not self._playlist:
            return
        name, dwell = self._playlist[self._current_idx]
        elapsed     = time.monotonic() - self._step_start
        remaining   = dwell - elapsed
        self._status_lbl.setText(
            f"▶ {name}  |  next in {max(0.0, remaining):.1f} s"
        )
        if elapsed >= dwell:
            next_idx = self._current_idx + 1
            if next_idx >= len(self._playlist):
                if self._loop_cb.isChecked():
                    next_idx = 0
                else:
                    self._stop()
                    return
            self._current_idx = next_idx
            self._launch_current()

    def stop_playback(self):
        """Call from outside (e.g. when another tab switches effect)."""
        if self._playing:
            self._stop()


# ─────────────────────────────────────────────────────────────────────
# GIF tab with live preview
# ─────────────────────────────────────────────────────────────────────

class GifTab(QWidget):
    def __init__(self, driver: MatrixDriver, settings: "Settings" = None):
        super().__init__()
        self._driver   = driver
        self._settings = settings
        self._gif_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._file_label = QLabel("(no file selected)")
        self._file_label.setStyleSheet("color:#666; font-size:11px;")

        browse_btn  = QPushButton("Browse GIF…")
        play_btn    = QPushButton("▶ Play")
        autofit_btn = QPushButton("Auto-fit")
        stop_btn    = QPushButton("⬛ Blank")

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
        lbl_s, self._sc, val_s = _row("Scale",      1, 500,  41, scale=10)
        for i, (l, s, v) in enumerate([(lbl_x, self._ox, val_x),
                                        (lbl_y, self._oy, val_y),
                                        (lbl_s, self._sc, val_s)]):
            pg.addWidget(l, i, 0); pg.addWidget(s, i, 1); pg.addWidget(v, i, 2)
        pg.setColumnStretch(1, 1)

        preview_group = QGroupBox("Preview (frame 0 — updates with sliders)")
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

        # ── GIF Playback Speed ────────────────────────────────────────
        gif_speed_row = QHBoxLayout(); gif_speed_row.setSpacing(6)
        gif_speed_row.addWidget(_label("⏩ Speed"))
        self._gif_speed_sld = QSlider(Qt.Horizontal)
        self._gif_speed_sld.setRange(10, 1000)
        self._gif_speed_sld.setValue(100)
        gif_speed_val = QLabel("1.0×")
        gif_speed_val.setFixedWidth(36)
        gif_speed_val.setStyleSheet("color:#ccc; font-size:11px;")
        self._gif_speed_sld.valueChanged.connect(
            lambda v: (
                gif_speed_val.setText(f"{v/100:.1f}×"),
                self._driver.set_gif_speed(v / 100.0),
            )
        )
        gif_speed_row.addWidget(self._gif_speed_sld)
        gif_speed_row.addWidget(gif_speed_val)
        layout.addLayout(gif_speed_row)

        layout.addWidget(pos_group)
        layout.addWidget(preview_group)
        layout.addWidget(img_group)
        layout.addStretch()

    def save(self, settings: "Settings"):
        settings.set_last_gif(self._gif_path)
        settings.set_gif_ox(self._ox.value())
        settings.set_gif_oy(self._oy.value())
        settings.set_gif_scale(self._sc.value())

    def restore(self, settings: "Settings"):
        path = settings.get_last_gif()
        if path and Path(path).exists():
            self._gif_path = path
            self._file_label.setText(Path(path).name)
            self._file_label.setStyleSheet("color:#aaa; font-size:11px;")
        self._ox.setValue(settings.get_gif_ox())
        self._oy.setValue(settings.get_gif_oy())
        self._sc.setValue(settings.get_gif_scale())
        if self._gif_path:
            self._preview_update()

    def replay(self):
        self._play()

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
# Audio tab
# ─────────────────────────────────────────────────────────────────────

class AudioTab(QWidget):
    """Dedicated audio visualizations with per-mode saved controls."""

    XY_POSITIONED = {
        "KITT / KARR",
        "Center Starburst",
        "Corner Convergence",
    }
    Y_ONLY = {"Oscilloscope"}

    def __init__(self, driver: MatrixDriver, settings: "Settings" = None):
        super().__init__()
        self._driver = driver
        self._settings = settings or Settings()
        self._loading = False
        self._previous_type = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Audio Visualizations")
        title.setStyleSheet(
            "color:#e8001d; font-size:13px; font-weight:bold;"
        )
        layout.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(_label("Visualization"))
        self._type = QComboBox()
        self._type.addItems(AUDIO_VISUALIZERS.keys())
        row.addWidget(self._type, 1)
        layout.addLayout(row)

        response = QGroupBox("Response")
        grid = QGridLayout(response)
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)
        self._sens, self._sens_val = self._slider(
            grid, 0, "Sensitivity", 20, 400, 100, 100.0, "{:.2f}×"
        )
        self._fall, self._fall_val = self._slider(
            grid, 1, "Falloff", 50, 98, 82, 100.0, "{:.2f}"
        )
        layout.addWidget(response)

        self._position_group = QGroupBox("Position")
        pos_grid = QGridLayout(self._position_group)
        self._x_label = _label("X Position")
        self._x = QSlider(Qt.Horizontal)
        self._x.setRange(0, 100)
        self._x_val = QLabel("50")
        self._x_val.setFixedWidth(40)
        self._y_label = _label("Y Position")
        self._y = QSlider(Qt.Horizontal)
        self._y.setRange(0, 100)
        self._y_val = QLabel("50")
        self._y_val.setFixedWidth(40)
        pos_grid.addWidget(self._x_label, 0, 0)
        pos_grid.addWidget(self._x, 0, 1)
        pos_grid.addWidget(self._x_val, 0, 2)
        pos_grid.addWidget(self._y_label, 1, 0)
        pos_grid.addWidget(self._y, 1, 1)
        pos_grid.addWidget(self._y_val, 1, 2)
        layout.addWidget(self._position_group)

        self._kitt_group = QGroupBox("KITT / KARR")
        kitt_grid = QGridLayout(self._kitt_group)
        self._kitt_style = KittKarrSwitch(0)
        kitt_grid.addWidget(self._kitt_style, 0, 0, Qt.AlignLeft)
        layout.addWidget(self._kitt_group)

        buttons = QHBoxLayout()
        start_btn = QPushButton("▶ Start Audio")
        start_btn.clicked.connect(self.start)
        stop_btn = QPushButton("■ Stop")
        stop_btn.clicked.connect(self._stop)
        buttons.addWidget(start_btn)
        buttons.addWidget(stop_btn)
        layout.addLayout(buttons)

        self._status = QLabel("Stopped")
        self._status.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self._status)
        layout.addStretch()

        self._x.valueChanged.connect(lambda v: self._x_val.setText(str(v)))
        self._y.valueChanged.connect(lambda v: self._y_val.setText(str(v)))
        self._sens.valueChanged.connect(self._control_changed)
        self._fall.valueChanged.connect(self._control_changed)
        self._x.valueChanged.connect(self._control_changed)
        self._y.valueChanged.connect(self._control_changed)
        self._kitt_style.valueChanged.connect(self._control_changed)
        self._type.currentTextChanged.connect(self._visualizer_changed)

        selected = self._settings.get_audio_visualizer()
        if selected not in AUDIO_VISUALIZERS:
            selected = "Oscilloscope"
        self._type.setCurrentText(selected)
        self._visualizer_changed(selected)

    def _slider(self, grid, row, label, lo, hi, default, scale, fmt):
        lbl = _label(label)
        sld = QSlider(Qt.Horizontal)
        sld.setRange(lo, hi)
        sld.setValue(default)
        val = QLabel(fmt.format(default / scale))
        val.setFixedWidth(52)
        val.setStyleSheet("color:#ccc; font-size:11px;")
        sld.valueChanged.connect(
            lambda v, l=val, sc=scale, f=fmt:
                l.setText(f.format(v / sc))
        )
        grid.addWidget(lbl, row, 0)
        grid.addWidget(sld, row, 1)
        grid.addWidget(val, row, 2)
        return sld, val

    def _current_values(self) -> dict:
        values = {
            "sensitivity": self._sens.value(),
            "falloff": self._fall.value(),
        }
        name = self._type.currentText()
        if name in self.XY_POSITIONED:
            values["x_pos"] = self._x.value()
            values["y_pos"] = self._y.value()
        elif name in self.Y_ONLY:
            values["y_pos"] = self._y.value()
        if name == "KITT / KARR":
            values["style"] = self._kitt_style.value()
        return values

    def _save_current_mode(self, name: str | None = None):
        name = name or self._type.currentText()
        if not name or self._loading:
            return
        self._settings.set_audio_visualizer(name)
        self._settings.set_audio_mode_defaults(name, self._current_values())

    def _load_mode(self, name: str):
        defaults = {
            "sensitivity": 100,
            "falloff": 82,
            "x_pos": 66 if name == "KITT / KARR" else 50,
            "y_pos": 45 if name == "KITT / KARR" else 50,
            "style": 0,
        }
        defaults.update(self._settings.get_audio_mode_defaults(name))

        self._loading = True
        try:
            self._sens.setValue(int(defaults["sensitivity"]))
            self._fall.setValue(int(defaults["falloff"]))
            self._x.setValue(int(defaults["x_pos"]))
            self._y.setValue(int(defaults["y_pos"]))
            self._kitt_style.setValue(int(defaults["style"]), emit=False)
        finally:
            self._loading = False

    def _visualizer_changed(self, name: str):
        if self._previous_type and self._previous_type != name:
            self._save_current_mode(self._previous_type)
        self._previous_type = name
        self._load_mode(name)

        is_kitt = name == "KITT / KARR"
        xy = name in self.XY_POSITIONED
        y_only = name in self.Y_ONLY
        self._kitt_group.setVisible(is_kitt)
        self._position_group.setVisible(xy or y_only)
        self._x_label.setVisible(xy)
        self._x.setVisible(xy)
        self._x_val.setVisible(xy)
        self._y_label.setVisible(xy or y_only)
        self._y.setVisible(xy or y_only)
        self._y_val.setVisible(xy or y_only)
        self._settings.set_audio_visualizer(name)

        if self._driver.mode == self._driver.MODE_AUDIO:
            self.start()

    def _extra(self):
        name = self._type.currentText()
        extra = {}
        if name in self.XY_POSITIONED:
            extra.update(x_pos=float(self._x.value()), y_pos=float(self._y.value()))
        elif name in self.Y_ONLY:
            extra["y_pos"] = float(self._y.value())
        if name == "KITT / KARR":
            extra["style"] = float(self._kitt_style.value())
        return extra

    def _control_changed(self, *_args):
        if self._loading:
            return
        self._save_current_mode()
        if self._driver.mode == self._driver.MODE_AUDIO:
            self.start()

    def start(self):
        name = self._type.currentText()
        self._save_current_mode(name)
        self._driver.set_mode_audio(
            name,
            self._sens.value() / 100.0,
            self._fall.value() / 100.0,
            self._extra(),
        )
        self._status.setText(f"Running: {name}")
        self._status.setStyleSheet("color:#e8001d; font-size:11px;")

    def _stop(self):
        self._save_current_mode()
        self._driver.set_mode_blank()
        self._status.setText("Stopped")
        self._status.setStyleSheet("color:#555; font-size:11px;")

    def restore(self, settings: "Settings"):
        selected = settings.get_audio_visualizer()
        if selected in AUDIO_VISUALIZERS:
            self._type.setCurrentText(selected)
            self._load_mode(selected)

    def save(self, settings: "Settings"):
        self._save_current_mode()


# ─────────────────────────────────────────────────────────────────────
# Preset panel tab
# ─────────────────────────────────────────────────────────────────────

class PresetPanel(QWidget):
    """
    Named effect presets stored as JSON files in
    %LOCALAPPDATA%/PolyWollyWin/presets/.

    Each preset saves: effect name, all current param values,
    brightness, and contrast.  Double-click or Load button applies it.
    Export/Import move a single bundle file containing all presets.
    """

    preset_activated = Signal(dict)   # emits the preset dict when applied

    def __init__(self, driver: "MatrixDriver", param_panel: "ParamPanel",
                 bc_bar: "BCBar", settings: "Settings",
                 owner: "ControlWindow" = None, parent=None):
        super().__init__(parent)
        self._driver      = driver
        self._param_panel = param_panel
        self._bc          = bc_bar
        self._settings    = settings
        self._owner       = owner
        self._mgr         = PresetManager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(_label("Saved Presets", "#888"))

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:#111;color:#ccc;border:1px solid #2a2a2a;font-size:12px;}"
            "QListWidget::item{padding:4px;}"
            "QListWidget::item:selected{background:#2a0005;color:#fff;}"
        )
        self._list.setMinimumHeight(140)
        self._list.itemDoubleClicked.connect(lambda _: self._load_selected())
        layout.addWidget(self._list)

        # ── Action buttons ────────────────────────────────────────────
        btn_row1 = QHBoxLayout(); btn_row1.setSpacing(6)
        save_btn   = QPushButton("💾 Save current")
        load_btn   = QPushButton("▶ Load")
        delete_btn = QPushButton("✕ Delete")
        for btn in (save_btn, load_btn, delete_btn):
            btn.setMinimumHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        save_btn.clicked.connect(self._save_current)
        load_btn.clicked.connect(self._load_selected)
        delete_btn.clicked.connect(self._delete_selected)
        btn_row1.addWidget(save_btn)
        btn_row1.addWidget(load_btn)
        btn_row1.addWidget(delete_btn)
        layout.addLayout(btn_row1)

        layout.addWidget(_sep())

        # ── Export / Import ───────────────────────────────────────────
        io_row = QHBoxLayout(); io_row.setSpacing(6)
        exp_btn = QPushButton("⬆ Export all…")
        imp_btn = QPushButton("⬇ Import…")
        open_dir_btn = QPushButton("📁 Open folder")
        for btn in (exp_btn, imp_btn, open_dir_btn):
            btn.setMinimumHeight(26)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        exp_btn.clicked.connect(self._export)
        imp_btn.clicked.connect(self._import)
        open_dir_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(PRESET_DIR))
        ))
        io_row.addWidget(exp_btn)
        io_row.addWidget(imp_btn)
        io_row.addWidget(open_dir_btn)
        layout.addLayout(io_row)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#666; font-size:10px;")
        layout.addWidget(self._status)
        layout.addStretch()

        self._refresh_list()

    # ── list management ───────────────────────────────────────────────

    def _refresh_list(self):
        self._list.clear()
        for p in self._mgr.load_all():
            self._list.addItem(f"  {p.get('name', '?')}  —  {p.get('effect', '?')}")

    def _selected_preset(self) -> dict | None:
        row = self._list.currentRow()
        presets = self._mgr.load_all()
        return presets[row] if 0 <= row < len(presets) else None

    # ── save ──────────────────────────────────────────────────────────

    def _save_current(self):
        effect = self._driver.current_effect_name()
        if not effect:
            self._status.setText("No active effect to save.")
            return
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name.strip():
            return
        blend_state = (
            self._owner._get_blend_preset_state()
            if self._owner is not None
            else {"effect": "", "params": {}, "alpha": 0}
        )
        preset = {
            "name":         name.strip(),
            "effect":       effect,
            "params":       self._param_panel.get_values(),
            "blend_effect": blend_state.get("effect", ""),
            "blend_params": blend_state.get("params", {}),
            "blend_alpha":  int(blend_state.get("alpha", 0)),
            "brightness":   self._bc.bri.value(),
            "contrast":     self._bc.con.value(),
        }
        self._mgr.save(preset)
        self._refresh_list()
        self._status.setText(f"Saved: {name.strip()}")

    # ── load ──────────────────────────────────────────────────────────

    def _load_selected(self):
        p = self._selected_preset()
        if p:
            self.apply_preset(p)

    def apply_preset(self, p: dict):
        """Apply a complete preset from either the Presets tab or tray menu."""
        if not isinstance(p, dict):
            return

        effect = str(p.get("effect", "") or "")
        params = p.get("params", {})
        if not isinstance(params, dict):
            params = {}

        bri = max(0, min(100, int(p.get("brightness", 100))))
        con = max(0, min(200, int(p.get("contrast", 100))))

        # Apply brightness and contrast through the real controls so labels,
        # settings, and the running driver all stay synchronized.
        self._bc.bri.setValue(bri)
        self._bc.con.setValue(con)

        if effect:
            runtime_params = _runtime_effect_values(effect, params)
            self._driver.set_mode_effect(effect, runtime_params)

            for cls in ALL_EFFECTS:
                if cls.name == effect:
                    self._param_panel.load(cls, saved_vals=params)
                    break

            # Keep the main effect UI and persistence aligned with the preset.
            if self._owner is not None:
                self._owner._settings.set_last_effect(effect)

        # Restore Layer B, its exact settings, and A/B mix.
        if self._owner is not None:
            self._owner._apply_blend_preset_state({
                "effect": p.get("blend_effect", ""),
                "params": p.get("blend_params", {}),
                "alpha": int(p.get("blend_alpha", 0)),
            })

        self._status.setText(f"Loaded: {p.get('name', '?')}")
        self.preset_activated.emit(p)

    # ── delete ────────────────────────────────────────────────────────

    def _delete_selected(self):
        p = self._selected_preset()
        if not p:
            return
        name = p.get("name", "")
        reply = QMessageBox.question(self, "Delete Preset",
                                      f"Delete preset '{name}'?",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._mgr.delete(name)
            self._refresh_list()
            self._status.setText(f"Deleted: {name}")

    # ── export / import ───────────────────────────────────────────────

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Presets", "PolyWollyWin_presets.json", "JSON files (*.json)")
        if path:
            self._mgr.export_to_file(path)
            self._status.setText(f"Exported to {Path(path).name}")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Presets", "", "JSON files (*.json)")
        if path:
            try:
                self._mgr.import_from_file(path)
                self._refresh_list()
                self._status.setText(f"Imported from {Path(path).name}")
            except Exception as e:
                self._status.setText(f"Import failed: {e}")

    def refresh(self):
        self._refresh_list()


# ─────────────────────────────────────────────────────────────────────
# Control window
# ─────────────────────────────────────────────────────────────────────

class ControlWindow(QWidget):
    def __init__(self, driver: MatrixDriver, settings: "Settings" = None):
        super().__init__()
        self._driver   = driver
        self._settings = settings or Settings()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_make_icon())
        self.setMinimumWidth(760)
        self.setStyleSheet(_STYLE)

        # Status row
        self._status = QLabel("⬤ Disconnected")
        self._status.setStyleSheet("color:#555;")
        self._conn_btn = QPushButton("Connect")
        self._conn_btn.setFixedWidth(90); self._conn_btn.setMinimumHeight(30)
        self._conn_btn.clicked.connect(self._connect)
        status_row = QHBoxLayout()
        status_row.addWidget(self._status); status_row.addStretch()
        status_row.addWidget(self._conn_btn)

        # Global BC bar
        self._bc = BCBar()
        self._bc.bri.valueChanged.connect(lambda v: driver.set_brightness(v / 100.0))
        self._bc.con.valueChanged.connect(lambda v: driver.set_contrast(v / 100.0))

        # Build effects tab first so param_panel exists for sequencer tab
        effects_tab_widget = self._effects_tab()

        # GIF tab
        self._gif_tab = GifTab(driver, self._settings)

        # Audio tab
        self._audio_tab = AudioTab(driver, self._settings)

        # Sequencer tab (needs _param_panel which is built in _effects_tab)
        self._seq_tab = SequencerTab(driver, self._param_panel)

        # Presets tab
        self._preset_panel = PresetPanel(
            driver, self._param_panel, self._bc, self._settings, owner=self
        )

        tabs = QTabWidget()
        tabs.addTab(effects_tab_widget, "Effects")
        tabs.addTab(self._gif_tab,       "GIF / Image")
        tabs.addTab(self._audio_tab,     "Audio")
        tabs.addTab(self._paint_tab(),   "Paint")
        tabs.addTab(self._seq_tab,       "Sequencer")
        tabs.addTab(self._preset_panel,  "Presets")

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

        self._start_minimized = QCheckBox("Start minimized")
        self._start_minimized.setStyleSheet("color:#666; font-size:10px;")
        self._start_minimized.setChecked(self._settings.get_start_minimized())
        self._start_minimized.stateChanged.connect(
            lambda state: self._settings.set_start_minimized(bool(state))
        )

        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("color:#555; font-size:10px;")
        author_label  = QLabel(f"by {AUTHOR_NAME}")
        author_label.setStyleSheet("color:#444; font-size:10px;")

        github_btn = QPushButton("GitHub")
        github_btn.setFixedHeight(22); github_btn.setFixedWidth(60)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))

        update_btn = QPushButton("Check Updates")
        update_btn.setFixedHeight(22); update_btn.setFixedWidth(100)
        update_btn.clicked.connect(lambda: check_for_updates(self))

        self._persist_cb = QCheckBox("Remember settings")
        self._persist_cb.setChecked(self._settings.get_persist_enabled())
        self._persist_cb.setStyleSheet("color:#666; font-size:10px;")
        self._persist_cb.stateChanged.connect(
            lambda v: self._settings.set_persist_enabled(bool(v))
        )

        clear_btn = QPushButton("Clear Saved")
        clear_btn.setFixedHeight(20); clear_btn.setFixedWidth(80)
        clear_btn.setStyleSheet(
            "QPushButton{font-size:10px;padding:1px 4px;color:#555;"
            "background:#1a1a1a;border:1px solid #2a2a2a;border-radius:3px;}"
            "QPushButton:hover{color:#f44;border-color:#f44;}"
        )
        clear_btn.clicked.connect(self._clear_settings)

        footer1 = QHBoxLayout()
        footer1.addWidget(self._close_to_tray)
        footer1.addSpacing(8)
        footer1.addWidget(self._startup)
        footer1.addSpacing(8)
        footer1.addWidget(self._start_minimized)
        footer1.addSpacing(8)
        footer1.addWidget(self._persist_cb)
        footer1.addSpacing(6)
        footer1.addWidget(clear_btn)
        footer1.addStretch()

        footer2 = QHBoxLayout()
        footer2.addWidget(self._debug_label)
        footer2.addStretch()
        footer2.addWidget(version_label)
        footer2.addSpacing(6)
        footer2.addWidget(author_label)
        footer2.addSpacing(10)
        footer2.addWidget(github_btn)
        footer2.addWidget(update_btn)

        footer = QVBoxLayout()
        footer.setSpacing(3)
        footer.addLayout(footer1)
        footer.addLayout(footer2)

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
        self._restore()

    # ── tab builders ──────────────────────────────────────────────────

    def _effects_tab(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Crossfade toggle ───────────────────────────────────────────
        xfade_row = QHBoxLayout(); xfade_row.setSpacing(8)
        self._xfade_cb = QCheckBox("Crossfade on switch")
        self._xfade_cb.setChecked(True)
        self._xfade_cb.setStyleSheet("color:#888; font-size:11px;")
        self._xfade_cb.stateChanged.connect(
            lambda v: self._driver.set_crossfade_enabled(bool(v))
        )
        xfade_row.addWidget(self._xfade_cb)

        self._screen_react_cb = QCheckBox("Screen react (dim with screen)")
        self._screen_react_cb.setChecked(False)
        self._screen_react_cb.setStyleSheet("color:#888; font-size:11px;")
        self._screen_react_cb.stateChanged.connect(
            lambda v: self._driver.set_screen_react(bool(v))
        )
        xfade_row.addWidget(self._screen_react_cb)
        xfade_row.addStretch()
        layout.addLayout(xfade_row)

        # ── Blend ─────────────────────────────────────────────────────
        blend_group = QGroupBox("Blend (mix primary effect with a second)")
        bg = QVBoxLayout(blend_group); bg.setSpacing(4)
        blend_btn_row = QHBoxLayout(); blend_btn_row.setSpacing(4)
        blend_btn_row.addWidget(_label("Layer B", "#888"))
        self._blend_label = QLabel("(none)")
        self._blend_label.setStyleSheet("color:#e8001d; font-size:11px;")
        blend_clear = QPushButton("✕ Clear")
        blend_clear.setFixedHeight(22); blend_clear.setFixedWidth(60)
        blend_clear.setStyleSheet(
            "QPushButton{font-size:10px;padding:1px 4px;color:#555;"
            "background:#1a1a1a;border:1px solid #2a2a2a;border-radius:3px;}"
            "QPushButton:hover{color:#f44;border-color:#f44;}"
        )
        blend_clear.clicked.connect(self._blend_clear)
        blend_btn_row.addWidget(self._blend_label)
        blend_btn_row.addStretch()
        blend_btn_row.addWidget(blend_clear)
        bg.addLayout(blend_btn_row)

        blend_sld_row = QHBoxLayout(); blend_sld_row.setSpacing(6)
        blend_sld_row.addWidget(_label("Mix"))
        self._blend_sld = QSlider(Qt.Horizontal)
        self._blend_sld.setRange(0, 100); self._blend_sld.setValue(0)
        self._blend_val = QLabel("A 100% / B 0%")
        self._blend_val.setFixedWidth(96)
        self._blend_val.setStyleSheet("color:#ccc; font-size:11px;")
        self._blend_sld.valueChanged.connect(self._on_blend_slider)
        blend_sld_row.addWidget(self._blend_sld)
        blend_sld_row.addWidget(self._blend_val)
        bg.addLayout(blend_sld_row)
        layout.addWidget(blend_group)

        layout.addWidget(_sep())

        # ── Per-effect parameter panel ─────────────────────────────────
        self._param_panel = ParamPanel(self._driver, self._settings)
        layout.addWidget(self._param_panel)

        layout.addWidget(_sep())

        # ── Effect buttons (3-col grid + Layer-B checkboxes) ───────────
        self._blend_checks: dict[str, QCheckBox] = {}
        btn_grid  = QGridLayout(); btn_grid.setSpacing(6)
        COLS_UI   = 3

        for i, name in enumerate(EFFECT_NAMES):
            row  = i // COLS_UI
            col  = (i % COLS_UI) * 2
            ccol = col + 1

            b = QPushButton(f"▶ {name}")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumHeight(30)
            b.clicked.connect(lambda _, n=name: self._launch_effect(n))
            btn_grid.addWidget(b, row, col)

            cb = QCheckBox()
            cb.setToolTip(f"Set {name} as Blend Layer B")
            cb.setFixedWidth(18)
            cb.stateChanged.connect(lambda state, n=name: self._on_blend_check(n, state))
            self._blend_checks[name] = cb
            btn_grid.addWidget(cb, row, ccol, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        for c in range(COLS_UI):
            btn_grid.setColumnStretch(c * 2, 1)
            btn_grid.setColumnStretch(c * 2 + 1, 0)

        self._effect_scroll = QScrollArea()
        self._effect_scroll.setWidgetResizable(True)
        self._effect_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._effect_scroll.setStyleSheet("QScrollArea{border:none;}")
        btn_w = QWidget()
        btn_w.setLayout(btn_grid)
        self._effect_scroll.setWidget(btn_w)
        layout.addWidget(self._effect_scroll)

        return w

    def _launch_effect(self, name: str):
        """Start an effect without moving the effect-list scroll position."""
        scroll_bar = self._effect_scroll.verticalScrollBar()
        saved_scroll = scroll_bar.value()

        raw_defaults = self._settings.get_effect_default(name)
        self._driver.set_mode_effect(
            name, _runtime_effect_values(name, raw_defaults)
        )
        for cls in ALL_EFFECTS:
            if cls.name == name:
                self._param_panel.load(cls, raw_defaults)
                break

        # ParamPanel.load() rebuilds widgets and can cause Qt to reveal the
        # newly focused control, which used to jump the effect list to the top.
        QTimer.singleShot(0, lambda v=saved_scroll: scroll_bar.setValue(v))

    def _paint_tab(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._paint = PaintEditor()
        self._paint.frame_ready.connect(self._driver.update_paint)
        scroll.setWidget(self._paint)

        send_btn = QPushButton("▶ Send to Matrix")
        send_btn.setMinimumHeight(30)
        send_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        send_btn.clicked.connect(lambda: self._driver.set_mode_paint(
            self._paint.canvas.get_physical()
        ))

        layout.addWidget(scroll)
        layout.addWidget(send_btn)
        return w

    # ── blend helpers ─────────────────────────────────────────────────

    def _on_blend_check(self, name: str, state: int):
        if state:
            for n, cb in self._blend_checks.items():
                if n != name:
                    cb.blockSignals(True); cb.setChecked(False); cb.blockSignals(False)
            self._set_blend_effect(name)
        else:
            self._blend_clear()

    def _on_blend_slider(self, v: int):
        self._blend_val.setText(f"A {100-v}% / B {v}%")
        self._driver.set_blend_alpha(v / 100.0)

    def _set_blend_effect(self, name: str, raw_params: dict | None = None):
        self._blend_label.setText(name)
        self._blend_label.setStyleSheet("color:#e8001d; font-size:11px;")
        if raw_params is None:
            raw_params = self._settings.get_effect_default(name)
        self._driver.set_blend_effect(
            name, _runtime_effect_values(name, raw_params)
        )

    def _blend_clear(self):
        self._blend_label.setText("(none)")
        self._blend_label.setStyleSheet("color:#555; font-size:11px;")
        self._blend_sld.setValue(0)
        self._driver.set_blend_effect(None)
        for cb in self._blend_checks.values():
            cb.blockSignals(True); cb.setChecked(False); cb.blockSignals(False)

    def _get_blend_preset_state(self) -> dict:
        """Capture Layer B, its raw saved values, and the exact mix."""
        name = self._blend_label.text()
        if name == "(none)":
            name = ""
        params = self._settings.get_effect_default(name) if name else {}
        return {
            "effect": name,
            "params": dict(params),
            "alpha": int(self._blend_sld.value()),
        }

    def _apply_blend_preset_state(self, state: dict):
        """Apply Layer B, its exact parameters, and the saved mix."""
        name = str(state.get("effect", "") or "")
        raw_params = state.get("params", {})
        if not isinstance(raw_params, dict):
            raw_params = {}
        alpha = max(0, min(100, int(state.get("alpha", 0))))

        if name and name in self._blend_checks:
            self._set_blend_effect(name, raw_params)
            for effect_name, cb in self._blend_checks.items():
                cb.blockSignals(True)
                cb.setChecked(effect_name == name)
                cb.blockSignals(False)
            self._blend_sld.setValue(alpha)
            self._driver.set_blend_alpha(alpha / 100.0)
        else:
            self._blend_clear()

    def _restore_blend(self):
        """Restore saved Layer B + mix slider without triggering checkbox side effects."""
        name = self._settings.get_blend_effect()
        alpha = max(0, min(100, self._settings.get_blend_alpha()))

        if name and name in self._blend_checks:
            self._set_blend_effect(name)
            for n, cb in self._blend_checks.items():
                cb.blockSignals(True)
                cb.setChecked(n == name)
                cb.blockSignals(False)
            self._blend_sld.setValue(alpha)
            self._driver.set_blend_alpha(alpha / 100.0)
        else:
            self._blend_clear()

    # ── slots ─────────────────────────────────────────────────────────

    def _connect(self):
        if self._driver.connected:
            self._driver.cleanup()
            self._conn_btn.setText("Connect")
            self._conn_btn.setEnabled(True)
            return

        self._conn_btn.setText("Connecting…")
        self._conn_btn.setEnabled(False)
        QApplication.processEvents()

        path = self._driver.connect()
        if path:
            self._status.setText(f"⬤ {path}")
            self._status.setStyleSheet("color:#e8001d;")
            self._conn_btn.setText("Disconnect")
            self._conn_btn.setEnabled(True)
        else:
            self._conn_btn.setText("Retry")
            self._conn_btn.setEnabled(True)

    def _on_status(self, s: str):
        if s == "connected":
            self._status.setStyleSheet("color:#e8001d;")
            self._conn_btn.setText("Disconnect")
            self._conn_btn.setEnabled(True)
        elif s == "disconnected":
            self._status.setText("⬤ Disconnected")
            self._status.setStyleSheet("color:#555;")
            self._conn_btn.setText("Connect")
            self._conn_btn.setEnabled(True)
        else:
            self._status.setText(f"⚠ {s}")
            self._status.setStyleSheet("color:#f80;")
            self._conn_btn.setText("Retry")
            self._conn_btn.setEnabled(True)

    def update_debug_info(self, dt: float):
        fps  = int(1.0 / dt) if dt > 0 else 0
        mode = self._driver.mode.upper()
        conn = "Connected" if self._driver.connected else "Disconnected"
        effect = self._driver.current_effect_name()
        effect_bits = f"   Effect: {effect}" if effect else ""
        self._debug_label.setText(
            f"Device: {conn}   FPS: {fps}   Mode: {mode}{effect_bits}"
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
                exe = sys.executable if not getattr(sys, "frozen", False) else sys.executable
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

    def _restore(self):
        if not self._settings.get_persist_enabled(): return
        self._bc.bri.setValue(self._settings.get_brightness())
        self._bc.con.setValue(self._settings.get_contrast())
        self._gif_tab.restore(self._settings)
        self._audio_tab.restore(self._settings)
        mode = self._settings.get_last_mode()
        if mode.startswith("effect:"):
            try:
                n = mode[7:]
                raw_defaults = self._settings.get_effect_default(n)
                self._driver.set_mode_effect(
                    n, _runtime_effect_values(n, raw_defaults)
                )
                for cls in ALL_EFFECTS:
                    if cls.name == n:
                        self._param_panel.load(cls, raw_defaults)
                        break
            except Exception:
                pass
        elif mode == "gif":
            self._gif_tab.replay()
        elif mode == "audio":
            self._audio_tab.start()
        elif mode == "blank":
            self._driver.set_mode_blank()

        self._restore_blend()

    def _save(self):
        if not self._settings.get_persist_enabled(): return
        self._settings.set_brightness(self._bc.bri.value())
        self._settings.set_contrast(self._bc.con.value())
        self._gif_tab.save(self._settings)
        self._audio_tab.save(self._settings)
        mode   = self._driver.mode
        effect = self._driver.current_effect_name()
        if mode == "effect" and effect:
            self._settings.set_last_mode(f"effect:{effect}")
        else:
            self._settings.set_last_mode(mode)

        blend_effect = self._blend_label.text()
        if blend_effect == "(none)":
            blend_effect = ""
        self._settings.set_blend_effect(blend_effect)
        self._settings.set_blend_alpha(self._blend_sld.value())
        self._settings.save_all()

    def _clear_settings(self):
        self._settings.clear()
        self._persist_cb.setChecked(False)

    def closeEvent(self, event):
        self._save()
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

        menu = QMenu()

        open_act = QAction("Open PolyWollyWin", menu)
        open_act.triggered.connect(window.show)
        open_act.triggered.connect(window.raise_)
        open_act.triggered.connect(window.activateWindow)
        menu.addAction(open_act)

        qc_act = QAction("Quick Controls", menu)
        qc_act.triggered.connect(qc.show_near_tray)
        menu.addAction(qc_act)

        menu.addSeparator()

        blank_act = QAction("⬛ Blank", menu)
        blank_act.triggered.connect(driver.set_mode_blank)
        menu.addAction(blank_act)

        fx_menu = menu.addMenu("Effects")
        for name in EFFECT_NAMES:
            act = QAction(name, fx_menu)
            act.triggered.connect(lambda _, n=name: driver.set_mode_effect(n))
            fx_menu.addAction(act)

        preset_menu = menu.addMenu("Presets")
        self._preset_menu = preset_menu
        self._preset_menu.aboutToShow.connect(self._refresh_preset_menu)
        self._refresh_preset_menu()

        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activate)

    def _refresh_preset_menu(self):
        self._preset_menu.clear()
        presets = PresetManager().load_all()
        if not presets:
            empty = QAction("(no presets saved)", self._preset_menu)
            empty.setEnabled(False)
            self._preset_menu.addAction(empty)
        else:
            for p in presets:
                name = p.get("name", "?")
                act  = QAction(name, self._preset_menu)
                act.triggered.connect(lambda _, preset=p: self._apply_tray_preset(preset))
                self._preset_menu.addAction(act)

    def _apply_tray_preset(self, preset: dict):
        """Use the same complete preset loader as the main Presets tab."""
        self._window._preset_panel.apply_preset(preset)

    def _on_activate(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self._window.isVisible():
                self._window.hide()
            else:
                self._window.show()
                self._window.raise_()
                self._window.activateWindow()

    def _quit(self):
        self._driver.cleanup()
        QApplication.quit()


# ─────────────────────────────────────────────────────────────────────
# Dark stylesheet
# ─────────────────────────────────────────────────────────────────────

_STYLE = """
QWidget {
    background: #141414;
    color: #cccccc;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 4px;
    color: #666;
    font-size: 11px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
}
QPushButton {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 4px 10px;
    color: #ccc;
}
QPushButton:hover  { background: #2a0005; border-color: #e8001d; color: #fff; }
QPushButton:pressed { background: #3a0008; }
QSlider::groove:horizontal {
    height: 4px;
    background: #2a2a2a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px; height: 12px;
    margin: -4px 0;
    border-radius: 6px;
    background: #e8001d;
}
QSlider::sub-page:horizontal { background: #e8001d; border-radius: 2px; }
QTabWidget::pane    { border: 1px solid #2a2a2a; }
QTabBar::tab        { background: #1a1a1a; color: #666; padding: 5px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #e8001d; border-bottom: 2px solid #e8001d; }
QTabBar::tab:hover    { color: #ccc; }
QScrollBar:vertical { width: 6px; background: #111; }
QScrollBar::handle:vertical { background: #333; border-radius: 3px; }
QCheckBox { color: #888; spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #444; border-radius: 3px; background: #1a1a1a; }
QCheckBox::indicator:checked { background: #e8001d; border-color: #e8001d; }
QListWidget { background: #111; border: 1px solid #2a2a2a; color: #ccc; }
QListWidget::item:selected { background: #2a0005; color: #fff; }
QComboBox { background: #1a1a1a; color: #ccc; border: 1px solid #333; padding: 3px 6px; border-radius: 4px; }
QComboBox QAbstractItemView { background: #1a1a1a; color: #ccc; selection-background-color: #2a0005; }
QDoubleSpinBox { background: #1a1a1a; color: #ccc; border: 1px solid #333; padding: 2px 4px; border-radius: 4px; }
"""


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    splash = StartupSplash()
    splash_started = time.monotonic()
    splash.center_on_screen()
    splash.show()
    splash.set_status("Loading application shell...", 10)

    try:
        # Keep one icon alive for the entire process and use it consistently.
        app_icon = _make_icon()
        app.setWindowIcon(app_icon)

        splash.set_status("Loading matrix driver...", 25)
        driver = MatrixDriver()

        splash.set_status("Loading saved settings...", 40)
        settings = Settings()

        splash.set_status("Building quick controls...", 55)
        qc = QuickControls(driver)

        splash.set_status("Building main window...", 70)
        window = ControlWindow(driver, settings)
        window.setWindowIcon(app_icon)
        qc.setWindowIcon(app_icon)
        window.sync_quick_controls(qc)

        splash.set_status("Preparing system tray...", 82)
        tray = TrayApp(driver, qc, window)
        tray.setIcon(app_icon)
        tray._stable_icon = app_icon
        tray.show()

        splash.set_status("Finalizing startup...", 92)
        if settings.get_start_minimized():
            window.hide()
        else:
            window.show()
            window.raise_()
            window.activateWindow()

        # Auto-connect whether the main window is visible or minimized.
        QTimer.singleShot(500, window._connect)

        last_t = [time.monotonic()]

        def _tick():
            now = time.monotonic()
            dt = now - last_t[0]
            last_t[0] = now
            driver.tick(dt)
            window.update_debug_info(dt)

        timer = QTimer()
        timer.setInterval(TICK_MS)
        timer.timeout.connect(_tick)
        timer.start()

        splash.set_status("Ready", 100)

        elapsed_ms = int(
            (time.monotonic() - splash_started) * 1000
        )
        remaining_ms = max(0, 4000 - elapsed_ms)
        splash.finish_later(remaining_ms)

        sys.exit(app.exec())

    except BaseException as exc:
        log_path = _write_startup_crash_log(
            type(exc), exc, exc.__traceback__
        )
        splash.show_error(exc, log_path)
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
