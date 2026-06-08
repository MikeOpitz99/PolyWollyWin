# -*- mode: python ; coding: utf-8 -*-
import os

a = Analysis(
    [os.path.join(SPECPATH, 'app.py')],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        # Add runtime assets here if app.py loads them from disk.
        # Example: (os.path.join(SPECPATH, 'assets', 'pww.ico'), 'assets'),
    ],
    hiddenimports=[
        'hid',       # hidapi — sometimes not auto-detected
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PolyWollyWin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(SPECPATH, 'assets', 'pww.ico')],
)