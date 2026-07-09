from __future__ import annotations

import re
import json
import threading
import time
from typing import Any

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

PLUGIN_ID = "commands"
PLUGIN_VERSION = "0.1.0"
PLUGIN_NAME = f"commands ver. {PLUGIN_VERSION}"
PLATFORMS = ("twitch", "tiktok", "youtube", "kick")


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _clean_action_text(value: Any) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ja", "on", "enabled", "aktiv"}:
        return True
    if text in {"0", "false", "no", "nein", "off", "disabled", "aus"}:
        return False
    return default


def _to_int(value: Any, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        out = int(float(str(value).strip()))
    except Exception:
        out = default
    if min_value is not None:
        out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def _normalize_platform(value: Any) -> str:
    text = str(value or "").strip().lower()
    return {
        "tt": "tiktok",
        "yt": "youtube",
        "youtube_chat": "youtube",
        "twitch_chat": "twitch",
        "tiktok_chat": "tiktok",
        "kick_chat": "kick",
    }.get(text, text)


def _normalize_trigger(value: Any) -> str:
    text = _clean_text(value).lower()
    if not text:
        return ""
    if text[0] not in {"!", "/"}:
        text = "!" + text
    return text.split()[0]


def _default_command_rows() -> list[dict[str, Any]]:
    return [
        {"trigger": "!lurk", "name": "Lurk", "response": "{user} verpieselt sich in die Hecke und beobachtet das Geschehen.", "meld_action": "switchScene:scn_13;callFunctionWithArgs:lyr_42:triggerLurk:[\"{user}\"]"},
        {"trigger": "!unlurk", "name": "Unlurk", "response": "Willkommen zurueck, {user}."},
        {"trigger": "!followage", "name": "Followage", "response": "{user}, Followage ist hier noch nicht angebunden."},
        {"trigger": "!uptime", "name": "Uptime", "response": "Der Stream ist live. Eine genaue Uptime ist hier noch nicht angebunden."},
        {"trigger": "!discord", "name": "Discord", "response": "Discord: Link hier eintragen."},
        {"trigger": "!youtube", "name": "YouTube", "response": "YouTube: Link hier eintragen."},
        {"trigger": "!twitter", "name": "X/Twitter", "response": "X/Twitter: Link hier eintragen."},
        {"trigger": "!instagram", "name": "Instagram", "response": "Instagram: Link hier eintragen."},
        {"trigger": "!tiktok", "name": "TikTok", "response": "TikTok: Link hier eintragen."},
        {"trigger": "!commands", "name": "Commands", "response": "Aktive Commands: hier Text anpassen."},
        {"trigger": "!so", "name": "Shoutout", "response": "Schaut gerne bei {args} vorbei."},
        {"trigger": "!raid", "name": "Raid", "response": "Raid Message: hier Text anpassen."},
    ]


class CommandsPlugin(ProviderPlugin):
    plugin_id = PLUGIN_ID
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = "Custom chat commands with chat replies plus optional OBS and Meld actions."

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._enabled = False
        self._recent: dict[str, float] = {}
        self._lock = threading.RLock()

    def settings_schema(self) -> list[dict[str, Any]]:
        def tab(name: str, items: list[dict[str, Any]], *, en: str | None = None) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for item in items:
                row = dict(item)
                row.setdefault("tab", name)
                row.setdefault("ui_tab", name)
                row.setdefault("category", name)
                if en:
                    row.setdefault("tab_en", en)
                    row.setdefault("ui_tab_en", en)
                out.append(row)
            return out

        schema: list[dict[str, Any]] = []
        schema += tab("Uebersicht", [
            {"key": "section_overview", "type": "separator", "label": "commands - eigene Chatbefehle", "label_en": "commands - custom chat commands"},
            {"key": "enabled", "label": "Plugin aktiv", "label_en": "Plugin enabled", "type": "bool"},
            {"key": "commands_enabled", "label": "Commands ausfuehren", "label_en": "Run commands", "type": "bool"},
            {"key": "default_cooldown_seconds", "label": "Standard-Cooldown Sekunden", "label_en": "Default cooldown seconds", "type": "number", "min": 0, "max": 3600},
            {"key": "status", "label": "Status", "label_en": "Status", "readonly": True},
            {"key": "help", "label": "Platzhalter", "label_en": "Placeholders", "readonly": True, "placeholder": "{user}, {platform}, {command}, {args}, {text}", "placeholder_en": "{user}, {platform}, {command}, {args}, {text}"},
            {"key": "commands_json", "label": "Commands JSON", "label_en": "Commands JSON", "type": "multiline", "wide": True},
        ], en="Overview")

        for idx in range(1, 13):
            schema += tab(f"Command {idx}", [
                {"key": f"cmd{idx}_section", "type": "separator", "label": f"Command {idx}", "label_en": f"Command {idx}"},
                {"key": f"cmd{idx}_enabled", "label": "Aktiv", "label_en": "Enabled", "type": "bool"},
                {"key": f"cmd{idx}_name", "label": "Name", "label_en": "Name"},
                {"key": f"cmd{idx}_trigger", "label": "Trigger (! oder /)", "label_en": "Trigger (! or /)", "placeholder": "!lurk"},
                {"key": f"cmd{idx}_cooldown_seconds", "label": "Cooldown Sekunden", "label_en": "Cooldown seconds", "type": "number", "min": 0, "max": 3600},
                {"key": f"cmd{idx}_source_twitch", "label": "Quelle Twitch", "label_en": "Source Twitch", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_source_tiktok", "label": "Quelle TikTok", "label_en": "Source TikTok", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_source_youtube", "label": "Quelle YouTube", "label_en": "Source YouTube", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_source_kick", "label": "Quelle Kick", "label_en": "Source Kick", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_chat_enabled", "label": "Chatantwort senden", "label_en": "Send chat reply", "type": "bool"},
                {"key": f"cmd{idx}_response", "label": "Antworttext", "label_en": "Reply text", "type": "multiline", "wide": True},
                {"key": f"cmd{idx}_reply_same_platform", "label": "Antwort in Ursprungschat", "label_en": "Reply in source chat", "type": "bool"},
                {"key": f"cmd{idx}_target_twitch", "label": "Ziel Twitch", "label_en": "Target Twitch", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_target_tiktok", "label": "Ziel TikTok", "label_en": "Target TikTok", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_target_youtube", "label": "Ziel YouTube", "label_en": "Target YouTube", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_target_kick", "label": "Ziel Kick", "label_en": "Target Kick", "type": "bool", "compact": True},
                {"key": f"cmd{idx}_obs_enabled", "label": "OBS ausloesen", "label_en": "Trigger OBS", "type": "bool"},
                {"key": f"cmd{idx}_obs_hotkey", "label": "OBS Hotkey", "label_en": "OBS hotkey", "placeholder": "Shift+F10"},
                {"key": f"cmd{idx}_meld_enabled", "label": "Meld ausloesen", "label_en": "Trigger Meld", "type": "bool"},
                {"key": f"cmd{idx}_meld_action", "label": "Meld Aktion", "label_en": "Meld action", "placeholder": "sendCommand:recordClip"},
            ], en=f"Command {idx}")
        return schema

    def default_settings(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "enabled": True,
            "commands_enabled": True,
            "default_cooldown_seconds": 15,
            "status": "bereit",
            "help": "{user}, {platform}, {command}, {args}, {text}",
        }
        rows = _default_command_rows()
        for idx in range(1, 13):
            row = rows[idx - 1]
            defaults.update({
                f"cmd{idx}_enabled": False,
                f"cmd{idx}_name": row["name"],
                f"cmd{idx}_trigger": row["trigger"],
                f"cmd{idx}_cooldown_seconds": 0,
                f"cmd{idx}_chat_enabled": True,
                f"cmd{idx}_response": row["response"],
                f"cmd{idx}_reply_same_platform": True,
                f"cmd{idx}_obs_enabled": False,
                f"cmd{idx}_obs_hotkey": "",
                f"cmd{idx}_meld_enabled": False,
                f"cmd{idx}_meld_action": row.get("meld_action", ""),
            })
            for platform in PLATFORMS:
                defaults[f"cmd{idx}_source_{platform}"] = True
                defaults[f"cmd{idx}_target_{platform}"] = False
        defaults["commands_json"] = json.dumps({"commands": self._default_command_list()}, ensure_ascii=False)
        return defaults

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._settings = settings if isinstance(settings, dict) else dict(settings or {})
        self._enabled = _as_bool(self._settings.get("enabled"), True)
        state = "connected" if self._enabled else "disabled"
        msg = f"{PLUGIN_NAME}: " + ("aktiv" if self._enabled else "deaktiviert")
        host.set_status(self.plugin_id, PluginStatus(state, msg))
        host.log(self.plugin_id, f"{PLUGIN_NAME} gestartet.")

    def stop(self, *args: Any, **kwargs: Any) -> None:
        self._enabled = False
        if self._host is not None:
            self._host.set_status(self.plugin_id, PluginStatus("stopped", "Stopped"))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        cfg = self._merged_settings(settings)
        active = [cmd["trigger"] for cmd in self._commands(cfg) if cmd["enabled"]]
        return True, "Aktive Commands: " + (", ".join(active) if active else "keine")

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> tuple[bool, str]:
        if host is not None:
            self._host = host
        if key.startswith("test_command:"):
            command_id = key.split(":", 1)[1].strip()
            settings = self._current_settings()
            for cmd in self._commands(settings):
                if str(cmd.get("id") or cmd.get("index") or "") == command_id:
                    return self._test_command_action(cmd)
            self._log(f"Test fehlgeschlagen: Command nicht gefunden ({command_id})")
            return False, f"Command nicht gefunden ({command_id})"
        return False, "Unbekannte Aktion"

    handle_settings_button = on_settings_button
    on_settings_action = on_settings_button

    def on_message(self, msg: Any) -> None:
        if not self._enabled:
            return
        if self._message_type(msg) not in {"chat", "message", "comment"}:
            return
        settings = self._current_settings()
        if not _as_bool(settings.get("commands_enabled"), True):
            return
        platform = self._message_platform(msg)
        if platform not in PLATFORMS:
            return
        text = self._message_text(msg)
        if not text or text[0] not in {"!", "/"}:
            return
        command, args = self._split_command(text)
        if not command:
            return
        username = self._message_username(msg)
        for cmd in self._commands(settings):
            if not cmd["enabled"] or cmd["trigger"] != command:
                continue
            if not cmd["sources"].get(platform, False):
                return
            if self._cooldown_hit(platform, command, cmd["cooldown"]):
                return
            threading.Thread(
                target=self._execute_command,
                args=(dict(settings), dict(cmd), platform, username, text, args),
                daemon=True,
                name="commands-execute",
            ).start()
            return

    on_chat_message = on_message
    handle_message = on_message

    def _test_command_action(self, cmd: dict[str, Any]) -> tuple[bool, str]:
        values = {
            "user": "TestUser",
            "platform": "test",
            "command": cmd["trigger"],
            "args": "",
            "text": cmd["trigger"],
        }
        details: list[str] = []
        ok_all = True
        if cmd["meld_enabled"] and cmd["meld_action"]:
            action = self._format(cmd["meld_action"], values)
            ok, detail = self._trigger_meld(action)
            self._log(f"Meld Test {cmd['trigger']}: {detail if detail else ok}")
            details.append(f"Meld: {detail if detail else ok}")
            ok_all = ok_all and bool(ok)
        if cmd["obs_enabled"] and cmd["obs_hotkey"]:
            ok, detail = self._trigger_obs(cmd["obs_hotkey"])
            self._log(f"OBS Test {cmd['trigger']}: {detail if detail else ok}")
            details.append(f"OBS: {detail if detail else ok}")
            ok_all = ok_all and bool(ok)
        if not details:
            return False, "Für diesen Command ist keine Meld- oder OBS-Aktion aktiv."
        return ok_all, " | ".join(details)

    def _execute_command(self, settings: dict[str, Any], cmd: dict[str, Any], platform: str, username: str, text: str, args: str) -> tuple[bool, str]:
        ok_all = True
        action_seen = False
        details: list[str] = []
        values = {
            "user": username or "chat",
            "platform": platform,
            "command": cmd["trigger"],
            "args": args,
            "text": text,
        }
        if cmd["chat_enabled"] and cmd["response"]:
            response = self._format(cmd["response"], values)
            targets = set(cmd["targets"])
            if cmd["reply_same_platform"]:
                targets.add(platform)
            for target in PLATFORMS:
                if target in targets:
                    if not self._send_chat(target, response):
                        details.append(f"Chat {target}: fehlgeschlagen")
                    else:
                        details.append(f"Chat {target}: gesendet")
            if not (cmd["obs_enabled"] and cmd["obs_hotkey"]) and not (cmd["meld_enabled"] and cmd["meld_action"]):
                action_seen = True
                ok_all = not any(detail.startswith("Chat ") and detail.endswith("fehlgeschlagen") for detail in details)
        if cmd["obs_enabled"] and cmd["obs_hotkey"]:
            action_seen = True
            ok, detail = self._trigger_obs(cmd["obs_hotkey"])
            self._log(f"OBS {cmd['trigger']}: {detail if detail else ok}")
            ok_all = ok_all and bool(ok)
            details.append(f"OBS: {detail if detail else ok}")
        if cmd["meld_enabled"] and cmd["meld_action"]:
            action_seen = True
            ok, detail = self._trigger_meld(self._format(cmd["meld_action"], values))
            self._log(f"Meld {cmd['trigger']}: {detail if detail else ok}")
            ok_all = ok_all and bool(ok)
            details.append(f"Meld: {detail if detail else ok}")
        if not details:
            details.append("Command ausgefuehrt.")
        return (ok_all if action_seen else True), " | ".join(details)

    def _commands(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        parsed = self._commands_from_json(settings)
        if parsed:
            return parsed
        out: list[dict[str, Any]] = []
        default_cd = _to_int(settings.get("default_cooldown_seconds"), 15, 0, 3600)
        for idx in range(1, 13):
            trigger = _normalize_trigger(settings.get(f"cmd{idx}_trigger"))
            if not trigger:
                continue
            sources = {p: _as_bool(settings.get(f"cmd{idx}_source_{p}"), True) for p in PLATFORMS}
            targets = [p for p in PLATFORMS if _as_bool(settings.get(f"cmd{idx}_target_{p}"), False)]
            cooldown = _to_int(settings.get(f"cmd{idx}_cooldown_seconds"), 0, 0, 3600) or default_cd
            out.append({
                "id": str(idx),
                "index": idx,
                "enabled": _as_bool(settings.get(f"cmd{idx}_enabled"), False),
                "name": _clean_text(settings.get(f"cmd{idx}_name")),
                "trigger": trigger,
                "cooldown": cooldown,
                "sources": sources,
                "chat_enabled": _as_bool(settings.get(f"cmd{idx}_chat_enabled"), True),
                "response": str(settings.get(f"cmd{idx}_response") or "").strip(),
                "reply_same_platform": _as_bool(settings.get(f"cmd{idx}_reply_same_platform"), True),
                "targets": targets,
                "obs_enabled": _as_bool(settings.get(f"cmd{idx}_obs_enabled"), False),
                "obs_hotkey": _clean_text(settings.get(f"cmd{idx}_obs_hotkey")),
                "meld_enabled": _as_bool(settings.get(f"cmd{idx}_meld_enabled"), False),
                "meld_action": _clean_text(settings.get(f"cmd{idx}_meld_action")),
            })
        return out

    def _default_command_list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, row in enumerate(_default_command_rows(), 1):
            out.append({
                "id": f"default_{idx}",
                "enabled": False,
                "name": row["name"],
                "trigger": row["trigger"],
                "cooldown_seconds": 0,
                "sources": {p: True for p in PLATFORMS},
                "chat_enabled": True,
                "response": row["response"],
                "reply_same_platform": True,
                "targets": {p: False for p in PLATFORMS},
                "obs_enabled": False,
                "obs_hotkey": "",
                "meld_enabled": False,
                "meld_action": row.get("meld_action", ""),
            })
        return out

    def _commands_from_json(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        raw = settings.get("commands_json")
        if not raw:
            return []
        try:
            data = json.loads(str(raw))
        except Exception:
            return []
        rows = data.get("commands") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        default_cd = _to_int(settings.get("default_cooldown_seconds"), 15, 0, 3600)
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            trigger = _normalize_trigger(item.get("trigger"))
            if not trigger:
                continue
            sources_raw = item.get("sources") if isinstance(item.get("sources"), dict) else {}
            targets_raw = item.get("targets") if isinstance(item.get("targets"), dict) else {}
            cooldown = _to_int(item.get("cooldown_seconds"), 0, 0, 3600) or default_cd
            out.append({
                "id": str(item.get("id") or idx),
                "index": idx,
                "enabled": _as_bool(item.get("enabled"), False),
                "name": _clean_text(item.get("name")),
                "trigger": trigger,
                "cooldown": cooldown,
                "sources": {p: _as_bool(sources_raw.get(p), True) for p in PLATFORMS},
                "chat_enabled": _as_bool(item.get("chat_enabled"), True),
                "response": str(item.get("response") or "").strip(),
                "reply_same_platform": _as_bool(item.get("reply_same_platform"), True),
                "targets": [p for p in PLATFORMS if _as_bool(targets_raw.get(p), False)],
                "obs_enabled": _as_bool(item.get("obs_enabled"), False),
                "obs_hotkey": _clean_text(item.get("obs_hotkey")),
                "meld_enabled": _as_bool(item.get("meld_enabled"), False),
                "meld_action": self._migrate_meld_action(_clean_text(item.get("meld_action"))),
            })
        return out

    def _migrate_meld_action(self, action: str) -> str:
        old = 'callFunctionWithArgs:lurk-alert:triggerLurk:["{user}"]'
        if str(action or "").strip() == old:
            return 'switchScene:scn_13;callFunctionWithArgs:lyr_42:triggerLurk:["{user}"]'
        old_eval = 'switchScene:scn_13;evalJs:lyr_42:window.triggerLurk("{user}")'
        if str(action or "").strip() == old_eval:
            return 'switchScene:scn_13;callFunctionWithArgs:lyr_42:triggerLurk:["{user}"]'
        return action

    def _cooldown_hit(self, platform: str, command: str, cooldown: int) -> bool:
        if cooldown <= 0:
            return False
        now = time.time()
        key = f"{platform}:{command}"
        with self._lock:
            for old_key, expires in list(self._recent.items()):
                if expires <= now:
                    self._recent.pop(old_key, None)
            if self._recent.get(key, 0.0) > now:
                return True
            self._recent[key] = now + cooldown
            return False

    def _send_chat(self, platform: str, message: str) -> bool:
        host = self._host
        if host is None or not message:
            return False
        try:
            return bool(host.send_platform_message(platform, message, sender=self.plugin_id))
        except Exception as exc:
            self._log(f"Chatantwort an {platform} fehlgeschlagen: {exc}")
            return False

    def _trigger_obs(self, hotkey: str) -> tuple[bool, str]:
        plugin = self._host_plugin("obs_control")
        if plugin is None:
            return False, "OBS Control plugin nicht geladen"
        fn = getattr(plugin, "trigger_hotkey_by_key_sequence", None)
        if callable(fn):
            try:
                return fn(hotkey)
            except Exception as exc:
                return False, f"OBS Hotkey fehlgeschlagen: {exc}"
        return False, "OBS Control unterstuetzt keine Hotkey-Aktion"

    def _trigger_meld(self, action: str) -> tuple[bool, str]:
        plugin = self._host_plugin("meld_control")
        if plugin is None:
            return False, "Meld Control plugin nicht geladen"
        action = _clean_action_text(action)
        if not action:
            return False, "Meld Aktion fehlt"
        actions = [part.strip() for part in action.split(";") if part.strip()]
        if len(actions) > 1:
            details: list[str] = []
            ok_any = False
            for sub_action in actions:
                ok, detail = self._trigger_meld(sub_action)
                ok_any = ok_any or bool(ok)
                details.append(f"{sub_action}: {detail or ok}")
                if not ok:
                    return False, " | ".join(details)
            return ok_any, " | ".join(details)
        try:
            if ":" in action:
                name, rest = action.split(":", 1)
                name = name.strip()
                parts = [part.strip() for part in rest.split(":")]
            else:
                name, parts = "sendCommand", [action]
            if name == "sendCommand" and hasattr(plugin, "send_command"):
                ok, detail = plugin.send_command(parts[0] if parts else action)
                return bool(ok), str(detail)
            if name in {"showScene", "switchScene", "switch_scene"} and hasattr(plugin, "invoke_meld_method") and parts:
                methods = ("showScene", "switchScene", "switch_scene", "setCurrentScene") if name == "showScene" else ("switch_scene", "switchScene", "showScene", "setCurrentScene")
                ok, detail = self._invoke_first_meld_method(plugin, methods, [parts[0]])
                return bool(ok), str(detail)
            if name in {"evalJs", "evaluateJs", "evaluateJavaScript", "executeScript"} and len(parts) >= 2:
                layer_id, layer_detail = self._resolve_meld_layer_id(plugin, parts[0])
                if not layer_id:
                    return False, layer_detail
                script = ":".join(parts[1:]).strip()
                return self._evaluate_meld_javascript(plugin, layer_id, script)
            if name == "callFunction" and hasattr(plugin, "call_layer_function") and len(parts) >= 2:
                layer_id, layer_detail = self._resolve_meld_layer_id(plugin, parts[0])
                if not layer_id:
                    return False, layer_detail
                self._prepare_meld_layer(plugin, layer_id)
                ok, detail = plugin.call_layer_function(layer_id, parts[1])
                return bool(ok), str(detail)
            if name == "callFunctionWithArgs" and hasattr(plugin, "call_layer_function_with_args") and len(parts) >= 3:
                try:
                    parsed_args = json.loads(":".join(parts[2:]))
                except Exception as exc:
                    return False, f"callFunctionWithArgs JSON ungueltig: {exc}"
                if not isinstance(parsed_args, list):
                    return False, "callFunctionWithArgs erwartet ein JSON-Array"
                layer_id, layer_detail = self._resolve_meld_layer_id(plugin, parts[0])
                if not layer_id:
                    return False, layer_detail
                self._prepare_meld_layer(plugin, layer_id)
                ok, detail = plugin.call_layer_function_with_args(layer_id, parts[1], parsed_args)
                return bool(ok), str(detail)
            if name == "setProperty" and hasattr(plugin, "set_session_property") and len(parts) >= 3:
                layer_id, _ = self._resolve_meld_layer_id(plugin, parts[0])
                ok, detail = plugin.set_session_property(layer_id or parts[0], parts[1], parts[2])
                return bool(ok), str(detail)
            if name == "sendStreamEvent" and hasattr(plugin, "send_stream_event"):
                ok, detail = plugin.send_stream_event(parts[0] if parts else "")
                return bool(ok), str(detail)
            inv = getattr(plugin, "invoke_meld_method", None)
            if callable(inv):
                ok, detail = inv(name, parts)
                return bool(ok), str(detail)
        except Exception as exc:
            return False, f"Meld Aktion fehlgeschlagen: {exc}"
        return False, f"Meld Aktion nicht unterstuetzt: {action}"

    def _invoke_first_meld_method(self, plugin: Any, names: tuple[str, ...], args: list[Any], timeout: float = 3.0) -> tuple[bool, str]:
        inv = getattr(plugin, "invoke_meld_method", None)
        if not callable(inv):
            return False, "Meld Control unterstuetzt keine generischen Methoden"
        details: list[str] = []
        for method in names:
            try:
                ok, detail = inv(method, args, timeout=timeout)
            except TypeError:
                ok, detail = inv(method, args)
            except Exception as exc:
                details.append(f"{method}: {exc}")
                continue
            details.append(f"{method}: {detail}")
            if ok:
                return True, str(detail or method)
            if "unknown meld method" not in str(detail).lower():
                return False, str(detail)
        return False, " | ".join(details)

    def _evaluate_meld_javascript(self, plugin: Any, layer_id: str, script: str) -> tuple[bool, str]:
        if not script:
            return False, "JavaScript fehlt"
        self._prepare_meld_layer(plugin, layer_id)
        method_args = (
            ("evaluateJavaScript", [layer_id, script]),
            ("evaluateJavascript", [layer_id, script]),
            ("evalJavaScript", [layer_id, script]),
            ("executeJavaScript", [layer_id, script]),
            ("executeJavascript", [layer_id, script]),
            ("executeScript", [layer_id, script]),
            ("evaluate", [layer_id, script]),
            ("callFunctionWithArgs", [layer_id, "eval", [script]]),
            ("callFunctionWithArgs", [layer_id, "evaluateJavaScript", [script]]),
            ("callFunctionWithArgs", [layer_id, "executeScript", [script]]),
        )
        details: list[str] = []
        for method, args in method_args:
            ok, detail = self._invoke_first_meld_method(plugin, (method,), list(args), timeout=3.0)
            details.append(f"{method}: {detail}")
            if ok:
                return True, str(detail or "JavaScript ausgefuehrt")
            if "unknown meld method" not in str(detail).lower() and "unknown" not in str(detail).lower():
                return False, str(detail)
        return False, "Keine passende Meld-JavaScript-Methode gefunden: " + " | ".join(details[-5:])

    def _resolve_meld_layer_id(self, plugin: Any, layer_ref: str) -> tuple[str, str]:
        ref = _clean_text(layer_ref)
        if not ref:
            return "", "Meld Layer fehlt"
        if ref.startswith("<") and ref.endswith(">"):
            return "", f"Meld Layer-ID/Name noch nicht ersetzt: {ref}"
        finder = getattr(plugin, "_find_target_layer", None)
        if callable(finder):
            scene_name = ""
            layer_name = ref
            if "/" in ref:
                left, right = ref.split("/", 1)
                scene_name, layer_name = left.strip(), right.strip()
            try:
                layer = finder(scene_name, layer_name)
                if isinstance(layer, dict) and layer.get("id"):
                    return str(layer["id"]), ""
            except Exception:
                pass
        items_getter = getattr(plugin, "get_session_items", None)
        if callable(items_getter):
            try:
                items = items_getter()
                if isinstance(items, dict):
                    if ref in items:
                        return ref, ""
                    matches = []
                    needle = ref.strip().casefold()
                    for item_id, item in items.items():
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("type") or "").casefold() != "layer":
                            continue
                        if str(item.get("name") or "").strip().casefold() == needle:
                            matches.append(str(item_id))
                    if len(matches) == 1:
                        return matches[0], ""
            except Exception:
                pass
        return ref, ""

    def _prepare_meld_layer(self, plugin: Any, layer_id: str) -> None:
        setter = getattr(plugin, "set_session_property", None)
        if not callable(setter) or not layer_id:
            return
        self._show_meld_parent_chain(plugin, layer_id)
        try:
            setter(layer_id, "visible", True, timeout=1.5)
        except Exception:
            pass

    def _show_meld_parent_chain(self, plugin: Any, layer_id: str) -> None:
        getter = getattr(plugin, "get_session_items", None)
        setter = getattr(plugin, "set_session_property", None)
        if not callable(getter) or not callable(setter):
            return
        try:
            items = getter()
            if not isinstance(items, dict):
                return
            item = items.get(str(layer_id))
            if not isinstance(item, dict):
                return
            parent_id = str(item.get("parentId") or item.get("parent_id") or item.get("parent") or item.get("groupId") or item.get("group_id") or "")
            visited: set[str] = set()
            while parent_id and parent_id not in visited:
                visited.add(parent_id)
                parent = items.get(parent_id)
                if not isinstance(parent, dict) or str(parent.get("type") or "").casefold() == "scene":
                    break
                setter(parent_id, "visible", True, timeout=1.5)
                parent_id = str(parent.get("parentId") or parent.get("parent_id") or parent.get("parent") or parent.get("groupId") or parent.get("group_id") or "")
        except Exception:
            pass

    def _host_plugin(self, plugin_id: str) -> Any:
        host = self._host
        if host is None:
            return None
        getter = getattr(host, "get_plugin", None)
        if callable(getter):
            try:
                plugin = getter(plugin_id)
                if plugin is not None:
                    return plugin
            except Exception:
                pass
        try:
            state = getattr(host, "state", None)
            instances = getattr(state, "plugin_instances", {}) if state is not None else {}
            return instances.get(plugin_id) if isinstance(instances, dict) else None
        except Exception:
            return None

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
        return self._merged_settings(self._settings)

    def _merged_settings(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = self.default_settings()
        if isinstance(settings, dict):
            merged.update(settings)
        return merged

    def _format(self, template: str, values: dict[str, Any]) -> str:
        class SafeValues(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        try:
            return str(template or "").format_map(SafeValues(values))
        except Exception:
            out = str(template or "")
            for key, value in values.items():
                out = out.replace("{" + key + "}", str(value))
            return out

    def _split_command(self, text: str) -> tuple[str, str]:
        parts = _clean_text(text).split(" ", 1)
        command = _normalize_trigger(parts[0] if parts else "")
        args = parts[1].strip() if len(parts) > 1 else ""
        return command, args

    def _message_type(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return str(payload.get("message_type") or payload.get("type") or payload.get("event_type") or "chat").strip().lower()
        return str(getattr(payload, "message_type", "") or getattr(payload, "type", "") or getattr(payload, "event_type", "") or "chat").strip().lower()

    def _message_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return _clean_text(payload.get("text") or payload.get("message") or payload.get("content") or payload.get("comment") or "")
        return _clean_text(getattr(payload, "text", "") or getattr(payload, "message", "") or getattr(payload, "content", "") or getattr(payload, "comment", "") or "")

    def _message_username(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return _clean_text(payload.get("username") or payload.get("display_name") or payload.get("user") or payload.get("nickname") or payload.get("unique_id") or "")
        return _clean_text(getattr(payload, "username", "") or getattr(payload, "display_name", "") or getattr(payload, "user", "") or getattr(payload, "nickname", "") or getattr(payload, "unique_id", "") or "")

    def _message_platform(self, payload: Any) -> str:
        if isinstance(payload, dict):
            raw = payload.get("platform") or payload.get("source_plugin_id") or payload.get("source") or ""
        else:
            raw = getattr(payload, "platform", "") or getattr(payload, "source_plugin_id", "") or getattr(payload, "source", "") or ""
        return _normalize_platform(raw)

    def _log(self, msg: str) -> None:
        if self._host is not None:
            try:
                self._host.log(self.plugin_id, msg)
                return
            except Exception:
                pass
        print(f"[{self.plugin_id}] {msg}")


def create_plugin() -> CommandsPlugin:
    return CommandsPlugin()
