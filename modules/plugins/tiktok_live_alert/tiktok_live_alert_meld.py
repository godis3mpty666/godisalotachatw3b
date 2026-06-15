from __future__ import annotations

import base64
import contextlib
import threading
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
from typing import Any

SOURCE_OPTIONS: list[tuple[str, str]] = [
    ('latest_follower.txt', 'Latest Follower'),
    ('new_follower.txt', 'New Follower'),
    ('latest_like.txt', 'Latest Like'),
    ('latest_gift.txt', 'Latest Gift'),
    ('top_liker.txt', 'Top Liker'),
    ('top_liker_leader.txt', 'Top Liker Leader'),
    ('top_liker_list.txt', 'Top Liker List'),
    ('top_gifter.txt', 'Top Gifter'),
    ('top_gifter_leader.txt', 'Top Gifter Leader'),
    ('top_gifter_list.txt', 'Top Gifter List'),
    ('follower_goal.txt', 'Follower Goal'),
    ('follower_goal_percent.txt', 'Follower Goal Percent'),
    ('follower_goal_current.txt', 'Follower Goal Current'),
    ('follower_goal_target.txt', 'Follower Goal Target'),
    ('like_goal.txt', 'Like Goal'),
    ('like_goal_percent.txt', 'Like Goal Percent'),
    ('like_goal_current.txt', 'Like Goal Current'),
    ('like_goal_target.txt', 'Like Goal Target'),
    ('gift_goal.txt', 'Gift Goal'),
    ('gift_goal_percent.txt', 'Gift Goal Percent'),
    ('gift_goal_current.txt', 'Gift Goal Current'),
    ('gift_goal_target.txt', 'Gift Goal Target'),
    ('ticker.txt', 'Ticker 1'),
    ('ticker_2.txt', 'Ticker 2'),
    ('ticker_3.txt', 'Ticker 3'),
    ('summary.txt', 'Summary'),
    ('like_milestone_trigger', 'Like Milestone Trigger'),
    ('live_action_follow', 'Action: Follow'),
    ('live_action_subscribe', 'Action: Subscribe / Member'),
    ('live_action_like', 'Action: Any Like'),
    ('live_action_like_milestone', 'Action: Like Milestone'),
    ('live_action_personal_like_milestone', 'Action: Personal Like Milestone'),
    ('live_action_personal_gift_milestone', 'Action: Personal Gift Milestone'),
    ('live_action_gift', 'Action: Any Gift'),
    ('live_action_gift_milestone', 'Action: Gift Milestone'),
    ('live_action_share', 'Action: Share'),
    ('live_action_join', 'Action: Join'),
]

LIVE_ACTION_SOURCE_OPTIONS: list[tuple[str, str]] = [
    ('live_action_follow', 'Follow'),
    ('live_action_subscribe', 'Subscribe / Member'),
    ('live_action_like', 'Any Like'),
    ('live_action_like_milestone', 'Like Milestone'),
    ('live_action_personal_like_milestone', 'Personal Like Milestone'),
    ('live_action_personal_gift_milestone', 'Personal Gift Milestone'),
    ('live_action_gift', 'Any Gift'),
    ('live_action_gift_milestone', 'Gift Milestone'),
    ('live_action_share', 'Share'),
    ('live_action_join', 'Join'),
]

LIVE_ACTION_SOURCE_KEYS = {key for key, _label in LIVE_ACTION_SOURCE_OPTIONS}
LIVE_ACTION_MILESTONE_KEYS = {'live_action_like_milestone', 'live_action_personal_like_milestone', 'live_action_gift_milestone', 'live_action_personal_gift_milestone'}
LEGACY_ACTION_SOURCE_KEYS = {'like_milestone_trigger', 'like_milestone_trigger.txt'}


PROPERTY_OPTIONS = ['text', 'content', 'value', 'label', 'show_hide_once', 'play_once', 'call:restart', 'call:play', 'visible:true', 'visible:false']


def _extract_webchannel_property_values(raw: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not isinstance(raw, list):
        return values
    for item in raw:
        if not isinstance(item, list):
            continue
        name = ''
        value = None
        if len(item) >= 4 and isinstance(item[0], int) and isinstance(item[1], str):
            name = item[1]
            value = item[3]
        elif len(item) >= 4 and isinstance(item[0], str):
            name = item[0]
            value = item[3]
        if name:
            values[str(name)] = value
    return values


def _clean_meld_type(value: Any) -> str:
    text = str(value or '').strip().casefold()
    if not text:
        return ''
    for sep in ('::', '.', '/', '\\'):
        if sep in text:
            text = text.rsplit(sep, 1)[-1]
    text = text.replace('_', '').replace('-', '').replace(' ', '')
    if text in {'scene', 'scenes', 'meldscene'} or text.endswith('scene'):
        return 'scene'
    if text in {'layer', 'layers', 'sourcelayer', 'medialayer', 'textlayer', 'imagelayer', 'browserlayer', 'videolayer', 'audiolayer'} or text.endswith('layer'):
        return 'layer'
    return ''


def _meld_parent_id(data: dict[str, Any]) -> str:
    for key in ('parent', 'parentId', 'parent_id', 'parentUuid', 'parent_uuid', 'scene', 'sceneId', 'scene_id', 'sceneUuid', 'scene_uuid', 'sceneID'):
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get('id') or value.get('uuid') or value.get('uid') or value.get('key')
        if value not in (None, ''):
            return str(value)
    return ''


def _meld_item_name(data: dict[str, Any]) -> str:
    for key in ('name', 'displayName', 'display_name', 'title', 'label', 'objectName'):
        value = data.get(key)
        if value not in (None, ''):
            return str(value)
    return ''


def _meld_item_type(data: dict[str, Any]) -> str:
    for key in ('type', 'itemType', 'item_type', 'kind', 'objectType', 'object_type', 'class', 'className', 'class_name', 'typeName', 'type_name', '__type'):
        item_type = _clean_meld_type(data.get(key))
        if item_type:
            return item_type
    if _meld_parent_id(data):
        return 'layer'
    for key in ('layers', 'children', 'items'):
        if isinstance(data.get(key), (list, tuple, dict)):
            return 'scene'
    if any(k in data for k in ('current', 'active', 'selected')) and _meld_item_name(data):
        return 'scene'
    return ''


def _normalize_meld_session_items(items: Any) -> dict[str, dict[str, Any]]:
    """Return a flat Meld session map.

    Meld can expose objects either as a flat session.items dict or nested under
    scene/folder ``children`` / ``layers`` lists. Top-level layers sometimes do
    not carry an explicit parent/type, while folders and media layers both report
    as ``layer``. This normalizer keeps the real object ids and adds missing
    parent/type hints instead of inventing fake folder paths.
    """
    normalized: dict[str, dict[str, Any]] = {}

    def add_item(raw_id: Any, raw_data: Any, parent_id: str = '') -> str:
        if not isinstance(raw_data, dict):
            return ''

        row = dict(raw_data)
        row_id = str(row.get('id') or row.get('uuid') or row.get('uid') or row.get('key') or raw_id or '').strip()
        if not row_id:
            row_id = hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:16]

        existing_parent = _meld_parent_id(row)
        if not existing_parent and parent_id:
            row['parent'] = str(parent_id)
            existing_parent = str(parent_id)

        row_type = _meld_item_type(row)
        has_children = any(isinstance(row.get(k), (list, tuple, dict)) for k in ('layers', 'children', 'items'))
        if not row_type:
            if existing_parent:
                row_type = 'layer'
            elif has_children:
                row_type = 'scene'
            elif _meld_item_name(row):
                # Flat Meld snapshots can contain standalone top-level media
                # layers without parent/type. They still need to appear in the
                # plugin layer dropdown.
                row_type = 'layer'

        if row_type:
            row['type'] = row_type
        row_name = _meld_item_name(row)
        if row_name and not row.get('name'):
            row['name'] = row_name
        if existing_parent:
            row['parent'] = existing_parent

        normalized[row_id] = row

        # Flatten nested structures while preserving the current row as parent.
        for child_key in ('layers', 'children', 'items'):
            children = raw_data.get(child_key)
            if isinstance(children, dict):
                for child_id, child_data in children.items():
                    add_item(child_id, child_data, row_id)
            elif isinstance(children, (list, tuple)):
                for index, child_data in enumerate(children):
                    child_id = ''
                    if isinstance(child_data, dict):
                        child_id = str(child_data.get('id') or child_data.get('uuid') or child_data.get('uid') or child_data.get('key') or f'{row_id}:{child_key}:{index}')
                    add_item(child_id, child_data, row_id)
        return row_id

    if isinstance(items, dict):
        for item_id, item_data in items.items():
            add_item(item_id, item_data, '')
    elif isinstance(items, list):
        for index, item_data in enumerate(items):
            add_item(index, item_data, '')
    return normalized

class MeldConnectionError(RuntimeError):
    pass


class _SimpleMeldWebSocket:
    def __init__(self, host: str, port: int, timeout: float = 4.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        request = (
            f'GET / HTTP/1.1\r\n'
            f'Host: {self.host}:{self.port}\r\n'
            f'Upgrade: websocket\r\n'
            f'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            f'Sec-WebSocket-Version: 13\r\n\r\n'
        ).encode('ascii')
        sock.sendall(request)
        response = self._recv_http_response(sock)
        if b'101' not in response.split(b'\r\n', 1)[0]:
            raise MeldConnectionError('Meld websocket handshake failed')
        accept = self._extract_header(response, b'Sec-WebSocket-Accept')
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest())
        if accept != expected:
            raise MeldConnectionError('Meld websocket handshake validation failed')
        self.sock = sock

    def _recv_http_response(self, sock: socket.socket) -> bytes:
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def _extract_header(self, response: bytes, name: bytes) -> bytes:
        for line in response.split(b'\r\n'):
            if line.lower().startswith(name.lower() + b':'):
                return line.split(b':', 1)[1].strip()
        return b''

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode('utf-8'))

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            raise MeldConnectionError('Meld websocket is not connected')
        first = 0x80 | (opcode & 0x0F)
        mask_bit = 0x80
        length = len(payload)
        if length < 126:
            header = bytes([first, mask_bit | length])
        elif length < 65536:
            header = bytes([first, mask_bit | 126]) + struct.pack('!H', length)
        else:
            header = bytes([first, mask_bit | 127]) + struct.pack('!Q', length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def recv_text(self) -> str:
        if self.sock is None:
            raise MeldConnectionError('Meld websocket is not connected')
        while True:
            opcode, payload = self._read_frame()
            if opcode == 0x1:
                return payload.decode('utf-8', 'replace')
            if opcode == 0x8:
                raise MeldConnectionError('Meld websocket closed the connection')
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode == 0xA:
                continue

    def _read_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise MeldConnectionError('Meld websocket is not connected')
        data = b''
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise MeldConnectionError('Meld websocket connection lost')
            data += chunk
        return data

    def _read_frame(self) -> tuple[int, bytes]:
        header = self._read_exact(2)
        b1, b2 = header[0], header[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack('!H', self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b''
        payload = self._read_exact(length) if length else b''
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def _send_pong(self, payload: bytes = b'') -> None:
        self._send_frame(0xA, payload)

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self.sock.close()
        finally:
            self.sock = None


class MeldWebChannelClient:
    def __init__(self, host: str = '127.0.0.1', port: int = 13376, timeout: float = 4.0) -> None:
        self.host = str(host or '127.0.0.1').strip()
        self.port = int(port or 13376)
        self.timeout = float(timeout or 4.0)
        self.ws = _SimpleMeldWebSocket(self.host, self.port, self.timeout)
        self._method_map: dict[str, int] = {}
        self._session_items: dict[str, dict[str, Any]] = {}
        self._next_request_id = 100

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def connect(self) -> None:
        self.ws.connect()
        self.ws.send_text(json.dumps({'type': 3, 'id': 1}))
        while True:
            data = json.loads(self.ws.recv_text())
            if not isinstance(data, dict):
                continue
            msg_type = data.get('type')
            if msg_type not in (3, 10):
                continue
            if msg_type == 10 and data.get('id') != 1:
                continue
            payload = data.get('data')
            if not isinstance(payload, dict) or 'meld' not in payload:
                continue
            meld_obj = payload.get('meld') or {}
            self._method_map = self._build_method_map(meld_obj.get('methods'))
            extracted_values = _extract_webchannel_property_values(meld_obj.get('properties'))
            session = meld_obj.get('session') or extracted_values.get('session') or {}
            items = session.get('items') if isinstance(session, dict) else None
            self._session_items = _normalize_meld_session_items(items)
            return

    def close(self) -> None:
        self.ws.close()

    def get_session_items(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self._session_items.items()}

    def list_scenes(self) -> list[dict[str, Any]]:
        scenes: list[dict[str, Any]] = []
        for item_id, data in self._session_items.items():
            if _meld_item_type(data) == 'scene':
                row = dict(data)
                row['type'] = 'scene'
                row['id'] = item_id
                scenes.append(row)
        scenes.sort(key=lambda x: (int(not bool(x.get('current'))), int(x.get('index') or 0), str(x.get('name') or '').lower()))
        return scenes

    def list_layers(self, scene_id: str | None = None) -> list[dict[str, Any]]:
        layers: list[dict[str, Any]] = []
        for item_id, data in self._session_items.items():
            if _meld_item_type(data) != 'layer':
                continue
            parent_id = _meld_parent_id(data)
            if scene_id and parent_id != str(scene_id):
                continue
            row = dict(data)
            row['type'] = 'layer'
            if parent_id:
                row['parent'] = parent_id
            row['id'] = item_id
            layers.append(row)
        layers.sort(key=lambda x: (int(x.get('index') or 0), str(x.get('name') or '').lower()))
        return layers

    def invoke(self, method_name: str, args: list[Any] | None = None) -> Any:
        method_id = self._resolve_method_id(method_name)
        if method_id is None:
            raise MeldConnectionError(f'Unknown Meld method: {method_name}')
        request_id = self._next_request_id
        self._next_request_id += 1
        payload = {'type': 6, 'object': 'meld', 'method': method_id, 'args': list(args or []), 'id': request_id}
        self.ws.send_text(json.dumps(payload))
        while True:
            data = json.loads(self.ws.recv_text())
            if not isinstance(data, dict):
                continue
            if data.get('type') == 10 and data.get('id') == request_id:
                return data.get('data')
            if data.get('type') == 2:
                self._process_property_update(data)

    def set_property(self, object_id: str, property_name: str, value: Any) -> Any:
        return self.invoke('setProperty', [str(object_id), str(property_name), value])

    def _process_property_update(self, data: dict[str, Any]) -> None:
        payload = data.get('data')
        if not isinstance(payload, list):
            return
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if entry.get('object') != 'meld':
                continue
            props = entry.get('properties') or {}
            if not isinstance(props, dict):
                continue
            session = props.get('session')
            if isinstance(session, dict):
                items = session.get('items')
                if isinstance(items, (dict, list)):
                    self._session_items = _normalize_meld_session_items(items)

    def _build_method_map(self, raw: Any) -> dict[str, int]:
        result: dict[str, int] = {}
        if not isinstance(raw, list):
            return result
        for item in raw:
            if not isinstance(item, list) or len(item) < 2 or not isinstance(item[1], int):
                continue
            name = str(item[0] or '').strip()
            if not name:
                continue
            result.setdefault(name, item[1])
            result.setdefault(name.split('(', 1)[0].strip(), item[1])
        return result

    def _resolve_method_id(self, name: str) -> int | None:
        if name in self._method_map:
            return self._method_map[name]
        base = str(name or '').split('(', 1)[0].strip()
        return self._method_map.get(base)


class _DirectMeldAdapter:
    def __init__(self, host: str, port: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = int(port or 13376)
        self.timeout = float(timeout or 5.0)

    def is_connected(self) -> bool:
        return True

    def get_session_items(self) -> dict[str, dict[str, Any]]:
        with MeldWebChannelClient(host=self.host, port=self.port, timeout=self.timeout) as client:
            return client.get_session_items()

    def set_session_property(self, layer_id: str, property_name: str, value: Any, timeout: float | None = None) -> tuple[bool, str]:
        try:
            with MeldWebChannelClient(host=self.host, port=self.port, timeout=float(timeout or self.timeout)) as client:
                client.set_property(layer_id, property_name, value)
            return True, 'direct Meld connection'
        except Exception as exc:
            return False, str(exc)

    def invoke_meld_method(self, method_name: str, args: list[Any] | None = None, timeout: float | None = None) -> tuple[bool, str]:
        try:
            with MeldWebChannelClient(host=self.host, port=self.port, timeout=float(timeout or self.timeout)) as client:
                client.invoke(method_name, list(args or []))
            return True, 'direct Meld connection'
        except Exception as exc:
            return False, str(exc)


class MeldOutputManager:
    def __init__(self, logger=None, owner_plugin=None) -> None:
        self.logger = logger
        self.owner_plugin = owner_plugin
        self._restore_tokens: dict[str, int] = {}
        self._restore_lock = threading.RLock()


    def _get_runtime_host(self):
        plugin = self.owner_plugin
        if plugin is None:
            return None
        host = getattr(plugin, '_runtime_host', None)
        if host is not None:
            return host
        return getattr(plugin, '_host', None)

    def _unwrap_plugin_instance(self, candidate):
        if candidate is None:
            return None
        if getattr(candidate, 'plugin_id', '') == 'meld_control':
            return candidate
        nested = getattr(candidate, 'plugin', None)
        if nested is not None and getattr(nested, 'plugin_id', '') == 'meld_control':
            return nested
        nested = getattr(candidate, 'instance', None)
        if nested is not None and getattr(nested, 'plugin_id', '') == 'meld_control':
            return nested
        return candidate if hasattr(candidate, 'get_session_items') and hasattr(candidate, 'set_session_property') else None

    def _find_meld_plugin(self):
        runtime_host = self._get_runtime_host()
        if runtime_host is None:
            raise MeldConnectionError('meld_control runtime host is not available yet.')

        for method_name in ('get_plugin', 'get_plugin_instance', 'get_plugin_by_id', 'plugin'):
            method = getattr(runtime_host, method_name, None)
            if callable(method):
                try:
                    candidate = self._unwrap_plugin_instance(method('meld_control'))
                    if candidate is not None:
                        return candidate
                except Exception:
                    pass

        for attr_name in ('plugins', '_plugins', 'plugin_instances', '_plugin_instances'):
            bucket = getattr(runtime_host, attr_name, None)
            if isinstance(bucket, dict):
                for key, value in bucket.items():
                    if str(key) == 'meld_control':
                        candidate = self._unwrap_plugin_instance(value)
                        if candidate is not None:
                            return candidate
                    candidate = self._unwrap_plugin_instance(value)
                    if candidate is not None:
                        return candidate
            elif isinstance(bucket, (list, tuple)):
                for value in bucket:
                    candidate = self._unwrap_plugin_instance(value)
                    if candidate is not None:
                        return candidate

        raise MeldConnectionError('meld_control plugin was not found. Please keep meld_control loaded and connected.')

    def _require_meld_plugin(self):
        plugin = self._find_meld_plugin()
        connected = getattr(plugin, 'is_connected', None)
        if callable(connected):
            try:
                if not connected():
                    raise MeldConnectionError('meld_control is not connected to Meld.')
            except MeldConnectionError:
                raise
            except Exception:
                pass
        return plugin

    def _split_session_items(self, items: dict[str, dict[str, Any]]) -> dict[str, Any]:
        normalized = _normalize_meld_session_items(items)
        scenes: list[dict[str, Any]] = []
        raw_layers: list[dict[str, Any]] = []

        scene_ids: set[str] = set()
        for item_id, data in normalized.items():
            if not isinstance(data, dict):
                continue
            if _meld_item_type(data) == 'scene':
                row = dict(data)
                row['id'] = str(item_id)
                row['type'] = 'scene'
                scenes.append(row)
                scene_ids.add(str(item_id))

        children_by_parent: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for child_id, child_data in normalized.items():
            if not isinstance(child_data, dict):
                continue
            parent_id = _meld_parent_id(child_data)
            if parent_id:
                children_by_parent.setdefault(str(parent_id), []).append((str(child_id), child_data))

        def item_name(data: dict[str, Any]) -> str:
            return str(data.get('name') or _meld_item_name(data) or '').strip()

        def same_name(a: str, b: str) -> bool:
            return str(a or '').strip().casefold() == str(b or '').strip().casefold()

        def scene_ancestor(layer_id: str, layer_data: dict[str, Any]) -> tuple[str, str]:
            visited: set[str] = set()
            current = dict(layer_data or {})
            current_id = str(layer_id or '')
            while current_id and current_id not in visited:
                visited.add(current_id)
                parent_id = _meld_parent_id(current)
                if not parent_id:
                    break
                parent = normalized.get(parent_id)
                if not isinstance(parent, dict):
                    break
                if _meld_item_type(parent) == 'scene' or str(parent_id) in scene_ids:
                    return str(parent_id), item_name(parent)
                current_id = str(parent_id)
                current = parent
            return '', ''

        def is_known_filter_name(name: str) -> bool:
            needle = str(name or '').strip().casefold().replace('_', ' ').replace('-', ' ')
            compact = needle.replace(' ', '')
            return needle in {
                'chroma key', 'crop', 'color correction', 'color correction 1', 'color correction 2',
                'blur', 'mask', 'lut', 'luma key', 'color key', 'image mask', 'scroll', 'shader',
                'move', 'move value', 'audio monitor', 'gain', 'compressor', 'limiter', 'expander',
                'noise gate', 'noise suppression', 'vst 2.x plug-in', 'vst', 'delay', 'render delay',
            } or compact in {'chromakey', 'colorkey', 'colorkey1', 'colorcorrection', 'imagemask', 'lumakey'}

        def is_filter_child(data: dict[str, Any]) -> bool:
            name = item_name(data)
            raw_type = str(
                data.get('type') or data.get('itemType') or data.get('item_type') or
                data.get('kind') or data.get('objectType') or data.get('object_type') or
                data.get('class') or data.get('className') or data.get('class_name') or
                data.get('typeName') or data.get('type_name') or data.get('__type') or ''
            ).strip().casefold()
            compact_type = raw_type.replace('_', '').replace('-', '').replace(' ', '')
            if 'filter' in compact_type or 'effect' in compact_type:
                return True
            return is_known_filter_name(name)

        folder_container_ids: set[str] = set()
        internal_child_ids: set[str] = set()
        for parent_id, children in children_by_parent.items():
            parent = normalized.get(parent_id)
            if not isinstance(parent, dict) or _meld_item_type(parent) != 'layer':
                continue
            parent_name = item_name(parent)
            layer_children = [
                (str(cid), cdata) for cid, cdata in children
                if isinstance(cdata, dict) and _meld_item_type(cdata) == 'layer'
            ]
            if not layer_children:
                continue

            # Meld exposes filters/effects, for example Chroma Key, as children
            # below the edited media layer. Those children are not folders.
            # Treat them as internal children, otherwise the actual media layer
            # disappears from the dropdown and Live Actions cannot resolve it.
            filter_child_ids = [cid for cid, cdata in layer_children if is_filter_child(cdata)]
            if filter_child_ids:
                internal_child_ids.update(filter_child_ids)

            real_layer_children = [
                (cid, cdata) for cid, cdata in layer_children
                if cid not in filter_child_ids
            ]
            if not real_layer_children:
                continue

            different_named_children = [
                (cid, cdata) for cid, cdata in real_layer_children
                if not same_name(item_name(cdata), parent_name)
            ]
            same_named_children = [
                (cid, cdata) for cid, cdata in real_layer_children
                if same_name(item_name(cdata), parent_name)
            ]
            if different_named_children:
                folder_container_ids.add(str(parent_id))
                internal_child_ids.update(cid for cid, _ in same_named_children)
            else:
                internal_child_ids.update(cid for cid, _ in same_named_children)

        def layer_route_path(layer_id: str, layer_data: dict[str, Any]) -> str:
            names: list[str] = []
            current = dict(layer_data or {})
            current_name = item_name(current)
            visited: set[str] = set()
            parent_id = _meld_parent_id(current)
            while parent_id and parent_id not in visited:
                visited.add(parent_id)
                parent = normalized.get(parent_id)
                if not isinstance(parent, dict):
                    break
                if _meld_item_type(parent) == 'scene' or str(parent_id) in scene_ids:
                    break
                if str(parent_id) in folder_container_ids:
                    pname = item_name(parent)
                    if pname:
                        names.append(pname)
                parent_id = _meld_parent_id(parent)
            names.reverse()
            if current_name:
                names.append(current_name)
            collapsed: list[str] = []
            for name in names:
                if collapsed and same_name(collapsed[-1], name):
                    continue
                collapsed.append(name)
            return '/'.join(collapsed).strip('/')

        for item_id, data in normalized.items():
            if not isinstance(data, dict) or _meld_item_type(data) != 'layer':
                continue
            item_id = str(item_id)
            name = item_name(data)
            if not name or is_known_filter_name(name):
                continue
            if item_id in internal_child_ids:
                continue
            if item_id in folder_container_ids:
                continue

            row = dict(data)
            row['id'] = item_id
            row['type'] = 'layer'
            parent = _meld_parent_id(row)
            if parent:
                row['parent'] = parent
            sid, sname = scene_ancestor(item_id, row)
            row['_scene_id'] = sid
            row['_scene_name'] = sname
            full_path = layer_route_path(item_id, row) or name
            row['full_path'] = full_path
            row['display_name'] = full_path
            raw_layers.append(row)

        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for layer in raw_layers:
            key = (
                str(layer.get('_scene_id') or layer.get('_scene_name') or '').casefold(),
                str(layer.get('full_path') or layer.get('name') or '').casefold(),
            )
            old = deduped.get(key)
            if old is None:
                deduped[key] = layer
                continue
            old_depth = str(old.get('full_path') or '').count('/')
            new_depth = str(layer.get('full_path') or '').count('/')
            if new_depth < old_depth:
                deduped[key] = layer

        scenes.sort(key=lambda x: (int(not bool(x.get('current'))), int(x.get('index') or 0), str(x.get('name') or '').lower()))
        layers = list(deduped.values())
        layers.sort(key=lambda x: (str(x.get('_scene_name') or '').lower(), str(x.get('full_path') or x.get('name') or '').lower()))
        return {'scenes': scenes, 'layers': layers, 'items': normalized}

    def routes_file_path(self, settings: dict[str, Any] | None = None) -> Path:
        settings = dict(settings or {})
        configured = str(settings.get('meld_routes_file', '') or '').strip()
        if configured:
            p = Path(configured).expanduser()
            if not p.is_absolute():
                p = self._default_data_dir() / p
            return p
        return self._default_data_dir() / 'tiktok_live_alert_meld_routes.json'

    def _default_data_dir(self) -> Path:
        plugin_dir = Path(__file__).resolve().parent
        for parent in plugin_dir.parents:
            if parent.name.lower() == 'modules':
                return parent.parent / 'data' / 'tiktok_live_alert'
        # Dev fallback: keep it near the plugin, but still outside settings.json.
        return plugin_dir / 'data'

    def routes_file_marker(self, settings: dict[str, Any] | None = None) -> str:
        return '@file:tiktok_live_alert_meld_routes.json'

    def _decode_routes_data(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            return []
        routes: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            routes.append({
                'enabled': bool(entry.get('enabled', True)),
                'source_key': str(entry.get('source_key', 'latest_follower.txt') or 'latest_follower.txt'),
                'scene_id': str(entry.get('scene_id', '') or ''),
                'scene_name': str(entry.get('scene_name', '') or ''),
                'layer_id': str(entry.get('layer_id', '') or ''),
                'layer_name': str(entry.get('layer_name', '') or ''),
                'property_name': str(entry.get('property_name', 'text') or 'text'),
                'template': str(entry.get('template', '{value}') or '{value}'),
                'restore_delay': str(entry.get('restore_delay', entry.get('restore_delay_seconds', entry.get('timer_seconds', ''))) or ''),
                'threshold': int(float(str(entry.get('threshold', 0) or 0))) if str(entry.get('threshold', '') or '').strip() else 0,
                'target_user': str(entry.get('target_user', entry.get('user_name', '')) or ''),
            })
        return routes

    def _load_routes_from_text(self, raw: Any) -> list[dict[str, Any]]:
        text = str(raw or '').strip()
        if not text or text.startswith('@file:'):
            return []
        try:
            return self._decode_routes_data(json.loads(text))
        except Exception:
            return []

    def load_routes_from_file(self, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        path = self.routes_file_path(settings)
        try:
            if not path.exists():
                return []
            return self._decode_routes_data(json.loads(path.read_text(encoding='utf-8')))
        except Exception as exc:
            if self.logger:
                with contextlib.suppress(Exception):
                    self.logger.warning(f'Meld routes file could not be read: {path} ({exc})')
            return []

    def save_routes_to_file(self, routes: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> str:
        path = self.routes_file_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.save_routes_text(routes), encoding='utf-8')
        return str(path)

    def load_routes(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        raw = settings.get('meld_routes_json', '[]')
        inline_routes = self._load_routes_from_text(raw)

        # Temp tests pass a single inline route. Those must win over the external file.
        if settings.get('__prefer_inline_meld_routes'):
            return inline_routes

        file_routes = self.load_routes_from_file(settings)
        if file_routes:
            return file_routes

        # First run after this patch: migrate old settings.json routes into the new file.
        if inline_routes:
            with contextlib.suppress(Exception):
                self.save_routes_to_file(inline_routes, settings)
            return inline_routes
        return []

    def save_routes_text(self, routes: list[dict[str, Any]]) -> str:
        return json.dumps(routes, ensure_ascii=False, indent=2)

    def route_count(self, settings: dict[str, Any]) -> int:
        action_keys = set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)
        return sum(
            1 for route in self.load_routes(settings)
            if route.get('enabled') and str(route.get('source_key') or '').strip().lower() not in action_keys
        )

    def _direct_host_port(self) -> tuple[str, int]:
        settings = dict(getattr(self.owner_plugin, '_settings', {}) or {})
        host = str(settings.get('meld_host', settings.get('host', '127.0.0.1')) or '127.0.0.1').strip()
        port_raw = settings.get('meld_port', settings.get('port', 13376))
        try:
            port = int(str(port_raw or 13376).strip())
        except Exception:
            port = 13376
        return host or '127.0.0.1', port

    def _direct_adapter(self) -> _DirectMeldAdapter:
        host, port = self._direct_host_port()
        return _DirectMeldAdapter(host, port, timeout=5.0)

    def _fetch_session_snapshot_direct(self) -> dict[str, Any]:
        return self._split_session_items(self._direct_adapter().get_session_items())

    def fetch_session_snapshot(self) -> dict[str, Any]:
        # Erst die aktive meld_control-Verbindung nehmen. Falls sie zwar geladen ist,
        # aber keine Session-Items liefert, direkt über Melds WebChannel nachladen.
        last_error: Exception | None = None
        try:
            plugin = self._require_meld_plugin()
            items = plugin.get_session_items()
            snap = self._split_session_items(items)
            if snap.get('scenes') or snap.get('layers'):
                return snap
        except Exception as exc:
            last_error = exc

        try:
            return self._fetch_session_snapshot_direct()
        except Exception as exc:
            if last_error is not None:
                raise MeldConnectionError(f'{last_error}; direct Meld session fallback failed: {exc}')
            raise

    def apply_routes(self, settings: dict[str, Any], state: dict[str, Any], writer) -> None:
        routes = [route for route in self.load_routes(settings) if route.get('enabled')]
        if not routes:
            return
        payloads = writer._build_payloads(state, settings)
        try:
            plugin = self._require_meld_plugin()
            items = plugin.get_session_items()
            for route in routes:
                text = self._render_route_text(route, payloads)
                layer_id = self._resolve_layer_id(route, items)
                if not layer_id:
                    raise MeldConnectionError(f"Layer not found for route: {route.get('layer_name') or route.get('layer_id') or '?'}")
                ok, detail = self._set_property_resilient(plugin, layer_id, route.get('property_name') or 'text', text)
                if not ok:
                    raise MeldConnectionError(str(detail))
        except Exception as exc:
            if self.logger is not None:
                try:
                    self.logger.warning(f'Meld output failed: {exc}')
                except Exception:
                    pass

    def apply_routes_for_sources(self, settings: dict[str, Any], state: dict[str, Any], writer, source_keys: set[str] | list[str] | tuple[str, ...]) -> tuple[int, int, str]:
        wanted = {str(key or '').strip() for key in source_keys or [] if str(key or '').strip()}
        routes = [
            route for route in self.load_routes(settings)
            if route.get('enabled') and str(route.get('source_key') or '').strip() in wanted
        ]
        if not routes:
            return 0, 0, 'no matching enabled Meld route'

        payloads = writer._build_payloads(state, settings)
        ok_count = 0
        details: list[str] = []
        try:
            plugin = self._require_meld_plugin()
            items = plugin.get_session_items()
        except Exception as exc:
            try:
                plugin = self._direct_adapter()
                items = plugin.get_session_items()
                details.append(f'direct Meld fallback used after: {exc}')
            except Exception as direct_exc:
                return 0, len(routes), f'{exc}; direct Meld fallback failed: {direct_exc}'

        for route in routes:
            label = route.get('layer_name') or route.get('layer_id') or route.get('source_key') or '?'
            try:
                text = self._render_route_text(route, payloads)
                layer_id = self._resolve_layer_id(route, items)
                if not layer_id:
                    details.append(f'{label}: layer not found')
                    continue
                ok, detail = self._set_property_resilient(plugin, layer_id, route.get('property_name') or 'text', text)
                if ok:
                    ok_count += 1
                    preview = str(text).replace('\n', ' / ')
                    if len(preview) > 70:
                        preview = preview[:67] + '...'
                    details.append(f'{label}: {preview}')
                else:
                    details.append(f'{label}: {detail}')
            except Exception as exc:
                details.append(f'{label}: {exc}')

        failed = max(0, len(routes) - ok_count)
        if ok_count and self.logger is not None:
            try:
                self.logger.info(f'Meld output test/reset wrote {ok_count}/{len(routes)} route(s): ' + ' | '.join(details[:4]))
            except Exception:
                pass
        return ok_count, failed, ' | '.join(details)

    def _trigger_media_once(self, plugin: Any, layer_id: str, route: dict[str, Any], command: str = '', items: dict[str, dict[str, Any]] | None = None) -> tuple[bool, Any]:
        delay = self._restore_delay_from_route(route, default=8.0)
        action = str(route.get('property_name') or 'play_once').strip().lower()

        # If the selected media is inside a Meld folder/group, the parent group
        # must also be visible. Otherwise the child receives the command but
        # nothing appears on canvas. Restore parents after the trigger timer.
        parent_restore: list[tuple[str, bool]] = []
        for parent_id in self._parent_layer_chain(layer_id, items):
            previous = self._get_layer_visible(parent_id, items)
            if previous is not None:
                parent_restore.append((parent_id, bool(previous)))
            with contextlib.suppress(Exception):
                self._set_property_resilient(plugin, parent_id, 'visible', True)

        original_visible = self._get_layer_visible(layer_id, items)
        if original_visible is None:
            original_visible = False

        # For media layers: force hidden first, show again, then restart/play.
        # This is more reliable in Meld than trying to write a fake "play_once" property.
        with contextlib.suppress(Exception):
            self._set_property_resilient(plugin, layer_id, 'visible', False)

        show_ok, show_detail = self._set_property_resilient(plugin, layer_id, 'visible', True)

        tried: list[str] = []
        call_ok = False
        call_detail: Any = ''
        for candidate in [command, 'restart', 'play', 'start']:
            candidate = str(candidate or '').strip()
            if not candidate or candidate in tried:
                continue
            tried.append(candidate)
            call_ok, call_detail = self._call_layer_function_resilient(plugin, layer_id, candidate)
            if call_ok:
                break

        if show_ok or call_ok:
            # show_hide_once must really hide after the timer, regardless of the previous state.
            # play_once stops the media after the timer and then restores the previous visibility.
            force_hide = action in {'show_hide_once', 'show_once'}
            stop_after = action in {'show_hide_once', 'show_once', 'play_once', 'trigger', 'media_once', 'restart_media'}
            restore_visible = False if force_hide else bool(original_visible)
            self._schedule_media_restore(plugin, layer_id, delay, restore_visible, stop_after=stop_after)
            for parent_id, was_visible in parent_restore:
                self._schedule_visible_restore(plugin, parent_id, delay, was_visible)
            if force_hide:
                extra = f', parent folder restore={len(parent_restore)}' if parent_restore else ''
                return True, f'visible true, stop/hide in {delay:g}s{extra}'
            extra = f', parent folder restore={len(parent_restore)}' if parent_restore else ''
            return True, f'visible true, stop and restore visible={restore_visible} in {delay:g}s{extra}'

        return False, call_detail or show_detail or 'media trigger failed'

    def _restore_delay_from_route(self, route: dict[str, Any], default: float = 0.0) -> float:
        # Live actions have their own Timer field. Template remains a fallback for older saved routes.
        raw = str(route.get('restore_delay', route.get('restore_delay_seconds', route.get('timer_seconds', ''))) or '').strip().lower()
        if not raw:
            raw = str(route.get('template') or '').strip().lower()
        raw = raw.replace(',', '.')
        for token in ('sekunden', 'sekunde', 'secs', 'sec', 'sek', 'seconds', 'second'):
            raw = raw.replace(token, '')
        if raw.endswith('s'):
            raw = raw[:-1]
        raw = raw.strip()
        if raw and raw not in {'{value}', '{}'}:
            try:
                value = float(raw)
                if value > 0:
                    return max(0.25, min(3600.0, value))
                if value == 0:
                    return 0.0
            except Exception:
                pass
        return max(0.0, min(3600.0, float(default or 0.0)))

    def _parent_layer_chain(self, layer_id: str, items: dict[str, dict[str, Any]] | None) -> list[str]:
        if not items:
            return []
        normalized = _normalize_meld_session_items(items)
        chain: list[str] = []
        visited: set[str] = set()
        current_id = str(layer_id or '')
        while current_id and current_id not in visited:
            visited.add(current_id)
            current = normalized.get(current_id)
            if not isinstance(current, dict):
                break
            parent_id = _meld_parent_id(current)
            if not parent_id or parent_id in visited:
                break
            parent = normalized.get(str(parent_id))
            if not isinstance(parent, dict):
                break
            parent_type = _meld_item_type(parent)
            if parent_type == 'scene':
                break
            if parent_type == 'layer':
                chain.append(str(parent_id))
            current_id = str(parent_id)
        chain.reverse()
        return chain

    def _get_layer_visible(self, layer_id: str, items: dict[str, dict[str, Any]] | None) -> bool | None:
        data = (items or {}).get(str(layer_id))
        if not isinstance(data, dict):
            return None

        def pick(obj: Any) -> bool | None:
            if not isinstance(obj, dict):
                return None
            for key in ('visible', 'isVisible', 'shown', 'enabled'):
                if key in obj:
                    value = obj.get(key)
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, (int, float)):
                        return bool(value)
                    if isinstance(value, str):
                        clean = value.strip().lower()
                        if clean in {'1', 'true', 'yes', 'on', 'visible'}:
                            return True
                        if clean in {'0', 'false', 'no', 'off', 'hidden'}:
                            return False
            return None

        direct = pick(data)
        if direct is not None:
            return direct
        for nested_key in ('properties', 'propertyValues', 'values', 'state', 'settings'):
            nested = data.get(nested_key)
            nested_value = pick(nested)
            if nested_value is not None:
                return nested_value
        return None

    def _schedule_visible_restore(self, plugin: Any, layer_id: str, delay: float, visible: bool) -> None:
        self._schedule_media_restore(plugin, layer_id, delay, bool(visible), stop_after=False)

    def _bump_restore_token(self, layer_id: str) -> int:
        key = str(layer_id or '')
        with self._restore_lock:
            value = int(self._restore_tokens.get(key) or 0) + 1
            self._restore_tokens[key] = value
            return value

    def _restore_token_is_current(self, layer_id: str, token: int) -> bool:
        key = str(layer_id or '')
        with self._restore_lock:
            return int(self._restore_tokens.get(key) or 0) == int(token)

    def _schedule_media_restore(self, plugin: Any, layer_id: str, delay: float, visible: bool, stop_after: bool = False) -> None:
        if float(delay or 0.0) <= 0:
            return
        restore_token = self._bump_restore_token(layer_id)

        def _restore() -> None:
            try:
                if not self._restore_token_is_current(layer_id, restore_token):
                    return
                if stop_after:
                    # Try to stop/pause first. Some Meld media layers support one name, some another.
                    for cmd in ('stop', 'pause'):
                        ok, _detail = self._call_layer_function_resilient(plugin, layer_id, cmd)
                        if ok:
                            break
                self._set_property_resilient(plugin, layer_id, 'visible', bool(visible))
            except Exception:
                pass

        owner = getattr(self, 'owner_plugin', None)
        runner = getattr(owner, '_run_on_ui_thread', None)

        def _timer_fire() -> None:
            if callable(runner):
                try:
                    runner(_restore, wait=False)
                    return
                except Exception:
                    pass
            _restore()

        timer = threading.Timer(float(delay), _timer_fire)
        timer.daemon = True
        timer.start()

    def _call_layer_function_resilient(self, plugin, layer_id: str, command: str) -> tuple[bool, Any]:
        command = str(command or '').strip()
        if not command:
            return False, 'empty layer function'
        method = getattr(plugin, 'call_layer_function', None)
        if callable(method):
            return method(layer_id, command, timeout=3.0)
        method = getattr(plugin, 'invoke_meld_method', None)
        if callable(method):
            return method('callFunction', [str(layer_id), command], timeout=3.0)
        return False, 'meld_control has no layer function bridge'

    def stop_routes(self, routes: list[dict[str, Any]]) -> tuple[int, int, str]:
        routes = [dict(route) for route in (routes or [])]
        if not routes:
            return 0, 0, 'no routes to stop'

        ok_count = 0
        failed = 0
        details: list[str] = []
        try:
            plugin = self._require_meld_plugin()
            items = plugin.get_session_items()
        except Exception as exc:
            try:
                plugin = self._direct_adapter()
                items = plugin.get_session_items()
                details.append(f'direct Meld fallback used after: {exc}')
            except Exception as direct_exc:
                return 0, len(routes), f'{exc}; direct Meld fallback failed: {direct_exc}'

        for route in routes:
            label = route.get('layer_name') or route.get('layer_id') or route.get('source_key') or '?'
            try:
                layer_id = self._resolve_layer_id(route, items)
                if not layer_id:
                    failed += 1
                    details.append(f'{label}: layer not found')
                    continue
                self._bump_restore_token(layer_id)
                stopped = False
                for cmd in ('stop', 'pause'):
                    with contextlib.suppress(Exception):
                        cmd_ok, _cmd_detail = self._call_layer_function_resilient(plugin, layer_id, cmd)
                        stopped = stopped or bool(cmd_ok)
                visible_ok, visible_detail = self._set_property_resilient(plugin, layer_id, 'visible', False)
                if visible_ok or stopped:
                    ok_count += 1
                    details.append(f'{label}: stopped/hidden')
                else:
                    failed += 1
                    details.append(f'{label}: {visible_detail}')
            except Exception as exc:
                failed += 1
                details.append(f'{label}: {exc}')

        return ok_count, failed, ' | '.join(details)

    def trigger_routes_for_sources(self, settings: dict[str, Any], state: dict[str, Any], writer, source_keys: set[str] | list[str] | tuple[str, ...]) -> tuple[int, int, str]:
        wanted = {str(key or '').strip().lower() for key in source_keys or [] if str(key or '').strip()}
        routes = [
            route for route in self.load_routes(settings)
            if route.get('enabled') and str(route.get('source_key') or '').strip().lower() in wanted
        ]
        if not routes:
            return 0, 0, 'no matching enabled Meld trigger route'

        ok_count = 0
        failed = 0
        details: list[str] = []
        try:
            plugin = self._require_meld_plugin()
            items = plugin.get_session_items()
        except Exception as exc:
            try:
                plugin = self._direct_adapter()
                items = plugin.get_session_items()
                details.append(f'direct Meld fallback used after: {exc}')
            except Exception as direct_exc:
                return 0, len(routes), f'{exc}; direct Meld fallback failed: {direct_exc}'

        payloads = writer._build_payloads(state, settings) if writer is not None else {}
        for route in routes:
            label = route.get('layer_name') or route.get('layer_id') or route.get('source_key') or '?'
            try:
                layer_id = self._resolve_layer_id(route, items)
                if not layer_id:
                    failed += 1
                    details.append(f'{label}: layer not found')
                    continue

                raw_action = str(route.get('property_name') or 'play_once').strip() or 'play_once'
                action = raw_action.lower()
                template = str(route.get('template') or '').strip()
                command = ''
                if action.startswith('call:'):
                    command = raw_action.split(':', 1)[1].strip()
                elif action in {'restart', 'play', 'start', 'stop', 'pause', 'resume'}:
                    command = action
                elif template and template != '{value}' and not template.startswith('{'):
                    try:
                        command = template.format(**payloads)
                    except Exception:
                        command = template

                if action in {'show_hide_once', 'show_once', 'play_once', 'trigger', 'media_once', 'restart_media'}:
                    success, detail = self._trigger_media_once(plugin, layer_id, route, command, items)
                    if success:
                        ok_count += 1
                        details.append(f'{label}: show/hide once')
                    else:
                        failed += 1
                        details.append(f'{label}: {detail}')
                    continue

                if action.startswith('visible:'):
                    value = action.split(':', 1)[1].strip() in {'1', 'true', 'yes', 'on'}
                    parent_restore: list[tuple[str, bool]] = []
                    if value:
                        for parent_id in self._parent_layer_chain(layer_id, items):
                            previous = self._get_layer_visible(parent_id, items)
                            if previous is not None:
                                parent_restore.append((parent_id, bool(previous)))
                            with contextlib.suppress(Exception):
                                self._set_property_resilient(plugin, parent_id, 'visible', True)
                    original_visible = self._get_layer_visible(layer_id, items)
                    success, detail = self._set_property_resilient(plugin, layer_id, 'visible', value)
                    if success:
                        delay = self._restore_delay_from_route(route, default=0.0)
                        if original_visible is not None and delay > 0:
                            self._schedule_visible_restore(plugin, layer_id, delay, bool(original_visible))
                            for parent_id, was_visible in parent_restore:
                                self._schedule_visible_restore(plugin, parent_id, delay, was_visible)
                            details.append(f'{label}: visible={value}, restore visible={bool(original_visible)} in {delay:g}s, parent restore={len(parent_restore)}')
                        else:
                            details.append(f'{label}: visible={value}')
                        ok_count += 1
                    else:
                        failed += 1
                        details.append(f'{label}: {detail}')
                    continue

                if command:
                    success, detail = self._call_layer_function_resilient(plugin, layer_id, command)
                    if success:
                        ok_count += 1
                        details.append(f'{label}: call {command}')
                    else:
                        failed += 1
                        details.append(f'{label}: {detail}')
                    continue

                text = self._render_route_text(route, payloads)
                success, detail = self._set_property_resilient(plugin, layer_id, raw_action, text)
                if success:
                    ok_count += 1
                    details.append(f'{label}: set {raw_action}')
                else:
                    failed += 1
                    details.append(f'{label}: {detail}')
            except Exception as exc:
                failed += 1
                details.append(f'{label}: {exc}')

        return ok_count, failed, ' | '.join(details[:8])

    def test_route(self, route: dict[str, Any], settings: dict[str, Any], state: dict[str, Any], writer) -> tuple[bool, str]:
        payloads = writer._build_payloads(state, settings)
        try:
            fallback_note = ''
            try:
                plugin = self._require_meld_plugin()
                items = plugin.get_session_items()
            except Exception as exc:
                # The normal Meld Outputs row-test must be just as tolerant as the
                # working Live Actions path. If the runtime plugin lookup is stale,
                # connect directly to Meld's WebChannel before declaring the test dead.
                plugin = self._direct_adapter()
                items = plugin.get_session_items()
                fallback_note = f'Direct Meld fallback used after: {exc}\n'

            layer_id = self._resolve_layer_id(route, items)
            if not layer_id:
                return False, 'Layer not found in Meld session.'

            raw_action = str(route.get('property_name') or 'text').strip() or 'text'
            action = raw_action.lower()
            template = str(route.get('template') or '').strip()
            command = ''
            if action.startswith('call:'):
                command = raw_action.split(':', 1)[1].strip()
            elif action in {'restart', 'play', 'start', 'stop', 'pause', 'resume'}:
                command = action
            elif template and template != '{value}' and not template.startswith('{'):
                with contextlib.suppress(Exception):
                    command = template.format(**payloads)

            if action in {'show_hide_once', 'show_once', 'play_once', 'trigger', 'media_once', 'restart_media'}:
                ok, detail = self._trigger_media_once(plugin, layer_id, route, command, items)
                return bool(ok), f'Triggered Meld layer {layer_id}.\n{detail}'

            if action.startswith('visible:'):
                value = action.split(':', 1)[1].strip() in {'1', 'true', 'yes', 'on'}
                parent_restore: list[tuple[str, bool]] = []
                if value:
                    for parent_id in self._parent_layer_chain(layer_id, items):
                        previous = self._get_layer_visible(parent_id, items)
                        if previous is not None:
                            parent_restore.append((parent_id, bool(previous)))
                        with contextlib.suppress(Exception):
                            self._set_property_resilient(plugin, parent_id, 'visible', True)
                original_visible = self._get_layer_visible(layer_id, items)
                ok, detail = self._set_property_resilient(plugin, layer_id, 'visible', value)
                if ok:
                    delay = self._restore_delay_from_route(route, default=0.0)
                    if original_visible is not None and delay > 0:
                        self._schedule_visible_restore(plugin, layer_id, delay, bool(original_visible))
                        for parent_id, was_visible in parent_restore:
                            self._schedule_visible_restore(plugin, parent_id, delay, was_visible)
                        return True, f'Set visible={value} on Meld layer {layer_id}. Restore visible={bool(original_visible)} in {delay:g}s. Parent restore={len(parent_restore)}.'
                    return True, f'Set visible={value} on Meld layer {layer_id}.\n{detail}'
                return False, str(detail)

            if command:
                ok, detail = self._call_layer_function_resilient(plugin, layer_id, command)
                return bool(ok), f'Called {command} on Meld layer {layer_id}.\n{detail}'

            text = self._render_route_text(route, payloads)
            ok, detail = self._set_property_resilient(plugin, layer_id, raw_action, text)
            preview = str(text).replace('\n', ' / ')
            if len(preview) > 120:
                preview = preview[:117] + '...'
            if ok:
                base = f'{fallback_note}Wrote to Meld layer {layer_id}.\nValue: {preview}'
                return True, (base + f'\n{detail}' if detail else base)
            return False, f'{fallback_note}{detail}\nValue was: {preview}'
        except Exception as exc:
            return False, str(exc)

    def _set_property_resilient(self, plugin: Any, layer_id: str, property_name: str, value: Any) -> tuple[bool, str]:
        prop = str(property_name or 'text')
        details: list[str] = []

        for timeout in (3.5, 6.0):
            try:
                ok, detail = plugin.set_session_property(layer_id, prop, value, timeout=timeout)
            except TypeError:
                try:
                    ok, detail = plugin.set_session_property(layer_id, prop, value)
                except Exception as exc:
                    ok, detail = False, str(exc)
            except Exception as exc:
                ok, detail = False, str(exc)
            if ok:
                return True, f'meld_control timeout={timeout:g}s'
            detail_text = str(detail or '').strip()
            if detail_text:
                details.append(detail_text)
            if detail_text and 'timed out' not in detail_text.lower():
                break

        fallback_ok, fallback_msg = self._test_route_direct_fallback(plugin, layer_id, prop, value)
        if fallback_ok:
            return True, 'direct fallback ok'

        if fallback_msg:
            details.append(str(fallback_msg))
        return False, ' | '.join(x for x in details if x) or 'Meld property write failed'

    def _test_route_direct_fallback(self, plugin: Any, layer_id: str, property_name: str, value: Any) -> tuple[bool, str]:
        try:
            plugin_settings = dict(getattr(plugin, '_settings', {}) or {})
            if plugin_settings:
                host = str(plugin_settings.get('host', plugin_settings.get('meld_host', '127.0.0.1')) or '127.0.0.1').strip()
                port = int(str(plugin_settings.get('port', plugin_settings.get('meld_port', '13376')) or '13376').strip())
            else:
                host, port = self._direct_host_port()
            with MeldWebChannelClient(host=host, port=port, timeout=5.0) as client:
                client.set_property(layer_id, str(property_name or 'text'), value)
            return True, 'direct fallback ok'
        except Exception as exc:
            return False, str(exc)

    def _canonical_layer_rows(self, items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            snap = self._split_session_items(items)
            return [dict(row) for row in (snap.get('layers') or []) if isinstance(row, dict)]
        except Exception:
            return []

    def _resolve_layer_id(self, route: dict[str, Any], items: dict[str, dict[str, Any]]) -> str:
        layer_path = str(route.get('layer_name') or '').strip().strip('/')
        layer_id = str(route.get('layer_id') or '').strip()
        scene_id = str(route.get('scene_id') or '').strip()
        scene_name = str(route.get('scene_name') or '').strip().replace('  [current]', '').strip().casefold()
        rows = self._canonical_layer_rows(items)

        def scene_matches(row: dict[str, Any]) -> bool:
            if scene_id and str(row.get('_scene_id') or '') != scene_id:
                return False
            if scene_name and str(row.get('_scene_name') or '').strip().casefold() != scene_name:
                return False
            return True

        def row_path(row: dict[str, Any]) -> str:
            return str(row.get('full_path') or row.get('display_name') or row.get('name') or '').strip().strip('/')

        def cf(value: Any) -> str:
            return str(value or '').strip().strip('/').casefold()

        if layer_id:
            # Prefer the real Meld object id from the dropdown, but never let a stale id block
            # a valid path/name fallback after Meld reloaded the scene.
            for row in rows:
                if str(row.get('id') or '') == layer_id:
                    return str(row.get('id') or '')

        if layer_path:
            wanted_path = cf(layer_path)
            wanted_leaf = cf(layer_path.rsplit('/', 1)[-1])

            # Exact full-path match inside the selected scene: Alerts/100likes, etc.
            for row in rows:
                if scene_matches(row) and cf(row_path(row)) == wanted_path:
                    return str(row.get('id') or '')

            # Same but allow older saved values with duplicated slashes/spaces.
            wanted_parts = [p for p in wanted_path.split('/') if p]
            for row in rows:
                path_parts = [p for p in cf(row_path(row)).split('/') if p]
                if scene_matches(row) and path_parts == wanted_parts:
                    return str(row.get('id') or '')

            # Legacy short-name fallback inside selected scene.
            in_scene_leaf = [row for row in rows if scene_matches(row) and cf(row.get('name')) == wanted_leaf]
            if len(in_scene_leaf) == 1:
                return str(in_scene_leaf[0].get('id') or '')
            for row in in_scene_leaf:
                if cf(row_path(row)).endswith('/' + wanted_leaf) or cf(row_path(row)) == wanted_leaf:
                    return str(row.get('id') or '')

            # Global unique full-path / leaf fallback for old saved routes without scene id.
            path_matches = [row for row in rows if cf(row_path(row)) == wanted_path]
            if len(path_matches) == 1:
                return str(path_matches[0].get('id') or '')
            leaf_matches = [row for row in rows if cf(row.get('name')) == wanted_leaf]
            if len(leaf_matches) == 1:
                return str(leaf_matches[0].get('id') or '')

        return ''

    def _render_route_text(self, route: dict[str, Any], payloads: dict[str, str]) -> str:
        source_key = str(route.get('source_key') or 'latest_follower.txt')
        value = str(payloads.get(source_key, ''))
        template = str(route.get('template') or '{value}')
        context: dict[str, str] = {'value': value}
        for key, content in payloads.items():
            safe = key.replace('.txt', '').replace('.', '_').replace('-', '_')
            context[safe] = str(content)
        try:
            return str(template).format(**context)
        except Exception:
            return value
