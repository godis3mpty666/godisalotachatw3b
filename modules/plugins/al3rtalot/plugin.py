from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

from al3rtalot_common import EVENT_LABELS, PLATFORM_LABELS, PLATFORMS, as_bool, atomic_write_json, main_data_dir, now_ms, to_int
from al3rtalot_platforms import KickAlerts, TikTokAlerts, TwitchAlerts, YouTubeAlerts

PLUGIN_ID = 'al3rtalot'
PLUGIN_VERSION = '0.03'
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
        self._export_state: dict[str, Any] = {"latest_alert": {}, "events": {}, "platforms": {}}
        self._leaderboards: dict[str, dict[str, dict[str, int]]] = {"tiktok": {"likes": {}, "gifts": {}}}
        self._automation_recent: dict[str, float] = {}
        self._like_threshold_fired: set[str] = set()
        self._auto_hide_timers: dict[str, threading.Timer] = {}
        self._startup_automation_attempt = 0
        self._startup_automation_done: set[str] = set()
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
            {'key': 'alert_to_chat_overlay', 'label': 'Alerts im Desktop-Alertbereich ausgeben', 'type': 'bool', 'help': 'Schickt den Alert ausschließlich an den zentralen Alertbereich des Desktopfensters.'},
            {'key': 'ignored_users', 'label': 'Global ignorierte User', 'type': 'taglist', 'wide': True, 'placeholder': 'nightbot, streamelements, ...'},
            {'key': 'dedupe_seconds', 'label': 'Doppelte Alerts blocken (Sekunden)', 'type': 'number', 'min': 0, 'max': 120},
            {'key': 'exports_path', 'label': 'OBS/Meld-Exportordner', 'readonly': True, 'placeholder': 'data/al3rtalot/exports'},
            {'key': 'button_test_alert', 'type': 'button', 'label': 'Desktop-Testalert', 'button_text': 'Testalert im Desktopfenster anzeigen'},
        ], en='Overview')
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
                    {'key': f'{platform}_{event}_template', 'label': f'{title} Text', 'type': 'template', 'wide': True, 'placeholder': '{user}: {text}', 'tokens': ['{platform}', '{event_label}', '{user}', '{text}', '{amount}', '{gift_name}', '{channel}']},
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
            'exports_path': str(DATA_DIR / 'exports'),
            'chat_title': '{event_label}',
            'chat_template': '{user}: {text}',
            'follow_title': 'Neuer Follow',
            'follow_template': '{user} folgt jetzt auf {platform}',
            'join_title': 'Join',
            'join_template': '{user} ist im Live',
            'like_title': 'Likes',
            'like_template': '{user} hat {amount} Likes geschickt',
            'gift_title': 'Gift',
            'gift_template': '{user}: {text}',
            'share_title': 'Share',
            'share_template': '{user} hat den Stream geteilt',
            'subscribe_title': 'Sub',
            'subscribe_template': '{user} hat abonniert',
            'raid_title': 'Raid',
            'raid_template': '{user} raidet den Kanal',
            'donation_title': 'Donation',
            'donation_template': '{user} hat {amount} gespendet',
            'bits_title': 'Bits',
            'bits_template': '{user} hat {amount} Bits gesendet',
            'member_title': 'Member',
            'member_template': '{user} ist Mitglied geworden',
            'superchat_title': 'Superchat',
            'superchat_template': '{user}: {text}',
            'supersticker_title': 'Supersticker',
            'supersticker_template': '{user} hat einen Supersticker geschickt',
            'live_status_title': 'Kick Live-Status',
            'live_status_template': '{user}: {text}',
        }
        for platform, handler in self._platforms.items():
            defaults[f'{platform}_enabled'] = True
            defaults[f'{platform}_accent_color'] = handler.default_color
            defaults[f'{platform}_ignored_users'] = ''
            for event in handler.supported_events:
                # Normale Chatnachrichten gehören ins Chatfenster, nicht als Alert ins Desktop-/OBS-/Meld-Fenster.
                # Die Option bleibt vorhanden, ist aber absichtlich standardmäßig aus.
                defaults[f'{platform}_enable_{event}'] = False if event == 'chat' else True
                defaults[f'{platform}_{event}_title'] = defaults.get(f'{event}_title', '{event_label}')
                defaults[f'{platform}_{event}_template'] = defaults.get(f'{event}_template', '{user}: {text}')
        return defaults

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        merged = self.default_settings()
        if isinstance(settings, dict):
            merged.update(settings)
        if str(merged.get('tiktok_gift_template') or '').strip() == '{user} hat ein Gift geschickt':
            merged['tiktok_gift_template'] = '{user}: {text}'
        self._settings = merged
        self._enabled = as_bool(merged.get('enabled'), True)
        self._startup_automation_attempt = 0
        self._startup_automation_done = set()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load_export_state()
        state = 'connected' if self._enabled else 'disabled'
        msg = f'{PLUGIN_NAME}: ' + ('aktiv' if self._enabled else 'deaktiviert')
        host.set_status(self.plugin_id, PluginStatus(state, msg))
        host.log(self.plugin_id, f'{PLUGIN_NAME} gestartet. Plattform-Alerts: Twitch/TikTok/YouTube/Kick.')
        if self._enabled:
            self._schedule_startup_automation()

    def stop(self, *args, **kwargs) -> None:
        self._enabled = False
        if self._host is not None:
            self._host.set_status(self.plugin_id, PluginStatus('stopped', 'Stopped'))

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        cfg = self._merged_settings(settings)
        enabled = [PLATFORM_LABELS[p] for p in PLATFORMS if as_bool(cfg.get(f'{p}_enabled'), True)]
        return True, 'Aktive Alert-Plattformen: ' + (', '.join(enabled) if enabled else 'keine')

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        if key == 'button_test_alert':
            self._push_alert({
                'platform': 'tiktok',
                'event_type': 'follow',
                'username': 'TestUser',
                'title': 'Follow',
                'text': 'folgt jetzt auf TikTok.',
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
            direct_bridge = as_bool(msg.get('direct_bridge'), False)
            if event.get('platform') == 'tiktok' and direct_bridge:
                self._update_live_values(event)
                return
            if not (event.get('platform') == 'tiktok' and event.get('event_type') in {'like', 'gift'}):
                self._update_live_values(event)
            if not handler.should_alert(event, settings):
                return
            alert = handler.build_alert(event, settings)
            if self._is_duplicate(alert, settings):
                return
            self._push_alert(alert)
            return

    def _update_live_values(self, event: dict[str, Any]) -> None:
        """Session-wide counters for durable values; deliberately separate from alerts."""
        if event.get('platform') != 'tiktok' or event.get('event_type') not in {'like', 'gift'}:
            return
        user = str(event.get('username') or '').strip()
        if not user:
            return
        board_name = 'likes' if event.get('event_type') == 'like' else 'gifts'
        amount = max(1, to_int(event.get('amount'), 1, 1))
        board = self._leaderboards['tiktok'][board_name]
        board[user] = int(board.get(user, 0)) + amount
        user_total = int(board.get(user, 0))
        top_user, top_amount = max(board.items(), key=lambda pair: (pair[1], pair[0].casefold()))
        live = self._export_state.setdefault('live_values', {}).setdefault('tiktok', {})
        value_key = 'top_liker' if board_name == 'likes' else 'top_gifter'
        live[value_key] = {'user': top_user, 'amount': top_amount, 'updated_at': now_ms()}
        if board_name == 'likes':
            live['like_total'] = {'user': user, 'amount': user_total, 'updated_at': now_ms()}
        self._write_live_value_exports('tiktok', value_key, top_user, top_amount)
        if board_name == 'likes':
            self._write_live_value_exports('tiktok', 'like_total', user, user_total)
            self._apply_like_threshold_rules(user, user_total)
        self._apply_automation_value('tiktok', value_key, top_user, top_amount)

    def _write_live_value_exports(self, platform: str, value: str, user: str, amount: int) -> None:
        export_dir = DATA_DIR / 'exports'
        item = {'platform': platform, 'value': value, 'user': user, 'amount': amount, 'updated_at': now_ms()}
        try:
            atomic_write_json(export_dir / f'{platform}_{value}.json', item)
            for name, content in ((f'{platform}_{value}.txt', user), (f'{platform}_{value}_count.txt', str(amount))):
                path = export_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(path.suffix + '.tmp')
                temp.write_text(content, encoding='utf-8')
                temp.replace(path)
            atomic_write_json(export_dir / 'state.json', self._export_state)
        except Exception as exc:
            self._log(f'live value export failed: {exc}')

    def _load_export_state(self) -> None:
        path = DATA_DIR / 'exports' / 'state.json'
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                self._export_state = data
        except Exception as exc:
            self._log(f'export state read failed: {exc}')

    def _startup_rule_key(self, rule: dict[str, Any]) -> str:
        return '|'.join([
            str(rule.get('platform') or '').strip().lower(),
            str(rule.get('value') or '').strip().lower(),
            str(rule.get('target') or '').strip().lower(),
            str(rule.get('action') or 'text').strip().lower(),
            str(rule.get('scene') or '').strip().casefold(),
            str(rule.get('source') or '').strip().casefold(),
        ])

    def _saved_live_value_text(self, rule: dict[str, Any]) -> str:
        platform = str(rule.get('platform') or '').strip().lower()
        value = str(rule.get('value') or '').strip().lower()
        live_values = self._export_state.get('live_values') if isinstance(self._export_state, dict) else None
        row: Any = None
        if isinstance(live_values, dict):
            platform_values = live_values.get(platform)
            if isinstance(platform_values, dict):
                row = platform_values.get(value)
        if not isinstance(row, dict):
            try:
                path = DATA_DIR / 'exports' / f'{platform}_{value}.json'
                if path.exists():
                    raw = json.loads(path.read_text(encoding='utf-8'))
                    if isinstance(raw, dict):
                        row = raw
            except Exception:
                row = None
        if isinstance(row, dict):
            return self._automation_text(platform, value, str(row.get('user') or ''), to_int(row.get('amount'), 0, 0))
        try:
            path = DATA_DIR / 'exports' / f'{platform}_{value}.txt'
            if path.exists():
                return path.read_text(encoding='utf-8').strip()
        except Exception:
            pass
        return ''

    def _startup_text_for_rule(self, rule: dict[str, Any]) -> str:
        startup = str(rule.get('startup') or 'keep').strip().lower()
        if startup == 'placeholder':
            return str(rule.get('placeholder') or '---').strip() or '---'
        return self._saved_live_value_text(rule)

    def _automation_target_ready(self, target: str) -> bool:
        plugin_id = 'meld_control' if target == 'meld' else 'obs_control' if target == 'obs' else ''
        plugin = self._get_plugin(plugin_id) if plugin_id else None
        return plugin is not None and bool(getattr(plugin, 'is_connected', lambda: False)())

    def _schedule_startup_automation(self, delay: float = 1.2) -> None:
        timer = threading.Timer(delay, self._apply_startup_automation)
        timer.daemon = True
        timer.start()

    def _apply_startup_automation(self) -> None:
        if not self._enabled:
            return
        settings = self._global_settings()
        rules = settings.get('automation_rules')
        if not isinstance(rules, list):
            return
        self._startup_automation_attempt += 1
        pending = 0
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if str(rule.get('action') or 'text').strip().lower() != 'text':
                continue
            key = self._startup_rule_key(rule)
            if key in self._startup_automation_done:
                continue
            text = self._startup_text_for_rule(rule)
            if not text:
                continue
            target = str(rule.get('target') or '').strip().lower()
            if not self._automation_target_ready(target):
                pending += 1
                continue
            ok = self._run_automation_rule(rule, text, force=True)
            if ok:
                self._startup_automation_done.add(key)
            else:
                pending += 1
        if pending > 0 and self._startup_automation_attempt < 15:
            self._schedule_startup_automation(2.0)

    def _global_settings(self) -> dict[str, Any]:
        host = self._host
        state = getattr(host, 'state', None) if host is not None else None
        try:
            if state is not None and hasattr(state, 'settings'):
                settings = state.settings()
                return settings if isinstance(settings, dict) else {}
        except Exception as exc:
            self._log(f'automation settings read failed: {exc}')
        return {}

    def _get_plugin(self, plugin_id: str) -> Any:
        host = self._host
        if host is None:
            return None
        try:
            getter = getattr(host, 'get_plugin', None)
            if callable(getter):
                plugin = getter(plugin_id)
                if plugin is not None:
                    return plugin
        except Exception:
            pass
        try:
            state = getattr(host, 'state', None)
            return getattr(state, 'plugin_instances', {}).get(plugin_id) if state is not None else None
        except Exception:
            return None

    def _automation_text(self, platform: str, value: str, user: str, amount: int) -> str:
        user = str(user or '').strip() or 'Unbekannt'
        amount = int(amount or 0)
        if value.startswith('latest_'):
            return user
        if platform == 'tiktok' and value == 'top_liker':
            return user
        if platform == 'tiktok' and value == 'like_total':
            return user
        if platform == 'tiktok' and value == 'top_gifter':
            return f'{user} · {amount} Gifts'
        if value.endswith('_count') or value.endswith('_total'):
            return str(amount)
        return f'{user} · {amount}' if amount else user

    def _apply_automation_value(self, platform: str, value: str, user: str, amount: int) -> None:
        settings = self._global_settings()
        rules = settings.get('automation_rules')
        if not isinstance(rules, list):
            return
        matching = [r for r in rules if isinstance(r, dict) and str(r.get('platform') or '').lower() == platform and str(r.get('value') or '').lower() == value]
        if not matching:
            return
        text = self._automation_text(platform, value, user, amount)
        for rule in matching:
            self._run_automation_rule(rule, text)

    def _apply_alert_automation(self, item: dict[str, Any]) -> None:
        platform = str(item.get('platform') or '').strip().lower()
        event_type = str(item.get('event_type') or '').strip().lower()
        username = str(item.get('username') or '').strip()
        if not platform or not event_type or event_type == 'chat':
            return
        value = f'latest_{event_type}'
        self._apply_automation_value(platform, value, username, to_int(item.get('amount'), 0, 0))

    def _apply_like_threshold_rules(self, user: str, total_likes: int) -> None:
        settings = self._global_settings()
        rules = settings.get('automation_rules')
        if not isinstance(rules, list):
            return
        username = str(user or '').strip()
        if not username:
            return
        total = int(total_likes or 0)
        text = self._automation_text('tiktok', 'like_total', username, total)
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if str(rule.get('platform') or '').strip().lower() != 'tiktok':
                continue
            if str(rule.get('value') or '').strip().lower() != 'like_total':
                continue
            configured_user = str(rule.get('likeUser') or rule.get('like_user') or '').strip().lstrip('@')
            if not configured_user or configured_user.casefold() != username.casefold():
                continue

            # likeThreshold is an interval, not a one-time absolute limit.
            # Example: threshold=50 triggers at 50, 100, 150, 200... likes.
            threshold = to_int(rule.get('likeThreshold') or rule.get('like_threshold'), 0, 0)
            if threshold <= 0 or total < threshold:
                continue
            reached_bucket = total // threshold
            if reached_bucket <= 0:
                continue

            # Fire every interval stage once per rule in the current plugin run.
            # Example threshold=50: bucket 1=50, bucket 2=100, bucket 3=150.
            for bucket in range(1, reached_bucket + 1):
                reached_at = bucket * threshold
                fire_key = '|'.join([
                    username.casefold(),
                    str(threshold),
                    str(bucket),
                    str(rule.get('target') or '').strip().lower(),
                    str(rule.get('action') or 'text').strip().lower(),
                    str(rule.get('scene') or '').strip().casefold(),
                    str(rule.get('source') or '').strip().casefold(),
                ])
                with self._lock:
                    if fire_key in self._like_threshold_fired:
                        continue
                    self._like_threshold_fired.add(fire_key)
                self._log(f'Like-Zähler ausgelöst: {username} hat {total} Likes erreicht, Intervall {threshold}, Stufe {reached_at}')
                self._run_automation_rule(rule, text)

    def _run_automation_rule(self, rule: dict[str, Any], text: str, *, force: bool = False) -> bool:
        target = str(rule.get('target') or '').strip().lower()
        action = str(rule.get('action') or 'text').strip().lower()
        scene = str(rule.get('scene') or '').strip()
        source = str(rule.get('source') or '').strip()
        if not target:
            return False
        dedupe_key = '|'.join([target, action, scene.casefold(), source.casefold(), text])
        now = time.time()
        with self._lock:
            last = self._automation_recent.get(dedupe_key)
            if not force and last is not None and now - last < 0.35:
                return True
            self._automation_recent[dedupe_key] = now
            if len(self._automation_recent) > 200:
                self._automation_recent = {k: v for k, v in self._automation_recent.items() if now - v < 30}
        try:
            if target == 'meld':
                ok, detail = self._apply_meld_rule(action, scene, source, text)
            elif target == 'obs':
                ok, detail = self._apply_obs_rule(action, scene, source, text)
            else:
                return False
            if not ok:
                self._log(f'automation failed: {target} {action} {scene}/{source}: {detail}')
                return False
            if action == 'show':
                self._schedule_auto_hide(target, scene, source, rule)
            return True
        except Exception as exc:
            self._log(f'automation failed: {target} {action} {scene}/{source}: {exc}')
            return False

    def _hide_automation_source(self, target: str, scene: str, source: str) -> None:
        try:
            if target == 'meld':
                self._apply_meld_rule('hide', scene, source, '')
            elif target == 'obs':
                self._apply_obs_rule('hide', scene, source, '')
        except Exception as exc:
            self._log(f'auto hide failed: {target} {scene}/{source}: {exc}')

    def _schedule_auto_hide(self, target: str, scene: str, source: str, rule: dict[str, Any] | None = None) -> None:
        source = str(source or '').strip()
        if not source:
            return
        try:
            seconds = float(str((rule or {}).get('hideSeconds') or (rule or {}).get('hide_seconds') or 4).replace(',', '.'))
        except Exception:
            seconds = 4.0
        seconds = max(0.0, min(3600.0, seconds))
        if seconds <= 0:
            return
        key = '|'.join([str(target or '').strip().lower(), str(scene or '').strip().casefold(), source.casefold()])
        with self._lock:
            old = self._auto_hide_timers.pop(key, None)
            if old is not None:
                try:
                    old.cancel()
                except Exception:
                    pass
            timer = threading.Timer(seconds, self._hide_automation_source, args=(str(target or '').strip().lower(), str(scene or '').strip(), source))
            timer.daemon = True
            self._auto_hide_timers[key] = timer
            timer.start()

    def _find_meld_layer(self, meld: Any, scene_name: str, source_name: str) -> dict[str, Any] | None:
        if meld is None or not source_name:
            return None
        finder = getattr(meld, '_find_target_layer', None)
        if callable(finder):
            try:
                found = finder(scene_name, source_name)
                if isinstance(found, dict):
                    return found
            except Exception:
                pass
        items = meld.get_session_items() if hasattr(meld, 'get_session_items') else {}
        if not isinstance(items, dict):
            return None
        scene_key = scene_name.casefold()
        source_key = source_name.casefold()
        for key, value in items.items():
            if not isinstance(value, dict):
                continue
            if str(value.get('type') or '').lower() != 'layer':
                continue
            if str(value.get('name') or '').casefold() != source_key:
                continue
            try:
                if scene_key and hasattr(meld, '_item_matches_scene') and not meld._item_matches_scene(value, scene_key, items):
                    continue
            except Exception:
                continue
            row = dict(value)
            row['id'] = key
            return row
        return None

    def _show_meld_parent_chain(self, meld: Any, layer: dict[str, Any]) -> None:
        try:
            items = meld.get_session_items() if hasattr(meld, 'get_session_items') else {}
            parent_id = str(layer.get('parentId') or layer.get('parent_id') or layer.get('parent') or layer.get('groupId') or layer.get('group_id') or '')
            visited: set[str] = set()
            while parent_id and parent_id not in visited:
                visited.add(parent_id)
                parent = items.get(parent_id) if isinstance(items, dict) else None
                if not isinstance(parent, dict) or str(parent.get('type') or '').lower() == 'scene':
                    break
                meld.set_session_property(parent_id, 'visible', True, timeout=3.0)
                parent_id = str(parent.get('parentId') or parent.get('parent_id') or parent.get('parent') or parent.get('groupId') or parent.get('group_id') or '')
        except Exception:
            pass

    def _apply_meld_rule(self, action: str, scene_name: str, source_name: str, text: str) -> tuple[bool, str]:
        meld = self._get_plugin('meld_control')
        if meld is None:
            return False, 'Meld-Control ist nicht verbunden'
        ensure = getattr(meld, 'ensure_connected', None)
        if callable(ensure):
            connected, detail = ensure(timeout=4.0)
        else:
            connected, detail = bool(getattr(meld, 'is_connected', lambda: False)()), 'Meld-Control ist nicht verbunden'
        cached_items = meld.get_session_items() if hasattr(meld, 'get_session_items') else {}
        if not connected and not cached_items:
            return False, str(detail or 'Meld-Control ist nicht verbunden')
        if action == 'scene':
            ok, detail = meld.invoke_meld_method('showScene', [scene_name], timeout=3.0)
            return bool(ok), str(detail or '')
        layer = self._find_meld_layer(meld, scene_name, source_name)
        if layer is None:
            return False, 'Meld-Quelle nicht gefunden'
        layer_id = str(layer.get('id') or '')
        if action == 'text':
            ok, detail = meld.set_session_property(layer_id, 'text', text, timeout=3.0)
            return bool(ok), str(detail or '')
        if action in {'show', 'hide'}:
            visible = action == 'show'
            if visible:
                self._show_meld_parent_chain(meld, layer)
                # Force a visible edge so repeated show-actions are visible again.
                try:
                    meld.set_session_property(layer_id, 'visible', False, timeout=1.0)
                    time.sleep(0.05)
                except Exception:
                    pass
            ok, detail = meld.set_session_property(layer_id, 'visible', visible, timeout=3.0)
            return bool(ok), str(detail or '')
        if action == 'play':
            self._show_meld_parent_chain(meld, layer)
            details: list[str] = []
            try:
                meld.set_session_property(layer_id, 'visible', False, timeout=1.0)
                time.sleep(0.12)
                meld.set_session_property(layer_id, 'visible', True, timeout=1.0)
            except Exception as exc:
                details.append(f'visible edge: {exc}')
            ok_any = False
            last_detail: Any = ''
            # Meld source types are inconsistent. Try all common function names so
            # already visible/finished clips can really start from the beginning.
            for command in ('stop', 'restart', 'replay', 'reset', 'seekToStart', 'play'):
                try:
                    ok, detail = meld.call_layer_function(layer_id, command, timeout=1.5)
                    ok_any = bool(ok) or ok_any
                    last_detail = detail
                    details.append(f'{command}={bool(ok)}:{detail}')
                    time.sleep(0.05)
                except Exception as exc:
                    details.append(f'{command}=False:{exc}')
            if ok_any:
                return True, str(last_detail or 'Meld play/restart sent')
            # Visibility edge still matters for some Meld layers even when callFunction
            # returns no supported command. Do not mark it failed if the layer toggled.
            return True, 'Meld source was re-shown; no supported play function confirmed. ' + ' | '.join(details[-6:])
        return False, f'Unbekannte Aktion: {action}'

    def _apply_obs_rule(self, action: str, scene_name: str, source_name: str, text: str) -> tuple[bool, str]:
        obs = self._get_plugin('obs_control')
        if obs is None or not getattr(obs, 'is_connected', lambda: False)():
            return False, 'OBS-Control ist nicht verbunden'
        if action == 'text':
            ok, detail = obs.request('SetInputSettings', {'inputName': source_name, 'inputSettings': {'text': text}, 'overlay': True}, timeout=3.0)
            return bool(ok), str(detail or '')
        if action in {'show', 'hide'}:
            if action == 'show':
                # Force an off->on edge, otherwise an already visible source cannot visibly trigger again.
                try:
                    obs.set_source_visible(source_name, False)
                    time.sleep(0.05)
                except Exception:
                    pass
            ok, detail = obs.set_source_visible(source_name, action == 'show')
            return bool(ok), str(detail or '')
        if action == 'scene':
            ok, detail = obs.request('SetCurrentProgramScene', {'sceneName': scene_name}, timeout=3.0)
            return bool(ok), str(detail or '')
        if action == 'play':
            # OBS media sources, browser sources and scene items need different restart edges.
            # Do all safe nudges: hide -> stop/cursor/restart/play -> browser refresh -> show.
            details: list[str] = []
            ok_any = False
            try:
                hide_ok, hide_detail = obs.set_source_visible(source_name, False)
                ok_any = bool(hide_ok) or ok_any
                details.append(f'hide={bool(hide_ok)}:{hide_detail}')
                time.sleep(0.12)
            except Exception as exc:
                details.append(f'hide=False:{exc}')
            try:
                cursor_ok, cursor_detail = obs.request('SetMediaInputCursor', {'inputName': source_name, 'mediaCursor': 0}, timeout=1.0)
                ok_any = bool(cursor_ok) or ok_any
                details.append(f'cursor={bool(cursor_ok)}:{cursor_detail}')
            except Exception as exc:
                details.append(f'cursor=False:{exc}')
            for media_action in (
                'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP',
                'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART',
                'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY',
            ):
                try:
                    step_ok, step_detail = obs.request('TriggerMediaInputAction', {'inputName': source_name, 'mediaAction': media_action}, timeout=1.5)
                    ok_any = bool(step_ok) or ok_any
                    details.append(f'{media_action}={bool(step_ok)}:{step_detail}')
                    time.sleep(0.08)
                except Exception as exc:
                    details.append(f'{media_action}=False:{exc}')
            # Browser sources do not support media actions. Refresh is their restart.
            for prop in ('refreshnocache', 'refresh'):
                try:
                    step_ok, step_detail = obs.request('PressInputPropertiesButton', {'inputName': source_name, 'propertyName': prop}, timeout=1.5)
                    ok_any = bool(step_ok) or ok_any
                    details.append(f'{prop}={bool(step_ok)}:{step_detail}')
                except Exception as exc:
                    details.append(f'{prop}=False:{exc}')
            try:
                show_ok, show_detail = obs.set_source_visible(source_name, True)
                ok_any = bool(show_ok) or ok_any
                details.append(f'show={bool(show_ok)}:{show_detail}')
            except Exception as exc:
                details.append(f'show=False:{exc}')
            return bool(ok_any), ' | '.join(str(x) for x in details[-8:])
        return False, f'Unbekannte Aktion: {action}'

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

    def _is_duplicate(self, alert: dict[str, Any], settings: dict[str, Any]) -> bool:
        ttl = to_int(settings.get('dedupe_seconds'), 8, 0, 120)
        if ttl <= 0:
            return False

        platform = str(alert.get('platform') or '').strip().lower()
        event_type = str(alert.get('event_type') or '').strip().lower()
        username = str(alert.get('username') or '').strip().casefold()
        message_id = str(alert.get('message_id') or '').strip().casefold()
        text = str(alert.get('text') or '').strip().casefold()[:180]
        amount = str(alert.get('amount') or '').strip()
        raw = alert.get('raw') if isinstance(alert.get('raw'), dict) else {}

        raw_event_id = str(
            raw.get('event_id')
            or raw.get('id')
            or raw.get('msg_id')
            or raw.get('message_id')
            or raw.get('gift_id')
            or raw.get('giftId')
            or ''
        ).strip().casefold()

        keys: list[str] = []

        # Harte ID-Dedupe, wenn Plattform/Integration eine ID liefert.
        if message_id:
            keys.append('|'.join(['id', platform, event_type, username, message_id]))
        if raw_event_id and raw_event_id != message_id:
            keys.append('|'.join(['rawid', platform, event_type, username, raw_event_id]))

        # Weiche Dedupe für TikTok/Realtime-Events, die teilweise doppelt mit verschiedenen IDs kommen.
        # Amount/Text bleiben drin, damit z.B. echte Like-/Gift-Stufen nicht pauschal verschluckt werden.
        keys.append('|'.join(['soft', platform, event_type, username, amount, text]))

        now = time.time()
        soft_ttl = min(float(ttl), 2.5) if event_type in {'like', 'gift', 'share'} else float(ttl)

        with self._lock:
            for old_key, ts in list(self._recent.items()):
                if now - ts > max(10, ttl * 3):
                    self._recent.pop(old_key, None)

            for key in keys:
                last = self._recent.get(key)
                if last is None:
                    continue
                limit = soft_ttl if key.startswith('soft|') else float(ttl)
                if now - last <= limit:
                    self._log(f'duplicate alert blocked: {platform}:{event_type}:{username}')
                    return True

            for key in keys:
                self._recent[key] = now
        return False

    def _push_alert(self, alert: dict[str, Any]) -> None:
        cfg = self._current_settings()
        item = dict(alert)
        item['id'] = now_ms()
        item['platform_label'] = PLATFORM_LABELS.get(str(item.get('platform')), str(item.get('platform') or 'al3rtalot'))
        self._write_exports(item)
        self._apply_alert_automation(item)
        self._save_runtime_state({'latest_alert': item})
        self._emit_desktop_alert(item, cfg)
        self._log(f"alert | {item.get('platform')}:{item.get('event_type')}:{item.get('username')} -> {item.get('text')}")

    def _emit_desktop_alert(self, item: dict[str, Any], settings: dict[str, Any]) -> None:
        if self._host is None or not as_bool(settings.get('alert_to_chat_overlay'), True):
            return
        platform = str(item.get('platform') or 'al3rtalot')
        text = str(item.get('text') or '')
        try:
            self._host.emit_message(self.plugin_id, {
                'platform': platform,
                'username': str(item.get('username') or 'al3rtalot'),
                'text': text,
                'message_type': 'alert',
                'type': 'alert',
                'event_type': str(item.get('event_type') or 'alert'),
                'title': str(item.get('title') or 'Alert'),
                'amount': item.get('amount'),
                'gift_name': str(item.get('gift_name') or ''),
                'color': str(item.get('color') or ''),
                'raw': item.get('raw') if isinstance(item.get('raw'), dict) else {},
                'gift_image_url': str(item.get('gift_image_url') or ''),
                'overlay_html': str(item.get('overlay_html') or ''),
                'source_plugin_id': self.plugin_id,
                'dispatch_to_plugins': False,
            })
        except Exception as exc:
            self._log(f'emit alert failed: {exc}')

    def _save_runtime_state(self, extra: dict[str, Any] | None = None) -> None:
        data = {
            'plugin': PLUGIN_ID,
            'version': PLUGIN_VERSION,
            'exports_path': str(DATA_DIR / 'exports'),
            'updated_at': time.time(),
        }
        if isinstance(extra, dict):
            data.update(extra)
        try:
            atomic_write_json(DATA_DIR / 'runtime_state.json', data)
        except Exception as exc:
            self._log(f'runtime_state write failed: {exc}')

    def _write_exports(self, item: dict[str, Any]) -> None:
        """Stable JSON/TXT files for OBS, Meld, or any external automation."""
        export_dir = DATA_DIR / 'exports'
        platform = str(item.get('platform') or 'unknown').lower()
        event_type = str(item.get('event_type') or 'alert').lower()
        self._export_state['latest_alert'] = dict(item)
        self._export_state.setdefault('platforms', {})[platform] = dict(item)
        self._export_state.setdefault('events', {})[event_type] = dict(item)
        try:
            atomic_write_json(export_dir / 'state.json', self._export_state)
            atomic_write_json(export_dir / 'latest_alert.json', item)
            atomic_write_json(export_dir / f'{platform}_{event_type}.json', item)
            line = f"{item.get('username') or 'Unbekannt'} · {item.get('text') or item.get('title') or 'Alert'}"
            for filename in ('latest_alert.txt', f'{platform}_latest_alert.txt', f'{event_type}.txt', f'{platform}_{event_type}.txt'):
                path = export_dir / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(path.suffix + '.tmp')
                temp.write_text(line, encoding='utf-8')
                temp.replace(path)
        except Exception as exc:
            self._log(f'alert export failed: {exc}')


def create_plugin():
    return Al3rtalotPlugin()
