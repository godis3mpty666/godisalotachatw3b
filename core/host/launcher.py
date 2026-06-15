from __future__ import annotations

import sys
from pathlib import Path

from core.runtime.webbased_server import run


def base_dir() -> str:
    """Return the portable runtime directory next to the script or executable."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    return str(Path(__file__).resolve().parents[2])


def main() -> None:
    if "--desktop-chat" in sys.argv:
        from core.host.desktop_window import run_desktop_chat
        index = sys.argv.index("--desktop-chat")
        url = sys.argv[index + 1] if len(sys.argv) > index + 1 else "http://127.0.0.1:17890/desktop-chat"
        raise SystemExit(run_desktop_chat(url))
    run(base_dir(), open_browser=True)
