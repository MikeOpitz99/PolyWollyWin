# -*- mode: python ; coding: utf-8 -*-
import os


# ---------------------------------------------------------------------
# PolyWollyWin optimized ONEDIR PyInstaller specification
#
# Keep:
#   QtCore, QtGui, QtWidgets, QtNetwork
#   Windows platform plugin
#   GIF, ICO, JPEG, SVG, WebP image plugins
#   Pillow formats used by PolyWollyWin
#
# Remove:
#   Qt Quick/QML/PDF/Virtual Keyboard/OpenGL extras
#   unused Qt platforms and input plugins
#   Qt translation catalogs
#   unused Pillow format plugins and native extensions
# ---------------------------------------------------------------------


def _normalise_toc_name(value):
    return str(value).replace("\\", "/").lower()


def _keep_binary(entry):
    name = _normalise_toc_name(entry[0])

    # Large Qt libraries not used by the application.
    unwanted_qt_binaries = {
        "pyside6/qt6quick.dll",
        "pyside6/qt6qml.dll",
        "pyside6/qt6qmlmodels.dll",
        "pyside6/qt6pdf.dll",
        "pyside6/qt6virtualkeyboard.dll",
        "pyside6/qt6opengl.dll",
        "pyside6/qt6openglwidgets.dll",
        "pyside6/opengl32sw.dll",
    }
    if name in unwanted_qt_binaries:
        return False

    # Keep qwindows only. PolyWollyWin does not run headlessly or through
    # Direct2D/minimal/offscreen platform backends.
    if "/pyside6/plugins/platforms/" in f"/{name}":
        return name.endswith("/qwindows.dll")

    # No touch or virtual-keyboard support.
    if "/pyside6/plugins/platforminputcontexts/" in f"/{name}":
        return False
    if name.endswith("/pyside6/plugins/generic/qtuiotouchplugin.dll"):
        return False

    # Retain only formats offered by the application UI or used by assets.
    if "/pyside6/plugins/imageformats/" in f"/{name}":
        keep_image_plugins = {
            "qgif.dll",
            "qico.dll",
            "qjpeg.dll",
            "qsvg.dll",
            "qwebp.dll",
        }
        return name.rsplit("/", 1)[-1] in keep_image_plugins

    # Unused Pillow native extensions.
    unwanted_pillow_binaries = {
        "pil/_avif.cp314-win_amd64.pyd",
        "pil/_imagingcms.cp314-win_amd64.pyd",
        "pil/_imagingtk.cp314-win_amd64.pyd",
    }
    if name in unwanted_pillow_binaries:
        return False

    return True


def _keep_data(entry):
    name = _normalise_toc_name(entry[0])

    # PolyWollyWin has no language selector and uses English UI text.
    if "/pyside6/translations/" in f"/{name}":
        return False

    return True


a = Analysis(
    [os.path.join(SPECPATH, "app.py")],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        (os.path.join(SPECPATH, "assets"), "assets"),
    ],
    hiddenimports=[
        "hid",
        "pynput",
        "pynput.keyboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "doctest",
        "pydoc",
        "xmlrpc",

        # Non-Windows pynput backends.
        "pynput.mouse",
        "pynput.mouse._darwin",
        "pynput.mouse._xorg",
        "pynput.keyboard._darwin",
        "pynput.keyboard._xorg",
        "pynput.keyboard._uinput",
        "pynput._util.darwin",
        "pynput._util.xorg",
        "pynput._util.uinput",

        # Unused Qt modules.
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtConcurrent",
        "PySide6.QtDataVisualization",
        "PySide6.QtDBus",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtLocation",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtPrintSupport",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtSensors",
        "PySide6.QtSerialBus",
        "PySide6.QtSerialPort",
        "PySide6.QtSpatialAudio",
        "PySide6.QtSql",
        "PySide6.QtStateMachine",
        "PySide6.QtTest",
        "PySide6.QtTextToSpeech",
        "PySide6.QtVirtualKeyboard",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
        "PySide6.QtXml",

        # Pillow formats PolyWollyWin does not offer or use.
        "PIL.AvifImagePlugin",
        "PIL.BlpImagePlugin",
        "PIL.BufrStubImagePlugin",
        "PIL.CurImagePlugin",
        "PIL.DcxImagePlugin",
        "PIL.DdsImagePlugin",
        "PIL.EpsImagePlugin",
        "PIL.FitsImagePlugin",
        "PIL.FliImagePlugin",
        "PIL.FpxImagePlugin",
        "PIL.FtexImagePlugin",
        "PIL.GbrImagePlugin",
        "PIL.GribStubImagePlugin",
        "PIL.Hdf5StubImagePlugin",
        "PIL.IcnsImagePlugin",
        "PIL.ImImagePlugin",
        "PIL.ImtImagePlugin",
        "PIL.IptcImagePlugin",
        "PIL.Jpeg2KImagePlugin",
        "PIL.McIdasImagePlugin",
        "PIL.MicImagePlugin",
        "PIL.MpegImagePlugin",
        "PIL.MpoImagePlugin",
        "PIL.MspImagePlugin",
        "PIL.PalmImagePlugin",
        "PIL.PcdImagePlugin",
        "PIL.PcxImagePlugin",
        "PIL.PdfImagePlugin",
        "PIL.PdfParser",
        "PIL.PixarImagePlugin",
        "PIL.PpmImagePlugin",
        "PIL.PsdImagePlugin",
        "PIL.QoiImagePlugin",
        "PIL.SgiImagePlugin",
        "PIL.SpiderImagePlugin",
        "PIL.SunImagePlugin",
        "PIL.TgaImagePlugin",
        "PIL.WmfImagePlugin",
        "PIL.XVThumbImagePlugin",
        "PIL.XbmImagePlugin",
        "PIL.XpmImagePlugin",
        "PIL.ImageCms",
        "PIL.ImageTk",
        "PIL._avif",
        "PIL._imagingcms",
        "PIL._imagingtk",
    ],
    noarchive=False,
    optimize=2,
)

# Some Qt and Pillow files are pulled in as indirect binary/data dependencies
# even when their Python modules are excluded. Filter those final TOCs.
a.binaries = [entry for entry in a.binaries if _keep_binary(entry)]
a.datas = [entry for entry in a.datas if _keep_data(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PolyWollyWin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=[os.path.join(SPECPATH, "assets", "pww.ico")],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PolyWollyWin",
)
