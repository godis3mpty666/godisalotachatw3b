from __future__ import annotations

import ctypes
import base64
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Any


WINDOW_TITLE = "godisalotachat Desktop Chat"
TRANSPARENT_KEY = "#010203"
DEFAULT_SIZE = (780, 820)
MIN_SIZE = (320, 240)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
MB_OK = 0x00000000
GA_ROOT = 2

user32 = ctypes.windll.user32 if os.name == "nt" else None

PLATFORM_LABELS = {
    "twitch": "Twitch",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "kick": "Kick",
}
PLATFORM_ICONS = {
    "twitch": "▣",
    "tiktok": "♪",
    "youtube": "▶",
    "kick": "K",
}
PLATFORM_COLORS = {
    "twitch": "#9146ff",
    "tiktok": "#161616",
    "youtube": "#ff0000",
    "kick": "#53fc18",
}


def _message_box(text: str, title: str = WINDOW_TITLE, flags: int = MB_OK) -> int:
    if user32 is None:
        print(f"{title}: {text}")
        return 1
    return int(user32.MessageBoxW(None, str(text), str(title), flags))


def _log(text: str) -> None:
    try:
        print(f"[desktop-window] {text}", flush=True)
    except Exception:
        pass


def _get_window_long(hwnd: int) -> int:
    if sys.maxsize > 2**32:
        return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))
    return int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))


def _set_window_long(hwnd: int, value: int) -> None:
    if sys.maxsize > 2**32:
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, value)
    else:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, value)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)


def _set_clickthrough(hwnd: int | None, enabled: bool) -> None:
    if user32 is None or not hwnd:
        return
    try:
        style = _get_window_long(hwnd)
        # Tkinter setzt fuer -transparentcolor selbst WS_EX_LAYERED und die
        # Layer-Attribute. Wir duerfen das hier nicht neu erzwingen, sonst
        # kann der transparente Farbkey kaputtgehen und das Fenster wird schwarz.
        style |= WS_EX_TOOLWINDOW
        style &= ~WS_EX_APPWINDOW
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        _set_window_long(hwnd, style)
    except Exception as exc:
        _log(f"click-through konnte nicht gesetzt werden: {exc}")



def _candidate_hwnds_from_widget(widget) -> list[int]:
    """Tkinter erzeugt mehrere HWNDs (Toplevel/Canvas/Wrapper).
    Click-through muss auf alle relevanten Handles, sonst blockt eines davon
    weiterhin die Maus und das Spiel darunter bekommt keine Klicks.
    """
    if user32 is None or widget is None:
        return []
    handles: list[int] = []
    try:
        hwnd = int(widget.winfo_id())
        if hwnd:
            handles.append(hwnd)
            try:
                root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT))
                if root_hwnd:
                    handles.append(root_hwnd)
            except Exception:
                pass
    except Exception:
        pass
    # Dedupe, Reihenfolge erhalten
    out: list[int] = []
    for hwnd in handles:
        if hwnd and hwnd not in out:
            out.append(hwnd)
    return out


def _set_widget_clickthrough(widget, enabled: bool) -> None:
    for hwnd in _candidate_hwnds_from_widget(widget):
        _set_clickthrough(hwnd, enabled)
    try:
        for child in widget.winfo_children():
            _set_widget_clickthrough(child, enabled)
    except Exception:
        pass

def _hex_to_rgb(value: str | None, fallback: str = "#0d101d") -> tuple[int, int, int]:
    s = str(value or fallback).strip().lstrip("#")
    if len(s) != 6:
        s = fallback.lstrip("#")
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except Exception:
        return 13, 16, 29


def _safe_draw_color(hex_color: str | None, fallback: str = "#0d101d") -> str:
    r, g, b = _hex_to_rgb(hex_color, fallback)
    # Niemals exakt den transparenten Farbkey verwenden, sonst stanzt Windows das
    # Element komplett aus. Auch sehr nahe Farben vermeiden wir, weil manche
    # Treiber/Web-Captures das sonst wie Schwarz/Flackern behandeln.
    if (r, g, b) in ((1, 2, 3), (2, 3, 4), (0, 0, 0)):
        r, g, b = (13, 16, 29)
    return f"#{r:02x}{g:02x}{b:02x}"



def _opacity_to_window_alpha(opacity_percent: int | float | None) -> float:
    try:
        value = float(opacity_percent)
    except Exception:
        value = 82.0
    # Tkinter kann keine echte Alpha-Transparenz pro Canvas-Rechteck.
    # Deshalb nutzen wir hier stabile globale Fenster-Alpha: keine Muster,
    # kein Weiss/Schwarz-Kippen, dafuer wird auch Text leicht transparent.
    value = max(18.0, min(100.0, value))
    return value / 100.0

def _opacity_stipple(_opacity_percent: int | float | None) -> str | None:
    # Wichtig: Tkinter kann auf Canvas-Rechtecken keine saubere, weiche
    # Alpha-Transparenz rendern. Stipple erzeugt ein sichtbares Muster,
    # Farbmischung gegen den Transparent-Key kippt je nach Wert nach Schwarz/Weiss.
    # Deshalb wird die Box-Opacity im nativen Desktop-Overlay bewusst ignoriert.
    # Die Flaeche ausserhalb der Boxen bleibt weiterhin echt transparent.
    return None

def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", str(value), flags=re.I)
    text = re.sub(r"<img[^>]*alt=['\"]?([^'\" >]+).*?>", r"\1", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _user_color(platform: str, user: str) -> str:
    h = 2166136261
    for ch in f"{platform}:{user}":
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    # einfache HSL->RGB Annäherung via colorsys
    import colorsys

    r, g, b = colorsys.hls_to_rgb((abs(h) % 360) / 360.0, 0.68, 0.78)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _fetch_json(url: str, timeout: float = 0.8) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _post_json(url: str, payload: Any, timeout: float = 1.2) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=timeout).read()


def _ping_url(url: str, timeout: float = 0.55) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            res.read(1)
        return True
    except Exception:
        return False


def _app_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]


@dataclass
class DragState:
    mode: str = ""
    target: str = ""
    start_x: int = 0
    start_y: int = 0
    start_box: dict[str, int] | None = None
    start_win_w: int = 0
    start_win_h: int = 0
    start_win_x: int = 0
    start_win_y: int = 0


class DesktopTkOverlay:
    def __init__(self, url: str):
        import tkinter as tk
        from tkinter import font as tkfont

        self.tk = tk
        self.tkfont = tkfont
        self.url = url
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme or 'http'}://{parsed.netloc}"
        self.base_url = base
        self.runtime_url = f"{base}/api/runtime"
        self.layout_url = f"{base}/api/desktop-chat/layout"
        self.state_url = f"{base}/api/desktop-chat/state"
        self.chat_url = f"{base}/api/chat-state"
        self.nowplaying_url = f"{base}/api/nowplaying"
        self.language = "de"

        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_KEY)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception as exc:
            _log(f"transparentcolor nicht verfuegbar: {exc}")
        self.root.geometry(f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}+80+80")
        self.root.minsize(*MIN_SIZE)

        # Zwei native Fenster:
        # 1) bg_root rendert nur die halbtransparenten Box-Hintergruende.
        # 2) root rendert Text/Symbole/Edit-Griffe voll deckend darueber.
        # Damit wird nur der Chathintergrund transparent, nicht der Inhalt.
        self.bg_root = tk.Toplevel(self.root)
        self.bg_root.title(WINDOW_TITLE + " Background")
        self.bg_root.overrideredirect(True)
        self.bg_root.attributes("-topmost", True)
        self.bg_root.configure(bg=TRANSPARENT_KEY)
        try:
            self.bg_root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception as exc:
            _log(f"background transparentcolor nicht verfuegbar: {exc}")
        self.bg_root.geometry(f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}+80+80")

        self.bg_canvas = tk.Canvas(self.bg_root, highlightthickness=0, bd=0, bg=TRANSPARENT_KEY)
        self.bg_canvas.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=TRANSPARENT_KEY)
        self.canvas.pack(fill="both", expand=True)

        self.layout: dict[str, Any] = {}
        self.editing = False
        self.hwnd: int | None = None
        self.bg_hwnd: int | None = None
        self.drag = DragState()
        self.last_chat_state: dict[str, Any] = {}
        self.last_nowplaying: dict[str, Any] = {}
        self.last_runtime_ok = True
        self.runtime_fail_count = 0
        self._save_after_id: str | None = None
        self._last_render_key = ""
        self._last_clickthrough_state: bool | None = None
        self._last_window_geometry: tuple[int, int, int, int] | None = None
        self._z_order_done = False
        self._last_bg_alpha: float | None = None
        self._platform_images: dict[str, Any] = {}
        self._chat_media_images: dict[str, Any] = {}
        self._chat_media_failures: dict[str, float] = {}
        self._chat_media_retry_scheduled = False
        self._chat_media_animation_scheduled = False

        self.canvas.bind("<ButtonPress-1>", self._pointer_down)
        self.canvas.bind("<B1-Motion>", self._pointer_move)
        self.canvas.bind("<ButtonRelease-1>", self._pointer_up)
        self.canvas.bind("<Configure>", self._on_configure)
        self.root.bind("<Escape>", lambda _e: self._set_remote_editing(False))
        self.root.bind("<F8>", lambda _e: self._set_remote_editing(not self.editing))

    def _on_configure(self, _event=None) -> None:
        geometry = (
            int(self.root.winfo_x()),
            int(self.root.winfo_y()),
            int(self.root.winfo_width()),
            int(self.root.winfo_height()),
        )
        if self._last_window_geometry == geometry:
            return
        self._last_window_geometry = geometry
        # Tk applies geometry changes asynchronously. Sync on the next idle
        # turn so the transparent background uses the final x/y as well as size.
        self.root.after_idle(self._sync_background_window)
        self.render()

    def run(self) -> int:
        self.root.after(100, self._init_window)
        self.root.after(150, self._poll)
        self.root.mainloop()
        return 0

    def _init_window(self) -> None:
        try:
            self.hwnd = int(self.root.winfo_id())
            self.bg_hwnd = int(self.bg_root.winfo_id())
        except Exception as exc:
            _log(f"hwnd init fehlgeschlagen: {exc}")
        self._load_layout()
        self._restore_window_geometry()
        self._sync_background_window()
        self._ensure_z_order()
        self.render()
        # Erst nach dem ersten Rendern click-through setzen. Hintergrundfenster
        # bleibt immer durchklickbar, Eingaben laufen nur ueber das Vorderfenster.
        self.root.after(250, lambda: self._apply_clickthrough_state(True))

    def _sync_background_window(self) -> None:
        try:
            self.root.update_idletasks()
            geom = f"{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}"
            if self.bg_root.winfo_geometry() != geom:
                self.bg_root.geometry(geom)
        except Exception:
            pass

    def _ensure_z_order(self) -> None:
        # Z-Reihenfolge nur gezielt setzen, nicht in jeder Poll-/Render-Runde.
        # Das staendige lower/lift war bei zwei transparenten Fenstern sichtbar am Zucken beteiligt.
        try:
            self.bg_root.lower(self.root)
            self.root.lift(self.bg_root)
            self._z_order_done = True
        except Exception:
            try:
                self.bg_root.lift()
                self.root.lift()
                self._z_order_done = True
            except Exception:
                pass

    def _apply_clickthrough_state(self, force: bool = False) -> None:
        # Style-Aenderungen an transparenten Tk-Fenstern sind teuer und koennen sichtbar flackern.
        # Darum nur anwenden, wenn sich der Modus wirklich geaendert hat oder explizit erzwungen wird.
        through = not self.editing
        if not force and self._last_clickthrough_state == through:
            return
        self._last_clickthrough_state = through

        # Hintergrundfenster darf niemals Maus fressen.
        _set_widget_clickthrough(self.bg_root, True)
        _set_widget_clickthrough(self.bg_canvas, True)

        # Vorderfenster: im Normalmodus komplett durchklickbar, im Editmode klickbar.
        _set_widget_clickthrough(self.root, through)
        _set_widget_clickthrough(self.canvas, through)

    def _load_layout(self) -> None:
        try:
            data = _fetch_json(self.layout_url)
            if isinstance(data, dict):
                self.layout = data
        except Exception as exc:
            _log(f"layout konnte nicht geladen werden: {exc}")
        self.layout.setdefault("layoutVersion", 3)
        self.layout.setdefault("viewerBar", {"x": 16, "y": 16, "w": 720, "h": 64})
        self.layout.setdefault("spotifyPanel", {"x": 16, "y": 92, "w": 720, "h": 84})
        self.layout.setdefault("chatPanel", {"x": 16, "y": 92, "w": 720, "h": 420})
        self.layout.setdefault("alertPanel", {"x": 16, "y": 524, "w": 720, "h": 188})
        self.layout.setdefault("systemInfoPanel", {"x": 16, "y": 724, "w": 720, "h": 112})
        self.layout.setdefault("alerts", {"enabled": True, "maxItems": 5, "showTimestamp": True, "platforms": {"twitch": True, "tiktok": True, "youtube": True, "kick": True}})
        self.layout.setdefault("systemInfo", {"enabled": True})
        self.layout.setdefault("viewers", {"enabled": True})
        if "spotify" not in self.layout and isinstance(self.layout.get("spotifyPanel"), dict):
            self.layout["spotify"] = {"enabled": True}
        self.layout.setdefault("spotify", {"enabled": False})
        self.layout.setdefault(
            "style",
            {
                "background": "#0d101d",
                "opacity": 82,
                "radius": 16,
                "fontFamily": "Segoe UI",
                "fontSize": 16,
                "textColor": "#ffffff",
            },
        )
        self.layout.setdefault("window", {"x": 80, "y": 80, "w": DEFAULT_SIZE[0], "h": DEFAULT_SIZE[1]})

    def _restore_window_geometry(self) -> None:
        window = self.layout.get("window") or {}
        try:
            x = max(-4000, min(4000, int(window.get("x", 80))))
            y = max(-4000, min(4000, int(window.get("y", 80))))
            w = max(MIN_SIZE[0], min(4000, int(window.get("w", DEFAULT_SIZE[0]))))
            h = max(MIN_SIZE[1], min(4000, int(window.get("h", DEFAULT_SIZE[1]))))
            try:
                if user32 is not None:
                    screen_x = int(user32.GetSystemMetrics(76))
                    screen_y = int(user32.GetSystemMetrics(77))
                    screen_w = int(user32.GetSystemMetrics(78))
                    screen_h = int(user32.GetSystemMetrics(79))
                else:
                    screen_x = 0
                    screen_y = 0
                    screen_w = int(self.root.winfo_screenwidth())
                    screen_h = int(self.root.winfo_screenheight())
                if x > screen_x + screen_w - 80 or y > screen_y + screen_h - 80 or x + w < screen_x + 80 or y + h < screen_y + 80:
                    x, y = 80, 80
            except Exception:
                pass
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception as exc:
            _log(f"Fensterposition konnte nicht geladen werden: {exc}")

    def _capture_window_geometry(self) -> None:
        self.layout["window"] = {
            "x": int(self.root.winfo_x()),
            "y": int(self.root.winfo_y()),
            "w": int(self.root.winfo_width()),
            "h": int(self.root.winfo_height()),
        }

    def _stable_json_key(self, value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(value)

    def _close_due_to_runtime_loss(self) -> None:
        try:
            _log("runtime nicht mehr erreichbar, Desktopfenster wird geschlossen")
            self.bg_root.destroy()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _poll(self) -> None:
        # Wenn der Browser/Main-Host geschlossen wurde, muss das Overlay auch weg.
        # Ein einzelner Timeout kann aber beim Build/Reload kurz passieren, deshalb
        # schliessen wir nach zwei direkten Fehlschlaegen (~1-1.5s) statt endlos
        # offen zu bleiben wie vorher.
        runtime = None
        try:
            runtime = _fetch_json(self.runtime_url, timeout=0.55)
        except Exception:
            runtime = None

        if not isinstance(runtime, dict):
            self.runtime_fail_count += 1
            if self.runtime_fail_count >= 2:
                self._close_due_to_runtime_loss()
                return
            self.root.after(500, self._poll)
            return

        # Wenn das eigentliche Browserfenster geschlossen wurde, endet der Main-UI-Heartbeat.
        # Der Server bleibt je nach Timing noch einige Sekunden offen; das Overlay soll aber direkt mitgehen.
        try:
            if bool(runtime.get("ui_heartbeat_enabled")):
                age = float(runtime.get("ui_heartbeat_age", 0.0))
                if age > 5.5:
                    _log("main ui heartbeat verloren, Desktopfenster wird geschlossen")
                    self._close_due_to_runtime_loss()
                    return
        except Exception:
            pass

        self.runtime_fail_count = 0
        self.last_runtime_ok = True
        new_language = "en" if str(runtime.get("language") or "de").lower().startswith("en") else "de"
        language_changed = new_language != self.language
        self.language = new_language
        needs_render = False
        if language_changed:
            needs_render = True

        try:
            state = _fetch_json(self.state_url, timeout=0.5)
            if isinstance(state, dict):
                new_editing = bool(state.get("editing", False))
                if self.editing != new_editing:
                    self.editing = new_editing
                    self._apply_clickthrough_state()
                    if self.editing:
                        self._ensure_z_order()
                        try:
                            self.root.focus_force()
                        except Exception:
                            pass
                    needs_render = True
        except Exception as exc:
            _log(f"edit-state konnte nicht gelesen werden: {exc}")

        try:
            chat = _fetch_json(self.chat_url, timeout=0.65)
            if isinstance(chat, dict):
                new_key = self._stable_json_key(chat)
                old_key = self._stable_json_key(self.last_chat_state)
                if new_key != old_key:
                    self.last_chat_state = chat
                    needs_render = True
        except Exception as exc:
            _log(f"chat-state konnte nicht gelesen werden: {exc}")

        if self.editing or bool((self.layout.get("spotify") or {}).get("enabled", False)):
            try:
                nowplaying = _fetch_json(self.nowplaying_url, timeout=0.65)
                if isinstance(nowplaying, dict):
                    new_key = self._stable_json_key(nowplaying)
                    old_key = self._stable_json_key(self.last_nowplaying)
                    if new_key != old_key:
                        self.last_nowplaying = nowplaying
                        needs_render = True
            except Exception as exc:
                _log(f"nowplaying konnte nicht gelesen werden: {exc}")

        try:
            layout = _fetch_json(self.layout_url, timeout=0.65)
            if isinstance(layout, dict) and not self.drag.mode:
                layout.setdefault("style", {})
                new_key = self._stable_json_key(layout)
                old_key = self._stable_json_key(self.layout)
                if new_key != old_key:
                    self.layout = layout
                    needs_render = True
        except Exception as exc:
            _log(f"layout konnte nicht aktualisiert werden: {exc}")

        if needs_render:
            self.render()

        self.root.after(900, self._poll)

    def set_editing(self, editing: bool) -> None:
        changed = self.editing != editing
        self.editing = editing
        self._apply_clickthrough_state(True)
        if editing:
            self._ensure_z_order()
            try:
                self.root.focus_force()
            except Exception:
                pass
        if changed:
            self.render()

    def _set_remote_editing(self, editing: bool) -> None:
        try:
            _post_json(self.state_url.rsplit("/", 1)[0] + "/edit", {"editing": editing})
        except Exception:
            pass
        self.set_editing(editing)

    def _box_at(self, x: int, y: int) -> tuple[str, str] | None:
        # Native Resize-Griff fuer das komplette Fenster
        if self.editing and x >= self.root.winfo_width() - 34 and y >= self.root.winfo_height() - 34:
            return ("window-resize", "window")
        for box_id in ("viewerBar", "spotifyPanel", "chatPanel", "alertPanel", "systemInfoPanel"):
            if box_id == "viewerBar" and not self.editing and not bool((self.layout.get("viewers") or {}).get("enabled", True)):
                continue
            if box_id == "spotifyPanel" and not self.editing and not bool((self.layout.get("spotify") or {}).get("enabled", False)):
                continue
            if box_id == "alertPanel" and not self.editing and not bool((self.layout.get("alerts") or {}).get("enabled", True)):
                continue
            if box_id == "systemInfoPanel" and not self.editing:
                info = self.last_chat_state.get("system_info", {}) if isinstance(self.last_chat_state, dict) else {}
                if not bool((self.layout.get("systemInfo") or {}).get("enabled", True)) or not bool(info.get("active")):
                    continue
            box = self.layout.get(box_id) or {}
            bx, by, bw, bh = int(box.get("x", 0)), int(box.get("y", 0)), int(box.get("w", 0)), int(box.get("h", 0))
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if self.editing and x >= bx + bw - 28 and y >= by + bh - 28:
                    return ("box-resize", box_id)
                return ("box-move", box_id)
        if self.editing:
            return ("window-move", "window")
        return None

    def _pointer_down(self, event) -> None:
        if not self.editing:
            return
        hit = self._box_at(int(event.x), int(event.y))
        if not hit:
            return
        mode, target = hit
        self.drag = DragState(
            mode=mode,
            target=target,
            start_x=int(event.x_root),
            start_y=int(event.y_root),
            start_box=dict(self.layout.get(target, {})) if target in self.layout else None,
            start_win_w=self.root.winfo_width(),
            start_win_h=self.root.winfo_height(),
            start_win_x=self.root.winfo_x(),
            start_win_y=self.root.winfo_y(),
        )

    def _pointer_move(self, event) -> None:
        if not self.drag.mode:
            return
        dx = int(event.x_root) - self.drag.start_x
        dy = int(event.y_root) - self.drag.start_y
        if self.drag.mode == "window-move":
            self.root.geometry(f"+{self.drag.start_win_x + dx}+{self.drag.start_win_y + dy}")
            self._sync_background_window()
        elif self.drag.mode == "window-resize":
            w = max(MIN_SIZE[0], self.drag.start_win_w + dx)
            h = max(MIN_SIZE[1], self.drag.start_win_h + dy)
            self.root.geometry(f"{w}x{h}")
            self._sync_background_window()
        elif self.drag.target in self.layout and self.drag.start_box:
            box = self.layout[self.drag.target]
            start = self.drag.start_box
            if self.drag.mode == "box-resize":
                box["w"] = max(140, int(start.get("w", 200)) + dx)
                box["h"] = max(42, int(start.get("h", 80)) + dy)
            else:
                box["x"] = max(0, int(start.get("x", 0)) + dx)
                box["y"] = max(0, int(start.get("y", 0)) + dy)
            self.render()

    def _pointer_up(self, _event) -> None:
        if self.drag.mode in ("box-move", "box-resize", "window-move", "window-resize"):
            if self.drag.mode in ("window-move", "window-resize"):
                self.drag = DragState()
                # Capture after Tk has committed the final mouse geometry.
                self.root.after_idle(self._capture_and_save_window_layout)
                return
            self._schedule_layout_save()
        self.drag = DragState()

    def _capture_and_save_window_layout(self) -> None:
        self._sync_background_window()
        self._capture_window_geometry()
        self._save_layout()

    def _schedule_layout_save(self) -> None:
        if self._save_after_id:
            try:
                self.root.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._save_after_id = self.root.after(150, self._save_layout)

    def _save_layout(self) -> None:
        self._save_after_id = None
        try:
            # The dashboard can change AutoStart/style while this native window
            # is open. Merge only the geometry owned by this window into the
            # newest server layout, otherwise an old local snapshot resets the
            # checkbox or other settings on every drag.
            latest = _fetch_json(self.layout_url, timeout=1.0)
            if not isinstance(latest, dict):
                latest = {}
            for key in ("viewerBar", "spotifyPanel", "chatPanel", "alertPanel", "systemInfoPanel", "window"):
                if isinstance(self.layout.get(key), dict):
                    latest[key] = dict(self.layout[key])
            self.layout = latest
            _post_json(self.layout_url, latest)
        except Exception as exc:
            _log(f"layout speichern fehlgeschlagen: {exc}")

    def _rounded_rect(self, x: int, y: int, w: int, h: int, r: int, canvas=None, **kwargs) -> None:
        c = canvas or self.canvas
        r = max(0, min(int(r), int(w / 2), int(h / 2)))
        if r <= 0:
            c.create_rectangle(x, y, x + w, y + h, **kwargs)
            return
        points = [
            x + r,
            y,
            x + w - r,
            y,
            x + w - r,
            y,
            x + w,
            y,
            x + w,
            y + r,
            x + w,
            y + r,
            x + w,
            y + h - r,
            x + w,
            y + h - r,
            x + w,
            y + h,
            x + w - r,
            y + h,
            x + w - r,
            y + h,
            x + r,
            y + h,
            x + r,
            y + h,
            x,
            y + h,
            x,
            y + h - r,
            x,
            y + h - r,
            x,
            y + r,
            x,
            y + r,
            x,
            y,
            x + r,
            y,
        ]
        c.create_polygon(points, smooth=True, splinesteps=12, **kwargs)

    def _platform_image(self, platform: str, blocked: bool = False, size: int = 16):
        asset_key = "no_entry" if blocked else platform
        key = f"{asset_key}:{size}"
        if key in self._platform_images:
            return self._platform_images[key]
        try:
            root = _app_root()
            image = self.tk.PhotoImage(file=str(root / "assets" / "pics" / f"{asset_key}.png"))
            scale = max(1, (max(image.width(), image.height()) + size - 1) // size)
            image = image.subsample(scale, scale)
            self._platform_images[key] = image
            return image
        except Exception:
            self._platform_images[key] = None
            return None

    def _photo_from_image_bytes(self, data: bytes, size: int):
        try:
            from io import BytesIO
            from PIL import Image, ImageSequence, ImageTk
            pil = Image.open(BytesIO(data))
            is_animated = bool(getattr(pil, "is_animated", False)) and int(getattr(pil, "n_frames", 1) or 1) > 1
            if is_animated:
                frames = []
                durations = []
                for frame in ImageSequence.Iterator(pil):
                    frame_rgba = frame.convert('RGBA')
                    ratio = min(float(size) / max(1, frame_rgba.width), float(size) / max(1, frame_rgba.height))
                    target = (max(1, int(frame_rgba.width * ratio)), max(1, int(frame_rgba.height * ratio)))
                    frame_rgba = frame_rgba.resize(target, Image.Resampling.LANCZOS)
                    frames.append(ImageTk.PhotoImage(frame_rgba, master=self.root))
                    durations.append(max(40, min(1000, int(frame.info.get('duration') or pil.info.get('duration') or 100))))
                    if len(frames) >= 180:
                        break
                if frames:
                    return {
                        'frames': frames,
                        'durations': durations or [100] * len(frames),
                        'total_ms': max(40, sum(durations or [100] * len(frames))),
                        'started_at': time.monotonic(),
                    }
                raise ValueError('animated image has no frames')
            pil = pil.convert('RGBA')
            ratio = min(float(size) / max(1, pil.width), float(size) / max(1, pil.height))
            target = (max(1, int(pil.width * ratio)), max(1, int(pil.height * ratio)))
            pil = pil.resize(target, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(pil, master=self.root)
        except Exception:
            pass

        try:
            from PyQt6 import QtCore, QtGui
            image = QtGui.QImage()
            if not image.loadFromData(data):
                raise ValueError('Qt could not decode image')
            if not image.isNull():
                scaled = image.scaled(size, size, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                buffer = QtCore.QBuffer()
                buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                scaled.save(buffer, "PNG")
                encoded = base64.b64encode(bytes(buffer.data())).decode('ascii')
                return self.tk.PhotoImage(data=encoded)
        except Exception:
            pass

        try:
            from PySide6 import QtCore, QtGui
            image = QtGui.QImage()
            if not image.loadFromData(data):
                raise ValueError('Qt could not decode image')
            if not image.isNull():
                scaled = image.scaled(size, size, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                buffer = QtCore.QBuffer()
                buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                scaled.save(buffer, "PNG")
                encoded = base64.b64encode(bytes(buffer.data())).decode('ascii')
                return self.tk.PhotoImage(data=encoded)
        except Exception:
            pass

        encoded = base64.b64encode(data).decode('ascii')
        image = self.tk.PhotoImage(data=encoded)
        scale = max(1, (max(image.width(), image.height()) + size - 1) // size)
        return image.subsample(scale, scale) if scale > 1 else image

    def _chat_media_image(self, source: str, size: int = 24):
        source = str(source or '').strip()
        if not source:
            return None
        key = f"{source}:{size}"
        if key in self._chat_media_images:
            return self._chat_media_frame(self._chat_media_images[key])
        failed_at = self._chat_media_failures.get(key)
        if failed_at is not None and time.monotonic() - failed_at < 1.25:
            return None
        try:
            media_url = urllib.parse.urljoin(self.base_url + '/', source.lstrip('/'))
            req = urllib.request.Request(media_url, headers={'User-Agent': 'godisalotachat-desktop'})
            with urllib.request.urlopen(req, timeout=2.0) as response:
                data = response.read(20 * 1024 * 1024 + 1)
            if not data or len(data) > 20 * 1024 * 1024:
                raise ValueError('chat media is empty or too large')
            if data[:6] in {b'GIF87a', b'GIF89a'}:
                image = self._tk_gif_animation(base64.b64encode(data).decode('ascii'), size)
                self._chat_media_images[key] = image
                self._chat_media_failures.pop(key, None)
                return self._chat_media_frame(image)
            image = self._photo_from_image_bytes(data, size)
            self._chat_media_images[key] = image
            self._chat_media_failures.pop(key, None)
            return self._chat_media_frame(image)
        except Exception as exc:
            _log(f"Chat-Medium konnte nicht geladen werden: {source}: {exc}")
            self._chat_media_failures[key] = time.monotonic()
            self._schedule_chat_media_retry()
            return None

    def _tk_gif_animation(self, encoded_data: str, size: int = 24):
        frames = []
        index = 0
        while index < 180:
            try:
                frame = self.tk.PhotoImage(data=encoded_data, format=f'gif -index {index}')
            except Exception:
                break
            scale = max(1, (max(frame.width(), frame.height()) + size - 1) // size)
            if scale > 1:
                frame = frame.subsample(scale, scale)
            frames.append(frame)
            index += 1
        if len(frames) > 1:
            return {
                'frames': frames,
                'durations': [100] * len(frames),
                'total_ms': max(100, 100 * len(frames)),
                'started_at': time.monotonic(),
            }
        if frames:
            return frames[0]
        raise ValueError('gif chat media has no readable frames')

    def _chat_media_frame(self, image: Any):
        if not isinstance(image, dict):
            return image
        frames = image.get('frames') if isinstance(image.get('frames'), list) else []
        if not frames:
            return None
        durations = image.get('durations') if isinstance(image.get('durations'), list) else []
        total_ms = max(40, int(image.get('total_ms') or sum(durations or [100] * len(frames)) or 100))
        elapsed_ms = int((time.monotonic() - float(image.get('started_at') or time.monotonic())) * 1000) % total_ms
        acc = 0
        index = 0
        for i, duration in enumerate(durations or [100] * len(frames)):
            acc += max(40, int(duration or 100))
            if elapsed_ms < acc:
                index = min(i, len(frames) - 1)
                break
        self._schedule_chat_media_animation()
        return frames[index]

    def _schedule_chat_media_animation(self) -> None:
        if self._chat_media_animation_scheduled:
            return
        self._chat_media_animation_scheduled = True
        def tick() -> None:
            self._chat_media_animation_scheduled = False
            if any(isinstance(item, dict) for item in self._chat_media_images.values()):
                self.render()
        self.root.after(80, tick)

    def _schedule_chat_media_retry(self) -> None:
        if self._chat_media_retry_scheduled:
            return
        self._chat_media_retry_scheduled = True
        def retry() -> None:
            self._chat_media_retry_scheduled = False
            self.render()
        self.root.after(1400, retry)

    def _spotify_cover_image(self, cover_url: str, size: int):
        cover_url = str(cover_url or "").strip()
        local_candidates = [
            _app_root() / "data" / "spotis3mptify" / "covers" / "cover_latest_640.jpg",
            _app_root() / "data" / "spotis3mptify" / "covers" / "cover_latest_300.jpg",
            _app_root() / "data" / "spotis3mptify" / "covers" / "cover_latest_64.jpg",
        ]
        newest = None
        for path in local_candidates:
            try:
                if path.is_file() and path.stat().st_size > 0:
                    if newest is None or path.stat().st_mtime > newest.stat().st_mtime:
                        newest = path
            except Exception:
                pass
        local_matches_cover = not cover_url
        if newest is not None and cover_url:
            try:
                marker = newest.with_suffix(newest.suffix + ".src")
                local_matches_cover = marker.is_file() and marker.read_text(encoding="utf-8", errors="ignore").strip() == cover_url
            except Exception:
                local_matches_cover = False
        if newest is not None and local_matches_cover:
            key = f"spotify-cover-file:{newest}:{newest.stat().st_mtime}:{size}"
            if key in self._chat_media_images:
                return self._chat_media_frame(self._chat_media_images[key])
            try:
                image = self._photo_from_image_bytes(newest.read_bytes(), size)
                self._chat_media_images[key] = image
                return self._chat_media_frame(image)
            except Exception as exc:
                _log(f"Spotify-Coverdatei konnte nicht geladen werden: {newest}: {exc}")
        return self._chat_media_image(cover_url, size=size) if cover_url else None

    @staticmethod
    def _is_emoji_char(char: str) -> bool:
        if not char:
            return False
        cp = ord(char)
        return (
            0x1F000 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x27BF
            or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF
            or cp in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x20E3}
        )

    def _inline_runs(self, html_value: str | None, fallback: str = "") -> list[tuple[str, str]]:
        source = str(html_value or "")
        parts: list[tuple[str, str]] = []
        if source:
            cursor = 0
            for match in re.finditer(r'<img\b[^>]*>', source, flags=re.I):
                if match.start() > cursor:
                    parts.append(('text', _strip_html(source[cursor:match.start()])))
                tag = match.group(0)
                src_match = re.search(r'\bsrc=["\']([^"\']+)', tag, flags=re.I)
                if src_match:
                    parts.append(('image', html.unescape(src_match.group(1))))
                cursor = match.end()
            if cursor < len(source):
                parts.append(('text', _strip_html(source[cursor:])))
        if not parts:
            parts = [('text', str(fallback or ''))]

        expanded: list[tuple[str, str]] = []
        for kind, value in parts:
            if kind != 'text':
                expanded.append((kind, value))
                continue
            shortcode_emoji = {
                'heart': '\u2764\ufe0f', 'fire': '\U0001f525', 'congrat': '\U0001f389',
                'thumb': '\U0001f44d', 'thumbup': '\U0001f44d', 'like': '\U0001f44d',
                'smile': '\U0001f60a', 'happy': '\U0001f604', 'angry': '\U0001f620',
                'cry': '\U0001f622', 'surprised': '\U0001f632', 'flushed': '\U0001f633',
                'laugh': '\U0001f602', 'laughwithtears': '\U0001f602', 'thinking': '\U0001f914',
                'lovely': '\U0001f970', 'wow': '\U0001f92f', 'cool': '\U0001f60e',
                'excited': '\U0001f929', 'proud': '\U0001f60c', 'angel': '\U0001f607',
                'loveface': '\U0001f60d', 'awkward': '\U0001f605', 'shock': '\U0001f631',
                'tears': '\U0001f62d', 'weep': '\U0001f62d', 'rage': '\U0001f621',
                'cute': '\U0001f97a', 'blink': '\U0001f609', 'evil': '\U0001f608',
            }
            value = re.sub(
                r'\[([A-Za-z0-9_]+)\]',
                lambda match: shortcode_emoji.get(match.group(1).lower(), match.group(0)),
                value,
            )
            buffer = ''
            index = 0
            while index < len(value):
                char = value[index]
                if not self._is_emoji_char(char):
                    buffer += char
                    index += 1
                    continue
                if buffer:
                    expanded.append(('text', buffer))
                    buffer = ''
                sequence = char
                index += 1
                # Country flags are pairs of regional-indicator characters.
                # Rendering each half separately produces the empty boxes seen
                # in the native desktop chat.
                first_cp = ord(char)
                if 0x1F1E6 <= first_cp <= 0x1F1FF and index < len(value) and 0x1F1E6 <= ord(value[index]) <= 0x1F1FF:
                    sequence += value[index]
                    index += 1
                while index < len(value):
                    cp = ord(value[index])
                    if cp in {0xFE0E, 0xFE0F, 0x200D, 0x20E3} or 0x1F3FB <= cp <= 0x1F3FF or (sequence.endswith('\u200d') and self._is_emoji_char(value[index])):
                        sequence += value[index]
                        index += 1
                    else:
                        break
                expanded.append(('emoji', sequence))
            if buffer:
                expanded.append(('text', buffer))
        return [(kind, value) for kind, value in expanded if value]

    def _emoji_image(self, emoji_text: str, size: int = 24):
        key = f"emoji:{emoji_text}:{size}"
        if key in self._chat_media_images:
            return self._chat_media_images[key]
        # Tk cannot display color fonts. Twemoji gives deterministic full-color
        # glyphs; keep the local Windows color font as an offline fallback.
        codepoints = '-'.join(f'{ord(char):x}' for char in emoji_text if ord(char) != 0xFE0F)
        if codepoints:
            twemoji = f'https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/{codepoints}.png'
            image = self._chat_media_image(twemoji, size=size)
            if image:
                self._chat_media_images[key] = image
                return image
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            font_path = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'seguiemj.ttf'
            font = ImageFont.truetype(str(font_path), max(16, int(size * .9)))
            image = Image.new('RGBA', (size * 3, size * 2), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.text((2, 0), emoji_text, font=font, embedded_color=True)
            bbox = image.getbbox()
            if bbox:
                image = image.crop(bbox)
            ratio = min(float(size) / max(1, image.width), float(size) / max(1, image.height))
            image = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image, master=self.root)
            self._chat_media_images[key] = photo
            return photo
        except Exception as exc:
            _log(f"Farbiges Emoji konnte nicht gerendert werden: {emoji_text}: {exc}")
            self._chat_media_failures[key] = time.monotonic()
            self._schedule_chat_media_retry()
            return None

    def _draw_inline_runs(self, runs: list[tuple[str, str]], x: int, center_y: float, font: Any, color: str, right: int, size: int) -> None:
        px = x
        for kind, value in runs:
            if px >= right:
                break
            if kind == 'text':
                # Runs have already been pixel-wrapped by _wrap_inline_runs.
                # Calling _wrap_text_px again stripped every whitespace-only
                # run and glued neighbouring words together.
                self.canvas.create_text(px, center_y, text=value, fill=color, font=font, anchor='w')
                px += font.measure(value)
            else:
                image = self._chat_media_image(value, size=size) if kind == 'image' else self._emoji_image(value, size=size)
                if image:
                    self.canvas.create_image(px + int(image.width() / 2), center_y, image=image, anchor='center')
                    px += image.width() + 3
                else:
                    if kind == 'emoji':
                        self.canvas.create_text(px, center_y, text=value, fill=color, font=font, anchor='w')
                        px += font.measure(value)
                    else:
                        # Keep the slot empty until the scheduled retry succeeds;
                        # never flash a misleading square for image emotes.
                        px += size + 3

    def _inline_runs_width(self, runs: list[tuple[str, str]], font: Any, size: int) -> int:
        width = 0
        for kind, value in runs:
            if kind == 'text':
                width += font.measure(value)
            else:
                image = self._chat_media_image(value, size=size) if kind == 'image' else self._emoji_image(value, size=size)
                width += (image.width() + 3) if image else font.measure(value)
        return width

    def _chat_badge_urls(self, msg: dict[str, Any]) -> list[str]:
        badges = msg.get("badges") if isinstance(msg, dict) else None
        if not isinstance(badges, list):
            return []
        urls: list[str] = []
        for badge in badges[:12]:
            if not isinstance(badge, dict):
                continue
            url = str(badge.get("url") or "").strip()
            if url:
                urls.append(url)
        return urls

    def _chat_badges_width(self, urls: list[str], size: int) -> int:
        width = 0
        for url in urls:
            image = self._chat_media_image(url, size=size)
            if image:
                width += image.width() + 4
        return width

    def _draw_chat_badges(self, urls: list[str], x: int, center_y: float, size: int, right: int) -> int:
        px = x
        for url in urls:
            if px >= right:
                break
            image = self._chat_media_image(url, size=size)
            if image:
                self.canvas.create_image(px + int(image.width() / 2), center_y, image=image, anchor="center")
                px += image.width() + 4
            else:
                # Badge images are optional; keep chat readable while the image
                # cache retries in the background.
                px += 0
        return max(0, px - x)

    def _wrap_inline_runs(self, runs: list[tuple[str, str]], font: Any, first_px: int, next_px: int, size: int, max_lines: int = 6) -> list[list[tuple[str, str]]]:
        lines: list[list[tuple[str, str]]] = [[]]
        used = 0
        limit = max(20, first_px)
        for kind, value in runs:
            units = [('text', part) for part in re.split(r'(\s+)', value) if part] if kind == 'text' else [(kind, value)]
            for unit_kind, unit_value in units:
                if unit_kind == 'text':
                    unit_width = font.measure(unit_value)
                else:
                    image = self._chat_media_image(unit_value, size=size) if unit_kind == 'image' else self._emoji_image(unit_value, size=size)
                    unit_width = (image.width() + 3) if image else size
                if used and used + unit_width > limit and not unit_value.isspace():
                    if len(lines) >= max_lines:
                        return lines
                    lines.append([])
                    used = 0
                    limit = max(20, next_px)
                if unit_kind == 'text' and unit_width > limit and not unit_value.isspace():
                    pieces = self._split_token_to_width(unit_value, font, limit)
                    for piece_index, piece in enumerate(pieces):
                        if piece_index and len(lines) < max_lines:
                            lines.append([])
                            used = 0
                            limit = max(20, next_px)
                        lines[-1].append(('text', piece))
                        used += font.measure(piece)
                    continue
                if not (not lines[-1] and unit_value.isspace()):
                    lines[-1].append((unit_kind, unit_value))
                    used += unit_width
        return [line for line in lines if line] or [[('text', '')]]

    def _draw_platform_badge(self, x: int, y: int, platform: str, text: str | None = None, blocked: bool = False, size: int = 21) -> int:
        icon = PLATFORM_ICONS.get(platform, "•")
        image = self._platform_image(platform, blocked, size=size)
        if image:
            self.canvas.create_image(x + int((size + 1) / 2), y + 12, image=image, anchor="center")
        else:
            self.canvas.create_text(x + int((size + 1) / 2), y + 12, text=icon, fill="#ffffff", font=("Segoe UI", 12, "bold"))
        return size + 1

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        text = text.replace("\r", "").strip()
        if not text:
            return [""]
        lines: list[str] = []
        for raw in text.split("\n"):
            words = raw.split(" ")
            cur = ""
            for word in words:
                candidate = word if not cur else cur + " " + word
                if len(candidate) <= max_chars:
                    cur = candidate
                else:
                    if cur:
                        lines.append(cur)
                    while len(word) > max_chars:
                        lines.append(word[:max_chars])
                        word = word[max_chars:]
                    cur = word
            if cur:
                lines.append(cur)
        return lines[-3:] if len(lines) > 3 else lines

    def _split_token_to_width(self, token: str, font: Any, max_px: int) -> list[str]:
        max_px = max(12, int(max_px))
        if not token:
            return [""]
        parts: list[str] = []
        cur = ""
        for char in token:
            candidate = cur + char
            if not cur or font.measure(candidate) <= max_px:
                cur = candidate
            else:
                parts.append(cur)
                cur = char
        if cur:
            parts.append(cur)
        return parts or [token]

    def _wrap_text_px(self, text: str, font: Any, first_px: int, next_px: int, *, max_lines: int = 12) -> list[str]:
        """Wrap text by real Tk font pixels, not guessed character counts.

        The desktop overlay can be resized with the mouse. Tk's canvas text does
        not know about our dashed edit border or resize handle, so we pre-wrap
        against the current element width. Normal words stay whole and wrap at
        spaces. Only single tokens that are wider than the available line are
        split as a last-resort overflow guard.
        """
        text = str(text or "").replace("\r", "").strip()
        if not text:
            return [""]

        first_px = max(20, int(first_px))
        next_px = max(20, int(next_px))
        lines: list[str] = []
        limit = first_px

        for raw in text.split("\n"):
            words = [w for w in raw.split(" ") if w != ""]
            cur = ""
            for word in words:
                candidate = word if not cur else cur + " " + word
                if font.measure(candidate) <= limit:
                    cur = candidate
                    continue

                if cur:
                    lines.append(cur)
                    if len(lines) >= max_lines:
                        return lines[:max_lines]
                    cur = ""
                    limit = next_px

                if font.measure(word) <= limit:
                    cur = word
                    continue

                pieces = self._split_token_to_width(word, font, limit)
                for piece in pieces[:-1]:
                    lines.append(piece)
                    if len(lines) >= max_lines:
                        return lines[:max_lines]
                    limit = next_px
                cur = pieces[-1]
                limit = next_px

            if cur:
                lines.append(cur)
                if len(lines) >= max_lines:
                    return lines[:max_lines]
                limit = next_px

        return lines or [""]

    def _is_fresh_alert_item(self, item: dict[str, Any], max_age_seconds: float = 900.0) -> bool:
        try:
            ts = float(item.get("created_at") or 0.0)
        except Exception:
            ts = 0.0
        if ts <= 0:
            try:
                raw_id = float(item.get("id") or 0.0)
                if raw_id > 1_000_000_000_000:
                    ts = raw_id / 1000.0
            except Exception:
                ts = 0.0
        return ts <= 0 or (time.time() - ts) <= max_age_seconds

    def render(self) -> None:
        c = self.canvas
        bgc = self.bg_canvas
        c.delete("all")
        bgc.delete("all")
        style = self.layout.get("style") or {}
        bg = _safe_draw_color(style.get("background"))
        bg_stipple = None
        try:
            # Nur das Hintergrundfenster bekommt Alpha. Das Vorderfenster mit
            # Text/Symbolen bleibt voll deckend. Alpha nur setzen, wenn es sich aendert.
            alpha = _opacity_to_window_alpha(style.get("opacity", 82))
            if self._last_bg_alpha != alpha:
                self.root.attributes("-alpha", 1.0)
                self.bg_root.attributes("-alpha", alpha)
                self._last_bg_alpha = alpha
        except Exception:
            pass
        radius = int(style.get("radius", 16) or 16)
        font_family = str(style.get("fontFamily") or "Segoe UI")
        font_size = int(style.get("fontSize") or 16)
        text_color = str(style.get("textColor") or "#ffffff")

        # Im Editmode braucht das komplette Fenster eine nicht-transparente
        # Trefferflaeche, sonst klickt Windows durch transparente Pixel durch.
        # Sehr dunkler Hilfshintergrund, nur waehrend Bearbeitung sichtbar.
        if self.editing:
            c.create_rectangle(0, 0, self.root.winfo_width(), self.root.winfo_height(), fill="#020304", outline="")

        if self.editing or bool((self.layout.get("viewers") or {}).get("enabled", True)):
            self._draw_viewer_bar(bg, bg_stipple, radius, font_family, text_color)
        self._draw_chat_panel(bg, bg_stipple, radius, font_family, font_size, text_color)
        self._draw_alert_panel(bg, bg_stipple, radius, font_family, font_size, text_color)
        self._draw_system_info_panel(bg, radius, font_family, font_size)
        if self.editing or bool((self.layout.get("spotify") or {}).get("enabled", False)):
            self._draw_spotify_panel(bg, bg_stipple, radius, font_family, font_size, text_color)

        if not self.last_chat_state and self.editing:
            c.create_text(18, 18, anchor="nw", text=("Desktop overlay active · F8 toggles edit mode" if self.language == "en" else "Desktop-Overlay aktiv · F8 schaltet den Bearbeitungsmodus um"), fill="#b9c2e2", font=(font_family, 10))

        if self.editing:
            w, h = self.root.winfo_width(), self.root.winfo_height()
            c.create_text(
                12,
                h - 18,
                anchor="w",
                text=("Move elements with the mouse. Resize at the bottom right. ESC finishes editing." if self.language == "en" else "Elemente mit der Maus verschieben. Unten rechts skalieren. ESC beendet die Bearbeitung."),
                fill="#b9c2e2",
                font=("Segoe UI", 10),
            )
            c.create_polygon(w, h - 34, w, h, w - 34, h, fill="#936cff", outline="")

        # Click-through nicht in jedem Render neu setzen; das verursacht bei transparenten
        # Fenstern sichtbar Flicker. Nur Moduswechsel erzwingen den Style neu.

    def _draw_viewer_bar(self, bg: str, bg_stipple: str | None, radius: int, font_family: str, text_color: str) -> None:
        box = self.layout.get("viewerBar") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        self._rounded_rect(x, y, w, h, radius, fill=bg, outline="", stipple=bg_stipple, canvas=self.bg_canvas)
        px = x + 12
        py = y + max(8, int((h - 28) / 2))
        platforms = self.last_chat_state.get("platforms", []) if isinstance(self.last_chat_state, dict) else []
        if not platforms and self.editing:
            platforms = [{"platform":"twitch","viewer_count":"-"},{"platform":"tiktok","viewer_count":"-"},{"platform":"youtube","viewer_count":"-"},{"platform":"kick","viewer_count":"-"}]
        for item in platforms or []:
            platform = str(item.get("platform") or "")
            blocked = bool(item.get("blocked"))
            raw_count = item.get("viewer_count", "-")
            missing_count = raw_count is None or str(raw_count).strip().lower() in ("", "none", "null", "-")
            bw = self._draw_platform_badge(px, py, platform, size=27)
            if blocked:
                status_icon = self._platform_image("no_entry", True, size=27)
                if status_icon:
                    self.canvas.create_image(px + bw + 20, py + 12, image=status_icon, anchor="center")
                else:
                    self.canvas.create_text(px + bw + 12, py + 12, text="⛔", fill="#ff4b60", font=(font_family, 10, "bold"), anchor="w")
            elif missing_count:
                self.canvas.create_text(px + bw + 12, py + 12, text="LIVE", fill=text_color, font=(font_family, 9, "bold"), anchor="w")
            else:
                self.canvas.create_text(px + bw + 12, py + 12, text=str(raw_count), fill=text_color, font=(font_family, 10, "bold"), anchor="w")
            px += bw + 44
        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")

    def _draw_spotify_panel(self, bg: str, bg_stipple: str | None, radius: int, font_family: str, font_size: int, text_color: str) -> None:
        cfg = self.layout.get("spotify") if isinstance(self.layout.get("spotify"), dict) else {}
        enabled = bool(cfg.get("enabled", False))
        if not enabled and not self.editing:
            return
        box = self.layout.get("spotifyPanel") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        self._rounded_rect(x, y, w, h, radius, fill=bg, outline="", stipple=bg_stipple, canvas=self.bg_canvas)

        nowplaying = self.last_nowplaying if isinstance(self.last_nowplaying, dict) else {}
        title = str(nowplaying.get("title") or ("Kein Song aktiv" if self.language != "en" else "No song active"))
        artist = str(nowplaying.get("artist") or nowplaying.get("album") or "")
        cover = str(nowplaying.get("cover") or "").strip()
        if self.editing and not enabled:
            title = "Spotify"
            artist = "Im Chat-Reiter aktivieren" if self.language != "en" else "Enable in the chat tab"

        pad = 12
        cover_size = max(34, min(64, h - 20))
        px = x + pad
        center_y = y + h / 2
        image = self._spotify_cover_image(cover, cover_size) if (cover or enabled or self.editing) else None
        if image:
            self.canvas.create_image(px + int(image.width() / 2), center_y, image=image, anchor="center")
            px += image.width() + 12
        else:
            self._rounded_rect(px, int(center_y - cover_size / 2), cover_size, cover_size, 8, fill="#172033", outline="", canvas=self.canvas)
            self.canvas.create_text(px + cover_size / 2, center_y, text="SP", fill="#1ed760", font=(font_family, max(9, int(font_size * .72)), "bold"), anchor="center")
            px += cover_size + 12

        right = x + w - (36 if self.editing else 14)
        label_font = self.tkfont.Font(family=font_family, size=max(8, int(font_size * .72)), weight="bold")
        title_font = self.tkfont.Font(family=font_family, size=max(10, font_size + 1), weight="bold")
        artist_font = self.tkfont.Font(family=font_family, size=max(8, font_size - 2))
        self.canvas.create_text(px, y + 17, text="SPOTIFY", fill="#1ed760", font=label_font, anchor="w")
        available = max(20, right - px)
        safe_title = self._wrap_text_px(title, title_font, available, available, max_lines=1)[0]
        safe_artist = self._wrap_text_px(artist, artist_font, available, available, max_lines=1)[0] if artist else ""
        self.canvas.create_text(px, y + max(36, int(h * .48)), text=safe_title, fill=text_color, font=title_font, anchor="w")
        if safe_artist:
            self.canvas.create_text(px, min(y + h - 14, y + max(54, int(h * .72))), text=safe_artist, fill="#b9c2e2", font=artist_font, anchor="w")

        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")

    def _draw_chat_panel(self, bg: str, bg_stipple: str | None, radius: int, font_family: str, font_size: int, text_color: str) -> None:
        box = self.layout.get("chatPanel") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        self._rounded_rect(x, y, w, h, radius, fill=bg, outline="", stipple=bg_stipple, canvas=self.bg_canvas)
        messages = [
            m for m in (self.last_chat_state.get("messages", []) or [])
            if m.get("message_type") in {"chat", "moderation_notice"}
        ][-40:]
        # Die Badge ist 24px hoch. Mit mindestens 34px pro Zeile bleibt sichtbar
        # Luft zwischen den farbigen Bereichen, auch bei kleiner Schrift.
        line_h = max(34, int(font_size * 1.8))
        rows: list[tuple[str, str, str, str, list[str], list[tuple[str, str]] | None]] = []
        text_font = self.tkfont.Font(family=font_family, size=font_size)
        name_font = self.tkfont.Font(family=font_family, size=font_size, weight="bold")
        left_pad = 12
        right_pad = 36 if self.editing else 18
        continuation_x = x + left_pad + 70
        panel_right = x + w - right_pad
        for msg in messages:
            platform = str(msg.get("platform") or "")
            user = str(msg.get("user") or "?")
            badge_urls = self._chat_badge_urls(msg)
            chat_badge_size = max(11, int(font_size * .95))
            chat_badges_w = self._chat_badges_width(badge_urls, chat_badge_size)
            text = _strip_html(msg.get("html")) or str(msg.get("text") or "")
            inline_runs = self._inline_runs(msg.get("html"), str(msg.get("text") or ""))
            has_visual_runs = any(kind in {'image', 'emoji'} for kind, _value in inline_runs)
            badge_w = 22
            first_text_x = x + left_pad + badge_w + 8 + chat_badges_w + name_font.measure(user) + 10
            first_line_width = max(40, panel_right - first_text_x)
            next_line_width = max(40, panel_right - continuation_x)
            if has_visual_runs:
                visual_size = max(34, int(font_size * 2.26))
                wrapped_runs = self._wrap_inline_runs(inline_runs, text_font, first_line_width, next_line_width, visual_size, max_lines=6)
                for i, line_runs in enumerate(wrapped_runs):
                    rows.append((platform if i == 0 else "", user if i == 0 else "", "", platform, badge_urls if i == 0 else [], line_runs))
            else:
                wrapped = self._wrap_text_px(text, text_font, first_line_width, next_line_width, max_lines=6)
                for i, line in enumerate(wrapped):
                    rows.append((platform if i == 0 else "", user if i == 0 else "", line, platform, badge_urls if i == 0 else [], None))
        max_rows = max(1, int((h - 24) / line_h))
        rows = rows[-max_rows:]
        cy = y + h - 12 - len(rows) * line_h
        for platform, user, line, color_platform, badge_urls, inline_runs in rows:
            px = x + left_pad
            if platform:
                badge_y = cy + int((line_h - 24) / 2)
                bw = self._draw_platform_badge(px, badge_y, platform)
                px += bw + 8
                chat_badge_size = max(11, int(font_size * .95))
                px += self._draw_chat_badges(badge_urls, px, cy + line_h / 2, chat_badge_size, panel_right)
                user_runs = self._inline_runs(None, user)
                user_size = max(22, int(font_size * 1.35))
                self._draw_inline_runs(user_runs, px, cy + line_h / 2, name_font, _user_color(platform, user), panel_right, user_size)
                px += self._inline_runs_width(user_runs, name_font, user_size) + 10
            else:
                px = continuation_x
            available = max(20, panel_right - px)
            if inline_runs:
                self._draw_inline_runs(inline_runs, px, cy + line_h / 2, text_font, text_color, panel_right, max(34, int(font_size * 2.26)))
            else:
                safe_line = self._wrap_text_px(line, text_font, available, available, max_lines=1)[0]
                self.canvas.create_text(px, cy + line_h / 2, text=safe_line, fill=text_color, font=text_font, anchor="w")
            cy += line_h
        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")

    def _draw_system_info_panel(self, bg: str, radius: int, font_family: str, font_size: int) -> None:
        cfg = self.layout.get("systemInfo") if isinstance(self.layout.get("systemInfo"), dict) else {}
        info = self.last_chat_state.get("system_info", {}) if isinstance(self.last_chat_state, dict) else {}
        active = bool(info.get("active"))
        if (not bool(cfg.get("enabled", True)) or not active) and not self.editing:
            return
        box = self.layout.get("systemInfoPanel") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        fill = "#781f32" if active else bg
        self._rounded_rect(x, y, w, h, radius, fill=fill, outline="#ff8ba1" if active else "", canvas=self.bg_canvas)
        title = info.get("title_en" if self.language == "en" else "title_de") if active else ("System information" if self.language == "en" else "Systeminfo")
        text = info.get("text_en" if self.language == "en" else "text_de") if active else ("Only visible during a system error." if self.language == "en" else "Nur bei einem Systemfehler sichtbar.")
        title_font = self.tkfont.Font(family=font_family, size=max(12, int(font_size * 1.1)), weight="bold")
        text_font = self.tkfont.Font(family=font_family, size=max(10, int(font_size * .9)))
        text_width = max(80, w - 32)
        self.canvas.create_text(x + 16, y + 14, text=str(title or ""), fill="#ffffff", font=title_font, anchor="nw", width=text_width)
        self.canvas.create_text(x + 16, y + 50, text=str(text or ""), fill="#ffe4e9" if active else "#aeb8dc", font=text_font, anchor="nw", width=text_width)
        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")

    def _draw_alert_panel(self, bg: str, bg_stipple: str | None, radius: int, font_family: str, font_size: int, text_color: str) -> None:
        cfg = self.layout.get("alerts") if isinstance(self.layout.get("alerts"), dict) else {}
        if not bool(cfg.get("enabled", True)) and not self.editing:
            return
        box = self.layout.get("alertPanel") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        self._rounded_rect(x, y, w, h, radius, fill=bg, outline="", stipple=bg_stipple, canvas=self.bg_canvas)
        platforms = cfg.get("platforms") if isinstance(cfg.get("platforms"), dict) else {}
        alerts = [
            item for item in (self.last_chat_state.get("messages", []) or [])
            if item.get("message_type") == "alert" and self._is_fresh_alert_item(item) and bool(platforms.get(str(item.get("platform") or "").lower(), True))
        ][-max(1, min(20, int(cfg.get("maxItems", 5) or 5))):]
        title_font = self.tkfont.Font(family=font_family, size=max(10, int(font_size * .9)), weight="bold")
        text_font = self.tkfont.Font(family=font_family, size=max(10, int(font_size * .9)))
        self.canvas.create_text(x + 12, y + 12, text="ALERTS", fill="#b9c2e2", font=title_font, anchor="w")
        if not alerts:
            if self.editing:
                self.canvas.create_text(x + 12, y + 36, text=("New live events appear here." if self.language == "en" else "Neue Live-Ereignisse erscheinen hier."), fill="#8f9abe", font=text_font, anchor="w")
        else:
            line_h = max(32, int(font_size * 1.7))
            rows = alerts[-max(1, int((h - 28) / line_h)):]
            cy = y + h - 10 - len(rows) * line_h
            for item in rows:
                platform = str(item.get("platform") or "")
                px = x + 12 + self._draw_platform_badge(x + 12, cy + int((line_h - 24) / 2), platform) + 8
                user = str(item.get("user") or "Unbekannt")
                media_source = str(item.get("gift_image_url") or "").strip()
                media_image = self._chat_media_image(media_source, size=max(34, int(font_size * 2.34))) if media_source else None
                if media_image:
                    # The native canvas draws the actual image, so do not retain
                    # the HTML <img alt> fallback (which previously became "Heart").
                    html_without_images = re.sub(r"<img\b[^>]*>", "", str(item.get("html") or ""), flags=re.I)
                    line = _strip_html(html_without_images) or str(item.get("text") or item.get("alert_title") or "Alert")
                else:
                    line = _strip_html(item.get("html")) or str(item.get("text") or item.get("alert_title") or "Alert")
                # Das Event kommt bereits mit einem User-Feld. Einen gleichlautenden
                # Präfix aus alten Templates entfernen, damit der Name nicht doppelt
                # erscheint und jede Meldung wirklich nur eine Zeile bleibt.
                line = re.sub(r"^\s*" + re.escape(user) + r"\s*[:·,\-–—]*\s*", "", line, flags=re.IGNORECASE)
                prefix = (str(item.get("time") or "") + "  ") if bool(cfg.get("showTimestamp", True)) else ""
                if prefix:
                    self.canvas.create_text(px, cy + line_h / 2, text=prefix, fill="#8f9abe", font=text_font, anchor="w")
                    px += text_font.measure(prefix)
                user_runs = self._inline_runs(None, user)
                user_size = max(20, int(font_size * 1.25))
                self._draw_inline_runs(user_runs, px, cy + line_h / 2, title_font, _user_color(platform, user), x + w - 18, user_size)
                px += self._inline_runs_width(user_runs, title_font, user_size) + 8
                panel_right = x + w - (36 if self.editing else 18)
                if media_image:
                    count = item.get("gift_count") if item.get("gift_count") is not None else item.get("amount")
                    try:
                        count_text = str(max(1, int(count or 1)))
                    except Exception:
                        count_text = "1"
                    gift_name = str(item.get("gift_name") or "Gift").strip() or "Gift"
                    if self.language == "en":
                        gift_prefix = " sent "
                        gift_suffix = f" {gift_name} x {count_text}"
                    else:
                        gift_prefix = " hat "
                        gift_suffix = f" {gift_name} x {count_text} gesendet"
                    self.canvas.create_text(px, cy + line_h / 2, text=gift_prefix, fill=text_color, font=text_font, anchor="w")
                    px += text_font.measure(gift_prefix)
                    self.canvas.create_image(px + int(media_image.width() / 2), cy + line_h / 2, image=media_image, anchor="center")
                    px += media_image.width() + 7
                    available = max(20, panel_right - px)
                    safe_suffix = self._wrap_text_px(gift_suffix, text_font, available, available, max_lines=1)[0]
                    self.canvas.create_text(px, cy + line_h / 2, text=safe_suffix, fill=text_color, font=text_font, anchor="w")
                    cy += line_h
                    continue
                if str(item.get("event_type") or "").lower() == "like":
                    heart_font = self.tkfont.Font(family="Arial", size=max(12, int(font_size * 1.15)), weight="bold")
                    like_count = item.get("amount")
                    try:
                        like_count_text = str(max(1, int(like_count or 1)))
                    except Exception:
                        like_count_text = "1"
                    like_prefix = " sent " if self.language == "en" else " hat "
                    self.canvas.create_text(px, cy + line_h / 2, text=like_prefix, fill=text_color, font=text_font, anchor="w")
                    px += text_font.measure(like_prefix)
                    self.canvas.create_text(px, cy + line_h / 2, text="♥", fill="#ff2d55", font=heart_font, anchor="w")
                    px += heart_font.measure("♥") + 6
                    like_label = "Like" if like_count_text == "1" else "Likes"
                    like_suffix = f" {like_label} x {like_count_text}" if self.language == "en" else f" {like_label} x {like_count_text} gesendet"
                    available = max(20, panel_right - px)
                    safe_like_suffix = self._wrap_text_px(like_suffix, text_font, available, available, max_lines=1)[0]
                    self.canvas.create_text(px, cy + line_h / 2, text=safe_like_suffix, fill=text_color, font=text_font, anchor="w")
                    cy += line_h
                    continue
                available = max(20, panel_right - px)
                safe_line = self._wrap_text_px(line, text_font, available, available, max_lines=1)[0]
                self.canvas.create_text(px, cy + line_h / 2, text=safe_line, fill=text_color, font=text_font, anchor="w")
                cy += line_h
        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")


def run_desktop_chat(url: str) -> int:
    if os.name != "nt":
        _message_box("Das Desktop-Overlay ist aktuell nur fuer Windows gebaut.")
        return 1
    try:
        overlay = DesktopTkOverlay(url)
        return overlay.run()
    except Exception as exc:
        try:
            log_dir = Path(sys.executable).resolve().parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            import traceback
            (log_dir / "desktop_chat_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        _message_box(f"Desktopfenster konnte nicht gestartet werden:\n\n{exc}", WINDOW_TITLE)
        return 1
