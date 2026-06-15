from __future__ import annotations
import os, sys
from pathlib import Path
from server.webbased_server import run

def base_dir():
    # Important: runtime base is always the folder of this script/EXE.
    # Templates/static are resolved separately inside the server, including PyInstaller _internal.
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    return str(Path(__file__).resolve().parent)

if __name__ == "__main__":
    run(base_dir(), open_browser=True)
