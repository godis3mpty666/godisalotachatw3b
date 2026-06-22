from __future__ import annotations

import sys
from pathlib import Path

def base_dir() -> str:
    """Return the portable runtime directory next to the script or executable."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    return str(Path(__file__).resolve().parents[2])


def main() -> None:
    if "--desktop-chat" in sys.argv:
        try:
            from core.host.desktop_window import run_desktop_chat
            index = sys.argv.index("--desktop-chat")
            url = sys.argv[index + 1] if len(sys.argv) > index + 1 else "http://127.0.0.1:17890/desktop-chat"
            raise SystemExit(run_desktop_chat(url))
        except SystemExit:
            raise
        except Exception:
            # The desktop process has no console in production. Keep its import
            # failure visible instead of silently returning to the main app.
            try:
                import traceback
                log_dir = Path(sys.executable).resolve().parent / "data" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / "desktop_chat_error.log").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
            raise
    # Importing the full backend is unnecessary for the desktop child and can
    # fail before it gets a chance to handle --desktop-chat in frozen builds.
    from core.runtime.webbased_server import run
    run(base_dir(), open_browser=True)
