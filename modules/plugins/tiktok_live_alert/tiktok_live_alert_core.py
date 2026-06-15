from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from PySide6 import QtCore, QtWidgets
from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    FollowEvent,
    GiftEvent,
    JoinEvent,
    LikeEvent,
    ShareEvent,
)
import TikTokLive.events as _tiktok_events

SubscribeEvent = getattr(_tiktok_events, 'SubscribeEvent', None)

from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin

from tiktok_live_alert_logging import PluginLogger
from tiktok_live_alert_settings import _PluginSettingsPatcher, _as_bool
from tiktok_live_alert_ui import _AlertWindow, _UiBridge
from tiktok_live_alert_obs_exports import ObsTextExportWriter
from tiktok_live_alert_meld import MeldOutputManager, SOURCE_OPTIONS, LIVE_ACTION_SOURCE_KEYS, LIVE_ACTION_MILESTONE_KEYS, LEGACY_ACTION_SOURCE_KEYS

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


class _PendingAlert:
    def __init__(
        self,
        username: str,
        text: str,
        channel: str,
        created_at: float,
        last_update: float,
        count: int = 1,
        message_type: str = 'alert',
    ) -> None:
        self.username = username
        self.text = text
        self.channel = channel
        self.created_at = created_at
        self.last_update = last_update
        self.count = count
        self.message_type = message_type


class _UiCallableInvoker(QtCore.QObject):
    invoke = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.invoke.connect(self._run, QtCore.Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot(object)
    def _run(self, payload: object) -> None:
        try:
            func, result, done = payload
        except Exception:
            return
        try:
            result['value'] = func()
        except Exception as exc:
            result['error'] = exc
        finally:
            try:
                done.set()
            except Exception:
                pass


class TikTokLiveAlertPlugin(ThreadedPlugin):
    plugin_id = 'tiktok_live_alert'
    display_name = 'TikTok LIVE Alert'
    version = '7.5.4'
    description = 'TikTok alerts with OBS text exports, desktop alerts, and direct Meld layer output mappings.'

    def __init__(self) -> None:
        super().__init__()
        self._pending_alerts: dict[str, _PendingAlert] = {}
        self._pending_lock: asyncio.Lock | None = None
        self._bridge: _UiBridge | None = None
        self._windows: list[_AlertWindow] = []
        self._state_lock = threading.Lock()
        self._state = self._new_state()
        self._last_state_emit = 0.0
        self._last_state_hash = ''
        self._settings_patcher: _PluginSettingsPatcher | None = None
        self._obs_export_writer = ObsTextExportWriter(_PLUGIN_DIR if '_PLUGIN_DIR' in globals() else os.path.dirname(__file__))
        self.logger = PluginLogger(self.plugin_id)
        self._runtime_host = None
        self._meld_output_manager = MeldOutputManager(self.logger, self)
        self._live_meld_routes_json = ''
        self._room_info_received = False
        self.ui_language = 'de'
        self._external_liker_rankings: dict[str, dict[str, Any]] = {}
        self._external_gifter_rankings: dict[str, dict[str, Any]] = {}
        self._like_milestone_next = 0
        self._like_milestone_last_trigger_at = 0.0
        self._live_action_next: dict[str, int] = {}
        self._live_action_last_trigger_at: dict[str, float] = {}
        self._live_action_lock = threading.RLock()
        self._live_action_active: dict[str, Any] | None = None
        self._live_action_queue: dict[str, dict[str, Any]] = {}
        self._live_action_timer: threading.Timer | None = None
        self._live_action_generation = 0
        self._personal_like_counts: dict[str, int] = {}
        self._personal_gift_counts: dict[str, int] = {}
        self._recent_event_seen: dict[str, float] = {}
        self._duplicate_event_suppressed: dict[str, int] = {}
        with contextlib.suppress(Exception):
            import builtins
            registry = getattr(builtins, '_godisalotachat_plugin_registry', None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(builtins, '_godisalotachat_plugin_registry', registry)
            registry[self.plugin_id] = self

        self._event_counters = {
            'follow': 0,
            'like': 0,
            'gift': 0,
            'comment': 0,
            'share': 0,
            'join': 0,
            'subscribe': 0,
            'state_updates': 0,
        }
        self._ui_invoker: _UiCallableInvoker | None = None

        app = QtWidgets.QApplication.instance()
        if app is not None:
            with contextlib.suppress(Exception):
                self._ui_invoker = _UiCallableInvoker()
                self._ui_invoker.moveToThread(app.thread())
            with contextlib.suppress(Exception):
                app.aboutToQuit.connect(
                    lambda: self._run_on_ui_thread(self._close_windows_ui, wait=False),
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

        self.logger.info(f"TikTok LIVE Alert Plugin v{self.version} initialized")

    def set_ui_language(self, language: str) -> None:
        lang = str(language or 'de').strip().lower()
        self.ui_language = lang if lang in {'de', 'en'} else 'de'

    def _run_on_ui_thread(self, func, *, wait: bool = False):
        app = QtWidgets.QApplication.instance()
        if app is None:
            return None
        if QtCore.QThread.currentThread() == app.thread():
            return func()

        result: dict[str, Any] = {}
        done = threading.Event()
        invoker = getattr(self, '_ui_invoker', None)
        if invoker is None:
            invoker = _UiCallableInvoker()
            invoker.moveToThread(app.thread())
            self._ui_invoker = invoker

        invoker.invoke.emit((func, result, done))
        if wait:
            done.wait(8.0)
            if 'error' in result:
                raise result['error']
            return result.get('value')
        return None


    def _platform_settings(self, host: PluginHost | None = None) -> dict[str, Any]:
        """Read central TikTok platform settings from the main tool.

        This plugin keeps its own alert/widget settings, but account/connect data
        belongs to the host now.
        """
        source = host or getattr(self, '_runtime_host', None)
        if source is None:
            return {}
        for name in ('platform_settings', 'get_platform_settings'):
            fn = getattr(source, name, None)
            if callable(fn):
                with contextlib.suppress(Exception):
                    data = fn('tiktok')
                    if isinstance(data, dict):
                        return dict(data)
        return {}

    def _platform_text(self, data: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = data.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        return ''

    def _effective_settings(self, settings: dict[str, Any] | None, host: PluginHost | None = None) -> dict[str, Any]:
        effective = dict(settings or {})
        platform = self._platform_settings(host)
        if not platform:
            return effective

        unique_id = self._platform_text(platform, 'main_account', 'unique_id', 'channel', 'live_channel')
        unique_id = unique_id.lstrip('@')
        if unique_id:
            effective['unique_id'] = unique_id

        if 'autoconnect' in platform:
            effective['autoconnect'] = _as_bool(platform.get('autoconnect'))
        if 'read_enabled' in platform:
            effective['_platform_read_enabled'] = _as_bool(platform.get('read_enabled'))
        else:
            effective['_platform_read_enabled'] = True
        if 'write_enabled' in platform:
            effective['_platform_write_enabled'] = _as_bool(platform.get('write_enabled'))
        if 'bot_account' in platform:
            effective['_platform_bot_account'] = str(platform.get('bot_account') or '').strip().lstrip('@')
        return effective

    def _window_keys(self) -> list[str]:
        return [
            'latest_follower', 'latest_like', 'latest_gift',
            'top_liker', 'top_gifter',
            'follower_goal', 'like_goal', 'gift_goal',
            'ticker', 'ticker_2', 'ticker_3',
        ]

    def settings_schema(self) -> list[dict[str, Any]]:
        self._schedule_settings_dialog_patch()
        fields: list[dict[str, Any]] = [
            {'key': 'logging_enabled', 'label': 'Enable event logging', 'type': 'checkbox'},
            {'key': 'aggregate_window_seconds', 'label': 'Alert bundle window (seconds)', 'type': 'number', 'min': 1, 'max': 15, 'step': 1},
            {'key': 'viewer_check_interval_seconds', 'label': 'Viewer check interval (seconds)', 'type': 'number', 'min': 1, 'max': 60, 'step': 1},
            {'key': 'state_emit_interval_seconds', 'label': 'Widget refresh interval (seconds)', 'type': 'number', 'min': 1, 'max': 30, 'step': 1},
            {'key': 'join_dedupe_seconds', 'label': 'Join duplicate filter (seconds)', 'type': 'number', 'min': 0, 'max': 600, 'step': 1},
            {'key': 'ranking_size', 'label': 'Top list size', 'type': 'number', 'min': 1, 'max': 20, 'step': 1},
            {'key': 'always_on_top', 'label': 'Keep alert windows always on top', 'type': 'checkbox'},
            {'key': 'enable_follows', 'label': 'Enable follows', 'type': 'checkbox'},
            {'key': 'enable_likes', 'label': 'Enable likes', 'type': 'checkbox'},
            {'key': 'enable_gifts', 'label': 'Enable gifts', 'type': 'checkbox'},
            {'key': 'enable_shares', 'label': 'Enable shares', 'type': 'checkbox'},
            {'key': 'enable_joins', 'label': 'Enable joins', 'type': 'checkbox'},
            {'key': 'enable_subscribes', 'label': 'Enable subscribes / members', 'type': 'checkbox'},
            {'key': 'enable_comments', 'label': 'Enable comments', 'type': 'checkbox'},
            {'key': 'show_alerts_in_desktop', 'label': 'Show alerts in desktop overlay', 'type': 'checkbox'},
            {'key': 'show_alerts_in_obs', 'label': 'Show alerts in OBS capture', 'type': 'checkbox'},
            {'key': 'show_comments_in_desktop', 'label': 'Show comments in desktop overlay', 'type': 'checkbox'},
            {'key': 'show_comments_in_obs', 'label': 'Show comments in OBS capture', 'type': 'checkbox'},
            {'key': 'meld_host', 'label': 'Meld host', 'placeholder': '127.0.0.1'},
            {'key': 'meld_port', 'label': 'Meld port', 'type': 'number', 'min': 1, 'max': 65535, 'step': 1},
            {'key': 'meld_routes_json', 'label': 'Meld routes', 'placeholder': '[]'},
        ]
        for prefix, title, default_title, goal, is_ticker in [
            ('latest_follower', 'Latest follower window', 'Latest Follower', None, False),
            ('latest_like', 'Latest like window', 'Latest Like', None, False),
            ('latest_gift', 'Latest gift window', 'Latest Gift', None, False),
            ('top_liker', 'Top liker window', 'Top Liker', None, False),
            ('top_gifter', 'Top gifter window', 'Top Gifter', None, False),
            ('follower_goal', 'Follower goal window', 'Follower Goal', 'follower_goal', False),
            ('like_goal', 'Like goal window', 'Like Goal', 'like_goal', False),
            ('gift_goal', 'Gift goal window', 'Gift Goal', 'gift_goal', False),
            ('ticker', 'Ticker banner 1', 'Ticker 1', None, True),
            ('ticker_2', 'Ticker banner 2', 'Ticker 2', None, True),
            ('ticker_3', 'Ticker banner 3', 'Ticker 3', None, True),
        ]:
            fields.extend([
                {'key': f'enable_{prefix}_txt', 'label': f'Enable {title} TXT export', 'type': 'checkbox'},
                {'key': f'enable_{prefix}_window', 'label': f'Enable {title} legacy window', 'type': 'checkbox'},
                {'key': f'{prefix}_title', 'label': f'{title} title', 'default': default_title},
                {'key': f'{prefix}_x', 'label': f'{title} X', 'type': 'number', 'min': -10000, 'max': 10000, 'step': 1},
                {'key': f'{prefix}_y', 'label': f'{title} Y', 'type': 'number', 'min': -10000, 'max': 10000, 'step': 1},
                {'key': f'{prefix}_width', 'label': f'{title} width', 'type': 'number', 'min': 180, 'max': 2400, 'step': 1},
                {'key': f'{prefix}_height', 'label': f'{title} height', 'type': 'number', 'min': 80, 'max': 1600, 'step': 1},
                {'key': f'{prefix}_font_family', 'label': f'{title} font', 'type': 'font'},
                {'key': f'{prefix}_font_size', 'label': f'{title} font size', 'type': 'number', 'min': 8, 'max': 72, 'step': 1},
                {'key': f'{prefix}_text_color', 'label': f'{title} text color', 'type': 'color'},
                {'key': f'{prefix}_text_opacity', 'label': f'{title} text opacity', 'type': 'float', 'min': 0.0, 'max': 1.0, 'step': 0.05},
                {'key': f'{prefix}_background_color', 'label': f'{title} background color', 'type': 'color'},
                {'key': f'{prefix}_background_opacity', 'label': f'{title} background opacity', 'type': 'float', 'min': 0.0, 'max': 1.0, 'step': 0.05},
                {'key': f'{prefix}_accent_color', 'label': f'{title} accent / bar color', 'type': 'color'},
                {'key': f'{prefix}_title_font_size', 'label': f'{title} title font size', 'type': 'number', 'min': 8, 'max': 72, 'step': 1},
                {'key': f'{prefix}_corner_radius', 'label': f'{title} corner radius', 'type': 'number', 'min': 0, 'max': 80, 'step': 1},
                {'key': f'{prefix}_show_title', 'label': f'{title} show title', 'type': 'checkbox'},
                {'key': f'{prefix}_bar_height', 'label': f'{title} bar height', 'type': 'number', 'min': 8, 'max': 120, 'step': 1},
                {'key': f'{prefix}_bar_style', 'label': f'{title} bar style', 'placeholder': 'default | tiktok_clean | tiktok_diagonal | neon | flat | double_border | soft_gradient | glass | candy_stripe | minimal_dark'},
            ])
            for item in ['title', 'main', 'secondary', 'progress', 'list', 'ticker']:
                fields.extend([
                    {'key': f'{prefix}_{item}_enabled', 'label': f'{title} {item} enabled', 'type': 'checkbox'},
                    {'key': f'{prefix}_{item}_x', 'label': f'{title} {item} X', 'type': 'number', 'min': -10000, 'max': 10000, 'step': 1},
                    {'key': f'{prefix}_{item}_y', 'label': f'{title} {item} Y', 'type': 'number', 'min': -10000, 'max': 10000, 'step': 1},
                    {'key': f'{prefix}_{item}_w', 'label': f'{title} {item} width', 'type': 'number', 'min': 20, 'max': 2400, 'step': 1},
                    {'key': f'{prefix}_{item}_h', 'label': f'{title} {item} height', 'type': 'number', 'min': 20, 'max': 1600, 'step': 1},
                ])
            if goal:
                fields.append({'key': goal, 'label': f'{title} target', 'type': 'number', 'min': 0, 'max': 100000000, 'step': 1})
                fields.append({'key': f'{goal}_progress_style', 'label': f'{title} progress style', 'placeholder': 'value | percent'})
            if is_ticker:
                base = prefix
                fields.extend([
                    {'key': f'{base}_direction', 'label': f'{title} direction', 'placeholder': 'left | right | bounce_left | bounce_right'},
                    {'key': f'{base}_speed', 'label': f'{title} speed', 'type': 'number', 'min': 1, 'max': 2000, 'step': 1},
                    {'key': f'{base}_text', 'label': f'{title} text', 'placeholder': 'Latest follower: {latest_follower} | Top liker: {top_liker} ({top_liker_count})'},
                ])
        return fields

    def default_settings(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            'unique_id': '',
            'autoconnect': False,
            'logging_enabled': False,
            'aggregate_window_seconds': 3,
            'viewer_check_interval_seconds': 5,
            'state_emit_interval_seconds': 1,
            'join_dedupe_seconds': 60,
            'ranking_size': 5,
            'always_on_top': False,
            'enable_comments': False,
            'enable_follows': False,
            'enable_likes': False,
            'enable_gifts': False,
            'enable_shares': True,
            'enable_joins': True,
            'enable_subscribes': True,
            'show_comments_in_desktop': False,
            'show_comments_in_obs': False,
            'show_alerts_in_desktop': True,
            'show_alerts_in_obs': False,
            'follower_goal': 1000,
            'like_goal': 10000,
            'gift_goal': 100,
            'follower_goal_progress_style': 'value',
            'like_goal_progress_style': 'value',
            'gift_goal_progress_style': 'value',
            'ticker_direction': 'left',
            'ticker_speed': 80,
            'ticker_text': 'Latest follower: {latest_follower} | Top liker: {top_liker} ({top_liker_count})',
            'ticker_2_direction': 'right',
            'ticker_2_speed': 80,
            'ticker_2_text': 'Follow on TikTok: {latest_follower}',
            'ticker_3_direction': 'bounce_left',
            'ticker_3_speed': 70,
            'ticker_3_text': 'Top gifter: {top_gifter} ({top_gifter_count})',
            'meld_host': '127.0.0.1',
            'meld_port': 13376,
            'meld_routes_json': '[]',
        }
        defaults.update(self._widget_defaults('latest_follower', 60, 60, 360, 140, 'Latest Follower'))
        defaults.update(self._widget_defaults('latest_like', 450, 60, 360, 140, 'Latest Like'))
        defaults.update(self._widget_defaults('latest_gift', 840, 60, 360, 140, 'Latest Gift'))
        defaults.update(self._widget_defaults('top_liker', 60, 240, 360, 220, 'Top Liker'))
        defaults.update(self._widget_defaults('top_gifter', 450, 240, 360, 220, 'Top Gifter'))
        defaults.update(self._widget_defaults('follower_goal', 840, 240, 360, 160, 'Follower Goal'))
        defaults.update(self._widget_defaults('like_goal', 840, 420, 360, 160, 'Like Goal'))
        defaults.update(self._widget_defaults('gift_goal', 840, 600, 360, 160, 'Gift Goal'))
        defaults.update(self._widget_defaults('ticker', 60, 500, 750, 90, 'Ticker 1'))
        defaults.update(self._widget_defaults('ticker_2', 60, 610, 750, 90, 'Ticker 2'))
        defaults.update(self._widget_defaults('ticker_3', 60, 720, 750, 90, 'Ticker 3'))
        return defaults

    def _widget_defaults(self, prefix: str, x: int, y: int, w: int, h: int, title: str) -> dict[str, Any]:
        data = {
            f'enable_{prefix}_txt': True,
            f'enable_{prefix}_window': False,
            f'{prefix}_title': title,
            f'{prefix}_x': x,
            f'{prefix}_y': y,
            f'{prefix}_width': w,
            f'{prefix}_height': h,
            f'{prefix}_font_family': 'Segoe UI',
            f'{prefix}_font_size': 18 if prefix != 'ticker' else 22,
            f'{prefix}_text_color': '#ffffff',
            f'{prefix}_text_opacity': 1.0,
            f'{prefix}_background_color': '#151515',
            f'{prefix}_background_opacity': 0.88,
            f'{prefix}_accent_color': '#ff2d55',
            f'{prefix}_title_font_size': 22 if not prefix.startswith('ticker') else 26,
            f'{prefix}_corner_radius': 16,
            f'{prefix}_show_title': False,
            f'{prefix}_bar_height': 22,
            f'{prefix}_bar_style': 'default',
        }
        defaults = {
            'title': (12, 10, max(100, w - 24), 28),
            'main': (18, 44, max(100, w - 36), 40),
            'secondary': (18, 88, max(100, w - 36), 28),
            'progress': (18, max(40, h - 44), max(100, w - 36), 22),
            'list': (16, 40, max(100, w - 32), max(60, h - 56)),
            'ticker': (16, max(16, (h - 40) // 2), max(100, w - 32), 32),
        }
        for item, (ix, iy, iw, ih) in defaults.items():
            data[f'{prefix}_{item}_enabled'] = True
            data[f'{prefix}_{item}_x'] = ix
            data[f'{prefix}_{item}_y'] = iy
            data[f'{prefix}_{item}_w'] = iw
            data[f'{prefix}_{item}_h'] = ih
        return data

    def _schedule_settings_dialog_patch(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if self._settings_patcher is None:
            self._settings_patcher = _PluginSettingsPatcher(self)
        self._settings_patcher.start()

    def start(self, settings, host: PluginHost) -> None:
        self._live_meld_routes_json = str(settings.get('meld_routes_json', '[]') or '[]')
        self.logger.set_enabled(_as_bool(settings.get('logging_enabled', False)))
        self._schedule_settings_dialog_patch()
        self.logger.info(
            f"Plugin starting with settings: unique_id={settings.get('unique_id', 'NOT SET')}, "
            f"enable_follows={_as_bool(settings.get('enable_follows'))}, "
            f"enable_likes={_as_bool(settings.get('enable_likes'))}, "
            f"enable_gifts={_as_bool(settings.get('enable_gifts'))}"
        )
        super().start(settings, host)
        with contextlib.suppress(Exception):
            self._run_on_ui_thread(self._close_windows_ui, wait=True)
        with contextlib.suppress(Exception):
            self.apply_live_settings(settings, self._state)

    def stop(self, wait: bool = False, timeout: float = 3.0) -> None:
        self.logger.info("Plugin stopping")
        self._runtime_host = None
        super().stop(wait=wait, timeout=timeout)
        with contextlib.suppress(Exception):
            self._run_on_ui_thread(self._close_windows_ui, wait=True)

    def _create_windows_ui(self, settings: dict[str, Any]) -> None:
        """Legacy Qt alert windows are intentionally disabled.

        Alerts are now delivered through OBS text exports and Meld/browser routes only.
        This keeps old settings compatible without ever spawning the small capture windows.
        """
        self._close_windows_ui()

    def _close_windows_ui(self) -> None:
        bridge = self._bridge
        self._bridge = None
        if bridge is not None:
            with contextlib.suppress(Exception):
                bridge.close_all.emit()
        for win in list(self._windows):
            with contextlib.suppress(Exception):
                win.hide()
                win.close()
                win.deleteLater()
        self._windows.clear()

    def _settings_with_live_meld_routes(self, settings: dict[str, Any]) -> dict[str, Any]:
        if dict(settings or {}).get('__prefer_inline_meld_routes'):
            return settings
        live_routes = str(getattr(self, '_live_meld_routes_json', '') or '').strip()
        if not live_routes:
            return settings
        merged = dict(settings or {})
        merged['meld_routes_json'] = live_routes
        return merged

    def apply_live_settings(self, settings: dict[str, Any], sample_state: dict[str, Any] | None = None) -> None:
        settings = self._settings_with_live_meld_routes(settings)
        state = sample_state if sample_state is not None else self._state
        with contextlib.suppress(Exception):
            self._run_on_ui_thread(self._close_windows_ui, wait=False)
        with contextlib.suppress(Exception):
            self._obs_export_writer.write_exports(state, settings)
        with contextlib.suppress(Exception):
            self._meld_output_manager.apply_routes(settings, state, self._obs_export_writer)

    def _new_state(self) -> dict[str, Any]:
        return {
            'channel': '',
            'latest': {
                'follower': '', 'like_user': '', 'like_count': 0,
                'gift_user': '', 'gift_name': '', 'gift_count': 0,
            },
            'goals': {
                'followers': {'current': 0, 'target': 0},
                'likes': {'current': 0, 'target': 0},
                'gifts': {'current': 0, 'target': 0},
            },
            'rankings': {'likers': [], 'gifters': []},
            'ticker': {'text': '', 'direction': 'left', 'speed': 80},
        }

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        settings = self._effective_settings(settings, getattr(self, '_runtime_host', None))
        if not _as_bool(settings.get('_platform_read_enabled', True)):
            return True, 'TikTok reading is disabled in Platforms.'
        raw_unique_id = str(settings.get('unique_id', '') or '').strip()
        normalized = self._normalize_unique_id(raw_unique_id)
        if not normalized:
            return True, 'No @unique_id set yet.'

        async def _check():
            client = TikTokLiveClient(unique_id=normalized)
            return await client.is_live()

        loop = None
        try:
            loop = asyncio.new_event_loop()
            return_value = loop.run_until_complete(_check())
        except Exception as exc:
            return False, str(exc)
        finally:
            if loop is not None:
                with contextlib.suppress(Exception):
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                with contextlib.suppress(Exception):
                    loop.close()
        return (True, 'Creator is live/reachable.') if return_value else (False, 'Creator currently not live or not reachable.')

    def _float_setting(self, settings: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
        try:
            value = float(settings.get(key, default) or default)
        except Exception:
            value = default
        return max(low, min(high, value))

    def _int_setting(self, settings: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
        try:
            value = int(float(settings.get(key, default) or default))
        except Exception:
            value = default
        return max(low, min(high, value))

    def _aggregate_window(self, settings: dict[str, Any]) -> float:
        return self._float_setting(settings, 'aggregate_window_seconds', 3.0, 1.0, 15.0)

    def _normalize_unique_id(self, value: Any) -> str:
        raw = str(value or '').strip()
        while raw.startswith('@'):
            raw = raw[1:].strip()
        return raw

    def _deep_get(self, obj: Any, path: str, default: Any = None) -> Any:
        current = obj
        for part in str(path or '').split('.'):
            if current is None:
                return default
            if isinstance(current, dict):
                current = current.get(part, default)
                continue
            if isinstance(current, (list, tuple)):
                try:
                    current = current[int(part)]
                    continue
                except Exception:
                    return default
            current = getattr(current, part, default)
        return current

    def _clean_user_text(self, value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        low = text.lower()
        if low in {'none', 'null', 'unknown', '---'}:
            return ''
        return text

    def _user_name(self, event: Any) -> str:
        for path in (
            'user.nickname', 'user.display_name', 'user.name',
            'user.unique_id', 'user.uniqueId',
            'unique_id', 'uniqueId', 'nickname', 'display_name', 'name',
            'user_info.nickname', 'user_info.unique_id',
        ):
            value = self._clean_user_text(self._deep_get(event, path))
            if value:
                return value
        return 'unknown'

    def _user_handle(self, event: Any) -> str:
        for path in (
            'user.unique_id', 'user.uniqueId', 'user.sec_uid', 'user.user_id', 'user.id',
            'sec_uid', 'user_id', 'id', 'unique_id', 'uniqueId',
            'user_info.unique_id', 'user_info.sec_uid',
        ):
            value = self._clean_user_text(self._deep_get(event, path))
            if value:
                return value
        return self._user_name(event).lower()

    def _normalize_route_user(self, value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        text = text.lstrip('@').strip().casefold()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _candidate_user_keys(self, username: str, user_key: str) -> set[str]:
        keys: set[str] = set()
        for value in (username, user_key):
            norm = self._normalize_route_user(value)
            if norm:
                keys.add(norm)
        return keys

    def _has_personal_routes_for_user(self, settings: dict[str, Any], source_key: str, username: str, user_key: str) -> bool:
        candidates = self._candidate_user_keys(username, user_key)
        if not candidates:
            return False
        for route in self._enabled_live_action_routes(settings, {source_key}):
            target = self._normalize_route_user(route.get('target_user') or route.get('user_name') or '')
            if target and target in candidates:
                return True
        return False

    def _extract_text(self, event: Any) -> str:
        for path in ('comment', 'text', 'message', 'content', 'comment.text'):
            value = self._deep_get(event, path)
            if value:
                text = str(value).strip()
                if text:
                    return text
        return ''

    def _int_from_paths(self, obj: Any, *paths: str, default: int = 1) -> int:
        for path in paths:
            current = self._deep_get(obj, path, None)
            if current is None:
                continue
            try:
                return int(current)
            except Exception:
                try:
                    return int(float(str(current).strip()))
                except Exception:
                    continue
        return default

    def _like_count(self, event: Any) -> int:
        # TikTokLive's LikeEvent increment is the event/user bundle count.
        # In the Python plugin this has historically been reliable as ``count``.
        # Do NOT prefer ``like_count`` here: depending on TikTokLive versions that
        # field can represent an accumulated value, which made personal milestones
        # fire before the configured threshold.
        count = self._int_from_paths(
            event,
            'count',
            'likes',
            'likeCount',
            'like_count',
            'repeat_count',
            'repeatCount',
            'alert_count',
            'event_count',
            'increment',
            'delta',
            default=1,
        )
        return count if count > 0 else 1

    def _debug_like_event_fields(self, event: Any, username: str, count: int) -> None:
        if not self.logger:
            return
        parts = []
        for path in ('count', 'likes', 'likeCount', 'like_count', 'total', 'total_likes', 'totalLikes', 'total_like_count'):
            value = self._deep_get(event, path, None)
            if value is not None:
                parts.append(f'{path}={value!r}')
        if parts:
            self.logger.debug(f"LIKE raw fields: user={username}, used_delta={count}, " + ', '.join(parts))

    def _gift_name(self, event: Any) -> str:
        gift = getattr(event, 'gift', None)
        if gift is None:
            return 'gift'
        for attr in ('name', 'gift_name', 'describe'):
            value = getattr(gift, attr, None)
            if value:
                return str(value)
        info = getattr(gift, 'info', None)
        if info is not None:
            for attr in ('name', 'gift_name'):
                value = getattr(info, attr, None)
                if value:
                    return str(value)
        return 'gift'

    def _gift_count(self, event: Any) -> int:
        gift = getattr(event, 'gift', None)
        if gift is None:
            return 1
        streakable = getattr(gift, 'streakable', False)
        streaking = getattr(event, 'streaking', False)
        if streakable and streaking:
            return 0
        repeat_count = getattr(event, 'repeat_count', 0)
        if repeat_count > 0:
            return repeat_count
        return self._int_from_paths(event, 'gift.repeat_count', 'repeat_count', 'count', default=1)

    def _fetch_profile_follower_count_sync(self, unique_id: str) -> int | None:
        normalized = self._normalize_unique_id(unique_id)
        if not normalized:
            return None
        url = f"https://www.tiktok.com/@{normalized}"
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                html = response.read().decode('utf-8', errors='ignore')
        except urllib.error.HTTPError as exc:
            self.logger.warning(f"Could not fetch TikTok profile for follower count (HTTP {exc.code})")
            return None
        except Exception as exc:
            self.logger.warning(f"Could not fetch TikTok profile for follower count: {exc}")
            return None

        patterns = [
            r'"followerCount"\s*:\s*(\d+)',
            r'"followerCount"\s*:\s*"(\d+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    pass

        universal_match = re.search(
            r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if universal_match:
            try:
                data = json.loads(universal_match.group(1))
                stack = [data]
                while stack:
                    current = stack.pop()
                    if isinstance(current, dict):
                        if 'followerCount' in current:
                            value = current.get('followerCount')
                            try:
                                return int(value)
                            except Exception:
                                pass
                        stack.extend(current.values())
                    elif isinstance(current, list):
                        stack.extend(current)
            except Exception as exc:
                self.logger.debug(f"Follower count JSON parse skipped: {exc}")

        self.logger.warning("TikTok profile follower count not found in profile page")
        return None

    async def _fetch_profile_follower_count(self, unique_id: str) -> int | None:
        return await asyncio.to_thread(self._fetch_profile_follower_count_sync, unique_id)

    def _alert_output_flags(self, settings: dict[str, Any]) -> tuple[bool, bool]:
        """Return Desktop/OBS alert route flags with a safe desktop fallback.

        Some older settings files stored both route flags as False while the
        TikTok event outputs themselves were enabled. In that state likes and
        milestones were counted, TXT/Meld state was written, but nothing was
        forwarded to the desktop/OBS message pipeline. Alerts should not die
        silently just because those legacy route flags are missing/false.
        """
        show_desktop = _as_bool(settings.get('show_alerts_in_desktop', True))
        show_obs = _as_bool(settings.get('show_alerts_in_obs', False))
        if not show_desktop and not show_obs:
            show_desktop = True
            with contextlib.suppress(Exception):
                self.logger.warning(
                    'Alert output routes were both disabled; forcing Desktop alerts on for compatibility.'
                )
        return show_desktop, show_obs

    def _emit_message(self, host: PluginHost, *, username: str, text: str, channel: str, message_type: str, show_in_desktop: bool, show_in_obs: bool) -> None:
        if not show_in_desktop and not show_in_obs:
            return

        # Keep the specific TikTok event type for newer renderers, but also
        # provide generic compatibility fields for desktop windows that only
        # route "alert" / "chat" messages.
        normalized_type = str(message_type or '').strip().lower()
        is_tiktok_alert = normalized_type.startswith('tiktok_')
        alert_type = normalized_type.replace('tiktok_', '', 1) if is_tiktok_alert else normalized_type
        generic_type = 'chat' if normalized_type == 'chat' else 'alert'

        payload = {
            'platform': 'tiktok',
            'username': username,
            'text': text,
            'message': text,
            'content': text,
            'comment': text,
            'channel': channel,
            'message_type': normalized_type or generic_type,
            'type': generic_type,
            'event_type': normalized_type or generic_type,
            'alert_type': alert_type if alert_type and alert_type != 'chat' else '',
            'alert_kind': alert_type if alert_type and alert_type != 'chat' else '',
            'category': generic_type,
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': show_in_desktop,
            'show_in_obs': show_in_obs,
            'show_in_obs_capture': show_in_obs,
        }
        host.emit_message(self.plugin_id, payload)

    def _message_type_from_alert_key(self, key: str) -> str:
        kind = str(key or '').split(':', 1)[0].strip().lower()
        if kind in {'join', 'like', 'follow', 'gift', 'share', 'subscribe'}:
            return f'tiktok_{kind}'
        return 'alert'


    def _dedupe_user_key(self, *values: Any) -> str:
        for value in values:
            text = str(value or '').strip()
            if text:
                text = text.lstrip('@').strip().casefold()
                text = re.sub(r'\s+', ' ', text)
                if text:
                    return text
        return 'unknown'

    def _should_process_recent_event(self, event_kind: str, user_key: str, window_seconds: float, *, log_label: str = '') -> bool:
        try:
            window = float(window_seconds)
        except Exception:
            window = 0.0
        if window <= 0:
            return True
        kind = str(event_kind or 'event').strip().lower() or 'event'
        user = self._dedupe_user_key(user_key)
        key = f'{kind}:{user}'
        now = time.monotonic()
        last = self._recent_event_seen.get(key, 0.0)
        if last and now - last < window:
            self._duplicate_event_suppressed[key] = self._duplicate_event_suppressed.get(key, 0) + 1
            return False
        suppressed = self._duplicate_event_suppressed.pop(key, 0)
        self._recent_event_seen[key] = now
        cutoff = now - max(window * 2.0, 300.0)
        if len(self._recent_event_seen) > 2000:
            self._recent_event_seen = {k: v for k, v in self._recent_event_seen.items() if v >= cutoff}
        if suppressed and log_label:
            self.logger.info(f'{log_label}: suppressed {suppressed} duplicate event(s)')
        return True

    def _emit_alert_now(self, host: PluginHost, *, username: str, text: str, channel: str, message_type: str, show_in_desktop: bool, show_in_obs: bool) -> None:
        """Emit non-bundled alerts immediately.

        Only likes use the aggregate/bundle queue because TikTok often sends
        like bursts that need to be counted cleanly. Follows, joins, shares,
        gifts and subscribes are single events and should feel instant.
        """
        self._emit_message(
            host,
            username=username,
            text=text,
            channel=channel,
            message_type=message_type,
            show_in_desktop=show_in_desktop,
            show_in_obs=show_in_obs,
        )

    async def _queue_alert(self, key: str, username: str, text: str, channel: str, increment: int = 1) -> None:
        message_type = self._message_type_from_alert_key(key)
        if self._pending_lock is None:
            self._pending_lock = asyncio.Lock()
        async with self._pending_lock:
            now = time.monotonic()
            existing = self._pending_alerts.get(key)
            if existing is None:
                self._pending_alerts[key] = _PendingAlert(username, text, channel, now, now, increment, message_type)
            else:
                existing.count += increment
                existing.last_update = now
                existing.message_type = message_type

    async def _flush_pending_loop(self, host: PluginHost, aggregate_window: float, show_in_desktop: bool, show_in_obs: bool) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(0.2)
            if self._pending_lock is None:
                continue
            now = time.monotonic()
            ready: list[_PendingAlert] = []
            async with self._pending_lock:
                to_remove = []
                for key, alert in self._pending_alerts.items():
                    if now - alert.last_update >= aggregate_window:
                        ready.append(alert)
                        to_remove.append(key)
                for key in to_remove:
                    self._pending_alerts.pop(key, None)
            for alert in ready:
                text = alert.text.replace('{count}', str(alert.count))
                self._emit_message(host, username=alert.username, text=text, channel=alert.channel, message_type=alert.message_type, show_in_desktop=show_in_desktop, show_in_obs=show_in_obs)

    def _init_runtime_state(self, settings: dict[str, Any], channel: str):
        persisted_follower = self._obs_export_writer.read_export_text('latest_follower.txt', self._obs_export_writer.default_text('latest_follower.txt'))
        with self._state_lock:
            self._state = self._new_state()
            self._state['channel'] = channel
            self._state['latest']['follower'] = persisted_follower
            self._state['goals']['followers']['target'] = self._int_setting(settings, 'follower_goal', 1000, 0, 100000000)
            self._state['goals']['likes']['target'] = self._int_setting(settings, 'like_goal', 10000, 0, 100000000)
            self._state['goals']['gifts']['target'] = self._int_setting(settings, 'gift_goal', 100, 0, 100000000)
            step = self._int_setting(settings, 'like_milestone_step', 200, 1, 100000000)
            self._like_milestone_next = step
            self._like_milestone_last_trigger_at = 0.0
            self._live_action_next = {}
            self._live_action_last_trigger_at = {}
            self._personal_like_counts = {}
            self._personal_gift_counts = {}
            self._recent_event_seen = {}
            self._duplicate_event_suppressed = {}
            self._state['ticker']['direction'] = str(settings.get('ticker_direction', 'left') or 'left')
            self._state['ticker']['speed'] = self._int_setting(settings, 'ticker_speed', 80, 1, 2000)
            self._state['ticker']['text'] = ''
        return {}, {}

    def _top_items(self, scores: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        items = list(scores.values())
        items.sort(key=lambda it: (-int(it.get('count') or 0), str(it.get('name') or '').lower()))
        return [{'name': str(it.get('name') or 'unknown'), 'count': int(it.get('count') or 0)} for it in items[:limit]]

    def _update_ticker(self, settings: dict[str, Any]) -> None:
        latest = self._state['latest']
        rankings = self._state['rankings']
        top_liker = rankings['likers'][0]['name'] if rankings['likers'] else 'sadly not you'
        top_liker_count = rankings['likers'][0]['count'] if rankings['likers'] else 0
        top_gifter = rankings['gifters'][0]['name'] if rankings['gifters'] else 'sadly not you'
        top_gifter_count = rankings['gifters'][0]['count'] if rankings['gifters'] else 0
        template = str(settings.get('ticker_text') or '')
        self._state['ticker']['text'] = template.format(
            latest_follower=latest.get('follower') or 'your name here',
            latest_like_user=latest.get('like_user') or 'your name here',
            latest_like_count=latest.get('like_count') or 0,
            latest_gift_user=latest.get('gift_user') or 'your name here',
            latest_gift_name=latest.get('gift_name') or 'gift',
            latest_gift_count=latest.get('gift_count') or 0,
            top_liker=top_liker,
            top_liker_count=top_liker_count,
            top_gifter=top_gifter,
            top_gifter_count=top_gifter_count,
        )

    def _regular_meld_output_keys(self) -> set[str]:
        action_keys = set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)
        return {str(key) for key, _label in SOURCE_OPTIONS if str(key) not in action_keys}

    def _apply_meld_routes_live(self, settings: dict[str, Any], state: dict[str, Any]) -> None:
        """Push normal Meld text outputs from live TikTok events.

        Live actions use the direct trigger path already. Normal Meld outputs now use
        the same direct route resolver, but action routes are excluded so media and
        milestone actions are not retriggered by every state update.
        """
        settings_copy = dict(settings or {})
        state_copy = {
            'channel': state.get('channel', ''),
            'latest': dict(state.get('latest') or {}),
            'goals': {k: dict(v) for k, v in (state.get('goals') or {}).items()},
            'rankings': {k: [dict(x) for x in v] for k, v in (state.get('rankings') or {}).items()},
            'ticker': dict(state.get('ticker') or {}),
        }
        try:
            ok, failed, detail = self._meld_output_manager.apply_routes_for_sources(
                settings_copy,
                state_copy,
                self._obs_export_writer,
                self._regular_meld_output_keys(),
            )
            if ok or failed:
                msg = f'Meld outputs live push: {ok} ok, {failed} failed. {detail}'
                if failed:
                    self.logger.warning(msg)
                else:
                    self.logger.info(msg)
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.logger.warning(f'Meld outputs live push failed: {exc}')

    def _emit_state(self, settings: dict[str, Any], force: bool = False) -> None:
        settings = self._settings_with_live_meld_routes(settings)
        now = time.monotonic()
        interval = self._float_setting(settings, 'state_emit_interval_seconds', 1.0, 0.25, 30.0)
        if not force and now - self._last_state_emit < interval:
            return
        with self._state_lock:
            state = dict(self._state)
            state['latest'] = dict(self._state['latest'])
            state['goals'] = {k: dict(v) for k, v in self._state['goals'].items()}
            state['rankings'] = {k: [dict(x) for x in v] for k, v in self._state['rankings'].items()}
            state['ticker'] = dict(self._state['ticker'])
        state_hash = repr(state)
        if not force and state_hash == self._last_state_hash:
            self._last_state_emit = now
            return
        self._last_state_emit = now
        self._last_state_hash = state_hash
        if self._bridge is not None:
            self._bridge.state_updated.emit(state)
        with contextlib.suppress(Exception):
            self._obs_export_writer.write_exports(state, settings)
        with contextlib.suppress(Exception):
            self._apply_meld_routes_live(settings, state)
        self.logger.debug(
            f"State emitted: follower={state['latest']['follower']}, likes={state['goals']['likes']['current']}, gifts={state['goals']['gifts']['current']}"
        )

    def _enabled_live_action_routes(self, settings: dict[str, Any], source_keys: set[str]) -> list[dict[str, Any]]:
        try:
            wanted = {str(k or '').strip().lower() for k in source_keys}
            return [
                dict(route)
                for route in self._meld_output_manager.load_routes(settings)
                if bool(route.get('enabled', True))
                and str(route.get('source_key') or '').strip().lower() in wanted
            ]
        except Exception:
            return []

    def _live_action_priority(self, source_key: str) -> int:
        key = str(source_key or '').strip().lower()
        if key == 'live_action_gift':
            return 400
        if key == 'live_action_personal_gift_milestone':
            return 370
        if key == 'live_action_gift_milestone':
            return 350
        if key == 'live_action_follow':
            return 300
        if key == 'live_action_subscribe':
            return 290
        if key == 'live_action_personal_like_milestone':
            return 220
        if key in {'live_action_like_milestone', 'like_milestone_trigger', 'like_milestone_trigger.txt'}:
            return 100
        if key == 'live_action_like':
            return 80
        if key in {'live_action_share', 'live_action_join'}:
            return 50
        return 10

    def _live_action_duration(self, routes: list[dict[str, Any]]) -> float:
        duration = 0.0
        for route in routes or []:
            try:
                value = self._meld_output_manager._restore_delay_from_route(route, default=8.0)
            except Exception:
                value = 8.0
            duration = max(duration, float(value or 0.0))
        if duration <= 0:
            duration = 8.0
        return max(0.25, min(3600.0, duration))

    def _stop_live_action_routes_ui(self, routes: list[dict[str, Any]], reason: str = '') -> None:
        if not routes:
            return

        def _stop() -> None:
            try:
                ok, failed, detail = self._meld_output_manager.stop_routes(routes)
                if ok:
                    suffix = f' ({reason})' if reason else ''
                    self.logger.info(f'Live action stopped{suffix}: {ok} route(s). {detail}')
                elif failed:
                    self.logger.warning(f'Live action stop failed: {detail}')
            except Exception as exc:
                self.logger.warning(f'Live action stop failed: {exc}')

        self._run_on_ui_thread(_stop, wait=False)

    def _fire_live_action_now(self, action: dict[str, Any]) -> None:
        settings = dict(action.get('settings') or {})
        state = action.get('state') or {}
        routes = list(action.get('routes') or [])
        label = str(action.get('label') or '')
        route_sources = {str(route.get('source_key') or '').strip().lower() for route in routes}

        def _trigger() -> None:
            try:
                temp_settings = dict(settings or {})
                temp_settings['meld_routes_json'] = self._meld_output_manager.save_routes_text(routes)
                temp_settings['__prefer_inline_meld_routes'] = True
                ok, failed, detail = self._meld_output_manager.trigger_routes_for_sources(
                    temp_settings,
                    state,
                    self._obs_export_writer,
                    route_sources,
                )
                if ok:
                    self.logger.info(f"Live action fired: {label} -> {ok} route(s). {detail}")
                else:
                    self.logger.warning(f"Live action reached: {label}, but no Meld action fired. {detail}")
            except Exception as exc:
                self.logger.warning(f'Live action failed ({label}): {exc}')

        self._run_on_ui_thread(_trigger, wait=False)

    def _start_live_action_locked(self, action: dict[str, Any]) -> None:
        self._live_action_generation += 1
        generation = self._live_action_generation
        routes = list(action.get('routes') or [])
        duration = self._live_action_duration(routes)
        action['duration'] = duration
        action['generation'] = generation
        self._live_action_active = action
        self._fire_live_action_now(action)

        old_timer = self._live_action_timer
        if old_timer is not None:
            with contextlib.suppress(Exception):
                old_timer.cancel()

        timer = threading.Timer(duration, lambda: self._finish_live_action(generation))
        timer.daemon = True
        self._live_action_timer = timer
        timer.start()
        self.logger.debug(f"Live action lock active for {duration:g}s: {action.get('label')}")

    def _finish_live_action(self, generation: int) -> None:
        with self._live_action_lock:
            active = self._live_action_active
            if not active or int(active.get('generation') or 0) != int(generation):
                return
            self._live_action_active = None
            self._live_action_timer = None
            if self._live_action_queue:
                key, next_action = sorted(
                    self._live_action_queue.items(),
                    key=lambda item: (-int(item[1].get('priority') or 0), float(item[1].get('queued_at') or 0.0)),
                )[0]
                self._live_action_queue.pop(key, None)
                self._start_live_action_locked(next_action)

    def _trigger_live_action_routes(self, settings: dict[str, Any], state: dict[str, Any], routes: list[dict[str, Any]], label: str) -> None:
        if not routes:
            return
        settings = self._settings_with_live_meld_routes(settings)
        normalized_routes = [dict(route) for route in routes]
        route_sources = {str(route.get('source_key') or '').strip().lower() for route in normalized_routes}
        source_key = max(route_sources, key=lambda key: self._live_action_priority(key)) if route_sources else ''
        priority = self._live_action_priority(source_key)
        action = {
            'settings': dict(settings or {}),
            'state': state,
            'routes': normalized_routes,
            'label': str(label or source_key or 'live action'),
            'source_key': source_key,
            'priority': priority,
            'queued_at': time.monotonic(),
        }

        with self._live_action_lock:
            active = self._live_action_active
            if active is None:
                self._start_live_action_locked(action)
                return

            active_priority = int(active.get('priority') or 0)
            if priority > active_priority:
                old_timer = self._live_action_timer
                if old_timer is not None:
                    with contextlib.suppress(Exception):
                        old_timer.cancel()
                self._live_action_timer = None
                old_label = str(active.get('label') or '')
                old_routes = list(active.get('routes') or [])
                self._live_action_active = None
                self._live_action_queue = {
                    key: queued for key, queued in self._live_action_queue.items()
                    if int(queued.get('priority') or 0) > priority
                }
                self._stop_live_action_routes_ui(old_routes, f'interrupted by {action["label"]}')
                self.logger.info(f'Live action interrupted: {old_label} -> {action["label"]}')
                self._start_live_action_locked(action)
                return

            self._live_action_queue[source_key or str(label or 'live_action')] = action
            self.logger.debug(
                f"Live action queued: {action['label']} (prio {priority}) while {active.get('label')} is active"
            )

    def trigger_live_action_test_route(self, settings: dict[str, Any], state: dict[str, Any], route: dict[str, Any], source_key: str, label: str) -> tuple[int, int, str]:
        route = dict(route or {})
        source_key = str(source_key or route.get('source_key') or '').strip().lower()
        if source_key:
            route['source_key'] = source_key
        self._trigger_live_action_routes(settings, state, [route], label)
        active = self._live_action_active
        if active and str(active.get('label') or '') == str(label or ''):
            return 1, 0, 'started through global Live Action lock'
        return 0, 0, 'queued through global Live Action lock'

    def _snapshot_state_for_actions(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                'channel': self._state.get('channel', ''),
                'latest': dict(self._state.get('latest') or {}),
                'goals': {k: dict(v) for k, v in (self._state.get('goals') or {}).items()},
                'rankings': {k: [dict(x) for x in v] for k, v in (self._state.get('rankings') or {}).items()},
                'ticker': dict(self._state.get('ticker') or {}),
            }

    def _trigger_live_action(self, settings: dict[str, Any], source_key: str, label: str) -> None:
        settings = self._settings_with_live_meld_routes(settings)
        source_key = str(source_key or '').strip().lower()
        routes = self._enabled_live_action_routes(settings, {source_key})
        if not routes:
            return
        state = self._snapshot_state_for_actions()
        self._trigger_live_action_routes(settings, state, routes, label)

    def _check_live_action_milestone(
        self,
        settings: dict[str, Any],
        source_key: str,
        total_value: int,
        default_step: int,
        *,
        before_value: int | None = None,
    ) -> bool:
        settings = self._settings_with_live_meld_routes(settings)
        source_key = str(source_key or '').strip().lower()
        routes = self._enabled_live_action_routes(settings, {source_key})
        # Keep old one-button versions working too.
        if source_key == 'live_action_like_milestone':
            routes += self._enabled_live_action_routes(settings, set(LEGACY_ACTION_SOURCE_KEYS))
        if not routes:
            return False

        total_value = max(0, int(total_value or 0))
        if before_value is None:
            before_value = max(0, total_value - 1)
        else:
            before_value = max(0, int(before_value or 0))
        if total_value <= before_value:
            return False

        matched: list[dict[str, Any]] = []
        reached_labels: list[str] = []
        for route in routes:
            try:
                step = int(route.get('threshold') or 0)
            except Exception:
                step = 0
            if step <= 0:
                step = int(default_step or 1)
            step = max(1, step)
            target_user = self._normalize_route_user(route.get('target_user') or route.get('user_name') or '')
            route_key = f"{source_key}:{target_user}:{step}:{route.get('scene_id','')}:{route.get('scene_name','')}:{route.get('layer_id','')}:{route.get('layer_name','')}:{route.get('property_name','')}"

            crossed_value = ((before_value // step) + 1) * step
            saved_next = int(self._live_action_next.get(route_key) or 0)
            if saved_next > crossed_value:
                crossed_value = saved_next

            if crossed_value > total_value:
                with contextlib.suppress(Exception):
                    self.logger.debug(
                        f"Live action milestone waiting: {source_key} before={before_value}, after={total_value}, next={crossed_value}, step={step}"
                    )
                continue

            route_copy = dict(route)
            route_copy['threshold'] = step
            matched.append(route_copy)

            reached_for_route: list[str] = []
            while crossed_value <= total_value:
                reached_for_route.append(str(crossed_value))
                crossed_value += step
            reached_labels.extend(reached_for_route)
            self._live_action_next[route_key] = crossed_value

        if not matched:
            return False

        reached_text = ','.join(reached_labels)
        with self._state_lock:
            latest = self._state.setdefault('latest', {})
            if source_key in {'live_action_like_milestone', 'live_action_personal_like_milestone'}:
                latest['like_milestone'] = reached_text
                latest['like_milestone_total'] = total_value
            elif source_key in {'live_action_gift_milestone', 'live_action_personal_gift_milestone'}:
                latest['gift_milestone'] = reached_text
                latest['gift_milestone_total'] = total_value

        state = self._snapshot_state_for_actions()
        self.logger.info(f"Milestone reached: {source_key} before={before_value}, after={total_value}, reached={reached_text}")
        self._trigger_live_action_routes(settings, state, matched, f"{source_key} {reached_text}/{total_value}")
        return True

    def _check_like_milestone(self, settings: dict[str, Any], before_likes: int, total_likes: int) -> bool:
        return self._check_live_action_milestone(settings, 'live_action_like_milestone', total_likes, 200, before_value=before_likes)

    def _check_personal_like_milestone(self, settings: dict[str, Any], username: str, user_key: str, before_total: int, user_total: int) -> bool:
        settings = self._settings_with_live_meld_routes(settings)
        candidates = self._candidate_user_keys(username, user_key)
        routes = []
        for route in self._enabled_live_action_routes(settings, {'live_action_personal_like_milestone'}):
            target = self._normalize_route_user(route.get('target_user') or route.get('user_name') or '')
            if not target or target not in candidates:
                continue
            routes.append(route)
        if not routes:
            return False
        temp_settings = {
            'meld_routes_json': MeldOutputManager(getattr(self, 'logger', None), self).save_routes_text(routes),
            '__prefer_inline_meld_routes': True,
        }
        return self._check_live_action_milestone(
            temp_settings,
            'live_action_personal_like_milestone',
            user_total,
            1000,
            before_value=before_total,
        )

    def _check_personal_gift_milestone(self, settings: dict[str, Any], username: str, user_key: str, before_total: int, user_total: int) -> bool:
        settings = self._settings_with_live_meld_routes(settings)
        candidates = self._candidate_user_keys(username, user_key)
        routes = []
        for route in self._enabled_live_action_routes(settings, {'live_action_personal_gift_milestone'}):
            target = self._normalize_route_user(route.get('target_user') or route.get('user_name') or '')
            if not target or target not in candidates:
                continue
            routes.append(route)
        if not routes:
            return False
        temp_settings = {
            'meld_routes_json': MeldOutputManager(getattr(self, 'logger', None), self).save_routes_text(routes),
            '__prefer_inline_meld_routes': True,
        }
        return self._check_live_action_milestone(
            temp_settings,
            'live_action_personal_gift_milestone',
            user_total,
            1000,
            before_value=before_total,
        )

    def _check_gift_milestone(self, settings: dict[str, Any], before_gifts: int, total_gifts: int) -> bool:
        return self._check_live_action_milestone(settings, 'live_action_gift_milestone', total_gifts, 10, before_value=before_gifts)

    def _record_follow(self, settings, username: str) -> None:
        self.logger.info(f"📌 FOLLOW event: {username} followed the stream")
        self._event_counters['follow'] += 1
        with self._state_lock:
            self._state['latest']['follower'] = username
            self._state['goals']['followers']['current'] += 1
            self._update_ticker(settings)
        self._emit_state(settings)
        self._trigger_live_action(settings, 'live_action_follow', f'follow:{username}')
        self.logger.debug(f"State after follow: follower_count={self._state['goals']['followers']['current']}")

    def _record_like(self, settings, username: str, user_key: str, count: int, liker_rankings: dict[str, dict[str, Any]]) -> None:
        count = max(1, int(count or 1))
        self.logger.info(f"❤️ LIKE event: {username} sent {count} like{'s' if count > 1 else ''}")
        self._event_counters['like'] += count
        limit = self._int_setting(settings, 'ranking_size', 5, 1, 20)
        with self._state_lock:
            before_total_likes = int(self._state['goals']['likes']['current'] or 0)
            self._state['latest']['like_user'] = username
            self._state['latest']['like_count'] = count
            self._state['goals']['likes']['current'] = before_total_likes + count
            total_likes = int(self._state['goals']['likes']['current'] or 0)
            entry = liker_rankings.setdefault(user_key, {'name': username, 'count': 0})
            if username and username != 'unknown':
                entry['name'] = username
            elif not entry.get('name'):
                entry['name'] = user_key
            entry['count'] += count
            self._state['rankings']['likers'] = self._top_items(liker_rankings, limit)
            self._update_ticker(settings)

        self._emit_state(settings)
        self._trigger_live_action(settings, 'live_action_like', f'like:{username}+{count}')

        user_total = 0
        before_user_total = 0
        personal_triggered = False
        if self._has_personal_routes_for_user(settings, 'live_action_personal_like_milestone', username, user_key):
            personal_key = self._normalize_route_user(user_key) or self._normalize_route_user(username)
            before_user_total = int(self._personal_like_counts.get(personal_key, 0))
            user_total = before_user_total + count
            self._personal_like_counts[personal_key] = user_total
            self.logger.info(
                f"Personal LIKE counter: user={username}, delta={count}, before={before_user_total}, after={user_total}"
            )
            personal_triggered = self._check_personal_like_milestone(settings, username, user_key, before_user_total, user_total)
        else:
            with contextlib.suppress(Exception):
                user_total = int(liker_rankings.get(user_key, {}).get('count') or 0)

        if personal_triggered:
            self.logger.debug(f"Global like milestone skipped because personal milestone fired for {username}")
        else:
            self._check_like_milestone(settings, before_total_likes, total_likes)
        self.logger.debug(f"State after like: total_likes={total_likes}, user_total={user_total}")

    def _record_gift(self, settings, username: str, user_key: str, gift_name: str, count: int, gifter_rankings: dict[str, dict[str, Any]]) -> None:
        count = max(1, int(count or 1))
        self.logger.info(f"🎁 GIFT event: {username} sent {count} x {gift_name}")
        self._event_counters['gift'] += count
        limit = self._int_setting(settings, 'ranking_size', 5, 1, 20)
        with self._state_lock:
            before_total_gifts = int(self._state['goals']['gifts']['current'] or 0)
            self._state['latest']['gift_user'] = username
            self._state['latest']['gift_name'] = gift_name
            self._state['latest']['gift_count'] = count
            self._state['goals']['gifts']['current'] = before_total_gifts + count
            total_gifts = int(self._state['goals']['gifts']['current'] or 0)
            entry = gifter_rankings.setdefault(user_key, {'name': username, 'count': 0})
            entry['name'] = username
            entry['count'] += count
            self._state['rankings']['gifters'] = self._top_items(gifter_rankings, limit)
            self._update_ticker(settings)
        self._emit_state(settings)
        self._trigger_live_action(settings, 'live_action_gift', f'gift:{username}x{count}')

        user_total = 0
        before_user_total = 0
        personal_triggered = False
        if self._has_personal_routes_for_user(settings, 'live_action_personal_gift_milestone', username, user_key):
            personal_key = self._normalize_route_user(user_key) or self._normalize_route_user(username)
            before_user_total = int(self._personal_gift_counts.get(personal_key, 0))
            user_total = before_user_total + count
            self._personal_gift_counts[personal_key] = user_total
            self.logger.info(
                f"Personal GIFT counter: user={username}, delta={count}, before={before_user_total}, after={user_total}"
            )
            personal_triggered = self._check_personal_gift_milestone(settings, username, user_key, before_user_total, user_total)
        else:
            with contextlib.suppress(Exception):
                user_total = int(gifter_rankings.get(user_key, {}).get('count') or 0)

        if personal_triggered:
            self.logger.debug(f"Global gift milestone skipped because personal milestone fired for {username}")
        else:
            self._check_gift_milestone(settings, before_total_gifts, total_gifts)
        self.logger.debug(f"State after gift: total_gifts={total_gifts}, user_total={user_total}")

    def _msg_value(self, msg: Any, key: str, default: Any = '') -> Any:
        try:
            if isinstance(msg, dict):
                return msg.get(key, default)
            return getattr(msg, key, default)
        except Exception:
            return default

    def _external_event_increment_from_message(self, msg: Any, *, is_gift: bool = False) -> int:
        # Important: this must be the DELTA of the current event/bundle, not TikTok's global stream total.
        # Using fields like total_likes/total_count as an increment made milestones fire on the first event.
        keys = (
            'alert_count',
            'event_count',
            'increment',
            'delta',
            'repeat_count',
            'repeatCount',
            'count',
        )
        if is_gift:
            keys = ('gift_count', 'giftCount') + keys
        else:
            keys = ('like_count', 'likeCount', 'likes') + keys
        for key in keys:
            value = self._msg_value(msg, key, None)
            try:
                if value is not None and str(value).strip() != '':
                    return max(1, int(float(str(value).strip())))
            except Exception:
                pass
        text = ' '.join(str(self._msg_value(msg, key, '') or '') for key in ('text', 'message', 'content', 'comment'))
        patterns = (
            r'(?i)\b(?:sent|sendet|schickt)?\s*(\d+)\s*(?:like|likes)\b',
            r'(?i)\b(?:sent|sendet|schickt)?\s*(\d+)\s*x\b',
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                with contextlib.suppress(Exception):
                    return max(1, int(match.group(1)))
        return 1

    def _external_like_count_from_message(self, msg: Any) -> int:
        return self._external_event_increment_from_message(msg, is_gift=False)

    def _external_gift_count_from_message(self, msg: Any) -> int:
        return self._external_event_increment_from_message(msg, is_gift=True)

    def _bridge_settings(self) -> dict[str, Any]:
        settings = dict(getattr(self, '_settings', {}) or {})
        if not settings:
            settings = self.default_settings()
        return self._settings_with_live_meld_routes(settings)

    def _bridge_emit_alert(self, settings: dict[str, Any], username: str, text: str, channel: str, message_type: str) -> None:
        host = getattr(self, '_runtime_host', None)
        if host is None:
            return
        show_desktop, show_obs = self._alert_output_flags(settings)
        self._emit_message(
            host,
            username=username,
            text=text,
            channel=channel,
            message_type=message_type,
            show_in_desktop=show_desktop,
            show_in_obs=show_obs,
        )

    def on_message(self, msg: Any) -> None:
        try:
            source_plugin = str(self._msg_value(msg, 'source_plugin_id', '') or '').strip()
            # Accept the direct alert bridge from the tiktok_live chat plugin.
            # Do NOT consume our own emitted tiktok_live_alert messages again;
            # that can create alert/log feedback loops, especially for joins.
            if source_plugin and source_plugin != 'tiktok_live':
                return
            platform = str(self._msg_value(msg, 'platform', '') or '').strip().lower()
            if platform and platform != 'tiktok':
                return

            msg_type = str(self._msg_value(msg, 'message_type', '') or self._msg_value(msg, 'event_type', '') or self._msg_value(msg, 'type', '') or '').strip().lower()
            alert_type = str(self._msg_value(msg, 'alert_type', '') or self._msg_value(msg, 'alert_kind', '') or '').strip().lower()
            is_follow = msg_type in {'tiktok_follow', 'follow', 'follower', 'new_follow', 'new_follower'} or alert_type in {'follow', 'follower'}
            is_like = msg_type in {'tiktok_like', 'like', 'likes'} or alert_type in {'like', 'likes'}
            is_gift = msg_type in {'tiktok_gift', 'gift', 'gifts'} or alert_type in {'gift', 'gifts'}
            is_share = msg_type in {'tiktok_share', 'share', 'shares'} or alert_type in {'share', 'shares'}
            is_join = msg_type in {'tiktok_join', 'join', 'joins', 'viewer_join', 'tiktok_viewer_join', 'user_join', 'joiner'} or alert_type in {'join', 'joins', 'viewer_join', 'user_join', 'joiner'}
            is_subscribe = msg_type in {'tiktok_subscribe', 'subscribe', 'sub', 'subscription', 'member', 'tiktok_member'} or alert_type in {'subscribe', 'sub', 'subscription', 'member'}
            if not any((is_follow, is_like, is_gift, is_share, is_join, is_subscribe)):
                return

            settings = self._bridge_settings()

            username = str(self._msg_value(msg, 'username', '') or self._msg_value(msg, 'user', '') or 'unknown').strip() or 'unknown'
            channel = str(self._msg_value(msg, 'channel', '') or settings.get('unique_id', '') or '').strip()
            bridge_user_key = self._dedupe_user_key(
                self._msg_value(msg, 'user_id', ''),
                self._msg_value(msg, 'unique_id', ''),
                self._msg_value(msg, 'sec_uid', ''),
                self._msg_value(msg, 'user_unique_id', ''),
                username,
            )
            with self._state_lock:
                if channel and not self._state.get('channel'):
                    self._state['channel'] = channel
                self._state['goals']['followers']['target'] = self._int_setting(settings, 'follower_goal', 1000, 0, 100000000)
                self._state['goals']['likes']['target'] = self._int_setting(settings, 'like_goal', 10000, 0, 100000000)
                self._state['goals']['gifts']['target'] = self._int_setting(settings, 'gift_goal', 100, 0, 100000000)

            if is_follow:
                self.logger.info(f"Live bridge FOLLOW from tiktok_live: {username}")
                self._record_follow(settings, username)
                self._bridge_emit_alert(settings, username, 'followed the stream', channel, 'tiktok_follow')
                return

            if is_share:
                self.logger.info(f"Live bridge SHARE from tiktok_live: {username}")
                self._event_counters['share'] += 1
                self._trigger_live_action(settings, 'live_action_share', f'share:{username}')
                self._bridge_emit_alert(settings, username, 'shared the stream', channel, 'tiktok_share')
                return

            if is_join:
                if not _as_bool(settings.get('enable_joins', True)):
                    self.logger.debug(f"Live bridge JOIN ignored because joins are disabled: {username}")
                    return
                join_dedupe_seconds = self._int_setting(settings, 'join_dedupe_seconds', 60, 0, 600)
                if not self._should_process_recent_event('join', bridge_user_key, join_dedupe_seconds, log_label=f'Live bridge JOIN from tiktok_live: {username}'):
                    return
                self.logger.info(f"Live bridge JOIN from tiktok_live: {username}")
                self._event_counters['join'] += 1
                self._trigger_live_action(settings, 'live_action_join', f'join:{username}')
                self._bridge_emit_alert(settings, username, 'joined the stream', channel, 'tiktok_join')
                return

            if is_subscribe:
                if not _as_bool(settings.get('enable_subscribes', True)):
                    self.logger.debug(f"Live bridge SUBSCRIBE ignored because subscribes are disabled: {username}")
                    return
                self.logger.info(f"Live bridge SUBSCRIBE from tiktok_live: {username}")
                self._event_counters['subscribe'] += 1
                self._trigger_live_action(settings, 'live_action_subscribe', f'subscribe:{username}')
                self._bridge_emit_alert(settings, username, 'subscribed / became a member', channel, 'tiktok_subscribe')
                return

            user_key = str(self._msg_value(msg, 'user_id', '') or self._msg_value(msg, 'unique_id', '') or username).strip().casefold() or username.casefold()
            if is_gift:
                count = self._external_gift_count_from_message(msg)
                gift_name = str(self._msg_value(msg, 'gift_name', '') or self._msg_value(msg, 'gift', '') or '').strip()
                if not gift_name:
                    text = ' '.join(str(self._msg_value(msg, key, '') or '') for key in ('text', 'message', 'content', 'comment'))
                    match = re.search(r'(?i)x\s+(.+)$', text)
                    gift_name = match.group(1).strip() if match else 'gift'
                self.logger.info(f"Live bridge GIFT from tiktok_live: {username} {gift_name} x{count}")
                self._record_gift(settings, username, user_key, gift_name, count, self._external_gifter_rankings)
                self._bridge_emit_alert(settings, username, f'sent {count} x {gift_name}', channel, 'tiktok_gift')
                return

            count = self._external_like_count_from_message(msg)
            self.logger.info(f"Live bridge LIKE from tiktok_live: {username} +{count}")
            self._record_like(settings, username, user_key, count, self._external_liker_rankings)
            self._bridge_emit_alert(settings, username, f'sent {count} likes', channel, 'tiktok_like')
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.logger.warning(f'Live bridge message handling failed: {exc}')

    def run(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._runtime_host = host
        settings = self._effective_settings(settings, host)
        if not _as_bool(settings.get('_platform_read_enabled', True)):
            host.set_status(self.plugin_id, PluginStatus('disabled', 'TikTok reading disabled in Platforms.'))
            self.logger.info('TikTok LIVE Alert not started because reading is disabled in Platforms.')
            return
        with contextlib.suppress(Exception):
            import builtins
            registry = getattr(builtins, '_godisalotachat_plugin_registry', None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(builtins, '_godisalotachat_plugin_registry', registry)
            registry[self.plugin_id] = self
        autoconnect = _as_bool(settings.get('autoconnect', False))
        viewer_check_interval = self._float_setting(settings, 'viewer_check_interval_seconds', 5.0, 1.0, 60.0)
        aggregate_window = self._aggregate_window(settings)
        enable_comments = _as_bool(settings.get('enable_comments', False))
        enable_follows = _as_bool(settings.get('enable_follows', False))
        enable_likes = _as_bool(settings.get('enable_likes', False))
        enable_gifts = _as_bool(settings.get('enable_gifts', False))
        enable_shares = _as_bool(settings.get('enable_shares', False))
        enable_joins = _as_bool(settings.get('enable_joins', True))
        enable_subscribes = _as_bool(settings.get('enable_subscribes', True))
        show_comments_in_desktop = _as_bool(settings.get('show_comments_in_desktop', False))
        show_comments_in_obs = _as_bool(settings.get('show_comments_in_obs', False))
        show_alerts_in_desktop, show_alerts_in_obs = self._alert_output_flags(settings)

        auto_follow_outputs = any(_as_bool(settings.get(k, True)) for k in ('enable_latest_follower_txt', 'enable_follower_goal_txt'))
        auto_like_outputs = any(_as_bool(settings.get(k, True)) for k in ('enable_latest_like_txt', 'enable_top_liker_txt', 'enable_like_goal_txt'))
        auto_gift_outputs = any(_as_bool(settings.get(k, True)) for k in ('enable_latest_gift_txt', 'enable_top_gifter_txt', 'enable_gift_goal_txt'))
        enable_follows = enable_follows or auto_follow_outputs
        enable_likes = enable_likes or auto_like_outputs
        enable_gifts = enable_gifts or auto_gift_outputs

        comments_visible_anywhere = enable_comments and (show_comments_in_desktop or show_comments_in_obs)
        alerts_visible_anywhere = (show_alerts_in_desktop or show_alerts_in_obs) and any(
            (enable_follows, enable_likes, enable_gifts, enable_shares, enable_joins, enable_subscribes)
        )
        self.logger.info(
            f"Alert output routes - Desktop: {show_alerts_in_desktop}, OBS: {show_alerts_in_obs}, active: {alerts_visible_anywhere}"
        )

        def _current_unique_id() -> str:
            return str(settings.get('unique_id', '') or '').strip()

        initial_unique_id = _current_unique_id()
        if not initial_unique_id:
            host.set_status(self.plugin_id, PluginStatus('error', 'Missing @unique_id.'))
            self.logger.error('No unique_id provided in settings')
            return

        self.logger.info(f"Starting connection to TikTok LIVE: @{initial_unique_id}")
        self.logger.info(
            f"Event settings - Follows: {enable_follows}, Likes: {enable_likes}, Gifts: {enable_gifts}, "
            f"Comments: {enable_comments}, Shares: {enable_shares}, Joins: {enable_joins}, Subscribes: {enable_subscribes}, Autoconnect: {autoconnect}"
        )

        async def _wait_for_live_start() -> str | None:
            last_target = ''
            while not self._stop.is_set():
                current_unique_id = _current_unique_id()
                if not current_unique_id:
                    host.set_status(self.plugin_id, PluginStatus('watching', 'Watching for live start'))
                    await asyncio.sleep(viewer_check_interval)
                    continue

                if current_unique_id != last_target:
                    self.logger.info(f'Watcher now monitoring @{current_unique_id} for live start')
                    host.set_status(self.plugin_id, PluginStatus('watching', f'Watching for live start: {current_unique_id}'))
                    last_target = current_unique_id

                try:
                    client = TikTokLiveClient(unique_id=current_unique_id)
                    is_live = await client.is_live()
                except Exception as exc:
                    self.logger.debug(f'Watcher check for @{current_unique_id} failed: {exc}')
                    is_live = False

                if is_live:
                    self.logger.info(f'Watcher detected live start for @{current_unique_id}')
                    return current_unique_id

                await asyncio.sleep(viewer_check_interval)
            return None

        async def _run_session(unique_id: str) -> tuple[str | None, bool]:
            channel = unique_id
            self._pending_alerts.clear()
            self._pending_lock = asyncio.Lock()
            liker_rankings, gifter_rankings = self._init_runtime_state(settings, channel)
            self._emit_state(settings, force=True)

            client = TikTokLiveClient(unique_id=unique_id)
            connection_established = asyncio.Event()

            @client.on(ConnectEvent)
            async def on_connect(event: ConnectEvent):
                self.logger.info(f"✅ Connected to TikTok LIVE: @{unique_id}")
                self._emit_state(settings, force=True)
                connection_established.set()

            async def _on_comment(event: CommentEvent):
                if not comments_visible_anywhere:
                    return
                text = self._extract_text(event)
                if not text:
                    return
                username = self._user_name(event)
                self.logger.info(f"💬 COMMENT from {username}: {text[:50]}...")
                self._event_counters['comment'] += 1
                self._emit_message(host, username=username, text=text, channel=channel, message_type='chat',
                                   show_in_desktop=show_comments_in_desktop, show_in_obs=show_comments_in_obs)

            async def _on_follow(event: FollowEvent):
                if not enable_follows:
                    self.logger.debug('Follow event received but follows are disabled')
                    return
                username = self._user_name(event)
                self._record_follow(settings, username)
                if alerts_visible_anywhere:
                    self._emit_alert_now(
                        host,
                        username=username,
                        text='followed the stream',
                        channel=channel,
                        message_type='tiktok_follow',
                        show_in_desktop=show_alerts_in_desktop,
                        show_in_obs=show_alerts_in_obs,
                    )

            async def _on_share(event: ShareEvent):
                if not alerts_visible_anywhere or not enable_shares:
                    return
                username = self._user_name(event)
                self.logger.info(f"📤 SHARE event: {username} shared the stream")
                self._event_counters['share'] += 1
                user_key = self._user_handle(event)
                self._emit_alert_now(
                    host,
                    username=username,
                    text='shared the stream',
                    channel=channel,
                    message_type='tiktok_share',
                    show_in_desktop=show_alerts_in_desktop,
                    show_in_obs=show_alerts_in_obs,
                )

            async def _on_join(event: JoinEvent):
                if not enable_joins:
                    return
                username = self._user_name(event)
                user_key = self._user_handle(event)
                join_dedupe_seconds = self._int_setting(settings, 'join_dedupe_seconds', 60, 0, 600)
                if not self._should_process_recent_event('join', user_key or username, join_dedupe_seconds, log_label=f'JOIN event: {username}'):
                    return
                self.logger.info(f"👋 JOIN event: {username} joined the stream")
                self._event_counters['join'] += 1
                if alerts_visible_anywhere:
                    self._emit_alert_now(
                        host,
                        username=username,
                        text='joined the stream',
                        channel=channel,
                        message_type='tiktok_join',
                        show_in_desktop=show_alerts_in_desktop,
                        show_in_obs=show_alerts_in_obs,
                    )

            async def _on_subscribe(event):
                if not enable_subscribes:
                    return
                username = self._user_name(event)
                self.logger.info(f"⭐ SUBSCRIBE event: {username} subscribed / became a member")
                self._event_counters['subscribe'] += 1
                self._trigger_live_action(settings, 'live_action_subscribe', f'subscribe:{username}')
                if alerts_visible_anywhere:
                    self._emit_alert_now(
                        host,
                        username=username,
                        text='subscribed / became a member',
                        channel=channel,
                        message_type='tiktok_subscribe',
                        show_in_desktop=show_alerts_in_desktop,
                        show_in_obs=show_alerts_in_obs,
                    )

            async def _on_like(event: LikeEvent):
                if not enable_likes:
                    self.logger.debug('Like event received but likes are disabled')
                    return
                username = self._user_name(event)
                user_key = self._user_handle(event)
                like_count = self._like_count(event)
                self._debug_like_event_fields(event, username, like_count)
                self._record_like(settings, username, user_key, like_count, liker_rankings)
                if alerts_visible_anywhere:
                    await self._queue_alert(f'like:{user_key}', username, 'sent {count} likes', channel, like_count)

            async def _on_gift(event: GiftEvent):
                if not enable_gifts:
                    self.logger.debug('Gift event received but gifts are disabled')
                    return
                username = self._user_name(event)
                user_key = self._user_handle(event)
                gift_name = self._gift_name(event)
                gift_count = self._gift_count(event)
                if gift_count <= 0:
                    self.logger.debug(f"Gift from {username}: {gift_name} - streak in progress, waiting for final count")
                    return
                self._record_gift(settings, username, user_key, gift_name, gift_count, gifter_rankings)
                if alerts_visible_anywhere:
                    self._emit_alert_now(
                        host,
                        username=username,
                        text=f'sent {gift_count} x {gift_name}',
                        channel=channel,
                        message_type='tiktok_gift',
                        show_in_desktop=show_alerts_in_desktop,
                        show_in_obs=show_alerts_in_obs,
                    )

            if comments_visible_anywhere:
                client.add_listener(CommentEvent, _on_comment)
                self.logger.info('Comment listener registered')
            if enable_follows:
                client.add_listener(FollowEvent, _on_follow)
                self.logger.info('Follow listener registered')
            if alerts_visible_anywhere and enable_shares:
                client.add_listener(ShareEvent, _on_share)
                self.logger.info('Share listener registered')
            if enable_joins:
                client.add_listener(JoinEvent, _on_join)
                if alerts_visible_anywhere:
                    self.logger.info('Join listener registered for alerts')
                else:
                    self.logger.info('Join listener registered for logging/counting only')
            if enable_subscribes and SubscribeEvent is not None:
                client.add_listener(SubscribeEvent, _on_subscribe)
                self.logger.info('Subscribe/member listener registered')
            elif enable_subscribes:
                self.logger.info('Subscribe/member listener unavailable in installed TikTokLive version')
            if enable_likes:
                client.add_listener(LikeEvent, _on_like)
                self.logger.info('Like listener registered')
            if enable_gifts:
                client.add_listener(GiftEvent, _on_gift)
                self.logger.info('Gift listener registered')

            flush_task = None
            connect_task = None
            should_watch_again = False
            final_status_text: str | None = None

            try:
                self.logger.info(f"Checking if @{unique_id} is live...")
                try:
                    live = await client.is_live()
                except Exception as exc:
                    self.logger.error(f"Connection error while checking live status: {exc}")
                    if autoconnect and not self._stop.is_set():
                        return f'Connection error: {exc}', True
                    host.set_status(self.plugin_id, PluginStatus('error', f"Connection error: {exc}"))
                    return None, False

                if not live:
                    self.logger.warning(f"Creator @{unique_id} is not live")
                    if autoconnect and not self._stop.is_set():
                        return f'@{unique_id} is currently offline.', True
                    host.set_status(self.plugin_id, PluginStatus('error', 'Creator is not live.'))
                    return None, False

                self.logger.info(f"✅ Creator @{unique_id} is live! Starting stream monitoring...")
                host.set_status(self.plugin_id, PluginStatus('connecting', f'Reading {channel}'))

                follower_count = await self._fetch_profile_follower_count(unique_id)
                if follower_count is not None:
                    with self._state_lock:
                        self._state['goals']['followers']['current'] = max(0, int(follower_count))
                    self.logger.info(f"Loaded current follower count: {follower_count}")
                else:
                    self.logger.warning('Current follower count could not be loaded; using 0 until follow events arrive')

                self._emit_state(settings, force=True)

                if alerts_visible_anywhere:
                    flush_task = asyncio.create_task(
                        self._flush_pending_loop(host, aggregate_window, show_alerts_in_desktop, show_alerts_in_obs)
                    )
                    self.logger.info(f"Alert flush task started (window: {aggregate_window}s)")

                self.logger.info('Connecting to TikTok LIVE stream...')
                connect_task = asyncio.create_task(client.connect())

                last_log_time = time.time()
                was_connected = False
                while not self._stop.is_set():
                    self._emit_state(settings, force=False)

                    if connection_established.is_set() and not was_connected:
                        host.set_status(self.plugin_id, PluginStatus('connected', f'Reading {channel}'))
                        was_connected = True

                    if connect_task.done():
                        exc = connect_task.exception()
                        if exc is not None:
                            self.logger.error(f'Connection task ended with error: {exc}')
                            if autoconnect and not self._stop.is_set():
                                should_watch_again = True
                                final_status_text = f'@{unique_id} disconnected.'
                                break
                            raise exc
                        if autoconnect and not self._stop.is_set():
                            should_watch_again = True
                            final_status_text = f'@{unique_id} stream ended.'
                        break

                    now = time.time()
                    if now - last_log_time >= 60:
                        self.logger.info(
                            f"Event counters - Follows: {self._event_counters['follow']}, Likes: {self._event_counters['like']}, "
                            f"Gifts: {self._event_counters['gift']}, Comments: {self._event_counters['comment']}, "
                            f"Shares: {self._event_counters['share']}, Joins: {self._event_counters['join']}"
                        )
                        last_log_time = now

                    await asyncio.sleep(0.5)

            finally:
                self.logger.info('Shutting down TikTok LIVE connection...')
                if flush_task is not None:
                    flush_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await flush_task

                if connect_task is not None and not connect_task.done():
                    connect_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await connect_task

                try:
                    await client.disconnect()
                    self.logger.info('Disconnected from TikTok LIVE')
                except Exception as e:
                    self.logger.error(f'Error during disconnect: {e}')

            return final_status_text, should_watch_again

        async def _main():
            final_status_text: str | None = None
            while not self._stop.is_set():
                current_unique_id = _current_unique_id()
                if not current_unique_id:
                    host.set_status(self.plugin_id, PluginStatus('error', 'Missing @unique_id.'))
                    return None

                if autoconnect:
                    resolved_unique_id = await _wait_for_live_start()
                    if resolved_unique_id is None:
                        break
                else:
                    resolved_unique_id = current_unique_id

                final_status_text, should_watch_again = await _run_session(resolved_unique_id)
                if not autoconnect or not should_watch_again:
                    return final_status_text

                current_target = _current_unique_id() or resolved_unique_id
                host.set_status(self.plugin_id, PluginStatus('watching', final_status_text or f'Watching for live start: {current_target}'))

            return final_status_text

        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_status_text = loop.run_until_complete(_main())
            host.set_status(self.plugin_id, PluginStatus('disconnected', final_status_text or 'Stopped'))
        except Exception as e:
            self.logger.error(f'Plugin error: {e}')
            host.set_status(self.plugin_id, PluginStatus('error', 'Plugin error occurred'))
        finally:
            if loop is not None:
                with contextlib.suppress(Exception):
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                with contextlib.suppress(Exception):
                    loop.close()
            with contextlib.suppress(Exception):
                asyncio.set_event_loop(None)


TikTokLiveAlertPlugin.__abstractmethods__ = frozenset()


def create_plugin():
    return TikTokLiveAlertPlugin()
