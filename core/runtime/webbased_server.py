from __future__ import annotations
import base64, hashlib, json, mimetypes, os, re, secrets, socket, struct, sys, threading, time, urllib.parse, urllib.request, urllib.error, webbrowser, tempfile, subprocess, sqlite3, shutil, ctypes, importlib.util, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from shared.version import APP_VERSION

APP_NAME = "godisalotachat webbased"
VERSION = APP_VERSION

PLATFORM_ORDER = ["twitch", "tiktok", "youtube", "kick", "spotify", "openai", "meld", "obs"]
CHAT_INPUT_PLUGIN_IDS = {"twitch_chat", "tiktok_chat", "youtube_chat", "kick_chat"}
CALLBACK_PORT = 5173
MAIN_PORT = 17890
OPENAI_API_BASE = "https://api.openai.com/v1"

DEFAULT_SCOPES = {
    # Original-Logik: Bot bleibt Chat/Moderation, Main ist separat für Broadcast/Editor-Funktionen.
    "twitch": {
        "main": "chat:read chat:edit user:read:chat user:write:chat moderator:read:chatters moderator:manage:banned_users moderator:manage:chat_messages channel:manage:broadcast",
        "bot": "chat:read chat:edit user:read:chat user:write:chat moderator:read:chatters moderator:manage:banned_users moderator:manage:chat_messages channel:manage:broadcast",
    },
    "youtube": {
        "main": "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.force-ssl https://www.googleapis.com/auth/youtube.readonly",
        "bot": "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.force-ssl https://www.googleapis.com/auth/youtube.readonly",
    },
    "kick": {"main": "user:read channel:read channel:write chat:write moderation:ban moderation:chat_message:manage", "bot": "user:read channel:read channel:write chat:write moderation:ban moderation:chat_message:manage"},
    "spotify": {"main": "user-modify-playback-state user-read-playback-state user-read-currently-playing playlist-modify-private playlist-modify-public playlist-read-private ugc-image-upload"},
}

DEFAULT_REDIRECTS = {
    "twitch": "http://localhost:17564/callback/",
    "youtube": "http://127.0.0.1:17566/callback/",
    "kick": "http://localhost:17865/kick/callback",
    "spotify": "http://127.0.0.1:5173/callback",
}

CALLBACK_PORTS = (5173, 17564, 17566, 17865)

AUTH_URLS = {
    "twitch": "https://id.twitch.tv/oauth2/authorize",
    "youtube": "https://accounts.google.com/o/oauth2/v2/auth",
    "kick": "https://id.kick.com/oauth/authorize",
    "spotify": "https://accounts.spotify.com/authorize",
}
TOKEN_URLS = {
    "twitch": "https://id.twitch.tv/oauth2/token",
    "youtube": "https://oauth2.googleapis.com/token",
    "kick": "https://id.kick.com/oauth/token",
    "spotify": "https://accounts.spotify.com/api/token",
}

def _now_ms():
    return int(time.time() * 1000)

def _json_load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _json_save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

def _desktop_dir() -> Path:
    home = Path.home()
    candidates = [home / "Desktop", home / "OneDrive" / "Desktop"]
    for path in candidates:
        try:
            if path.exists():
                return path
        except Exception:
            pass
    return home

def _open_text_file(path: Path) -> None:
    try:
        if os.name == "nt":
            subprocess.Popen(["notepad.exe", str(path)], creationflags=_win_hidden_flags())
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _find_free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start



class WebbasedPluginHost:
    def __init__(self, state):
        self.state = state

    def platform_settings(self, platform: str) -> dict:
        """Return normalized central platform configuration for plugins.

        Host is the single source for OAuth/account/token data. Plugins should
        not keep their own OAuth copies and should only keep plugin-specific
        behavior settings.
        """
        try:
            platform = str(platform or "").strip().lower()
            settings = self.state.settings()

            # Some bridge-style plugins need the complete platform map, while
            # older plugins ask for one platform at a time. Support both. This
            # is important for bridg3alot: without the full map it marks every
            # target as inactive/non-writable and silently skips bridging.
            if not platform:
                out = {}
                for name in PLATFORM_ORDER:
                    try:
                        out[name] = self.platform_settings(name)
                    except Exception:
                        out[name] = dict(settings.get("platforms", {}).get(name, {}) or {})
                return out

            cfg = dict(settings.get("platforms", {}).get(platform, {}) or {})

            def clean_account(value):
                return str(value or "").strip().lstrip("@#").strip()

            if platform in ("twitch", "youtube", "kick"):
                main = clean_account(
                    cfg.get("main")
                    or cfg.get("main_account")
                    or cfg.get("channel")
                    or cfg.get("main_username")
                    or cfg.get("main_channel")
                    or cfg.get("main_channel_title")
                    or cfg.get("channel_slug")
                )
                bot = clean_account(
                    cfg.get("bot")
                    or cfg.get("bot_account")
                    or cfg.get("bot_username")
                    or cfg.get("username")
                    or cfg.get("bot_channel")
                    or cfg.get("bot_channel_title")
                )
                if main:
                    cfg["main"] = main
                    cfg["main_account"] = main
                    cfg["channel"] = main
                else:
                    cfg.setdefault("main", "")
                    cfg.setdefault("main_account", "")
                    cfg.setdefault("channel", "")
                if bot:
                    cfg["bot"] = bot
                    cfg["bot_account"] = bot
                    cfg["bot_username"] = bot
                    cfg["username"] = bot
                else:
                    cfg.setdefault("bot", "")
                    cfg.setdefault("bot_account", "")
                    cfg.setdefault("bot_username", "")
                    cfg.setdefault("username", "")

            accounts = ("main",) if platform == "spotify" else ("main", "bot")
            for account in accounts:
                token = _json_load(self.state.auth_dir / f"{platform}_{account}.json", {})
                if not isinstance(token, dict):
                    continue
                prefix = "" if (platform == "spotify" or account == "bot") else "main_"
                for key in ("access_token", "refresh_token", "expires_in", "expires_at", "scope", "token_type", "saved_at"):
                    value = token.get(key)
                    if value not in (None, ""):
                        cfg[prefix + key] = value
                if token.get("access_token") and not token.get("expires_at"):
                    try:
                        saved_at = float(token.get("saved_at") or 0)
                        expires_in = float(token.get("expires_in") or 0)
                        if saved_at > 0 and expires_in > 0:
                            cfg[prefix + "expires_at"] = saved_at + expires_in
                    except Exception:
                        pass
                if account == "bot":
                    # Canonical bot token stays access_token/refresh_token.
                    # bot_* aliases only exist for legacy call sites.
                    if token.get("access_token"):
                        cfg["bot_access_token"] = token.get("access_token")
                    if token.get("refresh_token"):
                        cfg["bot_refresh_token"] = token.get("refresh_token")

            # YouTube keeps separate auth files for main and bot. The plugin now
            # consumes the same canonical shape as Twitch/Kick: main_* for the
            # broadcaster token and plain access_token/refresh_token for bot.
            if platform == "youtube":
                cfg.setdefault("redirect_port", 17566)
                cfg.setdefault("redirect_url", DEFAULT_REDIRECTS.get("youtube", ""))
                cfg.setdefault("redirect_uri", DEFAULT_REDIRECTS.get("youtube", ""))
                cfg.setdefault("main_scopes", DEFAULT_SCOPES.get("youtube", {}).get("main", ""))
                cfg.setdefault("scopes", DEFAULT_SCOPES.get("youtube", {}).get("bot", ""))
                if cfg.get("access_token") and not cfg.get("bot_access_token"):
                    cfg["bot_access_token"] = cfg.get("access_token")
                if cfg.get("refresh_token") and not cfg.get("bot_refresh_token"):
                    cfg["bot_refresh_token"] = cfg.get("refresh_token")
            if platform in ("twitch", "youtube", "kick"):
                try:
                    cfg = self.state.refresh_platform_oauth(platform, cfg)
                except Exception as exc:
                    try:
                        self.state.log(platform, "oauth refresh from platform settings failed", exc)
                    except Exception:
                        pass
            return cfg
        except Exception:
            return {}

    def get_platform_settings(self, platform: str = "") -> dict:
        return self.platform_settings(platform)

    def get_plugin(self, plugin_id: str):
        try:
            return self.state.plugin_instances.get(str(plugin_id))
        except Exception:
            return None

    def set_status(self, plugin_id: str, status) -> None:
        try:
            st = getattr(status, "state", None) or (status.get("state") if isinstance(status, dict) else None) or str(status)
            msg = getattr(status, "message", None) or (status.get("message") if isinstance(status, dict) else None) or ""
            self.state.plugin_status[str(plugin_id)] = {"state": str(st), "message": str(msg), "ts": time.time()}
            self.state.log(str(plugin_id), "status", st, msg)
        except Exception:
            pass

    def log(self, plugin_id: str, message: str) -> None:
        try:
            self.state.log(str(plugin_id), str(message))
        except Exception:
            pass

    def emit_message(self, plugin_id: str, payload: dict) -> None:
        try:
            payload = dict(payload or {})
            message_type = str(payload.get("message_type") or payload.get("type") or "").strip().lower()
            if payload.get("metric_only") or message_type in {"viewer_count", "followers_count", "metric", "stats", "live_status"}:
                self.emit_metric(plugin_id, payload)
                return
            text = str(payload.get("text") or payload.get("message") or payload.get("content") or "").strip()
            overlay_html = str(payload.get("overlay_html") or "")
            if not text and not overlay_html:
                return
            if self._is_suppressed_outbound_echo(payload, text):
                return
            item = {
                "id": _now_ms(),
                "platform": str(payload.get("platform") or plugin_id or "plugin"),
                "user": str(payload.get("username") or payload.get("display_name") or payload.get("user") or ""),
                "text": text,
                "html": overlay_html,
                "channel": str(payload.get("channel") or ""),
                "message_type": str(payload.get("message_type") or "chat"),
                "type": str(payload.get("type") or payload.get("message_type") or "chat"),
                "event_type": str(payload.get("event_type") or payload.get("type") or payload.get("message_type") or "chat"),
                "source_plugin_id": str(payload.get("source_plugin_id") or plugin_id),
                "source": str(payload.get("source") or payload.get("source_plugin_id") or plugin_id),
                "dispatch_to_plugins": bool(payload.get("dispatch_to_plugins") or payload.get("bridge_to_platforms")),
                "botalot_reply": bool(payload.get("botalot_reply")),
                "message_id": str(payload.get("message_id") or payload.get("id") or ""),
                "user_id": str(payload.get("user_id") or ""),
                "raw_tags": payload.get("raw_tags") if isinstance(payload.get("raw_tags"), dict) else {},
                "content": str(payload.get("content") or payload.get("message") or text),
                "live_chat_id": str(payload.get("live_chat_id") or payload.get("liveChatId") or ""),
                "author_channel_id": str(payload.get("author_channel_id") or payload.get("authorChannelId") or ""),
                "time": time.strftime("%H:%M:%S"),
            }

            # Safety net for realtime providers that can emit the same event via
            # multiple websocket channels. This prevents duplicate rows in the
            # tool's platform chats without blocking a user from repeating the
            # same message a few seconds later.
            recent = getattr(self.state, "_recent_chat_emit", None)
            if not isinstance(recent, dict):
                recent = {}
                setattr(self.state, "_recent_chat_emit", recent)
            now = time.time()
            try:
                for key, ts in list(recent.items()):
                    if now - float(ts or 0.0) > 5.0:
                        recent.pop(key, None)
            except Exception:
                pass
            dedupe_key = "|".join([
                item.get("source_plugin_id", ""),
                item.get("platform", ""),
                item.get("channel", ""),
                item.get("user", "").strip().lower(),
                " ".join(str(item.get("text") or "").split()).lower(),
                str(item.get("message_type") or "chat").lower(),
            ])
            old_ts = recent.get(dedupe_key)
            if old_ts is not None and now - float(old_ts or 0.0) <= 2.5:
                self.log(plugin_id, f"duplicate chat row suppressed: {item.get('platform')} {item.get('user')} {str(item.get('text') or '')[:120]}")
                return
            recent[dedupe_key] = now

            self.state.messages.append(item)
            if len(self.state.messages) > 300:
                self.state.messages = self.state.messages[-300:]
            if item.get("message_type", "chat") in {"chat", "message", "comment"}:
                self.log(plugin_id, f"chat | {item.get('platform')}:{item.get('user')}: {str(item.get('text') or '')[:180]}")
            self._dispatch_chat_message(plugin_id, item)
        except Exception as exc:
            self.log(plugin_id, f"emit_message failed: {exc}")

    def _dispatch_chat_message(self, plugin_id: str, item: dict) -> None:
        try:
            source_plugin_id = str(item.get("source_plugin_id") or plugin_id or "").strip()
            allow_plugin_dispatch = bool(item.get("dispatch_to_plugins") or item.get("bridge_to_platforms"))
            if not allow_plugin_dispatch and source_plugin_id not in CHAT_INPUT_PLUGIN_IDS and str(plugin_id or "").strip() not in CHAT_INPUT_PLUGIN_IDS:
                return
            message_type = str(item.get("message_type") or "chat").strip().lower()
            if message_type not in {"chat", "message", "comment"}:
                return
            if not str(item.get("text") or "").strip():
                return
            targets = []
            for target_id, plugin in list(getattr(self.state, "plugin_instances", {}).items()):
                if target_id == source_plugin_id or target_id in CHAT_INPUT_PLUGIN_IDS:
                    continue
                handler = getattr(plugin, "on_message", None)
                if callable(handler):
                    targets.append((target_id, handler))
            if not targets:
                return

            msg = dict(item)
            msg.setdefault("source_platform", item.get("platform") or "")

            def run_dispatch() -> None:
                for target_id, handler in targets:
                    try:
                        handler(dict(msg))
                    except Exception as exc:
                        self.log(target_id, f"on_message failed: {exc}")

            threading.Thread(target=run_dispatch, daemon=True, name="chat-command-dispatch").start()
        except Exception as exc:
            self.log("chat-dispatch", f"failed: {exc}")

    def emit_metric(self, plugin_id: str, payload: dict) -> None:
        try:
            payload = dict(payload or {})
            platform = str(payload.get("platform") or "")
            if platform:
                self.state.metrics[platform] = {**payload, "ts": time.time(), "plugin_id": plugin_id}
            sig = "|".join([
                str(plugin_id),
                platform,
                str(payload.get("message_type") or payload.get("type") or ""),
                str(payload.get("viewer_count") if payload.get("viewer_count") is not None else payload.get("text") or ""),
                str(payload.get("followers_count") if payload.get("followers_count") is not None else ""),
            ])
            now = time.time()
            recent = getattr(self.state, "_recent_metric_log", None)
            if not isinstance(recent, dict):
                recent = {}
                setattr(self.state, "_recent_metric_log", recent)
            last = float(recent.get(sig) or 0.0)
            if now - last >= 60.0:
                recent[sig] = now
                self.state.log(str(plugin_id), "metric", json.dumps(payload, ensure_ascii=False)[:500])
        except Exception:
            pass

    def _outbound_echo_key(self, platform: str, text: str) -> str:
        return "|".join([
            str(platform or "").strip().lower(),
            " ".join(str(text or "").split()).lower(),
        ])

    def _mark_outbound_echo(self, sender: str, platform: str, message: str, ttl: float = 45.0) -> None:
        if str(sender or "").strip().lower() not in {"bridg3alot", "spotis3mptify", "botalot", "gam3pick3r", "bot"}:
            return
        key = self._outbound_echo_key(platform, message)
        if not key.strip("|"):
            return
        recent = getattr(self.state, "_suppressed_outbound_echoes", None)
        if not isinstance(recent, dict):
            recent = {}
            setattr(self.state, "_suppressed_outbound_echoes", recent)
        now = time.time()
        try:
            for old_key, expires in list(recent.items()):
                if float(expires or 0.0) < now:
                    recent.pop(old_key, None)
        except Exception:
            pass
        recent[key] = now + max(3.0, float(ttl or 45.0))

    def _is_suppressed_outbound_echo(self, payload: dict, text: str) -> bool:
        message_type = str(payload.get("message_type") or payload.get("type") or "chat").strip().lower()
        if message_type not in {"chat", "message", "comment"}:
            return False
        platform = str(payload.get("platform") or "").strip().lower()
        key = self._outbound_echo_key(platform, text)
        recent = getattr(self.state, "_suppressed_outbound_echoes", None)
        if not isinstance(recent, dict):
            return False
        now = time.time()
        try:
            for old_key, expires in list(recent.items()):
                if float(expires or 0.0) < now:
                    recent.pop(old_key, None)
        except Exception:
            pass
        if float(recent.get(key) or 0.0) < now:
            return False
        return True

    def send_platform_message(self, platform: str, message: str, **kwargs) -> bool:
        try:
            sender = str(kwargs.get("sender") or "").strip()
            self._mark_outbound_echo(sender, platform, message)
            plugin = self.state.plugin_instances.get(f"{platform}_chat") or self.state.plugin_instances.get(platform)
            if plugin is not None and hasattr(plugin, "send_message"):
                result = plugin.send_message(message, settings=self.state.plugin_settings(getattr(plugin, "plugin_id", f"{platform}_chat")), host=self)
                if isinstance(result, tuple):
                    ok = bool(result[0]) if result else False
                    detail = str(result[1]) if len(result) > 1 else ""
                    self.log("platform-send", f"{platform}: {detail or ('sent' if ok else 'failed')}")
                    return ok
                ok = bool(result)
                self.log("platform-send", f"{platform}: {'sent' if ok else 'failed'}")
                return ok
            self.log("platform-send", f"{platform}: no send_message handler")
        except Exception as exc:
            self.log("platform-send", f"{platform}: {exc}")
        return False


class WebbasedPluginManager:
    def __init__(self, state):
        self.state = state
        self.host = WebbasedPluginHost(state)
        self.started = False

    def discover(self) -> list[dict]:
        out = []
        try:
            for module_root in self.state.module_roots:
                for folder in sorted(module_root.iterdir()):
                    if not folder.is_dir() or not (folder / "manifest.json").is_file() or not (folder / "plugin.py").is_file():
                        continue
                    man = _json_load(folder / "manifest.json", {})
                    pid = str(man.get("id") or folder.name)
                    status = self.state.plugin_status.get(pid, {"state": "ready", "message": "Bereit"})
                    state = str(status.get("state") or "ready")
                    msg = str(status.get("message") or "Bereit")
                    out.append({
                        "id": pid,
                        "name": man.get("name") or folder.name,
                        "version": man.get("version") or "",
                        "description": man.get("description") or man.get("description_de") or "",
                        "enabled": bool(self.state.plugin_enabled(pid)),
                        "status": self._status_label(state, msg),
                        "state": state,
                        "message": msg,
                    })
        except Exception as exc:
            self.state.log("plugins", "discover failed", exc)
        return out

    def _status_label(self, state: str, msg: str) -> str:
        st = (state or "").lower()
        if st in {"connected", "running"}:
            return "Verbunden" if not msg else f"Verbunden · {msg}"
        if st in {"connecting", "starting"}:
            return "Verbindet" if not msg else f"Verbindet · {msg}"
        if st in {"error", "failed"}:
            return "Fehler" if not msg else f"Fehler · {msg}"
        if st in {"disconnected", "stopped"}:
            return "Gestoppt" if not msg else f"Gestoppt · {msg}"
        return msg or "Bereit"

    def ensure_started(self) -> None:
        if self.started:
            return
        self.started = True
        for plugin_id in ("twitch_chat", "tiktok_chat", "youtube_chat", "kick_chat", "spotis3mptify", "gam3pick3r", "botalot", "bridg3alot", "modalot"):
            self.start_plugin(plugin_id)

    def load_plugin(self, plugin_id: str):
        if plugin_id in self.state.plugin_instances:
            return self.state.plugin_instances[plugin_id]
        folder = self.state.module_folder(plugin_id)
        plugin_file = folder / "plugin.py"
        if not plugin_file.exists():
            raise RuntimeError(f"plugin.py fehlt: {plugin_id}")
        root = str(self.state.base)
        module_roots = [str(path) for path in self.state.module_roots]
        for item in (root, *module_roots, str(folder)):
            if item and item not in sys.path:
                sys.path.insert(0, item)
        mod_name = f"webbased_plugin_{plugin_id}_{abs(hash(str(plugin_file)))}"
        spec = importlib.util.spec_from_file_location(mod_name, plugin_file)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Plugin kann nicht geladen werden: {plugin_id}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        if not hasattr(module, "create_plugin"):
            raise RuntimeError(f"create_plugin fehlt: {plugin_id}")
        plugin = module.create_plugin()
        self.state.plugin_instances[plugin_id] = plugin
        return plugin

    def start_plugin(self, plugin_id: str) -> bool:
        try:
            if not self.state.plugin_enabled(plugin_id):
                self.state.plugin_status[plugin_id] = {"state": "stopped", "message": "Deaktiviert", "ts": time.time()}
                return False
            plugin = self.load_plugin(plugin_id)
            settings = self.state.plugin_settings(plugin_id, plugin)
            plugin.start(settings, self.host)
            return True
        except Exception as exc:
            self.state.plugin_status[plugin_id] = {"state": "error", "message": str(exc), "ts": time.time()}
            self.state.log(plugin_id, "start failed", exc)
            return False

    def restart_plugin_async(self, plugin_id: str, reason: str = "") -> None:
        plugin_id = str(plugin_id or "").strip()
        if not plugin_id:
            return

        def worker() -> None:
            try:
                self.state.plugin_status[plugin_id] = {"state": "starting", "message": reason or "Neustart laeuft", "ts": time.time()}
                old_plugin = self.state.plugin_instances.get(plugin_id)
                if old_plugin is not None:
                    try:
                        old_plugin.stop(wait=True, timeout=3.0)
                    except TypeError:
                        try:
                            old_plugin.stop()
                        except Exception:
                            pass
                    except Exception as exc:
                        self.state.log(plugin_id, "stop before restart failed", exc)
                    self.state.plugin_instances.pop(plugin_id, None)
                self.start_plugin(plugin_id)
            except Exception as exc:
                self.state.plugin_status[plugin_id] = {"state": "error", "message": str(exc), "ts": time.time()}
                self.state.log(plugin_id, "async restart failed", exc)

        threading.Thread(target=worker, daemon=True, name=f"plugin-restart-{plugin_id}").start()

    def stop_all(self) -> None:
        for pid, plugin in list(self.state.plugin_instances.items()):
            try:
                plugin.stop(wait=True)
            except TypeError:
                try: plugin.stop()
                except Exception: pass
            except Exception as exc:
                self.state.log(pid, "stop failed", exc)

class AppState:
    def __init__(self, base: str, port: int):
        self.base = Path(base)
        self.port = port

        # Runtime data stays next to the EXE/script.
        self.data = self.base / "data"
        # UI resources and bundled modules may be next to the script or inside PyInstaller.
        resource_candidates = [
            self.base,
            self.base / "_internal",
            Path(getattr(sys, "_MEIPASS", self.base)),
        ]
        host_candidates = [p / "core" / "host" for p in resource_candidates]
        self.resource_base = next((p for p in host_candidates if (p / "templates").exists() and (p / "static").exists()), host_candidates[0])
        self.static = self.resource_base / "static"
        self.templates = self.resource_base / "templates"
        module_candidates = [p / "modules" for p in resource_candidates]
        self.modules = next((p for p in module_candidates if p.exists()), module_candidates[0])
        self.module_roots = [self.modules / "integrations", self.modules / "plugins"]
        self.settings_path = self.data / "settings.json"
        self.auth_dir = self.data / "auth"
        self.messages = [{
            "id": _now_ms(),
            "platform": "system",
            "user": "webbased",
            "text": "Webbased gestartet. Chat-Browser ist bereit.",
            "time": time.strftime("%H:%M:%S")
        }]
        self.started = time.time()
        self.last_ui_heartbeat = 0.0
        self.ui_heartbeat_enabled = False
        self.ui_heartbeat_lost = False
        self.last_ui_reopen = 0.0
        self.ui_reload_requested = False
        self.ui_reload_nonce = 0
        self.last_ui_reload_request = 0.0
        self.main_url = ""
        self.shutting_down = False
        self._tiktok_cookie_backoff = {}
        self._tiktok_cookie_warned = set()
        self._meld_status_cache = {"ts": 0.0, "host": "", "port": 0, "ok": False, "detail": "nicht verbunden", "locked": False}
        self._obs_status_cache = {"ts": 0.0, "host": "", "port": 0, "ok": False, "detail": "nicht verbunden", "locked": False}
        self._youtube_status_cache = {"ts": 0.0, "ok": False, "detail": "nicht verbunden", "locked": False, "key": None}
        self._spotify_status_cache = {"ts": 0.0, "ok": False, "detail": "nicht verbunden", "key": None}
        self._openai_status_cache = {"ts": 0.0, "ok": False, "detail": "nicht verbunden", "locked": False, "key": None, "models": []}
        # OBS must be a real/persistent connection like in the original tool.
        # A short test socket makes the dashboard green, but OBS shows no active session afterwards.
        self._obs_sock = None
        self._obs_thread = None
        self._obs_stop = threading.Event()
        self._obs_lock = threading.RLock()
        self._obs_conn_key = None
        self.data.mkdir(exist_ok=True)
        (self.data / "plugins").mkdir(parents=True, exist_ok=True)
        for module_root in self.module_roots:
            module_root.mkdir(parents=True, exist_ok=True)
        self.log_dir = self.data / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "webbased.log"
        self.run_state_path = self.log_dir / "run_state.json"
        self.crash_report_path = self.log_dir / "godisalotachat_crashlog.txt"
        try:
            self.auth_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._import_auth_from_source_data_fallback()
        self.plugin_status = {}
        self.plugin_instances = {}
        self.metrics = {}
        self.desktop_chat_editing = False
        self._unclean_exit_marked = False
        # Do not create/open desktop crash report text files on startup.
        # The persistent run_state.json is enough for diagnostics and keeps Invoke/image workflows unobstructed.
        self._write_run_state("running", clean=False, reason="started")
        self.plugin_manager = WebbasedPluginManager(self)
        self.log("start", "base=" + str(self.base), "resource=" + str(self.resource_base), "templates=" + str(self.templates), "static=" + str(self.static))

    def _json_has_runtime_token(self, path: Path) -> bool:
        try:
            data = _json_load(path, {})
            return isinstance(data, dict) and bool(str(data.get("access_token") or data.get("refresh_token") or "").strip())
        except Exception:
            return False

    def _source_data_fallback_dirs(self) -> list[Path]:
        """Runtime safety net for rebuilt EXEs.

        A rebuilt EXE runs from dist/webbased and normally uses dist/webbased/data.
        If that folder is freshly created or stale while the project-root data folder
        still contains OAuth files, autoconnect must hydrate from that source copy
        instead of forcing a new OAuth round.
        """
        out: list[Path] = []
        try:
            # C:\project\dist\webbased -> C:\project\data
            if self.base.name.lower() == "webbased" and self.base.parent.name.lower() == "dist":
                out.append(self.base.parent.parent / "data")
        except Exception:
            pass
        try:
            cwd_data = Path.cwd().resolve() / "data"
            out.append(cwd_data)
        except Exception:
            pass
        clean: list[Path] = []
        seen: set[str] = set()
        for item in out:
            try:
                resolved = item.resolve()
                if resolved == self.data.resolve():
                    continue
                key = str(resolved).lower()
                if key in seen or not resolved.exists():
                    continue
                seen.add(key)
                clean.append(resolved)
            except Exception:
                pass
        return clean

    def _merge_auth_settings_from_source(self, dst: dict, src: dict) -> bool:
        if not isinstance(dst, dict) or not isinstance(src, dict):
            return False
        changed = False
        dst_platforms = dst.setdefault("platforms", {})
        src_platforms = src.get("platforms", {}) if isinstance(src.get("platforms", {}), dict) else {}
        keys = {
            "enabled", "autoconnect", "main", "bot", "channel", "main_account", "bot_account", "username",
            "bot_username", "main_username", "channel_slug", "client_id", "client_secret", "redirect_uri", "redirect_url",
            "redirect_port", "scopes", "main_scopes", "access_token", "refresh_token", "main_access_token",
            "main_refresh_token", "bot_access_token", "bot_refresh_token", "oauth_login", "oauth_user_id",
            "main_oauth_login", "main_oauth_user_id", "broadcaster_user_id", "broadcaster_id", "chatroom_id",
            "chatroom_channel", "channel_id", "main_user_id", "bot_user_id", "main_channel_id", "bot_channel_id",
            "main_channel_title", "bot_channel_title", "broadcaster_channel_id", "expires_at", "expires_in",
            "main_expires_at", "main_expires_in", "saved_at", "main_saved_at", "token_type", "main_token_type",
        }
        for platform, src_cfg in src_platforms.items():
            if not isinstance(src_cfg, dict):
                continue
            dst_cfg = dst_platforms.setdefault(platform, {})
            if not isinstance(dst_cfg, dict):
                dst_platforms[platform] = {}
                dst_cfg = dst_platforms[platform]
                changed = True
            for key in keys:
                value = src_cfg.get(key)
                if value in (None, ""):
                    continue
                current = dst_cfg.get(key)
                # Preserve explicit user switches, but fill missing account/auth fields.
                if key in {"enabled", "autoconnect"} and key in dst_cfg:
                    continue
                main_blocked = bool(dst_cfg.get("main_disconnected_at")) and key.startswith("main_")
                bot_blocked = bool(dst_cfg.get("bot_disconnected_at")) and (not key.startswith("main_")) and key in {
                    "access_token", "refresh_token", "bot_access_token", "bot_refresh_token",
                    "oauth_login", "oauth_user_id", "username", "bot_username", "bot_user_id",
                    "bot_channel_id", "bot_channel_title",
                }
                spotify_blocked = platform == "spotify" and bool(dst_cfg.get("main_disconnected_at")) and key in {
                    "access_token", "refresh_token", "saved_at", "expires_at", "expires_in", "token_type",
                }
                if main_blocked or bot_blocked or spotify_blocked:
                    continue
                if current in (None, ""):
                    dst_cfg[key] = value
                    changed = True
        return changed

    def _import_auth_from_source_data_fallback(self) -> None:
        try:
            sources = self._source_data_fallback_dirs()
            if not sources:
                return
            self.auth_dir.mkdir(parents=True, exist_ok=True)
            imported = []
            def disconnected_auth_file(name: str) -> bool:
                try:
                    stem = Path(name).stem.lower()
                    if "_" not in stem:
                        return False
                    platform, account = stem.rsplit("_", 1)
                    account = "main" if account == "main" else "bot"
                    dst_settings = _json_load(self.settings_path, {})
                    cfg = (dst_settings.get("platforms", {}) if isinstance(dst_settings, dict) else {}).get(platform, {})
                    if not isinstance(cfg, dict):
                        return False
                    return bool(cfg.get("main_disconnected_at" if account == "main" else "bot_disconnected_at"))
                except Exception:
                    return False
            for src_data in sources:
                src_auth = src_data / "auth"
                if src_auth.exists():
                    for src_file in src_auth.glob("*.json"):
                        dst_file = self.auth_dir / src_file.name
                        if disconnected_auth_file(src_file.name):
                            continue
                        if self._json_has_runtime_token(dst_file):
                            continue
                        if self._json_has_runtime_token(src_file):
                            try:
                                dst_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src_file, dst_file)
                                imported.append(f"auth/{src_file.name}")
                            except Exception:
                                pass
                src_settings_path = src_data / "settings.json"
                if src_settings_path.exists():
                    dst_settings = _json_load(self.settings_path, {})
                    src_settings = _json_load(src_settings_path, {})
                    if not isinstance(dst_settings, dict) or not dst_settings:
                        try:
                            shutil.copy2(src_settings_path, self.settings_path)
                            imported.append("settings.json")
                        except Exception:
                            pass
                    elif self._merge_auth_settings_from_source(dst_settings, src_settings):
                        _json_save(self.settings_path, dst_settings)
                        imported.append("settings.json auth fields")
            if imported:
                try:
                    self.log("auth", "imported runtime auth fallback", ", ".join(sorted(set(imported))))
                except Exception:
                    pass
        except Exception as exc:
            try:
                self.log("auth", "runtime auth fallback failed", exc)
            except Exception:
                pass

    def _write_run_state(self, state: str, *, clean: bool, reason: str = "", extra: dict | None = None) -> None:
        try:
            payload = {
                "app": APP_NAME,
                "version": VERSION,
                "pid": os.getpid(),
                "state": str(state or ""),
                "clean_shutdown": bool(clean),
                "reason": str(reason or ""),
                "base": str(self.base),
                "data": str(self.data),
                "log": str(self.log_file),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_ts": time.time(),
            }
            if isinstance(extra, dict):
                payload.update(extra)
            _json_save(self.run_state_path, payload)
        except Exception:
            pass

    def mark_clean_shutdown(self, reason: str = "normal shutdown") -> None:
        if self._unclean_exit_marked:
            return
        self._write_run_state("stopped", clean=True, reason=reason)

    def mark_unclean_exit(self, reason: str, detail: str = "") -> None:
        self._unclean_exit_marked = True
        extra = {"detail": str(detail or "")}
        self._write_run_state("unclean-exit", clean=False, reason=reason, extra=extra)

    def _report_previous_unclean_exit(self) -> None:
        previous = _json_load(self.run_state_path, {})
        if not isinstance(previous, dict) or previous.get("clean_shutdown") is True or not previous:
            return
        try:
            self.log(
                "startup",
                "previous run was not clean",
                "reason=" + str(previous.get("reason", "") or "unbekannt"),
                "state=" + str(previous.get("state", "")),
            )
        except Exception:
            pass

    def module_folder(self, module_id: str) -> Path:
        for module_root in self.module_roots:
            folder = module_root / module_id
            if folder.is_dir():
                return folder
        return self.module_roots[-1] / module_id

    def log(self, *parts):
        try:
            source, level, message = _normalize_log_parts(parts)
            line = time.strftime("%Y-%m-%d %H:%M:%S") + f" | {source} | {level} | " + _redact_dev_log(message) + "\n"
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def settings(self):
        default = {
            "version": VERSION,
            "platforms": {p: {"enabled": False, "status": "nicht verbunden"} for p in PLATFORM_ORDER},
            "plugins": {}
        }
        s = _json_load(self.settings_path, default)
        s["version"] = VERSION
        s.setdefault("platforms", {})
        for p in PLATFORM_ORDER:
            s["platforms"].setdefault(p, {"enabled": False, "status": "nicht verbunden"})
        # Original-kompatible Redirect-URIs und sichtbare/unsichtbare Token-Felder.
        for k, v in DEFAULT_REDIRECTS.items():
            s["platforms"].setdefault(k, {})
            if not str(s["platforms"][k].get("redirect_uri") or s["platforms"][k].get("redirect_url") or "").strip():
                s["platforms"][k]["redirect_uri"] = v
                s["platforms"][k]["redirect_url"] = v
        self._migrate_platform_defaults(s["platforms"])
        self._ensure_auth_files_from_settings(s)
        return s

    def _migrate_platform_defaults(self, platforms):
        def merge_scopes(current, required):
            items = []
            for raw in (str(current or ""), str(required or "")):
                for part in raw.split():
                    part = part.strip()
                    if part and part not in items:
                        items.append(part)
            return " ".join(items)

        tw = platforms.setdefault("twitch", {})
        tw.setdefault("enabled", True); tw.setdefault("autoconnect", True)
        tw.setdefault("redirect_port", 17564); tw.setdefault("redirect_url", DEFAULT_REDIRECTS["twitch"]); tw.setdefault("redirect_uri", DEFAULT_REDIRECTS["twitch"])
        tw.setdefault("scopes", DEFAULT_SCOPES["twitch"]["bot"]); tw.setdefault("main_scopes", DEFAULT_SCOPES["twitch"]["main"])
        tw["scopes"] = merge_scopes(tw.get("scopes"), DEFAULT_SCOPES["twitch"]["bot"])
        tw["main_scopes"] = merge_scopes(tw.get("main_scopes"), DEFAULT_SCOPES["twitch"]["main"])
        tw.setdefault("channel", tw.get("main") or tw.get("main_account") or ""); tw.setdefault("bot_username", tw.get("bot") or tw.get("bot_account") or "")
        for k in ("access_token","refresh_token","oauth_login","oauth_user_id","main_access_token","main_refresh_token","main_oauth_login","main_oauth_user_id","broadcaster_user_id","broadcaster_id"):
            tw.setdefault(k, "")

        yt = platforms.setdefault("youtube", {})
        yt.setdefault("enabled", True); yt.setdefault("autoconnect", True)
        yt.setdefault("redirect_port", 17566); yt.setdefault("redirect_url", DEFAULT_REDIRECTS["youtube"]); yt.setdefault("redirect_uri", DEFAULT_REDIRECTS["youtube"])
        yt.setdefault("scopes", DEFAULT_SCOPES["youtube"]["bot"]); yt.setdefault("main_scopes", DEFAULT_SCOPES["youtube"]["main"])
        yt["scopes"] = merge_scopes(yt.get("scopes"), DEFAULT_SCOPES["youtube"]["bot"])
        yt["main_scopes"] = merge_scopes(yt.get("main_scopes"), DEFAULT_SCOPES["youtube"]["main"])
        for k in ("access_token","refresh_token","main_access_token","main_refresh_token","bot_channel_id","bot_channel_title","bot_channel_custom_url","main_channel_id","main_channel_title","main_channel_custom_url","broadcaster_channel_id"):
            yt.setdefault(k, "")

        kk = platforms.setdefault("kick", {})
        kk.setdefault("enabled", True); kk.setdefault("autoconnect", True)
        kk.setdefault("redirect_url", DEFAULT_REDIRECTS["kick"]); kk.setdefault("redirect_uri", DEFAULT_REDIRECTS["kick"])
        kk.setdefault("scopes", DEFAULT_SCOPES["kick"]["bot"]); kk.setdefault("main_scopes", DEFAULT_SCOPES["kick"]["main"])
        kk["scopes"] = merge_scopes(kk.get("scopes"), DEFAULT_SCOPES["kick"]["bot"])
        kk["main_scopes"] = merge_scopes(kk.get("main_scopes"), DEFAULT_SCOPES["kick"]["main"])
        kk.setdefault("channel", kk.get("main") or kk.get("main_account") or ""); kk.setdefault("bot_username", kk.get("bot") or kk.get("bot_account") or "")
        if not str(kk.get("channel") or "").strip():
            kk["channel"] = str(kk.get("main") or kk.get("main_account") or "").strip()
        kk.setdefault("main_account", kk.get("main") or kk.get("channel") or "")
        kk.setdefault("bot_account", kk.get("bot") or kk.get("bot_username") or "")
        for k in ("access_token","refresh_token","main_access_token","main_refresh_token","bot_user_id","main_user_id","broadcaster_user_id","channel_id","channel_slug"):
            kk.setdefault(k, "")

        sp = platforms.setdefault("spotify", {})
        sp.setdefault("enabled", True); sp.setdefault("autoconnect", True)
        sp.setdefault("redirect_uri", DEFAULT_REDIRECTS["spotify"]); sp.setdefault("scopes", DEFAULT_SCOPES["spotify"]["main"]); sp.setdefault("port", 5173)

        ai = platforms.setdefault("openai", {})
        ai.setdefault("enabled", False)
        ai.setdefault("autoconnect", True)
        ai.setdefault("api_key", "")
        ai.setdefault("organization", "")
        ai.setdefault("project", "")
        ai.pop("model", None)

        # TikTok hat keinen OAuth-Redirect wie Twitch/YouTube/Kick/Spotify.
        # Wir halten getrennte Browserprofile für Main und Bot vor, damit QR-/Login-Cookies erhalten bleiben.
        tt = platforms.setdefault("tiktok", {})
        tt.setdefault("enabled", True)
        tt.setdefault("autoconnect", True)
        main_name = str(tt.get("main") or tt.get("main_account") or tt.get("unique_id") or "").strip().lstrip("@")
        bot_name = str(tt.get("bot") or tt.get("bot_account") or "").strip().lstrip("@")
        tt["main"] = main_name; tt["main_account"] = main_name; tt["unique_id"] = main_name
        tt["bot"] = bot_name; tt["bot_account"] = bot_name
        tt["live_url"] = f"https://www.tiktok.com/@{main_name}/live" if main_name else ""
        tt["resolved_live_url"] = tt["live_url"]
        tt.setdefault("browser_path", "")
        default_main_profile = str(self.data / "tiktok" / "main_profile")
        default_bot_profile = str(self.data / "tiktok" / "bot_profile")
        # Alte Zwischenversionen konnten versehentlich ein gemeinsames profile_dir benutzen.
        # Main und Bot müssen getrennte Browserprofile behalten, sonst überschreibt der Bot-Login
        # optisch/technisch den Main-Status.
        if not str(tt.get("main_profile_dir") or "").strip():
            tt["main_profile_dir"] = default_main_profile
        if not str(tt.get("bot_profile_dir") or "").strip():
            tt["bot_profile_dir"] = default_bot_profile
        if str(tt.get("main_profile_dir") or "") == str(tt.get("bot_profile_dir") or ""):
            tt["main_profile_dir"] = default_main_profile
            tt["bot_profile_dir"] = default_bot_profile
        tt.setdefault("main_login_ok", False)
        tt.setdefault("bot_login_ok", False)
        if bool(tt.get("main_login_ok") or tt.get("bot_login_ok")):
            tt["enabled"] = True
        tt.setdefault("remote_debug_port", 9229)
        tt.setdefault("bot_remote_debug_port", 9230)

        # Meld Studio braucht keine OAuth-/Login-Daten. Genau wie im Original: nur aktiv, Autoconnect, Host und Port.
        meld = platforms.setdefault("meld", {})
        meld.setdefault("enabled", True)
        meld.setdefault("autoconnect", True)
        meld.setdefault("host", "127.0.0.1")
        meld.setdefault("port", 13376)
        meld.pop("password", None)

        # OBS: Standard-WebSocket v5. Grundlegend reicht dadurch im Normalfall nur das Passwort.
        obs = platforms.setdefault("obs", {})
        obs.setdefault("enabled", True)
        obs.setdefault("autoconnect", True)
        obs.setdefault("host", "127.0.0.1")
        obs.setdefault("port", 4455)
        obs.setdefault("password", "")
        obs.setdefault("url", "ws://127.0.0.1:4455")
        return platforms

    def _tiktok_profile_dir(self, cfg, account):
        account = "bot" if str(account or "").lower().strip() == "bot" else "main"
        key = "bot_profile_dir" if account == "bot" else "main_profile_dir"
        fallback = self.data / "tiktok" / ("bot_profile" if account == "bot" else "main_profile")
        # Kein gemeinsames profile_dir mehr als Fallback nutzen. Main und Bot brauchen getrennte Profile.
        raw = str((cfg or {}).get(key) or fallback).strip()
        return Path(raw) if raw else fallback

    def _find_browser_exe(self, cfg=None):
        cfg = cfg or {}
        raw = str(cfg.get("browser_path") or "").strip().strip('"')
        if raw and Path(raw).exists():
            return raw
        candidates = []
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            candidates += [
                Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(base) / "Chromium" / "Application" / "chrome.exe",
            ]
        for c in candidates:
            try:
                if c.exists():
                    return str(c)
            except Exception:
                pass
        return ""

    def _windows_process_children(self, root_pid: int):
        """Return root pid + descendants on Windows using Toolhelp32Snapshot."""
        pids = set()
        if os.name != "nt" or not root_pid:
            return pids
        try:
            TH32CS_SNAPPROCESS = 0x00000002
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", ctypes.c_ulong),
                    ("cntUsage", ctypes.c_ulong),
                    ("th32ProcessID", ctypes.c_ulong),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", ctypes.c_ulong),
                    ("cntThreads", ctypes.c_ulong),
                    ("th32ParentProcessID", ctypes.c_ulong),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", ctypes.c_ulong),
                    ("szExeFile", ctypes.c_wchar * 260),
                ]

            kernel32 = ctypes.windll.kernel32
            snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snap == INVALID_HANDLE_VALUE:
                return {int(root_pid)}
            try:
                pe = PROCESSENTRY32()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
                parent_map = {}
                if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
                    while True:
                        parent_map.setdefault(int(pe.th32ParentProcessID), set()).add(int(pe.th32ProcessID))
                        if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                            break
                queue = [int(root_pid)]
                while queue:
                    cur = queue.pop(0)
                    if cur in pids:
                        continue
                    pids.add(cur)
                    queue.extend(parent_map.get(cur, set()))
            finally:
                kernel32.CloseHandle(snap)
        except Exception:
            pids.add(int(root_pid))
        return pids

    def _windows_pids_by_command_hint(self, profile_dir: Path | None = None, port: int | None = None):
        """Find Chrome/Edge pids that belong to the TikTok profile.

        If Chrome/Edge already has a process for that user-data-dir, a new command
        can be forwarded to the old process. Then the real window does not belong
        to the freshly spawned Popen pid. This finds that existing browser process.
        """
        pids = set()
        if os.name != "nt":
            return pids
        hints = []
        try:
            if profile_dir:
                hints.append(str(Path(profile_dir)).replace("\\", "\\\\"))
                hints.append(str(Path(profile_dir)))
        except Exception:
            pass
        if port:
            hints.append(f"remote-debugging-port={int(port)}")
        if not hints:
            return pids
        try:
            # PowerShell is available on normal Windows installs and is only used
            # as a fallback to locate already-running Chrome/Edge profile processes.
            cond = " -or ".join(["$_.CommandLine -like " + repr("*" + h + "*") for h in hints if h])
            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                f"Get-CimInstance Win32_Process | Where-Object {{ {cond} }} | ForEach-Object {{ $_.ProcessId }}"
            ]
            kwargs = {"stderr": subprocess.DEVNULL, "timeout": 2, "text": True, "encoding": "utf-8", "errors": "ignore"}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kwargs["startupinfo"] = si
            out = subprocess.check_output(cmd, **kwargs)
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        except Exception:
            pass
        return pids

    def _bring_windows_to_front(self, pid: int = 0, profile_dir: Path | None = None, port: int | None = None, title_hint: str = "TikTok"):
        """Best-effort: put externally opened login windows in front of the webbased page.

        The old version only looked at the exact Popen pid. Chrome/Edge often
        creates the visible window in a child process, or forwards the command to
        an already-running browser process for the same profile. This version
        searches root pid, children, profile/port processes and TikTok-titled
        windows, then temporarily makes the login window topmost.
        """
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            IsWindowVisible = user32.IsWindowVisible
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            ShowWindow = user32.ShowWindow
            SetForegroundWindow = user32.SetForegroundWindow
            BringWindowToTop = user32.BringWindowToTop
            SetWindowPos = user32.SetWindowPos
            GetWindowTextLengthW = user32.GetWindowTextLengthW
            GetWindowTextW = user32.GetWindowTextW
            GetForegroundWindow = user32.GetForegroundWindow
            GetCurrentThreadId = ctypes.windll.kernel32.GetCurrentThreadId
            AttachThreadInput = user32.AttachThreadInput
            try:
                user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass
            SW_RESTORE = 9
            SW_SHOW = 5
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            target_pids = set()
            if pid:
                target_pids.update(self._windows_process_children(int(pid)))
            target_pids.update(self._windows_pids_by_command_hint(profile_dir, port))
            found = []
            hint = str(title_hint or "").lower()

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_proc(hwnd, lparam):
                try:
                    if not IsWindowVisible(hwnd):
                        return True
                    out_pid = ctypes.c_ulong()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(out_pid))
                    title = ""
                    try:
                        ln = int(GetWindowTextLengthW(hwnd))
                        if ln > 0:
                            buf = ctypes.create_unicode_buffer(ln + 1)
                            GetWindowTextW(hwnd, buf, ln + 1)
                            title = str(buf.value or "")
                    except Exception:
                        title = ""
                    pid_match = int(out_pid.value) in target_pids if target_pids else False
                    title_match = bool(hint and hint in title.lower())
                    if pid_match or title_match:
                        found.append(hwnd)
                except Exception:
                    pass
                return True

            # Several passes because Edge/Chrome app windows appear a little late.
            for _ in range(24):
                found.clear()
                if pid:
                    target_pids.update(self._windows_process_children(int(pid)))
                target_pids.update(self._windows_pids_by_command_hint(profile_dir, port))
                EnumWindows(enum_proc, 0)
                if found:
                    break
                time.sleep(0.2)

            for hwnd in found:
                try:
                    ShowWindow(hwnd, SW_RESTORE)
                    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                    BringWindowToTop(hwnd)
                    # Windows blockt Fremdprozesse beim Fokusklau gern. AttachThreadInput macht das
                    # zuverlässiger und verhindert, dass das TikTok-Fenster hinter der Webbased-Seite bleibt.
                    try:
                        fg = GetForegroundWindow()
                        cur_thread = GetCurrentThreadId()
                        fg_pid = ctypes.c_ulong()
                        target_pid = ctypes.c_ulong()
                        fg_thread = GetWindowThreadProcessId(fg, ctypes.byref(fg_pid)) if fg else 0
                        target_thread = GetWindowThreadProcessId(hwnd, ctypes.byref(target_pid))
                        if fg_thread and target_thread and fg_thread != target_thread:
                            AttachThreadInput(cur_thread, fg_thread, True)
                            AttachThreadInput(cur_thread, target_thread, True)
                        SetForegroundWindow(hwnd)
                        BringWindowToTop(hwnd)
                        if fg_thread and target_thread and fg_thread != target_thread:
                            AttachThreadInput(cur_thread, target_thread, False)
                            AttachThreadInput(cur_thread, fg_thread, False)
                    except Exception:
                        SetForegroundWindow(hwnd)
                    time.sleep(0.08)
                    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                except Exception:
                    pass

            # Keep it topmost just long enough to actually appear in front, then
            # release topmost so it doesn't annoy while QR login is open.
            if found:
                def release():
                    time.sleep(1.5)
                    for hwnd in found:
                        try:
                            SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                        except Exception:
                            pass
                threading.Thread(target=release, daemon=True).start()
        except Exception as exc:
            try: self.log("tiktok", "bring-to-front failed", exc)
            except Exception: pass


    def _close_tiktok_login_windows(self, pid: int = 0, profile_dir: Path | None = None, port: int | None = None):
        """Close the TikTok login app window after a real login was detected."""
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            IsWindowVisible = user32.IsWindowVisible
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            PostMessageW = user32.PostMessageW
            WM_CLOSE = 0x0010
            target_pids = set()
            if pid:
                target_pids.update(self._windows_process_children(int(pid)))
            target_pids.update(self._windows_pids_by_command_hint(profile_dir, port))
            if not target_pids:
                return

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_proc(hwnd, lparam):
                try:
                    if not IsWindowVisible(hwnd):
                        return True
                    out_pid = ctypes.c_ulong()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(out_pid))
                    if int(out_pid.value) in target_pids:
                        PostMessageW(hwnd, WM_CLOSE, 0, 0)
                except Exception:
                    pass
                return True
            EnumWindows(enum_proc, 0)
            time.sleep(0.12)
            for target_pid in sorted(target_pids):
                try:
                    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "timeout": 2}
                    if os.name == "nt":
                        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    subprocess.run(["taskkill", "/PID", str(int(target_pid)), "/T", "/F"], **kwargs)
                except Exception:
                    pass
        except Exception as exc:
            try: self.log("tiktok", "close login window failed", exc)
            except Exception: pass

    def _close_tiktok_browser_windows(self) -> None:
        try:
            s = self.settings()
            tt = s.setdefault("platforms", {}).setdefault("tiktok", {})
            for account in ("main", "bot"):
                profile = self._tiktok_profile_dir(tt, account)
                port_key = "bot_remote_debug_port" if account == "bot" else "remote_debug_port"
                try:
                    port = int(tt.get(port_key) or (9230 if account == "bot" else 9229))
                except Exception:
                    port = 9230 if account == "bot" else 9229
                self._close_tiktok_login_windows(profile_dir=profile, port=port)
        except Exception as exc:
            try: self.log("tiktok", "close browser windows failed", exc)
            except Exception: pass

    def _mark_tiktok_login_ok(self, account: str, ok: bool = True):
        account = "bot" if str(account or "").lower().strip() == "bot" else "main"
        try:
            s = self.settings()
            tt = s.setdefault("platforms", {}).setdefault("tiktok", {})
            tt["bot_login_ok" if account == "bot" else "main_login_ok"] = bool(ok)
            if ok:
                tt["bot_disconnected_at" if account == "bot" else "main_disconnected_at"] = 0
            self.save_settings(s)
        except Exception as exc:
            try: self.log("tiktok", "mark login failed", account, exc)
            except Exception: pass

    def _monitor_tiktok_login_success(self, account: str, pid: int = 0, profile_dir: Path | None = None, port: int | None = None):
        """Wait until the selected profile has real TikTok session cookies, then close the login popup."""
        account = "bot" if str(account or "").lower().strip() == "bot" else "main"
        deadline = time.time() + 600.0
        # Give Chromium time to create and flush the cookie DB.
        time.sleep(2.0)
        while time.time() < deadline and not self.shutting_down:
            try:
                s = self.settings()
                tt = s.setdefault("platforms", {}).setdefault("tiktok", {})
                ok, detail = self._tiktok_account_status_raw(tt, account)
                if ok:
                    tt["bot_login_ok" if account == "bot" else "main_login_ok"] = True
                    self.save_settings(s)
                    self.log("tiktok", f"{account} login detected", detail)
                    time.sleep(1.0)
                    self._close_tiktok_login_windows(pid=pid, profile_dir=profile_dir, port=port)
                    return
            except Exception as exc:
                try: self.log("tiktok", "monitor failed", account, exc)
                except Exception: pass
            time.sleep(2.0)


    def _tiktok_cookie_db_candidates(self, profile_dir: Path):
        return [
            profile_dir / "Default" / "Network" / "Cookies",
            profile_dir / "Default" / "Cookies",
            profile_dir / "Network" / "Cookies",
            profile_dir / "Cookies",
        ]

    def _tiktok_cookie_names(self, profile_dir: Path):
        names = set()
        now = time.time()
        for db in self._tiktok_cookie_db_candidates(profile_dir):
            rows = []
            db_key = str(db)
            try:
                if now < float(self._tiktok_cookie_backoff.get(db_key, 0.0) or 0.0):
                    continue
            except Exception:
                pass
            try:
                if not db.exists() or db.stat().st_size <= 0:
                    continue
                tmp = Path(tempfile.gettempdir()) / ("gla_tiktok_cookies_" + secrets.token_hex(6) + ".sqlite")
                try:
                    shutil.copy2(db, tmp)
                    con = sqlite3.connect(str(tmp))
                    try:
                        rows = con.execute("select host_key,name from cookies where host_key like ?", ("%tiktok%",)).fetchall()
                    finally:
                        con.close()
                finally:
                    try: tmp.unlink(missing_ok=True)
                    except Exception: pass
            except Exception as exc:
                try:
                    uri = db.resolve().as_uri() + "?mode=ro"
                    con = sqlite3.connect(uri, uri=True, timeout=1)
                    try:
                        rows = con.execute("select host_key,name from cookies where host_key like ?", ("%tiktok%",)).fetchall()
                    finally:
                        con.close()
                except Exception:
                    msg = str(exc)
                    if "WinError 32" in msg or "being used by another process" in msg or "Der Prozess kann nicht auf die Datei zugreifen" in msg:
                        self._tiktok_cookie_backoff[db_key] = time.time() + 45.0
                        if db_key not in self._tiktok_cookie_warned:
                            self._tiktok_cookie_warned.add(db_key)
                            try: self.log("tiktok", "cookie DB locked; delaying next read", str(db))
                            except Exception: pass
                    else:
                        try: self.log("tiktok", "cookie read failed", str(db), exc)
                        except Exception: pass
            for host, name in rows:
                if host and name:
                    names.add(str(name))
        return names

    def _tiktok_account_status_raw(self, cfg, account):
        profile = self._tiktok_profile_dir(cfg, account)
        try:
            names = self._tiktok_cookie_names(profile)
            # Wichtig: TikTok setzt Tracking-/Besucher-Cookies wie ttwid schon auf der Loginseite.
            # Die dürfen NICHT als verbunden zählen, sonst wird der Status grün, obwohl der QR-/Account-Login
            # abgebrochen wurde. Verbunden ist der Account erst bei echten Session-/User-Cookies.
            strong = {"sessionid", "sessionid_ss", "sid_tt", "uid_tt", "uid_tt_ss", "sid_guard", "passport_csrf_token"}
            if names.intersection(strong):
                return True, "Login-Cookies gespeichert"
            return False, "noch kein echter TikTok-Login im Profil gefunden"
        except Exception as exc:
            return False, "TikTok-Profil nicht lesbar: " + str(exc)

    def tiktok_account_status(self, cfg, account):
        account = "bot" if str(account or "").lower().strip() == "bot" else "main"
        # Wenn ein Login einmal sauber erkannt wurde, bleibt der Status erhalten,
        # solange der Nutzer nicht explizit trennt. Dadurch muss die gesperrte
        # Chromium-Cookie-DB nicht dauerhaft im UI-Polling gelesen werden.
        sticky_key = "bot_login_ok" if account == "bot" else "main_login_ok"
        profile = self._tiktok_profile_dir(cfg, account)
        if bool((cfg or {}).get(sticky_key)) and profile.exists():
            return True, "Login gespeichert"
        ok, detail = self._tiktok_account_status_raw(cfg, account)
        if ok:
            return True, detail
        return False, detail

    def tiktok_status(self, cfg):
        main_ok, main_detail = self.tiktok_account_status(cfg, "main")
        bot_ok, bot_detail = self.tiktok_account_status(cfg, "bot")
        if main_ok and bot_ok:
            return True, "Main OK · Bot OK"
        if main_ok:
            return False, "Main OK · Bot fehlt"
        if bot_ok:
            return False, "Bot OK · Main fehlt"
        return False, "Main fehlt · Bot fehlt"

    def open_tiktok_login(self, account):
        account = "bot" if str(account or "").lower().strip() == "bot" else "main"
        s = self.settings()
        cfg = s.setdefault("platforms", {}).setdefault("tiktok", {})
        cfg["enabled"] = True
        profile_dir = self._tiktok_profile_dir(cfg, account)
        profile_dir.mkdir(parents=True, exist_ok=True)
        port_key = "bot_remote_debug_port" if account == "bot" else "remote_debug_port"
        try:
            port = int(cfg.get(port_key) or (9230 if account == "bot" else 9229))
        except Exception:
            port = 9230 if account == "bot" else 9229
        url = "https://www.tiktok.com/login"
        browser = self._find_browser_exe(cfg)
        if browser:
            # Like the other platform logins: open a clean, fixed-size login window instead of a random full browser tab.
            # --app keeps the stored TikTok profile/cookies but makes the QR login window much cleaner.
            args = [
                browser,
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={port}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1000,800",
                "--window-position=140,80",
                "--new-window",
                f"--app={url}",
            ]
            popen_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
            if os.name == "nt":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 1
                popen_kwargs["startupinfo"] = si
            proc = subprocess.Popen(args, **popen_kwargs)
            threading.Thread(target=self._bring_windows_to_front, kwargs={"pid": proc.pid, "profile_dir": profile_dir, "port": port, "title_hint": "TikTok"}, daemon=True).start()
            threading.Thread(target=self._monitor_tiktok_login_success, kwargs={"account": account, "pid": proc.pid, "profile_dir": profile_dir, "port": port}, daemon=True).start()
        else:
            # Fallback speichert Cookies im Standardbrowserprofil, aber öffnet wenigstens die Loginseite.
            webbrowser.open(url, new=1)
        cfg["last_login_account"] = account
        cfg["last_login_opened_at"] = time.time()
        cfg["main_profile_dir"] = str(self._tiktok_profile_dir(cfg, "main"))
        cfg["bot_profile_dir"] = str(self._tiktok_profile_dir(cfg, "bot"))
        s["platforms"]["tiktok"] = cfg
        self.save_settings(s)
        return {"ok": True, "account": account, "profile_dir": str(profile_dir), "debug_port": port, "browser": browser or "default"}

    def save_settings(self, s):
        s["version"] = VERSION
        _json_save(self.settings_path, s)

    def _oauth_access_needs_refresh(self, cfg: dict, account: str) -> bool:
        account = "main" if str(account or "").lower().strip() == "main" else "bot"
        prefix = "main_" if account == "main" else ""
        access = str(cfg.get(prefix + "access_token") or "").strip()
        refresh = str(cfg.get(prefix + "refresh_token") or "").strip()
        if not refresh:
            return False
        if not access:
            return True
        try:
            expires_at = float(cfg.get(prefix + "expires_at") or 0)
            if expires_at and time.time() >= expires_at - 90:
                return True
        except Exception:
            pass
        try:
            saved_at = float(cfg.get(prefix + "saved_at") or 0)
            if not cfg.get(prefix + "expires_at") and (not saved_at or time.time() - saved_at > 3300):
                return True
        except Exception:
            if not cfg.get(prefix + "expires_at"):
                return True
        return False

    def _oauth_refresh_payload(self, platform: str, cfg: dict, account: str) -> dict:
        account = "main" if str(account or "").lower().strip() == "main" else "bot"
        prefix = "main_" if account == "main" else ""
        refresh = str(cfg.get(prefix + "refresh_token") or "").strip()
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        payload = {"grant_type": "refresh_token", "refresh_token": refresh}
        if client_id:
            payload["client_id"] = client_id
        if client_secret:
            payload["client_secret"] = client_secret
        return payload

    def _save_refreshed_oauth(self, platform: str, account: str, cfg: dict, token: dict) -> dict:
        account = "main" if str(account or "").lower().strip() == "main" else "bot"
        prefix = "main_" if account == "main" else ""
        access = self._clean_token(token.get("access_token"))
        if not access:
            return cfg
        refresh = str(token.get("refresh_token") or cfg.get(prefix + "refresh_token") or "").strip()
        try:
            expires_in = float(token.get("expires_in") or cfg.get(prefix + "expires_in") or 0)
        except Exception:
            expires_in = 0.0
        expires_at = time.time() + expires_in if expires_in > 0 else cfg.get(prefix + "expires_at")
        scope = str(token.get("scope") or cfg.get("main_scopes" if account == "main" else "scopes") or cfg.get(prefix + "scope") or "").strip()
        saved_at = time.time()

        auth_token = dict(token or {})
        auth_token.update({
            "platform": platform,
            "account": account,
            "access_token": access,
            "refresh_token": refresh,
            "saved_at": saved_at,
        })
        if expires_in:
            auth_token["expires_in"] = expires_in
        if expires_at:
            auth_token["expires_at"] = expires_at
        if scope:
            auth_token["scope"] = scope
        _json_save(self.auth_dir / f"{platform}_{account}.json", auth_token)

        cfg[prefix + "access_token"] = access
        cfg[prefix + "refresh_token"] = refresh
        cfg[prefix + "saved_at"] = saved_at
        if expires_in:
            cfg[prefix + "expires_in"] = expires_in
        if expires_at:
            cfg[prefix + "expires_at"] = expires_at
        if account == "main":
            if scope:
                cfg["main_scopes"] = scope
            cfg["main_disconnected_at"] = 0
        else:
            if scope:
                cfg["scopes"] = scope
            cfg["bot_access_token"] = access
            cfg["bot_refresh_token"] = refresh
            cfg["bot_disconnected_at"] = 0

        s = self.settings()
        live_cfg = s.setdefault("platforms", {}).setdefault(platform, {})
        live_cfg.update({k: v for k, v in cfg.items() if k in {
            "access_token", "refresh_token", "saved_at", "expires_at", "expires_in",
            "main_access_token", "main_refresh_token", "main_saved_at", "main_expires_at", "main_expires_in",
            "bot_access_token", "bot_refresh_token", "scopes", "main_scopes",
            "main_disconnected_at", "bot_disconnected_at",
        }})
        self.save_settings(s)
        return cfg

    def refresh_platform_oauth(self, platform: str, cfg: dict) -> dict:
        platform = str(platform or "").lower().strip()
        cfg = dict(cfg or {})
        if platform not in {"twitch", "youtube", "kick"}:
            return cfg
        for account in ("main", "bot"):
            if bool(cfg.get("main_disconnected_at" if account == "main" else "bot_disconnected_at")):
                continue
            if not self._oauth_access_needs_refresh(cfg, account):
                continue
            payload = self._oauth_refresh_payload(platform, cfg, account)
            if not payload.get("refresh_token"):
                continue
            try:
                token = self._http_json(TOKEN_URLS[platform], data=payload, method="POST", timeout=20)
                cfg = self._save_refreshed_oauth(platform, account, cfg, token)
                self.log(platform, f"{account} OAuth refreshed for autoconnect")
            except Exception as exc:
                self.log(platform, f"{account} OAuth refresh failed", exc)
        return cfg

    def _disconnect_account_settings(self, settings: dict, platform: str, account: str) -> None:
        platform = str(platform or "").lower().strip()
        account = "bot" if str(account or "").lower().strip() == "bot" else "main"
        cfg = settings.setdefault("platforms", {}).setdefault(platform, {})
        if not isinstance(cfg, dict):
            settings["platforms"][platform] = {}
            cfg = settings["platforms"][platform]
        now = int(time.time())

        if platform == "openai":
            for key in ("api_key", "organization", "project", "status", "detail", "connection_status"):
                cfg[key] = ""
            cfg["main_disconnected_at"] = now
            return

        if platform == "tiktok":
            cfg["bot_login_ok" if account == "bot" else "main_login_ok"] = False
            cfg["bot_disconnected_at" if account == "bot" else "main_disconnected_at"] = now
            cfg["last_login_account"] = ""
            return

        if platform == "spotify":
            for key in ("access_token", "refresh_token", "saved_at", "expires_at", "expires_in", "scope", "scopes", "token_type", "connection_status", "status", "detail"):
                cfg[key] = ""
            cfg["main_disconnected_at"] = now
            return

        if account == "main":
            for key in (
                "main_access_token", "main_refresh_token", "main_saved_at", "main_expires_at", "main_expires_in",
                "main_token_type", "main_oauth_login", "main_oauth_user_id", "main_connection_status",
                "main_channel_id", "main_channel_title", "main_channel_custom_url", "main_user_id", "main_username",
                "broadcaster_user_id", "broadcaster_id", "broadcaster_channel_id", "channel_id",
            ):
                cfg[key] = ""
            cfg["main_disconnected_at"] = now
        else:
            for key in (
                "access_token", "refresh_token", "bot_access_token", "bot_refresh_token", "saved_at", "expires_at",
                "expires_in", "token_type", "oauth_login", "oauth_user_id", "connection_status",
                "bot_user_id", "bot_username", "username", "bot_channel_id", "bot_channel_title",
                "bot_channel_custom_url",
            ):
                cfg[key] = ""
            cfg["bot_disconnected_at"] = now
        cfg["status"] = "nicht verbunden"
        cfg["detail"] = "getrennt"

    def _settings_token_snapshot(self, platform: str, account: str, cfg: dict | None = None) -> dict:
        """Build a canonical auth-file-shaped token from platform settings.

        This is the safety net for new builds: if settings.json survived but
        data/auth/*.json is missing, the app can recreate the auth files and
        plugins can autoconnect without forcing a fresh OAuth login.
        """
        cfg = cfg if isinstance(cfg, dict) else {}
        platform = str(platform or "").lower().strip()
        account = "main" if str(account or "").lower().strip() == "main" else "bot"
        if bool(cfg.get("main_disconnected_at" if account == "main" else "bot_disconnected_at")):
            return {}
        prefix = "" if (platform == "spotify" or account == "bot") else "main_"
        access = str(cfg.get(prefix + "access_token") or "").strip()
        refresh = str(cfg.get(prefix + "refresh_token") or "").strip()
        if not access and not refresh:
            return {}
        token = {"platform": platform, "account": account}
        if access:
            token["access_token"] = access
        if refresh:
            token["refresh_token"] = refresh
        for key in ("expires_in", "expires_at", "scope", "token_type", "saved_at"):
            value = cfg.get(prefix + key)
            if value not in (None, ""):
                token[key] = value
        if "scope" not in token:
            scopes_key = "main_scopes" if account == "main" else "scopes"
            scopes = str(cfg.get(scopes_key) or DEFAULT_SCOPES.get(platform, {}).get(account) or DEFAULT_SCOPES.get(platform, {}).get("main") or "").strip()
            if scopes:
                token["scope"] = scopes
        if "saved_at" not in token:
            token["saved_at"] = time.time()
        return token

    def _ensure_auth_files_from_settings(self, settings: dict | None = None) -> None:
        """Recreate missing data/auth token files from settings.json tokens.

        Builds should preserve data/auth, but in practice users often copy only
        the source package or rebuild into a fresh dist. Since OAuth callbacks
        also mirror tokens into data/settings.json, this makes existing auth
        portable across builds and prevents unnecessary re-auth.
        """
        try:
            settings = settings if isinstance(settings, dict) else _json_load(self.settings_path, {})
            platforms = settings.get("platforms", {}) if isinstance(settings.get("platforms", {}), dict) else {}
            for platform in ("twitch", "youtube", "kick"):
                cfg = platforms.get(platform, {}) if isinstance(platforms.get(platform, {}), dict) else {}
                for account in ("main", "bot"):
                    path = self.auth_dir / f"{platform}_{account}.json"
                    existing = _json_load(path, {})
                    if isinstance(existing, dict) and str(existing.get("access_token") or existing.get("refresh_token") or "").strip():
                        continue
                    token = self._settings_token_snapshot(platform, account, cfg)
                    if token:
                        _json_save(path, token)
            cfg = platforms.get("spotify", {}) if isinstance(platforms.get("spotify", {}), dict) else {}
            path = self.auth_dir / "spotify_main.json"
            existing = _json_load(path, {})
            if not (isinstance(existing, dict) and str(existing.get("access_token") or existing.get("refresh_token") or "").strip()):
                token = self._settings_token_snapshot("spotify", "main", cfg)
                if token:
                    _json_save(path, token)
        except Exception as exc:
            try:
                self.log("auth", "settings auth restore failed", exc)
            except Exception:
                pass

    def _auth_token_ok(self, platform, account="main") -> bool:
        try:
            platform = str(platform or "").lower().strip()
            account = "main" if str(account or "").lower().strip() == "main" else "bot"
            token = _json_load(self.auth_dir / f"{platform}_{account}.json", {})
            if isinstance(token, dict) and bool(str(token.get("access_token") or token.get("refresh_token") or "").strip()):
                return True
            s = self.settings()
            cfg = s.get("platforms", {}).get(platform, {}) if isinstance(s.get("platforms", {}), dict) else {}
            restored = self._settings_token_snapshot(platform, account, cfg)
            if restored:
                _json_save(self.auth_dir / f"{platform}_{account}.json", restored)
                return True
        except Exception:
            return False
        return False

    def platform_status(self, platform, account="main"):
        return "verbunden" if self._auth_token_ok(platform, account) else "nicht verbunden"

    def _plugin_connected_detail(self, plugin_id: str) -> tuple[bool, str]:
        try:
            ps = self.plugin_status.get(plugin_id, {}) or {}
            state = str(ps.get("state") or "").strip().lower()
            msg = str(ps.get("message") or "").strip()
            if state in {"connected", "running"}:
                plugin = self.plugin_instances.get(plugin_id)
                checker = getattr(plugin, "is_connected", None) if plugin is not None else None
                if callable(checker):
                    try:
                        if not bool(checker()):
                            return False, msg or "Plugin meldet nicht verbunden"
                    except Exception:
                        return False, msg or "Pluginstatus nicht pruefbar"
                return True, msg or "Plugin verbunden"
            return False, msg
        except Exception:
            return False, ""

    def _plugin_active_account(self, plugin_id: str) -> str:
        try:
            plugin = self.plugin_instances.get(plugin_id)
            if plugin is None:
                return ""
            value = str(getattr(plugin, "_active_account", "") or "").strip().lower()
            if value in {"main", "bot"}:
                return value
            return ""
        except Exception:
            return ""

    def _account_auth_stamp(self, platform: str, account: str, cfg: dict | None = None) -> float:
        try:
            platform = str(platform or "").lower().strip()
            account = "main" if str(account or "").lower().strip() == "main" else "bot"
            cfg = cfg if isinstance(cfg, dict) else {}
            token = _json_load(self.auth_dir / f"{platform}_{account}.json", {})
            values = []
            if isinstance(token, dict):
                values.extend([token.get("saved_at"), token.get("updated_at"), token.get("created_at")])
            prefix = "main_" if account == "main" else ""
            values.extend([cfg.get(prefix + "saved_at"), cfg.get(prefix + "updated_at"), cfg.get(prefix + "created_at")])
            for value in values:
                try:
                    stamp = float(value or 0.0)
                    if stamp > 0:
                        return stamp
                except Exception:
                    pass
            path = self.auth_dir / f"{platform}_{account}.json"
            return float(path.stat().st_mtime) if path.exists() else 0.0
        except Exception:
            return 0.0

    def _set_visible_saved_account(self, cfg: dict, platform: str) -> str:
        main_ok = self.platform_status(platform, "main") == "verbunden"
        bot_ok = self.platform_status(platform, "bot") == "verbunden"
        active = ""
        if main_ok and bot_ok:
            main_stamp = self._account_auth_stamp(platform, "main", cfg)
            bot_stamp = self._account_auth_stamp(platform, "bot", cfg)
            active = "bot" if bot_stamp > main_stamp else "main"
        elif main_ok:
            active = "main"
        elif bot_ok:
            active = "bot"
        cfg["main_status"] = "verbunden" if active == "main" else "nicht verbunden"
        cfg["bot_status"] = "verbunden" if active == "bot" else "nicht verbunden"
        return active

    def _set_visible_active_account(self, cfg: dict, plugin_id: str, platform: str) -> None:
        active = self._plugin_active_account(plugin_id)
        if not active and platform == "tiktok":
            active = "bot" if bool(cfg.get("bot_login_ok")) else "main" if bool(cfg.get("main_login_ok")) else ""
        if not active:
            self._set_visible_saved_account(cfg, platform)
            return
        cfg["main_status"] = "verbunden" if active == "main" else "nicht verbunden"
        cfg["bot_status"] = "verbunden" if active == "bot" else "nicht verbunden"

    def _log_line_ts(self, line: str) -> float:
        try:
            head = str(line or "")[:19]
            return time.mktime(time.strptime(head, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            return 0.0

    def _recent_auth_error(self, platform: str, *, lines=220, since_ts: float = 0.0) -> str:
        try:
            if not self.log_file.exists():
                return ""
            txt = self.log_file.read_text(encoding="utf-8", errors="replace")
            tail = txt.splitlines()[-int(lines):]
            needle = platform.lower()
            since_ts = float(since_ts or 0.0)
            for line in reversed(tail):
                low = line.lower()
                if needle not in low:
                    continue
                line_ts = self._log_line_ts(line)
                if since_ts and line_ts and line_ts <= since_ts:
                    # Alles davor gehört zu einem älteren Auth-Stand. Alte Bad-Request-Zeilen
                    # dürfen nach erneutem OAuth nicht mehr den aktuellen Status rot färben.
                    return ""
                if any(x in low for x in ("status | connected", "using valid cached authorization", "refreshed token", "oauth ok", "oauth gespeichert", "current playback ok")):
                    return ""
                if any(x in low for x in ("token failed", "auth failed", "oauth failed", "http error 400", "http error 401", "http error 403", "bad request", "unauthorized", "forbidden")):
                    return line.split(" | ", 2)[-1].strip()
        except Exception:
            return ""
        return ""

    def _spotify_status_legacy_token_only(self, cfg: dict) -> tuple[bool, str]:
        try:
            cfg = cfg if isinstance(cfg, dict) else {}
            token = _json_load(self.auth_dir / "spotify_main.json", {})
            if not isinstance(token, dict):
                token = {}
            saved_at = float(token.get("saved_at") or cfg.get("saved_at") or 0.0)
            has_access = bool(str(token.get("access_token") or cfg.get("access_token") or "").strip())
            has_refresh = bool(str(token.get("refresh_token") or cfg.get("refresh_token") or "").strip())
            err = self._recent_auth_error("spotify", since_ts=saved_at)
            if err and not has_access:
                return False, err
            if has_access or has_refresh:
                if err:
                    # Refresh kann fehlschlagen, während der gerade neu gesetzte Access-Token
                    # trotzdem funktioniert. Der Status darf dann nicht an einer alten Logzeile kleben.
                    return True, "OAuth gespeichert · letzter Refresh-Hinweis: " + err
                detail = str(cfg.get("connection_status") or "OAuth gespeichert").strip()
                try:
                    np_candidates = [
                        self.data / "spotis3mptify" / "nowplaying" / "nowplaying.json",
                        self.data / "spotis3mptify" / "nowplaying.json",
                    ]
                    newest = max((p.stat().st_mtime for p in np_candidates if p.exists()), default=0.0)
                    if newest and time.time() - newest < 180:
                        detail = "Verbunden · Songinfos kommen rein"
                except Exception:
                    pass
                return True, detail
            return False, "kein Spotify OAuth gespeichert"
        except Exception as exc:
            return False, "Spotify Statusfehler: " + str(exc)

    def spotify_status(self, cfg: dict) -> tuple[bool, str]:
        try:
            cfg = cfg if isinstance(cfg, dict) else {}
            token = _json_load(self.auth_dir / "spotify_main.json", {})
            if not isinstance(token, dict):
                token = {}
            access = str(token.get("access_token") or cfg.get("access_token") or "").strip()
            refresh = str(token.get("refresh_token") or cfg.get("refresh_token") or "").strip()
            client_id = str(cfg.get("client_id") or "").strip()
            client_secret = str(cfg.get("client_secret") or "").strip()
            key = (
                hashlib.sha256(access.encode("utf-8")).hexdigest()[:12] if access else "",
                hashlib.sha256(refresh.encode("utf-8")).hexdigest()[:12] if refresh else "",
                client_id,
            )
            cache = self._spotify_status_cache
            now = time.time()
            if cache.get("key") == key and now - float(cache.get("ts") or 0.0) < 10.0:
                return bool(cache.get("ok")), str(cache.get("detail") or "nicht verbunden")
            if not access and not refresh:
                detail = "kein Spotify OAuth gespeichert"
                self._spotify_status_cache = {"ts": now, "ok": False, "detail": detail, "key": key}
                return False, detail
            if not access and refresh and client_id and client_secret:
                try:
                    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
                    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh}).encode("utf-8")
                    req = urllib.request.Request(TOKEN_URLS["spotify"], data=body, method="POST")
                    req.add_header("Authorization", "Basic " + basic)
                    req.add_header("Content-Type", "application/x-www-form-urlencoded")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
                    access = str(data.get("access_token") or "").strip()
                    if access:
                        token.update({
                            "access_token": access,
                            "refresh_token": str(data.get("refresh_token") or refresh),
                            "expires_in": data.get("expires_in"),
                            "expires_at": time.time() + float(data.get("expires_in") or 3600),
                            "scope": data.get("scope") or token.get("scope") or cfg.get("scopes") or cfg.get("scope") or "",
                            "saved_at": time.time(),
                        })
                        _json_save(self.auth_dir / "spotify_main.json", token)
                        s = self.settings()
                        sp = s.setdefault("platforms", {}).setdefault("spotify", {})
                        sp.update({
                            "access_token": access,
                            "refresh_token": token.get("refresh_token") or refresh,
                            "expires_at": token.get("expires_at"),
                            "expires_in": token.get("expires_in"),
                            "scope": token.get("scope") or "",
                            "scopes": token.get("scope") or "",
                            "saved_at": token.get("saved_at"),
                        })
                        self.save_settings(s)
                except Exception as exc:
                    detail = "Spotify Refresh fehlgeschlagen: " + str(exc)
                    self._spotify_status_cache = {"ts": now, "ok": False, "detail": detail, "key": key}
                    return False, detail
            if not access:
                detail = "Spotify OAuth gespeichert, aber kein nutzbarer Access-Token"
                self._spotify_status_cache = {"ts": now, "ok": False, "detail": detail, "key": key}
                return False, detail
            try:
                req = urllib.request.Request("https://api.spotify.com/v1/me", headers={"Authorization": "Bearer " + access, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
                user = str(data.get("display_name") or data.get("id") or "Spotify").strip()
                detail = "Spotify API verbunden" + (f" als {user}" if user else "")
                self._spotify_status_cache = {"ts": now, "ok": True, "detail": detail, "key": key}
                return True, detail
            except urllib.error.HTTPError as exc:
                detail = f"Spotify API nicht verbunden: HTTP {int(getattr(exc, 'code', 0) or 0)}"
                self._spotify_status_cache = {"ts": now, "ok": False, "detail": detail, "key": key}
                return False, detail
            except Exception as exc:
                detail = "Spotify API nicht erreichbar: " + str(exc)
                self._spotify_status_cache = {"ts": now, "ok": False, "detail": detail, "key": key}
                return False, detail
        except Exception as exc:
            return False, "Spotify Statusfehler: " + str(exc)

    def live_platform_statuses(self) -> dict:
        s = self.settings()
        source = s.get("platforms", {}) if isinstance(s.get("platforms", {}), dict) else {}
        out = {}
        plugin_map = {"twitch": "twitch_chat", "tiktok": "tiktok_chat", "youtube": "youtube_chat", "kick": "kick_chat"}
        for p in PLATFORM_ORDER:
            cfg = dict(source.get(p, {}) or {})
            enabled = bool(cfg.get("enabled", False))
            cfg["enabled"] = enabled
            if not enabled:
                if p == "tiktok":
                    main_ok, _ = self.tiktok_account_status(cfg, "main")
                    bot_ok, _ = self.tiktok_account_status(cfg, "bot")
                    cfg["main_status"] = "verbunden" if main_ok else "nicht verbunden"
                    cfg["bot_status"] = "verbunden" if bot_ok else "nicht verbunden"
                    if main_ok or bot_ok:
                        cfg["status"] = "verbunden"
                        cfg["detail"] = "Main OK · Bot OK" if (main_ok and bot_ok) else "Main OK · Bot fehlt" if main_ok else "Bot OK · Main fehlt"
                        out[p] = cfg
                        continue
                cfg["status"] = "nicht verbunden"
                cfg.setdefault("detail", "inaktiv")
                out[p] = cfg
                continue

            autoconnect = bool(cfg.get("autoconnect", True))
            if not autoconnect and p in {"twitch", "tiktok", "youtube", "kick", "spotify", "meld", "obs"}:
                cfg["status"] = "nicht verbunden"
                cfg["detail"] = "Autoconnect aus"
                if p in {"twitch", "youtube", "kick"}:
                    cfg["main_status"] = self.platform_status(p, "main")
                    cfg["bot_status"] = self.platform_status(p, "bot")
                elif p == "tiktok":
                    main_ok, _ = self.tiktok_account_status(cfg, "main")
                    bot_ok, _ = self.tiktok_account_status(cfg, "bot")
                    cfg["main_status"] = "verbunden" if main_ok else "nicht verbunden"
                    cfg["bot_status"] = "verbunden" if bot_ok else "nicht verbunden"
                out[p] = cfg
                continue

            plugin_id = plugin_map.get(p)
            if plugin_id:
                plug_ok, plug_msg = self._plugin_connected_detail(plugin_id)
                if plug_ok:
                    cfg["status"] = "verbunden"
                    cfg["detail"] = plug_msg
                    if p in {"twitch", "kick", "youtube", "tiktok"}:
                        self._set_visible_active_account(cfg, plugin_id, p)
                    out[p] = cfg
                    continue

            if p == "meld":
                ok, detail = self.meld_status(cfg)
                cfg["status"] = "verbunden" if ok else "nicht verbunden"
                cfg["detail"] = detail
            elif p == "obs":
                ok, detail = self.obs_status(cfg)
                cfg["status"] = "verbunden" if ok else "nicht verbunden"
                cfg["detail"] = detail
            elif p == "tiktok":
                main_ok, _ = self.tiktok_account_status(cfg, "main")
                bot_ok, _ = self.tiktok_account_status(cfg, "bot")
                cfg["main_status"] = "verbunden" if main_ok else "nicht verbunden"
                cfg["bot_status"] = "verbunden" if bot_ok else "nicht verbunden"
                cfg["status"] = "verbunden" if (main_ok or bot_ok) else "nicht verbunden"
                cfg["detail"] = "Main OK · Bot OK" if (main_ok and bot_ok) else "Main OK · Bot fehlt" if main_ok else "Bot OK · Main fehlt" if bot_ok else "Main fehlt · Bot fehlt"
            elif p == "youtube":
                main_saved = self._auth_token_ok("youtube", "main") or bool(str(cfg.get("main_access_token") or cfg.get("main_refresh_token") or "").strip())
                bot_saved = self._auth_token_ok("youtube", "bot") or bool(str(cfg.get("access_token") or cfg.get("refresh_token") or "").strip())
                if main_saved or bot_saved:
                    ok = True
                    active = "Bot" if bot_saved else "Main"
                    detail = f"{active} OAuth gespeichert"
                else:
                    ok, detail = self.youtube_status(cfg)
                cfg["status"] = "verbunden" if ok else "nicht verbunden"
                cfg["detail"] = detail
                self._set_visible_saved_account(cfg, p)
            elif p == "spotify":
                ok, detail = self.spotify_status(cfg)
                cfg["status"] = "verbunden" if ok else "nicht verbunden"
                cfg["detail"] = detail
            elif p == "openai":
                ok, detail = self.openai_status(cfg, force=False)
                cfg["status"] = "verbunden" if ok else "nicht verbunden"
                cfg["detail"] = detail
                cfg.pop("model", None)
                cfg.pop("api_key", None)
            else:
                active = self._set_visible_saved_account(cfg, p)
                cfg["status"] = "verbunden" if active else "nicht verbunden"
                cfg["detail"] = ("Bot OAuth gespeichert" if active == "bot" else "Main OAuth gespeichert") if active else "kein OAuth gespeichert"
            out[p] = cfg
        return out

    def _sync_youtube_auth_files(self, cfg: dict) -> bool:
        changed = False
        for account, main in (("main", True), ("bot", False)):
            token = _json_load(self.auth_dir / f"youtube_{account}.json", {})
            if not isinstance(token, dict):
                continue
            mapping = {
                "main_access_token" if main else "access_token": token.get("access_token"),
                "main_refresh_token" if main else "refresh_token": token.get("refresh_token"),
                "main_saved_at" if main else "saved_at": token.get("saved_at"),
                "main_scopes" if main else "scopes": token.get("scope"),
            }
            for key, value in mapping.items():
                if value not in (None, "") and cfg.get(key) != value:
                    cfg[key] = value
                    changed = True
        return changed

    def youtube_status(self, cfg: dict) -> tuple[bool, str]:
        """Validate YouTube OAuth like the original tool, but gently for the web dashboard.

        YouTube has no local persistent socket like OBS/Meld. The useful check is:
        Access token still valid? If not, refresh token available and refresh works?
        Once a valid token was seen, the dashboard stops polling just like Meld/OBS.
        """
        try:
            cfg = cfg if isinstance(cfg, dict) else {}
            if not bool(cfg.get("enabled", True)):
                self._youtube_status_cache = {"ts": time.time(), "ok": False, "detail": "deaktiviert", "locked": False, "key": None}
                return False, "deaktiviert"
            if self._sync_youtube_auth_files(cfg):
                try:
                    s = self.settings()
                    s.setdefault("platforms", {}).setdefault("youtube", {}).update(cfg)
                    self.save_settings(s)
                except Exception as exc:
                    self.log("youtube", "auth file sync failed", exc)
            client_id = str(cfg.get("client_id") or "").strip()
            key = (
                bool(cfg.get("enabled", True)),
                bool(cfg.get("autoconnect", False)),
                client_id,
                bool(str(cfg.get("access_token") or "").strip()),
                bool(str(cfg.get("refresh_token") or "").strip()),
                bool(str(cfg.get("main_access_token") or "").strip()),
                bool(str(cfg.get("main_refresh_token") or "").strip()),
            )
            cache = self._youtube_status_cache
            if cache.get("locked") and cache.get("key") == key:
                return True, str(cache.get("detail") or "YouTube verbunden")
            now = time.time()
            if cache.get("key") == key and (now - float(cache.get("ts") or 0.0)) < 10.0:
                return bool(cache.get("ok")), str(cache.get("detail") or "nicht verbunden")

            if not client_id:
                detail = "YouTube Client ID fehlt"
                self._youtube_status_cache = {"ts": now, "ok": False, "detail": detail, "locked": False, "key": key}
                return False, detail

            changed = False
            main_ok, main_detail, main_updates = _youtube_check_account(cfg, main=True)
            bot_ok, bot_detail, bot_updates = _youtube_check_account(cfg, main=False)
            if main_updates:
                cfg.update(main_updates)
                changed = True
            if bot_updates:
                cfg.update(bot_updates)
                changed = True
            if changed:
                try:
                    s = self.settings()
                    s.setdefault("platforms", {}).setdefault("youtube", {}).update(cfg)
                    self.save_settings(s)
                except Exception as exc:
                    self.log("youtube", "settings save failed", exc)

            if main_ok and bot_ok:
                detail = f"Main OK · Bot OK"
            elif main_ok:
                detail = f"Main OK · Bot fehlt/ungültig: {bot_detail}"
            elif bot_ok:
                detail = f"Bot OK · Main fehlt/ungültig: {main_detail}"
            else:
                detail = f"Main: {main_detail} · Bot: {bot_detail}"
            main_saved = bool(str(cfg.get("main_access_token") or cfg.get("main_refresh_token") or "").strip())
            bot_saved = bool(str(cfg.get("access_token") or cfg.get("refresh_token") or "").strip())
            if not main_ok and main_saved:
                main_ok = True
            if not bot_ok and bot_saved:
                bot_ok = True
            if main_ok and bot_ok:
                detail = "Main OK · Bot OK"
            elif main_ok:
                detail = "Main OK · Bot fehlt"
            elif bot_ok:
                detail = "Bot OK · Main fehlt"
            ok = bool(main_ok or bot_ok)
            # Sobald YouTube einmal über gültigen/aktualisierten OAuth erkannt wurde,
            # bleibt der Dashboard-Status stehen und es wird nicht weiter gepollt.
            self._youtube_status_cache = {"ts": now, "ok": ok, "detail": detail, "locked": bool(ok), "key": key}
            return ok, detail
        except Exception as exc:
            detail = f"YouTube nicht verbunden: {exc}"
            self._youtube_status_cache = {"ts": time.time(), "ok": False, "detail": detail, "locked": False, "key": None}
            return False, detail

    def openai_status(self, cfg: dict, force=False) -> tuple[bool, str]:
        cfg = cfg if isinstance(cfg, dict) else {}
        if not bool(cfg.get("enabled", False)):
            self._openai_status_cache = {"ts": time.time(), "ok": False, "detail": "deaktiviert", "locked": False, "key": None, "models": []}
            return False, "deaktiviert"

        api_key = str(cfg.get("api_key") or "").strip()
        organization = str(cfg.get("organization") or "").strip()
        project = str(cfg.get("project") or "").strip()
        key_fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16] if api_key else ""
        cache_key = (key_fingerprint, organization, project)
        if not api_key:
            detail = "OpenAI API-Key fehlt"
            self._openai_status_cache = {"ts": time.time(), "ok": False, "detail": detail, "locked": False, "key": cache_key, "models": []}
            return False, detail

        cache = self._openai_status_cache
        now = time.time()
        if not force and cache.get("locked") and cache.get("key") == cache_key:
            return True, str(cache.get("detail") or "OpenAI API verbunden")
        if not force and cache.get("key") == cache_key and now - float(cache.get("ts") or 0.0) < 10.0:
            return bool(cache.get("ok")), str(cache.get("detail") or "nicht verbunden")

        ok, detail, models = _check_openai_api(api_key, organization, project)
        self._openai_status_cache = {"ts": now, "ok": ok, "detail": detail, "locked": bool(ok), "key": cache_key, "models": models}
        return ok, detail

    def openai_models(self, cfg: dict, force=False) -> tuple[bool, str, list[str]]:
        ok, detail = self.openai_status(cfg, force=force)
        models = self._openai_status_cache.get("models") if isinstance(self._openai_status_cache, dict) else []
        return ok, detail, list(models or [])

    def plugin_enabled(self, plugin_id: str) -> bool:
        try:
            s = self.settings()
            platforms = s.get("platforms", {}) if isinstance(s.get("platforms", {}), dict) else {}
            platform_for_plugin = {"twitch_chat": "twitch", "tiktok_chat": "tiktok", "youtube_chat": "youtube", "kick_chat": "kick"}.get(plugin_id)
            if platform_for_plugin:
                pdata = platforms.get(platform_for_plugin, {}) if isinstance(platforms.get(platform_for_plugin, {}), dict) else {}
                # Core platform switch is the source of truth for chat plugins.
                # Old plugin-local enabled=false values must not block autoconnect.
                return bool(pdata.get("enabled", False)) and bool(pdata.get("autoconnect", True))
            if plugin_id == "spotis3mptify":
                spotify = platforms.get("spotify", {}) if isinstance(platforms.get("spotify", {}), dict) else {}
                # Same rule: Spotify page controls Spotis3mptify autostart.
                return bool(spotify.get("enabled", False)) and bool(spotify.get("autoconnect", True))
            pcfg = s.setdefault("plugins", {}).setdefault(plugin_id, {})
            if plugin_id == "bridg3alot" and "enabled" not in pcfg:
                return any(bool(platforms.get(key, {}).get("enabled", False)) for key in ("twitch", "tiktok", "youtube", "kick"))
            if plugin_id == "modalot" and "enabled" not in pcfg:
                return any(bool(platforms.get(key, {}).get("enabled", False)) for key in ("twitch", "youtube", "kick"))
            return bool(pcfg.get("enabled", False))
        except Exception:
            return False

    def plugin_settings(self, plugin_id: str, plugin=None) -> dict:
        data_cfg_path = self.data / plugin_id / "settings.json"
        cfg = {}
        try:
            if plugin is not None and hasattr(plugin, "default_settings"):
                defaults = plugin.default_settings()
                if isinstance(defaults, dict):
                    cfg.update(defaults)
        except Exception:
            pass
        try:
            stored = _json_load(data_cfg_path, {})
            if isinstance(stored, dict):
                cfg.update(stored)
        except Exception:
            pass
        try:
            if plugin_id == "tiktok_chat":
                legacy = self.settings().get("plugins", {}).get("tiktok_live", {})
                if isinstance(legacy, dict):
                    cfg.update(legacy)
            in_main = self.settings().get("plugins", {}).get(plugin_id, {})
            if isinstance(in_main, dict):
                cfg.update(in_main)
        except Exception:
            pass
        if plugin_id in CHAT_PLATFORM_PLUGINS.values():
            cfg.setdefault("metrics_poll_seconds", "20")
            cfg["viewer_count_enabled"] = True
        if plugin_id == "twitch_chat":
            cfg.setdefault("viewer_join_alerts", True)
        return cfg

    def plugin_list(self):
        try:
            return self.plugin_manager.discover()
        except Exception:
            return []

    def meld_status(self, cfg: dict) -> tuple[bool, str]:
        try:
            if not bool(cfg.get("enabled", True)):
                self._meld_status_cache = {"ts": time.time(), "host": "", "port": 0, "ok": False, "detail": "deaktiviert", "locked": False}
                return False, "deaktiviert"
            if str(cfg.get("autoconnect", True)).strip().lower() in {"0", "false", "no", "off"}:
                self._meld_status_cache = {"ts": time.time(), "host": "", "port": 0, "ok": False, "detail": "Autoconnect aus", "locked": False}
                return False, "Autoconnect aus"
            host = str(cfg.get("host") or "127.0.0.1").strip() or "127.0.0.1"
            port = int(str(cfg.get("port") or 13376).strip())
            cache = self._meld_status_cache
            now = time.time()

            # Wenn Meld einmal sauber verbunden erkannt wurde, bleibt der Status stehen.
            # Danach wird nicht weiter gepollt, damit das Dashboard ruhig bleibt und Meld nicht dauernd angepingt wird.
            if cache.get("locked") and cache.get("host") == host and cache.get("port") == port and cache.get("ok"):
                return True, str(cache.get("detail") or "Meld verbunden")

            # Solange Meld noch nicht läuft, nur leicht pollen. Sobald Meld später gestartet wird,
            # springt der Status automatisch auf verbunden und wird dann oben gelockt.
            if cache.get("host") == host and cache.get("port") == port and now - float(cache.get("ts") or 0.0) < 3.0:
                return bool(cache.get("ok")), str(cache.get("detail") or "")

            ok, detail = _check_meld_webchannel(host, port, timeout=0.8)
            self._meld_status_cache = {"ts": now, "host": host, "port": port, "ok": ok, "detail": detail, "locked": bool(ok)}
            return ok, detail
        except Exception as exc:
            return False, f"Meld nicht verbunden: {exc}"

    def obs_status(self, cfg: dict) -> tuple[bool, str]:
        try:
            if not bool(cfg.get("enabled", True)):
                self._close_obs_connection()
                self._obs_status_cache = {"ts": time.time(), "host": "", "port": 0, "ok": False, "detail": "deaktiviert", "locked": False}
                return False, "deaktiviert"
            if str(cfg.get("autoconnect", True)).strip().lower() in {"0", "false", "no", "off"}:
                self._close_obs_connection()
                self._obs_status_cache = {"ts": time.time(), "host": "", "port": 0, "ok": False, "detail": "Autoconnect aus", "locked": False}
                return False, "Autoconnect aus"

            host, port = _obs_host_port_from_cfg(cfg)
            password = str(cfg.get("password") or "")
            key = (host, int(port), password)

            # If we already own a persistent OBS connection for exactly these settings,
            # keep it and report connected. This is the part that makes OBS itself show
            # an active WebSocket session, not just a quick test connection.
            with self._obs_lock:
                if self._obs_sock is not None and self._obs_conn_key == key:
                    detail = str(self._obs_status_cache.get("detail") or "OBS verbunden")
                    return True, detail

            cache = self._obs_status_cache
            now = time.time()
            if cache.get("host") == host and cache.get("port") == port and cache.get("key") == key and now - float(cache.get("ts") or 0.0) < 3.0:
                return bool(cache.get("ok")), str(cache.get("detail") or "")

            ok, detail = self._connect_obs_persistent(host, int(port), password, timeout=3.0)
            self._obs_status_cache = {"ts": now, "host": host, "port": int(port), "ok": ok, "detail": detail, "locked": bool(ok), "key": key}
            return ok, detail
        except Exception as exc:
            self._close_obs_connection()
            return False, f"OBS nicht verbunden: {exc}"

    def _connect_obs_persistent(self, host: str, port: int, password: str = "", timeout: float = 3.0) -> tuple[bool, str]:
        self._close_obs_connection()
        sock = None
        try:
            sock, detail = _open_obs_identified_socket(host, int(port), password, timeout=timeout)
            try:
                sock.settimeout(0.25)
            except Exception:
                pass
            stop = threading.Event()
            with self._obs_lock:
                self._obs_sock = sock
                self._obs_stop = stop
                self._obs_conn_key = (host, int(port), str(password or ""))
                self._obs_status_cache = {"ts": time.time(), "host": host, "port": int(port), "ok": True, "detail": detail, "locked": True, "key": self._obs_conn_key}
            t = threading.Thread(target=self._obs_pump_loop, args=(sock, stop), name="WebbasedOBSPump", daemon=True)
            with self._obs_lock:
                self._obs_thread = t
            t.start()
            self.log("obs", detail)
            return True, detail
        except Exception as exc:
            if sock is not None:
                try: sock.close()
                except Exception: pass
            self._close_obs_connection()
            return False, _obs_connection_error(host, int(port), exc)

    def _obs_pump_loop(self, sock: socket.socket, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                _ws_recv_text(sock)
            except (socket.timeout, TimeoutError):
                continue
            except Exception as exc:
                with self._obs_lock:
                    if self._obs_sock is sock:
                        self._obs_sock = None
                        self._obs_conn_key = None
                        self._obs_status_cache = {"ts": time.time(), "host": "", "port": 0, "ok": False, "detail": f"OBS getrennt: {exc}", "locked": False}
                try:
                    sock.close()
                except Exception:
                    pass
                try:
                    self.log("obs", "disconnected", exc)
                except Exception:
                    pass
                break

    def _close_obs_connection(self) -> None:
        sock = None
        with self._obs_lock:
            try:
                self._obs_stop.set()
            except Exception:
                pass
            sock = self._obs_sock
            self._obs_sock = None
            self._obs_conn_key = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

STATE: AppState | None = None

def _ws_read_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("Verbindung geschlossen")
        data += chunk
    return data

def _ws_send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    first = 0x81
    if len(payload) < 126:
        header = bytes([first, 0x80 | len(payload)])
    elif len(payload) < 65536:
        header = bytes([first, 0x80 | 126]) + struct.pack("!H", len(payload))
    else:
        header = bytes([first, 0x80 | 127]) + struct.pack("!Q", len(payload))
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + mask + masked)

def _ws_recv_text(sock: socket.socket) -> str:
    while True:
        b1, b2 = _ws_read_exact(sock, 2)
        opcode = b1 & 0x0F
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", _ws_read_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _ws_read_exact(sock, 8))[0]
        mask = _ws_read_exact(sock, 4) if (b2 & 0x80) else b""
        payload = _ws_read_exact(sock, length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x1:
            return payload.decode("utf-8", "replace")
        if opcode == 0x8:
            raise RuntimeError("Meld WebSocket geschlossen")
        if opcode == 0x9:
            # pong
            first = 0x8A
            sock.sendall(bytes([first, len(payload)]) + payload)

def _obs_host_port_from_cfg(cfg: dict) -> tuple[str, int]:
    raw_url = str(cfg.get("url") or "").strip()
    host = str(cfg.get("host") or "").strip()
    port_val = str(cfg.get("port") or "").strip()
    if raw_url:
        u = raw_url if "://" in raw_url else "ws://" + raw_url
        parsed = urllib.parse.urlparse(u)
        if parsed.hostname:
            host = parsed.hostname
        if parsed.port:
            port_val = str(parsed.port)
    if not host:
        host = "127.0.0.1"
    try:
        port = int(port_val or 4455)
    except Exception:
        port = 4455
    return host, port

def _obs_connection_error(host: str, port: int, exc: Exception) -> str:
    if isinstance(exc, ConnectionRefusedError) or getattr(exc, "winerror", None) == 10061:
        return (
            f"OBS WebSocket antwortet nicht auf {host}:{port}. "
            "OBS öffnen und unter Werkzeuge > WebSocket-Servereinstellungen "
            "den WebSocket-Server aktivieren."
        )
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return f"OBS WebSocket auf {host}:{port} antwortet nicht rechtzeitig."
    return f"OBS nicht verbunden: {exc}"

def _ws_http_handshake(sock: socket.socket, host: str, port: int, timeout: float) -> None:
    sock.settimeout(timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    sock.sendall(req)
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            break
        resp += chunk
    first = resp.split(b"\r\n", 1)[0]
    if b"101" not in first:
        raise RuntimeError("WebSocket antwortet nicht korrekt")
    accept = b""
    for line in resp.split(b"\r\n"):
        if line.lower().startswith(b"sec-websocket-accept:"):
            accept = line.split(b":", 1)[1].strip()
            break
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest())
    if accept != expected:
        raise RuntimeError("WebSocket handshake ungültig")

def _open_obs_identified_socket(host: str, port: int, password: str = "", timeout: float = 1.5) -> tuple[socket.socket, str]:
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    try:
        _ws_http_handshake(sock, host, int(port), timeout)
        hello = json.loads(_ws_recv_text(sock))
        if hello.get("op") != 0:
            raise RuntimeError("OBS antwortet, aber ohne Hello")
        auth = None
        auth_data = ((hello.get("d") or {}).get("authentication") or {})
        if auth_data:
            if not str(password or ""):
                raise RuntimeError("OBS Passwort fehlt")
            secret = base64.b64encode(hashlib.sha256((str(password or "") + auth_data.get("salt", "")).encode("utf-8")).digest()).decode("utf-8")
            auth = base64.b64encode(hashlib.sha256((secret + auth_data.get("challenge", "")).encode("utf-8")).digest()).decode("utf-8")
        identify = {"op": 1, "d": {"rpcVersion": 1}}
        if auth:
            identify["d"]["authentication"] = auth
        _ws_send_text(sock, json.dumps(identify))
        identified = json.loads(_ws_recv_text(sock))
        if identified.get("op") != 2:
            err = identified.get("d") if isinstance(identified, dict) else identified
            raise RuntimeError(f"OBS Identifizierung fehlgeschlagen: {err}")
        version = ""
        rpc = ((hello.get("d") or {}).get("obsWebSocketVersion") or "")
        if rpc:
            version = f" v{rpc}"
        return sock, f"OBS verbunden{version}"
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise

def _check_obs_websocket(host: str, port: int, password: str = "", timeout: float = 1.5) -> tuple[bool, str]:
    sock = None
    try:
        sock, detail = _open_obs_identified_socket(host, int(port), password, timeout=timeout)
        return True, detail
    except Exception as exc:
        return False, _obs_connection_error(host, int(port), exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

def _check_meld_webchannel(host: str, port: int, timeout: float = 1.0) -> tuple[bool, str]:
    sock = None
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        sock.sendall(req)
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += sock.recv(4096)
            if not resp:
                break
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            return False, "Meld WebSocket antwortet nicht korrekt"
        _ws_send_text(sock, json.dumps({"type": 3, "id": 1}))
        end = time.time() + timeout
        while time.time() < end:
            text = _ws_recv_text(sock)
            try:
                data = json.loads(text)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") not in (3, 10):
                continue
            if data.get("type") == 10 and data.get("id") != 1:
                continue
            payload = data.get("data")
            if not isinstance(payload, dict):
                continue
            if "meld" not in payload:
                return False, "WebChannel ohne meld-Objekt"
            obj = payload.get("meld")
            version = ""
            if isinstance(obj, dict) and obj.get("version"):
                version = f" v{obj.get('version')}"
            return True, f"Meld verbunden{version}"
        return False, "Meld WebChannel Timeout"
    except Exception as exc:
        return False, f"Meld nicht verbunden: {exc}"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

YOUTUBE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


def _openai_model_sort_key(model_id: str):
    text = str(model_id or "")
    low = text.lower()
    group = 0 if low.startswith("gpt-5") else 1 if low.startswith("gpt-4.1") else 2 if low.startswith("gpt-4o") else 3 if low.startswith(("o4", "o3", "o1")) else 4
    return (group, low)


def _openai_chat_model_ids(data: dict) -> list[str]:
    blocked = (
        "embedding", "audio", "tts", "whisper", "dall-e", "image", "moderation",
        "realtime", "transcribe", "search", "instruct", "babbage", "davinci",
        "preview", "codex",
    )
    stable_chat_aliases = {
        "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat-latest",
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "gpt-4o", "gpt-4o-mini",
        "o4-mini", "o3", "o3-mini", "o1", "o1-mini",
    }
    models = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        low = model_id.lower()
        if not model_id or any(part in low for part in blocked):
            continue
        # /models also returns snapshots and special-purpose variants. Keep the
        # dropdown conservative so selecting an item means botalot can call it.
        if low in stable_chat_aliases:
            models.append(model_id)
    return sorted(set(models), key=_openai_model_sort_key)


def _check_openai_api(api_key: str, organization="", project="", timeout=10.0) -> tuple[bool, str, list[str]]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project
    try:
        req = urllib.request.Request(OPENAI_API_BASE + "/models", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            models = _openai_chat_model_ids(data)
            if models:
                return True, f"OpenAI API verbunden - {len(models)} Chat-Modelle verfuegbar", models
            return False, "OpenAI API verbunden, aber keine passenden Chat-Modelle gefunden", []
        return False, "OpenAI API antwortet, aber ohne Modellliste", []
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
            detail = str((body.get("error") or {}).get("message") or "").strip()
        except Exception:
            pass
        if exc.code == 401:
            return False, "OpenAI API-Key ungueltig", []
        if exc.code == 403:
            return False, "OpenAI API-Zugriff verweigert; Projekt- und Organisations-ID pruefen", []
        return False, f"OpenAI API HTTP {exc.code}" + (f": {detail}" if detail else ""), []
    except Exception as exc:
        return False, f"OpenAI API nicht erreichbar: {exc}", []


def _yt_clean(value) -> str:
    return str(value or "").strip()


def _yt_http_json(url: str, *, data=None, headers=None, method="GET", timeout=8.0) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    h = dict(headers or {})
    if body is not None:
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    h.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")
    return json.loads(raw or "{}") if raw.strip() else {}


def _youtube_tokeninfo(access_token: str) -> tuple[bool, str, str]:
    access_token = _yt_clean(access_token)
    if not access_token:
        return False, "Access Token fehlt", ""
    try:
        url = YOUTUBE_TOKENINFO_URL + "?" + urllib.parse.urlencode({"access_token": access_token})
        info = _yt_http_json(url, timeout=6.0)
        scope = _yt_clean(info.get("scope")) if isinstance(info, dict) else ""
        if isinstance(info, dict) and (info.get("aud") or info.get("expires_in") or scope):
            return True, "Token gültig", scope
        return False, "Tokeninfo leer", scope
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
        return False, f"Token ungültig/abgelaufen: HTTP {exc.code}", ""
    except Exception as exc:
        return False, f"Tokenprüfung fehlgeschlagen: {exc}", ""


def _youtube_channel_for_token(access_token: str) -> dict:
    access_token = _yt_clean(access_token)
    if not access_token:
        return {}
    try:
        url = YOUTUBE_CHANNELS_URL + "?" + urllib.parse.urlencode({"part": "id,snippet", "mine": "true", "maxResults": "1"})
        data = _yt_http_json(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=8.0)
        items = data.get("items") if isinstance(data, dict) else []
        if not items:
            return {}
        item = items[0] if isinstance(items[0], dict) else {}
        snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
        return {
            "id": _yt_clean(item.get("id")),
            "title": _yt_clean(snippet.get("title")),
            "customUrl": _yt_clean(snippet.get("customUrl")),
        }
    except Exception:
        # Channels lookup must not break the dashboard: tokeninfo already proved OAuth.
        return {}


def _youtube_refresh(cfg: dict, *, main: bool) -> tuple[bool, str, dict]:
    refresh_key = "main_refresh_token" if main else "refresh_token"
    access_key = "main_access_token" if main else "access_token"
    scopes_key = "main_scopes" if main else "scopes"
    status_key = "main_connection_status" if main else "connection_status"
    saved_key = "main_saved_at" if main else "saved_at"
    refresh = _yt_clean(cfg.get(refresh_key))
    client_id = _yt_clean(cfg.get("client_id"))
    client_secret = _yt_clean(cfg.get("client_secret"))
    role = "Main" if main else "Bot"
    if not refresh:
        return False, f"kein {role} Refresh Token", {}
    if not client_id:
        return False, "YouTube Client ID fehlt", {}
    try:
        payload = {"client_id": client_id, "grant_type": "refresh_token", "refresh_token": refresh}
        if client_secret:
            payload["client_secret"] = client_secret
        data = _yt_http_json(YOUTUBE_TOKEN_URL, method="POST", data=payload, timeout=12.0)
        access = _yt_clean(data.get("access_token"))
        if not access:
            return False, f"{role} Refresh lieferte keinen Access Token", {}
        ok, detail, scope = _youtube_tokeninfo(access)
        if not ok:
            return False, detail, {access_key: "", status_key: f"{role} Refresh ungültig: {detail}"}
        ch = _youtube_channel_for_token(access)
        title = _yt_clean(ch.get("title") or ch.get("id")) or "YouTube"
        updates = {
            access_key: access,
            refresh_key: _yt_clean(data.get("refresh_token") or refresh),
            scopes_key: scope or _yt_clean(cfg.get(scopes_key)),
            saved_key: int(time.time()),
            status_key: f"{role} verbunden als {title}",
        }
        if main:
            updates.update({"main_channel_id": ch.get("id", ""), "main_channel_title": ch.get("title", ""), "main_channel_custom_url": ch.get("customUrl", ""), "broadcaster_channel_id": ch.get("id", "")})
        else:
            updates.update({"bot_channel_id": ch.get("id", ""), "bot_channel_title": ch.get("title", ""), "bot_channel_custom_url": ch.get("customUrl", "")})
        return True, f"{role} Token aktualisiert", updates
    except Exception as exc:
        return False, f"{role} Refresh fehlgeschlagen: {exc}", {access_key: "", status_key: f"{role} Refresh fehlgeschlagen"}


def _youtube_check_account(cfg: dict, *, main: bool) -> tuple[bool, str, dict]:
    access_key = "main_access_token" if main else "access_token"
    scopes_key = "main_scopes" if main else "scopes"
    status_key = "main_connection_status" if main else "connection_status"
    saved_key = "main_saved_at" if main else "saved_at"
    role = "Main" if main else "Bot"
    access = _yt_clean(cfg.get(access_key))
    if access:
        ok, detail, scope = _youtube_tokeninfo(access)
        if ok:
            updates = {scopes_key: scope or _yt_clean(cfg.get(scopes_key)), saved_key: int(time.time())}
            title = _yt_clean(cfg.get("main_channel_title" if main else "bot_channel_title")) or "YouTube"
            updates[status_key] = f"{role} verbunden als {title}"
            return True, detail, updates
    refreshed, refresh_detail, updates = _youtube_refresh(cfg, main=main)
    if refreshed:
        return True, refresh_detail, updates
    if access and not refreshed:
        return False, refresh_detail if refresh_detail else "Token ungültig", updates
    return False, refresh_detail, updates

def _content_type(path):
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"

def esc_html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

LOG_LEVELS = {"debug", "info", "status", "metric", "warning", "warn", "error", "failed"}

def _clean_log_field(value, fallback="app"):
    text = str(value if value is not None else "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:120] or fallback

def _normalize_log_parts(parts) -> tuple[str, str, str]:
    items = [str(item) for item in (parts or ()) if item is not None]
    if not items:
        return "app", "info", ""
    source = _clean_log_field(items[0])
    level = "info"
    rest = items[1:]
    if rest:
        maybe_level = str(rest[0] or "").strip().lower()
        if maybe_level in LOG_LEVELS:
            level = "warning" if maybe_level == "warn" else maybe_level
            rest = rest[1:]
    if level == "info":
        low = " ".join(rest).lower()
        if any(word in low for word in ("error", "failed", "fehlgeschlagen", "exception", "traceback")):
            level = "error"
        elif any(word in low for word in ("warning", "warnung", "blocked", "ungueltig", "invalid")):
            level = "warning"
    message = " | ".join(_clean_log_field(item, "") for item in rest).strip(" |")
    return source, level, message

def _redact_dev_log(text):
    text = str(text or "")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token|password)([\"']?\s*[:=]\s*[\"']?)[^\"'\s,;}]+", r"\1\2[REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED-OPENAI-KEY]", text)
    return text

def _safe_dev_settings(value, key=""):
    if re.search(r"(?i)(secret|password|token|api[_-]?key)", str(key)):
        return "[GESPEICHERT]" if value else ""
    if isinstance(value, dict):
        return {k: _safe_dev_settings(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_dev_settings(v) for v in value]
    return value

def _available_dev_log_sources(text, plugin_ids):
    sources = []
    seen = set()
    for line in str(text or "").splitlines():
        src = _dev_log_source(line)
        if not src or src in seen:
            continue
        seen.add(src)
        sources.append(src)
    known_platform_sources = set().union(*DEV_PLATFORM_LOG_SOURCES.values()) if 'DEV_PLATFORM_LOG_SOURCES' in globals() else set()
    boring = {"start", "listen", "shutdown", "callback-listen", "callback-port-busy", "port_warning", "status", "static missing", "static error"}
    out = []
    for src in sorted(sources, key=str.lower):
        if src in plugin_ids or src in known_platform_sources:
            continue
        if src in boring:
            continue
        out.append({"id": src, "name": src})
    return out

DEV_PLATFORM_LOG_SOURCES = {
    "twitch": {"twitch", "twitch_chat"},
    "tiktok": {"tiktok", "tiktok_chat", "tiktok_live_alert"},
    "youtube": {"youtube", "youtube_chat"},
    "kick": {"kick", "kick_chat"},
    "spotify": {"spotify", "spotis3mptify"},
    "openai": {"openai"},
    "meld": {"meld", "meld_control"},
    "obs": {"obs", "obs_control"},
}

def _dev_log_source(line):
    parts = str(line or "").split(" | ", 2)
    return parts[1].strip() if len(parts) >= 3 else ""

def _dev_log_level(line):
    parts = str(line or "").split(" | ", 3)
    if len(parts) >= 4 and parts[2].strip().lower() in LOG_LEVELS:
        level = parts[2].strip().lower()
        return "warning" if level == "warn" else level
    low = str(line or "").lower()
    if any(word in low for word in ("error", "failed", "fehlgeschlagen", "traceback")):
        return "error"
    if any(word in low for word in ("warning", "warnung", "blocked", "ungueltig", "invalid")):
        return "warning"
    return "info"

def _dev_source_matches(source, allowed):
    return any(source == item or source.startswith(item + " ") for item in allowed)

def _filter_dev_log(text, scope, selected, plugin_ids, level="all", search=""):
    scope = str(scope or "all").strip().lower()
    selected = str(selected or "").strip()
    level = str(level or "all").strip().lower()
    search = str(search or "").strip().lower()
    plugin_ids = set(plugin_ids or [])
    platform_sources = set().union(*DEV_PLATFORM_LOG_SOURCES.values())
    lines = str(text or "").splitlines()
    if scope == "platform":
        allowed = DEV_PLATFORM_LOG_SOURCES.get(selected, {selected})
        lines = [line for line in lines if _dev_source_matches(_dev_log_source(line), allowed)]
    elif scope == "plugin":
        lines = [line for line in lines if _dev_log_source(line) == selected]
    elif scope == "plugins":
        lines = [line for line in lines if _dev_log_source(line) in plugin_ids]
    elif scope == "core":
        lines = [line for line in lines if _dev_log_source(line) not in plugin_ids and not _dev_source_matches(_dev_log_source(line), platform_sources)]
    if level in {"debug", "info", "status", "metric", "warning", "error", "failed"}:
        lines = [line for line in lines if _dev_log_level(line) == level]
    if search:
        lines = [line for line in lines if search in line.lower()]
    return "\n".join(lines)

def _dev_plugin_filter_list(st):
    plugins = []
    seen = set()
    try:
        for item in st.plugin_list():
            pid = str(item.get("id") or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            plugins.append({"id": pid, "name": str(item.get("name") or pid)})
    except Exception:
        pass
    try:
        txt = st.log_file.read_text(encoding="utf-8") if st.log_file.exists() else ""
        for item in _available_dev_log_sources(txt, seen):
            pid = str(item.get("id") or "").strip()
            if pid and pid not in seen:
                seen.add(pid)
                plugins.append(item)
    except Exception:
        pass
    return plugins

CHAT_PLATFORM_PLUGINS = {
    "twitch": "twitch_chat",
    "tiktok": "tiktok_chat",
    "youtube": "youtube_chat",
    "kick": "kick_chat",
}
CHAT_PLATFORM_ICON_PATHS = {
    "twitch": ("integrations", "twitch_chat", "assets", "twitch.png"),
    "tiktok": ("integrations", "tiktok_chat", "assets", "TikTok.png"),
    "youtube": ("integrations", "youtube_chat", "assets", "youtube.png"),
    "kick": ("integrations", "kick_chat", "assets", "Kick.png"),
}

def _chat_platform_state(st, settings):
    out = []
    now = time.time()
    for platform, plugin_id in CHAT_PLATFORM_PLUGINS.items():
        cfg = settings.get("platforms", {}).get(platform, {})
        if not bool(cfg.get("enabled", False)):
            continue
        metric = dict(st.metrics.get(platform, {}) or {})
        plugin_status = dict(st.plugin_status.get(plugin_id, {}) or {})
        viewer = metric.get("viewer_count")
        metric_fresh = bool(metric) and now - float(metric.get("ts") or 0.0) < 120.0
        connected = str(plugin_status.get("state") or "").lower() in {"connected", "running"}
        viewer_error = bool(metric.get("viewer_count_error") or metric.get("metric_error"))
        out.append({
            "platform": platform,
            "plugin_id": plugin_id,
            "connected": connected,
            "viewer_count": int(viewer) if metric_fresh and not viewer_error and str(viewer).isdigit() else None,
            "blocked": not connected or viewer_error,
            "detail": str(plugin_status.get("message") or "Noch keine aktuellen Zuschauerdaten"),
        })
    return out

class Handler(BaseHTTPRequestHandler):
    server_version = "webbased/0.33"

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        if extra:
            for k,v in extra.items():
                self.send_header(k,v)
        self.end_headers()
        self.wfile.write(b)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

    def _read_json(self):
        ln = int(self.headers.get("Content-Length") or 0)
        if ln <= 0:
            return {}
        raw = self.rfile.read(ln)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        global STATE
        st = STATE
        if st is None:
            self._send(500, "no state")
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/static/"):
            rel = path[len("/static/"):].lstrip("/")
            candidates = [st.static / rel, st.base / "static" / rel, st.resource_base / "static" / rel]
            for p in candidates:
                try:
                    if p.exists() and p.is_file():
                        self._send(200, p.read_bytes(), _content_type(p))
                        return
                except Exception as e:
                    st.log("static error", str(p), str(e))
            st.log("static missing", path, "candidates=" + " | ".join(str(x) for x in candidates))
            self._send(404, "Static missing: " + rel, "text/plain; charset=utf-8")
            return
        if path.startswith("/platform-icon/"):
            platform = path.rsplit("/", 1)[-1].lower()
            parts = CHAT_PLATFORM_ICON_PATHS.get(platform)
            if parts:
                icon = st.modules.joinpath(*parts)
                if icon.is_file():
                    return self._send(200, icon.read_bytes(), _content_type(icon))
            return self._send(404, "Icon missing", "text/plain")

        if path in ("/", "/dashboard"):
            return self._page("index.html")
        if path in ("/plattformen", "/platforms"):
            return self._page("platforms.html")
        if path == "/chat":
            return self._page("chat.html")
        if path in ("/spotis3mptify", "/spotify"):
            return self._page("spotify.html")
        if path in ("/overlays", "/overlay-urls"):
            return self._page("overlays.html")
        if path == "/plugins":
            return self._page("plugins.html")
        if path == "/dev":
            return self._page("dev.html")
        if path == "/desktop-chat":
            return self._page("desktop_chat.html")

        if path == "/api/status":
            try:
                plats = st.live_platform_statuses()
            except Exception as exc:
                st.log("status", "failed", exc)
                plats = {p: {"enabled": False, "status": "nicht verbunden", "detail": str(exc)} for p in PLATFORM_ORDER}
            self._json({"version": VERSION, "uptime": int(time.time()-st.started), "port": st.port, "platforms": plats, "plugins": st.plugin_list()})
            return
        if path == "/api/settings":
            self._json(st.settings())
            return
        if path == "/api/openai/models":
            cfg = st.settings().get("platforms", {}).get("openai", {})
            force = str((urllib.parse.parse_qs(parsed.query).get("force") or [""])[0]).lower() in {"1", "true", "yes"}
            ok, detail, models = st.openai_models(cfg, force=force)
            self._json({"ok": ok, "detail": detail, "models": models})
            return
        m_plugin_settings = re.match(r"^/api/plugins/([^/]+)/settings$", path)
        if m_plugin_settings:
            plugin_id = urllib.parse.unquote(m_plugin_settings.group(1)).strip()
            schema = []
            defaults = {}
            plugin = None
            load_error = ""
            try:
                plugin = st.plugin_manager.load_plugin(plugin_id)
            except Exception as exc:
                load_error = str(exc)
                st.log(plugin_id or "plugins", "settings plugin load failed", exc)
            if plugin is not None:
                try:
                    if hasattr(plugin, "settings_schema"):
                        try:
                            schema = plugin.settings_schema(language="de", ui_language="de")
                        except TypeError:
                            schema = plugin.settings_schema()
                except Exception as exc:
                    st.log(plugin_id, "settings_schema failed", exc)
                    schema = []
                try:
                    if hasattr(plugin, "default_settings"):
                        defaults = plugin.default_settings()
                        if not isinstance(defaults, dict):
                            defaults = {}
                except Exception:
                    defaults = {}
            values = st.plugin_settings(plugin_id, plugin)
            if not schema:
                merged_keys = []
                for source in (defaults, values):
                    if isinstance(source, dict):
                        for key in source.keys():
                            if key not in merged_keys and not str(key).startswith("_"):
                                merged_keys.append(key)
                schema = []
                for key in merged_keys:
                    val = values.get(key, defaults.get(key) if isinstance(defaults, dict) else "")
                    typ = "bool" if isinstance(val, bool) else ("number" if isinstance(val, (int, float)) and not isinstance(val, bool) else "text")
                    schema.append({"key": key, "label": key, "type": typ})
            self._json({"ok": True, "plugin_id": plugin_id, "schema": schema or [], "defaults": defaults, "values": values, "status": st.plugin_status.get(plugin_id, {}), "load_error": load_error})
            return
        if path == "/api/debug":
            try:
                txt = st.log_file.read_text(encoding="utf-8") if st.log_file.exists() else ""
            except Exception as e:
                txt = "Log lesen fehlgeschlagen: " + str(e)
            self._json({"version": VERSION, "base": str(st.base), "resource_base": str(st.resource_base), "templates": str(st.templates), "static": str(st.static), "log": txt[-12000:]})
            return
        if path == "/api/dev/log":
            try:
                txt = st.log_file.read_text(encoding="utf-8") if st.log_file.exists() else ""
            except Exception as exc:
                txt = "Log lesen fehlgeschlagen: " + str(exc)
            query = urllib.parse.parse_qs(parsed.query)
            scope = str((query.get("scope") or ["all"])[0])
            selected = str((query.get("id") or [""])[0])
            level = str((query.get("level") or ["all"])[0])
            search = str((query.get("q") or [""])[0])
            plugin_ids = [str(item.get("id") or "") for item in st.plugin_list()]
            filtered = _filter_dev_log(txt, scope, selected, plugin_ids, level=level, search=search)
            self._json({
                "log": _redact_dev_log(filtered[-100000:]),
                "bytes": st.log_file.stat().st_size if st.log_file.exists() else 0,
                "scope": scope,
                "id": selected,
                "level": level,
                "search": search,
                "lines": len(filtered.splitlines()) if filtered else 0,
            })
            return
        if path == "/api/dev/info":
            settings = st.settings()
            try:
                platforms = st.live_platform_statuses()
            except Exception as exc:
                st.log("dev", "status failed", exc)
                platforms = {name: {"enabled": bool(settings.get("platforms", {}).get(name, {}).get("enabled", False)), "status": "nicht verbunden", "detail": str(exc)} for name in PLATFORM_ORDER}
            try:
                usage = shutil.disk_usage(st.base)
                disk_free = usage.free
            except Exception:
                disk_free = 0
            self._json({
                "version": VERSION,
                "uptime": int(time.time() - st.started),
                "port": st.port,
                "pid": os.getpid(),
                "python": sys.version.split()[0],
                "frozen": bool(getattr(sys, "frozen", False)),
                "executable": str(sys.executable),
                "cwd": str(Path.cwd()),
                "paths": {
                    "base": str(st.base), "resource": str(st.resource_base), "data": str(st.data),
                    "log": str(st.log_file), "templates": str(st.templates), "static": str(st.static),
                },
                "counts": {
                    "messages": len(st.messages), "plugins": len(st.plugin_list()),
                    "active_plugins": len(st.plugin_instances), "auth_files": len(list(st.auth_dir.glob("*.json"))) if st.auth_dir.exists() else 0,
                },
                "disk_free": disk_free,
                "platforms": platforms,
                "log_filters": {
                    "platforms": PLATFORM_ORDER,
                    "plugins": _dev_plugin_filter_list(st),
                },
            })
            return
        if path == "/api/dev/settings":
            self._json(_safe_dev_settings(st.settings()))
            return
        if path == "/debug":
            try:
                txt = st.log_file.read_text(encoding="utf-8") if st.log_file.exists() else ""
            except Exception as e:
                txt = "Log lesen fehlgeschlagen: " + str(e)
            body = "<!doctype html><meta charset=utf-8><title>webbased debug</title><body style='background:#080a13;color:#fff;font-family:Consolas,monospace;white-space:pre-wrap;padding:24px'><h2>webbased debug Ver. " + VERSION + "</h2>" + esc_html(txt[-20000:]) + "</body>"
            self._send(200, body)
            return

        if path == "/api/spotis3mptify/overlay-state":
            cfg = self._overlay_settings()
            self._json(cfg)
            return
        if path == "/api/system-fonts":
            self._json({"fonts": self._system_fonts()})
            return
        if path == "/api/messages":
            self._json({"messages": st.messages[-80:]})
            return
        if path == "/api/chat-state":
            self._json({"messages": st.messages[-100:], "platforms": _chat_platform_state(st, st.settings())})
            return
        if path == "/api/desktop-chat/layout":
            default = {"viewerBar": {"x": 16, "y": 16, "w": 720, "h": 64}, "chatPanel": {"x": 16, "y": 92, "w": 720, "h": 620}, "style": {"background": "#0d101d", "opacity": 82, "radius": 16, "fontFamily": "Segoe UI", "fontSize": 16, "textColor": "#ffffff"}}
            stored = _json_load(st.data / "plugins" / "chat_desktop" / "layout.json", {})
            merged = {key: {**value, **(stored.get(key, {}) if isinstance(stored.get(key), dict) else {})} for key, value in default.items()}
            self._json(merged)
            return
        if path == "/api/desktop-chat/state":
            self._json({"editing": bool(st.desktop_chat_editing)})
            return
        if path == "/api/nowplaying":
            self._json(self._nowplaying())
            return
        if path == "/api/runtime":
            base = f"http://127.0.0.1:{st.port}"
            settings = st.settings()
            spotify_redirect = settings.get("platforms", {}).get("spotify", {}).get("redirect_uri") or f"http://127.0.0.1:{CALLBACK_PORT}/callback"
            self._json({
                "version": VERSION,
                "port": st.port,
                "base_url": base,
                "callback_port": CALLBACK_PORT,
                "spotify_redirect_uri": spotify_redirect,
                "port_warning": ""
            })
            return
        if path.startswith("/api/tiktok/open/"):
            parts = path.strip("/").split("/")
            account = parts[-1] if parts else "main"
            try:
                res = st.open_tiktok_login(account)
                self._json(res)
            except Exception as exc:
                st.log("tiktok", "open failed", exc)
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/test-platform/tiktok":
            cfg = st.settings().get("platforms", {}).get("tiktok", {})
            ok, detail = st.tiktok_status(cfg)
            self._json({"ok": ok, "status": "verbunden" if ok else "nicht verbunden", "detail": detail})
            return

        if path == "/api/test-platform/meld":
            cfg = st.settings().get("platforms", {}).get("meld", {})
            ok, detail = _check_meld_webchannel(str(cfg.get("host") or "127.0.0.1"), int(str(cfg.get("port") or 13376)), timeout=1.5)
            st._meld_status_cache = {"ts": time.time(), "host": str(cfg.get("host") or "127.0.0.1"), "port": int(str(cfg.get("port") or 13376)), "ok": ok, "detail": detail, "locked": bool(ok)}
            self._json({"ok": ok, "status": "verbunden" if ok else "nicht verbunden", "detail": detail})
            return
        if path == "/api/test-platform/obs":
            cfg = st.settings().get("platforms", {}).get("obs", {})
            host, port = _obs_host_port_from_cfg(cfg)
            ok, detail = st._connect_obs_persistent(host, port, str(cfg.get("password") or ""), timeout=3.0)
            st._obs_status_cache = {"ts": time.time(), "host": host, "port": port, "ok": ok, "detail": detail, "locked": bool(ok), "key": (host, int(port), str(cfg.get("password") or ""))}
            self._json({"ok": ok, "status": "verbunden" if ok else "nicht verbunden", "detail": detail})
            return
        if path == "/api/test-platform/youtube":
            cfg = st.settings().get("platforms", {}).get("youtube", {})
            st._youtube_status_cache = {"ts": 0.0, "ok": False, "detail": "manuell geprüft", "locked": False, "key": None}
            ok, detail = st.youtube_status(cfg)
            self._json({"ok": ok, "status": "verbunden" if ok else "nicht verbunden", "detail": detail})
            return
        if path == "/api/test-platform/openai":
            cfg = st.settings().get("platforms", {}).get("openai", {})
            ok, detail = st.openai_status(cfg, force=True)
            self._json({"ok": ok, "status": "verbunden" if ok else "nicht verbunden", "detail": detail})
            return

        if path == "/api/overlay-urls":
            base = f"http://127.0.0.1:{st.port}"
            self._json({
                "main": [
                    {"name":"Chat Browser", "url":base + "/chat-browser"},
                    {"name":"Spotis3mptify Overlay", "url":base + "/overlay/spotify"}
                ],
                "groups": [
                    {"title": "Wichtige Browserquellen", "items": [
                        {"name":"Chat Browser", "url":base + "/chat-browser"},
                        {"name":"Spotis3mptify Overlay", "url":base + "/overlay/spotify"}
                    ]},
                    {"title": "Spotis3mptify Kompatibilität", "items": [
                        {"name":"Titel", "url":base + "/browser/title"},
                        {"name":"Artist", "url":base + "/browser/artist"},
                        {"name":"Song Alias", "url":base + "/browser/song"},
                        {"name":"Cover", "url":base + "/browser/cover"},
                        {"name":"Linie oben", "url":base + "/browser/line-up"},
                        {"name":"Linie unten", "url":base + "/browser/line-down"}
                    ]}
                ]
            })
            return

        if path in ("/chat-browser", "/overlay/chat"):
            return self._page("overlay_chat.html")
        if path in ("/overlay/spotify", "/customoverlay"):
            return self._page("overlay_spotify.html")
        if path.startswith("/browser/"):
            return self._spotify_browser(path.rsplit("/",1)[-1])

        if path.startswith("/oauth/start/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                return self._oauth_start(parts[2], parts[3])
        if path.startswith("/oauth/callback/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                return self._oauth_callback(parts[2], parts[3], parsed.query)
        if path in ("/callback", "/callback/", "/kick/callback", "/kick/callback/"):
            return self._oauth_callback_auto(parsed.query)

        self._send(404, "Not Found", "text/plain")

    def do_POST(self):
        global STATE
        st = STATE
        if st is None:
            return self._json({"ok": False, "error":"no state"}, 500)
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        data = self._read_json()

        m_plugin_action = re.match(r"^/api/plugins/([^/]+)/action$", path)
        if m_plugin_action:
            plugin_id = urllib.parse.unquote(m_plugin_action.group(1)).strip()
            key = str(data.get("key") or data.get("action") or "").strip() if isinstance(data, dict) else ""
            if not plugin_id or not key:
                return self._json({"ok": False, "error": "plugin_id oder action fehlt"}, 400)
            try:
                incoming = data.get("values") if isinstance(data, dict) and isinstance(data.get("values"), dict) else {}
                current = st.settings()
                current.setdefault("plugins", {})
                old_cfg = current["plugins"].get(plugin_id, {})
                if not isinstance(old_cfg, dict):
                    old_cfg = {}
                new_cfg = dict(old_cfg)
                if isinstance(incoming, dict):
                    new_cfg.update(incoming)
                current["plugins"][plugin_id] = new_cfg
                st.save_settings(current)

                plugin = st.plugin_manager.load_plugin(plugin_id)
                if hasattr(plugin, "_settings"):
                    try:
                        plugin._settings = dict(new_cfg)
                    except Exception:
                        pass
                if hasattr(plugin, "_host"):
                    try:
                        plugin._host = st.plugin_manager.host
                    except Exception:
                        pass

                handler = None
                for name in ("on_settings_button", "handle_settings_button", "on_settings_action"):
                    fn = getattr(plugin, name, None)
                    if callable(fn):
                        handler = fn
                        break
                if handler is None:
                    return self._json({"ok": False, "error": "Plugin unterstuetzt keine Settings-Aktionen"}, 400)
                try:
                    result = handler(key, st.plugin_manager.host, None)
                except TypeError:
                    try:
                        result = handler(key, st.plugin_manager.host)
                    except TypeError:
                        result = handler(key)
                ok = bool(result)
                detail = "Aktion ausgeführt." if ok else "Aktion fehlgeschlagen. Details stehen im DEV-Log."
                self._json({"ok": ok, "plugin_id": plugin_id, "key": key, "detail": detail, "values": st.plugin_settings(plugin_id, plugin)})
            except Exception as exc:
                st.log(plugin_id or "plugins", "settings action failed", exc)
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        m_plugin_settings = re.match(r"^/api/plugins/([^/]+)/settings$", path)
        if m_plugin_settings:
            plugin_id = urllib.parse.unquote(m_plugin_settings.group(1)).strip()
            try:
                current = st.settings()
                current.setdefault("plugins", {})
                old_cfg = current["plugins"].get(plugin_id, {})
                if not isinstance(old_cfg, dict):
                    old_cfg = {}
                incoming = data.get("values") if isinstance(data, dict) and isinstance(data.get("values"), dict) else (data if isinstance(data, dict) else {})
                new_cfg = dict(old_cfg)
                new_cfg.update(incoming)
                current["plugins"][plugin_id] = new_cfg
                st.save_settings(current)
                st.plugin_manager.restart_plugin_async(plugin_id, "Settings gespeichert; Neustart laeuft")
                self._json({"ok": True, "plugin_id": plugin_id, "values": st.plugin_settings(plugin_id), "restart": "queued"})
            except Exception as exc:
                st.log(plugin_id or "plugins", "save settings failed", exc)
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/settings":
            current = st.settings()
            incoming = data if isinstance(data, dict) else {}
            if "platforms" in incoming and isinstance(incoming["platforms"], dict):
                old_tiktok = current.get("platforms", {}).get("tiktok", {})
                new_tiktok = incoming["platforms"].get("tiktok", {})
                if isinstance(new_tiktok, dict):
                    # Browser/Formular-Zwischenstände können während des Login-Monitors veralten.
                    # Ein bereits bestätigter Login darf nur über den Trennen-Endpunkt gelöscht werden.
                    new_tiktok["main_login_ok"] = bool(old_tiktok.get("main_login_ok") or new_tiktok.get("main_login_ok"))
                    new_tiktok["bot_login_ok"] = bool(old_tiktok.get("bot_login_ok") or new_tiktok.get("bot_login_ok"))
                    if bool(new_tiktok.get("main_login_ok") or new_tiktok.get("bot_login_ok")):
                        new_tiktok["enabled"] = True
                openai_cfg = incoming["platforms"].get("openai", {})
                if isinstance(openai_cfg, dict):
                    openai_cfg.pop("model", None)
                current["platforms"] = incoming["platforms"]
            if "plugins" in incoming and isinstance(incoming["plugins"], dict):
                current["plugins"] = incoming["plugins"]
            old_key = getattr(st, "_obs_conn_key", None)
            st.save_settings(current)
            try:
                changed_platforms = incoming.get("platforms", {}) if isinstance(incoming.get("platforms"), dict) else {}
                for platform, plugin_id in CHAT_PLATFORM_PLUGINS.items():
                    if platform not in changed_platforms:
                        continue
                    st.plugin_manager.restart_plugin_async(plugin_id, f"{platform} gespeichert; Neustart laeuft")
            except Exception as exc:
                st.log("chat-plugins", "restart after settings failed", exc)
            try:
                obs_cfg = current.get("platforms", {}).get("obs", {})
                host, port = _obs_host_port_from_cfg(obs_cfg)
                new_key = (host, int(port), str(obs_cfg.get("password") or ""))
                if old_key and old_key != new_key:
                    st._close_obs_connection()
                    st._obs_status_cache = {"ts": 0.0, "host": "", "port": 0, "ok": False, "detail": "neu gespeichert", "locked": False}
            except Exception:
                pass
            return self._json({"ok": True, "settings": current})

        if path == "/api/client-error":
            st.log("client-error", json.dumps(data, ensure_ascii=False))
            return self._json({"ok": True})
        if path == "/api/dev/log/clear":
            try:
                st.log_file.parent.mkdir(parents=True, exist_ok=True)
                st.log_file.write_text("", encoding="utf-8")
                return self._json({"ok": True})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)
        if path == "/api/dev/log/event":
            level = str(data.get("level") or "info").strip().lower()
            if level not in {"info", "warning", "error"}:
                level = "info"
            message = str(data.get("message") or "Manueller DEV-Testeintrag").strip()[:300]
            st.log("dev", level, message)
            return self._json({"ok": True})

        if path == "/api/ui-heartbeat":
            reload_requested = bool(getattr(st, "ui_reload_requested", False))
            reload_nonce = int(getattr(st, "ui_reload_nonce", 0) or 0)
            if st.ui_heartbeat_lost:
                try: st.log("ui", "main ui heartbeat recovered")
                except Exception: pass
            st.last_ui_heartbeat = time.time()
            st.ui_heartbeat_enabled = True
            st.ui_heartbeat_lost = False
            if reload_requested:
                st.ui_reload_requested = False
            return self._json({"ok": True, "version": VERSION, "reload": reload_requested, "reload_nonce": reload_nonce})

        if path == "/api/shutdown":
            st.shutting_down = True
            try:
                st.log("shutdown", "exe close requested by ui")
            except Exception:
                pass
            try:
                st._close_tiktok_browser_windows()
            except Exception:
                pass
            try:
                st.plugin_manager.stop_all()
            except Exception:
                pass
            try:
                st._close_obs_connection()
            except Exception:
                pass
            try:
                st.mark_clean_shutdown("exe close requested by ui")
            except Exception:
                pass
            _schedule_hard_exit(3.4)
            return self._json({"ok": True, "shutdown": True, "mode": "exe_exit"})

        if path == "/api/spotis3mptify/overlay-state":
            try:
                clean = self._clean_overlay_settings(data)
                _json_save(self._spotis_overlay_settings_path(), clean)
                return self._json({"ok": True, "state": clean})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 500)
        if path == "/api/desktop-chat/layout":
            try:
                clean = {}
                for key in ("viewerBar", "chatPanel"):
                    raw = data.get(key) if isinstance(data, dict) else {}
                    clean[key] = {name: max(0, min(4000, int(raw.get(name, fallback)))) for name, fallback in (("x", 16), ("y", 16), ("w", 720), ("h", 100))}
                raw_style = data.get("style") if isinstance(data, dict) else {}
                clean["style"] = {
                    "background": str(raw_style.get("background") or "#0d101d")[:20],
                    "opacity": max(0, min(100, int(raw_style.get("opacity", 82)))),
                    "radius": max(0, min(100, int(raw_style.get("radius", 16)))),
                    "fontFamily": str(raw_style.get("fontFamily") or "Segoe UI")[:80],
                    "fontSize": max(8, min(72, int(raw_style.get("fontSize", 16)))),
                    "textColor": str(raw_style.get("textColor") or "#ffffff")[:20],
                }
                _json_save(st.data / "plugins" / "chat_desktop" / "layout.json", clean)
                return self._json({"ok": True, "layout": clean})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)
        if path == "/api/desktop-chat/edit":
            st.desktop_chat_editing = bool(data.get("editing", False)) if isinstance(data, dict) else False
            return self._json({"ok": True, "editing": st.desktop_chat_editing})
        if path == "/api/desktop-chat/open":
            try:
                st.desktop_chat_editing = False
                url = f"http://127.0.0.1:{st.port}/desktop-chat"
                if getattr(sys, "frozen", False):
                    cmd = [sys.executable, "--desktop-chat", url]
                else:
                    cmd = [sys.executable, str(st.base / "run_webbased.py"), "--desktop-chat", url]
                subprocess.Popen(cmd, cwd=str(st.base), creationflags=_win_hidden_flags())
                return self._json({"ok": True})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)
        if path == "/api/message":
            text = str(data.get("text") or "").strip()
            if text:
                st.messages.append({"id": _now_ms(), "platform":"test", "user":"Test", "text":text, "message_type":"chat", "time":time.strftime("%H:%M:%S")})
            return self._json({"ok": True})

        if path.startswith("/api/disconnect/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 4:
                p, acc = parts[2], parts[3]
                plugin_id = CHAT_PLATFORM_PLUGINS.get(p)
                try:
                    (st.auth_dir / f"{p}_{acc}.json").unlink(missing_ok=True)
                except Exception:
                    pass
                if p == "spotify":
                    try:
                        (st.auth_dir / "spotify_main.json").unlink(missing_ok=True)
                    except Exception:
                        pass
                    plugin_id = "spotis3mptify"
                if p == "tiktok":
                    try:
                        s = st.settings()
                        tt = s.setdefault("platforms", {}).setdefault("tiktok", {})
                        profile = st._tiktok_profile_dir(tt, acc)
                        shutil.rmtree(profile, ignore_errors=True)
                        st._disconnect_account_settings(s, p, acc)
                        st.save_settings(s)
                    except Exception as exc:
                        st.log("tiktok", "disconnect cleanup failed", exc)
                else:
                    try:
                        s = st.settings()
                        st._disconnect_account_settings(s, p, acc)
                        st.save_settings(s)
                    except Exception as exc:
                        st.log(p or "platform", "disconnect settings cleanup failed", exc)
                try:
                    (st.auth_dir / f"{p}_{acc}.json").unlink(missing_ok=True)
                    if p == "spotify":
                        (st.auth_dir / "spotify_main.json").unlink(missing_ok=True)
                except Exception:
                    pass
                if p == "youtube":
                    st._youtube_status_cache = {"ts": 0.0, "ok": False, "detail": "getrennt", "locked": False, "key": None}
                if p == "openai":
                    try:
                        st._openai_status_cache = {"ts": 0.0, "ok": False, "detail": "getrennt", "locked": False, "key": None, "models": []}
                    except Exception as exc:
                        st.log("openai", "disconnect cache cleanup failed", exc)
                if plugin_id:
                    try:
                        st.plugin_manager.restart_plugin_async(plugin_id, f"{p} {acc} getrennt; Neustart laeuft")
                    except Exception as exc:
                        st.log(plugin_id, "restart after disconnect failed", exc)
                return self._json({"ok": True})
        return self._json({"ok": False, "error": "unknown"}, 404)


    def _overlay_default(self):
        return {
            "background": {"enabled": True, "x": 0, "y": 0, "w": 430, "h": 132, "radius": 24, "color": "#4a4d56", "opacity": 0.72},
            "cover": {"enabled": True, "x": 18, "y": 18, "w": 96, "h": 96, "radius": 22, "shape": "rounded", "rotate": False},
            "title": {"enabled": True, "x": 136, "y": 34, "w": 270, "h": 42, "fontSize": 28, "fontFamily": "Segoe UI", "color": "#ffffff", "uppercase": True, "marqueeMode": "off", "marqueeSpeed": 45, "marqueeGap": 60},
            "artist": {"enabled": True, "x": 137, "y": 77, "w": 270, "h": 30, "fontSize": 18, "fontFamily": "Segoe UI", "color": "#d7dcff", "marqueeMode": "off", "marqueeSpeed": 45, "marqueeGap": 60},
            "extras": []
        }

    def _spotis_overlay_settings_path(self):
        global STATE
        return STATE.data / "spotis3mptify" / "config" / "overlay_settings.json"

    def _legacy_spotis_overlay_settings_path(self):
        global STATE
        return STATE.data / "plugins" / "spotis3mptify" / "overlay_settings.json"

    def _overlay_settings(self):
        global STATE
        default = self._overlay_default()
        path = self._spotis_overlay_settings_path()
        legacy_path = self._legacy_spotis_overlay_settings_path()
        if not path.exists() and legacy_path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy_path, path)
            except Exception:
                pass
        cfg = _json_load(path, default)
        # migrate old card settings if present
        if "background" not in cfg:
            old = cfg if isinstance(cfg, dict) else {}
            cfg = default
            cfg["background"]["x"] = int(old.get("cardX", 0) or 0)
            cfg["background"]["y"] = int(old.get("cardY", 0) or 0)
            cfg["background"]["w"] = int(old.get("cardW", 430) or 430)
            cfg["background"]["h"] = int(old.get("cardH", 132) or 132)
            cfg["background"]["radius"] = int(old.get("radius", 24) or 24)
            cfg["background"]["opacity"] = float(old.get("bgOpacity", .72) or .72)
            cfg["cover"]["enabled"] = bool(old.get("showCover", True))
            cfg["title"]["enabled"] = bool(old.get("showTitle", True))
            cfg["artist"]["enabled"] = bool(old.get("showArtist", True))
            cfg["title"]["fontSize"] = int(old.get("fontSize", 28) or 28)
            cfg["artist"]["fontSize"] = int(old.get("artistSize", 18) or 18)
        for k, v in default.items():
            cfg.setdefault(k, v)
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                for kk, vv in v.items(): cfg[k].setdefault(kk, vv)
        cfg.setdefault("extras", [])
        return cfg

    def _clean_overlay_settings(self, data):
        cur = self._overlay_settings()
        if not isinstance(data, dict): return cur
        def num(v, d, mn=None, mx=None):
            try: x = float(v)
            except Exception: x = d
            if mn is not None: x = max(mn, x)
            if mx is not None: x = min(mx, x)
            return x
        def text(v, d=""):
            return str(v if v is not None else d)[:240]
        for key in ("background","cover","title","artist"):
            if key in data and isinstance(data[key], dict):
                cur[key].update(data[key])
        bg=cur["background"]
        bg["enabled"]=bool(bg.get("enabled", True)); bg["x"]=int(num(bg.get("x"),0)); bg["y"]=int(num(bg.get("y"),0)); bg["w"]=int(num(bg.get("w"),430,20,5000)); bg["h"]=int(num(bg.get("h"),132,20,5000)); bg["radius"]=int(num(bg.get("radius"),24,0,400)); bg["opacity"]=num(bg.get("opacity"),.72,0,1); bg["color"]=text(bg.get("color"),"#4a4d56")
        cv=cur["cover"]
        cv["enabled"]=bool(cv.get("enabled", True)); cv["x"]=int(num(cv.get("x"),18)); cv["y"]=int(num(cv.get("y"),18)); cv["w"]=int(num(cv.get("w"),96,8,2000)); cv["h"]=int(num(cv.get("h"),96,8,2000)); cv["radius"]=int(num(cv.get("radius"),22,0,1000)); cv["shape"]="circle" if cv.get("shape")=="circle" else "rounded"; cv["rotate"]=bool(cv.get("rotate", False))
        for key, fs in (("title",28),("artist",18)):
            el=cur[key]
            el["enabled"]=bool(el.get("enabled", True)); el["x"]=int(num(el.get("x"),136)); el["y"]=int(num(el.get("y"),34)); el["w"]=int(num(el.get("w"),270,8,3000)); el["h"]=int(num(el.get("h"),42,8,1000)); el["fontSize"]=int(num(el.get("fontSize"),fs,6,300)); el["fontFamily"]=text(el.get("fontFamily"),"Segoe UI"); el["color"]=text(el.get("color"),"#ffffff"); el["uppercase"]=bool(el.get("uppercase", key=="title"))
            el["marqueeMode"]=text(el.get("marqueeMode"),"off") if el.get("marqueeMode") in ("off","bounce","loop-rtl","loop-ltr") else "off"; el["marqueeSpeed"]=int(num(el.get("marqueeSpeed"),45,5,500)); el["marqueeGap"]=int(num(el.get("marqueeGap"),60,0,1000))
        extras=[]
        for item in data.get("extras", cur.get("extras", [])) if isinstance(data.get("extras", cur.get("extras", [])), list) else []:
            if not isinstance(item, dict): continue
            etype = text(item.get("type", "text"), "text")
            if etype not in ("text", "rect", "circle"): etype = "text"
            extra_item = {
                "id": text(item.get("id"), "x"+str(int(time.time()*1000))),
                "type": etype,
                "enabled": bool(item.get("enabled", True)),
                "x": int(num(item.get("x"),50)),
                "y": int(num(item.get("y"),150)),
                "w": int(num(item.get("w"),260,8,3000)),
                "h": int(num(item.get("h"),40,8,1000)),
                "color": text(item.get("color"),"#ffffff"),
                "opacity": num(item.get("opacity"), 1 if etype=="text" else .5, 0, 1)
            }
            if etype == "text":
                extra_item["text"] = text(item.get("text"),"Neues Element")
                extra_item["fontSize"] = int(num(item.get("fontSize"),24,6,300))
                extra_item["fontFamily"] = text(item.get("fontFamily"),"Segoe UI")
                extra_item["uppercase"] = bool(item.get("uppercase", False))
            elif etype == "rect":
                extra_item["radius"] = int(num(item.get("radius"),0,0,200))
            extras.append(extra_item)
        cur["extras"] = extras[:24]
        return cur

    def _system_fonts(self):
        names = ["Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Calibri", "Consolas", "Impact", "Georgia", "Times New Roman", "Courier New"]
        seen = set(n.lower() for n in names)
        dirs = []
        windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
        if windir: dirs.append(Path(windir) / "Fonts")
        dirs += [Path.home()/"AppData/Local/Microsoft/Windows/Fonts"]
        for d in dirs:
            try:
                for f in d.glob("*.ttf"):
                    nm = f.stem.replace("-Regular", "").replace(" Regular", "")
                    if nm.lower() not in seen:
                        names.append(nm); seen.add(nm.lower())
                for f in d.glob("*.otf"):
                    nm = f.stem.replace("-Regular", "").replace(" Regular", "")
                    if nm.lower() not in seen:
                        names.append(nm); seen.add(nm.lower())
            except Exception:
                pass
        return sorted(names, key=str.lower)[:300]

    def _page(self, name):
        global STATE
        p = STATE.templates / name
        if not p.exists():
            STATE.log("template missing", str(p), "resource=" + str(STATE.resource_base), "base=" + str(STATE.base))
            return self._send(404, f"Template missing: {p}\n\nDebug: http://127.0.0.1:{STATE.port}/debug", "text/plain; charset=utf-8")
        html = p.read_text(encoding="utf-8").replace("__VERSION__", VERSION)
        return self._send(200, html)

    def _spotify_token(self):
        global STATE
        p = STATE.auth_dir / "spotify_main.json"
        try:
            if not p.exists():
                return None
            token = json.loads(p.read_text(encoding="utf-8"))
            exp = float(token.get("saved_at", 0)) + float(token.get("expires_in", 0) or 0) - 90
            if token.get("refresh_token") and time.time() >= exp:
                settings = STATE.settings().get("platforms", {}).get("spotify", {})
                payload = {
                    "grant_type": "refresh_token",
                    "refresh_token": token.get("refresh_token"),
                    "client_id": str(settings.get("client_id") or "").strip(),
                }
                secret = str(settings.get("client_secret") or "").strip()
                if secret:
                    payload["client_secret"] = secret
                req = urllib.request.Request(TOKEN_URLS["spotify"], data=urllib.parse.urlencode(payload).encode(), headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"})
                raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
                fresh = json.loads(raw)
                if not fresh.get("refresh_token"):
                    fresh["refresh_token"] = token.get("refresh_token")
                fresh["platform"] = "spotify"
                fresh["account"] = "main"
                fresh["saved_at"] = time.time()
                _json_save(p, fresh)
                token = fresh
            return token
        except Exception as e:
            try:
                now = time.time()
                last = float(getattr(STATE, "_spotify_token_fail_logged_at", 0.0) or 0.0)
                if now - last > 30:
                    STATE._spotify_token_fail_logged_at = now
                    STATE.log("spotify token failed", str(e))
            except Exception:
                pass
            try:
                # Wenn ein Access-Token vorhanden ist, geben wir ihn als letzten Versuch zurück.
                # Spotify kann noch damit antworten, auch wenn ein Refresh gerade wegen falscher
                # Client-Daten 400 liefert. Der erfolgreiche Player-Request korrigiert dann Status/Log.
                if isinstance(token, dict) and str(token.get("access_token") or "").strip():
                    return token
            except Exception:
                pass
            return None

    def _spotify_current_from_api(self):
        global STATE
        token = self._spotify_token()
        if not token or not token.get("access_token"):
            return {}
        try:
            req = urllib.request.Request("https://api.spotify.com/v1/me/player/currently-playing", headers={"Authorization":"Bearer " + token.get("access_token"), "Accept":"application/json"})
            try:
                res = urllib.request.urlopen(req, timeout=12)
            except urllib.error.HTTPError as e:
                if e.code in (204, 404):
                    return {}
                raise
            raw = res.read().decode("utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            item = data.get("item") or {}
            title = item.get("name") or ""
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name"))
            album = (item.get("album") or {}).get("name") or ""
            images = (item.get("album") or {}).get("images") or []
            cover = images[0].get("url") if images else ""
            out = {"title": title, "artist": artists, "album": album, "cover": cover, "active": bool(title), "source": "Spotify"}
            try:
                now = time.time()
                last = float(getattr(STATE, "_spotify_current_ok_logged_at", 0.0) or 0.0)
                if out.get("active") and now - last > 120:
                    STATE._spotify_current_ok_logged_at = now
                    STATE.log("spotify", "status", "connected", "current playback OK")
            except Exception:
                pass
            try:
                npdir = STATE.data / "spotis3mptify" / "nowplaying"
                npdir.mkdir(parents=True, exist_ok=True)
                _json_save(npdir / "nowplaying.json", out)
            except Exception:
                pass
            return out
        except Exception as e:
            try: STATE.log("spotify current failed", str(e))
            except Exception: pass
            return {}

    def _nowplaying(self):
        global STATE
        live = self._spotify_current_from_api()
        if live.get("active"):
            return live
        bases = [
            STATE.data / "spotis3mptify",
        ]
        data = {}
        for base in bases:
            candidates = [base / "nowplaying" / "nowplaying.json", base / "nowplaying.json"]
            for p in candidates:
                try:
                    if p.exists():
                        data = json.loads(p.read_text(encoding="utf-8"))
                        break
                except Exception:
                    pass
            if data:
                break
        def read_txt(*names):
            for base in bases:
                for n in names:
                    for folder in [base / "nowplaying", base]:
                        p = folder / n
                        try:
                            if p.exists():
                                return p.read_text(encoding="utf-8").strip()
                        except Exception:
                            pass
            return ""
        title = data.get("title") or data.get("name") or read_txt("nowplaying_title.txt")
        artist = data.get("artist") or data.get("artists") or read_txt("nowplaying_artist.txt")
        album = data.get("album") or read_txt("nowplaying_album.txt")
        cover = data.get("cover") or data.get("cover_url") or read_txt("nowplaying_cover.txt", "nowplaying_url.txt")
        return {"title": title or "Kein Song aktiv", "artist": artist or "", "album": album or "", "cover": cover or "", "active": bool(title and title != "Kein Song aktiv"), "source":"Spotify"}

    def _spotify_browser(self, kind):
        np = self._nowplaying()
        if kind in ("title","song"):
            return self._send(200, self._mini_text(np.get("title","")), "text/html; charset=utf-8")
        if kind == "artist":
            return self._send(200, self._mini_text(np.get("artist","")), "text/html; charset=utf-8")
        if kind in ("line-up","line-down"):
            return self._send(200, '<!doctype html><html><body style="margin:0;background:transparent;overflow:hidden"><div style="height:4px;width:100vw;background:#1ed760;box-shadow:0 0 18px #1ed760"></div></body></html>')
        if kind == "cover":
            return self._page("browser_cover.html")
        return self._send(404, "Not found", "text/plain")

    def _mini_text(self, text):
        text = (text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/css/overlay.css?v={VERSION}"></head><body class="transparent"><div class="spotifyText">{text}</div></body></html>'

    def _clean_login(self, value):
        return str(value or "").strip().lstrip("@#").lower()

    def _clean_token(self, value):
        t = str(value or "").strip()
        return t[6:].strip() if t.startswith("oauth:") else t

    def _redirect_for(self, cfg, platform, account):
        raw = str(cfg.get("redirect_uri") or cfg.get("redirect_url") or DEFAULT_REDIRECTS.get(platform) or "").strip()
        if raw:
            return raw
        return f"http://127.0.0.1:{CALLBACK_PORT}/oauth/callback/{platform}/{account}"

    def _port_from_url(self, url, fallback):
        try:
            parsed = urllib.parse.urlparse(str(url or ""))
            if parsed.port:
                return int(parsed.port)
        except Exception:
            pass
        return int(fallback)

    def _http_json(self, url, *, data=None, headers=None, method="GET", timeout=12):
        body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        h = dict(headers or {})
        if body is not None:
            h.setdefault("Content-Type", "application/x-www-form-urlencoded")
        h.setdefault("Accept", "application/json")
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")
        return json.loads(raw or "{}") if raw.strip() else {}

    def _save_platform_updates(self, platform, updates):
        global STATE
        st = STATE
        s = st.settings()
        cfg = s.setdefault("platforms", {}).setdefault(platform, {})
        cfg.update(updates or {})
        # Keep old webbased UI aliases and original plugin aliases in sync.
        if platform in ("twitch", "youtube", "kick"):
            main = self._clean_login(cfg.get("main") or cfg.get("main_account") or cfg.get("channel"))
            bot = self._clean_login(cfg.get("bot") or cfg.get("bot_account") or cfg.get("bot_username"))
            cfg["main"] = main; cfg["main_account"] = main; cfg["channel"] = main
            cfg["bot"] = bot; cfg["bot_account"] = bot; cfg["bot_username"] = bot
        st.save_settings(s)
        return cfg

    def _twitch_validate(self, token):
        try:
            return self._http_json("https://id.twitch.tv/oauth2/validate", headers={"Authorization":"OAuth " + self._clean_token(token)}, timeout=10)
        except Exception:
            return {}

    def _youtube_channel(self, token):
        try:
            url = "https://www.googleapis.com/youtube/v3/channels?" + urllib.parse.urlencode({"part":"id,snippet", "mine":"true", "maxResults":"1"})
            data = self._http_json(url, headers={"Authorization":"Bearer " + self._clean_token(token)}, timeout=10)
            items = data.get("items") or []
            if not items:
                return {}
            item = items[0] if isinstance(items[0], dict) else {}
            sn = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            return {"id": str(item.get("id") or ""), "title": str(sn.get("title") or ""), "customUrl": str(sn.get("customUrl") or "")}
        except Exception as e:
            try: STATE.log("youtube channel lookup failed", str(e))
            except Exception: pass
            return {}

    def _kick_get_user(self, token):
        for url in ("https://api.kick.com/public/v1/users", "https://api.kick.com/public/v1/users/me"):
            try:
                data = self._http_json(url, headers={"Authorization":"Bearer " + self._clean_token(token)}, timeout=10)
                if isinstance(data.get("data"), list) and data["data"]:
                    return data["data"][0]
                if isinstance(data.get("data"), dict):
                    return data["data"]
                if isinstance(data, dict) and (data.get("name") or data.get("user_id") or data.get("id")):
                    return data
            except Exception:
                continue
        return {}

    def _kick_get_channel(self, token):
        for url in ("https://api.kick.com/public/v1/channels", "https://api.kick.com/public/v1/channels/me"):
            try:
                data = self._http_json(url, headers={"Authorization":"Bearer " + self._clean_token(token)}, timeout=10)
                if isinstance(data.get("data"), list) and data["data"]:
                    return data["data"][0]
                if isinstance(data.get("data"), dict):
                    return data["data"]
            except Exception:
                continue
        return {}

    def _kick_resolve_chatroom_after_main_auth(self, channel_slug: str):
        try:
            STATE.log("kick_chat", "browser chatroom resolver disabled; no browser window opened after OAuth")
        except Exception:
            pass

    def _oauth_state_prefix(self, platform, account):
        # gla2 carries platform/account in the state itself. The verifier is appended
        # in _oauth_start for PKCE platforms, so callbacks stay resolvable even if
        # a stale callback server or a missing state file would otherwise lose the mapping.
        return "gla2." + str(platform or "").lower().strip() + "." + str(account or "").lower().strip() + "."

    def _remember_oauth_pending(self, platform, account, state, verifier, redirect):
        """Persist pending OAuth state in two places so callback ports and old browser windows
        can still resolve the login even if the file was missed or an old state file exists."""
        global STATE
        st = STATE
        data = {
            "platform": str(platform or "").lower().strip(),
            "account": "main" if str(account or "").lower().strip() == "main" else "bot",
            "state": str(state or ""),
            "verifier": str(verifier or ""),
            "redirect_uri": str(redirect or ""),
            "created": time.time(),
        }
        try:
            _json_save(st.auth_dir / f"{data['platform']}_{data['account']}_state.json", data)
        except Exception as e:
            try: st.log("oauth state file save failed", str(e))
            except Exception: pass
        try:
            s = st.settings()
            pend = s.setdefault("oauth_pending", {})
            # Drop stale entries after roughly one hour.
            now = time.time()
            for k in list(pend.keys()):
                try:
                    if now - float((pend.get(k) or {}).get("created") or 0) > 3600:
                        pend.pop(k, None)
                except Exception:
                    pend.pop(k, None)
            pend[data["state"]] = data
            pend[f"latest:{data['platform']}:{data['account']}"] = data
            st.save_settings(s)
        except Exception as e:
            try: st.log("oauth pending save failed", str(e))
            except Exception: pass

    def _pending_oauth_from_settings(self, got_state):
        global STATE
        try:
            s = STATE.settings()
            pend = s.get("oauth_pending") or {}
            data = pend.get(str(got_state or ""))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _platform_from_callback_port(self):
        try:
            port = int(self.server.server_address[1])
        except Exception:
            port = 0
        if port == 17564:
            return "twitch"
        if port == 17566:
            return "youtube"
        if port == 17865:
            return "kick"
        if port == 5173:
            return "spotify"
        return ""

    def _platform_account_from_state_text(self, got_state):
        text = str(got_state or "").lower().strip()
        # Accept every state format we have ever generated: gla1.platform.account.xxx,
        # gla2.platform.account.xxx.verifier and even cached/old variants that only
        # contain the platform/account words. This prevents the callback page from
        # dying before token exchange just because the pending file was not found.
        for prefix in ("gla2.", "gla1.", "gla."):
            if text.startswith(prefix):
                parts = text.split(".")
                if len(parts) >= 3 and parts[1] in TOKEN_URLS:
                    return parts[1], ("main" if parts[2] == "main" else "bot")
        for plat in ("twitch", "youtube", "kick", "spotify"):
            if plat in text:
                acc = "main" if ".main." in text or ":main:" in text or "-main-" in text else "bot"
                if plat == "spotify":
                    acc = "main"
                return plat, acc
        return "", ""

    def _platform_from_query_hint(self, query_dict):
        try:
            scopes = " ".join(query_dict.get("scope") or [])
            scopes = urllib.parse.unquote(scopes).lower()
            if "channel:manage:broadcast" in scopes or "chat:edit" in scopes or "moderator:manage" in scopes:
                return "twitch"
            if "youtube" in scopes:
                return "youtube"
            if "playlist-" in scopes or "user-read" in scopes or "ugc-image-upload" in scopes:
                return "spotify"
            if "chat:write" in scopes or "channel:write" in scopes:
                return "kick"
        except Exception:
            pass
        return ""

    def _latest_pending_for_platform(self, platform):
        global STATE
        st = STATE
        try:
            candidates = []
            for p in st.auth_dir.glob(f"{platform}_*_state.json"):
                data = _json_load(p, {})
                candidates.append((p.stat().st_mtime, p, data))
            if candidates:
                candidates.sort(reverse=True, key=lambda x: x[0])
                parts = candidates[0][1].stem.split("_")
                if len(parts) >= 3:
                    return parts[0], parts[1], candidates[0][2]
        except Exception:
            pass
        try:
            s = st.settings(); pend = s.get("oauth_pending") or {}
            candidates = [v for v in pend.values() if isinstance(v, dict) and v.get("platform") == platform]
            if candidates:
                candidates.sort(key=lambda x: float(x.get("created") or 0), reverse=True)
                d = candidates[0]
                return str(d.get("platform")), str(d.get("account") or ("main" if platform == "spotify" else "bot")), d
        except Exception:
            pass
        return "", "", {}

    def _resolve_oauth_callback_target(self, got_state, query_dict=None):
        """Return (platform, account, state_data) for callback/?code=...&state=...
        Resolution order: auth state file, settings backup, embedded state prefix, port/query fallback."""
        global STATE
        st = STATE
        got_state = str(got_state or "")
        if got_state:
            try:
                matches = []
                for p in st.auth_dir.glob("*_state.json"):
                    data = _json_load(p, {})
                    if data.get("state") == got_state:
                        matches.append((p, data))
                if matches:
                    matches.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
                    parts = matches[0][0].stem.split("_")
                    if len(parts) >= 3:
                        return parts[0], parts[1], matches[0][1]
            except Exception as e:
                try: st.log("oauth state file resolve failed", str(e))
                except Exception: pass

            data = self._pending_oauth_from_settings(got_state)
            if data.get("platform") and data.get("account"):
                return str(data.get("platform")), str(data.get("account")), data

            p2, a2 = self._platform_account_from_state_text(got_state)
            if p2:
                data = {"state": got_state}
                # gla2 stores the PKCE verifier after the fourth dot. For Twitch it is harmless.
                if got_state.startswith("gla2."):
                    parts = got_state.split(".", 4)
                    if len(parts) == 5:
                        data["verifier"] = parts[4]
                return p2, a2, data

        # Last safety net: infer by callback port/query and take the newest pending state for that platform.
        platform = self._platform_from_callback_port() or self._platform_from_query_hint(query_dict or {})
        if platform:
            p3, a3, d3 = self._latest_pending_for_platform(platform)
            if p3:
                return p3, a3, d3
            # Twitch can exchange without PKCE. Spotify/YouTube/Kick need the verifier, so for them
            # we still return the platform to show the real token-exchange error instead of the useless
            # "keiner Anmeldung" page.
            return platform, ("main" if platform in ("twitch", "spotify") else "bot"), {}

        return "", "", {}

    def _oauth_start(self, platform, account):
        global STATE
        st = STATE
        platform = str(platform or "").lower().strip()
        account = "main" if str(account or "").lower().strip() == "main" else "bot"
        if platform == "spotify":
            account = "main"
        s = st.settings()
        cfg = s.get("platforms", {}).get(platform, {})
        client_id = str(cfg.get("client_id") or "").strip()
        if not client_id:
            return self._send(400, "Client ID fehlt. Erst speichern.", "text/plain; charset=utf-8")
        if platform not in AUTH_URLS:
            return self._send(400, "Für diese Plattform gibt es kein OAuth.", "text/plain; charset=utf-8")

        redirect = self._redirect_for(cfg, platform, account)
        cfg["redirect_uri"] = redirect
        if platform != "spotify":
            cfg["redirect_url"] = redirect
        if platform in ("twitch", "youtube"):
            cfg["redirect_port"] = self._port_from_url(redirect, 17564 if platform == "twitch" else 17566)
        s.setdefault("platforms", {})[platform] = cfg
        st.save_settings(s)

        verifier = secrets.token_urlsafe(64)
        # Put the PKCE verifier into the state as a second backup. This fixes the
        # ugly "Callback konnte keiner Anmeldung zugeordnet werden" case for
        # Spotify/YouTube/Kick if an old callback process or stale browser tab ate
        # the normal pending-state file. Twitch ignores the verifier.
        state = self._oauth_state_prefix(platform, account) + secrets.token_urlsafe(18) + "." + verifier
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self._remember_oauth_pending(platform, account, state, verifier, redirect)

        scopes = str(cfg.get("main_scopes" if account == "main" else "scopes") or DEFAULT_SCOPES.get(platform, {}).get(account) or DEFAULT_SCOPES.get(platform, {}).get("main") or "").strip()
        params = {"client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": scopes, "state": state}
        # Twitch muss force_verify behalten, damit man beim Bot-Login sauber
        # den aktuell eingeloggten Twitch-Account wechseln kann.
        if platform == "twitch":
            params["force_verify"] = "true"
        if platform in ("youtube", "spotify", "kick"):
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        if platform == "youtube":
            params["access_type"] = "offline"
            params["prompt"] = "consent"
            params["include_granted_scopes"] = "true"
        if platform == "kick" and "127.0.0.1" in redirect:
            params = {"redirect": "127.0.0.1", **params}

        full = AUTH_URLS[platform] + "?" + urllib.parse.urlencode(params)
        self.send_response(302)
        self.send_header("Location", full)
        self.end_headers()

    def _oauth_callback_auto(self, query):
        q = urllib.parse.parse_qs(query)
        got_state = (q.get("state") or [""])[0]
        platform, account, state_data = self._resolve_oauth_callback_target(got_state, q)
        if platform and account:
            return self._oauth_callback(platform, account, query, state_data)
        try: STATE.log("oauth unresolved", "port=" + str(self.server.server_address[1]), "state=" + got_state, "query=" + str(q))
        except Exception: pass
        return self._send(400, "OAuth Callback konnte keiner Plattform zugeordnet werden. Diese Seite kommt sehr wahrscheinlich von einem alten Browser-/Prozess-Callback. Bitte Webbased komplett schließen und die aktuelle Version starten. Debug: Port=" + str(getattr(self.server, 'server_address', ['', ''])[1]) + " State=" + got_state[:80], "text/plain; charset=utf-8")

    def _oauth_callback(self, platform, account, query, resolved_state_data=None):
        global STATE
        st = STATE
        platform = str(platform or "").lower().strip()
        account = "main" if str(account or "").lower().strip() == "main" else "bot"
        if platform == "spotify":
            account = "main"
        q = urllib.parse.parse_qs(query)
        if "error" in q:
            return self._send(400, "OAuth Fehler: " + str((q.get("error") or [""])[0]), "text/plain; charset=utf-8")
        code = (q.get("code") or [""])[0]
        got_state = (q.get("state") or [""])[0]
        state_path = st.auth_dir / f"{platform}_{account}_state.json"
        state_data = dict(resolved_state_data or {})
        if not state_data:
            state_data = _json_load(state_path, {})
        if not state_data and got_state:
            state_data = self._pending_oauth_from_settings(got_state)
        if not code:
            return self._send(400, "OAuth Code fehlt.", "text/plain; charset=utf-8")
        if state_data.get("state") and got_state != state_data.get("state"):
            return self._send(400, "OAuth State passt nicht.", "text/plain; charset=utf-8")
        s = st.settings()
        cfg = s.get("platforms", {}).get(platform, {})
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        redirect = state_data.get("redirect_uri") or self._redirect_for(cfg, platform, account)
        payload = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect, "client_id": client_id}
        if platform in ("youtube", "spotify", "kick") and state_data.get("verifier"):
            payload["code_verifier"] = state_data.get("verifier", "")
        if client_secret:
            payload["client_secret"] = client_secret
        try:
            token = self._http_json(TOKEN_URLS[platform], data=payload, method="POST", timeout=25)
            access = self._clean_token(token.get("access_token"))
            refresh = str(token.get("refresh_token") or "").strip()
            if not access:
                return self._send(500, "Token-Austausch lieferte keinen Access Token.", "text/plain; charset=utf-8")
            token["platform"] = platform; token["account"] = account; token["saved_at"] = time.time()
            _json_save(st.auth_dir / f"{platform}_{account}.json", token)

            updates = {"redirect_uri": redirect, "main_disconnected_at" if account == "main" else "bot_disconnected_at": 0}
            if platform != "spotify":
                updates["redirect_url"] = redirect
            if platform == "twitch":
                meta = self._twitch_validate(access)
                login = self._clean_login(meta.get("login") or cfg.get("main_account" if account == "main" else "bot_account"))
                uid = str(meta.get("user_id") or "").strip()
                scopes = meta.get("scopes") or meta.get("scope") or cfg.get("main_scopes" if account == "main" else "scopes") or DEFAULT_SCOPES["twitch"][account]
                if isinstance(scopes, list): scopes = " ".join(sorted(str(x).strip() for x in scopes if str(x).strip()))
                if account == "main":
                    updates.update({"main_access_token": access, "main_refresh_token": refresh or cfg.get("main_refresh_token", ""), "main_oauth_login": login, "main_oauth_user_id": uid, "main_scopes": str(scopes), "main_saved_at": int(time.time()), "main_connection_status": f"Main verbunden als {login}", "broadcaster_user_id": uid, "broadcaster_id": uid})
                    if login and not self._clean_login(cfg.get("main_account") or cfg.get("main")): updates.update({"main": login, "main_account": login, "channel": login})
                else:
                    updates.update({"access_token": access, "refresh_token": refresh or cfg.get("refresh_token", ""), "oauth_login": login, "oauth_user_id": uid, "scopes": str(scopes), "saved_at": int(time.time()), "connection_status": f"Verbunden als {login}"})
                    if login and not self._clean_login(cfg.get("bot_account") or cfg.get("bot")): updates.update({"bot": login, "bot_account": login, "bot_username": login})
            elif platform == "youtube":
                ch = self._youtube_channel(access)
                title = ch.get("title") or ch.get("id") or ("YouTube" if not account else account)
                scopes = str(token.get("scope") or cfg.get("main_scopes" if account == "main" else "scopes") or DEFAULT_SCOPES["youtube"][account]).strip()
                if account == "main":
                    updates.update({"main_access_token": access, "main_refresh_token": refresh or cfg.get("main_refresh_token", ""), "main_scopes": scopes, "main_saved_at": int(time.time()), "main_channel_id": ch.get("id", ""), "main_channel_title": ch.get("title", ""), "main_channel_custom_url": ch.get("customUrl", ""), "broadcaster_channel_id": ch.get("id", ""), "main_connection_status": f"Main verbunden als {title}"})
                else:
                    updates.update({"access_token": access, "refresh_token": refresh or cfg.get("refresh_token", ""), "scopes": scopes, "saved_at": int(time.time()), "bot_channel_id": ch.get("id", ""), "bot_channel_title": ch.get("title", ""), "bot_channel_custom_url": ch.get("customUrl", ""), "connection_status": f"Bot verbunden als {title}"})
            elif platform == "kick":
                user = self._kick_get_user(access)
                channel = self._kick_get_channel(access)
                username = self._clean_login(user.get("name") or user.get("username") or cfg.get("main_account" if account == "main" else "bot_account"))
                uid = str(user.get("user_id") or user.get("id") or "").strip()
                slug = self._clean_login(channel.get("slug") or channel.get("channel_slug") or cfg.get("main_account") or username)
                broadcaster_id = str(channel.get("broadcaster_user_id") or channel.get("id") or uid or "").strip()
                scopes = str(token.get("scope") or cfg.get("main_scopes" if account == "main" else "scopes") or DEFAULT_SCOPES["kick"][account]).strip()
                if account == "main":
                    updates.update({"enabled": True, "main_access_token": access, "main_refresh_token": refresh or cfg.get("main_refresh_token", ""), "main_scopes": scopes, "main_saved_at": int(time.time()), "main_user_id": uid, "main_username": username, "broadcaster_user_id": broadcaster_id, "channel_id": broadcaster_id, "channel_slug": slug, "chatroom_id": "", "chatroom_channel": "", "main_connection_status": f"Verbunden als {slug or username}"})
                    if slug and not self._clean_login(cfg.get("main_account") or cfg.get("main")): updates.update({"main": slug, "main_account": slug, "channel": slug})
                else:
                    updates.update({"enabled": True, "access_token": access, "refresh_token": refresh or cfg.get("refresh_token", ""), "scopes": scopes, "saved_at": int(time.time()), "bot_user_id": uid, "bot_username": username, "bot_account": username, "connection_status": f"Verbunden als {username}"})
                    if username and not self._clean_login(cfg.get("bot_account") or cfg.get("bot")): updates.update({"bot": username, "bot_account": username, "bot_username": username})
            elif platform == "spotify":
                updates.update({"access_token": access, "refresh_token": refresh or cfg.get("refresh_token", ""), "scopes": str(token.get("scope") or cfg.get("scopes") or DEFAULT_SCOPES["spotify"]["main"]), "saved_at": int(time.time()), "connection_status": "Verbunden"})
            self._save_platform_updates(platform, updates)
            if platform == "kick" and account == "main":
                self._kick_resolve_chatroom_after_main_auth(updates.get("channel_slug") or updates.get("main_username") or cfg.get("channel") or cfg.get("main_account"))
            if platform == "spotify":
                try: st.log("spotify", "status", "connected", "OAuth gespeichert")
                except Exception: pass
            if platform == "twitch":
                try:
                    old = st.plugin_instances.get("twitch_chat")
                    if old is not None:
                        try: old.stop(wait=True)
                        except TypeError: old.stop()
                    st.plugin_manager.start_plugin("twitch_chat")
                except Exception as exc:
                    st.log("twitch_chat", "restart after oauth failed", exc)
            try:
                state_path.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                s2 = st.settings()
                pend = s2.get("oauth_pending") or {}
                pend.pop(got_state, None)
                pend.pop(f"latest:{platform}:{account}", None)
                s2["oauth_pending"] = pend
                st.save_settings(s2)
            except Exception:
                pass
            main_url = f"http://127.0.0.1:{st.port}/plattformen?v={VERSION}&auth={platform}"
            title = f"{esc_html(platformLabel(platform) if 'platformLabel' in globals() else platform)} verbunden"
            return self._send(200, f"""<!doctype html><html><head><meta charset='utf-8'><title>Verbunden</title><style>body{{margin:0;background:#070914;color:#fff;font-family:Segoe UI,Arial,sans-serif;display:grid;place-items:center;height:100vh}}.box{{background:#15182a;border:1px solid #303656;border-radius:18px;padding:28px;max-width:520px;text-align:center}}a{{color:#8d6bff}}</style></head><body><div class='box'><h2>{esc_html(platform)} {esc_html(account)} verbunden</h2><p>Token wurde original-kompatibel gespeichert.</p><p>Dieses Fenster schließt sich gleich automatisch.</p><p><a href='{main_url}'>Zurück zu Plattformen</a></p></div><script>setTimeout(()=>{{try{{window.open('','_self');window.close();}}catch(e){{}}}},3000);setTimeout(()=>{{document.body.innerHTML='<div class=\"box\"><h2>Kann automatisch nicht geschlossen werden</h2><p>Der Login ist gespeichert. Du kannst dieses Fenster schließen.</p><p><a href=\"{main_url}\">Zurück zu Plattformen</a></p></div>'; }},3800);</script></body></html>""")
        except urllib.error.HTTPError as e:
            try: detail = e.read().decode("utf-8", errors="replace")
            except Exception: detail = str(e)
            return self._send(500, f"Token-Austausch fehlgeschlagen: HTTP {e.code} {detail[:800]}", "text/plain; charset=utf-8")
        except Exception as e:
            return self._send(500, "Token-Austausch fehlgeschlagen: " + str(e), "text/plain; charset=utf-8")


def _win_hidden_flags():
    return 0x08000000 if os.name == "nt" else 0


def _taskkill_pid(pid: int) -> bool:
    if os.name != "nt":
        return False
    try:
        if int(pid) == os.getpid():
            return False
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_win_hidden_flags(), timeout=8)
        return True
    except Exception:
        return False


def _kill_old_webbased_processes() -> int:
    """Kill old webbased EXEs / old python launcher processes.
    Closing the browser tab only closes the UI, not the local server. Old versions
    then keep owning OAuth callback ports and steal Twitch/Spotify callbacks.
    """
    if os.name != "nt":
        return 0
    killed = 0
    me = os.getpid()
    try:
        ps = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            "$me=" + str(me) + "; "
            "$p=Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $me -and ("
            "$_.Name -like '*webbased*.exe' -or "
            "$_.CommandLine -match 'run_webbased\\.py' -or "
            "$_.CommandLine -match 'godisalotachat.*webbased'"
            ") }; $p | ForEach-Object { $_.ProcessId }"
        ]
        out = subprocess.check_output(ps, text=True, encoding="utf-8", errors="ignore", creationflags=_win_hidden_flags(), timeout=10)
        for line in out.splitlines():
            line = line.strip()
            if not line.isdigit():
                continue
            pid = int(line)
            if pid and pid != me and _taskkill_pid(pid):
                killed += 1
        if killed:
            time.sleep(0.6)
    except Exception:
        pass
    return killed


def _schedule_hard_exit(delay: float = 0.2):
    def _bye():
        try:
            time.sleep(max(0.0, float(delay)))
        except Exception:
            pass
        os._exit(0)
    threading.Thread(target=_bye, daemon=True).start()


def _start_ui_watchdog():
    def _watch():
        global STATE
        while True:
            time.sleep(3.0)
            st = STATE
            if st is None or st.shutting_down:
                continue
            try:
                if st.ui_heartbeat_enabled and st.last_ui_heartbeat > 0 and time.time() - st.last_ui_heartbeat > 8.0:
                    now = time.time()
                    st.ui_heartbeat_lost = True
                    # Der Backend-Server ist das Fundament fuer Plugins, Overlays und Callback-Listener.
                    # Ein verlorener UI-Heartbeat darf deshalb niemals den Server beenden und auch
                    # keinen neuen Browser-Tab aufmachen. Stattdessen wird ein Reload-Flag gesetzt,
                    # das der vorhandene Tab beim naechsten Heartbeat im selben Tab verarbeitet.
                    if now - float(getattr(st, "last_ui_reload_request", 0.0) or 0.0) > 15.0:
                        st.last_ui_reload_request = now
                        st.ui_reload_requested = True
                        st.ui_reload_nonce = _now_ms()
                        try: st.log("ui", "main ui heartbeat lost - reload requested for existing tab")
                        except Exception: pass
            except Exception:
                pass
    threading.Thread(target=_watch, daemon=True).start()

def _kill_process_using_port(port: int) -> bool:
    """Windows safety net: old webbased callback servers on 17564/17566/17865/5173
    are the usual reason why OAuth callbacks hit an outdated process and show
    "keiner Anmeldung zugeordnet". Kill only the process that owns that listening
    port, and never kill our own PID.
    """
    if os.name != "nt":
        return False
    try:
        me = os.getpid()
        cmd = ["netstat", "-ano", "-p", "tcp"]
        out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore", creationflags=_win_hidden_flags())
        pids = set()
        suffixes = (f":{int(port)}", f":{int(port)} ")
        for line in out.splitlines():
            up = line.upper()
            if "LISTENING" not in up:
                continue
            cols = line.split()
            if len(cols) < 5:
                continue
            local = cols[1]
            pid = cols[-1]
            if any(local.endswith(suf) for suf in suffixes):
                try:
                    ipid = int(pid)
                except Exception:
                    continue
                if ipid and ipid != me:
                    pids.add(ipid)
        killed = False
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_win_hidden_flags(), timeout=6)
                killed = True
            except Exception:
                pass
        if killed:
            time.sleep(0.4)
        return killed
    except Exception:
        return False


def _free_callback_ports_before_start():
    _kill_old_webbased_processes()
    for p in CALLBACK_PORTS:
        _kill_process_using_port(int(p))


def _write_pid(port: int):
    try:
        p = Path(tempfile.gettempdir()) / f"godisalotachat_webbased_{port}.pid"
        p.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

class ThreadingHTTPServerV6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


class WebbasedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class WebbasedHTTPServerV6(ThreadingHTTPServerV6):
    daemon_threads = True

def _start_server_on(address, port):
    cb = WebbasedHTTPServer((address, int(port)), Handler)
    t = threading.Thread(target=cb.serve_forever, daemon=True)
    t.start()
    return cb

def _start_server_on_v6(port):
    cb = WebbasedHTTPServerV6(("::1", int(port)), Handler)
    t = threading.Thread(target=cb.serve_forever, daemon=True)
    t.start()
    return cb

def _start_extra_callback_servers(main_port: int):
    global STATE
    servers = []
    for port in CALLBACK_PORTS:
        if int(port) == int(main_port):
            continue
        # 0.0.0.0 catches localhost->IPv4. ::1 catches browsers that prefer IPv6 localhost.
        # If one bind fails, keep the other; the debug log shows exactly which one is active.
        for label, maker in (
            ("ipv4", lambda p=port: _start_server_on("0.0.0.0", p)),
            ("ipv6", lambda p=port: _start_server_on_v6(p)),
        ):
            try:
                cb = maker()
                servers.append(cb)
                try: STATE.log("callback-listen", label, f"http://localhost:{port}/callback")
                except Exception: pass
            except OSError as e:
                try: STATE.log("callback-port-busy", label, port, str(e))
                except Exception: pass
    return servers

def run(base_dir: str, open_browser: bool = True):
    global STATE
    _free_callback_ports_before_start()
    preferred_port = MAIN_PORT
    port = _find_free_port(preferred_port)
    STATE = AppState(base_dir, port)
    try:
        STATE.plugin_manager.ensure_started()
    except Exception as exc:
        try: STATE.log("plugins", "autostart failed", exc)
        except Exception: pass
    _start_ui_watchdog()
    _write_pid(port)
    httpd = WebbasedHTTPServer(("127.0.0.1", port), Handler)
    callback_servers = _start_extra_callback_servers(port)
    url = f"http://127.0.0.1:{port}/?v={VERSION}&t={_now_ms()}"
    STATE.main_url = url
    if port != preferred_port:
        STATE.log("port_warning", f"{preferred_port} belegt, nutze {port}", "hauptseite nutzt ersatzport; callback bleibt 5173 falls frei")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        STATE.log("listen", url)
    except Exception:
        pass
    print(f"{APP_NAME} Ver. {VERSION} läuft auf {url}")
    print("OAuth Callback-Ports: " + ", ".join(f"http://127.0.0.1:{p}/callback" for p in CALLBACK_PORTS))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        try:
            STATE.mark_clean_shutdown("keyboard interrupt")
        except Exception:
            pass
        pass
    except Exception as exc:
        try:
            STATE.log("crash", traceback.format_exc())
            STATE.mark_unclean_exit("server exception", traceback.format_exc())
        except Exception:
            pass
        raise
    finally:
        try:
            STATE.plugin_manager.stop_all()
        except Exception:
            pass
        try:
            STATE._close_obs_connection()
        except Exception:
            pass
        try:
            if STATE is not None and not STATE.shutting_down:
                STATE.mark_clean_shutdown("server stopped")
        except Exception:
            pass
