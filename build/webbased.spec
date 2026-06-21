# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parent if SPEC_DIR.name.lower() == "build" else SPEC_DIR

# Wichtig:
# - data NICHT in PyInstaller packen. Laufzeitdaten/Tokens/Profile werden neben die EXE kopiert.
# - modules werden ebenfalls neben die EXE kopiert, damit Plugins erweiterbar bleiben.
# - PySide6/QtWebEngine/WebView2 ist komplett raus. Desktop-Overlay nutzt jetzt Tkinter/Win32.
a = Analysis(
    [str(PROJECT_ROOT / 'run_webbased.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / 'core'), 'core'),
        (str(PROJECT_ROOT / 'shared'), 'shared'),
        (str(PROJECT_ROOT / 'assets'), 'assets'),
        # Nur die Data-Python-Helfer packen, NICHT den ganzen data-Ordner mit Tokens/Caches.
        (str(PROJECT_ROOT / 'data' / '__init__.py'), 'data'),
        (str(PROJECT_ROOT / 'data' / 'paths.py'), 'data'),
    ],
    hiddenimports=[
        'requests',
        'websocket',
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
