from __future__ import annotations
from pathlib import Path
from common import as_bool
from writers.tiktok_browser_writer import TikTokBrowserWriter
from writers.twitch_writer import TwitchWriter
from writers.youtube_writer import YouTubeWriter
from writers.kick_writer import KickWriter

class PlatformOutputs:
    def __init__(self, plugin_dir: Path, host_getter, logger) -> None:
        self._log = logger
        self.twitch = TwitchWriter(host_getter, logger)
        self.tiktok = TikTokBrowserWriter(plugin_dir, logger)
        self.youtube = YouTubeWriter(host_getter, logger)
        self.kick = KickWriter(host_getter, logger)

    def _normalize_platform(self, platform: str) -> str:
        p = str(platform or '').strip().lower()
        if p in {'tt', 'tiktok', 'tiktok_live'}:
            return 'tiktok'
        if p in {'twitch', 'twitch_chat'}:
            return 'twitch'
        if p in {'youtube', 'youtube_live', 'youtube_chat', 'yt'}:
            return 'youtube'
        if p in {'kick', 'kick_chat'}:
            return 'kick'
        return p

    def send_to_platform(self, settings: dict, message: str, target_platform: str) -> bool:
        """Send directly to an explicit target platform.

        Used for optional AI mirroring/cross-platform context. This deliberately
        ignores the source-platform lock from send_to_source(), but still obeys
        the target write_* toggles.
        """
        p = self._normalize_platform(target_platform)
        if p == 'twitch':
            if not as_bool(settings.get('write_twitch'), False):
                self._log('Spiegelung nicht gesendet: Twitch schreiben ist deaktiviert.')
                return False
            return self.twitch.send(settings, message)
        if p == 'tiktok':
            if not as_bool(settings.get('write_tiktok'), False):
                self._log('Spiegelung nicht gesendet: TikTok schreiben ist deaktiviert.')
                return False
            return self.tiktok.send(settings, message)
        if p == 'youtube':
            if not as_bool(settings.get('write_youtube'), False) and not self.youtube.has_send_access(settings):
                self._log('Spiegelung nicht gesendet: YouTube schreiben ist deaktiviert.')
                return False
            return self.youtube.send(settings, message)
        if p == 'kick':
            # KickWriter prüft Haupttool/kick_chat selbst. Alte gespeicherte
            # botalot-Settings können write_kick=False enthalten, obwohl der
            # zentrale Kick-Bot bereits angemeldet ist.
            return self.kick.send(settings, message)
        self._log(f'Spiegelung nicht gesendet: Plattform "{target_platform}" hat keine Sendebrücke.')
        return False

    def send_to_source(self, settings: dict, message: str, source_platform: str) -> bool:
        """Send only back to the platform where the trigger came from.

        This prevents TikTok triggers from being sent to Twitch just because Twitch
        writing is enabled in the UI. The write_* toggles now mean:
        "allow replies on this source platform", not "crosspost to this platform".
        """
        p = self._normalize_platform(source_platform)
        if p == 'twitch':
            if not as_bool(settings.get('write_twitch'), False):
                self._log('Antwort nicht gesendet: Twitch war die Eingangsplattform, aber Twitch schreiben ist deaktiviert.')
                return False
            return self.twitch.send(settings, message)

        if p == 'tiktok':
            if not as_bool(settings.get('write_tiktok'), False):
                self._log('Antwort nicht gesendet: TikTok war die Eingangsplattform, aber TikTok schreiben ist deaktiviert.')
                return False
            return self.tiktok.send(settings, message)

        if p == 'youtube':
            if not as_bool(settings.get('write_youtube'), False) and not self.youtube.has_send_access(settings):
                self._log('Antwort nicht gesendet: YouTube war die Eingangsplattform, aber YouTube schreiben ist deaktiviert.')
                return False
            return self.youtube.send(settings, message)

        if p == 'kick':
            return self.kick.send(settings, message)


        self._log(f'Antwort nicht gesendet: Plattform "{source_platform}" hat keine Sendebrücke.')
        return False



    def delete_message(self, settings: dict, source_platform: str, message_id: str, channel: str = '') -> bool:
        p = self._normalize_platform(source_platform)
        msg_id = str(message_id or '').strip()
        if not msg_id:
            self._log('Moderation Nachricht löschen übersprungen: Message-ID fehlt.')
            return False
        if p == 'twitch':
            return self.twitch.delete_message(settings, msg_id, channel)
        self._log(f'Moderation Nachricht löschen nicht möglich: Plattform "{source_platform}" hat keine Lösch-Brücke.')
        return False

    def ban_user(self, settings: dict, source_platform: str, username: str, reason: str = '') -> bool:
        p = self._normalize_platform(source_platform)
        user = str(username or '').strip().lstrip('@')
        if not user:
            self._log('Moderation Ban übersprungen: Nutzer fehlt.')
            return False
        if p == 'twitch':
            return self.twitch.ban_user(settings, user, reason)
        if p == 'tiktok':
            return self.tiktok.ban_user(settings, user, reason)
        self._log(f'Moderation Ban nicht möglich: Plattform "{source_platform}" hat keine Ban-Brücke.')
        return False

    def unban_user(self, settings: dict, source_platform: str, username: str) -> bool:
        p = self._normalize_platform(source_platform)
        user = str(username or '').strip().lstrip('@')
        if not user:
            self._log('Moderation Unban übersprungen: Nutzer fehlt.')
            return False
        if p == 'twitch':
            return self.twitch.unban_user(settings, user)
        if p == 'tiktok':
            return self.tiktok.unban_user(settings, user)
        self._log(f'Moderation Unban nicht möglich: Plattform "{source_platform}" hat keine Unban-Brücke.')
        return False

    def send_enabled(self, settings: dict, message: str) -> bool:
        # Legacy fallback only. New botalot routing must use send_to_source().
        sent_any = False
        if as_bool(settings.get('write_twitch'), False):
            sent_any = self.twitch.send(settings, message) or sent_any
        if as_bool(settings.get('write_tiktok'), False):
            sent_any = self.tiktok.send(settings, message) or sent_any
        if as_bool(settings.get('write_youtube'), False):
            sent_any = self.youtube.send(settings, message) or sent_any
        if as_bool(settings.get('write_kick'), False):
            sent_any = self.kick.send(settings, message) or sent_any
        return sent_any
