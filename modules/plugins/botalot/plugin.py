from __future__ import annotations

import sys
import threading
import time
import re
from pathlib import Path
from typing import Any

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

from ai_client import OpenAIChatClient
from common import as_bool, clean_text, to_int
from context_memory import ContextMemory
PLUGIN_VERSION = "1.22"
PLUGIN_NAME = f"botalot ver. {PLUGIN_VERSION}"


def _data_dir() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == "modules":
            return parent.parent / "data" / "botalot"
    return _PLUGIN_DIR / "data"


def _is_service_command(text: str) -> bool:
    low = clean_text(text).lower().strip()
    return any(low == cmd or low.startswith(cmd + " ") for cmd in ("!sr", "!sr+", "!yt"))


class BotalotPlugin(ProviderPlugin):
    plugin_id = "botalot"
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = "AI chat bot. Platform auth and sending are owned by the core platform settings."

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._enabled = False
        self._context = ContextMemory(10)
        self._ai = OpenAIChatClient(self._log)
        self._last_reply_at = 0.0
        self._worker_lock = threading.Lock()

    def settings_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "enabled", "label": "Bot aktiv", "type": "bool"},
            {"key": "openai_connection_status", "label": "OpenAI / ChatGPT", "readonly": True, "placeholder": "aus Core"},
            {"key": "openai_model", "label": "OpenAI Modell", "type": "select", "options": [{"value": "", "label": "Modelle aus API-Key laden..."}]},
            {"key": "openai_prompt_id", "label": "OpenAI Prompt ID", "placeholder": "pmpt_..."},
            {"key": "openai_prompt_version", "label": "OpenAI Prompt Version", "placeholder": "leer = aktuelle Version"},
            {"key": "custom_system_prompt", "label": "Eigener Prompt", "type": "multiline", "wide": True},
            {"key": "trigger_commands", "label": "Commands", "placeholder": "!bot,!ask,!ai", "wide": True},
            {"key": "reply_to_source", "label": "Antwort an Ursprungsplattform senden", "type": "bool"},
            {"key": "emit_to_desktop", "label": "Antwort im Desktopchat anzeigen", "type": "bool"},
            {"key": "cooldown_seconds", "label": "Cooldown Sekunden", "type": "number", "min": 0, "max": 600},
            {"key": "context_messages", "label": "Kontext-Nachrichten pro User", "type": "number", "min": 1, "max": 30},
            {"key": "max_response_chars", "label": "Max Antwortzeichen", "type": "number", "min": 40, "max": 500},
        ]

    def default_settings(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "openai_connection_status": "aus Core",
            "openai_model": "gpt-5-mini",
            "openai_prompt_id": "",
            "openai_prompt_version": "",
            "custom_system_prompt": "Du bist ein Chatbot fuer einen Livestream. Bleibe im Charakter, reagiere natuerlich und halte dich an die Kanalregeln.",
            "trigger_commands": "!bot,!ask,!ai",
            "reply_to_source": True,
            "emit_to_desktop": True,
            "cooldown_seconds": 8,
            "context_messages": 8,
            "max_response_chars": 200,
        }

    def _log(self, *parts: Any) -> None:
        msg = " ".join(str(p) for p in parts if p is not None)
        if self._host is not None:
            try:
                self._host.log(self.plugin_id, msg)
                return
            except Exception:
                pass
        print(f"[{self.plugin_id}] {msg}")

    def _host_platform_settings(self, platform: str) -> dict[str, Any]:
        host = self._host
        if host is None:
            return {}
        for name in ("platform_settings", "get_platform_settings"):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    data = fn(platform)
                    if isinstance(data, dict):
                        return dict(data)
                except Exception:
                    pass
        return {}

    def _effective_settings(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(self.default_settings())
        merged.update(self._settings if settings is None else dict(settings or {}))
        if not str(merged.get("custom_system_prompt") or "").strip() and str(merged.get("base_system_prompt") or "").strip():
            merged["custom_system_prompt"] = str(merged.get("base_system_prompt") or "").strip()
        openai = self._host_platform_settings("openai")
        merged["openai_api_key"] = str(openai.get("api_key") or "").strip()
        merged["openai_organization"] = str(openai.get("organization") or "").strip()
        merged["openai_project"] = str(openai.get("project") or "").strip()
        merged["openai_enabled"] = as_bool(openai.get("enabled"), True)
        merged["openai_connection_status"] = "OpenAI API-Key aus Core geladen" if merged["openai_api_key"] else "OpenAI API-Key fehlt im Core"
        return merged

    def _current_settings(self) -> dict[str, Any]:
        host = self._host
        state = getattr(host, "state", None) if host is not None else None
        getter = getattr(state, "plugin_settings", None) if state is not None else None
        if callable(getter):
            try:
                fresh = getter(self.plugin_id, self)
                if isinstance(fresh, dict):
                    self._settings.update(fresh)
            except Exception:
                pass
        settings = self._effective_settings(self._settings)
        self._enabled = as_bool(settings.get("enabled"), True)
        self._context.resize(to_int(settings.get("context_messages"), 8, 1, 30))
        return settings

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._settings = self._effective_settings(settings)
        self._enabled = as_bool(self._settings.get("enabled"), True)
        self._context.resize(to_int(self._settings.get("context_messages"), 8, 1, 30))
        host.set_status(self.plugin_id, PluginStatus("connected" if self._enabled else "disabled", PLUGIN_NAME + (" aktiv" if self._enabled else " deaktiviert")))

    def stop(self, *args, **kwargs) -> None:
        self._enabled = False
        if self._host is not None:
            self._host.set_status(self.plugin_id, PluginStatus("stopped", "Stopped"))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        cfg = self._effective_settings(settings)
        if not as_bool(cfg.get("openai_enabled"), True):
            return False, "OpenAI ist im Core deaktiviert."
        return self._ai.test_connection(cfg)

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        if host is not None:
            self._host = host
        if key == "button_test_openai_connection":
            ok, msg = self.test_connection(self._settings)
            self._log(msg)
            return ok
        return False

    handle_settings_button = on_settings_button
    on_settings_action = on_settings_button

    def _message_platform(self, plugin_id: str, payload: Any) -> str:
        if isinstance(payload, dict):
            raw = payload.get("platform") or payload.get("source_plugin_id") or plugin_id
        else:
            raw = getattr(payload, "platform", "") or getattr(payload, "source_plugin_id", "") or plugin_id
        text = str(raw or "").strip().lower()
        return {"twitch_chat": "twitch", "tiktok_chat": "tiktok", "tiktok_live": "tiktok", "youtube_chat": "youtube", "kick_chat": "kick"}.get(text, text)

    def _message_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return clean_text(payload.get("text") or payload.get("message") or payload.get("content") or payload.get("comment") or "")
        return clean_text(getattr(payload, "text", "") or getattr(payload, "message", "") or "")

    def _message_username(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return clean_text(payload.get("username") or payload.get("display_name") or payload.get("user") or "")
        return clean_text(getattr(payload, "username", "") or getattr(payload, "display_name", "") or "")

    def _message_channel(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return clean_text(payload.get("channel") or "")
        return clean_text(getattr(payload, "channel", "") or "")

    def _message_type(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return str(payload.get("message_type") or payload.get("type") or payload.get("event_type") or "chat").strip().lower()
        return str(getattr(payload, "message_type", "") or getattr(payload, "type", "") or "chat").strip().lower()

    def _command_trigger(self, settings: dict[str, Any], text: str) -> tuple[bool, str, str]:
        commands = self._command_triggers(settings)
        low = text.lower().strip()
        for cmd in commands:
            if low == cmd:
                return True, cmd, text[len(cmd):].strip() or text
            if low.startswith(cmd):
                tail = text[len(cmd):]
                if tail and (tail[0].isspace() or not tail[0].isalnum()):
                    return True, cmd, tail.lstrip(" \t\r\n,.:;!?-").strip() or text
        return False, "", text

    def _command_triggers(self, settings: dict[str, Any]) -> list[str]:
        raw_items = re.split(r"[\n,;]+", str(settings.get("trigger_commands") or ""))
        commands: list[str] = []
        for item in raw_items:
            cmd = item.strip().lower()
            if cmd and cmd not in commands:
                commands.append(cmd)
        path = _data_dir() / "triggers" / "commands.txt"
        try:
            if path.exists():
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    cmd = line.split("#", 1)[0].strip().lower()
                    if cmd and cmd not in commands:
                        commands.append(cmd)
        except Exception as exc:
            self._log(f"Commands-Datei konnte nicht gelesen werden: {exc}")
        return commands

    def on_message(self, msg: Any) -> None:
        if self._message_type(msg) not in {"chat", "message", "comment"}:
            return
        settings = self._current_settings()
        if not self._enabled:
            return
        platform = self._message_platform("", msg)
        if platform not in {"twitch", "tiktok", "youtube", "kick"}:
            return
        username = self._message_username(msg)
        text = self._message_text(msg)
        if not username or not text:
            return
        if _is_service_command(text):
            return
        self._context.add(platform, username, text)
        command_hit, command, command_text = self._command_trigger(settings, text)
        if not command_hit:
            return
        reason = command
        text = command_text
        self._log(f"Trigger erkannt: {reason} von {username} auf {platform}")
        if not str(settings.get("openai_api_key") or "").strip():
            self._log("AI-Antwort uebersprungen: OpenAI API-Key fehlt im Core.")
            return
        cooldown = to_int(settings.get("cooldown_seconds"), 8, 0, 600)
        now = time.time()
        if cooldown and now - self._last_reply_at < cooldown:
            self._log(f"AI-Antwort uebersprungen: Cooldown noch {int(cooldown - (now - self._last_reply_at))}s.")
            return
        if not self._worker_lock.acquire(blocking=False):
            self._log("AI-Antwort uebersprungen: vorherige Antwort laeuft noch.")
            return
        self._last_reply_at = now
        threading.Thread(target=self._reply_worker, args=(settings, platform, username, text, reason, self._message_channel(msg)), daemon=True, name="botalot-ai-reply").start()

    def _reply_worker(self, settings: dict[str, Any], platform: str, username: str, text: str, reason: str, channel: str) -> None:
        try:
            context = self._context.format_recent_for_user(platform, username, to_int(settings.get("context_messages"), 8, 1, 30))
            reply = self._ai.generate(settings, platform, username, text, reason, context)
            if not reply:
                return
            if as_bool(settings.get("emit_to_desktop"), True) and self._host is not None:
                self._host.emit_message(self.plugin_id, {
                    "platform": platform,
                    "username": "botalot",
                    "display_name": "botalot",
                    "text": reply,
                    "message": reply,
                    "channel": channel,
                    "message_type": "chat",
                    "source_plugin_id": self.plugin_id,
                })
            if as_bool(settings.get("reply_to_source"), True) and self._host is not None:
                sent = bool(self._host.send_platform_message(platform, reply, sender=self.plugin_id))
                if not sent:
                    self._log(f"Antwort konnte nicht an {platform} gesendet werden.")
        finally:
            self._worker_lock.release()


def create_plugin():
    return BotalotPlugin()
