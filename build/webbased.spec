# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parent if SPEC_DIR.name.lower() == "build" else SPEC_DIR

PY_ROOT = Path(sys.base_prefix).resolve()
TK_SOURCE_CANDIDATES = [
    PY_ROOT / "tcl",
    Path(r"C:\pinokio\bin\miniconda\Library\lib"),
    Path(r"C:\pinokio\bin\miniconda\Library\mingw64\lib"),
]
TK_DATA = []
for candidate in TK_SOURCE_CANDIDATES:
    if (candidate / "tcl8.6" / "init.tcl").is_file() and (candidate / "tk8.6" / "tk.tcl").is_file():
        TK_DATA = [
            (str(candidate / "tcl8.6"), "_tcl_data"),
            (str(candidate / "tk8.6"), "_tk_data"),
        ]
        break

TKINTER_PACKAGE = PY_ROOT / "Lib" / "tkinter"
TKINTER_DATA = [(str(TKINTER_PACKAGE), "tkinter")] if TKINTER_PACKAGE.is_dir() else []

TK_BINARIES = []
for name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
    path = PY_ROOT / "DLLs" / name
    if path.is_file():
        TK_BINARIES.append((str(path), "."))

# Wichtig:
# - data NICHT in PyInstaller packen. Laufzeitdaten/Tokens/Profile werden neben die EXE kopiert.
# - modules werden ebenfalls neben die EXE kopiert, damit Plugins erweiterbar bleiben.
# - PySide6/QtWebEngine/WebView2 ist komplett raus. Desktop-Overlay nutzt jetzt Tkinter/Win32.
a = Analysis(
    [str(PROJECT_ROOT / 'run_webbased.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=TK_BINARIES,
    datas=[
        (str(PROJECT_ROOT / 'core'), 'core'),
        (str(PROJECT_ROOT / 'shared'), 'shared'),
        *TKINTER_DATA,
        *TK_DATA,
    ],
    hiddenimports=[
        'tkinter',
        '_tkinter',
        'requests',
        'websockets',
        'TikTokLive',
        'TikTokLive.events',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'shiboken6',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'qtpy',
        'cefpython3',
        'webview',
        'pythonnet',
        'clr_loader',
        'numpy',
        'pandas',
        'matplotlib',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='webbased',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(PROJECT_ROOT / 'core' / 'host' / 'static' / 'img' / 'app.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='webbased',
)
