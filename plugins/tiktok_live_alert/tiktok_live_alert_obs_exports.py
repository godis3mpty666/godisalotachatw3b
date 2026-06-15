from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any


def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'plugins':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'


def _safe_name(value: str) -> str:
    text = str(value or '').strip().lower()
    text = re.sub(r'[^a-z0-9._-]+', '_', text)
    return text.strip('_') or 'value'


class ObsTextExportWriter:
    DEFAULT_FILES = (
        'state.json',
        'latest_follower.txt',
        'new_follower.txt',
        'latest_like.txt',
        'latest_gift.txt',
        'top_liker.txt',
        'top_liker_leader.txt',
        'top_liker_list.txt',
        'top_gifter.txt',
        'top_gifter_leader.txt',
        'top_gifter_list.txt',
        'follower_goal.txt',
        'follower_goal_percent.txt',
        'follower_goal_current.txt',
        'follower_goal_target.txt',
        'like_goal.txt',
        'like_goal_percent.txt',
        'like_goal_current.txt',
        'like_goal_target.txt',
        'gift_goal.txt',
        'gift_goal_percent.txt',
        'gift_goal_current.txt',
        'gift_goal_target.txt',
        'ticker.txt',
        'ticker_2.txt',
        'ticker_3.txt',
        'summary.txt',
    )

    DEFAULT_PLACEHOLDERS = {
        'latest_follower.txt': 'your name here',
        'new_follower.txt': 'your name here',
        'latest_like.txt': 'your name here',
        'latest_gift.txt': 'your name here',
        'top_liker.txt': 'sadly not you',
        'top_liker_leader.txt': 'sadly not you',
        'top_liker_list.txt': 'sadly not you',
        'top_gifter.txt': 'sadly not you',
        'top_gifter_leader.txt': 'sadly not you',
        'top_gifter_list.txt': 'sadly not you',
        'follower_goal.txt': '0 / 0',
        'follower_goal_percent.txt': '0',
        'follower_goal_current.txt': '0',
        'follower_goal_target.txt': '0',
        'like_goal.txt': '0 / 0',
        'like_goal_percent.txt': '0',
        'like_goal_current.txt': '0',
        'like_goal_target.txt': '0',
        'gift_goal.txt': '0 / 0',
        'gift_goal_percent.txt': '0',
        'gift_goal_current.txt': '0',
        'gift_goal_target.txt': '0',
        'ticker.txt': 'ticker ready',
        'ticker_2.txt': 'ticker 2 ready',
        'ticker_3.txt': 'ticker 3 ready',
        'summary.txt': 'TikTok alert outputs ready',
    }

    def __init__(self, plugin_dir: str | os.PathLike[str]) -> None:
        self.plugin_dir = Path(plugin_dir)
        self.export_dir = _main_data_dir('tiktok_live_alert') / 'obs_exports'
        self._lock = threading.Lock()
        self.ensure_placeholders()

    def ensure_dir(self) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        return self.export_dir

    def ensure_placeholders(self) -> Path:
        with self._lock:
            export_dir = self.ensure_dir()
            for name in self.DEFAULT_FILES:
                path = export_dir / name
                if not path.exists():
                    path.write_text(self.DEFAULT_PLACEHOLDERS.get(name, ''), encoding='utf-8')
            return export_dir

    def write_exports(self, state: dict[str, Any], settings: dict[str, Any]) -> None:
        with self._lock:
            export_dir = self.ensure_dir()
            payloads = self._build_payloads(state, settings)
            for name in self.DEFAULT_FILES:
                self._write_text_atomic(export_dir / name, payloads.get(name, ''))
            for name, content in payloads.items():
                if name not in self.DEFAULT_FILES:
                    self._write_text_atomic(export_dir / name, content)

    def _write_text_atomic(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + '.tmp')
        tmp_path.write_text(content, encoding='utf-8')
        os.replace(tmp_path, path)

    def _read_existing_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8').strip()
        except Exception:
            return ''

    def default_text(self, filename: str) -> str:
        return str(self.DEFAULT_PLACEHOLDERS.get(filename, ''))

    def _is_placeholderish(self, value: str) -> bool:
        return str(value or '').strip().lower() in {'', '---', 'latest follower', 'latest like', 'latest gift'}

    def _preserve_existing_text(self, filename: str, candidate: str, default: str | None = None) -> str:
        fallback = self.default_text(filename) if default is None else str(default)
        value = str(candidate or '').strip()
        if not self._is_placeholderish(value):
            return value
        existing = self._read_existing_text(self.ensure_dir() / filename)
        if existing and not self._is_placeholderish(existing):
            return existing
        return fallback

    def read_export_text(self, filename: str, default: str = '') -> str:
        value = self._read_existing_text(self.ensure_dir() / filename)
        return value or str(default or '')

    def _ctx(self, state: dict[str, Any]) -> dict[str, Any]:
        latest = dict(state.get('latest') or {})
        rankings = dict(state.get('rankings') or {})
        goals = dict(state.get('goals') or {})
        followers = dict(goals.get('followers') or {})
        likes = dict(goals.get('likes') or {})
        gifts = dict(goals.get('gifts') or {})
        likers = list(rankings.get('likers') or [])
        gifters = list(rankings.get('gifters') or [])
        top_liker = likers[0] if likers else {}
        top_gifter = gifters[0] if gifters else {}
        return {
            'channel': str(state.get('channel') or ''),
            'latest_follower': str(latest.get('follower') or self.default_text('latest_follower.txt')),
            'latest_like_user': str(latest.get('like_user') or self.default_text('latest_like.txt')),
            'latest_like_count': int(latest.get('like_count') or 0),
            'latest_gift_user': str(latest.get('gift_user') or self.default_text('latest_gift.txt')),
            'latest_gift_name': str(latest.get('gift_name') or 'gift'),
            'latest_gift_count': int(latest.get('gift_count') or 0),
            'like_milestone': str(latest.get('like_milestone') or ''),
            'like_milestone_total': int(latest.get('like_milestone_total') or 0),
            'gift_milestone': str(latest.get('gift_milestone') or ''),
            'gift_milestone_total': int(latest.get('gift_milestone_total') or 0),
            'top_liker': str(top_liker.get('name') or self.default_text('top_liker_leader.txt')),
            'top_liker_count': int(top_liker.get('count') or 0),
            'top_gifter': str(top_gifter.get('name') or self.default_text('top_gifter_leader.txt')),
            'top_gifter_count': int(top_gifter.get('count') or 0),
            'follower_goal_current': int(followers.get('current') or 0),
            'follower_goal_target': int(followers.get('target') or 0),
            'like_goal_current': int(likes.get('current') or 0),
            'like_goal_target': int(likes.get('target') or 0),
            'gift_goal_current': int(gifts.get('current') or 0),
            'gift_goal_target': int(gifts.get('target') or 0),
            'likers': likers,
            'gifters': gifters,
        }

    def _safe_format(self, template: str, ctx: dict[str, Any], fallback: str = '') -> str:
        try:
            return str(template or '').format(**ctx)
        except Exception:
            return fallback

    def _goal_percent(self, current: int, target: int) -> int:
        if target <= 0:
            return 0
        return max(0, min(100, int(round((current / float(target)) * 100.0))))

    def _ranking_lines(self, items: list[dict[str, Any]], default: str = 'sadly not you') -> str:
        if not items:
            return default
        lines = []
        for idx, item in enumerate(items, start=1):
            lines.append(f"{idx}. {item.get('name', '---')}")
        return '\n'.join(lines)

    def _build_payloads(self, state: dict[str, Any], settings: dict[str, Any]) -> dict[str, str]:
        ctx = self._ctx(state)
        payloads: dict[str, str] = {}

        payloads['state.json'] = json.dumps(state, ensure_ascii=False, indent=2)
        payloads['latest_follower.txt'] = self._preserve_existing_text('latest_follower.txt', ctx['latest_follower'])
        payloads['new_follower.txt'] = self._preserve_existing_text('new_follower.txt', ctx['latest_follower'], self.default_text('new_follower.txt'))
        payloads['latest_like.txt'] = self._preserve_existing_text('latest_like.txt', ctx['latest_like_user'])
        gift_user = self._preserve_existing_text('latest_gift.txt', ctx['latest_gift_user'])
        if gift_user == self.default_text('latest_gift.txt'):
            payloads['latest_gift.txt'] = gift_user
        else:
            payloads['latest_gift.txt'] = f"{gift_user} - {ctx['latest_gift_name']} x{ctx['latest_gift_count']}"

        top_liker_leader = ctx['top_liker'] or self.default_text('top_liker_leader.txt')
        top_gifter_leader = ctx['top_gifter'] or self.default_text('top_gifter_leader.txt')
        payloads['top_liker.txt'] = top_liker_leader
        payloads['top_liker_leader.txt'] = top_liker_leader
        payloads['top_liker_list.txt'] = self._ranking_lines(ctx['likers'], self.default_text('top_liker_list.txt'))
        payloads['top_gifter.txt'] = top_gifter_leader
        payloads['top_gifter_leader.txt'] = top_gifter_leader
        payloads['top_gifter_list.txt'] = self._ranking_lines(ctx['gifters'], self.default_text('top_gifter_list.txt'))

        for goal_key, current_key, target_key in (
            ('follower_goal', 'follower_goal_current', 'follower_goal_target'),
            ('like_goal', 'like_goal_current', 'like_goal_target'),
            ('gift_goal', 'gift_goal_current', 'gift_goal_target'),
        ):
            current = int(ctx[current_key])
            target = int(ctx[target_key])
            payloads[f'{goal_key}.txt'] = f"{current} / {target}"
            payloads[f'{goal_key}_percent.txt'] = str(self._goal_percent(current, target))
            payloads[f'{goal_key}_current.txt'] = str(current)
            payloads[f'{goal_key}_target.txt'] = str(target)

        payloads['ticker.txt'] = self._safe_format(
            str(settings.get('ticker_text') or state.get('ticker', {}).get('text') or self.default_text('ticker.txt')),
            ctx,
            fallback=str(state.get('ticker', {}).get('text') or self.default_text('ticker.txt')),
        )
        payloads['ticker_2.txt'] = self._safe_format(str(settings.get('ticker_2_text') or state.get('ticker', {}).get('text_2') or self.default_text('ticker_2.txt')), ctx, fallback=self.default_text('ticker_2.txt'))
        payloads['ticker_3.txt'] = self._safe_format(str(settings.get('ticker_3_text') or state.get('ticker', {}).get('text_3') or self.default_text('ticker_3.txt')), ctx, fallback=self.default_text('ticker_3.txt'))

        summary_lines = [
            f"Latest follower: {ctx['latest_follower']}",
            f"Latest like: {ctx['latest_like_user']} ({ctx['latest_like_count']})",
            f"Latest gift: {ctx['latest_gift_user']} - {ctx['latest_gift_name']} x{ctx['latest_gift_count']}",
            f"Top liker: {ctx['top_liker']} ({ctx['top_liker_count']})",
            f"Top gifter: {ctx['top_gifter']} ({ctx['top_gifter_count']})",
            f"Follower goal: {ctx['follower_goal_current']} / {ctx['follower_goal_target']}",
            f"Like goal: {ctx['like_goal_current']} / {ctx['like_goal_target']}",
            f"Gift goal: {ctx['gift_goal_current']} / {ctx['gift_goal_target']}",
        ]
        payloads['summary.txt'] = '\n'.join(summary_lines)

        payloads['like_milestone_trigger'] = str(ctx.get('like_milestone') or ctx.get('like_goal_current') or '')
        payloads['live_action_follow'] = str(ctx.get('latest_follower') or '')
        payloads['live_action_like'] = f"{ctx.get('latest_like_user', '')} +{ctx.get('latest_like_count', 0)}"
        payloads['live_action_like_milestone'] = str(ctx.get('like_milestone') or ctx.get('like_milestone_total') or ctx.get('like_goal_current') or '')
        payloads['live_action_gift'] = f"{ctx.get('latest_gift_user', '')} - {ctx.get('latest_gift_name', 'gift')} x{ctx.get('latest_gift_count', 0)}"
        payloads['live_action_gift_milestone'] = str(ctx.get('gift_milestone') or ctx.get('gift_milestone_total') or ctx.get('gift_goal_current') or '')
        payloads['live_action_share'] = str(ctx.get('channel') or '')
        payloads['live_action_join'] = str(ctx.get('channel') or '')

        for name, value in list(payloads.items()):
            if not isinstance(value, str):
                payloads[name] = str(value)

        return payloads