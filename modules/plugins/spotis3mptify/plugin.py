from __future__ import annotations

import importlib.util
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover
    QtCore = QtGui = QtWidgets = None  # type: ignore

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_API_PORT = 17891

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return PLUGIN_DIR / 'data'

DATA_DIR = _main_data_dir('spotis3mptify')
AUTH_DIR = DATA_DIR / 'auth'
CENTRAL_AUTH_DIR = DATA_DIR.parent / 'auth'
CONFIG_DIR = DATA_DIR / 'config'
NOWPLAYING_DIR = DATA_DIR / 'nowplaying'
COVERS_DIR = DATA_DIR / 'covers'
PLAYLISTS_DIR = DATA_DIR / 'playlists'
STATE_DIR = DATA_DIR / 'state'
EXPORT_DIR = DATA_DIR / 'export'
CERTS_DIR = DATA_DIR / 'certs'
YOUTUBE_DIR = DATA_DIR / 'youtube'
ASSETS_DIR = PLUGIN_DIR / 'assets'
CORE_FILE = PLUGIN_DIR / 'spotis3mptify_core.py'
LEGACY_TOKEN_FILE = PLUGIN_DIR / 'spotis3mptify_tokens.json'
LOCAL_CONFIG_FILE = CONFIG_DIR / 'spotis3mptify_plugin_config.json'
SRB_STATE_FILE = STATE_DIR / 'song_request_battle.json'

SRB_TEXT_DEFAULTS_DE = {
    'srb_text_started': '{challenger} fordert {opponent} heraus! {opponent}, schreibe {stop_command}. Du hast {seconds} Sekunden.',
    'srb_text_letter': '{opponent} hat gestoppt. Buchstabe: {letter}. Requeste jetzt mit {request_command} eine passende Band und einen Song!',
    'srb_text_wrong': '{opponent}: {artist} beginnt nicht mit {letter}. Versuche es erneut - noch {seconds} Sekunden.',
    'srb_text_winner': '{winner} gewinnt mit {artist} - {song} und erhält {reward} Requestpunkte!',
    'srb_text_timeout': 'Zeit abgelaufen! {winner} gewinnt und erhält {reward} Requestpunkte.',
    'srb_text_points': '{user} hat {points} Requestpunkte.',
    'srb_text_not_enough_points': '@{user}, du hast erst {points} von {required} benötigten Requestpunkten. Requeste zunächst normale Songs oder gewinne ein Battle, zu dem du herausgefordert wurdest.',
}

SRB_TEXT_DEFAULTS_EN = {
    'srb_text_started': '{challenger} challenges {opponent}! {opponent}, type {stop_command}. You have {seconds} seconds.',
    'srb_text_letter': '{opponent} stopped the timer. Letter: {letter}. Request a matching artist and song with {request_command} now!',
    'srb_text_wrong': '{opponent}: {artist} does not start with {letter}. Try again - {seconds} seconds left.',
    'srb_text_winner': '{winner} wins with {artist} - {song} and gets {reward} request points!',
    'srb_text_timeout': 'Time is up! {winner} wins and gets {reward} request points.',
    'srb_text_points': '{user} has {points} request points.',
    'srb_text_not_enough_points': '@{user}, you only have {points} of {required} required request points. Request normal songs first or win a battle you were challenged to.',
}

SRB_TEXT_DEFAULT_ALIASES = {
    'srb_text_started': {
        '{challenger} fordert {opponent} heraus! {opponent}, schreibe {stop_command}. Du hast {Sekunden} Sekunden.',
        '{challenger} fordert {opponent} heraus! {opponent}, schreibe {stop_command}. Du hast {seconds} seconds.',
    },
    'srb_text_letter': {
        '{opponent} hat gestoppt. Buchstabe: {letter}. Requeste jetzt mit {request_command} eine passende Band und einen Lied!',
        '{opponent} hat gestoppt. Buchstabe: {letter}. Requeste jetzt with {request_command} eine passende Band and einen Song!',
    },
    'srb_text_wrong': {
        '{opponent}: {artist} beginnt nicht mit {letter}. Versuche es erneut – noch {Sekunden} Sekunden.',
    },
    'srb_text_winner': {
        '{winner} gewinnt mit {artist} – {song} und erhält {reward} Requestpunkte!',
    },
}


def _ensure_data_dirs() -> None:
    for path in (DATA_DIR, AUTH_DIR, CENTRAL_AUTH_DIR, CONFIG_DIR, NOWPLAYING_DIR, COVERS_DIR, PLAYLISTS_DIR, STATE_DIR, EXPORT_DIR, CERTS_DIR, YOUTUBE_DIR):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def _move_legacy_file(src: Path, dst: Path) -> None:
    try:
        if not src.exists() or not src.is_file() or src.resolve() == dst.resolve():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            try:
                src.replace(dst)
                return
            except Exception:
                dst.write_bytes(src.read_bytes())
        try:
            if dst.exists() and src.exists():
                src.unlink()
        except Exception:
            pass
    except Exception:
        pass


def _migrate_legacy_runtime_files() -> None:
    _ensure_data_dirs()
    mapping = {
        AUTH_DIR: ('spotis3mptify_tokens.json', 'twitch_state_main.json', 'twitch_state_bot.json'),
        CONFIG_DIR: ('custom_overlay.json', 'spotis3mptify_plugin_config.json'),
        NOWPLAYING_DIR: ('nowplaying.json', 'nowplaying.txt', 'nowplaying_artist.txt', 'nowplaying_title.txt', 'nowplaying_album.txt', 'nowplaying_url.txt', 'nowplaying_provider.txt', 'nowplaying_color.txt'),
        COVERS_DIR: ('cover_latest_64.jpg', 'cover_latest_64.src', 'cover_latest_300.jpg', 'cover_latest_300.src', 'cover_latest_640.jpg', 'cover_latest_640.src', 'youtube_thumbnail.jpg', 'youtube_thumbnail.src'),
        PLAYLISTS_DIR: ('spotis3mptify_playlists.json',),
        STATE_DIR: ('spotis3mptify_recent.json', 'spotis3mptify_takeover.json', 'spotis3mptify_guard.json'),
        EXPORT_DIR: ('songrequests.txt',),
        CERTS_DIR: ('spotis3mptify_local_root_ca.crt', 'spotis3mptify_local_root_ca.key', 'localhost_https_cert.pem', 'localhost_https_key.pem'),
        YOUTUBE_DIR: ('youtube_debug.log', 'youtube_queue.json'),
    }
    for target_dir, names in mapping.items():
        for name in names:
            _move_legacy_file(DATA_DIR / name, target_dir / name)
            _move_legacy_file(PLUGIN_DIR / name, target_dir / name)


_migrate_legacy_runtime_files()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'ja', 'on', 'enabled', 'aktiv'}:
        return True
    if text in {'0', 'false', 'no', 'nein', 'off', 'disabled', 'aus', ''}:
        return False
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or str(value).strip() == '':
            return int(default)
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_text(value: Any) -> str:
    return str(value or '').strip()


def _normalize_default_text(value: Any) -> str:
    return str(value or '').strip().replace('–', '-').replace('  ', ' ').strip()


def _is_srb_default_text(key: str, value: Any) -> bool:
    text = _normalize_default_text(value)
    defaults = {
        _normalize_default_text(SRB_TEXT_DEFAULTS_DE.get(key)),
        _normalize_default_text(SRB_TEXT_DEFAULTS_EN.get(key)),
    }
    defaults.update(_normalize_default_text(item) for item in SRB_TEXT_DEFAULT_ALIASES.get(key, set()))
    return text in defaults


def _apply_language_default_texts(settings: dict[str, Any], language: str) -> dict[str, Any]:
    target = SRB_TEXT_DEFAULTS_EN if str(language or '').lower().startswith('en') else SRB_TEXT_DEFAULTS_DE
    for key, default_value in target.items():
        if not str(settings.get(key) or '').strip() or _is_srb_default_text(key, settings.get(key)):
            settings[key] = default_value
    return settings


def _spotify_expires_at(data: dict[str, Any]) -> float:
    try:
        explicit = float(data.get('expires_at') or 0)
    except Exception:
        explicit = 0.0
    if explicit > 0:
        return explicit
    try:
        saved_at = float(data.get('saved_at') or 0)
        expires_in = float(data.get('expires_in') or 0)
        if saved_at > 0 and expires_in > 0:
            return saved_at + expires_in
    except Exception:
        pass
    return 0.0




def _format_cooldown_minutes(seconds: Any) -> str:
    try:
        total = max(0, int(float(str(seconds).strip())))
    except Exception:
        total = 0
    minutes = total // 60
    secs = total % 60
    return f'{minutes}:{secs:02d} min'


def _friendly_sr_error(error: Any) -> str:
    err = str(error or '').strip()
    if err.upper().startswith('RATELIMIT:'):
        retry = err.split(':', 1)[1].strip()
        return f'This song is on cooldown for {_format_cooldown_minutes(retry)}. Please choose another song.'
    return err or 'Request failed'


def _extract_service_command(text: str) -> str:
    raw = _safe_text(text)
    if not raw:
        return ''
    low = raw.lower().strip()
    if raw.lstrip().startswith('!'):
        return raw.strip()
    for cmd in ('!srpoints', '!srb', '!stop', '!sr+', '!sr', '!yt'):
        if low == cmd or low.startswith(cmd + ' '):
            return raw.strip()
    mention_match = re.search(r'(?i)(?:^|\s)@\S+\s+(!(?:srpoints|srb|stop|sr\+?|yt)(?:\s+.+)?$)', raw.strip())
    if mention_match:
        return mention_match.group(1).strip()
    # Accept old bridge text like "Name from TT: !sr song" but only keep the
    # actual command, never the bridge label.
    match = re.search(r'(?i)(?:^|:\s)(!(?:srpoints|srb|stop|sr\+?|yt)(?:\s+.+)?$)', raw.strip())
    return match.group(1).strip() if match else ''


def _clean_platform(value: Any) -> str:
    p = str(value or '').strip().lower()
    if p in {'tt', 'tiktok_chat'}:
        return 'tiktok'
    if p in {'tw', 'twitch_chat'}:
        return 'twitch'
    if p in {'yt', 'youtube_live'}:
        return 'youtube'
    if p in {'kick_chat'}:
        return 'kick'
    return p


def _clean_request_user(value: Any, platform: str = '') -> str:
    name = str(value or '').strip()
    if not name:
        return 'someone'
    name = re.sub(r'[\u200b-\u200f\u2060\ufeff\u034f]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'^(?:@+)', '', name).strip()

    # Desktop/bridge labels like "Name@TW", "Name @ TT" or "Name - Twitch" must not become new users.
    name = re.sub(r'\s*@\s*(?:tw|tt|yt|twitch|tiktok|youtube|kick)$', '', name, flags=re.I).strip()
    name = re.sub(r'\s*[-_/|]\s*(?:tw|tt|yt|twitch|tiktok|youtube|kick)$', '', name, flags=re.I).strip()

    # Old bridge builds sometimes glued the platform suffix directly to the name, e.g. usernameTW.
    p = _clean_platform(platform)
    suffixes = {'twitch': ('tw', 'twitch'), 'tiktok': ('tt', 'tiktok'), 'youtube': ('yt', 'youtube'), 'kick': ('kick',)}.get(p, ())
    low = name.lower()
    for suf in suffixes:
        if len(low) > len(suf) + 2 and low.endswith(suf):
            name = name[:-len(suf)].strip(' -_/@|')
            break

    return (name[:50].strip() or 'someone')


def _split_list(raw: Any) -> set[str]:
    text = str(raw or '').strip()
    if not text:
        return set()
    return {x.strip().lower() for x in re.split(r'[;,\s]+', text) if x.strip()}


def _asset_image_options() -> list[dict[str, str]]:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, str]] = [{'label': 'Kein Playlist-Cover', 'value': ''}]
    try:
        files = []
        for ext in ('*.jpg', '*.jpeg'):
            files.extend(ASSETS_DIR.glob(ext))
            files.extend(ASSETS_DIR.glob(ext.upper()))
        seen = set()
        for path in sorted(files, key=lambda x: x.name.lower()):
            name = path.name
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            items.append({'label': name, 'value': name})
    except Exception:
        pass
    return items


def _selected_asset_image(name: Any) -> str:
    n = Path(str(name or '').strip()).name
    if not n:
        return ''
    if not n.lower().endswith(('.jpg', '.jpeg')):
        return ''
    p = ASSETS_DIR / n
    try:
        return str(p) if p.exists() and p.is_file() else ''
    except Exception:
        return ''




def _asset_image_names() -> list[str]:
    opts = _asset_image_options()
    return [str(x.get('value') or '') for x in opts if str(x.get('value') or '').strip()]


def _load_local_config() -> dict[str, Any]:
    try:
        if LOCAL_CONFIG_FILE.exists():
            data = json.loads(LOCAL_CONFIG_FILE.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_local_config(data: dict[str, Any]) -> None:
    try:
        _migrate_legacy_runtime_files()
        LOCAL_CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

def _msg_get(msg: Any, *names: str, default: Any = '') -> Any:
    if isinstance(msg, dict):
        for name in names:
            if name in msg and msg.get(name) is not None:
                return msg.get(name)
        return default
    for name in names:
        try:
            value = getattr(msg, name)
            if value is not None:
                return value
        except Exception:
            pass
    return default


class _DashboardWindow(QtWidgets.QWidget if QtWidgets is not None else object):  # type: ignore[misc]
    def __init__(self, plugin: 'Spotis3mptifyPlugin') -> None:
        super().__init__()
        self.plugin = plugin
        self.setWindowTitle('spotis3mptify Dashboard')
        self.resize(720, 420)
        self.setMinimumSize(520, 320)
        self.setObjectName('appRoot')
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        top = QtWidgets.QHBoxLayout()
        self.cover = QtWidgets.QLabel()
        self.cover.setFixedSize(220, 220)
        self.cover.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.cover.setObjectName('coverPreview')
        self.cover.setStyleSheet('QLabel#coverPreview { border-radius: 12px; background: rgba(255,255,255,22); }')
        top.addWidget(self.cover)
        meta = QtWidgets.QVBoxLayout()
        self.status = QtWidgets.QLabel('Spotify')
        self.status.setObjectName('sectionNote')
        self.title = QtWidgets.QLabel('Noch kein Song')
        self.title.setWordWrap(True)
        f = self.title.font(); f.setPointSize(max(18, f.pointSize() + 6)); f.setBold(True); self.title.setFont(f)
        self.artist = QtWidgets.QLabel('')
        self.artist.setWordWrap(True)
        af = self.artist.font(); af.setPointSize(max(13, af.pointSize() + 2)); self.artist.setFont(af)
        self.url = QtWidgets.QLabel('')
        self.url.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url.setWordWrap(True)
        meta.addWidget(self.status)
        meta.addSpacing(8)
        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        meta.addStretch(1)
        meta.addWidget(self.url)
        top.addLayout(meta, 1)
        root.addLayout(top)
        row = QtWidgets.QHBoxLayout()
        self.overlay_url = QtWidgets.QLineEdit()
        self.overlay_url.setReadOnly(True)
        self.open_btn = QtWidgets.QPushButton('Browseranzeige Ã¶ffnen')
        self.open_btn.clicked.connect(self.plugin.open_overlay)
        row.addWidget(self.overlay_url, 1)
        row.addWidget(self.open_btn)
        root.addLayout(row)

        self.cover_box = QtWidgets.QGroupBox('User-Playlist Cover')
        cover_layout = QtWidgets.QVBoxLayout(self.cover_box)
        cover_row = QtWidgets.QHBoxLayout()
        self.playlist_cover_combo = QtWidgets.QComboBox()
        self.playlist_cover_combo.currentTextChanged.connect(self._cover_changed)
        self.reload_cover_btn = QtWidgets.QPushButton('Bilder neu laden')
        self.reload_cover_btn.clicked.connect(self._reload_cover_dropdown)
        self.asset_label = QtWidgets.QLabel('Bild aus assets:')
        cover_row.addWidget(self.asset_label)
        cover_row.addWidget(self.playlist_cover_combo, 1)
        cover_row.addWidget(self.reload_cover_btn)
        cover_layout.addLayout(cover_row)
        self.cover_note = QtWidgets.QLabel('Das Bild wird bei neu erstellten User-Playlists als Spotify-Cover gesetzt.')
        self.cover_note.setWordWrap(True)
        cover_layout.addWidget(self.cover_note)
        root.addWidget(self.cover_box)
        self.apply_language()
        self._reload_cover_dropdown()

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def apply_language(self) -> None:
        english = str(self.plugin._settings.get('_ui_language') or 'de').lower().startswith('en')
        self.title.setText('No song yet' if english else 'Noch kein Song')
        self.open_btn.setText('Open browser view' if english else 'Browseranzeige öffnen')
        self.cover_box.setTitle('User playlist cover' if english else 'Cover der Benutzer-Playlist')
        self.reload_cover_btn.setText('Reload images' if english else 'Bilder neu laden')
        self.asset_label.setText('Image from assets:' if english else 'Bild aus Assets:')
        self.cover_note.setText('The image is used as the Spotify cover for newly created user playlists.' if english else 'Das Bild wird bei neu erstellten Benutzer-Playlists als Spotify-Cover gesetzt.')

    def _reload_cover_dropdown(self) -> None:
        try:
            current = str((self.plugin._effective_settings()).get('playlist_cover_image') or 'pl_cover.jpg')
        except Exception:
            current = 'pl_cover.jpg'
        try:
            self.playlist_cover_combo.blockSignals(True)
            self.playlist_cover_combo.clear()
            names = _asset_image_names()
            if not names:
                self.playlist_cover_combo.addItem('No .jpg/.jpeg files found in assets')
                self.playlist_cover_combo.setEnabled(False)
            else:
                self.playlist_cover_combo.setEnabled(True)
                for name in names:
                    self.playlist_cover_combo.addItem(name)
                idx = self.playlist_cover_combo.findText(current)
                if idx < 0:
                    idx = self.playlist_cover_combo.findText('pl_cover.jpg')
                if idx >= 0:
                    self.playlist_cover_combo.setCurrentIndex(idx)
            self.playlist_cover_combo.blockSignals(False)
        except Exception:
            pass

    def _cover_changed(self, name: str) -> None:
        name = str(name or '').strip()
        if not name or not name.lower().endswith(('.jpg', '.jpeg')):
            return
        self.plugin.set_playlist_cover_image(name)
        english = str(self.plugin._settings.get('_ui_language') or 'de').lower().startswith('en')
        self.cover_note.setText((f'Active: {name} · used for new user playlists.' if english else f'Aktiv: {name} · wird bei neuen Benutzer-Playlists gesetzt.'))

    def refresh(self) -> None:
        data = self.plugin.current_nowplaying()
        title = str(data.get('title') or '').strip()
        artist = str(data.get('artist') or '').strip()
        provider = str(data.get('provider') or 'spotify').strip()
        playing = bool(data.get('is_playing'))
        self.status.setText(('â–¶ ' if playing else 'â¸ ') + provider.upper())
        english = str(self.plugin._settings.get('_ui_language') or 'de').lower().startswith('en')
        self.title.setText(title or ('No song yet' if english else 'Noch kein Song'))
        self.artist.setText(artist or '')
        self.url.setText(str(data.get('url') or ''))
        self.overlay_url.setText(self.plugin.overlay_url())
        cover_path = self.plugin.cover_path()
        pix = QtGui.QPixmap(str(cover_path)) if cover_path and cover_path.exists() else QtGui.QPixmap()
        if not pix.isNull():
            pix = pix.scaled(self.cover.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
            self.cover.setPixmap(pix)
        else:
            self.cover.setText('Kein Cover')


class Spotis3mptifyPlugin(ProviderPlugin):
    plugin_id = 'spotis3mptify'
    display_name = 'spotis3mptify'
    version = '0.19'
    description = 'Spotify songrequests + Browseranzeige als godisalotachat Plugin.'

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._core = None
        self._running = False
        self._recent_msg_keys: dict[str, float] = {}
        self._dashboard = None
        self._lock = threading.RLock()
        self._srb_state: dict[str, Any] = {'points': {}, 'battle': None}
        self._srb_stop = threading.Event()
        self._srb_thread: threading.Thread | None = None

    def settings_schema(self) -> list[dict[str, Any]]:
        return [
            {'key': 'enabled', 'type': 'bool', 'label': 'Plugin aktiv', 'label_en': 'Plugin enabled', 'default': True, 'tab': 'Allgemein', 'tab_en': 'General'},
            {'key': 'autoconnect', 'type': 'bool', 'label': 'Beim App-Start automatisch verbinden', 'label_en': 'Connect automatically on app start', 'default': True, 'tab': 'Allgemein', 'tab_en': 'General'},
            {'key': 'button_open_dashboard', 'type': 'button', 'label': 'Dashboard', 'button_text': 'Dashboard mit Cover oeffnen', 'button_text_en': 'Open dashboard with cover', 'tab': 'Allgemein', 'tab_en': 'General'},
            {'key': 'button_open_overlay', 'type': 'button', 'label': 'Browseranzeige', 'label_en': 'Browser overlay', 'button_text': 'Browseranzeige oeffnen', 'button_text_en': 'Open browser overlay', 'tab': 'Allgemein', 'tab_en': 'General'},
            {'key': 'port', 'type': 'number', 'label': 'Browser/API Port', 'default': DEFAULT_API_PORT, 'min': 1024, 'max': 65535, 'tab': 'Browser'},
            {'key': 'custom_overlay_url', 'label': 'Browseranzeige URL', 'label_en': 'Browser overlay URL', 'readonly': True, 'tab': 'Browser'},
            {'key': 'poll_ms', 'type': 'number', 'label': 'NowPlaying Poll ms', 'default': 2000, 'min': 500, 'max': 60000, 'tab': 'Browser'},
            {'key': 'cover_image_size', 'type': 'number', 'label': 'Covergroesse Datei', 'label_en': 'Cover file size', 'default': 640, 'min': 64, 'max': 640, 'tab': 'Browser'},
            {'key': 'sr_command', 'label': 'Songrequest Befehl', 'label_en': 'Song request command', 'default': '!sr', 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'srplus_command', 'label': 'SR+ Befehl', 'label_en': 'SR+ command', 'default': '!sr+', 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'reply_enabled', 'type': 'bool', 'label': 'Antwort in Ursprungsplattform senden', 'label_en': 'Reply on source platform', 'default': True, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'broadcast_queue_reply', 'type': 'bool', 'label': 'Queue-Antwort auf andere Plattformen spiegeln', 'label_en': 'Mirror queue reply to other platforms', 'default': True, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'allowed_platforms', 'label': 'Erlaubte Plattformen leer=alle', 'label_en': 'Allowed platforms empty=all', 'placeholder': 'twitch,tiktok,youtube,kick', 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'cooldown_minutes', 'type': 'number', 'label': 'Link Cooldown Minuten', 'label_en': 'Link cooldown minutes', 'default': 60, 'min': 0, 'max': 10080, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'playlist_prefix', 'label': 'User-Playlist Prefix', 'label_en': 'User playlist prefix', 'default': 'Spotis3mptify - ', 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'playlist_cover_enabled', 'type': 'bool', 'label': 'Playlist-Cover setzen', 'label_en': 'Set playlist cover', 'default': True, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'playlist_cover_image', 'label': 'Playlist-Cover Datei (.jpg aus assets)', 'label_en': 'Playlist cover file (.jpg from assets)', 'default': 'pl_cover.jpg', 'placeholder': 'pl_cover.jpg', 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'playlist_cover_assets_hint', 'label': 'Gefundene Coverbilder', 'label_en': 'Found cover images', 'readonly': True, 'default': ', '.join(_asset_image_names()) or 'Keine .jpg/.jpeg in assets', 'default_en': ', '.join(_asset_image_names()) or 'No .jpg/.jpeg files in assets', 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'play_now', 'type': 'bool', 'label': 'Request sofort spielen', 'label_en': 'Play request immediately', 'default': False, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'queue_then_skip', 'type': 'bool', 'label': 'In Queue + direkt skippen', 'label_en': 'Queue and skip immediately', 'default': False, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'repeat_guard', 'type': 'bool', 'label': 'Repeat Track automatisch ausschalten', 'label_en': 'Disable repeat track automatically', 'default': True, 'tab': 'Anfragen', 'tab_en': 'Requests'},
            {'key': 'srb_enabled', 'type': 'bool', 'label': 'Song Request Battle aktiv', 'label_en': 'Song Request Battle enabled', 'default': True, 'tab': 'SR Battle'},
            {'key': 'srb_broadcast_enabled', 'type': 'bool', 'label': 'Battle-Nachrichten auf allen Plattformen senden', 'label_en': 'Send battle messages to all platforms', 'default': True, 'tab': 'SR Battle'},
            {'key': 'srb_test_enabled', 'type': 'bool', 'label': 'Testablauf mit !srb @testen erlauben', 'label_en': 'Allow test flow with !srb @testen', 'default': False, 'tab': 'SR Battle'},
            {'key': 'srb_command', 'label': 'Battle-Befehl', 'label_en': 'Battle command', 'default': '!srb', 'tab': 'SR Battle'},
            {'key': 'srb_stop_command', 'label': 'Stop-Befehl', 'label_en': 'Stop command', 'default': '!stop', 'tab': 'SR Battle'},
            {'key': 'srb_points_command', 'label': 'Punkte-Befehl', 'label_en': 'Points command', 'default': '!srpoints', 'tab': 'SR Battle'},
            {'key': 'srb_required_points', 'type': 'number', 'label': 'Benötigte Punkte', 'label_en': 'Required points', 'default': 3, 'min': 0, 'max': 1000, 'tab': 'SR Battle'},
            {'key': 'srb_start_cost', 'type': 'number', 'label': 'Kosten beim Start', 'label_en': 'Start cost', 'default': 2, 'min': 0, 'max': 1000, 'tab': 'SR Battle'},
            {'key': 'srb_request_points', 'type': 'number', 'label': 'Punkte pro normalem Request', 'label_en': 'Points per normal request', 'default': 1, 'min': 0, 'max': 1000, 'tab': 'SR Battle'},
            {'key': 'srb_win_points', 'type': 'number', 'label': 'Punkte für Gewinner', 'label_en': 'Winner points', 'default': 3, 'min': 0, 'max': 1000, 'tab': 'SR Battle'},
            {'key': 'srb_stop_seconds', 'type': 'number', 'label': 'Zeit bis Stop (Sek.)', 'label_en': 'Stop time (sec.)', 'default': 30, 'min': 5, 'max': 600, 'tab': 'SR Battle'},
            {'key': 'srb_request_seconds', 'type': 'number', 'label': 'Zeit für Request (Sek.)', 'label_en': 'Request time (sec.)', 'default': 60, 'min': 5, 'max': 1800, 'tab': 'SR Battle'},
            {'key': 'srb_text_started', 'type': 'template', 'label': 'Text: Battle gestartet', 'label_en': 'Text: battle started', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_started'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_started'], 'tokens': ['{user}', '{challenger}', '{opponent}', '{points}', '{cost}', '{seconds}', '{stop_command}', '{request_command}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srb_text_letter', 'type': 'template', 'label': 'Text: Buchstabe', 'label_en': 'Text: letter', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_letter'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_letter'], 'tokens': ['{user}', '{challenger}', '{opponent}', '{letter}', '{seconds}', '{stop_command}', '{request_command}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srb_text_wrong', 'type': 'template', 'label': 'Text: falscher Kuenstler', 'label_en': 'Text: wrong artist', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_wrong'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_wrong'], 'tokens': ['{user}', '{challenger}', '{opponent}', '{letter}', '{artist}', '{song}', '{seconds}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srb_text_winner', 'type': 'template', 'label': 'Text: gewonnen', 'label_en': 'Text: winner', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_winner'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_winner'], 'tokens': ['{user}', '{challenger}', '{opponent}', '{winner}', '{loser}', '{letter}', '{artist}', '{song}', '{points}', '{reward}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srb_text_timeout', 'type': 'template', 'label': 'Text: Zeit abgelaufen', 'label_en': 'Text: timeout', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_timeout'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_timeout'], 'tokens': ['{user}', '{challenger}', '{opponent}', '{winner}', '{loser}', '{letter}', '{points}', '{reward}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srb_text_points', 'type': 'template', 'label': 'Text: Punktestand', 'label_en': 'Text: points', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_points'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_points'], 'tokens': ['{user}', '{points}', '{required}', '{cost}', '{reward}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srb_text_not_enough_points', 'type': 'template', 'label': 'Text: nicht genug Punkte', 'label_en': 'Text: not enough points', 'default': SRB_TEXT_DEFAULTS_DE['srb_text_not_enough_points'], 'default_en': SRB_TEXT_DEFAULTS_EN['srb_text_not_enough_points'], 'tokens': ['{user}', '{points}', '{required}', '{cost}', '{reward}', '{request_command}'], 'wide': True, 'tab': 'SR Battle Texte', 'tab_en': 'SR Battle Texts'},
            {'key': 'srplus_duration_min', 'type': 'number', 'label': 'SR+ Minuten', 'label_en': 'SR+ minutes', 'default': 15, 'min': 1, 'max': 240, 'tab': 'SR+'},
            {'key': 'srplus_once_per_stream', 'type': 'bool', 'label': 'SR+ nur einmal pro Stream', 'label_en': 'SR+ only once per stream', 'default': True, 'tab': 'SR+'},
            {'key': 'srplus_shuffle', 'type': 'bool', 'label': 'SR+ Shuffle', 'default': True, 'tab': 'SR+'},
            {'key': 'srplus_allowed_platforms', 'label': 'SR+ Plattformen leer=alle', 'label_en': 'SR+ platforms empty=all', 'placeholder': 'twitch,tiktok,youtube,kick', 'tab': 'SR+'},
            {'key': 'srplus_allowed_users', 'label': 'SR+ User leer=alle', 'label_en': 'SR+ users empty=all', 'placeholder': 'username1,username2', 'tab': 'SR+'},
            {'key': 'log_verbose', 'type': 'bool', 'label': 'Ausfuehrlich loggen', 'label_en': 'Verbose logging', 'default': True, 'tab': 'Protokolle', 'tab_en': 'Logs'},
        ]

    def default_settings(self) -> dict[str, Any]:
        return {
            'enabled': True,
            'autoconnect': True,
            'client_id': '',
            'client_secret': '',
            'redirect_uri': '',
            'port': DEFAULT_API_PORT,
            'custom_overlay_url': f'http://127.0.0.1:{DEFAULT_API_PORT}/customoverlay',
            'poll_ms': 2000,
            'cover_image_size': 640,
            'sr_command': '!sr',
            'srplus_command': '!sr+',
            'reply_enabled': True,
            'broadcast_queue_reply': True,
            'allowed_platforms': '',
            'cooldown_minutes': 60,
            'playlist_prefix': 'Spotis3mptify - ',
            'playlist_cover_enabled': True,
            'playlist_cover_image': 'pl_cover.jpg',
            'playlist_cover_assets_hint': ', '.join(_asset_image_names()) or 'Keine .jpg/.jpeg in assets',
            'play_now': False,
            'queue_then_skip': False,
            'repeat_guard': True,
            'srb_enabled': True,
            'srb_broadcast_enabled': True,
            'srb_test_enabled': False,
            'srb_command': '!srb',
            'srb_stop_command': '!stop',
            'srb_points_command': '!srpoints',
            'srb_required_points': 3,
            'srb_start_cost': 2,
            'srb_request_points': 1,
            'srb_win_points': 3,
            'srb_stop_seconds': 30,
            'srb_request_seconds': 60,
            'srb_text_started': SRB_TEXT_DEFAULTS_DE['srb_text_started'],
            'srb_text_letter': SRB_TEXT_DEFAULTS_DE['srb_text_letter'],
            'srb_text_wrong': SRB_TEXT_DEFAULTS_DE['srb_text_wrong'],
            'srb_text_winner': SRB_TEXT_DEFAULTS_DE['srb_text_winner'],
            'srb_text_timeout': SRB_TEXT_DEFAULTS_DE['srb_text_timeout'],
            'srb_text_points': SRB_TEXT_DEFAULTS_DE['srb_text_points'],
            'srb_text_not_enough_points': SRB_TEXT_DEFAULTS_DE['srb_text_not_enough_points'],
            'srplus_duration_min': 15,
            'srplus_once_per_stream': True,
            'srplus_shuffle': True,
            'srplus_allowed_platforms': '',
            'srplus_allowed_users': '',
            'log_verbose': True,
        }

    def _log(self, msg: str) -> None:
        try:
            if self._host:
                self._host.log(self.plugin_id, msg)
        except Exception:
            pass

    def _load_core(self):
        if self._core is not None:
            return self._core
        spec = importlib.util.spec_from_file_location('spotis3mptify_plugin_core', CORE_FILE)
        if not spec or not spec.loader:
            raise RuntimeError('spotis3mptify_core.py konnte nicht geladen werden')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._core = module
        return module

    def _effective_settings(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(settings or self._settings or {})
        local = _load_local_config()
        # The dashboard selection is authoritative because godisalotachat's generic settings UI
        # does not render a real dropdown reliably in all builds.
        if local.get('playlist_cover_image'):
            merged['playlist_cover_image'] = local.get('playlist_cover_image')
        if 'playlist_cover_enabled' in local:
            merged['playlist_cover_enabled'] = local.get('playlist_cover_enabled')
        spotify = self._host_platform_settings('spotify')
        if spotify:
            merged['client_id'] = _safe_text(spotify.get('client_id'))
            merged['client_secret'] = _safe_text(spotify.get('client_secret'))
            merged['redirect_uri'] = _safe_text(spotify.get('redirect_uri'))
            merged['spotify_access_token'] = _safe_text(spotify.get('access_token'))
            merged['spotify_refresh_token'] = _safe_text(spotify.get('refresh_token'))
            merged['spotify_expires_at'] = _spotify_expires_at(spotify)
            merged['spotify_scope'] = _safe_text(spotify.get('scope') or spotify.get('scopes'))
            merged['autoconnect'] = _as_bool(spotify.get('autoconnect'), _as_bool(merged.get('autoconnect'), True))
        return _apply_language_default_texts(merged, str(merged.get('_ui_language') or self._settings.get('_ui_language') or 'de'))

    def normalize_settings(self, settings: dict[str, Any], language: str | None = None) -> dict[str, Any]:
        merged = dict(settings or {})
        lang = str(language or merged.get('_ui_language') or self._settings.get('_ui_language') or 'de')
        return _apply_language_default_texts(merged, lang)

    def _host_platform_settings(self, platform: str) -> dict[str, Any]:
        host = self._host
        if host is None:
            return {}
        for name in ('platform_settings', 'get_platform_settings'):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    data = fn(platform)
                    if isinstance(data, dict):
                        return dict(data)
                except Exception:
                    pass
        return {}

    def set_playlist_cover_image(self, filename: str) -> None:
        filename = Path(str(filename or '').strip()).name
        if not filename.lower().endswith(('.jpg', '.jpeg')):
            return
        if not (ASSETS_DIR / filename).exists():
            self._log(f'Playlist-Cover nicht gefunden: assets/{filename}')
            return
        local = _load_local_config()
        local['playlist_cover_image'] = filename
        local['playlist_cover_enabled'] = True
        _save_local_config(local)
        self._settings['playlist_cover_image'] = filename
        self._settings['playlist_cover_enabled'] = True
        try:
            if self._core is not None:
                self._core.apply_settings(self._merged_config(self._settings))
        except Exception as exc:
            self._log(f'Playlist-Cover konnte nicht direkt Ã¼bernommen werden: {exc}')
        self._log(f'Playlist-Cover gewÃ¤hlt: assets/{filename}')

    def _merged_config(self, settings: dict[str, Any]) -> dict[str, Any]:
        _migrate_legacy_runtime_files()
        port = int(settings.get('port') or DEFAULT_API_PORT)
        if port == 5173:
            port = DEFAULT_API_PORT
            settings['port'] = port
        return {
            'enabled': _as_bool(settings.get('enabled'), True),
            'ui_language': str(settings.get('_ui_language') or 'de'),
            'main_ui_base': str(settings.get('_main_ui_base') or ''),
            'client_id': _safe_text(settings.get('client_id')),
            'client_secret': _safe_text(settings.get('client_secret')),
            'redirect_uri': _safe_text(settings.get('redirect_uri')),
            'spotify_access_token': _safe_text(settings.get('spotify_access_token')),
            'spotify_refresh_token': _safe_text(settings.get('spotify_refresh_token')),
            'spotify_expires_at': settings.get('spotify_expires_at') or 0,
            'spotify_scope': _safe_text(settings.get('spotify_scope')),
            'port': port,
            'data_dir': str(DATA_DIR),
            'tokens_dir': str(AUTH_DIR),
            'auth_dir': str(AUTH_DIR),
            'central_spotify_token_file': str(CENTRAL_AUTH_DIR / 'spotify_main.json'),
            'config_dir': str(CONFIG_DIR),
            'nowplaying_dir': str(NOWPLAYING_DIR),
            'cover_dir': str(COVERS_DIR),
            'playlist_dir': str(PLAYLISTS_DIR),
            'state_dir': str(STATE_DIR),
            'export_dir': str(EXPORT_DIR),
            'cert_dir': str(CERTS_DIR),
            'youtube_dir': str(YOUTUBE_DIR),
            'external_sr_file': str(EXPORT_DIR / 'songrequests.txt'),
            'shared_secret': '',
            'cooldown_minutes': int(settings.get('cooldown_minutes') or 60),
            'playlist_prefix': str(settings.get('playlist_prefix') or 'Spotis3mptify - '),
            'playlist_cover_enabled': _as_bool(settings.get('playlist_cover_enabled'), True),
            'playlist_cover_file': _selected_asset_image(settings.get('playlist_cover_image') or 'pl_cover.jpg'),
            'repeat_guard': _as_bool(settings.get('repeat_guard'), True),
            'play_now': _as_bool(settings.get('play_now'), False),
            'queue_then_skip': _as_bool(settings.get('queue_then_skip'), False),
            'srplus_duration_min': int(settings.get('srplus_duration_min') or 15),
            'srplus_once_per_stream': _as_bool(settings.get('srplus_once_per_stream'), True),
            'srplus_shuffle': _as_bool(settings.get('srplus_shuffle'), True),
            'nowplaying_enable_files': True,
            'poll_ms': int(settings.get('poll_ms') or 2000),
            'cover_image_size': int(settings.get('cover_image_size') or 640),
            'log_verbose': _as_bool(settings.get('log_verbose'), True),
            'log_np_on_change': False,
            'twitch_listen': False,
            'twitch_reply': False,
            'sr_source': 'twitch',
            'youtube_enabled': False,
            'youtube_cmd': '',
            'obs_ws_enabled': False,
            'async_playlist_add': False,
        }

    def set_ui_language(self, language: str) -> None:
        self._settings['_ui_language'] = 'en' if str(language or '').lower().startswith('en') else 'de'
        _apply_language_default_texts(self._settings, self._settings['_ui_language'])
        if self._core is not None:
            try:
                self._core.apply_settings(self._merged_config(self._settings))
            except Exception as exc:
                self._log(f'Language update failed: {exc}')
        if self._dashboard is not None:
            try:
                self._dashboard.apply_language()
            except Exception as exc:
                self._log(f'Dashboard language update failed: {exc}')

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._settings = self._effective_settings(dict(settings or {}))
        if not _as_bool(self._settings.get('enabled'), True):
            host.set_status(self.plugin_id, PluginStatus('disabled', 'Disabled'))
            return
        if not _as_bool(self._settings.get('autoconnect'), True):
            host.set_status(self.plugin_id, PluginStatus('stopped', 'Autoconnect off'))
            return
        core = self._load_core()
        core.set_logger(lambda level, line: self._log(str(line)))
        cfg = self._merged_config(self._settings)
        try:
            if self._running:
                core.stop_server()
                self._running = False
        except Exception:
            pass
        core.apply_settings(cfg)
        core.start_server()
        self._running = True
        url = self.overlay_url()
        self._settings['custom_overlay_url'] = url
        host.set_status(self.plugin_id, PluginStatus('connected', f'Overlay {url}'))
        self._log(f'Plugin started - Spotify-only - Overlay {url}')
        self._srb_load()
        self._srb_stop.clear()
        if self._srb_thread is None or not self._srb_thread.is_alive():
            self._srb_thread = threading.Thread(target=self._srb_watch, name='spotis3mptify-srb', daemon=True)
            self._srb_thread.start()

    def stop(self) -> None:
        self._srb_stop.set()
        try:
            if self._core is not None:
                self._core.stop_server()
        except Exception as exc:
            self._log(f'Stop failed: {exc}')
        self._running = False
        if self._host:
            self._host.set_status(self.plugin_id, PluginStatus('disconnected', 'Stopped'))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        try:
            if settings:
                merged = dict(self._settings or {})
                merged.update(settings)
                self._settings = self._effective_settings(merged)
            core = self._load_core()
            try:
                core.apply_settings(self._merged_config(self._settings))
            except Exception:
                pass
            h = core.get_health()
            if h.get('spotify'):
                scope_text = str(h.get('spotify_token_scope') or '').strip()
                required = {'playlist-modify-private', 'playlist-modify-public', 'playlist-read-private', 'ugc-image-upload'}
                if scope_text:
                    missing = sorted(x for x in required if x not in set(scope_text.split()))
                    if missing:
                        return False, 'Spotify connected, but token scope is missing: ' + ', '.join(missing) + ' - please run OAuth again'
                return True, f"Spotify connected - Overlay {self.overlay_url()}"
            return False, "Spotify not connected"
        except Exception as exc:
            return False, str(exc)

    def overlay_url(self) -> str:
        port = int((self._settings or {}).get('port') or DEFAULT_API_PORT)
        if port == 5173:
            port = DEFAULT_API_PORT
        return f'http://127.0.0.1:{port}/customoverlay'

    def open_overlay(self) -> None:
        try:
            webbrowser.open(self.overlay_url())
        except Exception as exc:
            self._log(f'Browser overlay could not be opened: {exc}')

    def open_login(self) -> None:
        self._log('Spotify login is managed centrally in the main tool under Platforms.')

    def current_nowplaying(self) -> dict[str, Any]:
        try:
            if self._core is not None:
                return dict(self._core._overlay_current())
        except Exception:
            pass
        try:
            path = NOWPLAYING_DIR / 'nowplaying.json'
            if path.exists():
                return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
        return {}

    def cover_path(self) -> Path | None:
        try:
            size = int((self._settings or {}).get('cover_image_size') or 640)
            p = COVERS_DIR / f'cover_latest_{size}.jpg'
            if p.exists():
                return p
            p = COVERS_DIR / 'cover_latest_640.jpg'
            if p.exists():
                return p
            p = COVERS_DIR / 'cover_latest_300.jpg'
            if p.exists():
                return p
        except Exception:
            pass
        return None

    def _allowed_platforms(self) -> set[str]:
        raw = str((self._settings or {}).get('allowed_platforms') or '').strip()
        if not raw:
            return set()
        return {_clean_platform(x) for x in re.split(r'[;,\s]+', raw) if _clean_platform(x)}

    def _refresh_runtime_core_settings(self) -> None:
        try:
            effective = self._effective_settings(self._settings)
            self._settings.update(effective)
            if self._core is not None:
                self._core.apply_settings(self._merged_config(self._settings))
        except Exception as exc:
            self._log(f'Spotify Core-Settings konnten nicht aktualisiert werden: {exc}')

    def on_message(self, msg: Any) -> None:
        if not _as_bool((self._settings or {}).get('enabled'), True):
            return
        platform = _clean_platform(_msg_get(msg, 'platform', 'source_platform', default=''))
        if not platform:
            platform = _clean_platform(_msg_get(msg, 'source_plugin_id', default='')) or 'unknown'
        raw_username = _msg_get(msg, 'username', 'user', 'display_name', 'author', 'name', default='')
        username = _clean_request_user(raw_username, platform)
        text = _extract_service_command(_msg_get(msg, 'text', 'message', 'content', default=''))
        msg_type = _safe_text(_msg_get(msg, 'message_type', 'type', default='')).lower()
        if not text or msg_type in {'viewer_count', 'followers_count', 'metric', 'stats', 'status', 'live_status'}:
            return
        allowed = self._allowed_platforms()
        if allowed and platform not in allowed:
            return
        cmd = str(self._settings.get('sr_command') or '!sr').strip() or '!sr'
        cmd_plus = str(self._settings.get('srplus_command') or '!sr+').strip() or '!sr+'
        cmd_srb = str(self._settings.get('srb_command') or '!srb').strip() or '!srb'
        cmd_stop = str(self._settings.get('srb_stop_command') or '!stop').strip() or '!stop'
        cmd_points = str(self._settings.get('srb_points_command') or '!srpoints').strip() or '!srpoints'
        low = text.lower().strip()
        action = ''
        query = ''
        if low == cmd_stop.lower():
            action = 'srb_stop'
        elif low == cmd_points.lower() or low.startswith(cmd_points.lower() + ' '):
            action = 'srb_points'
        elif low == cmd_srb.lower() or low.startswith(cmd_srb.lower() + ' '):
            action = 'srb'
            query = text[len(cmd_srb):].strip()
        elif low == cmd_plus.lower() or low.startswith(cmd_plus.lower() + ' '):
            action = 'srplus'
            query = text[len(cmd_plus):].strip()
        elif low == cmd.lower() or low.startswith(cmd.lower() + ' '):
            action = 'sr'
            query = text[len(cmd):].strip()
        else:
            return
        self._log(f'Chat command erkannt: {action} von {username}@{platform} · query="{query}"')
        self._refresh_runtime_core_settings()
        key = f'{platform}|{username.lower()}|{text}'
        now = time.time()
        with self._lock:
            self._recent_msg_keys = {k: v for k, v in self._recent_msg_keys.items() if now - v < 8.0}
            if key in self._recent_msg_keys:
                return
            self._recent_msg_keys[key] = now
        if action == 'srb_stop':
            self._handle_srb_stop(platform, username)
        elif action == 'srb_points':
            self._handle_srb_points(platform, username)
        elif action == 'srb':
            self._handle_srb_start(platform, username, query)
        elif action == 'srplus':
            self._handle_srplus(platform, username)
        elif query:
            self._handle_sr(platform, username, query)
        else:
            self._reply(platform, f'@{username} bitte Song oder Spotify-Link nach {cmd} schreiben.')

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        port = int((self._settings or {}).get('port') or DEFAULT_API_PORT)
        if port == 5173:
            port = DEFAULT_API_PORT
        url = f'http://127.0.0.1:{port}{path}'
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode('utf-8', 'ignore') or '{}')

    @staticmethod
    def _srb_user_key(username: str) -> str:
        return _clean_request_user(username).casefold()

    def _srb_load(self) -> None:
        with self._lock:
            try:
                data = json.loads(SRB_STATE_FILE.read_text(encoding='utf-8')) if SRB_STATE_FILE.exists() else {}
            except Exception as exc:
                self._log(f'SR Battle state could not be loaded: {exc}')
                data = {}
            points = data.get('points') if isinstance(data.get('points'), dict) else {}
            battle = data.get('battle') if isinstance(data.get('battle'), dict) else None
            if isinstance(battle, dict) and battle.get('phase') == 'resolving':
                battle['phase'] = 'request'
                battle['deadline'] = time.time() + max(5, _as_int(self._settings.get('srb_request_seconds'), 60))
            self._srb_state = {'points': {str(k): max(0, int(v or 0)) for k, v in points.items()}, 'battle': battle}

    def _srb_save_locked(self) -> None:
        try:
            SRB_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SRB_STATE_FILE.with_suffix('.tmp')
            tmp.write_text(json.dumps(self._srb_state, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(SRB_STATE_FILE)
        except Exception as exc:
            self._log(f'SR Battle state could not be saved: {exc}')

    def _srb_points(self, username: str) -> int:
        with self._lock:
            return int((self._srb_state.get('points') or {}).get(self._srb_user_key(username), 0) or 0)

    def _srb_add_points(self, username: str, amount: int) -> int:
        key = self._srb_user_key(username)
        with self._lock:
            points = self._srb_state.setdefault('points', {})
            points[key] = max(0, int(points.get(key, 0) or 0) + int(amount))
            self._srb_save_locked()
            return int(points[key])

    def _srb_values(self, battle: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
        battle = battle or {}
        winner = str(extra.get('winner') or '')
        challenger = str(battle.get('challenger') or '')
        opponent = str(battle.get('opponent') or '')
        loser = opponent if winner and self._srb_user_key(winner) == self._srb_user_key(challenger) else challenger
        values: dict[str, Any] = {
            'user': extra.get('user') or winner or challenger,
            'challenger': challenger, 'opponent': opponent, 'winner': winner, 'loser': loser if winner else '',
            'letter': battle.get('letter') or '', 'artist': extra.get('artist') or '', 'song': extra.get('song') or '',
            'points': extra.get('points', ''), 'required': _as_int(self._settings.get('srb_required_points'), 3),
            'cost': _as_int(self._settings.get('srb_start_cost'), 2),
            'reward': _as_int(self._settings.get('srb_win_points'), 3),
            'seconds': extra.get('seconds', ''),
            'stop_command': str(self._settings.get('srb_stop_command') or '!stop'),
            'request_command': str(self._settings.get('sr_command') or '!sr'),
            'platform': battle.get('platform') or extra.get('platform') or '',
        }
        values.update(extra)
        return values

    def _srb_reply(self, platform: str, template_key: str, battle: dict[str, Any] | None = None, **extra: Any) -> None:
        default = str(self.default_settings().get(template_key) or '')
        template = str(self._settings.get(template_key) or default)
        values = self._srb_values(battle, platform=platform, **extra)
        try:
            message = template.format_map({k: str(v) for k, v in values.items()})
        except Exception as exc:
            self._log(f'SR Battle Textvorlage {template_key} ungueltig: {exc}')
            message = default.format_map({k: str(v) for k, v in values.items()})
        if message.strip():
            message = message.strip()
            self._reply(platform, message)
            self._broadcast_srb_reply(platform, message)

    def _handle_srb_points(self, platform: str, username: str) -> None:
        points = self._srb_points(username)
        self._srb_reply(platform, 'srb_text_points', user=username, points=points)

    def _srb_active_for_request(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            battle = self._srb_state.get('battle')
            if not isinstance(battle, dict) or battle.get('phase') != 'request':
                return None
            if self._srb_user_key(username) != str(battle.get('opponent_key') or ''):
                return None
            if float(battle.get('deadline') or 0) <= time.time():
                return None
            snapshot = dict(battle)
            battle['phase'] = 'resolving'
            self._srb_save_locked()
            return snapshot

    def _srb_resume_request(self, battle_snapshot: dict[str, Any] | None) -> None:
        if not battle_snapshot:
            return
        with self._lock:
            battle = self._srb_state.get('battle')
            if not isinstance(battle, dict) or battle.get('phase') != 'resolving':
                return
            if battle.get('started_at') != battle_snapshot.get('started_at'):
                return
            battle['phase'] = 'request'
            self._srb_save_locked()

    def _handle_srb_start(self, platform: str, username: str, target: str) -> None:
        if not _as_bool(self._settings.get('srb_enabled'), True):
            return
        target = _clean_request_user(target) if str(target or '').strip() else ''
        if not str(target or '').strip() or target == 'someone':
            points = self._srb_points(username)
            self._srb_reply(platform, 'srb_text_points', user=username, points=points)
            return
        challenger_key = self._srb_user_key(username)
        opponent_key = self._srb_user_key(target)
        is_test_target = opponent_key in {'test', 'testen'}
        test_mode = is_test_target and _as_bool(self._settings.get('srb_test_enabled'), False)
        if is_test_target and not test_mode:
            self._reply(platform, f'@{username} der SR-Battle-Testmodus ist deaktiviert.')
            return
        if test_mode:
            opponent_key = challenger_key
        elif challenger_key == opponent_key:
            self._reply(platform, f'@{username} du kannst dich nicht selbst herausfordern.')
            return
        required = max(0, _as_int(self._settings.get('srb_required_points'), 3))
        cost = max(0, _as_int(self._settings.get('srb_start_cost'), 2))
        stop_seconds = max(5, _as_int(self._settings.get('srb_stop_seconds'), 30))
        with self._lock:
            if isinstance(self._srb_state.get('battle'), dict):
                self._reply(platform, 'Es läuft bereits ein Song Request Battle.')
                return
            points = int(self._srb_state.setdefault('points', {}).get(challenger_key, 0) or 0)
            if not test_mode and points < required:
                self._srb_reply(platform, 'srb_text_not_enough_points', user=username,
                                points=points, required=required)
                return
            if not test_mode:
                self._srb_state['points'][challenger_key] = max(0, points - cost)
            started = time.time()
            battle = {'phase': 'stopping', 'challenger': username, 'challenger_key': challenger_key,
                      'opponent': target, 'opponent_key': opponent_key, 'platform': platform,
                      'started_at': started, 'deadline': started + stop_seconds, 'letter': '',
                      'test_mode': test_mode}
            self._srb_state['battle'] = battle
            self._srb_save_locked()
        self._srb_reply(platform, 'srb_text_started', battle, user=username,
                        points=points if test_mode else max(0, points - cost),
                        cost=0 if test_mode else cost, seconds=stop_seconds)
        if test_mode:
            self._reply(platform, f'@{username} Testmodus aktiv: Du übernimmst @test und schreibst selbst '
                                  f'{self._settings.get("srb_stop_command") or "!stop"}.')

    def _handle_srb_stop(self, platform: str, username: str) -> None:
        now = time.time()
        with self._lock:
            battle = self._srb_state.get('battle')
            if not isinstance(battle, dict) or battle.get('phase') != 'stopping':
                return
            if self._srb_user_key(username) != str(battle.get('opponent_key') or ''):
                return
            if float(battle.get('deadline') or 0) <= now:
                return
            elapsed = max(0.0, now - float(battle.get('started_at') or now))
            letter = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[int(elapsed / 0.20) % 26]
            request_seconds = max(5, _as_int(self._settings.get('srb_request_seconds'), 60))
            battle.update({'phase': 'request', 'letter': letter, 'deadline': now + request_seconds})
            self._srb_save_locked()
            snapshot = dict(battle)
        self._srb_reply(platform, 'srb_text_letter', snapshot, user=username, seconds=request_seconds)

    def _srb_finish(self, platform: str, winner: str, artist: str = '', song: str = '', timeout: bool = False) -> None:
        with self._lock:
            battle = self._srb_state.get('battle')
            if not isinstance(battle, dict):
                return
            snapshot = dict(battle)
            reward = max(0, _as_int(self._settings.get('srb_win_points'), 3))
            key = self._srb_user_key(winner)
            points = self._srb_state.setdefault('points', {})
            if snapshot.get('test_mode'):
                total = int(points.get(key, 0) or 0)
            else:
                points[key] = max(0, int(points.get(key, 0) or 0) + reward)
                total = int(points[key])
            self._srb_state['battle'] = None
            self._srb_save_locked()
        template = 'srb_text_timeout' if timeout else 'srb_text_winner'
        self._srb_reply(platform or str(snapshot.get('platform') or ''), template, snapshot,
                        user=winner, winner=winner, artist=artist, song=song, points=total,
                        reward=0 if snapshot.get('test_mode') else reward)
        if snapshot.get('test_mode'):
            self._reply(platform or str(snapshot.get('platform') or ''),
                        'SR-Battle-Test beendet - der Punktestand wurde nicht veraendert.')

    def _srb_watch(self) -> None:
        while not self._srb_stop.wait(1.0):
            expired: dict[str, Any] | None = None
            with self._lock:
                battle = self._srb_state.get('battle')
                if (isinstance(battle, dict) and battle.get('phase') in {'stopping', 'request'}
                        and float(battle.get('deadline') or 0) <= time.time()):
                    expired = dict(battle)
            if expired:
                self._srb_finish(str(expired.get('platform') or ''), str(expired.get('challenger') or ''), timeout=True)

    def _handle_sr(self, platform: str, username: str, query: str) -> None:
        try:
            battle = self._srb_active_for_request(username)
            payload = {'q': query, 'user': username}
            if battle:
                payload['expected_initial'] = battle.get('letter') or ''
            res = self._post_json('/sr', payload)
            if not res.get('ok'):
                err = str(res.get('error') or 'Request fehlgeschlagen')
                if err == 'BATTLE_INITIAL' and battle:
                    self._srb_resume_request(battle)
                    remaining = max(0, int(float(battle.get('deadline') or 0) - time.time()))
                    self._srb_reply(platform, 'srb_text_wrong', battle, user=username,
                                    artist=str(res.get('artist') or ''), song=str(res.get('title') or ''), seconds=remaining)
                    return
                self._srb_resume_request(battle)
                self._reply(platform, f'@{username} {_friendly_sr_error(err)}')
                self._log(f'SR failed: {username}@{platform} -> {query} - {err}')
                return
            title = str(res.get('title') or '').strip()
            artist = str(res.get('artist') or '').strip()
            msg = f'@{username} queued: {artist} - {title}'.strip()
            self._reply(platform, msg)
            self._broadcast_queue_reply(platform, msg)
            self._log(f'SR OK: {username}@{platform} -> {artist} - {title}')
            if battle:
                self._srb_finish(platform, winner=username, artist=artist, song=title, timeout=False)
            else:
                request_points = max(0, _as_int(self._settings.get('srb_request_points'), 1))
                self._srb_add_points(username, request_points)
        except urllib.error.HTTPError as exc:
            self._srb_resume_request(locals().get('battle'))
            body = ''
            try:
                body = exc.read().decode('utf-8', 'ignore')
            except Exception:
                pass
            if exc.code == 401:
                msg = 'Spotify ist noch nicht autorisiert. Bitte im Haupttool Spotify neu verbinden.'
            else:
                msg = body or f'HTTP {exc.code}'
            self._reply(platform, f'@{username} {msg}')
            self._log(f'SR HTTP error: {msg}')
        except Exception as exc:
            self._srb_resume_request(locals().get('battle'))
            self._reply(platform, f'@{username} Songrequest Fehler: {exc}')
            self._log(f'SR error: {exc}')

    def _srplus_allowed(self, platform: str, username: str) -> bool:
        platforms = {_clean_platform(x) for x in _split_list((self._settings or {}).get('srplus_allowed_platforms'))}
        if platforms and _clean_platform(platform) not in platforms:
            return False
        users = {_clean_request_user(x).lower() for x in _split_list((self._settings or {}).get('srplus_allowed_users'))}
        if users and _clean_request_user(username).lower() not in users:
            return False
        return True

    def _handle_srplus(self, platform: str, username: str) -> None:
        if not self._srplus_allowed(platform, username):
            self._reply(platform, f'@{username} SR+ ist fuer dich oder diese Plattform nicht erlaubt.')
            self._log(f'SR+ blocked: {username}@{platform}')
            return
        try:
            res = self._post_json('/srplus/start', {'user': username})
            if not res.get('ok'):
                self._reply(platform, f'@{username} SR+ Fehler: {res.get("error") or "fehlgeschlagen"}')
                return
            dur = int(res.get('duration_min') or self._settings.get('srplus_duration_min') or 15)
            msg = f'@{username} SR+ gestartet fuer {dur} Minuten.'
            self._reply(platform, msg)
            self._broadcast_queue_reply(platform, msg)
            self._log(f'SR+ OK: {username}@{platform}')
        except Exception as exc:
            self._reply(platform, f'@{username} SR+ Fehler: {exc}')
            self._log(f'SR+ error: {exc}')

    def _reply(self, platform: str, message: str) -> bool:
        if not _as_bool((self._settings or {}).get('reply_enabled'), True):
            return False
        host = self._host
        if host is None:
            return False
        self._emit_dashboard_reply(platform, message)
        try:
            if hasattr(host, 'send_platform_message'):
                ok = bool(host.send_platform_message(platform, message, sender=self.plugin_id))
                if not ok:
                    self._log(f'Chat reply to {platform} failed: {message}')
                return ok
        except Exception as exc:
            self._log(f'Chat reply to {platform} failed: {exc}')
        return False

    def _emit_dashboard_reply(self, platform: str, message: str) -> None:
        host = self._host
        if host is None or not hasattr(host, 'emit_message'):
            return
        try:
            host.emit_message(self.plugin_id, {
                'platform': _clean_platform(platform) or platform,
                'username': 'spotis3mptify',
                'display_name': 'spotis3mptify',
                'text': message,
                'message': message,
                'message_type': 'chat',
                'type': 'chat',
                'source_plugin_id': self.plugin_id,
                'show_in_desktop': True,
                'show_in_obs': False,
            })
        except Exception as exc:
            self._log(f'Dashboard reply could not be added: {exc}')

    def _broadcast_queue_reply(self, source_platform: str, message: str) -> None:
        if not _as_bool((self._settings or {}).get('broadcast_queue_reply'), True):
            return
        host = self._host
        if host is None or not hasattr(host, 'send_platform_message'):
            return
        source = _clean_platform(source_platform)
        for target in ('twitch', 'tiktok', 'youtube', 'kick'):
            if target == source:
                continue
            try:
                ok = bool(host.send_platform_message(target, message, sender=self.plugin_id))
                if ok:
                    self._log(f'Queue reply mirrored to {target}: {message}')
            except Exception as exc:
                self._log(f'Queue reply to {target} failed: {exc}')

    def _broadcast_srb_reply(self, source_platform: str, message: str) -> None:
        if not _as_bool((self._settings or {}).get('srb_broadcast_enabled'), True):
            return
        host = self._host
        if host is None or not hasattr(host, 'send_platform_message'):
            return
        source = _clean_platform(source_platform)
        allowed = self._allowed_platforms()
        for target in ('twitch', 'tiktok', 'youtube', 'kick'):
            if target == source or (allowed and target not in allowed):
                continue
            try:
                ok = bool(host.send_platform_message(target, message, sender=self.plugin_id))
                if ok:
                    self._log(f'SR Battle reply mirrored to {target}: {message}')
            except Exception as exc:
                self._log(f'SR Battle reply to {target} failed: {exc}')

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        try:
            if parent is not None and hasattr(parent, 'values'):
                vals = dict(self._settings or {})
                vals.update(parent.values())
                self._settings = vals
        except Exception:
            pass
        if key == 'button_open_overlay':
            self.open_overlay()
            return True
        if key == 'button_open_dashboard':
            if QtWidgets is None:
                self.open_overlay()
                return True
            try:
                if self._dashboard is None:
                    self._dashboard = _DashboardWindow(self)
                self._dashboard.show()
                self._dashboard.raise_()
                self._dashboard.activateWindow()
            except Exception as exc:
                self._log(f'Dashboard konnte nicht geÃ¶ffnet werden: {exc}')
            return True
        return False


def create_plugin() -> Spotis3mptifyPlugin:
    return Spotis3mptifyPlugin()
