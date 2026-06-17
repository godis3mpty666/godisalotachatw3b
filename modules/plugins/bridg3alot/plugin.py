from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

_PLUGIN_IMPORT_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_IMPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_IMPORT_DIR))

from shared.models import PluginStatus
from shared.plugin_base import ProviderPlugin, PluginHost

from common import as_bool, clean_text, strip_response
from platform_outputs import PlatformOutputs

PLUGIN_VERSION = '1.0.2'
PLUGIN_NAME = f'bridg3alot ver. {PLUGIN_VERSION}'
PLUGIN_DIR = Path(__file__).resolve().parent


def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return PLUGIN_DIR / 'data'


DATA_DIR = _main_data_dir('bridg3alot')
OLD_BOTALOT_DATA_DIR = _main_data_dir('botalot')


class Bridg3alotPlugin(ProviderPlugin):
    plugin_id = 'bridg3alot'
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = 'Standalone chatbridge for Twitch, TikTok, YouTube and Kick.'

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._enabled = False
        self._outputs = PlatformOutputs(PLUGIN_DIR, lambda: self._host, self._log)
        self._recent_message_lock = threading.Lock()
        self._recent_messages: dict[str, float] = {}
        self._recent_outbound_lock = threading.Lock()
        self._recent_outbound: dict[str, float] = {}

    def settings_schema(self) -> list[dict[str, Any]]:
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
            {'key': 'section_overview', 'type': 'separator', 'label': 'bridg3alot ver. 1.0.2 - Chatbridge', 'label_en': 'bridg3alot ver. 1.0.2 - Chatbridge'},
            {'key': 'enabled', 'label': 'Plugin aktiv', 'label_en': 'Plugin enabled', 'type': 'bool'},
            {'key': 'bridge_enabled', 'label': 'Chatbridge aktiv', 'label_en': 'Chatbridge enabled', 'type': 'bool'},
            {'key': 'bridge_only_when_write_enabled', 'label': 'Nur an aktive/schreibbare Zielplattformen senden', 'label_en': 'Only send to active/writable target platforms', 'type': 'bool'},
            {'key': 'bridge_prefix_format', 'label': 'Standard-Bridge-Format', 'placeholder': '{platform}-Message from {user}: {text}', 'help': 'Platzhalter: {platform}, {user}, {text}', 'help_en': 'Placeholders: {platform}, {user}, {text}'},
            {'key': 'bridge_format_twitch', 'label': 'Format für Twitch-Nachrichten', 'placeholder': '{platform}-Message from {user}: {text}', 'help': 'Leer lassen = Standard-Bridge-Format'},
            {'key': 'bridge_format_tiktok', 'label': 'Format für TikTok-Nachrichten', 'placeholder': '{platform}-Message from {user}: {text}', 'help': 'Leer lassen = Standard-Bridge-Format'},
            {'key': 'bridge_format_youtube', 'label': 'Format für YouTube-Nachrichten', 'placeholder': '{platform}-Message from {user}: {text}', 'help': 'Leer lassen = Standard-Bridge-Format'},
            {'key': 'bridge_format_kick', 'label': 'Format für Kick-Nachrichten', 'placeholder': '{platform}-Message from {user}: {text}', 'help': 'Leer lassen = Standard-Bridge-Format'},
        ], en='Overview')
        schema += tab('Routen', [
            {'key': 'section_routes', 'type': 'separator', 'label': 'Plattformen bridgen', 'label_en': 'Bridge platforms'},
            {'key': 'bridge_twitch', 'label': 'Twitch', 'type': 'bool'},
            {'key': 'bridge_tiktok', 'label': 'TikTok', 'type': 'bool'},
            {'key': 'bridge_youtube', 'label': 'YouTube', 'type': 'bool'},
            {'key': 'bridge_kick', 'label': 'Kick', 'type': 'bool'},
        ], en='Routes')
        return schema

    def default_settings(self) -> dict[str, Any]:
        return {
            'enabled': True,
            'bridge_enabled': True,
            'bridge_twitch': True,
            'bridge_tiktok': True,
            'bridge_youtube': True,
            'bridge_kick': True,
            'bridge_twitch_to_tiktok': True,
            'bridge_twitch_to_youtube': True,
            'bridge_twitch_to_kick': True,
            'bridge_tiktok_to_twitch': True,
            'bridge_tiktok_to_youtube': True,
            'bridge_tiktok_to_kick': True,
            'bridge_youtube_to_twitch': True,
            'bridge_youtube_to_tiktok': True,
            'bridge_youtube_to_kick': True,
            'bridge_kick_to_twitch': True,
            'bridge_kick_to_tiktok': True,
            'bridge_kick_to_youtube': True,
            'bridge_only_when_write_enabled': True,
            'bridge_prefix_format': '{platform}-Message from {user}: {text}',
            'bridge_format_twitch': '',
            'bridge_format_tiktok': '',
            'bridge_format_youtube': '',
            'bridge_format_kick': '',
            'twitch_connection_status': '⚪ inaktiv',
            'tiktok_connection_status': '⚪ inaktiv',
            'youtube_connection_status': '⚪ inaktiv',
            'kick_connection_status': '⚪ inaktiv',
            'read_twitch': True,
            'read_tiktok': True,
            'read_youtube': True,
            'read_kick': True,
            'write_twitch': True,
            'write_tiktok': True,
            'write_youtube': True,
            'write_kick': True,
        }

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._settings = settings if isinstance(settings, dict) else dict(settings or {})
        self._migrate_old_botalot_bridge_settings(self._settings)
        self._apply_platform_settings(self._settings)
        self._enabled = as_bool(self._settings.get('enabled'), True)
        host.set_status(self.plugin_id, PluginStatus('connected' if self._enabled else 'disabled', f'{PLUGIN_NAME}: ' + ('aktiv' if self._enabled else 'deaktiviert')))
        host.log(self.plugin_id, f'{PLUGIN_NAME} gestartet. Bridge: ' + ('aktiv' if as_bool(self._settings.get('bridge_enabled'), True) else 'aus'))

    def stop(self, *args, **kwargs) -> None:
        self._enabled = False
        if self._host is not None:
            self._host.set_status(self.plugin_id, PluginStatus('stopped', 'Stopped'))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        cfg = self._settings_with_platforms(settings)
        if not as_bool(cfg.get('enabled'), True):
            return True, f'{PLUGIN_NAME} ist deaktiviert.'
        if not as_bool(cfg.get('bridge_enabled'), True):
            return True, 'Chatbridge ist deaktiviert.'
        active = []
        for p in ('twitch', 'tiktok', 'youtube', 'kick'):
            if self._target_write_available(cfg, p):
                active.append(p)
        return True, 'Schreibbare Ziele: ' + (', '.join(active) if active else 'keine')

    def _log(self, *parts: Any) -> None:
        msg = ' '.join(str(p) for p in parts if p is not None)
        if self._host is not None:
            try:
                self._host.log(self.plugin_id, msg)
                return
            except Exception:
                pass
        print(f'[{self.plugin_id}] {msg}')

    def _migrate_old_botalot_bridge_settings(self, target: dict[str, Any]) -> None:
        """Best-effort migration for users that configured the bridge in botalot.

        The main settings usually pass only this plugin's own values. To avoid making
        users rebuild the whole route matrix, copy old botalot bridge fields when
        bridg3alot still has its defaults/empty values.
        """
        old: dict[str, Any] = {}
        try:
            p = OLD_BOTALOT_DATA_DIR / 'settings.json'
            if p.exists():
                loaded = json.loads(p.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    old.update(loaded)
        except Exception:
            pass
        try:
            current = Path(__file__).resolve()
            data_root = None
            for parent in current.parents:
                if parent.name.lower() == 'modules':
                    data_root = parent.parent / 'data'
                    break
            if data_root is not None:
                main_settings = data_root / 'settings.json'
                if main_settings.exists():
                    loaded = json.loads(main_settings.read_text(encoding='utf-8'))
                    botalot = ((loaded or {}).get('plugins') or {}).get('botalot')
                    if isinstance(botalot, dict):
                        old.update(botalot)
        except Exception:
            pass
        if not old:
            return
        for key in list(self.default_settings().keys()):
            if not key.startswith('bridge_'):
                continue
            if key in old and (key not in target or target.get(key) in (None, '')):
                target[key] = old.get(key)

    def _host_platform_settings(self, platform: str | None = None) -> dict[str, Any]:
        host = self._host
        if host is None:
            return {}
        for name in ('get_platform_settings', 'platform_settings'):
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

    def _clean_account_name(self, value: Any) -> str:
        raw = str(value or '').strip()
        if raw.startswith('http://') or raw.startswith('https://'):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(raw)
                if 'tiktok.com' in parsed.netloc.lower() and '/@' in parsed.path:
                    return parsed.path.split('/@', 1)[1].split('/', 1)[0].lstrip('@').strip()
            except Exception:
                pass
        return raw.lstrip('@').strip().strip('/')

    def _apply_platform_settings(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        target = settings if isinstance(settings, dict) else self._settings
        if not isinstance(target, dict):
            target = {}
        platforms = self._host_platform_settings(None)
        if not isinstance(platforms, dict) or not platforms:
            for key in ('twitch', 'tiktok', 'youtube', 'kick'):
                target[f'{key}_connection_status'] = '⚪ inaktiv'
            return target

        tw = platforms.get('twitch') if isinstance(platforms.get('twitch'), dict) else {}
        if tw:
            target.update({
                'read_twitch': self._platform_bool(tw, 'read_enabled', 'read', default=True),
                'write_twitch': self._platform_bool(tw, 'write_enabled', 'write', default=True),
            })
            target['twitch_connection_status'] = self._status_from_platform('twitch')

        tt = platforms.get('tiktok') if isinstance(platforms.get('tiktok'), dict) else {}
        if tt:
            target.update({
                'read_tiktok': self._platform_bool(tt, 'read_enabled', 'read', default=True),
                'write_tiktok': self._platform_bool(tt, 'write_enabled', 'write', default=True),
            })
            target['tiktok_connection_status'] = self._status_from_platform('tiktok')

        yt = platforms.get('youtube') if isinstance(platforms.get('youtube'), dict) else {}
        if yt:
            target.update({
                'read_youtube': self._platform_bool(yt, 'read_enabled', 'read', default=True),
                'write_youtube': self._platform_bool(yt, 'write_enabled', 'write', default=True),
            })
            target['youtube_connection_status'] = self._status_from_platform('youtube')

        kc = platforms.get('kick') if isinstance(platforms.get('kick'), dict) else {}
        if kc:
            target.update({
                'read_kick': self._platform_bool(kc, 'read_enabled', 'read', default=True),
                'write_kick': self._platform_bool(kc, 'write_enabled', 'write', default=True),
            })
            target['kick_connection_status'] = self._status_from_platform('kick')

        return target

    def _settings_with_platforms(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        base = dict(settings or self._settings or {})
        return self._apply_platform_settings(base)

    def _current_settings(self) -> dict[str, Any]:
        host = self._host
        state = getattr(host, 'state', None) if host is not None else None
        getter = getattr(state, 'plugin_settings', None) if state is not None else None
        if callable(getter):
            try:
                fresh = getter(self.plugin_id, self)
                if isinstance(fresh, dict):
                    self._settings.update(fresh)
            except Exception:
                pass
        return self._settings_with_platforms(self._settings)

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
                    state = getattr(host, 'state', None)
                    instances = getattr(state, 'plugin_instances', {}) if state is not None else {}
                    plugin = instances.get(plugin_id) if isinstance(instances, dict) else None
                except Exception:
                    plugin = None
            if plugin is not None:
                return plugin
        return None

    def _host_plugin_is_active(self, *plugin_ids: str) -> bool:
        plugin = self._host_plugin_object(*plugin_ids)
        if plugin is None:
            return False
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

    def _host_plugin_runtime_state(self, *plugin_ids: str) -> str:
        host = self._host
        state = getattr(host, 'state', None) if host is not None else None
        plugin_status = getattr(state, 'plugin_status', {}) if state is not None else {}
        if not isinstance(plugin_status, dict):
            return ''
        for plugin_id in plugin_ids:
            item = plugin_status.get(plugin_id)
            value = getattr(item, 'state', None) or getattr(item, 'status', None)
            if value:
                return str(value).strip().lower()
            if isinstance(item, dict):
                value = item.get('state') or item.get('status')
                if value:
                    return str(value).strip().lower()
        return ''

    def _platform_plugin_ids(self, key: str) -> tuple[str, ...]:
        return {
            'twitch': ('twitch_chat',),
            'tiktok': ('tiktok_chat', 'tiktok_live'),
            'youtube': ('youtube_chat', 'youtube_live'),
            'kick': ('kick_chat',),
        }.get(str(key or '').lower(), ())

    def _status_from_platform(self, platform: str) -> str:
        pids = self._platform_plugin_ids(platform)
        if not self._host_plugin_is_active(*pids):
            runtime_state = self._host_plugin_runtime_state(*pids)
            if runtime_state in {'connected', 'running', 'ready'}:
                return '✅ verbunden'
            if runtime_state in {'connecting', 'starting'}:
                return '🟡 verbindet'
            return '⚪ inaktiv'
        if self._host_plugin_is_connected(*pids):
            return '✅ verbunden'
        runtime_state = self._host_plugin_runtime_state(*pids)
        if runtime_state in {'connected', 'running', 'ready'}:
            return '✅ verbunden'
        if runtime_state in {'connecting', 'starting'}:
            return '🟡 verbindet'
        pdata = self._host_platform_settings(platform)
        raw = str(pdata.get('connection_status') or '').strip() if isinstance(pdata, dict) else ''
        if raw:
            return raw
        return '🟡 aktiv, aber nicht verbunden'

    def _normalize_platform(self, value: Any) -> str:
        p = str(value or '').strip().lower()
        if p in {'tt', 'tiktok_chat', 'tiktok_live'}:
            return 'tiktok'
        if p == 'twitch_chat':
            return 'twitch'
        if p in {'youtube_live', 'youtube_chat', 'yt'}:
            return 'youtube'
        if p == 'kick_chat':
            return 'kick'
        return p

    def _message_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return clean_text(payload.get('text') or payload.get('message') or payload.get('content') or payload.get('comment') or payload.get('body') or '')
        return clean_text(getattr(payload, 'text', '') or getattr(payload, 'message', '') or getattr(payload, 'content', '') or getattr(payload, 'comment', '') or getattr(payload, 'body', '') or '')

    def _message_username(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return clean_text(payload.get('username') or payload.get('display_name') or payload.get('user') or payload.get('nickname') or payload.get('unique_id') or '')
        return clean_text(getattr(payload, 'username', '') or getattr(payload, 'display_name', '') or getattr(payload, 'user', '') or getattr(payload, 'nickname', '') or getattr(payload, 'unique_id', '') or '')

    def _message_channel(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return clean_text(payload.get('channel') or '')
        return clean_text(getattr(payload, 'channel', '') or '')

    def _message_platform(self, plugin_id: str, payload: Any) -> str:
        raw = ''
        if isinstance(payload, dict):
            raw = str(payload.get('platform') or payload.get('source_plugin_id') or payload.get('source') or plugin_id or '')
        else:
            raw = str(getattr(payload, 'platform', '') or getattr(payload, 'source_plugin_id', '') or getattr(payload, 'source', '') or plugin_id or '')
        return self._normalize_platform(raw)

    def _message_type(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return str(payload.get('message_type') or payload.get('type') or payload.get('event_type') or 'chat').strip().lower()
        return str(getattr(payload, 'message_type', '') or getattr(payload, 'type', '') or getattr(payload, 'event_type', '') or 'chat').strip().lower()

    def _message_key(self, platform: str, username: str, text: str) -> str:
        return f'{self._normalize_platform(platform)}|{str(username or "").strip().lower()}|{clean_text(text).lower()}'

    def _is_recent_duplicate(self, platform: str, username: str, text: str, ttl: float = 10.0) -> bool:
        now = time.time()
        key = self._message_key(platform, username, text)
        with self._recent_message_lock:
            for k, expires in list(self._recent_messages.items()):
                if expires < now:
                    self._recent_messages.pop(k, None)
            if self._recent_messages.get(key, 0.0) >= now:
                return True
            self._recent_messages[key] = now + max(1.0, ttl)
            return False

    def _remember_outbound(self, platform: str, username: str, text: str, ttl: float = 45.0) -> None:
        key = self._message_key(platform, username, text)
        with self._recent_outbound_lock:
            self._recent_outbound[key] = time.time() + max(1.0, ttl)

    def _is_recent_outbound_echo(self, platform: str, username: str, text: str) -> bool:
        now = time.time()
        key = self._message_key(platform, username, text)
        with self._recent_outbound_lock:
            for k, expires in list(self._recent_outbound.items()):
                if expires < now:
                    self._recent_outbound.pop(k, None)
            return self._recent_outbound.get(key, 0.0) >= now

    def _is_echo_text(self, text: str) -> bool:
        low_text = str(text or '').strip().lower()
        bridge_prefixes = (
            'tt-message from ', 'tiktok-message from ', 'twitch-message from ',
            'youtube-message from ', 'kick-message from ',
            'tt-ai answer to ', 'tiktok-ai answer to ', 'twitch-ai answer to ',
            'youtube-ai answer to ', 'kick-ai answer to ',
        )
        return low_text.startswith(bridge_prefixes)

    def _is_service_command(self, text: str) -> bool:
        low = clean_text(text).lower().strip()
        return any(low == cmd or low.startswith(cmd + ' ') for cmd in ('!sr', '!sr+', '!yt'))

    def _is_gamepicker_system_text(self, text: str) -> bool:
        raw = str(text or '').strip()
        low_text = raw.lower()
        if '\u2063\u200b\u2063\u200b\u2063' in raw or '\u2063gam3pick3r-system\u2063' in raw:
            return True
        return any(phrase in low_text for phrase in ('the community has crowned ', 'the random picker chose '))

    def on_message(self, msg: Any) -> None:
        if not self._enabled:
            return
        msg_type = self._message_type(msg)
        if msg_type not in {'chat', 'message', 'comment'}:
            return
        platform = self._message_platform('', msg)
        username = self._message_username(msg)
        text = self._message_text(msg)
        channel = self._message_channel(msg)
        if not platform or platform not in {'twitch', 'tiktok', 'youtube', 'kick'} or not text:
            return
        if self._is_recent_outbound_echo(platform, username, text) or self._is_echo_text(text):
            return
        if self._is_recent_duplicate(platform, username, text, ttl=12.0):
            return
        settings = self._current_settings()
        if not self._should_read_platform(settings, platform):
            return
        self._maybe_bridge_message_async(settings, platform, username, text, channel)

    def _should_read_platform(self, settings: dict[str, Any], platform: str) -> bool:
        p = self._normalize_platform(platform)
        if not self._bridge_platform_enabled(settings, p):
            return False
        if p == 'tiktok':
            return as_bool(settings.get('read_tiktok'), True)
        if p == 'twitch':
            return as_bool(settings.get('read_twitch'), True)
        if p == 'youtube':
            return as_bool(settings.get('read_youtube'), True)
        if p == 'kick':
            return as_bool(settings.get('read_kick'), True)
        return False

    def _bridge_platform_enabled(self, settings: dict[str, Any], platform: str) -> bool:
        p = self._normalize_platform(platform)
        if p not in {'twitch', 'tiktok', 'youtube', 'kick'}:
            return False
        return as_bool(settings.get(f'bridge_{p}'), True)

    def _target_write_available(self, settings: dict[str, Any], target: str) -> bool:
        target = self._normalize_platform(target)
        if not self._bridge_platform_enabled(settings, target):
            return False
        pdata = self._host_platform_settings(target)
        platform_enabled = True
        if isinstance(pdata, dict) and 'enabled' in pdata:
            platform_enabled = as_bool(pdata.get('enabled'), False)
            if target == 'tiktok' and not platform_enabled:
                platform_enabled = bool(pdata.get('main_login_ok') or pdata.get('bot_login_ok'))
        if not platform_enabled:
            return False
        if target == 'tiktok':
            return as_bool(settings.get('write_tiktok'), False)
        if target == 'twitch':
            if isinstance(pdata, dict):
                has_token = any(str(pdata.get(k) or '').strip() for k in ('access_token', 'refresh_token', 'main_access_token', 'main_refresh_token'))
                has_channel = any(str(pdata.get(k) or '').strip() for k in ('channel', 'main_account', 'main', 'broadcaster_user_id', 'broadcaster_id'))
                if has_token and has_channel:
                    return as_bool(settings.get('write_twitch'), True)
            return as_bool(settings.get('write_twitch'), False)
        if target == 'youtube':
            if isinstance(pdata, dict):
                has_token = any(str(pdata.get(k) or '').strip() for k in ('access_token', 'refresh_token', 'main_access_token', 'main_refresh_token'))
                has_channel = any(str(pdata.get(k) or '').strip() for k in ('main_channel_id', 'broadcaster_channel_id', 'main_account', 'channel'))
                if has_token and has_channel:
                    return as_bool(settings.get('write_youtube'), True)
            return as_bool(settings.get('write_youtube'), False)
        if target == 'kick':
            if isinstance(pdata, dict):
                has_token = any(str(pdata.get(k) or '').strip() for k in ('access_token', 'refresh_token', 'main_access_token', 'main_refresh_token'))
                has_channel = any(str(pdata.get(k) or '').strip() for k in ('broadcaster_user_id', 'channel_id', 'main_user_id', 'channel_slug', 'main_account', 'channel'))
                if has_token and has_channel:
                    return as_bool(settings.get('write_kick'), True)
            return as_bool(settings.get('write_kick'), False)
        return False

    def _platform_has_kick_send_access(self, settings: dict[str, Any] | None = None) -> bool:
        return as_bool((settings or self._settings or {}).get('write_kick'), False)

    def _format_for_source_platform(self, settings: dict[str, Any], platform: str) -> str:
        p = self._normalize_platform(platform)
        specific = str(settings.get(f'bridge_format_{p}') or '').strip()
        if specific:
            return specific
        return str(settings.get('bridge_prefix_format') or '{platform}-Message from {user}: {text}')

    def _normalize_bridge_format(self, fmt: str) -> str:
        text = str(fmt or '').strip()
        # Be forgiving for the UI-friendly typo "{user from ...}".
        text = re.sub(r'\{user\s+from\s+', '{user} from ', text, flags=re.IGNORECASE)
        return text

    def _render_bridge_format(self, fmt: str, *, platform_label: str, username: str, text: str) -> str:
        class BridgeFormatValues(dict):
            def __missing__(self, key: str) -> str:
                return str(key)

        values = BridgeFormatValues(platform=platform_label, user=username, text=text)
        normalized = self._normalize_bridge_format(fmt)
        try:
            return normalized.format_map(values)
        except Exception:
            manual = normalized
            for key, value in values.items():
                manual = manual.replace('{' + key + '}', str(value))
            if manual != normalized:
                return manual
            return f'{platform_label}-Message from {username}: {text}'

    def _maybe_bridge_message_async(self, settings: dict[str, Any], source_platform: str, username: str, text: str, source_channel: str = '') -> None:
        if not as_bool(settings.get('bridge_enabled'), True):
            return
        bridge_settings = dict(settings or {})
        threading.Thread(
            target=self._maybe_bridge_message,
            args=(bridge_settings, source_platform, username, text, source_channel),
            daemon=True,
            name='bridg3alot-bridge-send',
        ).start()

    def _maybe_bridge_message(self, settings: dict[str, Any], source_platform: str, username: str, text: str, source_channel: str = '') -> None:
        if not as_bool(settings.get('bridge_enabled'), True):
            return
        p = self._normalize_platform(source_platform)
        if p not in {'twitch', 'tiktok', 'youtube', 'kick'}:
            return
        stripped = clean_text(text)
        if not stripped or self._is_echo_text(stripped):
            return
        if self._is_service_command(stripped):
            return
        if not self._bridge_platform_enabled(settings, p):
            return

        targets: list[str] = []
        for target in ('twitch', 'tiktok', 'youtube', 'kick'):
            if target == p:
                continue
            if self._bridge_platform_enabled(settings, target):
                targets.append(target)
        if not targets:
            return

        fmt = self._format_for_source_platform(settings, p)
        label = self._bridge_platform_label(p)
        bridged_base = self._render_bridge_format(fmt, platform_label=label, username=username, text=stripped)

        for target in targets:
            if as_bool(settings.get('bridge_only_when_write_enabled'), True) and not self._target_write_available(settings, target):
                self._log(f'Bridge {p} → {target} übersprungen: Zielplattform ist nicht aktiv/schreibbar.')
                continue

            bridged = bridged_base if target == 'tiktok' else strip_response(bridged_base, 240)

            if target == 'tiktok':
                parts = self._split_tiktok_outgoing_message(bridged, 150)
                total = len(parts)
                for idx, part in enumerate(parts, 1):
                    self._remember_outbound(target, self._bot_name_for_platform(settings, target), part)
                    ok = self._outputs.send_to_platform(settings, part, target)
                    if ok:
                        self._log(f'Bridge {p} → {target}' + (f' ({idx}/{total})' if total > 1 else '') + f': {part}')
                    else:
                        self._log(f'Bridge {p} → {target} fehlgeschlagen' + (f' ({idx}/{total})' if total > 1 else '') + f': {part}')
                    if total > 1 and idx < total:
                        time.sleep(0.25)
                continue

            self._remember_outbound(target, self._bot_name_for_platform(settings, target), bridged)
            ok = self._outputs.send_to_platform(settings, bridged, target)
            if ok:
                self._log(f'Bridge {p} → {target}: {bridged}')
            else:
                self._log(f'Bridge {p} → {target} fehlgeschlagen: {bridged}')

    def _split_tiktok_outgoing_message(self, text: str, limit: int = 150) -> list[str]:
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
            for word in words:
                add = word if not out else ' ' + word
                if len(out) + len(add) <= cap:
                    out += add
                    continue
                break
            if out:
                return out.strip(), value[len(out):].strip()
            return value[:cap].strip(), value[cap:].strip()

        def split_fixed(value: str, cap: int) -> list[str]:
            parts: list[str] = []
            rest = str(value or '').strip()
            while rest:
                part, rest = split_words(rest, cap)
                if not part:
                    part, rest = rest[:cap], rest[cap:].strip()
                parts.append(part)
            return parts

        prefix = ''
        body = msg
        m = re.match(r'^((?:TT|TikTok|Twitch|YouTube|Kick)[_\- ](?:Message from|AI answer to)\s+[^:]{1,80}:\s*)(.*)$', msg, flags=re.IGNORECASE | re.DOTALL)
        if m:
            prefix, body = m.group(1), m.group(2).strip()
        else:
            colon = msg.find(': ')
            if 0 < colon <= 90:
                prefix, body = msg[:colon + 2], msg[colon + 2:].strip()

        if not prefix or len(prefix) >= limit - 10:
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
        out = [(prefix + body_parts[0]).strip()[:limit]]
        for idx, part in enumerate(body_parts[1:], 2):
            marker = f'({idx}/{total}) '
            out.append(marker + str(part or '')[:max(0, limit - len(marker))])
        return [x for x in out if x]

    def _bridge_platform_label(self, platform: str) -> str:
        p = self._normalize_platform(platform)
        if p == 'tiktok':
            return 'TT'
        if p == 'twitch':
            return 'Twitch'
        if p == 'youtube':
            return 'YouTube'
        if p == 'kick':
            return 'Kick'
        return p.capitalize() if p else 'Chat'

    def _bot_name_for_platform(self, settings: dict[str, Any], platform: str) -> str:
        return 'bridg3alot'


def create_plugin() -> Bridg3alotPlugin:
    return Bridg3alotPlugin()
