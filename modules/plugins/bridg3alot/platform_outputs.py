from __future__ import annotations

from pathlib import Path
from typing import Any

from common import as_bool


class PlatformOutputs:
    def __init__(self, plugin_dir: Path, host_getter, logger) -> None:
        self._host_getter = host_getter
        self._log = logger

    def _host(self) -> Any:
        try:
            return self._host_getter() if callable(self._host_getter) else None
        except Exception:
            return None

    def _normalize_platform(self, platform: str) -> str:
        p = str(platform or "").strip().lower()
        if p in {"tt", "tiktok", "tiktok_chat"}:
            return "tiktok"
        if p in {"twitch", "twitch_chat"}:
            return "twitch"
        if p in {"youtube", "youtube_live", "youtube_chat", "yt"}:
            return "youtube"
        if p in {"kick", "kick_chat"}:
            return "kick"
        return p

    def _send(self, platform: str, message: str) -> bool:
        p = self._normalize_platform(platform)
        host = self._host()
        fn = getattr(host, "send_platform_message", None) if host is not None else None
        if not callable(fn):
            self._log(f"{p} nicht gesendet: zentraler Host-Sendepfad fehlt.")
            return False
        try:
            ok = bool(fn(p, message, sender="bridg3alot"))
        except TypeError:
            ok = bool(fn(p, message))
        except Exception as exc:
            self._log(f"{p} senden ueber Haupttool fehlgeschlagen: {exc}")
            return False
        if not ok:
            self._log(f"{p} senden ueber Haupttool nicht erfolgreich.")
        return ok

    def send_to_platform(self, settings: dict, message: str, target_platform: str) -> bool:
        p = self._normalize_platform(target_platform)
        if p == "twitch" and not as_bool(settings.get("write_twitch"), False):
            return False
        if p == "tiktok" and not as_bool(settings.get("write_tiktok"), False):
            return False
        if p == "youtube" and not as_bool(settings.get("write_youtube"), False):
            return False
        if p == "kick" and not as_bool(settings.get("write_kick"), False):
            return False
        return self._send(p, message)

    def send_to_source(self, settings: dict, message: str, source_platform: str) -> bool:
        return self.send_to_platform(settings, message, source_platform)

    def send_enabled(self, settings: dict, message: str) -> bool:
        sent = False
        for platform in ("twitch", "tiktok", "youtube", "kick"):
            if as_bool(settings.get(f"write_{platform}"), False):
                sent = self._send(platform, message) or sent
        return sent

    def delete_message(self, settings: dict, source_platform: str, message_id: str, channel: str = "") -> bool:
        self._log("Moderation loeschen ist in bridg3alot entfernt; Plattformaktionen laufen nur ueber zentrale Integrationen.")
        return False

    def ban_user(self, settings: dict, source_platform: str, username: str, reason: str = "") -> bool:
        self._log("Moderation Ban ist in bridg3alot entfernt; Plattformaktionen laufen nur ueber zentrale Integrationen.")
        return False

    def unban_user(self, settings: dict, source_platform: str, username: str) -> bool:
        self._log("Moderation Unban ist in bridg3alot entfernt; Plattformaktionen laufen nur ueber zentrale Integrationen.")
        return False
