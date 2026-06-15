
from __future__ import annotations

import threading
import time
import webbrowser
import re
from pathlib import Path
from typing import Any
import sys

# Make sibling module imports work with godisalotachat's file-based plugin loader.
_PLUGIN_IMPORT_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_IMPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_IMPORT_DIR))

from shared.models import PluginStatus
from shared.plugin_base import ProviderPlugin, PluginHost

from ai_client import OpenAIChatClient
from common import as_bool, clean_text, norm, strip_response, to_float, to_int
from context_memory import ContextMemory
from platform_outputs import PlatformOutputs
from trigger_matcher import TriggerMatcher

PLUGIN_VERSION = '1.14'
PLUGIN_NAME = f'botalot ver. {PLUGIN_VERSION}'
PLUGIN_DIR = Path(__file__).resolve().parent

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return PLUGIN_DIR / 'data'

DATA_DIR = _main_data_dir('botalot')
MODERATION_UNBAN_SLOT_COUNT = 200
MODERATION_VISIBLE_SLOT_HINT = 10
TRIGGER_FILE = DATA_DIR / 'triggers' / 'ursula_words.txt'
PROMPT_FILE = DATA_DIR / 'prompts' / 'default_prompt.txt'

DEFAULT_PROMPT = '''Du bist botalot im Stream von godis3mpty.

Du antwortest wie ein echter Chatter, nicht wie eine KI.
Keine Smileys. Keine Sternchenaktionen. Keine "hehe", "zwinker", "als KI", "ich hoffe", "gerne", "natürlich". Keine künstlich freundlichen Floskeln.

Antworten:
- kurz
- direkt
- trocken
- ehrlich
- leicht sarkastisch
- menschlich
- nicht wiederholend

Wenn jemand eine normale Frage stellt:
- antworte verständlich und sachlich korrekt
- wissenschaftlich korrekt wenn sinnvoll
- aber ohne Lehrerton oder Wikipedia-Stil

Wenn jemand Unsinn schreibt:
- kontere locker, trocken oder leicht frech
- aber nicht beleidigend

Wenn Ursula erwähnt wird:
- behandle es wie einen ausgelutschten Running Gag aus dem Chat
- reagiere genervt auf den SCHREIBER, nicht auf Ursula selbst
- Beispiele:
  - "du konntest es echt nicht lassen oder"
  - "da ist wieder der Ursula-Typ"
  - "lass Mr. Streamer mit deinem Ursula-Fieber in Ruhe"

Wichtig:
- Ursula nur erwähnen, wenn der aktuelle User auch wirklich Ursula geschrieben hat
- niemals zufällig Ursula in andere Gespräche ziehen
- jeder User hat seinen eigenen Kontext
- antworte immer in der Sprache des jeweiligen Users
- maximal 1-2 kurze Sätze
- niemals wie ein Supportbot klingen
- niemals Emojis oder Rollenspielstil benutzen'''

class BotalotPlugin(ProviderPlugin):
    plugin_id = 'botalot'
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = 'AI bot for all incoming godisalotachat messages. Twitch write + TikTok second-account browser bridge.'

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._enabled = False
        self._context = ContextMemory(10)
        self._triggers = TriggerMatcher(TRIGGER_FILE)
        self._ai = OpenAIChatClient(self._log)
        self._outputs = PlatformOutputs(PLUGIN_DIR, lambda: self._host, self._log)
        self._last_reply_at = 0.0
        self._last_by_platform: dict[str, float] = {}
        self._worker_busy = False
        self._recent_message_lock = threading.Lock()
        self._recent_messages: dict[str, float] = {}
        self._recent_outbound_lock = threading.Lock()
        self._recent_outbound: dict[str, float] = {}
        self._host_emit_original = None
        self._host_emit_filter_installed = False
        self._moderation_lock = threading.Lock()
        # Session-only moderation list: Twitch/Plattform-Bans bleiben extern bestehen,
        # die lokale UI-Liste startet bei jedem Programmstart leer.
        self._moderation_bans: list[dict[str, Any]] = []
        self._last_tiktok_is_live: bool | None = None
        self._tiktok_reloaded_for_current_live = False
        self._tiktok_live_reload_lock = threading.Lock()

    def settings_schema(self) -> list[dict[str, Any]]:
        """Settings UI layout.

        The host settings dialog renders real tabs from tab/ui_tab/category.
        Keep separators as a safe fallback for older builds.
        """
        def tab(name: str, items: list[dict[str, Any]], *, en: str | None = None) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for item in items:
                entry = dict(item)
                entry.setdefault('tab', name)
                entry.setdefault('ui_tab', name)
                entry.setdefault('category', name)
                if en:
                    entry.setdefault('tab_en', en)
                    entry.setdefault('ui_tab_en', en)
                out.append(entry)
            return out

        schema: list[dict[str, Any]] = []

        schema += tab('Übersicht', [
            {'key': 'section_overview', 'type': 'separator', 'label': 'botalot ver. 1.12 - Übersicht', 'label_en': 'botalot ver. 1.12 - Overview'},
            {'key': 'enabled', 'label': 'Bot aktiv', 'label_en': 'Bot enabled', 'type': 'bool'},
            {'key': 'autoconnect', 'label': 'Beim App-Start automatisch verbinden', 'label_en': 'Autoconnect on app start', 'type': 'bool', 'help': 'Öffnet/verbindet OpenAI/Twitch/TikTok beim Start. TikTok öffnet den Botbrowser automatisch.', 'help_en': 'Opens/connects OpenAI/Twitch/TikTok on startup. TikTok opens the bot browser automatically.'},
            {'key': 'section_connections', 'type': 'separator', 'label': 'Verbindungsstatus', 'label_en': 'Connection status'},
            {'key': 'openai_connection_status', 'label': 'OpenAI / ChatGPT', 'placeholder': '❔ Noch nicht verbunden', 'placeholder_en': '❔ Not connected yet', 'readonly': True},
            {'key': 'twitch_connection_status', 'label': 'Twitch OAuth / Senden', 'placeholder': '❔ Noch nicht verbunden', 'placeholder_en': '❔ Not connected yet', 'readonly': True},
            {'key': 'twitch_chat_live_status', 'label': 'Twitch Chat-Empfang', 'label_en': 'Twitch chat receiving', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'tiktok_connection_status', 'label': 'TikTok', 'placeholder': '❔ Noch nicht verbunden', 'placeholder_en': '❔ Not connected yet', 'readonly': True},
            {'key': 'youtube_connection_status', 'label': 'YouTube', 'placeholder': '🟡 vorbereitet / später', 'placeholder_en': '🟡 prepared / later', 'readonly': True},
            {'key': 'kick_connection_status', 'label': 'Kick', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'obs_connection_status', 'label': 'OBS', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'meld_connection_status', 'label': 'Meld Studio', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'button_connect_all', 'type': 'button', 'label': 'Status', 'label_en': 'Status', 'button_text': 'Alle Plattformen neu lesen / prüfen', 'button_text_en': 'Reload/check all platforms'},
        ], en='Overview')

        schema += tab('Plattformen', [
            {'key': 'section_platforms', 'type': 'separator', 'label': 'Zentrale Plattformdaten aus dem Haupttool', 'label_en': 'Central platform data from the main tool'},
            {'key': 'openai_connection_status', 'label': 'OpenAI / ChatGPT', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'twitch_connection_status', 'label': 'Twitch Schreiben/Mod', 'label_en': 'Twitch writing/mod', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'twitch_chat_live_status', 'label': 'Twitch Chat-Empfang', 'label_en': 'Twitch chat receiving', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'tiktok_connection_status', 'label': 'TikTok Schreiben', 'label_en': 'TikTok writing', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'youtube_connection_status', 'label': 'YouTube', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'kick_connection_status', 'label': 'Kick', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'obs_connection_status', 'label': 'OBS', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'meld_connection_status', 'label': 'Meld Studio', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'button_connect_all', 'type': 'button', 'label': 'Status', 'label_en': 'Status', 'button_text': 'Alle Plattformen neu lesen / prüfen', 'button_text_en': 'Reload/check all platforms'},
        ], en='Platforms')

        schema += tab('TikTok', [
            {'key': 'section_tiktok', 'type': 'separator', 'label': 'TikTok Botaccount-Browser', 'label_en': 'TikTok bot-account browser'},
            {'key': 'tiktok_connection_status', 'label': 'Status', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'read_tiktok', 'label': 'TikTok lesen (über tiktok_live)', 'label_en': 'Read TikTok (through tiktok_live)', 'type': 'bool', 'readonly': True},
            {'key': 'write_tiktok', 'label': 'In TikTok schreiben', 'label_en': 'Write to TikTok', 'type': 'bool', 'readonly': True},
            {'key': 'tiktok_second_account', 'label': 'TikTok Botaccount aus Haupttool', 'label_en': 'TikTok bot account from main tool', 'placeholder': 'aus Haupttool', 'readonly': True},
            {'key': 'tiktok_main_account', 'label': 'TikTok Mainaccount / Live-Kanal aus Haupttool', 'label_en': 'TikTok main account / live channel from main tool', 'placeholder': 'aus Haupttool', 'readonly': True},
            {'key': 'tiktok_resolved_live_url', 'label': 'TikTok Live URL automatisch', 'label_en': 'TikTok live URL automatic', 'placeholder': 'wird aus Mainaccount gebaut', 'placeholder_en': 'built from main account', 'readonly': True},
            {'key': 'tiktok_browser_path', 'label': 'Chrome/Edge Pfad aus Haupttool optional', 'label_en': 'Chrome/Edge path from main tool optional', 'placeholder': 'leer = Auto-Suche'},
            {'key': 'tiktok_profile_dir', 'label': 'TikTok Botprofil-Ordner', 'label_en': 'TikTok bot profile folder', 'placeholder': 'leer = automatisch in AppData speichern', 'placeholder_en': 'empty = save automatically in AppData', 'help': 'Hier bleiben TikTok-Cookies/Login vom Botaccount erhalten. Keine OAuth-/Accountdaten werden in botalot gespeichert.', 'help_en': 'TikTok cookies/login for the bot account stay here. No OAuth/account credentials are stored in botalot.'},
            {'key': 'tiktok_remote_debug_port', 'label': 'Browser Debug Port', 'type': 'number', 'min': 1024, 'max': 65535},
            {'key': 'tiktok_clipboard_focus_send', 'label': 'TikTok per Botaccount-Browser senden', 'label_en': 'Send TikTok through bot-account browser', 'type': 'bool', 'readonly': True, 'help': 'Wird aus "Schreiben aktiv" im Haupttool gesetzt.', 'help_en': 'Set from write enabled in the main tool.'},
            {'key': 'tiktok_send_delay_ms', 'label': 'TikTok Paste-Verzögerung ms', 'label_en': 'TikTok paste delay ms', 'type': 'number', 'min': 0, 'max': 3000},
            {'key': 'button_open_tiktok_bot_login', 'type': 'button', 'label': 'TikTok Botaccount', 'button_text': 'Botaccount-Browser / Login öffnen', 'button_text_en': 'Open bot-account browser / login'},
            {'key': 'button_open_tiktok_live', 'type': 'button', 'label': 'TikTok Main-Live', 'button_text': 'Main-Live im Botbrowser öffnen / reloaden', 'button_text_en': 'Open/reload main live in bot browser'},
            {'key': 'button_connect_tiktok', 'type': 'button', 'label': 'TikTok prüfen', 'button_text': 'TikTok Botbrowser prüfen', 'button_text_en': 'Check TikTok bot browser'},
            {'key': 'button_close_tiktok_browser', 'type': 'button', 'label': 'TikTok Browser', 'button_text': 'TikTok Botbrowser schließen', 'button_text_en': 'Close TikTok bot browser'},
        ])

        schema += tab('YouTube', [
            {'key': 'section_youtube', 'type': 'separator', 'label': 'YouTube Status', 'label_en': 'YouTube status'},
            {'key': 'youtube_connection_status', 'label': 'Status', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'read_youtube', 'label': 'YouTube lesen aus Haupttool', 'label_en': 'Read YouTube from main tool', 'type': 'bool', 'readonly': True},
            {'key': 'write_youtube', 'label': 'YouTube schreiben aus Haupttool', 'label_en': 'Write YouTube from main tool', 'type': 'bool', 'readonly': True},
            {'key': 'section_youtube_note', 'type': 'separator', 'label': 'botalot nutzt nur die zentralen Haupttool-Daten. Keine eigenen Anmeldedaten.', 'label_en': 'botalot only uses central main-tool data. No own credentials.'},
        ])

        schema += tab('Kick', [
            {'key': 'section_kick', 'type': 'separator', 'label': 'Kick Status', 'label_en': 'Kick status'},
            {'key': 'kick_connection_status', 'label': 'Status', 'placeholder': '❔ Noch nicht geprüft', 'placeholder_en': '❔ Not checked yet', 'readonly': True},
            {'key': 'read_kick', 'label': 'Kick lesen aus Haupttool', 'label_en': 'Read Kick from main tool', 'type': 'bool', 'readonly': True},
            {'key': 'write_kick', 'label': 'Kick schreiben aus Haupttool', 'label_en': 'Write Kick from main tool', 'type': 'bool', 'readonly': True},
            {'key': 'section_kick_note', 'type': 'separator', 'label': 'botalot nutzt nur die zentralen Haupttool-Daten. Keine eigenen Anmeldedaten.', 'label_en': 'botalot only uses central main-tool data. No own credentials.'},
        ])

        schema += tab('Moderation', [
            {'key': 'section_moderation', 'type': 'separator', 'label': 'Moderation', 'label_en': 'Moderation'},
            {'key': 'moderation_enabled', 'label': 'Moderation aktiv', 'label_en': 'Moderation enabled', 'type': 'bool', 'help': 'Prüft Chatnachrichten vor Bridge und AI auf gesperrte Wörter.', 'help_en': 'Checks chat messages for blocked words before bridge and AI.'},
            {'key': 'moderation_words', 'label': 'Gesperrte Wörter (Komma-getrennt)', 'label_en': 'Blocked words (comma separated)', 'type': 'multiline', 'help': 'Beispiel: wort1, wort2, phrase mit leerzeichen', 'help_en': 'Example: word1, word2, phrase with spaces'},
            {'key': 'moderation_ban_reason', 'label': 'Ban-Grund / Meldung', 'label_en': 'Ban reason / message', 'type': 'multiline', 'help': 'Platzhalter: (User), {user}, {platform}, {word}. Diese Meldung erscheint nur auf der Ursprungsplattform und im Desktopwindow.', 'help_en': 'Placeholders: (User), {user}, {platform}, {word}. This message is only sent to the source platform and the desktop window.'},
            {'key': 'moderation_mod_test_users', 'label': 'Mod/Test-User ohne Ban', 'label_en': 'Mod/test users without ban', 'type': 'multiline', 'help': 'Ein Name pro Zeile oder Komma-getrennt. Diese User lösen nur die Desktop-Testmeldung aus.', 'help_en': 'One name per line or comma separated. These users only trigger the desktop test message.'},
            {'key': 'moderation_mod_test_message', 'label': 'Mod-Testmeldung im Desktopwindow', 'label_en': 'Mod test message in desktop window', 'placeholder': '(User), zum Glück bist du Mod, du darfst das.', 'help': 'Wird nur im Desktopwindow angezeigt, kein Ban, keine Bridge.', 'help_en': 'Shown only in the desktop window, no ban, no bridge.'},
            {'key': 'section_moderation_unban_manual', 'type': 'separator', 'label': 'Manuell freigeben', 'label_en': 'Manual unban'},
            {'key': 'moderation_unban_platform', 'label': 'Plattform zum Freigeben', 'label_en': 'Platform to unban on', 'placeholder': 'twitch', 'help': 'Aktuell wichtig: twitch. Optional auch tiktok, falls später unterstützt.', 'help_en': 'Currently important: twitch. TikTok can be entered too if supported later.'},
            {'key': 'moderation_unban_user', 'label': 'Nutzer freigeben', 'label_en': 'User to unban', 'placeholder': 'Username ohne @'},
            {'key': 'button_moderation_unban_user', 'type': 'button', 'label': 'Freigeben', 'label_en': 'Unban', 'button_text': 'Nutzer freigeben', 'button_text_en': 'Unban user'},
            {'key': 'section_moderation_session_list', 'type': 'separator', 'label': 'Gesperrte Nutzer in dieser Session', 'label_en': 'Banned users in this session'},
            {'key': 'moderation_banned_users', 'label': 'Session-Liste', 'label_en': 'Session list', 'type': 'multiline', 'help': 'Nur Übersicht der in dieser Sitzung gesperrten User. Startet bei jedem Programmstart leer.', 'help_en': 'Read-only overview of users banned during this session. Clears on every app start.'},
            {'key': 'button_moderation_refresh_session_list', 'type': 'button', 'label': 'Session-Liste', 'label_en': 'Session list', 'button_text': 'Liste aktualisieren', 'button_text_en': 'Refresh list'},
        ])

        schema += tab('Bridge', [
            {'key': 'section_bridge', 'type': 'separator', 'label': 'Chat-Bridge / Plattform-Relay', 'label_en': 'Chat bridge / platform relay'},
            {'key': 'bridge_enabled', 'label': 'Chat-Bridge aktiv', 'label_en': 'Chat bridge enabled', 'type': 'bool', 'help': 'Spiegelt normale Chatnachrichten nur auf die jeweils andere Plattform. Twitch ↔ TikTok ↔ YouTube ↔ Kick funktioniert über die jeweiligen Chat-Plugins.', 'help_en': 'Mirrors normal chat messages only to the other platform. Twitch ↔ TikTok ↔ YouTube ↔ Kick works through the matching chat plugins.'},
            {'key': 'bridge_twitch_to_tiktok', 'label': 'Twitch → TikTok spiegeln', 'label_en': 'Mirror Twitch → TikTok', 'type': 'bool'},
            {'key': 'bridge_tiktok_to_twitch', 'label': 'TikTok → Twitch spiegeln', 'label_en': 'Mirror TikTok → Twitch', 'type': 'bool'},
            {'key': 'bridge_twitch_to_youtube', 'label': 'Twitch → YouTube spiegeln', 'label_en': 'Mirror Twitch → YouTube', 'type': 'bool'},
            {'key': 'bridge_youtube_to_twitch', 'label': 'YouTube → Twitch spiegeln', 'label_en': 'Mirror YouTube → Twitch', 'type': 'bool'},
            {'key': 'bridge_tiktok_to_youtube', 'label': 'TikTok → YouTube spiegeln', 'label_en': 'Mirror TikTok → YouTube', 'type': 'bool'},
            {'key': 'bridge_youtube_to_tiktok', 'label': 'YouTube → TikTok spiegeln', 'label_en': 'Mirror YouTube → TikTok', 'type': 'bool'},
            {'key': 'bridge_twitch_to_kick', 'label': 'Twitch → Kick spiegeln', 'label_en': 'Mirror Twitch → Kick', 'type': 'bool'},
            {'key': 'bridge_kick_to_twitch', 'label': 'Kick → Twitch spiegeln', 'label_en': 'Mirror Kick → Twitch', 'type': 'bool'},
            {'key': 'bridge_tiktok_to_kick', 'label': 'TikTok → Kick spiegeln', 'label_en': 'Mirror TikTok → Kick', 'type': 'bool'},
            {'key': 'bridge_kick_to_tiktok', 'label': 'Kick → TikTok spiegeln', 'label_en': 'Mirror Kick → TikTok', 'type': 'bool'},
            {'key': 'bridge_youtube_to_kick', 'label': 'YouTube → Kick spiegeln', 'label_en': 'Mirror YouTube → Kick', 'type': 'bool'},
            {'key': 'bridge_kick_to_youtube', 'label': 'Kick → YouTube spiegeln', 'label_en': 'Mirror Kick → YouTube', 'type': 'bool'},
            {'key': 'bridge_only_when_write_enabled', 'label': 'Nur spiegeln, wenn Zielplattform-Schreiben aktiv ist', 'label_en': 'Mirror only when target-platform writing is enabled', 'type': 'bool'},
            {'key': 'bridge_prefix_format', 'label': 'Bridge-Format', 'placeholder': '{platform}-Message from {user}: {text}', 'help': 'Platzhalter: {platform}, {user}, {text}. Beispiel: Twitch-Message from Fremdling: Hallo', 'help_en': 'Placeholders: {platform}, {user}, {text}.'},
            {'key': 'bridge_ignore_commands', 'label': 'Alt/ignoriert: Commands trotzdem spiegeln', 'label_en': 'Old/ignored: mirror commands anyway', 'type': 'bool'},
            {'key': 'bridge_show_in_desktop', 'label': 'Bridge-Nachrichten im Desktopwindow anzeigen', 'label_en': 'Show bridge messages in desktop window', 'type': 'bool'},
            {'key': 'section_ai_mirror', 'type': 'separator', 'label': 'AI-Antworten auf andere Plattform spiegeln', 'label_en': 'Mirror AI replies to the other platform'},
            {'key': 'ai_mirror_enabled', 'label': 'AI-Antworten zusätzlich spiegeln', 'label_en': 'Additionally mirror AI replies', 'type': 'bool', 'help': 'Wenn aktiv, kann die Botantwort zusätzlich auf die andere Plattform geschrieben werden, damit beide Chats den Kontext sehen.', 'help_en': 'When enabled, the bot reply can also be written to the other platform so both chats see the context.'},
            {'key': 'ai_mirror_twitch_to_tiktok', 'label': 'AI: Twitch → zusätzlich TikTok', 'label_en': 'AI: Twitch → also TikTok', 'type': 'bool'},
            {'key': 'ai_mirror_tiktok_to_twitch', 'label': 'AI: TikTok → zusätzlich Twitch', 'label_en': 'AI: TikTok → also Twitch', 'type': 'bool'},
            {'key': 'ai_mirror_twitch_to_youtube', 'label': 'AI: Twitch → zusätzlich YouTube', 'label_en': 'AI: Twitch → also YouTube', 'type': 'bool'},
            {'key': 'ai_mirror_youtube_to_twitch', 'label': 'AI: YouTube → zusätzlich Twitch', 'label_en': 'AI: YouTube → also Twitch', 'type': 'bool'},
            {'key': 'ai_mirror_tiktok_to_youtube', 'label': 'AI: TikTok → zusätzlich YouTube', 'label_en': 'AI: TikTok → also YouTube', 'type': 'bool'},
            {'key': 'ai_mirror_youtube_to_tiktok', 'label': 'AI: YouTube → zusätzlich TikTok', 'label_en': 'AI: YouTube → also TikTok', 'type': 'bool'},
            {'key': 'ai_mirror_twitch_to_kick', 'label': 'AI: Twitch → zusätzlich Kick', 'label_en': 'AI: Twitch → also Kick', 'type': 'bool'},
            {'key': 'ai_mirror_kick_to_twitch', 'label': 'AI: Kick → zusätzlich Twitch', 'label_en': 'AI: Kick → also Twitch', 'type': 'bool'},
            {'key': 'ai_mirror_tiktok_to_kick', 'label': 'AI: TikTok → zusätzlich Kick', 'label_en': 'AI: TikTok → also Kick', 'type': 'bool'},
            {'key': 'ai_mirror_kick_to_tiktok', 'label': 'AI: Kick → zusätzlich TikTok', 'label_en': 'AI: Kick → also TikTok', 'type': 'bool'},
            {'key': 'ai_mirror_youtube_to_kick', 'label': 'AI: YouTube → zusätzlich Kick', 'label_en': 'AI: YouTube → also Kick', 'type': 'bool'},
            {'key': 'ai_mirror_kick_to_youtube', 'label': 'AI: Kick → zusätzlich YouTube', 'label_en': 'AI: Kick → also YouTube', 'type': 'bool'},
            {'key': 'ai_mirror_only_when_write_enabled', 'label': 'Nur spiegeln, wenn Zielplattform-Schreiben aktiv ist', 'label_en': 'Mirror only when target-platform writing is enabled', 'type': 'bool'},
            {'key': 'ai_mirror_prefix_format', 'label': 'AI-Spiegel-Format', 'label_en': 'AI mirror format', 'placeholder': '{platform}-AI answer to {user}: {response}', 'help': 'Platzhalter: {platform}, {user}, {response}. Leer = gleiche Antwort ohne Zusatz.', 'help_en': 'Placeholders: {platform}, {user}, {response}. Empty = same reply without prefix.'},
            {'key': 'ai_mirror_show_in_desktop', 'label': 'Gespiegelte AI-Antwort im Desktopwindow anzeigen', 'label_en': 'Show mirrored AI reply in desktop window', 'type': 'bool'},
        ])

        schema += tab('AI', [
            {'key': 'section_ai', 'type': 'separator', 'label': 'AI / Prompt'},
            {'key': 'openai_model', 'label': 'OpenAI Modell', 'label_en': 'OpenAI model', 'placeholder': 'gpt-5-mini'},
            {'key': 'use_openai_hosted_prompt', 'label': 'OpenAI Hosted Prompt nutzen', 'label_en': 'Use OpenAI hosted prompt', 'type': 'bool', 'help': 'Wenn aktiv, nutzt botalot die Prompt-ID aus platform.openai.com statt nur das lokale Promptfeld.', 'help_en': 'When enabled, botalot uses the prompt ID from platform.openai.com instead of only the local prompt field.'},
            {'key': 'openai_prompt_id', 'label': 'OpenAI Prompt ID', 'placeholder': 'pmpt_...'},
            {'key': 'openai_prompt_version', 'label': 'OpenAI Prompt Version', 'label_en': 'OpenAI prompt version', 'placeholder': '2'},
            {'key': 'system_prompt', 'label': 'Lokaler Prompt / Fallback', 'label_en': 'Local prompt / fallback', 'type': 'multiline', 'help': 'Wird genutzt, wenn Hosted Prompt aus ist oder keine Prompt-ID gesetzt ist.', 'help_en': 'Used when hosted prompt is off or no prompt ID is set.'},
            {'key': 'button_update_default_prompt', 'type': 'button', 'label': 'Prompt', 'button_text': 'Neuen Standard-Prompt einsetzen', 'button_text_en': 'Insert new default prompt'},
            {'key': 'button_test_ai', 'type': 'button', 'label': 'AI-Test', 'button_text': 'AI Trigger-Test'},
            {'key': 'section_triggers', 'type': 'separator', 'label': 'Trigger', 'label_en': 'Triggers'},
            {'key': 'trigger_botis3mpty', 'label': 'Auf botis3mpty reagieren', 'label_en': 'React to botis3mpty', 'type': 'bool'},
            {'key': 'trigger_at_bot', 'label': 'Auf @bot / @botis3mpty reagieren', 'label_en': 'React to @bot / @botis3mpty', 'type': 'bool'},
            {'key': 'trigger_ursula', 'label': 'Auf Ursula-Varianten reagieren', 'label_en': 'React to Ursula variants', 'type': 'bool'},
            {'key': 'only_answer_questions_for_botis3mpty', 'label': 'botis3mpty nur bei Fragen beantworten', 'label_en': 'Only answer botis3mpty on questions', 'type': 'bool'},
            {'key': 'trigger_file_hint', 'label': 'Trigger-Datei', 'label_en': 'Trigger file', 'placeholder': str(TRIGGER_FILE)},
            {'key': 'button_open_trigger_file', 'type': 'button', 'label': 'Trigger-Datei öffnen', 'label_en': 'Open trigger file', 'button_text': 'Ursula-Wortliste öffnen', 'button_text_en': 'Open Ursula word list'},
            {'key': 'button_reload_triggers', 'type': 'button', 'label': 'Trigger neu laden', 'label_en': 'Reload triggers', 'button_text': 'Trigger neu laden', 'button_text_en': 'Reload triggers'},
            {'key': 'section_write', 'type': 'separator', 'label': 'Antwort-Ausgabe', 'label_en': 'Reply output'},
            {'key': 'reply_prefix_user', 'label': 'User erwähnen (@Name)', 'label_en': 'Mention user (@name)', 'type': 'bool'},
            {'key': 'show_bot_replies_in_desktop', 'label': 'Bot-Antworten im Desktopwindow anzeigen', 'label_en': 'Show bot replies in desktop window', 'type': 'bool'},
        ])

        schema += tab('Allgemein', [
            {'key': 'section_general', 'type': 'separator', 'label': 'Allgemein', 'label_en': 'General'},
            {'key': 'log_every_trigger', 'label': 'Trigger/Antworten loggen', 'label_en': 'Log triggers/replies', 'type': 'bool'},
            {'key': 'context_messages', 'label': 'Kontext-Nachrichten', 'label_en': 'Context messages', 'type': 'number', 'min': 1, 'max': 30},
            {'key': 'cooldown_seconds', 'label': 'Globaler Antwort-Cooldown Sekunden', 'label_en': 'Global reply cooldown seconds', 'type': 'float', 'min': 0, 'max': 999, 'decimals': 1},
            {'key': 'platform_cooldown_seconds', 'label': 'Plattform-Cooldown Sekunden', 'label_en': 'Platform cooldown seconds', 'type': 'float', 'min': 0, 'max': 999, 'decimals': 1},
            {'key': 'max_response_chars', 'label': 'Max. Antwortlänge Zeichen', 'label_en': 'Max. reply length characters', 'type': 'number', 'min': 40, 'max': 500},
            {'key': 'excluded_users', 'label': 'Ignorierte User/Login-Namen', 'label_en': 'Ignored users/login names', 'type': 'multiline', 'help': 'Ein Name pro Zeile. Gilt nur fuer AI-Antworten, nie fuer die Bridge.', 'help_en': 'One name per line. Applies only to AI replies, never to the bridge.'},
        ], en='General')

        return schema

    def default_settings(self) -> dict[str, Any]:
        self._ensure_files()
        try:
            prompt = PROMPT_FILE.read_text(encoding='utf-8').strip() or DEFAULT_PROMPT
        except Exception:
            prompt = DEFAULT_PROMPT
        return {
            'enabled': True,
            'log_every_trigger': True,
            'context_messages': 10,
            'cooldown_seconds': 8.0,
            'platform_cooldown_seconds': 4.0,
            'max_response_chars': 200,
            'excluded_users': 'streamelements\nnightbot\nstreamlabs',
            'openai_connection_status': '❔ Noch nicht verbunden',
            'twitch_connection_status': '❔ Noch nicht verbunden',
            'twitch_chat_live_status': '❔ Noch nicht geprüft',
            'tiktok_connection_status': '❔ Noch nicht verbunden',
            'youtube_connection_status': '🟡 optional / keine Daten nötig',
            'kick_connection_status': '🟡 optional / keine Daten nötig',
            'obs_connection_status': '🟡 optional / wird aus Haupttool gelesen',
            'meld_connection_status': '🟡 optional / wird aus Haupttool gelesen',
            'platforms_source_status': '❔ Noch nicht gelesen',
            'openai_api_key': '',
            'openai_model': 'gpt-5-mini',
            'use_openai_hosted_prompt': False,
            'openai_prompt_id': '',
            'openai_prompt_version': '2',
            'system_prompt': prompt,
            'trigger_botis3mpty': True,
            'trigger_at_bot': True,
            'trigger_ursula': True,
            'only_answer_questions_for_botis3mpty': False,
            'trigger_file_hint': str(TRIGGER_FILE),
            'read_tiktok': True,
            'read_twitch': True,
            'read_youtube': True,
            'read_kick': True,
            'bridge_enabled': False,
            'bridge_twitch_to_tiktok': False,
            'bridge_tiktok_to_twitch': False,
            'bridge_twitch_to_youtube': False,
            'bridge_youtube_to_twitch': False,
            'bridge_tiktok_to_youtube': False,
            'bridge_youtube_to_tiktok': False,
            'bridge_twitch_to_kick': False,
            'bridge_kick_to_twitch': False,
            'bridge_tiktok_to_kick': False,
            'bridge_kick_to_tiktok': False,
            'bridge_youtube_to_kick': False,
            'bridge_kick_to_youtube': False,
            'bridge_only_when_write_enabled': True,
            'bridge_prefix_format': '{platform}-Message from {user}: {text}',
            'bridge_ignore_commands': False,
            'bridge_show_in_desktop': False,
            'moderation_enabled': False,
            'moderation_words': '',
            'moderation_ban_reason': '(User) du wurdest wegen scheißigkeit gebannt.',
            'moderation_mod_test_users': '',
            'moderation_mod_test_message': '(User), zum Glück bist du Mod, du darfst das.',
            'moderation_unban_platform': 'twitch',
            'moderation_unban_user': '',
            'moderation_banned_users': '',
            'ai_mirror_enabled': True,
            'ai_mirror_twitch_to_tiktok': True,
            'ai_mirror_tiktok_to_twitch': True,
            'ai_mirror_twitch_to_youtube': False,
            'ai_mirror_youtube_to_twitch': False,
            'ai_mirror_tiktok_to_youtube': False,
            'ai_mirror_youtube_to_tiktok': False,
            'ai_mirror_twitch_to_kick': False,
            'ai_mirror_kick_to_twitch': False,
            'ai_mirror_tiktok_to_kick': False,
            'ai_mirror_kick_to_tiktok': False,
            'ai_mirror_youtube_to_kick': False,
            'ai_mirror_kick_to_youtube': False,
            'ai_mirror_only_when_write_enabled': True,
            'ai_mirror_prefix_format': '{platform}-AI answer to {user}: {response}',
            'ai_mirror_show_in_desktop': False,
            'write_tiktok': False,
            'write_twitch': True,
            'write_youtube': False,
            'write_kick': False,
            'reply_prefix_user': True,
            'show_bot_replies_in_desktop': True,
            'twitch_channel': '',
            'twitch_client_id': '',
            'twitch_client_secret': '',
            'twitch_redirect_port': '17564',
            'twitch_redirect_url': 'http://localhost:17564/callback/',
            'twitch_bot_username': '',
            'twitch_oauth_token': '',
            'prefer_existing_twitch_socket': False,
            'tiktok_second_account': '',
            'tiktok_main_account': '',
            'tiktok_resolved_live_url': '',
            'tiktok_browser_path': '',
            'tiktok_profile_dir': '',
            'tiktok_remote_debug_port': 9229,
            'tiktok_clipboard_focus_send': False,
            'tiktok_send_delay_ms': 150,
            'autoconnect': False,
        }


    def _host_platform_settings(self, platform: str | None = None) -> dict[str, Any]:
        host = self._host
        if host is None:
            return {}
        for name in ('platform_settings', 'get_platform_settings'):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    data = fn(platform) if platform is not None else fn()
                except TypeError:
                    try:
                        data = fn()
                    except Exception:
                        data = {}
                except Exception:
                    data = {}
                if isinstance(data, dict):
                    return dict(data)
        return {}

    def _platform_bool(self, data: dict[str, Any], *keys: str, default: bool = False) -> bool:
        for key in keys:
            if key in data:
                return as_bool(data.get(key), default)
        return default

    def _platform_str(self, data: dict[str, Any], *keys: str, default: str = '') -> str:
        for key in keys:
            value = data.get(key)
            if value is not None and str(value).strip() != '':
                return str(value).strip()
        return default

    def _platform_has_kick_send_access(self, settings: dict[str, Any] | None = None) -> bool:
        """Return True when Kick can realistically be written to.

        Kick writes are owned by the main tool. Older saved botalot settings may
        still have write_kick=False even after Kick OAuth succeeded, which made
        Twitch/TikTok/YouTube -> Kick silently skip. Treat a central bot token
        or an active kick_chat plugin as write-capable, while still keeping the
        normal UI checkbox in sync when the main tool exposes write_enabled.
        """
        local = settings if isinstance(settings, dict) else self._settings
        if isinstance(local, dict) and as_bool(local.get('write_kick'), False):
            return True
        pdata = self._host_platform_settings('kick')
        if isinstance(pdata, dict):
            if self._platform_bool(pdata, 'write_enabled', 'write', default=False):
                return True
            if self._platform_str(pdata, 'access_token', 'bot_access_token'):
                return True
        if isinstance(local, dict) and str(local.get('kick_access_token') or '').strip():
            return True
        return self._host_plugin_is_active('kick_chat')

    def _auto_bridge_to_kick_enabled(self, settings: dict[str, Any]) -> bool:
        """Allow old saved botalot settings to start sending TO Kick.

        The Kick checkboxes did not exist in older configs. When Kick is connected in
        the main tool, those old false/default values must not silently block
        Twitch/TikTok/YouTube -> Kick.
        """
        if not as_bool(settings.get('bridge_enabled'), False):
            return False
        return self._platform_has_kick_send_access(settings)

    def _auto_bridge_from_kick_enabled(self, settings: dict[str, Any], target: str) -> bool:
        """Allow Kick input to mirror to already writable targets with old configs."""
        if not as_bool(settings.get('bridge_enabled'), False):
            return False
        target = str(target or '').strip().lower()
        if target == 'twitch':
            return as_bool(settings.get('write_twitch'), False)
        if target == 'tiktok':
            return as_bool(settings.get('write_tiktok'), False)
        if target == 'youtube':
            return as_bool(settings.get('write_youtube'), False)
        return False

    def _clean_account_name(self, value: Any) -> str:
        raw = str(value or '').strip()
        if raw.startswith('http://') or raw.startswith('https://'):
            try:
                low = raw.lower()
                marker = 'tiktok.com/@'
                idx = low.find(marker)
                if idx >= 0:
                    tail = raw[idx + len(marker):].split('?', 1)[0].split('#', 1)[0]
                    return tail.strip('/').split('/', 1)[0].lstrip('@').strip()
            except Exception:
                pass
        return raw.lstrip('@').strip().strip('/')

    def _port_from_redirect_url(self, url: str, default: int = 17564) -> int:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(str(url or '').strip())
            if parsed.port:
                return int(parsed.port)
        except Exception:
            pass
        return int(default)

    def _host_plugin_object(self, *plugin_ids: str) -> Any:
        host = self._host
        if host is None:
            return None
        for plugin_id in plugin_ids:
            try:
                getter = getattr(host, 'get_plugin', None)
                plugin = getter(plugin_id) if callable(getter) else None
            except Exception:
                plugin = None
            if plugin is None:
                try:
                    plugins = getattr(host, 'plugins', {})
                    plugin = plugins.get(plugin_id) if isinstance(plugins, dict) else None
                except Exception:
                    plugin = None
            if plugin is not None:
                return plugin
        return None

    def _host_plugin_is_active(self, *plugin_ids: str) -> bool:
        plugin = self._host_plugin_object(*plugin_ids)
        if plugin is None:
            return False

        # WICHTIG: Das Haupttool lädt auch deaktivierte Plugins als Objekt.
        # Viele Plugins haben trotzdem ein allgemeines enabled=True im Objekt.
        # Deshalb ist _host der sichere Unterschied: nur gestartete/aktive
        # Plugins bekommen beim start(settings, host) einen Host gesetzt.
        try:
            if getattr(plugin, '_host', None) is None:
                return False
        except Exception:
            return False

        for attr in ('_enabled', 'enabled', '_running', 'running'):
            try:
                value = getattr(plugin, attr)
            except Exception:
                continue
            if isinstance(value, bool):
                return value
            if callable(value):
                try:
                    return bool(value())
                except Exception:
                    pass
        return True

    def _host_plugin_is_connected(self, *plugin_ids: str) -> bool:
        plugin = self._host_plugin_object(*plugin_ids)
        if plugin is None or not self._host_plugin_is_active(*plugin_ids):
            return False
        for attr in ('is_connected', 'connected', '_connected', '_is_connected'):
            try:
                value = getattr(plugin, attr)
            except Exception:
                continue
            if isinstance(value, bool):
                return value
            if callable(value):
                try:
                    return bool(value())
                except Exception:
                    pass
        return False

    def _platform_plugin_ids(self, key: str) -> tuple[str, ...]:
        return {
            'twitch': ('twitch_chat',),
            'tiktok': ('tiktok_live',),
            'youtube': ('youtube_chat', 'youtube_live'),
            'kick': ('kick_chat',),
            'obs': ('obs_control',),
            'meld': ('meld_control',),
        }.get(str(key or '').lower(), ())

    def _platform_status_text(self, platform: str) -> str:
        pdata = self._host_platform_settings(platform)
        if isinstance(pdata, dict):
            return str(pdata.get('connection_status') or '').strip()
        return ''

    def _platform_status_state(self, platform: str) -> str:
        """Return connected/active/inactive/error from the main-tool status text.

        The main tool already knows whether a platform/plugin is really active.
        botalot must not turn a platform green just because default platform
        credentials/settings exist.
        """
        text = self._platform_status_text(platform)
        low = text.lower()
        if text.startswith('✅') or 'connected' in low or 'verbunden' in low:
            return 'connected'
        if text.startswith('🟡') or 'connecting' in low or 'watching' in low or 'verbindet' in low or 'aktiv' in low:
            return 'active'
        if text.startswith('❌') or 'error' in low or 'fehler' in low:
            return 'error'
        if text.startswith('⚪') or 'disconnect' in low or 'idle' in low or 'disabled' in low or 'inaktiv' in low:
            return 'inactive'
        return ''

    def _format_optional_platform_status(self, platform: str, label: str | None = None) -> str:
        label = label or platform
        plugin_ids = self._platform_plugin_ids(platform)
        active = self._host_plugin_is_active(*plugin_ids)

        # Wichtig: YouTube/Kick/OBS/Meld dürfen niemals grün werden,
        # nur weil im Haupttool alte Plattformdaten oder ein alter Status stehen.
        # Grün gibt es hier nur, wenn das passende Plugin wirklich aktiv ist.
        if not active:
            return '⚪ inaktiv'

        if self._host_plugin_is_connected(*plugin_ids):
            return '✅ verbunden'

        state = self._platform_status_state(platform)
        raw = self._platform_status_text(platform)
        if state == 'connected':
            return '✅ verbunden'
        if state == 'active':
            return raw if raw.startswith('🟡') else '🟡 aktiv, aber nicht verbunden'
        if state == 'error':
            return raw if raw else '❌ Fehler'
        return '🟡 aktiv, aber nicht verbunden'

    def _apply_platform_settings(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Merge central Plattformen/Platforms data into botalot runtime settings.

        Missing platform data is intentionally not an error. botalot can run with
        only the platforms the user actually configured in the main tool.
        """
        target = settings if isinstance(settings, dict) else self._settings
        if not isinstance(target, dict):
            target = {}
        platforms = self._host_platform_settings(None)
        if not isinstance(platforms, dict) or not platforms:
            target['platforms_source_status'] = '❌ Keine zentralen Plattformdaten vom Haupttool gefunden.'
            for key in ('openai', 'twitch', 'tiktok', 'youtube', 'kick', 'obs', 'meld'):
                target[f'{key}_connection_status'] = '⚪ inaktiv'
            target['twitch_chat_live_status'] = '⚪ inaktiv'
            return target

        target['platforms_source_status'] = '✅ Zentrale Plattformdaten aus dem Haupttool aktiv'
        for key in ('openai', 'twitch', 'tiktok', 'youtube', 'kick', 'obs', 'meld'):
            target[f'{key}_connection_status'] = '⚪ inaktiv'
        target['twitch_chat_live_status'] = '⚪ inaktiv'

        tw = platforms.get('twitch') if isinstance(platforms.get('twitch'), dict) else {}
        if tw:
            main = self._clean_account_name(self._platform_str(tw, 'main_account', 'channel', 'twitch_channel'))
            bot = self._clean_account_name(self._platform_str(tw, 'bot_account', 'bot_username', 'username'))
            redirect_url = self._platform_str(tw, 'redirect_url', default=str(target.get('twitch_redirect_url') or 'http://localhost:17564/callback/'))
            target.update({
                'read_twitch': self._platform_bool(tw, 'read_enabled', 'read', default=True),
                'write_twitch': self._platform_bool(tw, 'write_enabled', 'write', default=False),
                'twitch_channel': main,
                'twitch_bot_username': bot or main,
                'twitch_client_id': self._platform_str(tw, 'client_id'),
                'twitch_client_secret': self._platform_str(tw, 'client_secret'),
                'twitch_redirect_url': redirect_url,
                'twitch_redirect_port': int(tw.get('redirect_port') or self._port_from_redirect_url(redirect_url, 17564)),
                'twitch_scopes': self._platform_str(tw, 'scopes', default='chat:read chat:edit moderator:manage:banned_users moderator:manage:chat_messages channel:manage:broadcast'),
                'twitch_oauth_token': self._platform_str(tw, 'access_token'),
                'twitch_refresh_token': self._platform_str(tw, 'refresh_token'),
                'twitch_oauth_login': self._platform_str(tw, 'oauth_login', 'login'),
                'twitch_oauth_user_id': self._platform_str(tw, 'oauth_user_id', 'user_id'),
                'twitch_autoconnect': self._platform_bool(tw, 'autoconnect', default=False),
                'twitch_mod_enabled': self._platform_bool(tw, 'moderation_rights_enabled', 'mod_enabled', default=True),
            })
            if target.get('write_twitch') or target.get('read_twitch'):
                if target.get('twitch_oauth_token'):
                    target['twitch_connection_status'] = '🟡 Twitch-Daten aus Haupttool geladen'
                else:
                    target['twitch_connection_status'] = '❌ Twitch aktiv, aber Haupttool-OAuth fehlt'
                target['twitch_chat_live_status'] = '🟡 Twitch-Chat hängt am Haupttool/twitch_chat' if target.get('read_twitch') else '⚪ inaktiv'
            else:
                target['twitch_connection_status'] = '⚪ inaktiv'
                target['twitch_chat_live_status'] = '⚪ inaktiv'

        tt = platforms.get('tiktok') if isinstance(platforms.get('tiktok'), dict) else {}
        if tt:
            live_url = self._platform_str(tt, 'resolved_live_url', 'live_url')
            # MAIN is the live channel. BOT is only the browser login/profile user.
            # Trust the live URL first, because it is the unambiguous target for the bridge.
            live_main = self._clean_account_name(live_url) if live_url else ''
            main = live_main or self._clean_account_name(self._platform_str(tt, 'main_account', 'unique_id', 'channel'))
            bot = self._clean_account_name(self._platform_str(tt, 'bot_account', 'second_account', 'bot_username'))
            # Safety: if a user accidentally swapped main/bot in the main tool but the
            # live URL points to the real main account, keep the live URL as MAIN.
            if live_main:
                main = live_main
            if bot and main and bot.lower() == main.lower():
                # Never use the live account as the bot name. Better leave bot blank than
                # showing/sending as the wrong account.
                bot = ''
            if not live_url and main:
                live_url = f'https://www.tiktok.com/@{main}/live'
            write_enabled = self._platform_bool(tt, 'write_enabled', 'write', default=False)
            target.update({
                'read_tiktok': self._platform_bool(tt, 'read_enabled', 'read', default=True),
                'write_tiktok': write_enabled,
                'tiktok_main_account': main,
                'tiktok_second_account': bot,
                'tiktok_resolved_live_url': live_url,
                'tiktok_browser_path': self._platform_str(tt, 'browser_path'),
                'tiktok_profile_dir': self._platform_str(tt, 'profile_dir'),
                'tiktok_remote_debug_port': int(tt.get('remote_debug_port') or 9229),
                'tiktok_send_delay_ms': int(tt.get('send_delay_ms') or 150),
                # botalot writes TikTok through its dedicated browser writer.
                # The visible decision is now only the central write_enabled checkbox.
                'tiktok_clipboard_focus_send': write_enabled,
                # TikTok-Schreiben läuft weiter über den Botaccount-Browser.
                # Autostart kommt aus dem Haupttool ODER aus dem botalot-Autoconnect.
                # Ein explizit false gesetztes Plattform-Autoconnect darf den globalen
                # botalot-Autoconnect nicht aushebeln.
                'tiktok_autoconnect': (
                    self._platform_bool(tt, 'autoconnect', default=False)
                    or as_bool(target.get('tiktok_autoconnect'), False)
                    or as_bool(target.get('autoconnect'), False)
                ),
            })
            if target.get('write_tiktok') or target.get('read_tiktok'):
                target['tiktok_connection_status'] = '🟡 TikTok-Daten aus Haupttool geladen' if (live_url or bot or main) else '❌ TikTok aktiv, aber Haupttool-Daten fehlen'
            else:
                target['tiktok_connection_status'] = '⚪ inaktiv'

        oa = platforms.get('openai') if isinstance(platforms.get('openai'), dict) else {}
        if oa:
            target.update({
                'openai_api_key': self._platform_str(oa, 'api_key'),
                'openai_autoconnect': self._platform_bool(oa, 'autoconnect', default=False),
                'openai_enabled': self._platform_bool(oa, 'enabled', default=True),
            })
            if not target.get('openai_enabled'):
                target['openai_connection_status'] = '⚪ inaktiv'
            elif target.get('openai_api_key'):
                target['openai_connection_status'] = '✅ OpenAI API Key aus Haupttool geladen'
            else:
                target['openai_connection_status'] = '❌ OpenAI aktiv, aber API Key fehlt im Haupttool'

        for key in ('youtube', 'kick'):
            pdata = platforms.get(key) if isinstance(platforms.get(key), dict) else {}
            if not pdata:
                continue
            target[f'read_{key}'] = self._platform_bool(pdata, 'read_enabled', 'read', default=False)
            if key == 'kick':
                target[f'write_{key}'] = (
                    self._platform_bool(pdata, 'write_enabled', 'write', default=False)
                    or bool(self._platform_str(pdata, 'access_token', 'bot_access_token'))
                )
            else:
                target[f'write_{key}'] = (
                    self._platform_bool(pdata, 'write_enabled', 'write', default=False)
                    or bool(self._platform_str(pdata, 'access_token', 'bot_access_token', 'refresh_token'))
                )
            if key == 'youtube':
                target['youtube_main_account'] = self._clean_account_name(self._platform_str(pdata, 'main_account', 'channel', 'live_channel'))
                target['youtube_bot_account'] = self._clean_account_name(self._platform_str(pdata, 'bot_account', 'bot_username', 'username'))
                target['youtube_client_id'] = self._platform_str(pdata, 'client_id')
                target['youtube_client_secret'] = self._platform_str(pdata, 'client_secret')
                target['youtube_access_token'] = self._platform_str(pdata, 'access_token')
                target['youtube_refresh_token'] = self._platform_str(pdata, 'refresh_token')
                target['youtube_main_access_token'] = self._platform_str(pdata, 'main_access_token')
                target['youtube_main_refresh_token'] = self._platform_str(pdata, 'main_refresh_token')
                target['youtube_live_chat_id'] = self._platform_str(pdata, 'live_chat_id')
                target['youtube_autoconnect'] = self._platform_bool(pdata, 'autoconnect', default=False)
            elif key == 'kick':
                target['kick_channel'] = self._clean_account_name(self._platform_str(pdata, 'channel', 'main_account', 'live_channel'))
                target['kick_main_account'] = self._clean_account_name(self._platform_str(pdata, 'main_account', 'channel', 'live_channel'))
                target['kick_bot_account'] = self._clean_account_name(self._platform_str(pdata, 'bot_account', 'bot_username', 'username'))
                target['kick_client_id'] = self._platform_str(pdata, 'client_id')
                target['kick_client_secret'] = self._platform_str(pdata, 'client_secret')
                target['kick_access_token'] = self._platform_str(pdata, 'access_token')
                target['kick_refresh_token'] = self._platform_str(pdata, 'refresh_token')
                target['kick_main_access_token'] = self._platform_str(pdata, 'main_access_token')
                target['kick_main_refresh_token'] = self._platform_str(pdata, 'main_refresh_token')
                target['kick_autoconnect'] = self._platform_bool(pdata, 'autoconnect', default=False)
            target[f'{key}_connection_status'] = self._format_optional_platform_status(key)

        for key in ('obs', 'meld'):
            pdata = platforms.get(key) if isinstance(platforms.get(key), dict) else {}
            if not pdata:
                continue
            target[f'{key}_enabled'] = self._platform_bool(pdata, 'enabled', default=True)
            target[f'{key}_autoconnect'] = self._platform_bool(pdata, 'autoconnect', default=False)
            target[f'{key}_host'] = self._platform_str(pdata, 'host', default='127.0.0.1')
            target[f'{key}_port'] = int(pdata.get('port') or (4455 if key == 'obs' else 13376))
            if 'password' in pdata:
                target[f'{key}_password'] = self._platform_str(pdata, 'password')
            if not target.get(f'{key}_enabled'):
                target[f'{key}_connection_status'] = '⚪ inaktiv'
            else:
                target[f'{key}_connection_status'] = self._format_optional_platform_status(key, 'Meld Studio' if key == 'meld' else 'OBS')

        if any(as_bool((platforms.get(k) or {}).get('autoconnect'), False) for k in ('twitch', 'openai', 'tiktok', 'youtube', 'kick') if isinstance(platforms.get(k), dict)):
            target['autoconnect'] = True
        return target

    def _settings_with_platforms(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        base = dict(settings or self._settings or {})
        return self._apply_platform_settings(base)

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._install_host_emit_filter(host)
        # Keep the host settings dict by reference so runtime-only fields like the
        # moderation session list can show up when the settings UI is reopened.
        self._settings = settings if isinstance(settings, dict) else dict(settings or {})
        self._apply_platform_settings(self._settings)
        # Bot-Antworten sollen wieder genau einmal im Desktopwindow erscheinen.
        # Alte gespeicherte Settings aus Versionen, in denen das aus war, werden hier
        # bewusst auf AN migriert; die Echo-Sperre verhindert weiterhin Doppelanzeigen.
        self._publish_setting_value('show_bot_replies_in_desktop', True)
        self._moderation_bans = []
        self._last_tiktok_is_live = None
        self._tiktok_reloaded_for_current_live = False
        self._publish_setting_value('moderation_banned_users', '')
        self._refresh_moderation_banned_users_field()
        self._enabled = as_bool(self._settings.get('enabled'), True)
        self._context.resize(to_int(self._settings.get('context_messages'), 10, 1, 30))
        count = self._triggers.reload()
        detail = 'aktiv - liest eingehende Chats' if self._enabled else 'deaktiviert'
        host.set_status(self.plugin_id, PluginStatus('connected' if self._enabled else 'disabled', f'{PLUGIN_NAME}: {detail}'))
        host.log(self.plugin_id, f'{PLUGIN_NAME} gestartet. Trigger geladen: {count}')
        self._refresh_runtime_status_fields(update_plugin_status=False, strict_receive=False)
        if (
            as_bool(self._settings.get('autoconnect'), False)
            or as_bool(self._settings.get('openai_autoconnect'), False)
            or as_bool(self._settings.get('twitch_autoconnect'), False)
            or as_bool(self._settings.get('tiktok_autoconnect'), False)
            or as_bool(self._settings.get('youtube_autoconnect'), False)
            or as_bool(self._settings.get('kick_autoconnect'), False)
        ):
            threading.Thread(target=self._autoconnect_on_start, args=(dict(self._settings),), daemon=True, name='botalot-autoconnect').start()


    def _autoconnect_on_start(self, settings: dict[str, Any]) -> None:
        """Best-effort startup connect without blocking the plugin UI.

        This method was referenced by start() in v0.30 but missing, which caused
        the AttributeError on startup. Keep it defensive: every connection part
        may fail without killing the plugin.
        """
        try:
            # Give godisalotachat a tiny moment to finish loading plugins/UI.
            time.sleep(0.8)
            settings = self._settings_with_platforms(settings)
            self._log('Autoconnect gestartet.')

            if as_bool(settings.get('openai_autoconnect'), as_bool(settings.get('autoconnect'), False)) and str(settings.get('openai_api_key') or '').strip():
                try:
                    ok, msg = self._ai.test_connection(settings)
                    self._log(('OpenAI Autoconnect OK: ' if ok else 'OpenAI Autoconnect Fehler: ') + msg)
                except Exception as exc:
                    self._log(f'OpenAI Autoconnect Fehler: {exc}')

            if as_bool(settings.get('twitch_autoconnect'), as_bool(settings.get('autoconnect'), False)) and as_bool(settings.get('write_twitch'), False):
                try:
                    ok, msg = self._outputs.twitch.check_auth(settings)
                    self._log(('Twitch Autoconnect OK: ' if ok else 'Twitch Autoconnect Hinweis: ') + msg)
                except Exception as exc:
                    self._log(f'Twitch Autoconnect Fehler: {exc}')

            if (
                (as_bool(settings.get('autoconnect'), False) or as_bool(settings.get('tiktok_autoconnect'), False))
                and as_bool(settings.get('write_tiktok'), False)
            ):
                try:
                    logged_hint = False
                    try:
                        logged_hint = bool(self._outputs.tiktok.profile_looks_logged_in(settings))
                    except Exception:
                        logged_hint = False
                    # Alter Stand, aber mit Haupttool-Daten:
                    # Botprofil eingeloggt -> Main-Live im Botbrowser minimiert öffnen.
                    # Botprofil nicht eingeloggt -> Loginseite sichtbar öffnen.
                    mode = 'live' if logged_hint else 'bot'
                    started = self._outputs.tiktok.open_browser(settings, mode=mode, minimized=logged_hint)
                    if not started:
                        msg = 'TikTok-Botbrowser konnte nicht gestartet werden.'
                        self._set_runtime_field('tiktok_connection_status', '❌ ' + msg)
                        self._log('TikTok Autoconnect Fehler: ' + msg)
                    else:
                        ready, wait_msg = self._outputs.tiktok.wait_for_debugger(settings, timeout_seconds=8.0)
                        if ready:
                            ok, msg = self._outputs.tiktok.check_login_hint(settings)
                        else:
                            ok, msg = False, wait_msg
                        self._set_runtime_field('tiktok_connection_status', ('✅ ' if ok else '❌ ') + msg)
                        self._log(('TikTok Autoconnect OK: ' if ok else 'TikTok Autoconnect Hinweis: ') + msg)
                except Exception as exc:
                    self._log(f'TikTok Autoconnect Fehler: {exc}')

            self._log('Autoconnect fertig.')
        except Exception as exc:
            self._log(f'Autoconnect abgebrochen: {exc}')

    def stop(self) -> None:
        self._enabled = False
        try:
            ok, msg = self._outputs.tiktok.close_browser(dict(self._settings or {}))
            self._log(msg)
        except Exception as exc:
            self._log(f'TikTok Zusatzbrowser konnte beim Beenden nicht geschlossen werden: {exc}')
        if self._host is not None:
            self._restore_host_emit_filter()
            self._host.set_status(self.plugin_id, PluginStatus('stopped', 'Stopped'))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        settings = self._settings_with_platforms(settings)
        if not as_bool(settings.get('enabled'), True):
            return True, f'{PLUGIN_NAME} ist deaktiviert.'
        problems = []
        notes = []
        if not str(settings.get('openai_api_key') or '').strip():
            notes.append('OpenAI API Key fehlt: AI bleibt aus, Bridge/Moderation können weiter laufen')
        if as_bool(settings.get('write_twitch'), False):
            has_existing = as_bool(settings.get('prefer_existing_twitch_socket'), False)
            ok_tw, _msg_tw = self._outputs.twitch.check_status(settings)
            if not ok_tw and not has_existing:
                problems.append('Twitch Write aktiv, aber Twitch OAuth ist nicht verbunden')
        if as_bool(settings.get('write_tiktok'), False):
            if not as_bool(settings.get('tiktok_clipboard_focus_send'), False):
                problems.append('TikTok Write aktiv, aber Zweitaccount-Browser-Senden aus')
            ok, hint = self._outputs.tiktok.check_login_hint(settings)
            if not ok:
                problems.append(hint)
        if problems:
            return False, '; '.join(problems)
        suffix = (' Hinweise: ' + '; '.join(notes)) if notes else ''
        return True, f'{PLUGIN_NAME} bereit. Plattformdaten kommen aus dem Haupttool.{suffix}'

    def _set_status_line(self, state: str, message: str) -> None:
        self._log(message)
        if self._host is not None:
            try:
                self._host.set_status(self.plugin_id, PluginStatus(state, message))
            except Exception:
                pass

    def _format_ts(self, ts: float | None = None) -> str:
        try:
            return time.strftime('%H:%M:%S', time.localtime(ts or time.time()))
        except Exception:
            return '--:--:--'

    def _set_runtime_field(self, key: str, value: Any, parent: Any = None) -> None:
        self._publish_setting_value(key, value)
        if parent is not None:
            self._set_dialog_field(parent, key, str(value))

    def _refresh_runtime_status_fields(self, parent: Any = None, *, update_plugin_status: bool = True, strict_receive: bool = True) -> bool:
        """Update overview fields from the central main-tool platform state.

        botalot does not own Twitch/OpenAI/TikTok credentials anymore. It only
        reads the main tool platform settings and checks/sends through host data.
        """
        settings = self._dialog_settings(parent)

        # OpenAI
        if not as_bool(settings.get('openai_enabled'), True):
            self._set_runtime_field('openai_connection_status', '⚪ inaktiv', parent)
            ok_ai = True
        elif str(settings.get('openai_api_key') or '').strip():
            self._set_runtime_field('openai_connection_status', '✅ API Key aus Haupttool geladen', parent)
            ok_ai = True
        else:
            self._set_runtime_field('openai_connection_status', '❌ aktiv, aber API Key fehlt im Haupttool', parent)
            ok_ai = False

        # Twitch write/mod path
        if as_bool(settings.get('write_twitch'), False):
            ok_write, msg_write = self._outputs.twitch.check_auth(settings)
            self._set_runtime_field('twitch_connection_status', ('✅ ' if ok_write else '❌ ') + msg_write, parent)
        elif as_bool(settings.get('read_twitch'), False):
            ok_write = True
            self._set_runtime_field('twitch_connection_status', '⚪ Schreiben inaktiv, Lesen aktiv', parent)
        else:
            ok_write = True
            self._set_runtime_field('twitch_connection_status', '⚪ inaktiv', parent)

        # Twitch read path is provided by twitch_chat / central host message stream.
        if as_bool(settings.get('read_twitch'), False):
            ok_read, msg_read = self._outputs.twitch.check_reader_status(settings)
            if ok_read:
                read_prefix = '✅ '
                read_status = 'OK'
            elif strict_receive:
                read_prefix = '❌ '
                read_status = 'FEHLER'
            else:
                read_prefix = '🟡 '
                read_status = 'WARTET'
                msg_read = 'Twitch Chat-Empfang wartet auf twitch_chat / erste eingehende Nachricht.'
            self._set_runtime_field('twitch_chat_live_status', read_prefix + msg_read, parent)
        else:
            ok_read = True
            read_status = 'INAKTIV'
            self._set_runtime_field('twitch_chat_live_status', '⚪ inaktiv', parent)

        # TikTok writing is still browser-based, but all account/profile/live data comes from the main tool.
        if as_bool(settings.get('write_tiktok'), False):
            ok_tt, msg_tt = self._outputs.tiktok.check_login_hint(settings)
            self._set_runtime_field('tiktok_connection_status', ('✅ ' if ok_tt else '❌ ') + msg_tt, parent)
        elif as_bool(settings.get('read_tiktok'), False):
            ok_tt = True
            self._set_runtime_field('tiktok_connection_status', '⚪ Schreiben inaktiv, Lesen über tiktok_live', parent)
        else:
            ok_tt = True
            self._set_runtime_field('tiktok_connection_status', '⚪ inaktiv', parent)

        for key in ('youtube', 'kick'):
            self._set_runtime_field(f'{key}_connection_status', self._format_optional_platform_status(key), parent)

        for key, label in (('obs', 'OBS'), ('meld', 'Meld Studio')):
            if not as_bool(settings.get(f'{key}_enabled'), False):
                self._set_runtime_field(f'{key}_connection_status', '⚪ inaktiv', parent)
            else:
                status = self._format_optional_platform_status(key, label)
                if status == '🟡 aktiv, aber nicht verbunden':
                    host = str(settings.get(f'{key}_host') or '127.0.0.1').strip()
                    port = str(settings.get(f'{key}_port') or '').strip()
                    status = f'🟡 aktiv, aber nicht verbunden ({host}:{port})'
                self._set_runtime_field(f'{key}_connection_status', status, parent)

        if update_plugin_status:
            write_status = 'OK' if ok_write else 'FEHLER'
            state = 'connected' if ok_ai and ok_write and ok_tt and (ok_read or not strict_receive) else 'error'
            self._set_status_line(state, f'Plattformstatus: Twitch Send={write_status} | Twitch Empfang={read_status}')
        return bool(ok_ai and ok_write and ok_tt and ok_read)

    def _mark_twitch_incoming(self, username: str, text: str, source_channel: str = '') -> None:
        # If a real message reached botalot, the receive path is alive right now.
        self._set_runtime_field('twitch_chat_live_status', '✅ Empfängt Twitch-Chat über twitch_chat.')

    def _mark_twitch_reply_result(self, ok: bool, response: str, source_channel: str = '') -> None:
        channel = clean_text(source_channel).lstrip('#')
        suffix = f' #{channel}' if channel else ''
        if ok:
            self._set_runtime_field('twitch_connection_status', f'✅ Botantwort gesendet{suffix}')
        else:
            msg = f'❌ Twitch-Botantwort konnte nicht gesendet werden{suffix}.'
            self._set_runtime_field('twitch_connection_status', msg)

    def _test_openai_connection(self, settings: dict[str, Any] | None = None) -> bool:
        settings = self._settings_with_platforms(settings)
        if not str(settings.get('openai_api_key') or '').strip():
            msg = 'OpenAI API Key fehlt im Haupttool. AI bleibt aus, Bridge/Moderation sind trotzdem nutzbar.'
            self._set_status_line('connected', msg)
            return True
        ok, msg = self._ai.test_connection(settings)
        self._set_status_line('connected' if ok else 'error', msg)
        return ok

    def _test_twitch_connection(self, settings: dict[str, Any] | None = None) -> bool:
        settings = self._settings_with_platforms(settings)
        ok, msg = self._outputs.twitch.check_auth(settings)
        self._set_status_line('connected' if ok else 'error', msg)
        return ok

    def _test_tiktok_status(self, settings: dict[str, Any] | None = None) -> bool:
        ok, msg = self._outputs.tiktok.check_login_hint(self._settings_with_platforms(settings))
        self._set_status_line('connected' if ok else 'error', msg)
        return ok

    def _dialog_settings(self, parent: Any = None) -> dict[str, Any]:
        settings = self._settings if isinstance(self._settings, dict) else {}
        if parent is not None and hasattr(parent, 'values'):
            try:
                values = parent.values()
                if isinstance(values, dict):
                    settings.update(values)
            except Exception:
                pass
        self._settings = settings
        return self._apply_platform_settings(settings)

    def _set_dialog_field(self, parent: Any, key: str, value: str) -> None:
        if parent is None:
            return
        try:
            widget = getattr(parent, '_widgets', {}).get(key)
            if widget is None:
                return
            # QTextEdit/QPlainTextEdit need setPlainText, QLineEdit needs setText.
            if hasattr(widget, 'setPlainText'):
                widget.setPlainText(value)
            elif hasattr(widget, 'setText'):
                widget.setText(value)
            elif hasattr(widget, 'insertPlainText'):
                try:
                    widget.clear()
                except Exception:
                    pass
                widget.insertPlainText(value)
        except Exception:
            pass

    def _publish_setting_value(self, key: str, value: Any) -> None:
        """Best-effort push for runtime fields shown in the plugin settings UI.

        The host currently passes settings into plugins as a plain dict in most
        builds. Mutating that dict is enough after keeping the reference in
        start(), but these optional calls make newer/older host variants update
        too without breaking if the method does not exist.
        """
        try:
            if isinstance(self._settings, dict):
                self._settings[key] = value
        except Exception:
            pass
        host = self._host
        if host is None:
            return
        for name, args in (
            ('set_plugin_setting', (self.plugin_id, key, value)),
            ('update_plugin_setting', (self.plugin_id, key, value)),
            ('set_setting', (self.plugin_id, key, value)),
            ('set_settings_value', (self.plugin_id, key, value)),
            ('update_setting', (self.plugin_id, key, value)),
        ):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    fn(*args)
                    return
                except TypeError:
                    try:
                        fn(key, value)
                        return
                    except Exception:
                        pass
                except Exception:
                    pass


    def _current_twitch_redirect_url(self, settings: dict[str, Any] | None = None) -> str:
        settings = self._settings_with_platforms(settings)
        try:
            port = int(str(settings.get('twitch_redirect_port') or '17564').strip())
        except Exception:
            port = 17564
        return f'http://localhost:{port}/callback/'

    def _update_twitch_redirect_url(self, parent: Any = None) -> bool:
        settings = self._dialog_settings(parent)
        url = self._current_twitch_redirect_url(settings)
        self._settings['twitch_redirect_url'] = url
        self._set_dialog_field(parent, 'twitch_redirect_url', url)
        self._log(f'Twitch Redirect URL: {url}')
        return True

    def _connect_openai(self, parent: Any = None) -> bool:
        settings = self._dialog_settings(parent)
        if not str(settings.get('openai_api_key') or '').strip():
            msg = 'OpenAI API Key fehlt im Haupttool. AI bleibt aus, Bridge/Moderation sind trotzdem nutzbar.'
            self._set_dialog_field(parent, 'openai_connection_status', '🟡 ' + msg)
            self._set_status_line('connected', msg)
            return True
        ok, msg = self._ai.test_connection(settings)
        self._set_dialog_field(parent, 'openai_connection_status', ('✅ ' if ok else '❌ ') + msg)
        self._set_status_line('connected' if ok else 'error', msg)
        return ok

    def _connect_twitch(self, parent: Any = None) -> bool:
        settings = self._dialog_settings(parent)
        # Auth/Login belongs to the central Plattformen tab in the main tool now.
        # botalot only checks whether the central Twitch data/cache is usable.
        ok, msg = self._outputs.twitch.check_auth(settings)
        self._set_dialog_field(parent, 'twitch_connection_status', ('✅ ' if ok else '❌ ') + msg)
        if ok:
            try:
                self._refresh_runtime_status_fields(parent)
            except Exception as exc:
                self._set_status_line('error', f'Live-Status konnte nicht geprüft werden: {exc}')
        self._set_status_line('connected' if ok else 'error', msg)
        return ok

    def _connect_tiktok(self, parent: Any = None) -> bool:
        settings = self._dialog_settings(parent)
        try:
            live_url = self._outputs.tiktok.build_live_url(settings)
            self._settings['tiktok_resolved_live_url'] = live_url
            self._set_dialog_field(parent, 'tiktok_resolved_live_url', live_url)
        except Exception:
            pass
        if not as_bool(settings.get('write_tiktok'), False):
            ok = True
            msg = 'TikTok-Schreiben ist im Haupttool inaktiv.'
            self._set_dialog_field(parent, 'tiktok_connection_status', '⚪ ' + msg)
            self._set_status_line('connected', msg)
            return True

        ok, msg = self._outputs.tiktok.check_login_hint(settings)
        # Wie im alten Stand: Wenn der Debug-Browser nicht läuft, wird er beim Prüfen
        # automatisch gestartet. Sonst kann die TikTok-Bridge nicht schreiben.
        if not ok and self._outputs.tiktok.is_debug_unreachable_message(msg):
            started = self._outputs.tiktok.open_browser(settings, mode='bot')
            if started:
                ready, wait_msg = self._outputs.tiktok.wait_for_debugger(settings, timeout_seconds=8.0)
                if ready:
                    ok, msg = self._outputs.tiktok.check_login_hint(settings)
                else:
                    msg = wait_msg
            else:
                msg = 'TikTok-Browser konnte nicht gestartet werden. Chrome/Edge Pfad prüfen oder manuell setzen.'
        self._set_dialog_field(parent, 'tiktok_connection_status', ('✅ ' if ok else '❌ ') + msg)
        self._set_status_line('connected' if ok else 'error', msg)
        return ok

    def _connect_all(self, parent: Any = None) -> bool:
        settings = self._dialog_settings(parent)

        ok_ai = self._connect_openai(parent)

        ok_tw = True
        if as_bool(settings.get('write_twitch'), False):
            ok_tw = self._connect_twitch(parent)
        elif as_bool(settings.get('read_twitch'), False):
            ok_tw, msg_tw = self._outputs.twitch.check_reader_status(settings)
            self._set_dialog_field(parent, 'twitch_connection_status', '⚪ Schreiben inaktiv, Lesen aktiv')
            self._set_dialog_field(parent, 'twitch_chat_live_status', ('✅ ' if ok_tw else '❌ ') + msg_tw)
        else:
            self._set_dialog_field(parent, 'twitch_connection_status', '⚪ inaktiv')
            self._set_dialog_field(parent, 'twitch_chat_live_status', '⚪ inaktiv')

        ok_tt = True
        if as_bool(settings.get('write_tiktok'), False):
            ok_tt = self._connect_tiktok(parent)
        elif as_bool(settings.get('read_tiktok'), False):
            self._set_dialog_field(parent, 'tiktok_connection_status', '⚪ Schreiben inaktiv, Lesen über tiktok_live')
        else:
            self._set_dialog_field(parent, 'tiktok_connection_status', '⚪ inaktiv')

        # One button updates every visible status row. Optional/future platforms are not errors.
        self._refresh_runtime_status_fields(parent, update_plugin_status=False, strict_receive=True)
        all_ok = bool(ok_ai and ok_tw and ok_tt)
        self._set_status_line('connected' if all_ok else 'error', 'Alle Plattformen geprüft.' if all_ok else 'Plattformprüfung mit Fehlern.')
        return all_ok

    def _test_all_connections(self) -> bool:
        settings = self._settings_with_platforms()
        results = []
        if str(settings.get('openai_api_key') or '').strip():
            ok_ai, msg_ai = self._ai.test_connection(settings)
        else:
            ok_ai, msg_ai = True, 'OpenAI API Key fehlt; AI bleibt aus, kein Plattformfehler.'
        results.append(('OpenAI', ok_ai, msg_ai))
        if as_bool(settings.get('write_twitch'), False):
            ok_tw, msg_tw = self._outputs.twitch.check_auth(settings)
        else:
            ok_tw, msg_tw = True, 'Twitch-Schreiben deaktiviert.'
        results.append(('Twitch', ok_tw, msg_tw))
        if as_bool(settings.get('write_tiktok'), False):
            ok_tt, msg_tt = self._outputs.tiktok.check_login_hint(settings)
        else:
            ok_tt, msg_tt = True, 'TikTok-Schreiben deaktiviert.'
        results.append(('TikTok', ok_tt, msg_tt))
        for name, ok, msg in results:
            self._log(f'{name}: {"OK" if ok else "FEHLER"} - {msg}')
        all_ok = all(ok for _, ok, _ in results)
        summary = ' | '.join(f'{name}: {"OK" if ok else "FEHLER"}' for name, ok, _ in results)
        self._set_status_line('connected' if all_ok else 'error', summary)
        return all_ok

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        host = host or self._host
        if key in {'button_connect_openai', 'button_test_openai_connection'}:
            return self._connect_openai(parent)
        if key == 'button_update_default_prompt':
            return self._update_default_prompt(parent)
        if key == 'button_update_twitch_redirect_url':
            return self._update_twitch_redirect_url(parent)
        if key in {'button_force_twitch_oauth', 'button_twitch_broadcast_oauth'}:
            msg = 'Twitch OAuth wird nur noch im Haupttool unter Plattformen verwaltet.'
            self._log(msg)
            self._set_dialog_field(parent, 'twitch_connection_status', '🟡 ' + msg)
            self._set_status_line('connected', msg)
            return True
        if key in {'button_connect_twitch', 'button_test_twitch_send'}:
            return self._connect_twitch(parent)
        if key in {'button_connect_tiktok', 'button_check_tiktok_login'}:
            return self._connect_tiktok(parent)
        if key in {'button_connect_all', 'button_test_all_connections'}:
            return self._connect_all(parent)
        if key == 'button_refresh_live_status':
            return self._connect_all(parent)
        if key == 'button_open_trigger_file':
            self._ensure_files()
            try:
                import os
                os.startfile(str(TRIGGER_FILE))  # type: ignore[attr-defined]
            except Exception:
                webbrowser.open(TRIGGER_FILE.as_uri())
            return True
        if key == 'button_reload_triggers':
            count = self._triggers.reload()
            self._log(f'Trigger neu geladen: {count}')
            return True
        if key == 'button_moderation_unban_user':
            return self._moderation_unban_from_dialog(parent)
        if key == 'button_moderation_refresh_session_list':
            self._refresh_moderation_banned_users_field(parent)
            return True
        if key == 'button_open_tiktok_bot_login':
            settings = self._settings_with_platforms(self._dialog_settings(parent))
            return self._outputs.tiktok.open_browser(settings, mode='bot')
        if key == 'button_open_tiktok_live':
            settings = self._settings_with_platforms(self._dialog_settings(parent))
            try:
                live_url = self._outputs.tiktok.build_live_url(settings)
                self._settings['tiktok_resolved_live_url'] = live_url
                self._set_dialog_field(parent, 'tiktok_resolved_live_url', live_url)
            except Exception:
                pass
            return self._outputs.tiktok.open_browser(settings, mode='live')
        if key == 'button_close_tiktok_browser':
            settings = self._settings_with_platforms(self._dialog_settings(parent))
            ok, msg = self._outputs.tiktok.close_browser(settings)
            self._set_dialog_field(parent, 'tiktok_connection_status', ('✅ ' if ok else '❌ ') + msg)
            self._set_status_line('stopped' if ok else 'error', msg)
            return ok
        if key == 'button_test_tiktok_send':
            return self._connect_tiktok(parent)
        if key == 'button_test_ai':
            fake = type('BotalotFakeMsg', (), {})()
            fake.platform = 'twitch'
            fake.username = 'BotalotTest'
            fake.text = '@botis3mpty was sagt die Wissenschaft zu Ursulaaaaa?'
            fake.channel = 'test'
            fake.message_type = 'chat'
            self.on_message(fake)
            return True
        return False

    def handle_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host=host, parent=parent)

    def on_settings_action(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host=host, parent=parent)

    def on_message(self, msg: Any) -> None:
        if not self._enabled:
            return
        if self._is_botalot_desktop_injection(msg):
            return
        settings = dict(self._settings or {})

        msg_type = str(
            getattr(msg, 'message_type', '')
            or getattr(msg, 'type', '')
            or getattr(msg, 'event_type', '')
            or 'chat'
        ).strip().lower()

        raw_platform = str(getattr(msg, 'platform', '') or '').strip().lower()
        raw_source_plugin = str(getattr(msg, 'source_plugin_id', '') or '').strip().lower()
        raw_source = str(getattr(msg, 'source', '') or '').strip().lower()
        platform_hint = raw_platform or raw_source_plugin or raw_source

        if msg_type == 'is_live' and (raw_source_plugin == 'tiktok_live' or raw_source == 'tiktok_live' or platform_hint in {'tiktok', 'tt', 'tiktok_live'}):
            self._handle_tiktok_is_live_event(msg, settings)
            return

        if msg_type not in {'chat', 'message', 'comment'}:
            return

        # botalot darf normale Eingangs-Chats nicht selbst im Desktopwindow anzeigen.
        # Die echte Ursprungsnachricht kommt bereits vom jeweiligen Chat-Plugin
        # (twitch_chat, tiktok_live, ...). botalot verarbeitet sie nur fuer Bridge/AI.
        # Sichtbar gespiegelt werden nur explizite Bot/GPT-Antworten ueber
        # _emit_bot_reply_to_desktop(). Dadurch verschwinden doppelte normale
        # Chatzeilen, ohne Bridge oder AI-Trigger anzufassen.
        self._suppress_desktop_echo(msg, 'normal input handled by source plugin')

        # botalot soll TikTok-Chat nur aus dem echten Chat-Plugin nehmen.
        # tiktok_live_alert darf Kommentare/Alerts liefern, aber nicht nochmal
        # durch Bridge/AI laufen, sonst entstehen Doppel-/Dreifachnachrichten.
        if raw_source_plugin == 'tiktok_live_alert' or raw_source == 'tiktok_live_alert':
            return

        platform = platform_hint
        if platform in {'tt', 'tiktok_live'}:
            platform = 'tiktok'
        elif platform == 'twitch_chat':
            platform = 'twitch'
        elif platform in {'youtube_live', 'youtube_chat', 'yt'}:
            platform = 'youtube'
        elif platform == 'kick_chat':
            platform = 'kick'

        username = clean_text(
            getattr(msg, 'username', '')
            or getattr(msg, 'user', '')
            or getattr(msg, 'display_name', '')
            or getattr(msg, 'nickname', '')
            or getattr(msg, 'unique_id', '')
            or ''
        )
        text = clean_text(
            getattr(msg, 'text', '')
            or getattr(msg, 'message', '')
            or getattr(msg, 'content', '')
            or getattr(msg, 'comment', '')
            or getattr(msg, 'body', '')
            or ''
        )
        if not text or not platform or not self._should_read_platform(settings, platform):
            return

        source_channel = clean_text(getattr(msg, 'channel', '') or '')
        if platform == 'twitch':
            self._mark_twitch_incoming(username, text, source_channel)

        if self._handle_moderation_message(settings, msg, platform, username, text, source_channel):
            return

        # Outbound-/Bridge-Echos kommen vom Ziel-Chatplugin wieder als normale
        # Chatnachricht rein. Sie sollen weiterhin im echten Zielchat stehen,
        # aber nicht nochmal im Desktopwindow/OBS-Capture landen und auch nicht
        # erneut durch Bridge oder AI laufen.
        if self._consume_recent_outbound(platform, username, text):
            self._suppress_desktop_echo(msg, 'recent outbound echo')
            return
        if self._is_echo_text(text):
            self._suppress_desktop_echo(msg, 'bridge/ai mirror echo')
            return
        if self._is_gamepicker_system_text(text):
            # gam3pick3r sends the winner once to every enabled platform itself.
            # When Twitch/Kick/YouTube/TikTok read that bot line back, botalot must
            # not treat it as fresh user chat, otherwise each platform receives the
            # original plus all cross-bridged echoes.
            return
        if self._is_recent_duplicate(platform, username, text, ttl=12.0):
            return

        # Bridge läuft immer zuerst und wird weder durch Trigger noch durch
        # excluded/self/bot-Filter blockiert.
        self._maybe_bridge_message_async(settings, platform, username, text, source_channel)

        # Ab hier nur AI. Die Blacklist gilt ausschließlich hier.
        if self._is_excluded_user(settings, username):
            return

        self._context.add(platform, username, text)
        triggered, reason = self._triggers.match(settings, text)
        if not triggered:
            return
        if self._worker_busy:
            self._log('AI busy, trigger skipped.')
            return
        now = time.time()
        global_cd = to_float(settings.get('cooldown_seconds'), 8.0, 0.0, 999.0)
        platform_cd = to_float(settings.get('platform_cooldown_seconds'), 4.0, 0.0, 999.0)
        if global_cd > 0 and now - self._last_reply_at < global_cd:
            return
        if platform_cd > 0 and now - self._last_by_platform.get(platform, 0.0) < platform_cd:
            return
        self._last_reply_at = now
        self._last_by_platform[platform] = now
        if as_bool(settings.get('log_every_trigger'), True):
            self._log(f'Trigger {reason} from {platform}/{username}: {text}')
        self._worker_busy = True
        threading.Thread(target=self._answer_worker, args=(settings, platform, username, text, reason, source_channel), daemon=True, name='botalot-ai').start()




    def _message_bool(self, msg: Any, *names: str) -> bool | None:
        for name in names:
            try:
                if isinstance(msg, dict) and name in msg:
                    value = msg.get(name)
                elif hasattr(msg, name):
                    value = getattr(msg, name)
                else:
                    continue
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return bool(value)
                low = str(value or '').strip().lower()
                if low in {'1', 'true', 'yes', 'ja', 'live', 'online'}:
                    return True
                if low in {'0', 'false', 'no', 'nein', 'offline'}:
                    return False
            except Exception:
                continue
        return None

    def _handle_tiktok_is_live_event(self, msg: Any, settings: dict[str, Any]) -> None:
        is_live = self._message_bool(msg, 'is_live', 'live')
        if is_live is None:
            return

        was_live = self._last_tiktok_is_live
        self._last_tiktok_is_live = bool(is_live)

        if not is_live:
            if self._tiktok_reloaded_for_current_live:
                self._log('TikTok Live ist offline. botalot Live-Reload wird für den nächsten Stream wieder freigegeben.')
            self._tiktok_reloaded_for_current_live = False
            return

        # Nur der echte Übergang offline/unbekannt -> live darf einen Reload auslösen.
        if was_live is True or self._tiktok_reloaded_for_current_live:
            return

        if not as_bool(settings.get('write_tiktok'), False):
            self._log('TikTok Live erkannt, aber TikTok-Schreiben ist in botalot deaktiviert. Kein Browser-Reload.')
            self._tiktok_reloaded_for_current_live = True
            return

        threading.Thread(
            target=self._reload_tiktok_browser_for_live,
            args=(dict(settings or self._settings or {}),),
            daemon=True,
            name='botalot-tiktok-live-reload',
        ).start()

    def _reload_tiktok_browser_for_live(self, settings: dict[str, Any]) -> None:
        with self._tiktok_live_reload_lock:
            if self._tiktok_reloaded_for_current_live:
                return
            self._tiktok_reloaded_for_current_live = True
            try:
                # TikTok braucht nach dem Live-Statuswechsel oft einen kurzen Moment,
                # bevor die Live-Seite den Chat korrekt initialisieren kann.
                time.sleep(3.0)
                ok, msg = self._outputs.tiktok.reload_live_tab(settings)
                if ok:
                    self._set_runtime_field('tiktok_connection_status', '✅ botalot hat beim Live-Gehen den TikTok-Botbrowser neu geladen.')
                    self._log('botalot hat beim Live-Gehen einen TikTok-Botbrowser-Reload durchgeführt.')
                else:
                    self._set_runtime_field('tiktok_connection_status', '❌ TikTok Live erkannt, aber Browser-Reload fehlgeschlagen: ' + msg)
                    self._log('TikTok Live erkannt, aber botalot konnte den Botbrowser nicht neu laden: ' + msg)
            except Exception as exc:
                self._set_runtime_field('tiktok_connection_status', '❌ TikTok Live erkannt, aber Browser-Reload hatte einen Fehler.')
                self._log(f'TikTok Live-Reload Fehler: {exc}')

    def _split_setting_names(self, value: Any) -> set[str]:
        raw = str(value or '').replace('\r', '\n')
        parts: list[str] = []
        for line in raw.split('\n'):
            parts.extend(line.split(','))
        out: set[str] = set()
        for part in parts:
            name = clean_text(part).lstrip('@').lower()
            if name:
                out.add(name)
        return out

    def _moderation_words(self, settings: dict[str, Any]) -> list[tuple[str, str]]:
        raw = str(settings.get('moderation_words') or '')
        words: list[tuple[str, str]] = []
        seen: set[str] = set()
        for part in raw.replace('\r', ',').replace('\n', ',').split(','):
            word = clean_text(part)
            key = norm(word)
            if word and key and key not in seen:
                seen.add(key)
                words.append((word, key))
        return words

    def _moderation_norm_spaced(self, value: Any) -> str:
        text = clean_text(value).lower()
        repl = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', '4': 'a', '5': 's', '0': 'o', '1': 'l', '3': 'e', '$': 's'}
        for a, b in repl.items():
            text = text.replace(a, b)
        text = re.sub(r'[^a-z0-9]+', ' ', text)
        return ' '.join(text.split())

    def _find_moderation_word(self, settings: dict[str, Any], text: str) -> str:
        # Früher wurde alles mit norm() zu einem einzigen String ohne Leerzeichen
        # zusammengezogen und dann per Substring gesucht. Dadurch konnten kurze
        # Sperrwörter zufällig in Bot-Triggern wie @botis3mpty landen und den
        # kompletten GPT-Pfad vorzeitig abbrechen.
        hay = self._moderation_norm_spaced(text)
        if not hay:
            return ''
        padded_hay = f' {hay} '
        for original, key in self._moderation_words(settings):
            if not key:
                continue
            needle = self._moderation_norm_spaced(original)
            if not needle:
                continue
            # Einzelwörter nur als echte Wörter matchen, nicht innerhalb anderer
            # Wörter/Namen. Mehrwort-Phrasen werden ebenfalls mit Wortgrenzen
            # gesucht. So bleibt Moderation aktiv, ohne GPT-Trigger kaputt zu
            # filtern.
            if f' {needle} ' in padded_hay:
                return original
        return ''

    def _format_moderation_message(self, template: str, username: str, platform: str, word: str) -> str:
        user = clean_text(username).lstrip('@') or 'User'
        p = self._bridge_platform_label(platform)
        text = str(template or '').strip() or '(User) wurde gebannt.'
        text = text.replace('(User)', user).replace('(user)', user)
        try:
            text = text.format(user=user, User=user, platform=p, Platform=p, word=word, Word=word)
        except Exception:
            pass
        return clean_text(text)

    def _load_moderation_bans(self) -> list[dict[str, Any]]:
        # Absichtlich nur im RAM: Die Liste soll bei jedem Programmstart leer sein.
        # Die echten Bans bleiben auf Twitch/TikTok bestehen und werden nicht lokal als Historie geladen.
        return [dict(x) for x in getattr(self, '_moderation_bans', []) if isinstance(x, dict)]

    def _save_moderation_bans(self, bans: list[dict[str, Any]]) -> None:
        # Nicht auf Platte speichern, sonst würden alte User beim nächsten Start wieder auftauchen.
        self._moderation_bans = [dict(x) for x in bans if isinstance(x, dict)]

    def _moderation_ban_display_user(self, ban: dict[str, Any]) -> str:
        return clean_text(ban.get('display_user') or ban.get('user') or '').lstrip('@')

    def _format_moderation_bans_field(self, bans: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for ban in bans:
            user = self._moderation_ban_display_user(ban)
            key = user.lower().lstrip('@')
            if user and key not in seen:
                seen.add(key)
                lines.append(user)
        return '\n'.join(lines)

    def _format_moderation_ban_slot(self, ban: dict[str, Any]) -> str:
        platform = clean_text(ban.get('platform') or '')
        user = self._moderation_ban_display_user(ban)
        word = clean_text(ban.get('word') or '')
        if not platform or not user:
            return ''
        suffix = f' | {word}' if word else ''
        return f'{platform}/{user}{suffix}'

    def _refresh_moderation_banned_users_field(self, parent: Any = None) -> None:
        bans = self._load_moderation_bans()
        text = self._format_moderation_bans_field(bans)
        self._publish_setting_value('moderation_banned_users', text)
        if parent is not None:
            self._set_dialog_field(parent, 'moderation_banned_users', text)

    def _remember_moderation_ban(self, platform: str, username: str, word: str, reason: str) -> None:
        p = str(platform or '').strip().lower()
        u = str(username or '').strip().lstrip('@').lower()
        if not p or not u:
            return
        with self._moderation_lock:
            bans = self._load_moderation_bans()
            bans = [b for b in bans if not (str(b.get('platform') or '').lower() == p and str(b.get('user') or '').lower().lstrip('@') == u)]
            bans.append({'platform': p, 'user': u, 'display_user': clean_text(username), 'word': word, 'reason': reason, 'time': time.strftime('%Y-%m-%d %H:%M:%S')})
            self._save_moderation_bans(bans)
            self._publish_setting_value('moderation_banned_users', self._format_moderation_bans_field(bans))
            self._log('Moderation Session-Liste aktualisiert: ' + self._format_moderation_ban_slot(bans[-1]))

    def _forget_moderation_ban(self, platform: str, username: str) -> None:
        p = str(platform or '').strip().lower()
        if p in {'tt', 'tiktok_live'}:
            p = 'tiktok'
        if p == 'twitch_chat':
            p = 'twitch'
        u = str(username or '').strip().lstrip('@').lower()
        with self._moderation_lock:
            bans = self._load_moderation_bans()
            bans = [b for b in bans if not (str(b.get('platform') or '').lower() == p and str(b.get('user') or '').lower().lstrip('@') == u)]
            self._save_moderation_bans(bans)
            self._publish_setting_value('moderation_banned_users', self._format_moderation_bans_field(bans))

    def _moderation_unban_from_dialog(self, parent: Any = None) -> bool:
        settings = self._dialog_settings(parent)
        platform = clean_text(settings.get('moderation_unban_platform') or '')
        username = clean_text(settings.get('moderation_unban_user') or '').lstrip('@')
        if not platform or not username:
            self._log('Moderation Unban übersprungen: Plattform oder Nutzer fehlt.')
            return False
        send_settings = dict(settings)
        if platform.lower() in {'twitch', 'twitch_chat'} and not str(send_settings.get('twitch_channel') or '').strip():
            self._log('Moderation Unban: Twitch Ziel-Kanal fehlt.')
        ok = self._outputs.unban_user(send_settings, platform, username)
        if ok:
            self._forget_moderation_ban(platform, username)
            self._settings['moderation_unban_user'] = ''
            self._refresh_moderation_banned_users_field(parent)
            if parent is not None:
                self._set_dialog_field(parent, 'moderation_unban_user', '')
            self._log(f'Moderation Unban ausgeführt: {platform}/{username}')
        else:
            self._log(f'Moderation Unban fehlgeschlagen: {platform}/{username}')
        return ok

    def _extract_message_id(self, msg: Any) -> str:
        for attr in ('message_id', 'msg_id', 'id', 'twitch_message_id'):
            value = getattr(msg, attr, '')
            if value:
                return clean_text(value)
        tags = getattr(msg, 'tags', None)
        if isinstance(tags, dict):
            for key in ('id', 'message_id', 'msg-id'):
                value = tags.get(key)
                if value:
                    return clean_text(value)
        raw = str(getattr(msg, 'raw', '') or getattr(msg, 'raw_line', '') or '')
        if raw.startswith('@'):
            head = raw.split(' ', 1)[0][1:]
            for part in head.split(';'):
                if part.startswith('id='):
                    return clean_text(part[3:])
        return ''

    def _handle_moderation_message(self, settings: dict[str, Any], msg: Any, platform: str, username: str, text: str, source_channel: str = '') -> bool:
        if not as_bool(settings.get('moderation_enabled'), False):
            return False
        word = self._find_moderation_word(settings, text)
        if not word:
            return False

        send_settings = dict(settings)
        if platform == 'twitch' and not str(send_settings.get('twitch_channel') or '').strip() and source_channel:
            send_settings['twitch_channel'] = source_channel.strip().lstrip('#')

        mod_users = self._split_setting_names(settings.get('moderation_mod_test_users') or '')
        clean_user = str(username or '').strip().lstrip('@').lower()
        if clean_user and clean_user in mod_users:
            out = self._format_moderation_message(str(settings.get('moderation_mod_test_message') or '(User), zum Glück bist du Mod, du darfst das.'), username, platform, word)
            self._suppress_desktop_echo(msg, 'moderation mod test')
            # Test-/Modmeldung nur auf der Ursprungsplattform senden.
            # Nicht künstlich ins Desktopwindow injizieren und nicht bridgen.
            self._remember_outbound(platform, self._bot_name_for_platform(settings, platform), out)
            sent = self._outputs.send_to_source(send_settings, out, platform)
            if sent:
                self._log(f'Moderation Test-User Meldung gesendet: {platform}/{username} mit Wort "{word}"')
            else:
                self._log(f'Moderation Test-User Meldung konnte nicht gesendet werden: {platform}/{username} mit Wort "{word}"')
            return True

        reason = self._format_moderation_message(str(settings.get('moderation_ban_reason') or '(User) wurde gebannt.'), username, platform, word)
        self._suppress_desktop_echo(msg, 'moderation blocked word')

        # Die Originalnachricht wird auf Twitch direkt gelöscht, sobald die Message-ID verfügbar ist.
        if platform == 'twitch':
            msg_id = self._extract_message_id(msg)
            if msg_id:
                self._outputs.delete_message(send_settings, platform, msg_id, source_channel)
            else:
                self._log('Moderation Twitch: Originalnachricht konnte nicht gelöscht werden, weil keine Message-ID am Event hängt.')

        # Moderationsmeldung bleibt strikt nur auf der Ursprungsplattform.
        # Keine Desktop-Injection, keine Bridge. Wenn die echte Chatquelle sie sieht,
        # kommt sie dort höchstens einmal im Desktopwindow an.
        self._remember_outbound(platform, self._bot_name_for_platform(settings, platform), reason)
        sent_reason = self._outputs.send_to_source(send_settings, reason, platform)

        # TikTok-Ban ist ein Chatbefehl im Botbrowser. Den merken wir ebenfalls als
        # Outbound, damit /block nicht durch die Bridge oder AI rutscht, falls TikTok
        # den Befehl als Chatzeile zurückliefert.
        if str(platform or '').strip().lower() in {'tiktok', 'tt', 'tiktok_live'}:
            self._remember_outbound(platform, self._bot_name_for_platform(settings, platform), f'/block @{str(username or '').strip().lstrip("@")}', ttl=20.0)

        banned = self._outputs.ban_user(send_settings, platform, username, reason)
        self._remember_moderation_ban(platform, username, word, reason)
        if banned:
            self._log(f'Moderation Ban ausgeführt: {platform}/{username} wegen "{word}"')
        else:
            self._log(f'Moderation Ban versucht/gespeichert: {platform}/{username} wegen "{word}"')
        if not sent_reason:
            self._log(f'Moderation Ban-Meldung konnte nicht auf der Ursprungsplattform gesendet werden: {platform}/{username}')
        return True

    def _message_key(self, platform: str, username: str, text: str) -> str:
        p = str(platform or '').strip().lower()
        if p in {'tt', 'tiktok_live'}:
            p = 'tiktok'
        if p == 'twitch_chat':
            p = 'twitch'
        u = str(username or '').strip().lstrip('@').lower()
        t = ' '.join(str(text or '').strip().split()).lower()
        return f'{p}|{u}|{t}'

    def _is_recent_duplicate(self, platform: str, username: str, text: str, ttl: float = 3.0) -> bool:
        now = time.time()
        key = self._message_key(platform, username, text)
        with self._recent_message_lock:
            old = self._recent_messages.get(key)
            # kleine Aufraeumrunde
            for k, ts in list(self._recent_messages.items()):
                if now - ts > 30.0:
                    self._recent_messages.pop(k, None)
            if old is not None and now - old <= ttl:
                return True
            self._recent_messages[key] = now
            return False

    def _is_botalot_desktop_injection(self, msg: Any) -> bool:
        try:
            if isinstance(msg, dict):
                return bool(msg.get('botalot_desktop_injection') or msg.get('botalot_force_desktop'))
        except Exception:
            pass
        for attr in ('botalot_desktop_injection', 'botalot_force_desktop'):
            try:
                if bool(getattr(msg, attr, False)):
                    return True
            except Exception:
                pass
        return False

    def _install_host_emit_filter(self, host: Any) -> None:
        """Filter botalot's own outbound bridge/AI echoes before the Desktopwindow sees them.

        The normal chat plugins emit bot-sent lines back into godisalotachat as if
        they were fresh incoming chat. By the time botalot.on_message() receives
        that ChatMessage, the Desktopwindow has already stored/rendered it. So the
        suppression must happen one step earlier: directly around host.emit_message.

        This does not touch the actual Twitch/TikTok bridge sending. It only sets
        show_in_desktop=False for messages that match botalot's recent outbound
        list, so real user messages still appear normally.
        """
        if host is None or self._host_emit_filter_installed:
            return
        try:
            current_emit = getattr(host, 'emit_message')
        except Exception:
            return
        if getattr(host, '_botalot_emit_filter_active', False):
            return
        self._host_emit_original = current_emit
        plugin_self = self

        def botalot_emit_message_filter(plugin_id: str, payload: dict[str, Any]) -> None:
            try:
                plugin_self._handle_host_metric_payload(plugin_id, payload)
            except Exception:
                pass
            try:
                plugin_self._filter_outbound_echo_payload(plugin_id, payload)
            except Exception:
                pass
            return current_emit(plugin_id, payload)

        try:
            setattr(host, 'emit_message', botalot_emit_message_filter)
            setattr(host, '_botalot_emit_filter_active', True)
            self._host_emit_filter_installed = True
        except Exception:
            self._host_emit_original = None
            self._host_emit_filter_installed = False

    def _restore_host_emit_filter(self) -> None:
        host = self._host
        if host is None or not self._host_emit_filter_installed or self._host_emit_original is None:
            return
        try:
            setattr(host, 'emit_message', self._host_emit_original)
            setattr(host, '_botalot_emit_filter_active', False)
        except Exception:
            pass
        self._host_emit_original = None
        self._host_emit_filter_installed = False

    def _filter_outbound_echo_payload(self, plugin_id: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get('botalot_desktop_injection') or payload.get('botalot_force_desktop'):
            return

        # Normale botalot-Events sind reine Verarbeitungs-/Bridge-Events und
        # sollen nicht als zweite Chatquelle im Desktopwindow landen. GPT/Bot-
        # Antworten setzen botalot_force_desktop=True und bleiben sichtbar.
        if str(plugin_id or '').strip().lower() == self.plugin_id:
            payload['show_in_desktop'] = False
            payload['desktop_visible'] = False
            payload['visible_in_desktop'] = False
            payload['display_in_desktop'] = False
            payload['emit_to_desktop'] = False
            payload['suppress_desktop'] = True
            payload['skip_desktop'] = True
            payload['desktop_suppressed'] = True
            payload['botalot_input_echo'] = True
            return
        platform = str(payload.get('platform') or plugin_id or '').strip().lower()
        if platform in {'tt', 'tiktok_live'}:
            platform = 'tiktok'
        elif platform == 'twitch_chat':
            platform = 'twitch'
        elif platform in {'youtube_live', 'youtube_chat', 'yt'}:
            platform = 'youtube'
        username = clean_text(
            payload.get('username')
            or payload.get('display_name')
            or payload.get('user')
            or payload.get('nickname')
            or payload.get('unique_id')
            or ''
        )
        text = clean_text(
            payload.get('text')
            or payload.get('message')
            or payload.get('content')
            or payload.get('comment')
            or payload.get('body')
            or ''
        )
        if not platform or not text:
            return

        # Bridge-/AI-Echos muessen VOR dem Desktopwindow gefiltert werden.
        # on_message() kommt dafuer zu spaet, weil das Hauptfenster die Zeile dann
        # schon angezeigt hat. Darum hier nicht nur nach Username matchen, sondern
        # auch die bekannten Bridge-/AI-Prefixe hart aus der Desktopanzeige nehmen.
        is_known_bridge_echo = self._is_echo_text(text)
        is_recent_outbound = bool(username and self._is_recent_outbound_echo(platform, username, text))
        if not is_known_bridge_echo and not is_recent_outbound:
            return

        # Nur die Desktop-Anzeige rausnehmen. Der echte Zielchat bleibt komplett
        # unverändert, und OBS/andere Ausgaben behalten ihre eigenen Schalter.
        payload['show_in_desktop'] = False
        payload['desktop_visible'] = False
        payload['visible_in_desktop'] = False
        payload['display_in_desktop'] = False
        payload['suppress_desktop'] = True
        payload['skip_desktop'] = True
        payload['desktop_suppressed'] = True
        payload['botalot_outbound_echo'] = True

    def _is_recent_outbound_echo(self, platform: str, username: str, text: str) -> bool:
        now = time.time()
        key = self._message_key(platform, username, text)
        with self._recent_outbound_lock:
            for k, expires in list(self._recent_outbound.items()):
                if expires < now:
                    self._recent_outbound.pop(k, None)
            expires = self._recent_outbound.get(key)
            return bool(expires and expires >= now)

    def _remember_outbound(self, platform: str, username: str, text: str, ttl: float = 45.0) -> None:
        key = self._message_key(platform, username, text)
        with self._recent_outbound_lock:
            self._recent_outbound[key] = time.time() + max(1.0, ttl)

    def _consume_recent_outbound(self, platform: str, username: str, text: str) -> bool:
        now = time.time()
        key = self._message_key(platform, username, text)
        with self._recent_outbound_lock:
            for k, expires in list(self._recent_outbound.items()):
                if expires < now:
                    self._recent_outbound.pop(k, None)
            expires = self._recent_outbound.get(key)
            if expires and expires >= now:
                # Nicht entfernen: TikTok/Twitch koennen dieselbe eigene Botzeile
                # mehrfach als Chat-Event zurueckliefern. Wenn wir den Marker beim
                # ersten Echo verbrauchen, rutscht das zweite Echo wieder als echte
                # Nachricht durch Bridge/AI und erzeugt genau diese 2x/4x-Kacke.
                return True
            return False

    def _suppress_desktop_echo(self, msg: Any, reason: str = '') -> None:
        """Mark a re-read outbound bridge/AI mirror line as hidden for desktop outputs.

        This does not change Twitch/TikTok sending at all. It only gives the
        host/Desktopwindow the strongest possible hint that this message is an
        outbound echo and should not be rendered a second time.
        """
        false_fields = (
            'show_in_desktop', 'show_in_obs', 'show_in_obs_capture',
            'desktop_visible', 'obs_visible', 'visible_in_desktop',
            'emit_to_desktop', 'emit_to_obs', 'display_in_desktop',
        )
        true_fields = (
            'suppress_desktop', 'skip_desktop', 'hidden_from_desktop',
            'desktop_suppressed', 'botalot_outbound_echo',
        )
        try:
            if isinstance(msg, dict):
                for key in false_fields:
                    msg[key] = False
                for key in true_fields:
                    msg[key] = True
                msg['metric_only'] = True
                msg['botalot_suppress_reason'] = reason
                return
        except Exception:
            pass
        for key in false_fields:
            try:
                setattr(msg, key, False)
            except Exception:
                pass
        for key in true_fields:
            try:
                setattr(msg, key, True)
            except Exception:
                pass
        try:
            setattr(msg, 'metric_only', True)
        except Exception:
            pass
        try:
            setattr(msg, 'botalot_suppress_reason', reason)
        except Exception:
            pass

    def _is_gamepicker_system_text(self, text: str) -> bool:
        raw = str(text or '').strip()
        low_text = raw.lower()
        if '\u2063\u200b\u2063\u200b\u2063' in raw or '\u2063gam3pick3r-system\u2063' in raw:
            return True
        # Fallback for platforms that strip invisible marker characters.
        gamepicker_phrases = (
            'the community has crowned ',
            'the random picker chose ',
        )
        return any(phrase in low_text for phrase in gamepicker_phrases)

    def _is_echo_text(self, text: str) -> bool:
        low_text = str(text or '').strip().lower()
        bridge_prefixes = (
            'tt-message from ', 'tiktok-message from ', 'twitch-message from ',
            'youtube-message from ', 'kick-message from ',
            'tt-ai answer to ', 'tiktok-ai answer to ', 'twitch-ai answer to ',
            'youtube-ai answer to ', 'kick-ai answer to ',
        )
        return low_text.startswith(bridge_prefixes)

    def _maybe_bridge_message_async(self, settings: dict[str, Any], source_platform: str, username: str, text: str, source_channel: str = '') -> None:
        """Run the normal chat bridge without blocking the AI path.

        TikTok browser sending and Twitch IRC/API setup can take noticeable time.
        In older versions a triggered @bot message waited for the bridge send first,
        so the GPT answer felt late even though OpenAI was already ready.
        This keeps the bridge behavior exactly the same, but lets AI generation start
        immediately.
        """
        if not as_bool(settings.get('bridge_enabled'), False):
            return
        bridge_settings = dict(settings or {})
        threading.Thread(
            target=self._maybe_bridge_message,
            args=(bridge_settings, source_platform, username, text, source_channel),
            daemon=True,
            name='botalot-bridge-send',
        ).start()


    def _maybe_bridge_message(self, settings: dict[str, Any], source_platform: str, username: str, text: str, source_channel: str = '') -> None:
        """Optional normal chat relay between Twitch, TikTok and YouTube.

        AI replies still use send_to_source(). This bridge is only for forwarding
        real user chat between enabled platforms with the original chatter name.
        """
        if not as_bool(settings.get('bridge_enabled'), False):
            return
        p = str(source_platform or '').strip().lower()
        if p in {'tt', 'tiktok_live'}:
            p = 'tiktok'
        if p == 'twitch_chat':
            p = 'twitch'
        if p in {'youtube_live', 'youtube_chat', 'yt'}:
            p = 'youtube'
        if p == 'kick_chat':
            p = 'kick'
        if p not in {'twitch', 'tiktok', 'youtube', 'kick'}:
            return
        stripped = (text or '').strip()
        if not stripped:
            return
        low_text = stripped.lower()
        bridge_prefixes = (
            'tt-message from ', 'tiktok-message from ', 'twitch-message from ',
            'youtube-message from ', 'kick-message from ',
            'tt-ai answer to ', 'tiktok-ai answer to ', 'twitch-ai answer to ',
            'youtube-ai answer to ', 'kick-ai answer to ',
        )
        if low_text.startswith(bridge_prefixes):
            return

        targets: list[str] = []
        if p == 'twitch':
            if as_bool(settings.get('bridge_twitch_to_tiktok'), False):
                targets.append('tiktok')
            if as_bool(settings.get('bridge_twitch_to_youtube'), False):
                targets.append('youtube')
            if as_bool(settings.get('bridge_twitch_to_kick'), False) or self._auto_bridge_to_kick_enabled(settings):
                targets.append('kick')
        elif p == 'tiktok':
            if as_bool(settings.get('bridge_tiktok_to_twitch'), False):
                targets.append('twitch')
            if as_bool(settings.get('bridge_tiktok_to_youtube'), False):
                targets.append('youtube')
            if as_bool(settings.get('bridge_tiktok_to_kick'), False) or self._auto_bridge_to_kick_enabled(settings):
                targets.append('kick')
        elif p == 'youtube':
            if as_bool(settings.get('bridge_youtube_to_twitch'), False):
                targets.append('twitch')
            if as_bool(settings.get('bridge_youtube_to_tiktok'), False):
                targets.append('tiktok')
            if as_bool(settings.get('bridge_youtube_to_kick'), False) or self._auto_bridge_to_kick_enabled(settings):
                targets.append('kick')
        elif p == 'kick':
            if as_bool(settings.get('bridge_kick_to_twitch'), False) or self._auto_bridge_from_kick_enabled(settings, 'twitch'):
                targets.append('twitch')
            if as_bool(settings.get('bridge_kick_to_tiktok'), False) or self._auto_bridge_from_kick_enabled(settings, 'tiktok'):
                targets.append('tiktok')
            if as_bool(settings.get('bridge_kick_to_youtube'), False) or self._auto_bridge_from_kick_enabled(settings, 'youtube'):
                targets.append('youtube')
        if not targets:
            return

        fmt = str(settings.get('bridge_prefix_format') or '[{platform}] {user}: {text}')
        label = self._bridge_platform_label(p)
        try:
            bridged_base = fmt.format(platform=label, user=username, text=stripped)
        except Exception:
            bridged_base = f'[{label}] {username}: {stripped}'

        for target in targets:
            if as_bool(settings.get('bridge_only_when_write_enabled'), True):
                if target == 'tiktok' and not as_bool(settings.get('write_tiktok'), False):
                    continue
                if target == 'twitch' and not as_bool(settings.get('write_twitch'), False):
                    continue
                if target == 'youtube' and not (as_bool(settings.get('write_youtube'), False) or str(settings.get('youtube_access_token') or settings.get('youtube_refresh_token') or '').strip()):
                    self._log('Bridge nach YouTube übersprungen: YouTube schreiben ist im Haupttool nicht verfügbar.')
                    continue
                if target == 'kick' and not self._platform_has_kick_send_access(settings):
                    self._log('Bridge nach Kick übersprungen: Kick schreiben ist im Haupttool nicht verfügbar oder kick_chat ist nicht aktiv.')
                    continue

            bridged = bridged_base
            if target != 'tiktok':
                bridged = strip_response(bridged, 240)

            send_settings = dict(settings)
            if target == 'twitch' and not str(send_settings.get('twitch_channel') or '').strip() and source_channel:
                send_settings['twitch_channel'] = source_channel.strip().lstrip('#')

            ok = False
            if target == 'tiktok':
                parts = self._split_tiktok_outgoing_message(bridged, 150)
                total = len(parts)
                ok = bool(parts)
                if total > 1:
                    send_settings['tiktok_disable_focus_fallback'] = True
                for idx, part in enumerate(parts, 1):
                    self._remember_outbound(target, self._bot_name_for_platform(settings, target), part)
                    part_ok = self._outputs.tiktok.send(send_settings, part)
                    if part_ok:
                        if total > 1:
                            self._log(f'Bridge {p} → {target} ({idx}/{total}): {part}')
                        else:
                            self._log(f'Bridge {p} → {target}: {part}')
                    else:
                        self._log(f'Bridge {p} → {target} fehlgeschlagen ({idx}/{total}): {part}')
                        ok = False
                    if total > 1 and idx < total:
                        time.sleep(0.25)
            else:
                self._remember_outbound(target, self._bot_name_for_platform(settings, target), bridged)
                ok = self._outputs.send_to_platform(send_settings, bridged, target)
                if ok:
                    self._log(f'Bridge {p} → {target}: {bridged}')
                else:
                    self._log(f'Bridge {p} → {target} fehlgeschlagen: {bridged}')


    def _split_tiktok_outgoing_message(self, text: str, limit: int = 150) -> list[str]:
        """Split every botalot message that goes to TikTok.

        TikTok gets a hard 150-char limit including the origin/user prefix.
        The full bridge/AI context stays only in part 1, for example:
        "Twitch-AI answer to godis3mpty: @godis3mpty ..."
        Follow-up parts use only "(2/3) ..." so the nickname/prefix does not
        waste the limit again.
        """
        msg = str(text or '').strip()
        if not msg:
            return []
        limit = max(50, int(limit or 150))
        if len(msg) <= limit:
            return [msg]

        def split_words(value: str, cap: int) -> tuple[str, str]:
            value = str(value or '').strip()
            cap = max(1, int(cap or 1))
            if len(value) <= cap:
                return value, ''
            words = value.split()
            if not words:
                return value[:cap], value[cap:].strip()
            out = ''
            used = 0
            for word in words:
                add = word if not out else ' ' + word
                if len(out) + len(add) <= cap:
                    out += add
                    used += len(add)
                    continue
                break
            if out:
                return out.strip(), value[len(out):].strip()
            return value[:cap].strip(), value[cap:].strip()

        def split_fixed(value: str, cap: int) -> list[str]:
            value = str(value or '').strip()
            cap = max(1, int(cap or 1))
            parts: list[str] = []
            rest = value
            while rest:
                part, rest = split_words(rest, cap)
                if not part:
                    part, rest = rest[:cap], rest[cap:].strip()
                parts.append(part)
            return parts

        prefix = ''
        body = msg
        # Known botalot bridge/AI formats: keep the expensive context only once.
        # Examples:
        # Twitch-Message from godis3mpty: hallo
        # Twitch-AI answer to godis3mpty: @godis3mpty hallo
        m = re.match(r'^((?:TT|TikTok|Twitch|YouTube|Kick)[_\- ](?:Message from|AI answer to)\s+[^:]{1,80}:\s*)(.*)$', msg, flags=re.IGNORECASE | re.DOTALL)
        if m:
            prefix, body = m.group(1), m.group(2).strip()
        else:
            # Generic safety: if a short prefix with a writer/name exists, keep it
            # only in part 1 too. Long texts without such prefix are split plainly.
            colon = msg.find(': ')
            if 0 < colon <= 90:
                prefix, body = msg[:colon + 2], msg[colon + 2:].strip()

        if not prefix:
            # No origin prefix. Use compact numbered follow-ups, first part stays clean.
            parts = split_fixed(msg, limit)
            if len(parts) <= 1:
                return parts
            total = len(parts)
            out = [parts[0][:limit]]
            for idx, part in enumerate(parts[1:], 2):
                marker = f'({idx}/{total}) '
                out.append(marker + part[:max(0, limit - len(marker))])
            return out

        if len(prefix) >= limit - 10:
            # Extremely long prefix: fall back to safe plain splitting, never exceed limit.
            parts = split_fixed(msg, limit)
            if len(parts) <= 1:
                return parts
            total = len(parts)
            out = [parts[0][:limit]]
            for idx, part in enumerate(parts[1:], 2):
                marker = f'({idx}/{total}) '
                out.append(marker + part[:max(0, limit - len(marker))])
            return out

        total_guess = 2
        body_parts: list[str] = []
        for _ in range(10):
            rest = body
            built: list[str] = []
            first_cap = max(1, limit - len(prefix))
            first, rest = split_words(rest, first_cap)
            built.append(first)
            idx = 2
            while rest:
                marker = f'({idx}/{total_guess}) '
                cap = max(1, limit - len(marker))
                part, rest = split_words(rest, cap)
                built.append(part)
                idx += 1
            new_total = len(built)
            body_parts = built
            if new_total == total_guess:
                break
            total_guess = new_total

        total = len(body_parts)
        if total <= 1:
            return [msg[:limit]]
        out: list[str] = []
        first_text = (prefix + body_parts[0]).strip()
        out.append(first_text[:limit])
        for idx, part in enumerate(body_parts[1:], 2):
            marker = f'({idx}/{total}) '
            out.append(marker + str(part or '')[:max(0, limit - len(marker))])
        return [x for x in out if x]

    def _split_twitch_to_tiktok_bridge_message(self, text: str, limit: int = 150) -> list[str]:
        # Backward-compatible wrapper for older call sites.
        return self._split_tiktok_outgoing_message(text, limit)

    def _bridge_platform_label(self, platform: str) -> str:
        """Human-readable origin label for bridged messages.

        This is intentionally short for TikTok so the Twitch side says
        `TT-Message from Name: ...`, while other platforms keep their normal
        names. The helper is generic so YouTube/Kick can use the same
        output style once their send bridges are wired.
        """
        p = str(platform or '').strip().lower()
        if p in {'tt', 'tiktok', 'tiktok_live'}:
            return 'TT'
        if p in {'twitch', 'twitch_chat'}:
            return 'Twitch'
        if p in {'youtube', 'youtube_live', 'youtube_chat', 'yt'}:
            return 'YouTube'
        if p in {'kick', 'kick_chat'}:
            return 'Kick'
        return p.capitalize() if p else 'Chat'

    def _emit_bridge_to_desktop(self, settings: dict[str, Any], target_platform: str, text: str, source_channel: str = '') -> None:
        if not as_bool(settings.get('bridge_show_in_desktop'), False):
            return
        bot_name = str(settings.get('twitch_bot_username') if target_platform == 'twitch' else settings.get('tiktok_second_account') or 'botalot').strip().lstrip('@') or 'botalot'
        self._emit_desktop_chat_message(target_platform, bot_name, text, source_channel, 'Bridge')

    def _desktop_source_plugin_id(self, platform: str) -> str:
        p = str(platform or '').strip().lower()
        if p in {'tt', 'tiktok', 'tiktok_live'}:
            return 'tiktok_live'
        if p in {'twitch', 'twitch_chat'}:
            return 'twitch_chat'
        if p in {'youtube', 'youtube_live', 'youtube_chat', 'yt'}:
            return 'youtube_chat'
        if p in {'kick', 'kick_chat'}:
            return 'kick_chat'
        return self.plugin_id

    def _emit_desktop_chat_message(self, platform: str, username: str, text: str, channel: str = '', label: str = 'Bot-Antwort') -> None:
        """Inject an already-sent bot/bridge message into godisalotachat's desktop/OBS message stream.

        botalot sends replies through its own Twitch/TikTok writers, so the normal
        source chat plugin never sees that outbound message. This explicitly mirrors
        the outbound line into the same ChatMessage path that twitch_chat/tiktok_live
        use. The source_plugin_id is mapped to the target platform plugin so the
        Desktopwindow filters/icons treat it like a normal platform chat message.
        """
        host = self._host
        if host is None:
            return
        p = str(platform or '').strip().lower() or 'botalot'
        if p in {'tt', 'tiktok_live'}:
            p = 'tiktok'
        if p == 'twitch_chat':
            p = 'twitch'
        msg_text = str(text or '').strip()
        if not msg_text:
            return
        source_plugin = self._desktop_source_plugin_id(p)
        clean_name = str(username or 'botalot').strip().lstrip('@') or 'botalot'
        payload = {
            'platform': p,
            'username': clean_name,
            'display_name': clean_name,
            'text': msg_text,
            'message': msg_text,
            'content': msg_text,
            'comment': msg_text,
            'overlay_html': msg_text,
            'channel': str(channel or '').strip(),
            'message_type': 'chat',
            'type': 'chat',
            'event_type': 'chat',
            'source_plugin_id': source_plugin,
            'source': source_plugin,
            'show_in_desktop': True,
            'desktop_visible': True,
            'visible_in_desktop': True,
            'display_in_desktop': True,
            'emit_to_desktop': True,
            'suppress_desktop': False,
            'skip_desktop': False,
            'desktop_suppressed': False,
            'botalot_desktop_injection': True,
            'botalot_force_desktop': True,
            'show_in_obs': True,
            'show_in_obs_capture': True,
            'metric_only': False,
            'is_alert': False,
            'alert': False,
        }
        try:
            # Wichtig: als Ziel-Plattform-Plugin emittieren, nicht als botalot.
            # Das Desktopwindow filtert/ordnet viele Chat-Zeilen nach der Plugin-ID.
            host.emit_message(source_plugin, payload)
            self._log(f'{label} im Desktopwindow gespiegelt: {p}/{payload["username"]}: {msg_text}')
        except Exception as exc:
            self._log(f'{label} konnte nicht ins Desktopwindow gespiegelt werden: {exc}')

    def _answer_worker(self, settings: dict[str, Any], source_platform: str, username: str, text: str, reason: str, source_channel: str = '') -> None:
        try:
            context_count = to_int(settings.get('context_messages'), 10, 1, 30)
            context_text = self._context.format_recent_for_user(source_platform, username, context_count)
            response = self._ai.generate(settings, source_platform, username, text, reason, context_text)
            if not response:
                return
            if as_bool(settings.get('reply_prefix_user'), True) and username:
                response = f'@{username} {response}'
            response = strip_response(response, to_int(settings.get('max_response_chars'), 200, 40, 500))

            # Wichtig für Twitch: Wenn im botalot-UI kein Ziel-Kanal eingetragen ist,
            # nehmen wir automatisch den Kanal der auslösenden Twitch-Nachricht.
            # Genau das liefert godisalotachat/twitch_chat bereits mit msg.channel.
            send_settings = dict(settings)
            if source_platform == 'twitch' and not str(send_settings.get('twitch_channel') or '').strip() and source_channel:
                send_settings['twitch_channel'] = source_channel.strip().lstrip('#')
                self._log(f'Twitch Ziel-Kanal automatisch aus Eingang gesetzt: #{send_settings["twitch_channel"]}')

            normalized_source = str(source_platform or '').strip().lower()
            if normalized_source in {'tt', 'tiktok_live'}:
                normalized_source = 'tiktok'
            if normalized_source == 'twitch_chat':
                normalized_source = 'twitch'

            sent = False
            if normalized_source == 'tiktok':
                if as_bool(send_settings.get('write_tiktok'), False):
                    parts = self._split_tiktok_outgoing_message(response, 150)
                    if len(parts) > 1:
                        send_settings['tiktok_disable_focus_fallback'] = True
                    sent = bool(parts)
                    for idx, part in enumerate(parts, 1):
                        self._remember_outbound(source_platform, self._bot_name_for_platform(settings, source_platform), part)
                        part_ok = self._outputs.tiktok.send(send_settings, part)
                        sent = bool(part_ok) and sent
                        if len(parts) > 1 and idx < len(parts):
                            time.sleep(0.25)
                else:
                    sent = False
            else:
                self._remember_outbound(source_platform, self._bot_name_for_platform(settings, source_platform), response)
                sent = self._outputs.send_to_source(send_settings, response, source_platform)
            if source_platform == 'twitch':
                self._mark_twitch_reply_result(bool(sent), response, source_channel)
            if sent:
                self._emit_bot_reply_to_desktop(send_settings, source_platform, response, source_channel)
            mirrored = self._maybe_mirror_ai_reply(send_settings, source_platform, username, response, source_channel)
            if sent:
                if mirrored:
                    self._log(f'Antwort gesendet und gespiegelt: {response}')
                else:
                    self._log(f'Antwort gesendet: {response}')
            else:
                if mirrored:
                    self._log(f'Antwort auf Eingangsplattform fehlgeschlagen, aber Spiegelung gesendet: {response}')
                else:
                    self._log(f'Antwort erzeugt, aber keine aktive Sendebrücke erfolgreich: {response}')
        finally:
            self._worker_busy = False

    def _maybe_mirror_ai_reply(self, settings: dict[str, Any], source_platform: str, username: str, response: str, source_channel: str = '') -> bool:
        """Optionally send the same AI answer to other enabled platform chats."""
        if not as_bool(settings.get('ai_mirror_enabled'), True):
            return False
        p = str(source_platform or '').strip().lower()
        if p in {'tt', 'tiktok_live'}:
            p = 'tiktok'
        if p == 'twitch_chat':
            p = 'twitch'
        if p in {'youtube_live', 'youtube_chat', 'yt'}:
            p = 'youtube'
        if p == 'kick_chat':
            p = 'kick'
        if p not in {'twitch', 'tiktok', 'youtube', 'kick'}:
            return False

        targets: list[str] = []
        if p == 'twitch':
            if as_bool(settings.get('ai_mirror_twitch_to_tiktok'), False):
                targets.append('tiktok')
            if as_bool(settings.get('ai_mirror_twitch_to_youtube'), False):
                targets.append('youtube')
            if as_bool(settings.get('ai_mirror_twitch_to_kick'), False):
                targets.append('kick')
        elif p == 'tiktok':
            if as_bool(settings.get('ai_mirror_tiktok_to_twitch'), False):
                targets.append('twitch')
            if as_bool(settings.get('ai_mirror_tiktok_to_youtube'), False):
                targets.append('youtube')
            if as_bool(settings.get('ai_mirror_tiktok_to_kick'), False):
                targets.append('kick')
        elif p == 'youtube':
            if as_bool(settings.get('ai_mirror_youtube_to_twitch'), False):
                targets.append('twitch')
            if as_bool(settings.get('ai_mirror_youtube_to_tiktok'), False):
                targets.append('tiktok')
            if as_bool(settings.get('ai_mirror_youtube_to_kick'), False):
                targets.append('kick')
        elif p == 'kick':
            if as_bool(settings.get('ai_mirror_kick_to_twitch'), False):
                targets.append('twitch')
            if as_bool(settings.get('ai_mirror_kick_to_tiktok'), False):
                targets.append('tiktok')
            if as_bool(settings.get('ai_mirror_kick_to_youtube'), False):
                targets.append('youtube')
        if not targets:
            return False

        sent_any = False
        for target in targets:
            if as_bool(settings.get('ai_mirror_only_when_write_enabled'), True):
                if target == 'tiktok' and not as_bool(settings.get('write_tiktok'), False):
                    continue
                if target == 'twitch' and not as_bool(settings.get('write_twitch'), False):
                    continue
                if target == 'youtube' and not (as_bool(settings.get('write_youtube'), False) or str(settings.get('youtube_access_token') or settings.get('youtube_refresh_token') or '').strip()):
                    self._log('Bridge nach YouTube übersprungen: YouTube schreiben ist im Haupttool nicht verfügbar.')
                    continue
                if target == 'kick' and not self._platform_has_kick_send_access(settings):
                    self._log('Bridge nach Kick übersprungen: Kick schreiben ist im Haupttool nicht verfügbar oder kick_chat ist nicht aktiv.')
                    continue

            out = str(response or '').strip()
            fmt = str(settings.get('ai_mirror_prefix_format') or '').strip()
            if fmt:
                label = self._bridge_platform_label(p)
                try:
                    out = fmt.format(platform=label, user=username, response=response)
                except Exception:
                    out = f'[{label}] {response}'
            if target != 'tiktok':
                out = strip_response(out, to_int(settings.get('max_response_chars'), 200, 40, 500))

            send_settings = dict(settings)
            if target == 'twitch' and not str(send_settings.get('twitch_channel') or '').strip() and source_channel:
                send_settings['twitch_channel'] = source_channel.strip().lstrip('#')

            if target == 'tiktok':
                parts = self._split_tiktok_outgoing_message(out, 150)
                if len(parts) > 1:
                    send_settings['tiktok_disable_focus_fallback'] = True
                ok = bool(parts)
                for idx, part in enumerate(parts, 1):
                    self._remember_outbound(target, self._bot_name_for_platform(settings, target), part)
                    part_ok = self._outputs.tiktok.send(send_settings, part)
                    ok = bool(part_ok) and ok
                    if part_ok:
                        if len(parts) > 1:
                            self._log(f'AI-Spiegel {p} → {target} ({idx}/{len(parts)}): {part}')
                        else:
                            self._log(f'AI-Spiegel {p} → {target}: {part}')
                    else:
                        self._log(f'AI-Spiegel {p} → {target} fehlgeschlagen ({idx}/{len(parts)}): {part}')
                    if len(parts) > 1 and idx < len(parts):
                        time.sleep(0.25)
                sent_any = ok or sent_any
                continue

            self._remember_outbound(target, self._bot_name_for_platform(settings, target), out)
            ok = self._outputs.send_to_platform(send_settings, out, target)
            if ok:
                self._log(f'AI-Spiegel {p} → {target}: {out}')
                sent_any = True
            else:
                self._log(f'AI-Spiegel {p} → {target} fehlgeschlagen: {out}')
        return sent_any

    def _bot_name_for_platform(self, settings: dict[str, Any], platform: str) -> str:
        p = str(platform or '').strip().lower()
        if p in {'tt', 'tiktok_live'}:
            p = 'tiktok'
        if p == 'twitch_chat':
            p = 'twitch'
        if p in {'youtube_live', 'youtube_chat', 'yt'}:
            p = 'youtube'
        if p == 'kick_chat':
            p = 'kick'
        if p == 'tiktok':
            name = str(settings.get('tiktok_second_account') or settings.get('twitch_bot_username') or settings.get('youtube_bot_account') or 'botalot')
        elif p == 'twitch':
            name = str(settings.get('twitch_bot_username') or settings.get('tiktok_second_account') or settings.get('youtube_bot_account') or 'botalot')
        elif p == 'youtube':
            name = str(settings.get('youtube_bot_account') or settings.get('twitch_bot_username') or settings.get('tiktok_second_account') or settings.get('kick_bot_account') or 'botalot')
        elif p == 'kick':
            name = str(settings.get('kick_bot_account') or settings.get('twitch_bot_username') or settings.get('tiktok_second_account') or settings.get('youtube_bot_account') or 'botalot')
        else:
            name = str(settings.get('twitch_bot_username') or settings.get('tiktok_second_account') or settings.get('youtube_bot_account') or 'botalot')
        return name.strip().lstrip('@') or 'botalot'

    def _emit_bot_reply_to_desktop(self, settings: dict[str, Any], source_platform: str, response: str, source_channel: str = '') -> None:
        # botalot sendet Antworten selbst über Twitch/TikTok-Writer. Je nach
        # Plattform/Account kommt diese eigene Outbound-Zeile nicht zuverlässig
        # wieder über das normale Chatplugin ins Desktopwindow. Deshalb spiegeln
        # wir sie hier genau einmal mit der Ursprungsplattform als Quelle.
        if not as_bool(settings.get('show_bot_replies_in_desktop'), True):
            return
        platform = str(source_platform or '').strip().lower()
        if platform in {'tt', 'tiktok_live'}:
            platform = 'tiktok'
        if platform == 'twitch_chat':
            platform = 'twitch'
        if platform in {'youtube_live', 'youtube_chat', 'yt'}:
            platform = 'youtube'
        if platform == 'kick_chat':
            platform = 'kick'
        bot_name = self._bot_name_for_platform(settings, platform)
        self._emit_desktop_chat_message(platform, bot_name, response, source_channel, 'Bot-Antwort')

    def _should_read_platform(self, settings: dict[str, Any], platform: str) -> bool:
        p = platform.lower()
        if p in {'tiktok', 'tt', 'tiktok_live'}:
            return as_bool(settings.get('read_tiktok'), True)
        if p == 'twitch':
            return as_bool(settings.get('read_twitch'), True)
        if p in {'youtube', 'youtube_live', 'youtube_chat'}:
            return as_bool(settings.get('read_youtube'), True)
        if p in {'kick', 'kick_chat'}:
            return as_bool(settings.get('read_kick'), True)
        return True

    def _is_excluded_user(self, settings: dict[str, Any], username: str) -> bool:
        norm_user = username.strip().lstrip('@').lower()
        excluded_raw = str(settings.get('excluded_users') or '')
        excluded = {line.strip().lstrip('@').lower() for line in excluded_raw.replace(',', '\n').splitlines() if line.strip()}
        # Nur die manuell eingetragenen Namen werden fuer AI ignoriert.
        # Main-/Botaccounts werden nicht mehr automatisch auf die Blacklist gesetzt.
        return norm_user in excluded

    def _ensure_files(self) -> None:
        try:
            (DATA_DIR / 'triggers').mkdir(parents=True, exist_ok=True)
            (DATA_DIR / 'prompts').mkdir(parents=True, exist_ok=True)
            if not PROMPT_FILE.exists():
                PROMPT_FILE.write_text(DEFAULT_PROMPT + '\n', encoding='utf-8')
            if not TRIGGER_FILE.exists():
                TRIGGER_FILE.write_text('ursula\nursu\nursul\nursla\nursela\nursuhla\nursulla\nsula\n', encoding='utf-8')
        except Exception:
            pass

    def _log(self, message: str) -> None:
        host = self._host
        if host is not None:
            try:
                host.log(self.plugin_id, message)
            except Exception:
                pass


def create_plugin() -> ProviderPlugin:
    return BotalotPlugin()
