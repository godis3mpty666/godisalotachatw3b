from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

PLUGIN_VERSION = "0.12"
PLUGIN_NAME = f"modalot ver. {PLUGIN_VERSION}"
PLUGIN_ID = "modalot"

TWITCH_REQUIRED_SCOPES = (
    "chat:read",
    "chat:edit",
    "user:read:chat",
    "user:write:chat",
    "moderator:read:chatters",
    "moderator:manage:banned_users",
    "moderator:manage:chat_messages",
    "channel:manage:broadcast",
)
KICK_REQUIRED_SCOPES = (
    "user:read",
    "channel:read",
    "channel:write",
    "chat:write",
    "moderation:ban",
    "moderation:chat_message:manage",
)
YOUTUBE_REQUIRED_SCOPES = (
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
)

TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
TWITCH_BANS_URL = "https://api.twitch.tv/helix/moderation/bans"
TWITCH_DELETE_CHAT_URL = "https://api.twitch.tv/helix/moderation/chat"
KICK_MOD_BANS_URL = "https://api.kick.com/public/v1/moderation/bans"
YOUTUBE_LIVE_CHAT_MESSAGES_URL = "https://www.googleapis.com/youtube/v3/liveChat/messages"
YOUTUBE_LIVE_CHAT_BANS_URL = "https://www.googleapis.com/youtube/v3/liveChat/bans"


def _data_dir() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == "modules":
            return parent.parent / "data" / PLUGIN_ID
    return current.parent / "data"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _clean_login(value: Any) -> str:
    return str(value or "").strip().lstrip("@#").strip().lower()


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


def _split_words(value: Any) -> list[str]:
    items: list[str] = []
    for raw in re.split(r"[\n,;]+", str(value or "")):
        word = raw.strip().lower()
        if word and word not in items:
            items.append(word)
    return items


def _split_names(value: Any) -> set[str]:
    return {_clean_login(x) for x in re.split(r"[\n,;]+", str(value or "")) if _clean_login(x)}


class ModalotPlugin(ProviderPlugin):
    plugin_id = PLUGIN_ID
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = "Standalone moderation plugin for Twitch, Kick and YouTube."

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._enabled = False
        self._lock = threading.RLock()
        self._recent: dict[str, float] = {}
        self._session_actions: list[dict[str, Any]] = []
        self._twitch_user_cache: dict[str, tuple[str, float]] = {}
        self._kick_user_cache: dict[str, tuple[str, float]] = {}

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

        action_options = [
            {"value": "delete", "label": "nur löschen"},
            {"value": "timeout", "label": "löschen + Timeout"},
            {"value": "ban", "label": "löschen + Ban"},
        ]

        def platform_tab(platform: str, label: str) -> list[dict[str, Any]]:
            prefix = platform.lower()
            rows: list[dict[str, Any]] = [
                {"key": f"section_{prefix}_click_rules", "type": "separator", "label": f"{label} Regeln"},
            ]
            for idx in range(1, 9):
                rows += [
                    {"key": f"{prefix}_rule_{idx}_word", "label": f"{idx}. Wort/Phrase", "placeholder": "Wort oder Phrase", "compact": True},
                    {"key": f"{prefix}_rule_{idx}_action", "label": f"{idx}. Aktion", "type": "select", "options": action_options, "compact": True},
                    {"key": f"{prefix}_rule_{idx}_timeout_minutes", "label": f"{idx}. Min.", "type": "number", "min": 1, "max": 20160, "compact": True, "hide_if": {"key": f"{prefix}_rule_{idx}_action", "value": "ban"}, "hide_mode": "invisible"},
                ]
            return tab(label, rows)

        schema: list[dict[str, Any]] = []
        schema += tab("Übersicht", [
            {"key": "section_overview", "type": "separator", "label": f"{PLUGIN_NAME} - Moderation"},
            {"key": "enabled", "label": "Plugin aktiv", "type": "bool"},
            {"key": "status", "label": "Status", "readonly": True, "placeholder": "bereit"},
            {"key": "auto_moderation_enabled", "label": "Automatik einschalten", "type": "bool", "help": "Wenn aktiv, prüft modalot neue Chatnachrichten mit den Regeln in den Plattform-Reitern."},
            {"key": "tiktok_mod_info_display", "label": "TikTok Mod", "readonly": True, "placeholder": "Seitens TikTok aktuell nicht verfügbar; Regeln bleiben intern deaktiviert und werden nicht angezeigt."},
        ], en="Overview")

        schema += platform_tab("twitch", "Twitch")
        schema += platform_tab("kick", "Kick")
        schema += platform_tab("youtube", "YouTube")

        schema += tab("Manuell", [
            {"key": "section_manual", "type": "separator", "label": "Manuelle Aktionen"},
            {"key": "manual_platform", "label": "Plattform", "type": "select", "options": [
                {"value": "twitch", "label": "Twitch"},
                {"value": "kick", "label": "Kick"},
                {"value": "youtube", "label": "YouTube"},
            ]},
            {"key": "manual_user", "label": "User", "placeholder": "Twitch/Kick Username oder YouTube Channel-ID"},
            {"key": "manual_duration_minutes", "label": "Timeout Minuten", "type": "number", "min": 1, "max": 20160},
            {"key": "manual_reason", "label": "Grund", "type": "multiline", "wide": True},
            {"key": "manual_message_id", "label": "Message-ID zum Löschen", "placeholder": "optional; für YouTube liveChatMessage.id"},
            {"key": "button_manual_delete", "type": "button", "label": "Nachricht löschen", "button_text": "Nachricht löschen"},
            {"key": "button_manual_timeout", "type": "button", "label": "Timeout", "button_text": "User timeouten"},
            {"key": "button_manual_ban", "type": "button", "label": "Ban", "button_text": "User bannen"},
            {"key": "button_manual_unban", "type": "button", "label": "Unban", "button_text": "User freigeben"},
        ], en="Manual")

        return schema

    def default_settings(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "enabled": True,
            "status": "bereit",
            "auto_moderation_enabled": True,
            "blocked_words": "",
            "excluded_users": "streamelements\nnightbot\nstreamlabs",
            "default_action": "delete",
            "default_timeout_seconds": 600,
            "delete_message_first": True,
            "send_mod_notice": False,
            "mod_notice_format": "@{user} wurde moderiert. ({action})",
            "reason_format": "Automod: {word}",
            "legacy_note": "Alte globale blocked_words/default_action bleiben als Fallback erhalten.",
            "manual_platform": "twitch",
            "manual_user": "",
            "manual_duration_minutes": 10,
            "manual_duration_seconds": 600,
            "manual_reason": "Manuelle Moderation",
            "manual_message_id": "",
            "session_actions": "Noch keine Aktionen in dieser Session.",
            "tiktok_mod_info_display": "Seitens TikTok aktuell nicht verfügbar; Regeln bleiben intern deaktiviert und werden nicht angezeigt.",
        }
        for platform in ("twitch", "kick", "youtube"):
            defaults[f"{platform}_enabled"] = True
            defaults[f"{platform}_status"] = f"nutzt OAuth aus Plattformen > {platform.capitalize()}"
            defaults[f"{platform}_blacklist_bulk"] = ""
            defaults[f"{platform}_default_action"] = "delete"
            defaults[f"{platform}_default_timeout_seconds"] = 600
            defaults[f"{platform}_default_timeout_minutes"] = 10
            for idx in range(1, 13):
                defaults[f"{platform}_rule_{idx}_word"] = ""
                defaults[f"{platform}_rule_{idx}_action"] = "delete"
                defaults[f"{platform}_rule_{idx}_timeout_seconds"] = 600
                defaults[f"{platform}_rule_{idx}_timeout_minutes"] = 10
        defaults["youtube_status"] = "nutzt OAuth aus Plattformen > YouTube"
        defaults["tiktok_enabled"] = False
        defaults["tiktok_status"] = "momentan deaktiviert"
        defaults["tiktok_info"] = "TikTok bietet momentan keine stabile Mod-API; nicht aktivierbar."
        defaults["tiktok_blacklist_bulk"] = ""
        defaults["tiktok_default_action"] = "delete"
        defaults["tiktok_default_timeout_seconds"] = 600
        defaults["tiktok_default_timeout_minutes"] = 10
        for idx in range(1, 13):
            defaults[f"tiktok_rule_{idx}_word"] = ""
            defaults[f"tiktok_rule_{idx}_action"] = "delete"
            defaults[f"tiktok_rule_{idx}_timeout_seconds"] = 600
            defaults[f"tiktok_rule_{idx}_timeout_minutes"] = 10
        return defaults

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._settings = settings if isinstance(settings, dict) else dict(settings or {})
        self._enabled = _as_bool(self._settings.get("enabled"), True)
        self._ensure_data_dir()
        self._sync_session_setting()
        host.set_status(self.plugin_id, PluginStatus("connected" if self._enabled else "disabled", f"{PLUGIN_NAME}: " + ("aktiv" if self._enabled else "deaktiviert")))
        host.log(self.plugin_id, f"{PLUGIN_NAME} gestartet. Twitch/Kick/YouTube Moderation vorbereitet. TikTok bleibt deaktiviert.")

    def stop(self, *args, **kwargs) -> None:
        self._enabled = False
        if self._host is not None:
            self._host.set_status(self.plugin_id, PluginStatus("stopped", "Stopped"))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        cfg = self._merged_settings(settings)
        checks = []
        if _as_bool(cfg.get("twitch_enabled"), True):
            ok, msg = self._test_twitch(cfg)
            checks.append((ok, "Twitch: " + msg))
        if _as_bool(cfg.get("kick_enabled"), True):
            ok, msg = self._test_kick(cfg)
            checks.append((ok, "Kick: " + msg))
        if _as_bool(cfg.get("youtube_enabled"), True):
            ok, msg = self._test_youtube(cfg)
            checks.append((ok, "YouTube: " + msg))
        ok_all = all(ok for ok, _ in checks) if checks else True
        return ok_all, " | ".join(msg for _, msg in checks) if checks else "modalot ist bereit."

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        if host is not None:
            self._host = host
        cfg = self._current_settings()
        if key == "button_test_twitch_mod":
            ok, msg = self._test_twitch(cfg)
            self._log("Twitch Modrechte: " + msg)
            return ok
        if key == "button_test_kick_mod":
            ok, msg = self._test_kick(cfg)
            self._log("Kick Modrechte: " + msg)
            return ok
        if key == "button_test_youtube_mod":
            ok, msg = self._test_youtube(cfg)
            self._log("YouTube Modrechte: " + msg)
            return ok
        if key == "button_tiktok_mod_info":
            self._log("TikTok Moderation ist sichtbar, aber bewusst nicht aktivierbar, weil aktuell keine stabile Mod-API angebunden ist.")
            return True
        if key in {"button_manual_delete", "button_manual_timeout", "button_manual_ban", "button_manual_unban"}:
            return self._manual_action(cfg, key)
        return False

    handle_settings_button = on_settings_button
    on_settings_action = on_settings_button

    def on_message(self, msg: Any) -> None:
        if not self._enabled:
            return
        settings = self._current_settings()
        if self._message_type(msg) not in {"chat", "message", "comment"}:
            return
        platform = self._message_platform(msg)
        if platform not in {"twitch", "kick", "youtube"}:
            return
        if not self._platform_enabled(settings, platform):
            return
        if not _as_bool(settings.get("auto_moderation_enabled"), False) and not self._platform_rules(settings, platform):
            return
        username = self._message_username(msg)
        clean_user = _clean_login(username)
        if not clean_user or clean_user in _split_names(settings.get("excluded_users")):
            return
        text = self._message_text(msg)
        if not text:
            return
        rule = self._find_matching_rule(settings, platform, text)
        if not rule:
            return
        word = str(rule.get("word") or "").strip()
        msg_id = self._message_id(msg)
        channel = self._message_channel(msg)
        if platform == "youtube":
            live_chat_id = self._message_live_chat_id(msg)
            author_channel_id = self._message_author_channel_id(msg)
            if live_chat_id:
                self._settings["youtube_live_chat_id_runtime"] = live_chat_id
            if author_channel_id:
                self._settings["youtube_last_author_channel_id"] = author_channel_id
                username_for_action = author_channel_id
            else:
                username_for_action = username
        else:
            username_for_action = username
        key = f"{platform}|{clean_user}|{word}|{msg_id or text[:80].lower()}"
        if self._recent_hit(key):
            return
        action = str(rule.get("action") or "delete").strip().lower()
        if action not in {"delete", "timeout", "ban"}:
            action = "delete"
        duration = _to_int(rule.get("duration"), _to_int(settings.get(f"{platform}_default_timeout_seconds"), 600, 1, 1209600), 1, 1209600)
        reason = self._format(settings.get("reason_format") or "Automod: {word}", username, platform, word, action, duration)

        delete_ok = False
        delete_detail = "keine Message-ID vorhanden"
        if msg_id:
            delete_ok, delete_detail = self._delete_message(settings, platform, msg_id, channel)

        ok = True
        detail = ""
        if action == "delete":
            ok, detail = delete_ok, delete_detail
        elif action == "timeout":
            ok, detail = self._timeout_user(settings, platform, username_for_action, duration, reason)
        elif action == "ban":
            ok, detail = self._ban_user(settings, platform, username_for_action, reason)

        if action in {"timeout", "ban"}:
            detail = f"Delete: {delete_detail} | Aktion: {detail}"
        self._remember_action(platform, action, username, word, reason, ok, detail, duration=duration, message_id=msg_id)
        if _as_bool(settings.get("send_mod_notice"), False) and self._host is not None:
            notice = self._format(settings.get("mod_notice_format") or "@{user} wurde moderiert. ({action})", username, platform, word, action, duration)
            try:
                self._host.send_platform_message(platform, notice, sender=self.plugin_id)
            except Exception as exc:
                self._log(f"Moderationsmeldung konnte nicht gesendet werden: {exc}")

    on_chat_message = on_message
    handle_message = on_message

    def _manual_action(self, settings: dict[str, Any], key: str) -> bool:
        platform = str(settings.get("manual_platform") or "").strip().lower()
        user = _clean_login(settings.get("manual_user"))
        reason = _clean_text(settings.get("manual_reason") or "Manuelle Moderation")
        duration = self._minutes_to_seconds(settings.get("manual_duration_minutes"), settings.get("manual_duration_seconds"), 600)
        message_id = _clean_text(settings.get("manual_message_id"))
        if platform not in {"twitch", "kick", "youtube"}:
            self._log("Manuelle Moderation: Plattform muss twitch, kick oder youtube sein. TikTok ist nicht aktivierbar.")
            return False
        if key == "button_manual_delete":
            ok, detail = self._delete_message(settings, platform, message_id, "")
            action = "delete"
        elif key == "button_manual_timeout":
            if not user:
                self._log("Manuelle Moderation: User fehlt.")
                return False
            ok, detail = self._timeout_user(settings, platform, user, duration, reason)
            action = "timeout"
        elif key == "button_manual_ban":
            if not user:
                self._log("Manuelle Moderation: User fehlt.")
                return False
            ok, detail = self._ban_user(settings, platform, user, reason)
            action = "ban"
        elif key == "button_manual_unban":
            if not user:
                self._log("Manuelle Moderation: User fehlt.")
                return False
            ok, detail = self._unban_user(settings, platform, user)
            action = "unban"
        else:
            return False
        self._remember_action(platform, action, user or "-", "manual", reason, ok, detail, duration=duration, message_id=message_id)
        self._log(f"Manuelle Moderation {platform}/{action}: {'ok' if ok else 'fehlgeschlagen'} - {detail}")
        return ok

    def _current_settings(self) -> dict[str, Any]:
        fresh = None
        host = self._host
        if host is not None:
            for name in ("plugin_settings", "get_plugin_settings"):
                fn = getattr(getattr(host, "state", None), name, None)
                if callable(fn):
                    try:
                        fresh = fn(self.plugin_id)
                    except Exception:
                        fresh = None
                    if isinstance(fresh, dict):
                        break
        if isinstance(fresh, dict):
            self._settings.update(fresh)
        return self._merged_settings(self._settings)

    def _merged_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        out = self.default_settings()
        if isinstance(settings, dict):
            out.update(settings)
        return out

    def _host_platform_settings(self, platform: str) -> dict[str, Any]:
        host = self._host
        if host is None:
            return {}
        for name in ("get_platform_settings", "platform_settings"):
            fn = getattr(host, name, None)
            if not callable(fn):
                continue
            try:
                data = fn(platform)
                if isinstance(data, dict):
                    return dict(data)
            except TypeError:
                try:
                    data = fn()
                    if isinstance(data, dict):
                        item = data.get(platform)
                        if isinstance(item, dict):
                            return dict(item)
                except Exception:
                    pass
            except Exception:
                pass
        return {}

    def _log(self, message: str) -> None:
        if self._host is not None:
            try:
                self._host.log(self.plugin_id, str(message))
                return
            except Exception:
                pass
        print(f"[{self.plugin_id}] {message}")

    def _ensure_data_dir(self) -> None:
        try:
            _data_dir().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _sync_session_setting(self) -> None:
        text = self._session_text()
        self._settings["session_actions"] = text
        try:
            self._ensure_data_dir()
            (_data_dir() / "session_actions.json").write_text(json.dumps(self._session_actions[-250:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _session_text(self) -> str:
        if not self._session_actions:
            return "Noch keine Aktionen in dieser Session."
        lines = []
        for item in self._session_actions[-80:]:
            ts = time.strftime("%H:%M:%S", time.localtime(float(item.get("ts") or time.time())))
            ok = "OK" if item.get("ok") else "FEHLER"
            platform = item.get("platform") or "?"
            action = item.get("action") or "?"
            user = item.get("user") or "?"
            word = item.get("word") or ""
            detail = item.get("detail") or ""
            lines.append(f"{ts} | {ok} | {platform} | {action} | {user} | {word} | {detail}")
        return "\n".join(lines)

    def _remember_action(self, platform: str, action: str, user: str, word: str, reason: str, ok: bool, detail: str, *, duration: int = 0, message_id: str = "") -> None:
        with self._lock:
            self._session_actions.append({
                "ts": time.time(),
                "platform": platform,
                "action": action,
                "user": user,
                "word": word,
                "reason": reason,
                "ok": bool(ok),
                "detail": detail,
                "duration": duration,
                "message_id": message_id,
            })
            self._session_actions = self._session_actions[-250:]
            self._sync_session_setting()

    def _recent_hit(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            for old, ts in list(self._recent.items()):
                if now - float(ts or 0.0) > 15.0:
                    self._recent.pop(old, None)
            if key in self._recent and now - float(self._recent[key] or 0.0) <= 10.0:
                return True
            self._recent[key] = now
        return False

    def _platform_enabled(self, settings: dict[str, Any], platform: str) -> bool:
        platform = str(platform or "").strip().lower()
        if platform == "tiktok":
            return False
        if platform not in {"twitch", "kick", "youtube"}:
            return False
        return _as_bool(settings.get(f"{platform}_enabled"), True)

    def _minutes_to_seconds(self, minutes_value: Any, seconds_fallback: Any = None, default_seconds: int = 600) -> int:
        if minutes_value not in (None, ""):
            minutes = _to_int(minutes_value, max(1, int(default_seconds / 60) if default_seconds else 10), 1, 20160)
            return minutes * 60
        return _to_int(seconds_fallback, default_seconds, 1, 1209600)

    def _parse_rule_text_line(self, platform: str, line: str, default_action: str, default_duration: int) -> dict[str, Any] | None:
        raw = str(line or "").strip()
        if not raw:
            return None
        parts = [part.strip() for part in raw.split("|")]
        word = parts[0].strip().lower()
        if not word:
            return None
        action = (parts[1].strip().lower() if len(parts) > 1 and parts[1].strip() else default_action)
        if action not in {"delete", "timeout", "ban"}:
            action = default_action if default_action in {"delete", "timeout", "ban"} else "delete"
        duration = _to_int(parts[2], default_duration, 1, 1209600) if len(parts) > 2 else default_duration
        return {"platform": platform, "word": word, "action": action, "duration": duration, "source": "bulk"}

    def _platform_rules(self, settings: dict[str, Any], platform: str) -> list[dict[str, Any]]:
        platform = str(platform or "").strip().lower()
        default_action = str(settings.get(f"{platform}_default_action") or settings.get("default_action") or "delete").strip().lower()
        if default_action not in {"delete", "timeout", "ban"}:
            default_action = "delete"
        default_duration = self._minutes_to_seconds(settings.get(f"{platform}_default_timeout_minutes"), settings.get(f"{platform}_default_timeout_seconds"), _to_int(settings.get("default_timeout_seconds"), 600, 1, 1209600))
        rules: list[dict[str, Any]] = []
        for line in str(settings.get(f"{platform}_blacklist_bulk") or "").splitlines():
            rule = self._parse_rule_text_line(platform, line, default_action, default_duration)
            if rule:
                rules.append(rule)
        for idx in range(1, 13):
            word = str(settings.get(f"{platform}_rule_{idx}_word") or "").strip().lower()
            if not word:
                continue
            action = str(settings.get(f"{platform}_rule_{idx}_action") or default_action).strip().lower()
            if action not in {"delete", "timeout", "ban"}:
                action = default_action
            duration = self._minutes_to_seconds(settings.get(f"{platform}_rule_{idx}_timeout_minutes"), settings.get(f"{platform}_rule_{idx}_timeout_seconds"), default_duration)
            rules.append({"platform": platform, "word": word, "action": action, "duration": duration, "source": f"rule_{idx}"})
        # Backward compatibility: old global blocked_words still works until the user moves entries into the platform tabs.
        if not rules:
            action = str(settings.get("default_action") or default_action or "delete").strip().lower()
            if action not in {"delete", "timeout", "ban"}:
                action = "delete"
            duration = _to_int(settings.get("default_timeout_seconds"), default_duration, 1, 1209600)
            for word in _split_words(settings.get("blocked_words")):
                if word:
                    rules.append({"platform": platform, "word": word, "action": action, "duration": duration, "source": "legacy"})
        # Deduplicate by word/action/duration while preserving order.
        seen: set[tuple[str, str, int]] = set()
        out: list[dict[str, Any]] = []
        for rule in rules:
            key = (str(rule.get("word") or ""), str(rule.get("action") or ""), int(rule.get("duration") or 0))
            if key in seen:
                continue
            seen.add(key)
            out.append(rule)
        return out

    def _rule_matches(self, rule: dict[str, Any], text: str) -> bool:
        word = str(rule.get("word") or "").strip().lower()
        if not word:
            return False
        low = text.lower()
        if " " in word:
            return word in low
        return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", low, re.IGNORECASE) is not None

    def _find_matching_rule(self, settings: dict[str, Any], platform: str, text: str) -> dict[str, Any] | None:
        for rule in self._platform_rules(settings, platform):
            if self._rule_matches(rule, text):
                return rule
        return None

    def _find_blocked_word(self, settings: dict[str, Any], text: str) -> str:
        # Kept for compatibility with older callers/tests.
        rule = self._find_matching_rule(settings, "twitch", text)
        return str(rule.get("word") or "") if rule else ""

    def _format(self, fmt: Any, user: str, platform: str, word: str, action: str, duration: int) -> str:
        return str(fmt or "").replace("{user}", user).replace("{platform}", platform).replace("{word}", word).replace("{action}", action).replace("{duration}", str(duration)).replace("(User)", user)

    def _message_value(self, msg: Any, key: str, default: Any = "") -> Any:
        if isinstance(msg, dict):
            return msg.get(key, default)
        return getattr(msg, key, default)

    def _message_type(self, msg: Any) -> str:
        return str(self._message_value(msg, "message_type", self._message_value(msg, "type", "chat")) or "chat").strip().lower()

    def _message_platform(self, msg: Any) -> str:
        raw = str(self._message_value(msg, "platform", self._message_value(msg, "source_plugin_id", "")) or "").strip().lower()
        return {"twitch_chat": "twitch", "kick_chat": "kick", "youtube_chat": "youtube", "tiktok_chat": "tiktok"}.get(raw, raw)

    def _message_text(self, msg: Any) -> str:
        return _clean_text(self._message_value(msg, "text", self._message_value(msg, "message", self._message_value(msg, "content", ""))))

    def _message_username(self, msg: Any) -> str:
        return _clean_text(self._message_value(msg, "username", self._message_value(msg, "display_name", self._message_value(msg, "user", ""))))

    def _message_channel(self, msg: Any) -> str:
        return _clean_text(self._message_value(msg, "channel", ""))

    def _message_id(self, msg: Any) -> str:
        return _clean_text(self._message_value(msg, "message_id", self._message_value(msg, "id", "")))

    def _message_live_chat_id(self, msg: Any) -> str:
        return _clean_text(self._message_value(msg, "live_chat_id", self._message_value(msg, "liveChatId", "")))

    def _message_author_channel_id(self, msg: Any) -> str:
        return _clean_text(self._message_value(msg, "author_channel_id", self._message_value(msg, "authorChannelId", self._message_value(msg, "channel_id", ""))))

    def _http_json(self, url: str, *, method: str = "GET", data: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 15.0) -> tuple[int, Any, str]:
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
        req_headers = dict(headers or {})
        if body is not None:
            req_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw.strip() else {}
                return int(resp.status), parsed, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except Exception:
                parsed = {}
            return int(exc.code), parsed, raw
        except Exception as exc:
            return 0, {}, str(exc)

    def _clean_token(self, value: Any) -> str:
        token = str(value or "").strip()
        if token.lower().startswith("oauth:"):
            token = token[6:]
        if token.lower().startswith("bearer "):
            token = token[7:]
        return token.strip()

    # Twitch
    def _twitch_settings(self) -> dict[str, Any]:
        return self._host_platform_settings("twitch")

    def _twitch_token(self, settings: dict[str, Any]) -> str:
        for key in ("access_token", "bot_access_token", "main_access_token", "twitch_oauth_token", "oauth_token"):
            token = self._clean_token(settings.get(key))
            if token:
                return token
        return ""

    def _twitch_client_id(self, settings: dict[str, Any]) -> str:
        return str(settings.get("client_id") or settings.get("twitch_client_id") or "").strip()

    def _twitch_channel(self, settings: dict[str, Any]) -> str:
        return _clean_login(settings.get("channel") or settings.get("main") or settings.get("main_account") or settings.get("main_username"))

    def _twitch_headers(self, settings: dict[str, Any]) -> dict[str, str]:
        token = self._twitch_token(settings)
        client_id = self._twitch_client_id(settings)
        return {"Authorization": f"Bearer {token}", "Client-Id": client_id, "Accept": "application/json"}

    def _twitch_validate(self, settings: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
        token = self._twitch_token(settings)
        if not token:
            return False, {}, "OAuth Token fehlt"
        status, data, raw = self._http_json(TWITCH_VALIDATE_URL, headers={"Authorization": f"OAuth {token}"})
        if status >= 400 or status == 0:
            return False, {}, f"Validate fehlgeschlagen: HTTP {status} {raw[:240]}"
        if not self._twitch_client_id(settings):
            settings["client_id"] = str(data.get("client_id") or "")
        return True, data if isinstance(data, dict) else {}, "ok"

    def _twitch_user_id(self, settings: dict[str, Any], login: str) -> str:
        login = _clean_login(login)
        if not login:
            return ""
        cached = self._twitch_user_cache.get(login)
        if cached and time.time() - cached[1] < 3600:
            return cached[0]
        url = TWITCH_USERS_URL + "?login=" + urllib.parse.quote(login)
        status, data, raw = self._http_json(url, headers=self._twitch_headers(settings))
        if status < 400 and isinstance(data, dict):
            rows = data.get("data") or []
            if rows and isinstance(rows[0], dict):
                uid = str(rows[0].get("id") or "")
                if uid:
                    self._twitch_user_cache[login] = (uid, time.time())
                    return uid
        self._log(f"Twitch User-ID nicht gefunden fuer {login}: HTTP {status} {raw[:180]}")
        return ""

    def _twitch_ids(self, settings: dict[str, Any], target_user: str = "") -> tuple[bool, dict[str, str], str]:
        ok, validation, msg = self._twitch_validate(settings)
        if not ok:
            return False, {}, msg
        channel = self._twitch_channel(settings)
        broadcaster_id = str(settings.get("broadcaster_id") or settings.get("channel_id") or "").strip() or self._twitch_user_id(settings, channel)
        moderator_id = str(validation.get("user_id") or settings.get("bot_user_id") or settings.get("user_id") or "").strip()
        target_id = self._twitch_user_id(settings, target_user) if target_user else ""
        if not broadcaster_id:
            return False, {}, "Broadcaster-ID fehlt"
        if not moderator_id:
            return False, {}, "Moderator-ID fehlt"
        if target_user and not target_id:
            return False, {}, f"User-ID fehlt fuer {target_user}"
        return True, {"broadcaster_id": broadcaster_id, "moderator_id": moderator_id, "target_id": target_id}, "ok"

    def _test_twitch(self, settings: dict[str, Any]) -> tuple[bool, str]:
        tw = self._twitch_settings()
        ok, validation, msg = self._twitch_validate(tw)
        if not ok:
            return False, msg
        scopes = set(str(s).strip() for s in (validation.get("scopes") or []))
        missing = [s for s in TWITCH_REQUIRED_SCOPES if s not in scopes]
        if missing:
            return False, "fehlende Scopes: " + ", ".join(missing)
        return True, f"ok als {validation.get('login') or validation.get('user_name') or 'OAuth-User'}"

    def _twitch_ban_payload(self, user_id: str, reason: str, duration: int = 0) -> dict[str, Any]:
        data: dict[str, Any] = {"user_id": user_id, "reason": reason[:500]}
        if duration and duration > 0:
            data["duration"] = int(duration)
        return {"data": data}

    def _twitch_ban_or_timeout(self, username: str, reason: str, duration: int = 0) -> tuple[bool, str]:
        tw = self._twitch_settings()
        ok, ids, msg = self._twitch_ids(tw, username)
        if not ok:
            return False, msg
        qs = urllib.parse.urlencode({"broadcaster_id": ids["broadcaster_id"], "moderator_id": ids["moderator_id"]})
        status, data, raw = self._http_json(TWITCH_BANS_URL + "?" + qs, method="POST", headers=self._twitch_headers(tw), data=self._twitch_ban_payload(ids["target_id"], reason, duration))
        if status < 400 and status != 0:
            return True, "Twitch Timeout/Ban ausgefuehrt"
        return False, f"Twitch Timeout/Ban fehlgeschlagen: HTTP {status} {raw[:300]}"

    def _twitch_unban(self, username: str) -> tuple[bool, str]:
        tw = self._twitch_settings()
        ok, ids, msg = self._twitch_ids(tw, username)
        if not ok:
            return False, msg
        qs = urllib.parse.urlencode({"broadcaster_id": ids["broadcaster_id"], "moderator_id": ids["moderator_id"], "user_id": ids["target_id"]})
        status, _data, raw = self._http_json(TWITCH_BANS_URL + "?" + qs, method="DELETE", headers=self._twitch_headers(tw))
        if status in {200, 204}:
            return True, "Twitch User freigegeben"
        return False, f"Twitch Unban fehlgeschlagen: HTTP {status} {raw[:300]}"

    def _twitch_delete_message(self, message_id: str) -> tuple[bool, str]:
        if not message_id:
            return False, "Twitch Delete: Message-ID fehlt"
        tw = self._twitch_settings()
        ok, ids, msg = self._twitch_ids(tw)
        if not ok:
            return False, msg
        qs = urllib.parse.urlencode({"broadcaster_id": ids["broadcaster_id"], "moderator_id": ids["moderator_id"], "message_id": message_id})
        status, _data, raw = self._http_json(TWITCH_DELETE_CHAT_URL + "?" + qs, method="DELETE", headers=self._twitch_headers(tw))
        if status in {200, 204}:
            return True, "Twitch Nachricht geloescht"
        return False, f"Twitch Delete fehlgeschlagen: HTTP {status} {raw[:300]}"

    # Kick
    def _kick_settings(self) -> dict[str, Any]:
        return self._host_platform_settings("kick")

    def _kick_token(self, settings: dict[str, Any]) -> str:
        for key in ("access_token", "bot_access_token", "main_access_token"):
            token = self._clean_token(settings.get(key))
            if token:
                return token
        return ""

    def _kick_broadcaster_id(self, settings: dict[str, Any]) -> str:
        for key in ("broadcaster_user_id", "channel_id", "main_user_id"):
            value = str(settings.get(key) or "").strip()
            if value:
                return value
        return ""

    def _kick_headers(self, settings: dict[str, Any]) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._kick_token(settings)}", "Accept": "application/json", "Content-Type": "application/json"}

    def _test_kick(self, settings: dict[str, Any]) -> tuple[bool, str]:
        kick = self._kick_settings()
        if not self._kick_token(kick):
            return False, "OAuth Token fehlt"
        if not self._kick_broadcaster_id(kick):
            return False, "Broadcaster/Channel-ID fehlt noch in Plattformdaten"
        scopes = {part.strip().lower() for part in str(kick.get("scopes") or kick.get("main_scopes") or "").split() if part.strip()}
        missing = [scope for scope in KICK_REQUIRED_SCOPES if scope not in scopes]
        if missing:
            return False, "fehlende Scopes: " + ", ".join(missing)
        return True, "Token und Broadcaster-ID vorhanden"

    def _kick_mod_request(self, username: str, reason: str, duration: int | None, delete: bool = False) -> tuple[bool, str]:
        kick = self._kick_settings()
        token = self._kick_token(kick)
        broadcaster_id = self._kick_broadcaster_id(kick)
        if not token:
            return False, "Kick OAuth Token fehlt"
        if not broadcaster_id:
            return False, "Kick Broadcaster-ID fehlt"
        user = _clean_login(username)
        if not user:
            return False, "Kick User fehlt"

        base_payloads: list[dict[str, Any]] = []
        bid_value: Any = int(broadcaster_id) if str(broadcaster_id).isdigit() else broadcaster_id
        for user_key in ("user_login", "username", "user_name"):
            payload: dict[str, Any] = {"broadcaster_user_id": bid_value, user_key: user, "reason": reason[:500]}
            if duration is not None and duration > 0:
                payload["duration"] = int(duration)
            base_payloads.append(payload)
        last_detail = ""
        method = "DELETE" if delete else "POST"
        for payload in base_payloads:
            status, _data, raw = self._http_json(KICK_MOD_BANS_URL, method=method, headers=self._kick_headers(kick), data=payload)
            if status and status < 400:
                return True, f"Kick Moderation API {method} ok"
            last_detail = f"HTTP {status} {raw[:240]}"
        # Practical fallback: many Kick moderation setups still accept slash commands from a mod/bot account.
        if self._host is not None and not delete:
            cmd = f"/timeout {user} {int(duration)} {reason}" if duration and duration > 0 else f"/ban {user} {reason}"
            try:
                if self._host.send_platform_message("kick", cmd, sender=self.plugin_id):
                    return True, "Kick API nicht bestaetigt, Chat-Modbefehl gesendet"
            except Exception as exc:
                last_detail += f" | fallback: {exc}"
        if self._host is not None and delete:
            try:
                if self._host.send_platform_message("kick", f"/unban {user}", sender=self.plugin_id):
                    return True, "Kick API nicht bestaetigt, /unban gesendet"
            except Exception as exc:
                last_detail += f" | fallback: {exc}"
        return False, "Kick Moderation fehlgeschlagen: " + last_detail

    def _kick_delete_message(self, message_id: str) -> tuple[bool, str]:
        if not message_id:
            return False, "Kick Delete: Message-ID fehlt"
        return False, "Kick Delete einzelner Nachrichten ist in modalot noch nicht per Public API angebunden"

    # YouTube
    def _youtube_settings(self) -> dict[str, Any]:
        return self._host_platform_settings("youtube")

    def _youtube_token(self, settings: dict[str, Any]) -> str:
        for key in ("access_token", "bot_access_token", "main_access_token", "youtube_access_token"):
            token = self._clean_token(settings.get(key))
            if token:
                return token
        return ""

    def _youtube_headers(self, settings: dict[str, Any]) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._youtube_token(settings)}", "Accept": "application/json", "Content-Type": "application/json"}

    def _youtube_live_chat_id(self, settings: dict[str, Any]) -> str:
        runtime = _clean_text(self._settings.get("youtube_live_chat_id_runtime"))
        if runtime and runtime != "__web_chat__":
            return runtime
        yt = self._youtube_settings()
        for key in ("live_chat_id", "active_live_chat_id", "api_live_chat_id", "youtube_live_chat_id"):
            value = _clean_text(settings.get(key) or yt.get(key))
            if value and value != "__web_chat__":
                return value
        return ""

    def _test_youtube(self, settings: dict[str, Any]) -> tuple[bool, str]:
        yt = self._youtube_settings()
        if not self._youtube_token(yt):
            return False, "OAuth Token fehlt"
        scopes = {part.strip().lower() for part in str(yt.get("scopes") or yt.get("scope") or yt.get("main_scopes") or "").split() if part.strip()}
        missing = [scope for scope in YOUTUBE_REQUIRED_SCOPES if scope not in scopes]
        if missing:
            return False, "fehlende Scopes: " + ", ".join(missing)
        live_chat_id = self._youtube_live_chat_id(settings)
        if not live_chat_id:
            return False, "live_chat_id fehlt noch; youtube_chat muss sie im Payload oder in Plattformdaten liefern"
        return True, "Token und live_chat_id vorhanden"

    def _youtube_delete_message(self, message_id: str) -> tuple[bool, str]:
        if not message_id:
            return False, "YouTube Delete: message_id/liveChatMessage.id fehlt"
        yt = self._youtube_settings()
        if not self._youtube_token(yt):
            return False, "YouTube OAuth Token fehlt"
        url = YOUTUBE_LIVE_CHAT_MESSAGES_URL + "?" + urllib.parse.urlencode({"id": message_id})
        status, _data, raw = self._http_json(url, method="DELETE", headers=self._youtube_headers(yt))
        if status in {200, 204}:
            return True, "YouTube Nachricht geloescht"
        return False, f"YouTube Delete fehlgeschlagen: HTTP {status} {raw[:300]}"

    def _youtube_ban_or_timeout(self, target_channel_id: str, reason: str, duration: int = 0) -> tuple[bool, str]:
        yt = self._youtube_settings()
        token = self._youtube_token(yt)
        if not token:
            return False, "YouTube OAuth Token fehlt"
        live_chat_id = self._youtube_live_chat_id(self._current_settings())
        if not live_chat_id:
            return False, "YouTube live_chat_id fehlt"
        channel_id = _clean_text(target_channel_id)
        if not channel_id:
            return False, "YouTube author_channel_id fehlt"
        snippet: dict[str, Any] = {
            "liveChatId": live_chat_id,
            "type": "temporary" if duration and duration > 0 else "permanent",
            "bannedUserDetails": {"channelId": channel_id},
        }
        if duration and duration > 0:
            snippet["banDurationSeconds"] = int(duration)
        payload = {"snippet": snippet}
        status, data, raw = self._http_json(YOUTUBE_LIVE_CHAT_BANS_URL + "?part=snippet", method="POST", headers=self._youtube_headers(yt), data=payload)
        if status and status < 400:
            ban_id = ""
            if isinstance(data, dict):
                ban_id = str(data.get("id") or "").strip()
            if ban_id:
                self._settings[f"youtube_ban_id:{channel_id}"] = ban_id
            return True, "YouTube Timeout/Ban ausgefuehrt"
        return False, f"YouTube Timeout/Ban fehlgeschlagen: HTTP {status} {raw[:300]}"

    def _youtube_unban(self, target_channel_id: str) -> tuple[bool, str]:
        yt = self._youtube_settings()
        if not self._youtube_token(yt):
            return False, "YouTube OAuth Token fehlt"
        channel_id = _clean_text(target_channel_id)
        if not channel_id:
            return False, "YouTube Channel-ID fehlt"
        ban_id = _clean_text(self._settings.get(f"youtube_ban_id:{channel_id}"))
        if not ban_id:
            # YouTube delete braucht die liveChatBan.id. Ohne gespeicherte ban_id kann modalot
            # nicht sauber entbannen; diese ID kommt normalerweise aus liveChatBans.insert.
            return False, "YouTube Unban braucht liveChatBan.id; nach modalot-Ban automatisch gespeichert, sonst manuell nicht sicher moeglich"
        url = YOUTUBE_LIVE_CHAT_BANS_URL + "?" + urllib.parse.urlencode({"id": ban_id})
        status, _data, raw = self._http_json(url, method="DELETE", headers=self._youtube_headers(yt))
        if status in {200, 204}:
            self._settings.pop(f"youtube_ban_id:{channel_id}", None)
            return True, "YouTube User freigegeben"
        return False, f"YouTube Unban fehlgeschlagen: HTTP {status} {raw[:300]}"

    # Platform dispatch
    def _delete_message(self, settings: dict[str, Any], platform: str, message_id: str, channel: str = "") -> tuple[bool, str]:
        platform = platform.lower().strip()
        if platform == "twitch":
            return self._twitch_delete_message(message_id)
        if platform == "kick":
            return self._kick_delete_message(message_id)
        if platform == "youtube":
            return self._youtube_delete_message(message_id)
        return False, f"{platform} Delete nicht unterstuetzt"

    def _timeout_user(self, settings: dict[str, Any], platform: str, username: str, duration: int, reason: str) -> tuple[bool, str]:
        platform = platform.lower().strip()
        if platform == "twitch":
            return self._twitch_ban_or_timeout(username, reason, duration)
        if platform == "kick":
            return self._kick_mod_request(username, reason, duration, delete=False)
        if platform == "youtube":
            return self._youtube_ban_or_timeout(username, reason, duration)
        return False, f"{platform} Timeout nicht unterstuetzt"

    def _ban_user(self, settings: dict[str, Any], platform: str, username: str, reason: str) -> tuple[bool, str]:
        platform = platform.lower().strip()
        if platform == "twitch":
            return self._twitch_ban_or_timeout(username, reason, 0)
        if platform == "kick":
            return self._kick_mod_request(username, reason, 0, delete=False)
        if platform == "youtube":
            return self._youtube_ban_or_timeout(username, reason, 0)
        return False, f"{platform} Ban nicht unterstuetzt"

    def _unban_user(self, settings: dict[str, Any], platform: str, username: str) -> tuple[bool, str]:
        platform = platform.lower().strip()
        if platform == "twitch":
            return self._twitch_unban(username)
        if platform == "kick":
            return self._kick_mod_request(username, "unban", 0, delete=True)
        if platform == "youtube":
            return self._youtube_unban(username)
        return False, f"{platform} Unban nicht unterstuetzt"


def create_plugin():
    return ModalotPlugin()
