from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

from al3rtalot_common import EVENT_LABELS, PLATFORM_LABELS, PLATFORMS, alert_html, as_bool, atomic_write_json, main_data_dir, now_ms, to_int
from al3rtalot_overlay_server import AlertOverlayServer, OverlayState
from al3rtalot_platforms import KickAlerts, TikTokAlerts, TwitchAlerts, YouTubeAlerts

PLUGIN_ID = 'al3rtalot'
PLUGIN_VERSION = '0.01'
PLUGIN_NAME = f'al3rtalot ver. {PLUGIN_VERSION}'
DATA_DIR = main_data_dir(PLUGIN_ID, __file__)


class Al3rtalotPlugin(ProviderPlugin):
    plugin_id = PLUGIN_ID
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = 'Alerts für Twitch, TikTok, YouTube und Kick mit getrennten Plattform-Einstellungen.'

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._enabled = False
        self._lock = threading.RLock()
        self._recent: dict[str, float] = {}
        self._overlay_state = OverlayState()
        self._overlay_server: AlertOverlayServer | None = None
        self._platforms = {
            'twitch': TwitchAlerts(self),
            'tiktok': TikTokAlerts(self),
            'youtube': YouTubeAlerts(self),
            'kick': KickAlerts(self),
        }

    def settings_schema(self) -> list[dict[str, Any]]:
        def tab(name: str, rows: list[dict[str, Any]], *, en: str | None = None) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item.setdefault('tab', name)
                item.setdefault('ui_tab', name)
                item.setdefault('category', name)
                if en:
                    item.setdefault('tab_en', en)
                    item.setdefault('ui_tab_en', en)
                out.append(item)
            return out

        schema: list[dict[str, Any]] = []
        schema += tab('Übersicht', [
            {'key': 'section_overview', 'type': 'separator', 'label': f'{PLUGIN_NAME} - Alerts'},
            {'key': 'enabled', 'label': 'Plugin aktiv', 'type': 'bool'},
            {'key': 'status', 'label': 'Status', 'readonly': True, 'placeholder': 'bereit'},
            {'key': 'alert_to_chat_overlay', 'label': 'Alerts zusätzlich in Chat/Overlay ausgeben', 'type': 'bool', 'help': 'Schickt den Alert als HTML-Nachricht an den gemeinsamen Chat/Browserbereich.'},
            {'key': 'ignored_users', 'label': 'Global ignorierte User', 'type': 'taglist', 'wide': True, 'placeholder': 'nightbot, streamelements, ...'},
            {'key': 'dedupe_seconds', 'label': 'Doppelte Alerts blocken (Sekunden)', 'type': 'number', 'min': 0, 'max': 120},
        ], en='Overview')
        schema += tab('Browser-Overlay', [
            {'key': 'section_overlay', 'type': 'separator', 'label': 'Eigenes Alert Browser-Overlay'},
            {'key': 'browser_overlay_enabled', 'label': 'Browser-Overlay aktiv', 'type': 'bool'},
            {'key': 'browser_overlay_port', 'label': 'Overlay Port', 'type': 'number', 'min': 1024, 'max': 65535},
            {'key': 'browser_overlay_url', 'label': 'Overlay URL', 'readonly': True, 'placeholder': 'wird nach Start gesetzt'},
            {'key': 'alert_duration_ms', 'label': 'Alertdauer (ms)', 'type': 'number', 'min': 1000, 'max': 30000},
            {'key': 'button_open_overlay', 'type': 'button', 'label': 'Overlay öffnen', 'button_text': 'Browser-Overlay öffnen'},
            {'key': 'button_test_alert', 'type': 'button', 'label': 'Testalert', 'button_text': 'Testalert anzeigen'},
        ], en='Browser overlay')

        def platform_tab(platform: str, events: tuple[str, ...]) -> list[dict[str, Any]]:
            label = PLATFORM_LABELS[platform]
            rows: list[dict[str, Any]] = [
                {'key': f'section_{platform}', 'type': 'separator', 'label': f'{label} Alerts'},
                {'key': f'{platform}_enabled', 'label': f'{label} aktiv', 'type': 'bool'},
                {'key': f'{platform}_accent_color', 'label': 'Akzentfarbe', 'placeholder': '#ff2d55'},
                {'key': f'{platform}_ignored_users', 'label': 'Ignorierte User nur hier', 'type': 'taglist', 'wide': True},
            ]
            for event in events:
                title = EVENT_LABELS.get(event, event.title())
                rows += [
                    {'key': f'{platform}_enable_{event}', 'label': f'{title} Alerts', 'type': 'bool', 'compact': True},
                    {'key': f'{platform}_{event}_title', 'label': f'{title} Titel', 'placeholder': '{event_label}', 'compact': True},
                    {'key': f'{platform}_{event}_template', 'label': f'{title} Text', 'type': 'template', 'wide': True, 'placeholder': '{user}: {text}', 'tokens': ['{platform}', '{event_label}', '{user}', '{text}', '{amount}', '{channel}']},
                ]
            return tab(label, rows)

        schema += platform_tab('twitch', self._platforms['twitch'].supported_events)
        schema += platform_tab('tiktok', self._platforms['tiktok'].supported_events)
        schema += platform_tab('youtube', self._platforms['youtube'].supported_events)
        schema += platform_tab('kick', self._platforms['kick'].supported_events)
        return schema

    def default_settings(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            'enabled': True,
            'status': 'bereit',
            'alert_to_chat_overlay': True,
            'ignored_users': 'nightbot\nstreamelements\nstreamlabs',
            'dedupe_seconds': 8,
            'browser_overlay_enabled': True,
            'browser_overlay_port': 17642,
            'browser_overlay_url': 'http://127.0.0.1:17642/',
            'alert_duration_ms': 6000,
            'chat_title': '{event_label}',
            'chat_template': '{user}: {text}',
            'follow_title': 'Neuer Follow',
            'follow_template': '{user} folgt jetzt auf {platform}',
            'join_title': 'Join',
            'join_template': '{user} ist im Live',
            'like_title': 'Likes',
            'like_template': '{user} hat {amount} Likes geschickt',
            'gift_title': 'Gift',
            'gift_template': '{user} hat ein Gift geschickt',
            'share_title': 'Share',
            'share_template': '{user} hat den Stream geteilt',
            'subscribe_title': 'Sub',
            'subscribe_template': '{user} hat abonniert',
            'raid_title': 'Raid',
            'raid_template': '{user} raidet den Kanal',
            'member_title': 'Member',
            'member_template': '{user} ist Mitglied geworden',
            'superchat_title': 'Superchat',
            'superchat_template': '{user}: {text}',
        }
        for platform, handler in self._platforms.items():
            defaults[f'{platform}_enabled'] = True
            defaults[f'{platform}_accent_color'] = handler.default_color
            defaults[f'{platform}_ignored_users'] = ''
            for event in handler.supported_events:
                defaults[f'{platform}_enable_{event}'] = True
                defaults[f'{platform}_{event}_title'] = defaults.get(f'{event}_title', '{event_label}')
                defaults[f'{platform}_{event}_template'] = defaults.get(f'{event}_template', '{user}: {text}')
        return defaults

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        merged = self.default_settings()
        if isinstance(settings, dict):
            merged.update(settings)
        self._settings = merged
        self._enabled = as_bool(merged.get('enabled'), True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._start_overlay_if_needed()
        state = 'connected' if self._enabled else 'disabled'
        msg = f'{PLUGIN_NAME}: ' + ('aktiv' if self._enabled else 'deaktiviert')
        host.set_status(self.plugin_id, PluginStatus(state, msg))
        host.log(self.plugin_id, f'{PLUGIN_NAME} gestartet. Plattform-Alerts: Twitch/TikTok/YouTube/Kick.')

    def stop(self, *args, **kwargs) -> None:
        self._enabled = False
        server = self._overlay_server
        self._overlay_server = None
        if server is not None:
            server.stop()
        if self._host is not None:
            self._host.set_status(self.plugin_id, PluginStatus('stopped', 'Stopped'))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        cfg = self._merged_settings(settings)
        enabled = [PLATFORM_LABELS[p] for p in PLATFORMS if as_bool(cfg.get(f'{p}_enabled'), True)]
        return True, 'Aktive Alert-Plattformen: ' + (', '.join(enabled) if enabled else 'keine')

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        if key == 'button_open_overlay':
            self._start_overlay_if_needed(force=True)
            url = self._overlay_url()
            try:
                webbrowser.open(url)
            except Exception:
                pass
            self._log(f'Overlay URL: {url}')
            return True
        if key == 'button_test_alert':
            self._push_alert({
                'platform': 'tiktok',
                'event_type': 'follow',
                'username': 'TestUser',
                'title': 'Testalert',
                'text': 'al3rtalot ist bereit.',
                'amount': 1,
                'color': self._settings.get('tiktok_accent_color') or '#ff2d55',
                'channel': '',
                'message_id': f'test-{now_ms()}',
            })
            return True
        return False

    handle_settings_button = on_settings_button
    on_settings_action = on_settings_button

    def on_message(self, msg: Any) -> None:
        if not self._enabled:
            return
        settings = self._current_settings()
        for platform, handler in self._platforms.items():
            event = handler.normalize_event(msg)
            if not event:
                continue
            if not handler.should_alert(event, settings):
                return
            alert = handler.build_alert(event, settings)
            if self._is_duplicate(alert, settings):
                return
            self._push_alert(alert)
            return

    def _merged_settings(self, incoming: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = self.default_settings()
        cfg.update(self._settings if isinstance(self._settings, dict) else {})
        if isinstance(incoming, dict):
            cfg.update(incoming)
        return cfg

    def _current_settings(self) -> dict[str, Any]:
        return self._merged_settings()

    def _log(self, message: str) -> None:
        if self._host is not None:
            try:
                self._host.log(self.plugin_id, message)
                return
            except Exception:
                pass
        print(f'[{self.plugin_id}] {message}')

    def _overlay_url(self) -> str:
        port = to_int(self._settings.get('browser_overlay_port'), 17642, 1024, 65535)
        return f'http://127.0.0.1:{port}/'

    def _start_overlay_if_needed(self, force: bool = False) -> None:
        cfg = self._current_settings()
        if not force and not as_bool(cfg.get('browser_overlay_enabled'), True):
            return
        port = to_int(cfg.get('browser_overlay_port'), 17642, 1024, 65535)
        self._overlay_state.set_settings(duration_ms=to_int(cfg.get('alert_duration_ms'), 6000, 1000, 30000))
        if self._overlay_server is not None and self._overlay_server.port == port:
            self._settings['browser_overlay_url'] = self._overlay_server.url
            return
        if self._overlay_server is not None:
            self._overlay_server.stop()
            self._overlay_server = None
        server = AlertOverlayServer(port, self._overlay_state, self._log)
        if server.start():
            self._overlay_server = server
            self._settings['browser_overlay_url'] = server.url
            self._save_runtime_state({'browser_overlay_url': server.url})

    def _is_duplicate(self, alert: dict[str, Any], settings: dict[str, Any]) -> bool:
        ttl = to_int(settings.get('dedupe_seconds'), 8, 0, 120)
        if ttl <= 0:
            return False
        key = '|'.join([
            str(alert.get('platform') or ''),
            str(alert.get('event_type') or ''),
            str(alert.get('username') or '').lower(),
            str(alert.get('message_id') or alert.get('text') or '')[:160].lower(),
        ])
        now = time.time()
        with self._lock:
            for old_key, ts in list(self._recent.items()):
                if now - ts > max(10, ttl * 3):
                    self._recent.pop(old_key, None)
            last = self._recent.get(key)
            if last is not None and now - last <= ttl:
                return True
            self._recent[key] = now
        return False

    def _push_alert(self, alert: dict[str, Any]) -> None:
        cfg = self._current_settings()
        item = dict(alert)
        item['id'] = now_ms()
        item['platform_label'] = PLATFORM_LABELS.get(str(item.get('platform')), str(item.get('platform') or 'al3rtalot'))
        self._start_overlay_if_needed()
        self._overlay_state.set_settings(duration_ms=to_int(cfg.get('alert_duration_ms'), 6000, 1000, 30000))
        self._overlay_state.push(item)
        self._save_runtime_state({'latest_alert': item})
        self._emit_overlay_message(item, cfg)
        self._log(f"alert | {item.get('platform')}:{item.get('event_type')}:{item.get('username')} -> {item.get('text')}")

    def _emit_overlay_message(self, item: dict[str, Any], settings: dict[str, Any]) -> None:
        if self._host is None or not as_bool(settings.get('alert_to_chat_overlay'), True):
            return
        platform = str(item.get('platform') or 'al3rtalot')
        title = str(item.get('title') or 'Alert')
        text = str(item.get('text') or '')
        color = str(item.get('color') or '#ff2d55')
        try:
            self._host.emit_message(self.plugin_id, {
                'platform': platform,
                'username': str(item.get('username') or 'al3rtalot'),
                'text': text,
                'overlay_html': alert_html(title, text, platform=platform, color=color),
                'message_type': 'alert',
                'type': 'alert',
                'event_type': str(item.get('event_type') or 'alert'),
                'source_plugin_id': self.plugin_id,
                'dispatch_to_plugins': False,
            })
        except Exception as exc:
            self._log(f'emit alert failed: {exc}')

    def _save_runtime_state(self, extra: dict[str, Any] | None = None) -> None:
        data = {
            'plugin': PLUGIN_ID,
            'version': PLUGIN_VERSION,
            'overlay_url': self._overlay_url(),
            'updated_at': time.time(),
        }
        if isinstance(extra, dict):
            data.update(extra)
        try:
            atomic_write_json(DATA_DIR / 'runtime_state.json', data)
        except Exception as exc:
            self._log(f'runtime_state write failed: {exc}')


def create_plugin():
    return Al3rtalotPlugin()
