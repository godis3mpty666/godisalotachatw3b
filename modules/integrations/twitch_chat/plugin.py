from __future__ import annotations
import base64
import html
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional
from data.paths import app_root
from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin
IRC_HOST = 'irc.chat.twitch.tv'
IRC_PORT_SSL = 6697
VALIDATE_URL = 'https://id.twitch.tv/oauth2/validate'
HELIX_USERS_URL = 'https://api.twitch.tv/helix/users'
HELIX_STREAMS_URL = 'https://api.twitch.tv/helix/streams'
HELIX_FOLLOWERS_URL = 'https://api.twitch.tv/helix/channels/followers'
HELIX_CHANNEL_EMOTES_URL = 'https://api.twitch.tv/helix/chat/emotes?broadcaster_id={channel_id}'
HELIX_GLOBAL_EMOTES_URL = 'https://api.twitch.tv/helix/chat/emotes/global'
BTTV_GLOBAL_URL = 'https://api.betterttv.net/3/cached/emotes/global'
BTTV_USER_URL = 'https://api.betterttv.net/3/cached/users/twitch/{channel_id}'
FFZ_GLOBAL_URL = 'https://api.frankerfacez.com/v1/set/global'
FFZ_ROOM_URL = 'https://api.frankerfacez.com/v1/room/id/{channel_id}'
SEVENTV_GLOBAL_URLS = [
    'https://7tv.io/v3/emote-sets/global',
    'https://api.7tv.app/v3/emote-sets/global',
]
SEVENTV_USER_URLS = [
    'https://7tv.io/v3/users/twitch/{channel_id}',
    'https://api.7tv.app/v3/users/twitch/{channel_id}',
]
SEVENTV_EMOTE_SET_URLS = [
    'https://7tv.io/v3/emote-sets/{set_id}',
    'https://api.7tv.app/v3/emote-sets/{set_id}',
]

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'
DEFAULT_SCOPES = 'chat:read chat:edit user:read:chat user:write:chat moderator:read:chatters moderator:manage:banned_users moderator:manage:chat_messages channel:manage:broadcast'
EMOTE_REFRESH_SECONDS = 900.0
IMG_STYLE = 'display:inline;vertical-align:-0.10em;height:1em;max-height:1em;width:auto;margin:0;padding:0;border:0;'
_TOKEN_RE = re.compile(r'(\s+)')
_BOUNDARY_SPLIT_RE = re.compile(r'(\s+|[^\w]+)', re.UNICODE)
_COLON_EMOTE_RE = re.compile(r':([A-Za-z0-9_]+):')
_TWITCH_JOIN_BOT_LOGINS = {
    'streamelements',
    'streamlabs',
    'nightbot',
    'moobot',
    'own3d',
    'own3dpro',
    'kofistreambot',
    'fossabot',
    'sery_bot',
    'wizebot',
    'soundalerts',
    'commanderroot',
    'streamelementsbot',
    'deepbot',
    'phantombot',
}
class TwitchChatPlugin(ThreadedPlugin):
    plugin_id = 'twitch_chat'
    display_name = 'Twitch Chat'
    version = '1.7.9'
    description = 'Twitch chat via IRC with OAuth, viewer count polling, and inline emote rendering for Twitch/7TV/BTTV/FFZ.'
    def __init__(self) -> None:
        super().__init__()
        self._sock: Optional[socket.socket] = None
        self._last_viewer_count: int | None = None
        self._last_followers_count: int | None = None
        self._last_is_live: bool | None = None
        self._last_metrics_poll = 0.0
        self._last_valid_live_viewers: int | None = None
        self._resolved_broadcaster_id: str = ''
        self._resolved_display_name: str = ''
        self._third_party_emotes: dict[str, dict[str, Any]] = {}
        self._official_named_emotes: dict[str, dict[str, Any]] = {}
        self._emote_source_counts: dict[str, int] = {'official': 0, '7tv': 0, 'bttv': 0, 'ffz': 0}
        self._third_party_emotes_loaded_for: str = ''
        self._third_party_emotes_loaded_at: float = 0.0
        self._image_data_uri_cache: dict[str, str] = {}
        self._known_follower_ids: set[str] = set()
        self._followers_initialized: bool = False
        self._processed_usernotice_ids: set[str] = set()
        self._processed_join_names: set[str] = set()
        self._processed_join_seen_at: dict[str, float] = {}
        self._host: PluginHost | None = None
        self._send_lock = threading.RLock()
        self._current_channel: str = ''
        self._active_account: str = ''
    def settings_schema(self):
        # Login/auth data now lives in the main tool under Plattformen/Platforms -> Twitch.
        # Keep this plugin overlay limited to Twitch-chat specific behavior only.
        return [
            {
                'key': 'metrics_poll_seconds',
                'label': 'Metrics Poll Seconds',
                'placeholder': '20',
                'help': 'How often viewer, live status, and followers are refreshed.'
            },
            {'key': 'test_twitch_sr_export', 'label': 'Test Twitch !sr export', 'type': 'button', 'button_text': 'Test Twitch !sr'},
            {'key': 'test_twitch_yt_export', 'label': 'Test Twitch !yt export', 'type': 'button', 'button_text': 'Test Twitch !yt'},
            {
                'key': 'viewer_count_enabled',
                'label': 'Zuschauerzahl anzeigen',
                'type': 'checkbox',
                'help': 'Gibt die Twitch-Zuschauerzahl an Overlays/Tools weiter.'
            },
            {
                'key': 'viewer_join_alerts',
                'label': 'Zuschauernamen anzeigen',
                'type': 'checkbox',
                'help': 'Zeigt Join-Alerts/Namensmeldungen, wenn Twitch IRC einen User im Chat meldet.'
            },
        ]
    def default_settings(self):
        return {
            # OAuth/account data is provided by the main Plattformen tab.
            'metrics_poll_seconds': '20',
            'autoconnect': False,
            'viewer_count_enabled': True,
            'viewer_join_alerts': True,
        }
    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        if key == 'test_twitch_sr_export':
            return self._emit_songrequest_export_test(host, '!sr', 'TwitchSrTest', 'https://youtu.be/godisalotachat_twitch_sr_test')
        if key == 'test_twitch_yt_export':
            return self._emit_songrequest_export_test(host, '!yt', 'TwitchYtTest', 'https://youtu.be/godisalotachat_twitch_yt_test')
        return False

    def on_settings_action(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host=host, parent=parent)

    def handle_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host=host, parent=parent)

    def _songrequest_export_line_count(self) -> int:
        try:
            path = app_root() / 'data' / 'spotis3mptify' / 'export' / 'songrequests.txt'
            if not path.exists():
                return 0
            return len([line for line in path.read_text(encoding='utf-8').splitlines() if line.strip()])
        except Exception:
            return -1

    def _emit_songrequest_export_test(self, host: PluginHost | None, command: str, username: str, url: str) -> bool:
        if host is None:
            return False
        text = f'{command} {url}'
        before = self._songrequest_export_line_count()
        host.emit_message(self.plugin_id, {
            'platform': 'twitch',
            'username': username,
            'text': text,
            'message': text,
            'content': text,
            'channel': 'twitch_export_test',
            'message_type': 'chat',
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': True,
            'show_in_obs': True,
        })
        after = self._songrequest_export_line_count()
        added = after - before if before >= 0 and after >= 0 else 'unknown'
        try:
            host.log(self.plugin_id, f'SR export test {command}: before={before} after={after} added={added}')
        except Exception:
            pass
        return True
    @staticmethod
    def _clean_channel(value: str) -> str:
        return (value or '').strip().lstrip('#').lstrip('@').strip().lower()
    @staticmethod
    def _clean_username(value: str) -> str:
        return (value or '').strip().lstrip('@').strip().lower()
    @staticmethod
    def _clean_token(value: str) -> str:
        token = (value or '').strip()
        if token.startswith('oauth:'):
            token = token[6:]
        return token
    @staticmethod
    def _redirect_uri(port: int) -> str:
        return f'http://localhost:{port}/callback'
    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            if isinstance(value, bool):
                return int(value)
            return int(str(value).strip())
        except Exception:
            return None
    @staticmethod
    def _parse_redirect_port(value: Any, default: int = 17564) -> int:
        text = str(value or '').strip()
        if not text:
            return default
        try:
            if '://' in text:
                after_host = text.split('://', 1)[1]
                host_port = after_host.split('/', 1)[0]
                if ':' in host_port:
                    return int(host_port.rsplit(':', 1)[1])
            return int(text)
        except Exception:
            return default

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {'1', 'true', 'yes', 'ja', 'on', 'enabled'}:
            return True
        if text in {'0', 'false', 'no', 'nein', 'off', 'disabled'}:
            return False
        return default

    def _host_platform_settings(self, host: PluginHost | None = None) -> dict[str, Any]:
        host = host or self._host
        if host is None:
            return {}
        for name in ('get_platform_settings', 'platform_settings'):
            fn = getattr(host, name, None)
            if not callable(fn):
                continue
            try:
                data = fn('twitch')
                if isinstance(data, dict):
                    return dict(data)
            except Exception:
                pass
        return {}

    def _effective_settings(self, settings: dict | None, host: PluginHost | None = None) -> dict[str, Any]:
        """Resolve Twitch runtime settings from the central host, like kick_chat.

        Host platform data is the source of truth. The plugin only contributes
        Twitch-chat behavior settings. Empty old plugin fields never overwrite the
        Plattformen tab and stale local OAuth data is not used unless there is no
        host data at all.
        """
        local = dict(settings or {})
        merged: dict[str, Any] = {}
        platform = self._host_platform_settings(host)
        if isinstance(platform, dict):
            merged.update(platform)

        # Plugin-local behavior only. This mirrors kick_chat's non-empty merge,
        # but avoids pulling old local OAuth/client fields back into runtime data.
        for key in ('metrics_poll_seconds', 'viewer_count_enabled', 'viewer_join_alerts'):
            value = local.get(key)
            if value not in (None, ''):
                merged[key] = value

        # Legacy fallback only for installs that have no central Plattformen data.
        if not merged.get('channel'):
            channel = self._clean_channel(local.get('channel') or local.get('main') or local.get('main_account') or '')
            if channel:
                merged['channel'] = channel
                merged['main'] = channel
                merged['main_account'] = channel
        if not merged.get('username'):
            username = self._clean_username(local.get('username') or local.get('bot_username') or local.get('bot_account') or merged.get('channel') or '')
            if username:
                merged['username'] = username
                merged['bot'] = username
                merged['bot_account'] = username
                merged['bot_username'] = username
        for key in ('client_id', 'access_token', 'main_access_token', 'main_oauth_login', 'main_username', 'main_account'):
            if not merged.get(key) and local.get(key) not in (None, ''):
                merged[key] = str(local.get(key)).strip()

        redirect_url = str(merged.get('redirect_url') or merged.get('redirect_uri') or '').strip()
        redirect_port = merged.get('redirect_port') or self._parse_redirect_port(redirect_url, 17564)
        merged['redirect_port'] = str(self._parse_redirect_port(redirect_port, self._parse_redirect_port(redirect_url, 17564)))
        if redirect_url:
            merged['redirect_url'] = redirect_url
            merged['redirect_uri'] = redirect_url

        scopes = str(merged.get('scopes') or '').strip()
        if not scopes:
            scopes = 'chat:read chat:edit'
            if self._as_bool(merged.get('moderation_rights_enabled'), True):
                scopes += ' moderator:manage:banned_users moderator:manage:chat_messages'
        scopes = scopes.replace('moderator:manage_banned_users', 'moderator:manage:banned_users')
        scope_items = []
        for raw in (scopes, DEFAULT_SCOPES):
            for part in str(raw or '').split():
                part = part.strip()
                if part and part not in scope_items:
                    scope_items.append(part)
        scopes = ' '.join(scope_items)
        merged['scopes'] = scopes
        merged['read_enabled'] = self._as_bool(merged.get('read_enabled'), True)
        merged['write_enabled'] = self._as_bool(merged.get('write_enabled'), True)
        merged['autoconnect'] = self._as_bool(merged.get('autoconnect'), self._as_bool(local.get('autoconnect'), False))
        return merged

    def _merge_platform_settings(self, settings: dict | None, host: PluginHost | None = None) -> dict:
        # Compatibility wrapper for older call-sites inside this plugin.
        return self._effective_settings(settings, host)

    def _oauth_scopes(self, settings: dict) -> str:
        scopes = str((settings or {}).get('scopes') or '').strip()
        return scopes or DEFAULT_SCOPES

    @staticmethod
    def _normalize_chat_text(value: Any) -> str:
        if value is None:
            return ''
        text = str(value).replace('\r', ' ').replace('\n', ' ')
        text = ' '.join(text.split())
        return text.strip()
    @staticmethod
    def _parse_irc_tags(line: str) -> tuple[dict[str, str], str]:
        if not line.startswith('@'):
            return {}, line
        try:
            raw_tags, rest = line[1:].split(' ', 1)
        except ValueError:
            return {}, line
        tags: dict[str, str] = {}
        for pair in raw_tags.split(';'):
            if not pair:
                continue
            if '=' in pair:
                key, value = pair.split('=', 1)
            else:
                key, value = pair, ''
            tags[key] = value
        return tags, rest
    @staticmethod
    def _unescape_tag(value: str) -> str:
        if not value:
            return ''
        return (
            value.replace(r'\s', ' ')
            .replace(r'\:', ';')
            .replace(r'\\', '\\')
            .replace(r'\r', '\r')
            .replace(r'\n', '\n')
        )
    @staticmethod
    def _twitch_emote_url(emote_id: str, animated: bool = False) -> str:
        if not emote_id:
            return ''
        if animated:
            return f'https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/2.0'
        return f'https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/2.0'
    def _guess_image_content_type(self, url: str, header_content_type: str = '') -> str:
        content_type = (header_content_type or '').strip().lower()
        if content_type and content_type != 'application/octet-stream':
            return content_type
        parsed = urllib.parse.urlparse(url or '')
        path = (parsed.path or '').lower()
        if path.endswith('.gif'):
            return 'image/gif'
        if path.endswith('.png'):
            return 'image/png'
        if path.endswith('.jpg') or path.endswith('.jpeg'):
            return 'image/jpeg'
        if path.endswith('.webp'):
            return 'image/webp'
        if path.endswith('.avif'):
            return 'image/avif'
        return 'image/png'
    def _is_probably_animated_url(self, url: str, explicit_animated: bool = False) -> bool:
        if explicit_animated:
            return True
        lowered = (url or '').strip().lower()
        if not lowered:
            return False
        return lowered.endswith('.gif') or '.gif?' in lowered or lowered.endswith('.webp') or '.webp?' in lowered
    def _url_to_data_uri(self, url: str, *, prefer_remote: bool = False) -> str:
        url = (url or '').strip()
        if not url:
            return ''
        if prefer_remote:
            return url
        cached = self._image_data_uri_cache.get(url)
        if cached:
            return cached
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                content_type = self._guess_image_content_type(url, resp.headers.get_content_type() or '')
            if not data:
                return url
            encoded = base64.b64encode(data).decode('ascii')
            data_uri = f'data:{content_type};base64,{encoded}'
            self._image_data_uri_cache[url] = data_uri
            return data_uri
        except Exception:
            return url
    def _build_img_html(self, url: str, alt_text: str, animated: bool = False) -> str:
        src = self._url_to_data_uri(url, prefer_remote=self._is_probably_animated_url(url, animated))
        safe_url = html.escape(src, quote=True)
        clean_alt = (alt_text or '').strip()
        if clean_alt.startswith(':') and clean_alt.endswith(':') and len(clean_alt) > 2:
            clean_alt = clean_alt[1:-1]
        safe_alt = html.escape(clean_alt, quote=True)
        return f'<img src="{safe_url}" alt="{safe_alt}" title="{safe_alt}" style="{IMG_STYLE}">'
    def _http_get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        req = urllib.request.Request(url, headers=headers or {}, method='GET')
        with urllib.request.urlopen(req, timeout=20) as resp:
            txt = resp.read().decode('utf-8', errors='ignore')
        return json.loads(txt or '{}')
    def _http_json(self, url: str, *, method='GET', data: dict | None = None, headers: dict | None = None) -> dict:
        body = None
        req_headers = dict(headers or {})
        if data is not None:
            body = urllib.parse.urlencode(data).encode('utf-8')
            req_headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as resp:
            txt = resp.read().decode('utf-8', errors='ignore')
        return json.loads(txt or '{}')
    @staticmethod
    def _is_http_unauthorized(exc: Exception) -> bool:
        return isinstance(exc, urllib.error.HTTPError) and int(getattr(exc, 'code', 0) or 0) == 401
    def _validate_token(self, token: str) -> tuple[bool, str, str, list[str]]:
        token = self._clean_token(token)
        if not token:
            return False, '', 'Missing access token.', []
        try:
            data = self._http_json(VALIDATE_URL, headers={'Authorization': f'OAuth {token}'})
            login = (data.get('login') or '').strip().lower()
            scopes = data.get('scopes') or []
            if 'chat:read' not in scopes:
                return False, login, 'Token exists, but chat:read scope is missing.', list(scopes)
            return True, login, 'Token validated.', list(scopes)
        except Exception as exc:
            return False, '', f'Token validation failed: {exc}', []
    def _resolve_auth(self, settings: dict, *, allow_oauth: bool) -> tuple[bool, str, str, dict]:
        cache: dict[str, Any] = {}
        for key in ('access_token', 'main_access_token', 'client_id', 'scopes', 'main_scopes'):
            value = settings.get(key)
            if value not in (None, ''):
                cache[key] = value

        # Main-alone mode is mandatory: a missing or stale bot token must never
        # block Twitch chat. Try the bot first only when it really has a token,
        # then fall back to the broadcaster/main token before reporting failure.
        candidates: list[tuple[str, str, str]] = []
        bot_token = self._clean_token(cache.get('access_token') or '')
        main_token = self._clean_token(cache.get('main_access_token') or '')
        if bot_token:
            candidates.append(('bot', bot_token, self._clean_username(
                settings.get('username')
                or settings.get('bot_username')
                or settings.get('bot_account')
                or settings.get('bot')
                or ''
            )))
        if main_token and main_token != bot_token:
            candidates.append(('main', main_token, self._clean_username(
                settings.get('main_oauth_login')
                or settings.get('main_username')
                or settings.get('main_account')
                or settings.get('main')
                or settings.get('channel')
                or ''
            )))

        if not candidates:
            return False, '', 'Missing Twitch main/bot access token from core Platforms.', cache

        errors: list[str] = []
        for account, token, username in candidates:
            ok, login, msg, scopes = self._validate_token(token)
            if not ok:
                errors.append(f'{account}: {msg}')
                continue
            if login:
                username = login
            cache.update({
                'access_token': token,
                'username': username,
                'auth_account': account,
                'client_id': (settings.get('client_id') or '').strip(),
                'scopes': scopes,
                'saved_at': int(time.time()),
            })
            suffix = 'bot' if account == 'bot' else 'main fallback'
            return True, username, f'Using core Twitch authorization ({suffix}).', cache

        return False, '', 'Twitch OAuth unusable: ' + ' | '.join(errors), cache
    def _refresh_runtime_auth(self, settings: dict, cache: dict) -> tuple[bool, str, str, dict]:
        ok, username, msg, fresh_cache = self._resolve_auth(settings, allow_oauth=False)
        if ok:
            cache.clear()
            cache.update(fresh_cache)
            return True, username, msg, cache
        return False, username, msg, fresh_cache
    def _helix_headers(self, settings: dict, cache: dict) -> dict[str, str]:
        client_id = (settings.get('client_id') or cache.get('client_id') or '').strip()
        token = self._clean_token(cache.get('access_token') or '')
        if not client_id or not token:
            raise RuntimeError('Missing Client ID or access token for Helix.')
        return {
            'Client-Id': client_id,
            'Authorization': f'Bearer {token}',
        }
    def _helix_get(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        return self._http_json(url, headers=headers)
    def _resolve_broadcaster(self, settings: dict, cache: dict, channel: str) -> tuple[str, str]:
        headers = self._helix_headers(settings, cache)
        data = self._helix_get(f'{HELIX_USERS_URL}?login={urllib.parse.quote(channel)}', headers)
        rows = data.get('data') if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise RuntimeError('Broadcaster not found on Twitch.')
        row = rows[0] if isinstance(rows[0], dict) else {}
        broadcaster_id = str(row.get('id') or '').strip()
        display_name = str(row.get('display_name') or channel).strip() or channel
        if not broadcaster_id:
            raise RuntimeError('Broadcaster ID missing in Helix users response.')
        self._resolved_broadcaster_id = broadcaster_id
        self._resolved_display_name = display_name
        return broadcaster_id, display_name
    def _fetch_metrics(self, settings: dict, cache: dict, channel: str) -> dict[str, Any]:
        headers = self._helix_headers(settings, cache)
        broadcaster_id, display_name = self._resolve_broadcaster(settings, cache, channel)
        is_live = False
        viewer_count = 0
        try:
            streams = self._helix_get(f'{HELIX_STREAMS_URL}?user_login={urllib.parse.quote(channel)}', headers)
            rows = streams.get('data') if isinstance(streams, dict) else None
            if isinstance(rows, list) and rows:
                row = rows[0] if isinstance(rows[0], dict) else {}
                is_live = True
                viewer_count = self._to_int(row.get('viewer_count')) or 0
                self._last_valid_live_viewers = viewer_count if viewer_count > 0 else self._last_valid_live_viewers
            else:
                is_live = False
                viewer_count = 0
        except Exception:
            if self._last_is_live is True and isinstance(self._last_valid_live_viewers, int):
                is_live = True
                viewer_count = self._last_valid_live_viewers
            else:
                raise
        followers_count = None
        try:
            followers = self._helix_get(f'{HELIX_FOLLOWERS_URL}?broadcaster_id={urllib.parse.quote(broadcaster_id)}', headers)
            followers_count = self._to_int(followers.get('total')) if isinstance(followers, dict) else None
        except Exception:
            followers_count = self._last_followers_count
        return {
            'broadcaster_id': broadcaster_id,
            'display_name': display_name,
            'is_live': is_live,
            'viewer_count': viewer_count,
            'followers_count': followers_count,
        }
    def _emit_viewer_count(self, host: PluginHost, channel: str, viewer_count: int) -> None:
        viewer_count = int(viewer_count)
        if self._last_viewer_count == viewer_count:
            return
        self._last_viewer_count = viewer_count
        host.emit_message(self.plugin_id, {
            'platform': 'twitch',
            'username': '',
            'text': str(viewer_count),
            'channel': channel,
            'message_type': 'viewer_count',
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': True,
            'show_in_obs': True,
            'metric_only': True,
            'viewer_count': viewer_count,
        })
    def _emit_followers_count(self, host: PluginHost, channel: str, followers_count: int | None) -> None:
        if followers_count is None:
            return
        self._last_followers_count = followers_count

    def _emit_metric_error(self, host: PluginHost, channel: str, detail: str) -> None:
        host.emit_metric(self.plugin_id, {
            'platform': 'twitch',
            'channel': channel,
            'message_type': 'metric',
            'metric_error': True,
            'viewer_count_error': True,
            'followers_count_error': True,
            'detail': detail,
        })

    def _emit_alert(self, host: PluginHost, channel: str, username: str, text: str, message_type: str) -> None:
        clean_text = self._normalize_chat_text(text)
        clean_name = (username or 'Twitch').strip() or 'Twitch'
        clean_type = (message_type or 'twitch_alert').strip() or 'twitch_alert'
        if not clean_text:
            return

        # Keep this payload intentionally redundant. Older godisalotachat builds
        # looked at message_type only, newer/other alert renderers may look for
        # is_alert/alert/event_type/alert_type. Sending all of them makes real
        # Twitch events and test commands use the exact same desktop/OBS path.
        payload = {
            'platform': 'twitch',
            'username': clean_name,
            'display_name': clean_name,
            'text': clean_text,
            'message': clean_text,
            'channel': channel,
            'message_type': clean_type,
            'event_type': clean_type,
            'alert_type': clean_type,
            'source_plugin_id': self.plugin_id,
            'source': self.plugin_id,
            'is_alert': True,
            'alert': True,
            'metric_only': False,
            'show_in_desktop': True,
            'show_in_obs': True,
        }
        host.emit_message(self.plugin_id, payload)
        try:
            host.log(self.plugin_id, f'Alert emitted: {clean_type} | {clean_name} | {clean_text}')
        except Exception:
            pass

    @staticmethod
    def _settings_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {'1', 'true', 'yes', 'ja', 'on', 'enabled'}:
            return True
        if text in {'0', 'false', 'no', 'nein', 'off', 'disabled'}:
            return False
        return default

    def _parse_join_name(self, line: str, channel: str) -> str:
        raw = (line or '').strip()
        if not raw or ' JOIN ' not in raw:
            return ''
        try:
            _prefix, rest = raw[1:].split(' ', 1) if raw.startswith(':') else ('', raw)
            nick = _prefix.split('!', 1)[0].strip() if _prefix else ''
            parts = rest.split()
            if len(parts) < 2 or parts[0].upper() != 'JOIN':
                return ''
            joined_channel = parts[1].lstrip('#').strip().lower()
            if joined_channel and joined_channel != (channel or '').strip().lower():
                return ''
            return nick
        except Exception:
            return ''

    def _handle_join_event(self, host: PluginHost, settings: dict, channel: str, login_username: str, line: str) -> None:
        if not self._settings_bool(settings.get('viewer_join_alerts'), True):
            return
        joined_name = self._parse_join_name(line, channel)
        if not joined_name:
            return

        joined_key = joined_name.strip().lower()
        if not joined_key:
            return

        if joined_key in _TWITCH_JOIN_BOT_LOGINS:
            self._processed_join_names.add(joined_key)
            self._processed_join_seen_at[joined_key] = time.monotonic()
            return

        # Mainaccount und der eigene Botaccount sollen sichtbar bleiben, weil das
        # beim Testen hilft. Service-Bots werden oben weiterhin unterdrückt.
        now = time.monotonic()
        last_seen = self._processed_join_seen_at.get(joined_key, 0.0)
        if joined_key in self._processed_join_names and (now - last_seen) < 300.0:
            return
        self._processed_join_names.add(joined_key)
        self._processed_join_seen_at[joined_key] = now
        if len(self._processed_join_names) > 1000:
            keep = list(self._processed_join_names)[-700:]
            self._processed_join_names = set(keep)
            self._processed_join_seen_at = {k: self._processed_join_seen_at.get(k, now) for k in keep}

        self._emit_alert(host, channel, joined_name, 'ist dem Stream beigetreten', 'twitch_alert')

    def _handle_test_alert_command(self, host: PluginHost, channel: str, sender: str, message_text: str) -> bool:
        raw = self._normalize_chat_text(message_text)
        if not raw.startswith('!'):
            return False

        parts = raw.split()
        command = parts[0].strip().lower() if parts else ''
        if not command:
            return False

        # Optional custom name: !testfollow SomeUser
        custom_name = ' '.join(parts[1:]).strip()
        test_name = custom_name or sender or 'TwitchTester'

        commands = {
            '!testalert': ('twitch_alert', 'hat einen Twitch-Testalert ausgelöst'),
            '!testfollow': ('twitch_follow', 'folgt jetzt dem Kanal'),
            '!testsub': ('twitch_sub', 'abonniert den Kanal'),
            '!testresub': ('twitch_resub', 'abonniert seit 6 Monaten'),
            '!testgift': ('twitch_subgift', 'verschenkt ein Sub'),
            '!testsubgift': ('twitch_subgift', 'verschenkt ein Sub'),
            '!testraid': ('twitch_raid', 'raided mit 42 Zuschauern'),
            '!testbits': ('twitch_cheer', 'cheered 100 Bits'),
            '!testcheer': ('twitch_cheer', 'cheered 100 Bits'),
        }

        item = commands.get(command)
        if item is None:
            return False

        message_type, text = item
        self._emit_alert(host, channel, test_name, text, message_type)
        return True

    def _fetch_recent_followers(self, settings: dict, cache: dict, channel: str, limit: int = 5) -> list[dict[str, Any]]:
        headers = self._helix_headers(settings, cache)
        broadcaster_id = self._resolved_broadcaster_id
        if not broadcaster_id:
            broadcaster_id, _ = self._resolve_broadcaster(settings, cache, channel)
        url = f'{HELIX_FOLLOWERS_URL}?broadcaster_id={urllib.parse.quote(broadcaster_id)}&first={max(1, min(int(limit), 20))}'
        data = self._helix_get(url, headers)
        rows = data.get('data') if isinstance(data, dict) else None
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _maybe_poll_follow_alerts(self, host: PluginHost, settings: dict, cache: dict, channel: str) -> None:
        rows = self._fetch_recent_followers(settings, cache, channel, limit=5)
        ids: list[str] = []
        for row in rows:
            fid = str(row.get('user_id') or row.get('from_id') or row.get('user_login') or '').strip()
            if fid:
                ids.append(fid)
        if not self._followers_initialized:
            self._known_follower_ids = set(ids)
            self._followers_initialized = True
            return

        new_rows = []
        for row in rows:
            fid = str(row.get('user_id') or row.get('from_id') or row.get('user_login') or '').strip()
            if fid and fid not in self._known_follower_ids:
                new_rows.append(row)

        for row in reversed(new_rows):
            name = str(row.get('user_name') or row.get('user_login') or row.get('from_name') or 'Jemand').strip()
            self._emit_alert(host, channel, name, 'folgt jetzt dem Kanal', 'twitch_follow')

        self._known_follower_ids.update(ids)
        if len(self._known_follower_ids) > 250:
            self._known_follower_ids = set(list(self._known_follower_ids)[-200:])

    def _handle_usernotice(self, host: PluginHost, tags: dict[str, str], channel: str) -> None:
        msg_id = self._unescape_tag(tags.get('msg-id', '')).strip().lower()
        if not msg_id:
            return
        dedupe = tags.get('id') or f"{tags.get('tmi-sent-ts', '')}:{msg_id}:{tags.get('login', '')}:{tags.get('system-msg', '')}"
        if dedupe in self._processed_usernotice_ids:
            return
        self._processed_usernotice_ids.add(dedupe)
        if len(self._processed_usernotice_ids) > 500:
            self._processed_usernotice_ids = set(list(self._processed_usernotice_ids)[-300:])

        username = self._unescape_tag(
            tags.get('display-name')
            or tags.get('login')
            or tags.get('msg-param-displayName')
            or tags.get('msg-param-recipient-display-name')
            or 'Twitch'
        ) or 'Twitch'
        system_msg = self._normalize_chat_text(self._unescape_tag(tags.get('system-msg', '')))

        if msg_id == 'raid':
            raider = self._unescape_tag(tags.get('msg-param-displayName') or username) or username
            viewers = self._to_int(tags.get('msg-param-viewerCount'))
            text = f'raided mit {viewers} Zuschauern' if viewers else 'raided den Stream'
            self._emit_alert(host, channel, raider, text, 'twitch_raid')
            return

        if msg_id in {'sub', 'primepaidupgrade'}:
            self._emit_alert(host, channel, username, system_msg or 'abonniert den Kanal', 'twitch_sub')
            return

        if msg_id == 'resub':
            months = self._to_int(tags.get('msg-param-cumulative-months') or tags.get('msg-param-months'))
            text = system_msg or (f'abonniert seit {months} Monaten' if months else 'hat resubbed')
            self._emit_alert(host, channel, username, text, 'twitch_resub')
            return

        if msg_id in {'subgift', 'anonsubgift'}:
            recipient = self._unescape_tag(tags.get('msg-param-recipient-display-name') or '')
            text = system_msg or (f'verschenkt ein Sub an {recipient}' if recipient else 'verschenkt ein Sub')
            self._emit_alert(host, channel, username, text, 'twitch_subgift')
            return

        if msg_id == 'submysterygift':
            count = self._to_int(tags.get('msg-param-mass-gift-count'))
            text = system_msg or (f'verschenkt {count} Subs' if count else 'verschenkt mehrere Subs')
            self._emit_alert(host, channel, username, text, 'twitch_subgift')
            return

        if msg_id in {'giftpaidupgrade', 'anongiftpaidupgrade'}:
            self._emit_alert(host, channel, username, system_msg or 'setzt ein Geschenk-Sub fort', 'twitch_sub')
            return

        if 'sub' in msg_id and system_msg:
            self._emit_alert(host, channel, username, system_msg, 'twitch_sub')
    def _emit_is_live(self, host: PluginHost, channel: str, is_live: bool) -> None:
        if self._last_is_live is is_live:
            return
        self._last_is_live = is_live

        payload = {
            'platform': 'twitch',
            'channel': channel,
            'message_type': 'is_live',
            'is_live': is_live,
            'metric_only': True,
        }

        # Live/offline state is technical status data, not a chat message.
        # Sending it through emit_message can create empty desktop rows in
        # older host builds, even with show_in_desktop=False.
        try:
            host.emit_metric(self.plugin_id, payload)
        except Exception:
            pass
    def _looks_like_placeholder_chat(self, text: str) -> bool:
        s = (text or '').strip()
        if not s:
            return True
        if s in {':', '-', '—', '...', '…'}:
            return True
        return False
    def _maybe_poll_metrics(self, host: PluginHost, settings: dict, cache: dict, channel: str, *, force: bool = False) -> None:
        try:
            poll_seconds = max(float(settings.get('metrics_poll_seconds') or '20'), 5.0)
        except Exception:
            poll_seconds = 20.0
        now = time.monotonic()
        if not force and (now - self._last_metrics_poll) < poll_seconds:
            return
        self._last_metrics_poll = now
        try:
            metrics = self._fetch_metrics(settings, cache, channel)
        except Exception as exc:
            if self._is_http_unauthorized(exc):
                ok, _username, auth_msg, _cache = self._refresh_runtime_auth(settings, cache)
                if ok:
                    host.log(self.plugin_id, f'Helix token refreshed after 401: {auth_msg}')
                    try:
                        metrics = self._fetch_metrics(settings, cache, channel)
                    except Exception as exc2:
                        host.log(self.plugin_id, f'Metrics retry failed after refresh: {exc2}')
                        self._emit_metric_error(host, channel, str(exc2))
                        return
                else:
                    host.log(self.plugin_id, f'Helix token refresh failed after 401: {auth_msg}')
                    self._emit_metric_error(host, channel, auth_msg)
                    return
            else:
                host.log(self.plugin_id, f'Metrics poll warning: {exc}')
                self._emit_metric_error(host, channel, str(exc))
                return
        self._emit_is_live(host, channel, bool(metrics.get('is_live')))
        if self._settings_bool(settings.get('viewer_count_enabled'), True):
            self._emit_viewer_count(host, channel, self._to_int(metrics.get('viewer_count')) or 0)
        self._emit_followers_count(host, channel, self._to_int(metrics.get('followers_count')))
        try:
            self._maybe_poll_follow_alerts(host, settings, cache, channel)
        except Exception as exc:
            host.log(self.plugin_id, f'Follower alert poll warning: {exc}')
    def _connect_socket(self, username: str, token: str, channel: str) -> socket.socket:
        raw = socket.create_connection((IRC_HOST, IRC_PORT_SSL), timeout=10)
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=IRC_HOST)
        sock.settimeout(2.0)
        sock.sendall(b'CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n')
        sock.sendall(f'PASS oauth:{self._clean_token(token)}\r\n'.encode('utf-8'))
        sock.sendall(f'NICK {username}\r\n'.encode('utf-8'))
        sock.sendall(f'JOIN #{channel}\r\n'.encode('utf-8'))
        return sock
    def _handshake(self, sock: socket.socket) -> tuple[bool, str]:
        buffer = ''
        deadline = time.time() + 12.0
        while time.time() < deadline:
            try:
                data = sock.recv(4096)
                if not data:
                    time.sleep(0.05)
                    continue
                buffer += data.decode('utf-8', errors='ignore')
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    if not line:
                        continue
                    if line.startswith('PING'):
                        sock.sendall(b'PONG :tmi.twitch.tv\r\n')
                        continue
                    low = line.lower()
                    if 'authentication failed' in low or 'improperly formatted auth' in low or 'login authentication failed' in low:
                        return False, 'IRC login failed. Check token / OAuth app.'
                    if 'msg_channel_suspended' in low:
                        return False, 'Channel is suspended.'
                    if ' no such nick/channel' in low or ' no such channel' in low:
                        return False, 'Channel not found.'
                    if ' 001 ' in line:
                        return True, 'IRC connected.'
            except socket.timeout:
                continue
        return False, 'Timed out while connecting to Twitch IRC.'
    def _get_named_emote(self, token: str) -> dict[str, Any] | None:
        raw = (token or '').strip()
        if not raw:
            return None
        for candidate in (raw, raw.strip(':'), raw.lower(), raw.strip(':').lower()):
            if not candidate:
                continue
            em = self._official_named_emotes.get(candidate)
            if em:
                return em
            em = self._third_party_emotes.get(candidate)
            if em:
                return em
        return None
    def _remember_official_emote(self, name: str, url: str, source: str = 'twitch', animated: bool = False) -> None:
        key = (name or '').strip()
        url = (url or '').strip()
        if not key or not url:
            return
        payload = {'url': url, 'source': source, 'animated': bool(animated)}
        added = False
        for candidate in {key, key.lower(), key.strip(':'), key.strip(':').lower()}:
            if candidate and candidate not in self._official_named_emotes:
                self._official_named_emotes[candidate] = payload
                added = True
            elif candidate:
                self._official_named_emotes[candidate] = payload
        if added:
            self._emote_source_counts['official'] = self._emote_source_counts.get('official', 0) + 1
    def _pick_twitch_emote_url(self, row: dict[str, Any]) -> str:
        emote_id = str(row.get('id') or '').strip()
        fmt = row.get('format')
        animated = isinstance(fmt, list) and 'animated' in [str(x).strip().lower() for x in fmt]
        if emote_id:
            return self._twitch_emote_url(emote_id, animated=animated)
        images = row.get('images') if isinstance(row, dict) else None
        if isinstance(images, dict):
            for key in ('url_4x', 'url_2x', 'url_1x'):
                value = images.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ''
    def _fetch_official_twitch_emotes(self, headers: dict[str, str], channel_id: str, host: PluginHost | None = None) -> None:
        urls = [HELIX_GLOBAL_EMOTES_URL]
        if channel_id:
            urls.append(HELIX_CHANNEL_EMOTES_URL.format(channel_id=urllib.parse.quote(channel_id)))
        for url in urls:
            try:
                data = self._helix_get(url, headers)
            except Exception as exc:
                if host is not None:
                    try:
                        host.log(self.plugin_id, f'Official Twitch emote fetch failed: {exc}')
                    except Exception:
                        pass
                continue
            rows = data.get('data') if isinstance(data, dict) else None
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                code = str(row.get('name') or '').strip()
                url_value = self._pick_twitch_emote_url(row)
                fmt = row.get('format')
                animated = isinstance(fmt, list) and 'animated' in [str(x).strip().lower() for x in fmt]
                if code and url_value:
                    self._remember_official_emote(code, url_value, 'twitch', animated)
    def _remember_emote(self, name: str, url: str, source: str, animated: bool = False) -> None:
        key = (name or '').strip()
        url = (url or '').strip()
        if not key or not url:
            return
        payload = {'url': url, 'source': source, 'animated': bool(animated)}
        added = False
        for candidate in {key, key.lower(), key.strip(':'), key.strip(':').lower()}:
            if not candidate:
                continue
            existing = self._third_party_emotes.get(candidate)
            if existing and existing.get('source') == '7tv' and source != '7tv':
                continue
            if existing and existing.get('animated') and not animated:
                continue
            if candidate not in self._third_party_emotes:
                added = True
            self._third_party_emotes[candidate] = payload
        if added:
            self._emote_source_counts[source] = self._emote_source_counts.get(source, 0) + 1
    def _fetch_bttv_emotes(self, channel_id: str) -> None:
        try:
            rows = self._http_get_json(BTTV_GLOBAL_URL)
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    code = str(row.get('code') or '').strip()
                    emote_id = str(row.get('id') or '').strip()
                    image_type = str(row.get('imageType') or 'png').strip().lower() or 'png'
                    if code and emote_id:
                        self._remember_emote(code, f'https://cdn.betterttv.net/emote/{emote_id}/2x.{image_type}', 'bttv', image_type == 'gif')
        except Exception:
            pass
        try:
            data = self._http_get_json(BTTV_USER_URL.format(channel_id=urllib.parse.quote(channel_id)))
            if isinstance(data, dict):
                rows = []
                for key in ('channelEmotes', 'sharedEmotes'):
                    part = data.get(key)
                    if isinstance(part, list):
                        rows.extend(part)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    code = str(row.get('code') or '').strip()
                    emote_id = str(row.get('id') or '').strip()
                    image_type = str(row.get('imageType') or 'png').strip().lower() or 'png'
                    if code and emote_id:
                        self._remember_emote(code, f'https://cdn.betterttv.net/emote/{emote_id}/2x.{image_type}', 'bttv', image_type == 'gif')
        except Exception:
            pass
    def _ffz_pick_url(self, urls: dict[str, Any]) -> str:
        if not isinstance(urls, dict):
            return ''
        for key in ('4', '2', '1'):
            value = urls.get(key)
            if isinstance(value, str) and value.strip():
                return value if value.startswith('http') else f'https:{value}'
        return ''
    def _fetch_ffz_emotes(self, channel_id: str) -> None:
        for url in (FFZ_GLOBAL_URL, FFZ_ROOM_URL.format(channel_id=urllib.parse.quote(channel_id))):
            try:
                data = self._http_get_json(url)
            except Exception:
                continue
            sets = data.get('sets') if isinstance(data, dict) else None
            if not isinstance(sets, dict):
                continue
            for set_payload in sets.values():
                if not isinstance(set_payload, dict):
                    continue
                emotes = set_payload.get('emoticons')
                if not isinstance(emotes, list):
                    continue
                for row in emotes:
                    if not isinstance(row, dict):
                        continue
                    code = str(row.get('name') or '').strip()
                    url_value = self._ffz_pick_url(row.get('urls') or {})
                    if code and url_value:
                        animated = '.gif' in url_value.lower() or '.webp' in url_value.lower()
                        self._remember_emote(code, url_value, 'ffz', animated)
    def _extract_7tv_url(self, emote: dict[str, Any]) -> tuple[str, bool]:
        host = emote.get('host') if isinstance(emote, dict) else None
        files = host.get('files') if isinstance(host, dict) else None
        base_url = ''
        if isinstance(host, dict):
            base_url = str(host.get('url') or '').strip()
            if base_url and not base_url.startswith('http'):
                base_url = 'https:' + base_url
        animated = bool(emote.get('animated'))
        best = ''
        best_score = -1
        if isinstance(files, list):
            for row in files:
                if not isinstance(row, dict):
                    continue
                name = str(row.get('name') or '').strip()
                fmt = str(row.get('format') or '').strip().lower()
                width = self._to_int(row.get('width')) or 0
                row_animated = bool(row.get('animated')) or fmt == 'gif'
                candidate = ''
                if base_url and name:
                    candidate = base_url.rstrip('/') + '/' + name.lstrip('/')
                if not candidate:
                    continue
                score = width
                if animated or row_animated:
                    if fmt == 'gif':
                        score += 10000
                    elif fmt == 'png':
                        score += 100
                    elif fmt in {'webp', 'avif'}:
                        score += 10
                else:
                    if fmt == 'png':
                        score += 10000
                    elif fmt == 'gif':
                        score += 5000
                    elif fmt in {'webp', 'avif'}:
                        score += 1000
                if score > best_score:
                    best = candidate
                    best_score = score
                    animated = row_animated or animated
        if not best:
            emote_id = str(emote.get('id') or '').strip()
            if emote_id:
                best = f"https://cdn.7tv.app/emote/{emote_id}/2x.{'gif' if animated else 'png'}"
        return best, animated
    def _iter_7tv_emote_rows(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        rows = payload.get('emotes')
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        emote_set = payload.get('emote_set')
        if isinstance(emote_set, dict):
            rows = emote_set.get('emotes')
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []

    def _extract_7tv_emote_set_id(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ''
        emote_set = payload.get('emote_set')
        if isinstance(emote_set, dict):
            return str(emote_set.get('id') or '').strip()
        return ''

    def _store_7tv_rows(self, emotes: list[dict[str, Any]]) -> int:
        added = 0
        for row in emotes:
            if not isinstance(row, dict):
                continue
            data_row = row.get('data') if isinstance(row.get('data'), dict) else {}
            merged = {}
            if isinstance(data_row, dict):
                merged.update(data_row)
            merged.update(row)
            code = str(merged.get('name') or '').strip()
            url, animated = self._extract_7tv_url(merged)
            if not code or not url:
                continue
            before = len(self._third_party_emotes)
            self._remember_emote(code, url, '7tv', animated)
            if len(self._third_party_emotes) > before:
                added += 1
        return added

    def _fetch_7tv_emotes(self, channel_id: str) -> None:
        for url in SEVENTV_GLOBAL_URLS:
            try:
                if self._store_7tv_rows(self._iter_7tv_emote_rows(self._http_get_json(url))):
                    break
            except Exception:
                continue

        for url_tmpl in SEVENTV_USER_URLS:
            try:
                data = self._http_get_json(url_tmpl.format(channel_id=urllib.parse.quote(channel_id)))
            except Exception:
                continue

            emotes = self._iter_7tv_emote_rows(data)
            if emotes:
                self._store_7tv_rows(emotes)
                return

            set_id = self._extract_7tv_emote_set_id(data)
            if not set_id:
                continue

            for set_url in SEVENTV_EMOTE_SET_URLS:
                try:
                    emotes = self._iter_7tv_emote_rows(self._http_get_json(set_url.format(set_id=urllib.parse.quote(set_id))))
                except Exception:
                    continue
                if emotes:
                    self._store_7tv_rows(emotes)
                    return

    def _ensure_third_party_emotes(self, host: PluginHost, headers: dict[str, str], channel_id: str) -> None:
        now = time.monotonic()
        if (
            self._third_party_emotes_loaded_for == channel_id
            and (now - self._third_party_emotes_loaded_at) < EMOTE_REFRESH_SECONDS
            and (self._third_party_emotes or self._official_named_emotes)
        ):
            return
        self._third_party_emotes = {}
        self._official_named_emotes = {}
        self._emote_source_counts = {'official': 0, '7tv': 0, 'bttv': 0, 'ffz': 0}
        self._fetch_official_twitch_emotes(headers, channel_id, host)
        self._fetch_7tv_emotes(channel_id)
        self._fetch_bttv_emotes(channel_id)
        self._fetch_ffz_emotes(channel_id)
        self._third_party_emotes_loaded_for = channel_id
        self._third_party_emotes_loaded_at = now
        try:
            host.log(
                self.plugin_id,
                f"Loaded emotes for Twitch channel {channel_id}: official={self._emote_source_counts.get('official', 0)}, 7tv={self._emote_source_counts.get('7tv', 0)}, bttv={self._emote_source_counts.get('bttv', 0)}, ffz={self._emote_source_counts.get('ffz', 0)}."
            )
        except Exception:
            pass
    def _parse_twitch_emotes_tag(self, emotes_tag: str, message_text: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if not emotes_tag or not message_text:
            return results
        for part in emotes_tag.split('/'):
            if not part or ':' not in part:
                continue
            emote_id, ranges_part = part.split(':', 1)
            emote_id = emote_id.strip()
            if not emote_id:
                continue
            for range_part in ranges_part.split(','):
                if '-' not in range_part:
                    continue
                try:
                    start_s, end_s = range_part.split('-', 1)
                    start = int(start_s)
                    end = int(end_s)
                except Exception:
                    continue
                if start < 0 or end < start or end >= len(message_text):
                    continue
                token = message_text[start:end + 1]
                results.append({
                    'start': start,
                    'end': end,
                    'token': token,
                    'html': self._build_img_html((self._get_named_emote(token) or {}).get('url') or self._twitch_emote_url(emote_id), token, bool((self._get_named_emote(token) or {}).get('animated'))),
                })
        results.sort(key=lambda item: (item['start'], item['end']))
        return results
    def _build_overlay_html(self, message_text: str, tags: dict[str, str]) -> str:
        if not message_text:
            return ''
        native = self._parse_twitch_emotes_tag(tags.get('emotes', ''), message_text)
        native_map = {item['start']: item for item in native}
        html_parts: list[str] = []
        idx = 0
        limit = len(message_text)
        while idx < limit:
            native_item = native_map.get(idx)
            if native_item is not None:
                html_parts.append(native_item['html'])
                idx = native_item['end'] + 1
                continue
            if message_text[idx] == ':':
                match = _COLON_EMOTE_RE.match(message_text, idx)
                if match:
                    wrapped = match.group(0)
                    inner = match.group(1)
                    emote = self._get_named_emote(wrapped) or self._get_named_emote(inner)
                    if emote:
                        html_parts.append(self._build_img_html(str(emote.get('url') or ''), inner, bool(emote.get('animated'))))
                        idx = match.end()
                        continue
            matched = False
            chunk = message_text[idx:idx + 512]
            for part in _BOUNDARY_SPLIT_RE.split(chunk):
                if part == '':
                    continue
                if part.isspace():
                    html_parts.append(html.escape(part).replace('\n', '<br>'))
                    idx += len(part)
                    matched = True
                    break
                emote = self._get_named_emote(part)
                if emote:
                    html_parts.append(self._build_img_html(str(emote.get('url') or ''), part, bool(emote.get('animated'))))
                else:
                    html_parts.append(html.escape(part))
                idx += len(part)
                matched = True
                break
            if not matched:
                html_parts.append(html.escape(message_text[idx]))
                idx += 1
        joined = ''.join(html_parts)
        return f'<div style="text-align:left;white-space:normal;line-height:1.08;margin:0;padding:0;">{joined}</div>'
    def test_connection(self, settings):
        # Like kick_chat: resolve effective runtime data from the central host first,
        # then use plugin-local values only as non-empty fallback.
        settings = self._effective_settings(settings, getattr(self, '_host', None))
        channel = self._clean_channel(settings.get('channel', ''))
        if not channel:
            return False, 'Missing Twitch main account / live channel in Plattformen.'
        if not self._as_bool(settings.get('read_enabled'), True):
            return False, 'Twitch reading is disabled in Plattformen.'
        ok, username, auth_msg, cache = self._resolve_auth(settings, allow_oauth=False)
        if not ok:
            return False, auth_msg
        token = self._clean_token(cache.get('access_token') or '')
        if not username:
            username = self._clean_username(settings.get('username', ''))
        if not username or not token:
            return False, 'Token ok, but username could not be resolved.'
        try:
            metrics = self._fetch_metrics(settings, cache, channel)
            metric_text = (
                f"live={'yes' if metrics.get('is_live') else 'no'} | "
                f"viewers={self._to_int(metrics.get('viewer_count')) or 0} | "
                f"followers={self._to_int(metrics.get('followers_count')) if metrics.get('followers_count') is not None else 'unknown'}"
            )
        except Exception as exc:
            metric_text = f'metrics unavailable: {exc}'
        sock = None
        try:
            sock = self._connect_socket(username, token, channel)
            ok2, msg2 = self._handshake(sock)
            if ok2:
                return True, f'{auth_msg} {msg2} | {metric_text}'
            return False, msg2
        except Exception as exc:
            return False, f'Connection failed: {exc}'
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
    def stop(self, *args, **kwargs) -> None:
        try:
            super().stop(*args, **kwargs)
        except TypeError:
            super().stop()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        self._current_channel = ''
        self._active_account = ''

    def is_connected(self) -> bool:
        return self._sock is not None

    def active_account(self) -> str:
        return self._active_account or 'main'

    def send_message(self, message: str, settings: dict | None = None, host: PluginHost | None = None):
        text = self._normalize_chat_text(str(message or '')).replace('\r', ' ').replace('\n', ' ').strip()
        if not text:
            return False, 'Twitch message is empty.'
        channel = self._current_channel or self._clean_channel((settings or {}).get('channel', ''))
        if not channel:
            return False, 'Twitch channel is unknown.'
        sock = self._sock
        if sock is None:
            return False, 'Twitch IRC is not connected.'
        if len(text) > 450:
            text = text[:447].rstrip() + '...'
        try:
            with self._send_lock:
                sock.sendall(f'PRIVMSG #{channel} :{text}\r\n'.encode('utf-8'))
            return True, f'Twitch message sent to #{channel}.'
        except Exception as exc:
            return False, f'Twitch send failed: {exc}'

    def run(self, settings, host: PluginHost):
        self._host = host
        base_settings = dict(settings or {})
        settings = self._effective_settings(base_settings, host)
        channel = self._clean_channel(settings.get('channel', ''))
        if not channel:
            raise RuntimeError('Missing Twitch main account / live channel in Plattformen.')
        if not self._as_bool(settings.get('read_enabled'), True):
            raise RuntimeError('Twitch reading is disabled in Plattformen.')
        ok, username, auth_msg, cache = self._resolve_auth(settings, allow_oauth=False)
        if not ok:
            raise RuntimeError(auth_msg)
        self._active_account = str(cache.get('auth_account') or 'main').strip().lower() or 'main'
        self._last_viewer_count = None
        self._last_followers_count = None
        self._last_is_live = None
        self._last_metrics_poll = 0.0
        self._last_valid_live_viewers = None
        self._known_follower_ids = set()
        self._followers_initialized = False
        self._processed_usernotice_ids = set()
        self._processed_join_names = set()
        self._processed_join_seen_at = {}
        try:
            broadcaster_id, _ = self._resolve_broadcaster(settings, cache, channel)
            headers = self._helix_headers(settings, cache)
            self._ensure_third_party_emotes(host, headers, broadcaster_id)
        except Exception as exc:
            host.log(self.plugin_id, f'Emote cache warning: {exc}')
        host.log(self.plugin_id, auth_msg)
        reconnect_delay = 3.0
        while not self._stop.is_set():
            buffer = ''
            empty_reads = 0
            try:
                # Like kick_chat: refresh central host settings before each reconnect,
                # because OAuth/account values can change in Plattformen while the plugin runs.
                settings = self._effective_settings(base_settings, host)
                new_channel = self._clean_channel(settings.get('channel', ''))
                if new_channel and new_channel != channel:
                    channel = new_channel
                    self._third_party_emotes_loaded_for = ''
                ok_auth, username, auth_msg, cache = self._refresh_runtime_auth(settings, cache)
                if not ok_auth:
                    raise RuntimeError(auth_msg)
                self._active_account = str(cache.get('auth_account') or self._active_account or 'main').strip().lower() or 'main'
                token = self._clean_token(cache.get('access_token') or '')
                if not username:
                    username = self._clean_username(settings.get('username', ''))
                if not username or not token:
                    raise RuntimeError('Missing username or access token.')
                host.set_status(self.plugin_id, PluginStatus('connecting', f'Connecting to #{channel}...'))
                self._sock = self._connect_socket(username, token, channel)
                ok2, message = self._handshake(self._sock)
                if not ok2:
                    raise RuntimeError(message)
                reconnect_delay = 3.0
                host.set_status(self.plugin_id, PluginStatus('connected', f'Reading #{channel} as {username}'))
                self._current_channel = channel
                self._maybe_poll_metrics(host, settings, cache, channel, force=True)
                while not self._stop.is_set():
                    try:
                        self._maybe_poll_metrics(host, settings, cache, channel)
                        data = self._sock.recv(4096)
                        if not data:
                            empty_reads += 1
                            if empty_reads >= 3:
                                raise ConnectionError('Twitch IRC closed the socket.')
                            time.sleep(0.2)
                            continue
                        empty_reads = 0
                        buffer += data.decode('utf-8', errors='ignore')
                        while '\r\n' in buffer:
                            line, buffer = buffer.split('\r\n', 1)
                            if not line:
                                continue
                            if line.startswith('PING'):
                                self._sock.sendall(b'PONG :tmi.twitch.tv\r\n')
                                continue
                            low = line.lower()
                            if line.startswith('RECONNECT'):
                                raise ConnectionError('Twitch IRC requested reconnect.')
                            if 'authentication failed' in low or 'improperly formatted auth' in low or 'login authentication failed' in low:
                                raise RuntimeError('IRC login failed. Check token / OAuth app.')
                            if ' JOIN ' in line:
                                try:
                                    self._handle_join_event(host, settings, channel, username, line)
                                except Exception as exc:
                                    host.log(self.plugin_id, f'JOIN parse warning: {exc}')
                                continue
                            if ' USERNOTICE ' in line:
                                try:
                                    tags, _line_no_tags = self._parse_irc_tags(line)
                                    self._handle_usernotice(host, tags, channel)
                                except Exception as exc:
                                    host.log(self.plugin_id, f'USERNOTICE parse warning: {exc}')
                                continue
                            if 'PRIVMSG' in line:
                                try:
                                    tags, line_no_tags = self._parse_irc_tags(line)
                                    prefix, rest = line_no_tags[1:].split(' ', 1)
                                    sender = prefix.split('!', 1)[0]
                                    display_name = self._unescape_tag(tags.get('display-name') or sender) or sender
                                    message_text = rest.split(' :', 1)[1] if ' :' in rest else ''
                                    message_text = self._normalize_chat_text(message_text)
                                    bits = self._to_int(tags.get('bits'))
                                    if bits and bits > 0:
                                        suffix = f': {message_text}' if message_text else ''
                                        self._emit_alert(host, channel, display_name, f'cheered {bits} Bits{suffix}', 'twitch_cheer')
                                    if self._handle_test_alert_command(host, channel, display_name, message_text):
                                        continue
                                    if self._looks_like_placeholder_chat(message_text):
                                        continue
                                    overlay_html = self._build_overlay_html(message_text, tags)
                                    host.emit_message(self.plugin_id, {
                                        'platform': 'twitch',
                                        'username': display_name,
                                        'display_name': display_name,
                                        'text': message_text,
                                        'message': message_text,
                                        'content': message_text,
                                        'overlay_html': overlay_html,
                                        'channel': channel,
                                        'message_id': tags.get('id') or '',
                                        'user_id': tags.get('user-id') or '',
                                        'raw_tags': dict(tags),
                                        'message_type': 'chat',
                                        'type': 'chat',
                                        'event_type': 'chat',
                                        'source_plugin_id': self.plugin_id,
                                        'source': self.plugin_id,
                                        'show_in_desktop': True,
                                        'show_in_obs': True,
                                    })
                                except Exception as exc:
                                    host.log(self.plugin_id, f'Parse warning: {exc}')
                    except socket.timeout:
                        continue
            except Exception as exc:
                if self._stop.is_set():
                    break
                host.log(self.plugin_id, f'Connection warning: {exc}')
                host.set_status(self.plugin_id, PluginStatus('connecting', f'Reconnecting to #{channel}...'))
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 20.0)
                continue
            finally:
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None
                self._current_channel = ''
            break
        host.set_status(self.plugin_id, PluginStatus('disconnected', 'IRC stopped.'))
def create_plugin():
    return TwitchChatPlugin()
