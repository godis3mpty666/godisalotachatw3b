from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import importlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
import webbrowser
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

TikTokChatClient = getattr(importlib.import_module("TikTok" + "Live"), "TikTok" + "LiveClient")

from data.paths import app_root
from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin

try:
    from PySide6 import QtCore, QtWidgets
    _QT_AVAILABLE = True
except Exception:  # pragma: no cover
    _QT_AVAILABLE = False

    class _DummySignal:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def connect(self, *args: Any, **kwargs: Any) -> None:
            pass

        def emit(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _DummyWidget:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _DummyQtCore:
        Signal = _DummySignal

        class Qt:
            class WidgetAttribute:
                WA_DeleteOnClose = 0

    class _DummyQtWidgets:
        QWidget = _DummyWidget
        QDialog = _DummyWidget

    QtCore = _DummyQtCore()
    QtWidgets = _DummyQtWidgets()

def _norm_lang(value: str | None) -> str:
    lang = str(value or 'de').strip().lower()
    return lang if lang in {'de', 'en'} else 'de'


_I18N = {
    'en': {
        'Aktiviert': 'Enabled',
        'Testen': 'Test',
        'Speichern': 'Save',
        'Löschen': 'Delete',
        'Aktion': 'Action',
        'Meld-Aktion': 'Meld action',
        'Befehl': 'Command',
        'Ziel-WebSocket': 'Target WebSocket',
        'Erlaubte Nutzer': 'Allowed users',
        'z.B. !cp': 'e.g. !cp',
        'OBS: z.B. Shift+F10': 'OBS: e.g. Shift+F10',
        'z.B. meld.recordClip oder showScene:<sceneId>': 'e.g. meld.recordClip or showScene:<sceneId>',
        'user1,user2 oder leer = alle': 'user1,user2 or empty = everyone',
        '+ Neuer Befehl': '+ New command',
        'Alle speichern': 'Save all',
        'Close': 'Close',
        'Clip aufnehmen': 'Record clip',
        'Replay anzeigen': 'Show replay',
        'Replay ausblenden': 'Hide replay',
        'Screenshot': 'Screenshot',
        'Screenshot vertical': 'Vertical screenshot',
        'Streaming starten': 'Start streaming',
        'Streaming stoppen': 'Stop streaming',
        'Streaming togglen': 'Toggle streaming',
        'Recording starten': 'Start recording',
        'Recording stoppen': 'Stop recording',
        'Recording togglen': 'Toggle recording',
        'Virtual Camera togglen': 'Toggle virtual camera',
        'Eigener Meld-Befehl ...': 'Custom Meld command ...',
        'Bitte einen Befehl eintragen.': 'Please enter a command.',
        'Bitte einen Meld-Command eintragen.': 'Please enter a Meld command.',
        'Bitte eine OBS-Tastenkombi eintragen.': 'Please enter an OBS hotkey.',
        'Fehlt': 'Missing',
    },
    'de': {
        'Enabled': 'Aktiviert',
        'Test': 'Testen',
        'Save': 'Speichern',
        'Delete': 'Löschen',
        'Action': 'Aktion',
        'Command': 'Befehl',
        'Allowed users': 'Erlaubte Nutzer',
        '+ New command': '+ Neuer Befehl',
        'Save all': 'Alle speichern',
        'Close': 'Schließen',
    },
}


def _tr(lang: str | None, text: str) -> str:
    base = str(text or '')
    return _I18N.get(_norm_lang(lang), {}).get(base, base)


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
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.username = username
        self.text = text
        self.channel = channel
        self.created_at = created_at
        self.last_update = last_update
        self.count = count
        self.message_type = message_type
        self.extra = dict(extra or {})


class _CommandRowWidget(QtWidgets.QWidget):
    save_requested = QtCore.Signal(object)
    delete_requested = QtCore.Signal(object)
    test_requested = QtCore.Signal(object)

    MELD_PRESETS: list[tuple[str, str]] = [
        ("Clip aufnehmen", "meld.recordClip"),
        ("Replay anzeigen", "meld.replay.show"),
        ("Replay ausblenden", "meld.replay.dismiss"),
        ("Screenshot", "meld.screenshot"),
        ("Screenshot vertical", "meld.screenshot.vertical"),
        ("Streaming starten", "meld.startStreamingAction"),
        ("Streaming stoppen", "meld.stopStreamingAction"),
        ("Streaming togglen", "meld.toggleStreamingAction"),
        ("Recording starten", "meld.startRecordingAction"),
        ("Recording stoppen", "meld.stopRecordingAction"),
        ("Recording togglen", "meld.toggleRecordingAction"),
        ("Virtual Camera togglen", "meld.toggleVirtualCameraAction"),
        ("toggleRecord()", "toggleRecord()"),
        ("toggleStream()", "toggleStream()"),
        ("showStagedScene()", "showStagedScene()"),
        ("showScene:<sceneId>", "showScene:<sceneId>"),
        ("setStagedScene:<sceneId>", "setStagedScene:<sceneId>"),
        ("toggleMute:<trackId>", "toggleMute:<trackId>"),
        ("setMuted:<trackId>:true", "setMuted:<trackId>:true"),
        ("toggleMonitor:<trackId>", "toggleMonitor:<trackId>"),
        ("toggleLayer:<sceneId>:<layerId>", "toggleLayer:<sceneId>:<layerId>"),
        ("toggleEffect:<sceneId>:<layerId>:<effectId>", "toggleEffect:<sceneId>:<layerId>:<effectId>"),
        ("setGain:<trackId>:0.5", "setGain:<trackId>:0.5"),
        ("setProperty:<objectId>:visible:true", "setProperty:<objectId>:visible:true"),
        ("callFunction:<layerId>:play", "callFunction:<layerId>:play"),
        ("callFunctionWithArgs:<layerId>:seekTo:[0]", "callFunctionWithArgs:<layerId>:seekTo:[0]"),
        ("sendStreamEvent:CONFETTIPOP_TRIGGER", "sendStreamEvent:CONFETTIPOP_TRIGGER"),
        ("sendStreamEvent:SUBATHONTIMER_ADDTIME:{\"amount\":120}", "sendStreamEvent:SUBATHONTIMER_ADDTIME:{\"amount\":120}"),
        ("Eigener Meld-Befehl ...", "__custom__"),
    ]

    def __init__(self, data: dict[str, Any] | None = None, parent: QtWidgets.QWidget | None = None, language: str = 'de') -> None:
        super().__init__(parent)
        self.language = _norm_lang(language)
        self._data = dict(data or {})
        self._build_ui()
        self.set_data(self._data)

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        self.enabled_cb = QtWidgets.QCheckBox(_tr(self.language, "Aktiviert"))
        top.addWidget(self.enabled_cb)
        top.addStretch(1)

        self.test_btn = QtWidgets.QPushButton(_tr(self.language, "Testen"))
        self.save_btn = QtWidgets.QPushButton(_tr(self.language, "Speichern"))
        self.delete_btn = QtWidgets.QPushButton(_tr(self.language, "Löschen"))
        self.test_btn.clicked.connect(self._emit_test)
        self.save_btn.clicked.connect(self._emit_save)
        self.delete_btn.clicked.connect(self._emit_delete)
        top.addWidget(self.test_btn)
        top.addWidget(self.save_btn)
        top.addWidget(self.delete_btn)

        root.addLayout(top)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        self.command_edit = QtWidgets.QLineEdit()
        self.command_edit.setPlaceholderText(_tr(self.language, "z.B. !cp"))

        self.backend_combo = QtWidgets.QComboBox()
        self.backend_combo.addItem("OBS", "obs")
        self.backend_combo.addItem("Meld", "meld")
        self.backend_combo.currentIndexChanged.connect(self._update_backend_ui)

        self.action_label = QtWidgets.QLabel(_tr(self.language, "Aktion"))

        self.action_stack = QtWidgets.QStackedWidget()

        self.hotkey_edit = QtWidgets.QLineEdit()
        self.hotkey_edit.setPlaceholderText(_tr(self.language, "OBS: z.B. Shift+F10"))
        self.action_stack.addWidget(self.hotkey_edit)

        self.meld_widget = QtWidgets.QWidget()
        meld_layout = QtWidgets.QVBoxLayout(self.meld_widget)
        meld_layout.setContentsMargins(0, 0, 0, 0)
        meld_layout.setSpacing(4)

        self.meld_combo = QtWidgets.QComboBox()
        for label, value in self.MELD_PRESETS:
            self.meld_combo.addItem(_tr(self.language, label), value)
        self.meld_combo.currentIndexChanged.connect(self._on_meld_preset_changed)

        self.meld_custom_edit = QtWidgets.QLineEdit()
        self.meld_custom_edit.setPlaceholderText(_tr(self.language, "z.B. meld.recordClip oder showScene:<sceneId>"))

        meld_layout.addWidget(self.meld_combo)
        meld_layout.addWidget(self.meld_custom_edit)
        self.action_stack.addWidget(self.meld_widget)

        self.users_edit = QtWidgets.QLineEdit()
        self.users_edit.setPlaceholderText(_tr(self.language, "user1,user2 oder leer = alle"))

        form.addRow(_tr(self.language, "Befehl"), self.command_edit)
        form.addRow(_tr(self.language, "Ziel-WebSocket"), self.backend_combo)
        form.addRow(self.action_label, self.action_stack)
        form.addRow(_tr(self.language, "Erlaubte Nutzer"), self.users_edit)

        root.addLayout(form)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        root.addWidget(line)

        self._update_backend_ui()

    def _emit_test(self) -> None:
        self.test_requested.emit(self)

    def _emit_save(self) -> None:
        self.save_requested.emit(self)

    def _emit_delete(self) -> None:
        self.delete_requested.emit(self)

    def _update_backend_ui(self) -> None:
        backend = str(self.backend_combo.currentData() or "obs")
        if backend == 'meld':
            self.action_stack.setCurrentWidget(self.meld_widget)
            self.action_label.setText(_tr(self.language, "Meld-Aktion"))
        else:
            self.action_stack.setCurrentWidget(self.hotkey_edit)
            self.action_label.setText("OBS Hotkey")

    def _on_meld_preset_changed(self) -> None:
        value = str(self.meld_combo.currentData() or '')
        is_custom = value == '__custom__'
        self.meld_custom_edit.setEnabled(True)
        if not is_custom:
            self.meld_custom_edit.setText(value)

    def _current_action_value(self) -> str:
        backend = str(self.backend_combo.currentData() or "obs")
        if backend == 'meld':
            preset_value = str(self.meld_combo.currentData() or '')
            custom_value = self.meld_custom_edit.text().strip()
            if preset_value == '__custom__':
                return custom_value
            return custom_value or preset_value
        return self.hotkey_edit.text().strip()

    def get_data(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled_cb.isChecked(),
            "command": self.command_edit.text().strip(),
            "target_backend": str(self.backend_combo.currentData() or "obs"),
            "obs_hotkey": self._current_action_value(),
            "allowed_users": self.users_edit.text().strip(),
        }

    def set_data(self, data: dict[str, Any]) -> None:
        self.enabled_cb.setChecked(bool(data.get("enabled", True)))
        self.command_edit.setText(str(data.get("command", "") or ""))
        backend = str(data.get("target_backend", data.get("backend", "obs")) or "obs").strip().lower()
        idx = self.backend_combo.findData(backend)
        self.backend_combo.setCurrentIndex(idx if idx >= 0 else 0)

        action_value = str(data.get("obs_hotkey", data.get("obs_hotkey_name", "")) or "").strip()
        self.hotkey_edit.setText(action_value)

        preset_idx = self.meld_combo.findData(action_value)
        if preset_idx >= 0:
            self.meld_combo.setCurrentIndex(preset_idx)
            self.meld_custom_edit.setText(action_value)
        else:
            custom_idx = self.meld_combo.findData('__custom__')
            self.meld_combo.setCurrentIndex(custom_idx if custom_idx >= 0 else 0)
            self.meld_custom_edit.setText(action_value)

        self.users_edit.setText(str(data.get("allowed_users", "") or ""))
        self._update_backend_ui()


class _ChatCommandsWindow(QtWidgets.QDialog):
    def __init__(
        self,
        plugin: "TikTokChatPlugin",
        host: PluginHost | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.plugin = plugin
        self.host = host
        self.language = _norm_lang(getattr(plugin, 'ui_language', 'de'))
        self.row_widgets: list[_CommandRowWidget] = []
        self.setWindowTitle("TikTok Chat - Chat Commands")
        self.resize(760, 620)
        self.setModal(False)
        self._build_ui()
        self._load_from_plugin()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton(_tr(self.language, "+ Neuer Befehl"))
        self.add_btn.clicked.connect(self._add_empty_row)
        top.addWidget(self.add_btn)
        top.addStretch(1)
        root.addLayout(top)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QtWidgets.QWidget()
        self.container_layout = QtWidgets.QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(6)
        self.container_layout.addStretch(1)

        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)

        self.save_all_btn = QtWidgets.QPushButton(_tr(self.language, "Alle speichern"))
        self.save_all_btn.clicked.connect(self._save_all)

        self.close_btn = QtWidgets.QPushButton(_tr(self.language, "Close"))
        self.close_btn.clicked.connect(self.close)

        bottom.addWidget(self.save_all_btn)
        bottom.addWidget(self.close_btn)
        root.addLayout(bottom)

    def _clear_rows(self) -> None:
        for row in self.row_widgets[:]:
            self._remove_row_widget(row, persist=False)
        self.row_widgets.clear()

    def _load_from_plugin(self) -> None:
        self._clear_rows()
        commands = self.plugin._get_chat_commands(dict(self.plugin._settings or {}))
        if not commands:
            commands = [{
                "enabled": True,
                "command": "!cp",
                "target_backend": "obs",
                "obs_hotkey": "",
                "allowed_users": "",
            }]
        for item in commands:
            self._add_row(item)

    def _insert_before_stretch(self, widget: QtWidgets.QWidget) -> None:
        idx = max(0, self.container_layout.count() - 1)
        self.container_layout.insertWidget(idx, widget)

    def _add_row(self, data: dict[str, Any] | None = None) -> None:
        row = _CommandRowWidget(data=data, parent=self.container, language=self.language)
        row.test_requested.connect(self._test_single_row)
        row.save_requested.connect(self._save_single_row)
        row.delete_requested.connect(self._delete_single_row)
        self.row_widgets.append(row)
        self._insert_before_stretch(row)

    def _add_empty_row(self) -> None:
        self._add_row({
            "enabled": True,
            "command": "",
            "target_backend": "obs",
            "obs_hotkey_name": "",
            "allowed_users": "",
        })

    def _remove_row_widget(self, row: _CommandRowWidget, *, persist: bool) -> None:
        if row in self.row_widgets:
            self.row_widgets.remove(row)
        row.setParent(None)
        row.deleteLater()
        if persist:
            self._save_all()

    def _delete_single_row(self, row: _CommandRowWidget) -> None:
        self._remove_row_widget(row, persist=True)

    def _validate_row(self, data: dict[str, Any]) -> str | None:
        if not str(data.get("command", "") or "").strip():
            return _tr(self.language, "Bitte einen Befehl eintragen.")
        target_backend = str(data.get("target_backend", "obs") or "obs").strip().lower()
        action_value = str(data.get("obs_hotkey", data.get("obs_hotkey_name", "")) or "").strip()
        if not action_value:
            if target_backend == "meld":
                return _tr(self.language, "Bitte einen Meld-Command eintragen.")
            return _tr(self.language, "Bitte eine OBS-Tastenkombi eintragen.")
        return None

    def _test_single_row(self, row: _CommandRowWidget) -> None:
        data = row.get_data()
        error = self._validate_row(data)
        if error:
            QtWidgets.QMessageBox.warning(self, _tr(self.language, "Fehlt"), error)
            return
        ok, detail = self.plugin._test_chat_command_action(self.host or self.plugin._host, data)
        backend = str(data.get('target_backend', 'obs') or 'obs').strip().lower()
        title = ("Meld-Test erfolgreich" if ok else "Meld-Test fehlgeschlagen") if backend == 'meld' else ("OBS-Test erfolgreich" if ok else "OBS-Test fehlgeschlagen")
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(detail)
        box.setIcon(QtWidgets.QMessageBox.Icon.Information if ok else QtWidgets.QMessageBox.Icon.Warning)
        box.exec()

    def _save_single_row(self, row: _CommandRowWidget) -> None:
        data = row.get_data()
        error = self._validate_row(data)
        if error:
            QtWidgets.QMessageBox.warning(self, _tr(self.language, "Fehlt"), error)
            return
        self._persist_current_rows()
        if self.host and hasattr(self.host, "log"):
            self.host.log(self.plugin.plugin_id, f"Saved chat command: {data.get('command', '')}")

    def _collect_rows(self) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        for row in self.row_widgets:
            data = row.get_data()
            if not any([
                data.get("command"),
                data.get("target_backend"),
                data.get("obs_hotkey"),
                data.get("obs_hotkey_name"),
                data.get("allowed_users"),
            ]):
                continue
            commands.append({
                "enabled": bool(data.get("enabled", True)),
                "command": str(data.get("command", "") or "").strip(),
                "target_backend": str(data.get("target_backend", "obs") or "obs").strip().lower(),
                "obs_hotkey": str(data.get("obs_hotkey", data.get("obs_hotkey_name", "")) or "").strip(),
                "allowed_users": str(data.get("allowed_users", "") or "").strip(),
            })
        return commands

    def _persist_current_rows(self) -> None:
        commands = self._collect_rows()
        self.plugin._save_chat_commands(self.host or self.plugin._host, commands)

    def _save_all(self) -> None:
        self._persist_current_rows()
        if self.host and hasattr(self.host, "log"):
            self.host.log(self.plugin.plugin_id, "Saved all chat commands.")


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
            raise RuntimeError('Meld websocket handshake failed')

        accept = self._extract_header(response, b'Sec-WebSocket-Accept')
        expected = base64.b64encode(
            hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()
        )
        if accept != expected:
            raise RuntimeError('Meld websocket handshake validation failed')

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
            raise RuntimeError('Meld websocket is not connected')

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

    def recv(self) -> str:
        if self.sock is None:
            raise RuntimeError('Meld websocket is not connected')

        while True:
            opcode, payload = self._read_frame()
            if opcode == 0x1:
                return payload.decode('utf-8', 'replace')
            if opcode == 0x8:
                raise RuntimeError('Meld websocket closed the connection')
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode == 0xA:
                continue

    def _read_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise RuntimeError('Meld websocket is not connected')

        data = b''
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise RuntimeError('Meld websocket connection lost')
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


class TikTokChatPlugin(ThreadedPlugin):
    plugin_id = 'tiktok_chat'
    display_name = 'TikTok Chat'
    version = '1.7.8.test-channel-alerts'
    description = 'TikTok chat read/write using central TikTok account data from core.'

    def __init__(self) -> None:
        super().__init__()
        self._pending_alerts: dict[str, _PendingAlert] = {}
        self._pending_lock: asyncio.Lock | None = None
        self._last_viewer_count: int | None = None
        self._last_is_live: bool | None = None
        self._last_valid_live_viewers: int | None = None
        self._last_like_totals: dict[str, int] = {}
        self._host: PluginHost | None = None
        self._chat_commands_window: _ChatCommandsWindow | None = None
        self._recent_songrequest_comment_keys: dict[str, float] = {}
        self._current_session_started_at: float = 0.0
        self._connected_at_monotonic: float = 0.0
        self._initial_comment_grace_seconds: float = 2.5
        self._live_window_opened = False
        self._live_reload_done = False
        self._live_window_last_url = ''
        self.ui_language = 'de'

    def _close_browser_profile_windows(self, profile_dir: str = '', port: int = 0) -> None:
        if os.name != 'nt':
            return
        hints: list[str] = []
        if str(profile_dir or '').strip():
            hints.append(str(profile_dir))
        if port:
            hints.append(f'remote-debugging-port={int(port)}')
        if not hints:
            return
        try:
            cond = ' -or '.join(["$_.CommandLine -like " + repr('*' + h + '*') for h in hints if h])
            cmd = [
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
                f"Get-CimInstance Win32_Process | Where-Object {{ {cond} }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
            ]
            kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'timeout': 3}
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.run(cmd, **kwargs)
        except Exception:
            pass

    def stop(self, *args, **kwargs) -> None:
        close_browser_windows = bool(kwargs.pop('close_browser_windows', False))
        if close_browser_windows:
            settings = self._settings if isinstance(self._settings, dict) else {}
            for account in ('main', 'bot'):
                try:
                    profile = self._account_profile_dir(settings, account)
                    port = self._debug_port(settings, account)
                    self._close_browser_profile_windows(profile, port)
                except Exception:
                    pass
        try:
            super().stop(*args, **kwargs)
        except TypeError:
            super().stop()

    def set_ui_language(self, language: str) -> None:
        self.ui_language = _norm_lang(language)

    def _commands_store_path(self) -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if parent.name.lower() == 'modules':
                return parent.parent / 'data' / self.plugin_id / 'tiktok_chat_commands.json'
        return current.parent / 'data' / 'tiktok_chat_commands.json'

    def _read_commands_store(self) -> list[dict[str, Any]]:
        path = self._commands_store_path()
        try:
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return []

        commands: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                normalized = self._normalize_command_entry(item)
                if normalized is not None:
                    commands.append(normalized)
        return commands

    def _write_commands_store(self, commands: list[dict[str, Any]]) -> None:
        path = self._commands_store_path()
        try:
            path.write_text(json.dumps(commands, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def settings_schema(self):
        # Login/connect data now lives in the main tool under Plattformen/Platforms -> TikTok.
        # Keep this plugin overlay limited to TikTok chat behavior only.
        return [
            {'key': 'enabled', 'label': 'Aktiv', 'type': 'checkbox'},
            {'key': 'aggregate_window_seconds', 'label': 'Alert bundle window (seconds)', 'type': 'number', 'min': 1, 'max': 15, 'step': 1},
            {'key': 'viewer_check_interval_seconds', 'label': 'Viewer check interval (seconds)', 'type': 'number', 'min': 1, 'max': 60, 'step': 1},
            {'key': 'enable_comments', 'label': 'Show chat comments', 'type': 'checkbox'},
            {'key': 'enable_follows', 'label': 'Show follow alerts', 'type': 'checkbox'},
            {'key': 'enable_likes', 'label': 'Show like alerts', 'type': 'checkbox'},
            {'key': 'enable_gifts', 'label': 'Show gift alerts', 'type': 'checkbox'},
            {'key': 'enable_shares', 'label': 'Show share alerts', 'type': 'checkbox'},
            {'key': 'enable_joins', 'label': 'Show join alerts', 'type': 'checkbox'},
            {'key': 'show_comments_in_desktop', 'label': 'Show chat comments in Desktop Overlay', 'type': 'checkbox'},
            {'key': 'show_comments_in_obs', 'label': 'Show chat comments in OBS Capture', 'type': 'checkbox'},
            {'key': 'show_alerts_in_desktop', 'label': 'Show alerts in Desktop Overlay', 'type': 'checkbox'},
            {'key': 'show_alerts_in_obs', 'label': 'Show alerts in OBS Capture', 'type': 'checkbox'},

            {'key': 'enable_chat_commands', 'label': 'Enable chat commands (e.g. !cp)', 'type': 'checkbox'},
            {'key': 'open_main_live_window', 'label': 'Open main TikTok chat window', 'type': 'checkbox'},
            {'key': 'reload_live_window_on_live', 'label': 'Reload chat window when stream starts', 'type': 'checkbox'},

            # Neuer Button für separates Fenster
            {'key': 'open_chat_commands_window', 'label': 'Open Chat Commands Window', 'type': 'button'},
            {'key': 'test_tiktok_sr_export', 'label': 'Test TikTok !sr export', 'type': 'button', 'button_text': 'Test TikTok !sr'},
            {'key': 'test_tiktok_yt_export', 'label': 'Test TikTok !yt export', 'type': 'button', 'button_text': 'Test TikTok !yt'},

            # Unsichtbarer/technischer Speicher
            {'key': 'chat_commands_json', 'label': 'Chat Commands JSON', 'type': 'hidden'},
        ]

    def default_settings(self):
        return {
            'enabled': True,
            'unique_id': '',
            'autoconnect': False,
            'aggregate_window_seconds': 3,
            'viewer_check_interval_seconds': 5,
            'enable_comments': True,
            'enable_follows': True,
            'enable_likes': True,
            'enable_gifts': True,
            'enable_shares': True,
            'enable_joins': True,
            'show_comments_in_desktop': True,
            'show_comments_in_obs': True,
            'show_alerts_in_desktop': True,
            'show_alerts_in_obs': True,
            'enable_chat_commands': False,
            'open_main_live_window': True,
            'reload_live_window_on_live': True,

            # neuer persistenter Speicher
            'chat_commands_json': '[]',

            # Legacy-Kompatibilität
            'cmd1_enabled': True,
            'cmd1_command': '!cp',
            'cmd1_hotkey': '',
            'cmd1_users': '',
            'cmd2_enabled': True,
            'cmd2_command': '',
            'cmd2_hotkey': '',
            'cmd2_users': '',
            'cmd3_enabled': True,
            'cmd3_command': '',
            'cmd3_hotkey': '',
            'cmd3_users': '',
        }

    # --------------------------------------------------------------------------
    # Settings window / button hooks
    # --------------------------------------------------------------------------
    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        if key == 'open_chat_commands_window':
            return self._open_chat_commands_window(host=host, parent=parent)
        if key == 'test_tiktok_sr_export':
            return self._emit_songrequest_export_test(host, '!sr', 'TikTokSrTest', 'https://youtu.be/godisalotachat_tiktok_sr_test')
        if key == 'test_tiktok_yt_export':
            return self._emit_songrequest_export_test(host, '!yt', 'TikTokYtTest', 'https://youtu.be/godisalotachat_tiktok_yt_test')
        return False

    def on_settings_action(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host=host, parent=parent)

    def handle_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host=host, parent=parent)

    def _open_chat_commands_window(self, host: PluginHost | None = None, parent: Any = None) -> bool:
        if not _QT_AVAILABLE:
            return False

        if not isinstance(self._settings, dict):
            self._settings = {}
        if 'chat_commands_json' not in self._settings:
            file_commands = self._read_commands_store()
            if file_commands:
                self._settings['chat_commands_json'] = json.dumps(file_commands, ensure_ascii=False, indent=2)

        if host is not None:
            self._host = host

        parent_widget = parent if isinstance(parent, QtWidgets.QWidget) else None

        if self._chat_commands_window is not None:
            try:
                self._chat_commands_window.raise_()
                self._chat_commands_window.activateWindow()
                self._chat_commands_window.show()
                return True
            except Exception:
                self._chat_commands_window = None

        self._chat_commands_window = _ChatCommandsWindow(self, self._host, parent_widget)
        self._chat_commands_window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)

        def _closed() -> None:
            self._chat_commands_window = None

        self._chat_commands_window.destroyed.connect(_closed)
        self._chat_commands_window.show()
        self._chat_commands_window.raise_()
        self._chat_commands_window.activateWindow()
        return True

    # --------------------------------------------------------------------------
    # Chat command storage helpers
    # --------------------------------------------------------------------------
    def _normalize_command_entry(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        command = str(item.get('command', '') or '').strip()
        hotkey = str(item.get('obs_hotkey', item.get('obs_hotkey_name', item.get('hotkey', ''))) or '').strip()
        users = str(item.get('allowed_users', item.get('users', '')) or '').strip()
        enabled = bool(item.get('enabled', True))
        target_backend = str(item.get('target_backend', item.get('backend', item.get('websocket_target', 'obs'))) or 'obs').strip().lower()

        if target_backend not in {'obs', 'meld'}:
            target_backend = 'obs'

        if not command and not hotkey and not users:
            return None

        return {
            'enabled': enabled,
            'command': command,
            'target_backend': target_backend,
            'obs_hotkey': hotkey,
            'allowed_users': users,
        }

    def _load_chat_commands_from_json(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        raw = settings.get('chat_commands_json', '[]')
        if isinstance(raw, list):
            parsed = raw
        else:
            try:
                parsed = json.loads(str(raw or '[]'))
            except Exception:
                parsed = []

        commands: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            for item in parsed:
                normalized = self._normalize_command_entry(item)
                if normalized is not None:
                    commands.append(normalized)
        return commands

    def _load_legacy_commands(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        for i in range(1, 4):
            enabled = self._setting_enabled(settings, f'cmd{i}_enabled', True)
            command = str(settings.get(f'cmd{i}_command', '') or '').strip()
            hotkey = str(settings.get(f'cmd{i}_hotkey', '') or '').strip()
            users = str(settings.get(f'cmd{i}_users', '') or '').strip()

            if not command and not hotkey and not users:
                continue

            commands.append({
                'enabled': enabled,
                'command': command,
                'target_backend': 'obs',
                'obs_hotkey': hotkey,
                'allowed_users': users,
            })
        return commands

    def _get_chat_commands(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        commands = self._load_chat_commands_from_json(settings)
        if commands:
            return commands

        file_commands = self._read_commands_store()
        if file_commands:
            return file_commands

        return self._load_legacy_commands(settings)

    def _save_chat_commands(self, host: PluginHost | None, commands: list[dict[str, Any]]) -> None:
        cleaned: list[dict[str, Any]] = []
        for item in commands:
            normalized = self._normalize_command_entry(item)
            if normalized is not None:
                cleaned.append(normalized)

        if not isinstance(self._settings, dict):
            self._settings = {}

        self._settings['chat_commands_json'] = json.dumps(cleaned, ensure_ascii=False, indent=2)
        self._write_commands_store(cleaned)

        # Legacy-Felder leeren/angleichen, damit nichts doppelt verwirrt
        for i in range(1, 4):
            self._settings[f'cmd{i}_enabled'] = True
            self._settings[f'cmd{i}_command'] = ''
            self._settings[f'cmd{i}_hotkey'] = ''
            self._settings[f'cmd{i}_users'] = ''

        for idx, item in enumerate(cleaned[:3], start=1):
            self._settings[f'cmd{idx}_enabled'] = bool(item.get('enabled', True))
            self._settings[f'cmd{idx}_command'] = str(item.get('command', '') or '')
            self._settings[f'cmd{idx}_hotkey'] = str(item.get('obs_hotkey', '') or '')
            self._settings[f'cmd{idx}_users'] = str(item.get('allowed_users', '') or '')

        # möglichst viele Host-Varianten abdecken
        if host is not None:
            try:
                if hasattr(host, 'save_plugin_settings'):
                    host.save_plugin_settings(self.plugin_id, dict(self._settings))
                elif hasattr(host, 'update_plugin_settings'):
                    host.update_plugin_settings(self.plugin_id, dict(self._settings))
                elif hasattr(host, 'set_plugin_settings'):
                    host.set_plugin_settings(self.plugin_id, dict(self._settings))
                elif hasattr(host, 'save_settings'):
                    host.save_settings()
            except Exception as exc:
                if hasattr(host, 'log'):
                    host.log(self.plugin_id, f'Failed to persist chat commands: {exc}')

    def _normalize_unique_id(self, value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return ''

        if '://' in text:
            try:
                parsed = urlparse(text)
                path = (parsed.path or '').strip('/')
                if path:
                    first = path.split('/')[0]
                    if first.startswith('@'):
                        first = first[1:]
                    text = first
            except Exception:
                pass

        text = text.strip()
        if text.startswith('@'):
            text = text[1:]
        if '/' in text:
            text = text.split('/', 1)[0]
        if '?' in text:
            text = text.split('?', 1)[0]
        return text.strip()

    def _candidate_unique_ids(self, value: Any) -> list[str]:
        base = self._normalize_unique_id(value)
        candidates: list[str] = []
        for item in (base, base.lower(), base.replace(' ', '')):
            item = (item or '').strip()
            if item and item not in candidates:
                candidates.append(item)
        return candidates

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

    def _merge_platform_settings(self, settings: dict | None, host: PluginHost | None = None) -> dict:
        merged = dict(settings or {})
        platform: dict[str, Any] = {}
        if host is not None:
            try:
                candidate = host.platform_settings('tiktok')
            except Exception:
                candidate = {}
            if isinstance(candidate, dict):
                platform = candidate
        if not platform:
            return merged

        # The main tool owns TikTok connect data. For reading TikTok chat this plugin
        # only needs the creator/main account. URL/profile/browser/debug settings
        # are intentionally not part of this plugin anymore.
        main_account = (
            platform.get('main_account')
            or platform.get('channel')
            or platform.get('unique_id')
            or platform.get('creator_unique_id')
            or merged.get('unique_id')
            or ''
        )
        bot_account = platform.get('bot_account') or platform.get('bot_username') or merged.get('bot_account') or ''

        test_channel_enabled = self._as_bool(
            platform.get('test_channel_enabled'),
            self._as_bool(platform.get('test_enabled'), False),
        )
        test_channel = (
            platform.get('test_channel')
            or platform.get('test_unique_id')
            or platform.get('test_account')
            or ''
        )

        unique_id = self._normalize_unique_id(test_channel if test_channel_enabled and str(test_channel or '').strip() else main_account)
        main_unique_id = self._normalize_unique_id(main_account)
        if unique_id:
            merged['unique_id'] = unique_id
            merged['creator_unique_id'] = unique_id
            merged['active_read_channel'] = unique_id
        if main_unique_id:
            merged['main_unique_id'] = main_unique_id
        merged['test_channel_enabled'] = bool(test_channel_enabled)
        merged['test_channel'] = self._normalize_unique_id(test_channel)
        if bot_account not in (None, ''):
            merged['bot_account'] = self._normalize_unique_id(bot_account)

        merged['read_enabled'] = self._as_bool(platform.get('read_enabled'), True)
        merged['write_enabled'] = self._as_bool(platform.get('write_enabled'), True)
        merged['autoconnect'] = self._as_bool(platform.get('autoconnect'), self._as_bool(merged.get('autoconnect'), False))
        for key in ('live_url', 'resolved_live_url', 'main_profile_dir', 'bot_profile_dir', 'browser_path', 'remote_debug_port', 'bot_remote_debug_port', 'main_login_ok', 'bot_login_ok'):
            value = platform.get(key)
            if value not in (None, ''):
                merged[key] = value
        return merged

    def _live_url_for(self, settings: dict[str, Any], channel: str = '') -> str:
        raw = str(settings.get('resolved_live_url') or settings.get('live_url') or '').strip()
        if raw:
            return raw
        unique_id = self._normalize_unique_id(channel or settings.get('unique_id') or settings.get('creator_unique_id') or '')
        return f'https://www.tiktok.com/@{unique_id}/live' if unique_id else 'https://www.tiktok.com/live'

    def _main_profile_dir(self, settings: dict[str, Any]) -> str:
        raw = str(settings.get('main_profile_dir') or '').strip()
        if raw:
            return raw
        try:
            root = app_root()
            return str(root / 'data' / 'tiktok' / 'main_profile')
        except Exception:
            return str(Path(__file__).resolve().parent / 'data' / 'main_profile')

    def _bot_profile_dir(self, settings: dict[str, Any]) -> str:
        raw = str(settings.get('bot_profile_dir') or '').strip()
        if raw:
            return raw
        try:
            root = app_root()
            return str(root / 'data' / 'tiktok' / 'bot_profile')
        except Exception:
            return str(Path(__file__).resolve().parent / 'data' / 'bot_profile')

    def _account_profile_dir(self, settings: dict[str, Any], account: str) -> str:
        return self._bot_profile_dir(settings) if str(account or '').lower() == 'bot' else self._main_profile_dir(settings)

    def _preferred_viewer_account(self, settings: dict[str, Any]) -> str:
        if self._as_bool(settings.get('bot_login_ok'), False):
            return 'bot'
        if self._as_bool(settings.get('main_login_ok'), False):
            return 'main'
        return 'main'

    def active_account(self) -> str:
        settings = self._settings if isinstance(self._settings, dict) else {}
        return self._preferred_viewer_account(settings)

    def _live_window_lock_path(self, account: str) -> Path:
        try:
            return app_root() / 'data' / 'tiktok' / f'live_window_{account}.lock'
        except Exception:
            return Path(__file__).resolve().parent / 'data' / f'live_window_{account}.lock'

    def _claim_live_window_launch(self, account: str, ttl_seconds: float = 20.0) -> bool:
        path = self._live_window_lock_path(account)
        now = time.time()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                age = now - float(path.stat().st_mtime or 0.0)
                if age < max(2.0, ttl_seconds):
                    return False
                with contextlib.suppress(Exception):
                    path.unlink()
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(now).encode('ascii', errors='ignore'))
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            return False
        except Exception:
            return True

    def _debug_port(self, settings: dict[str, Any], account: str = 'main') -> int:
        key = 'bot_remote_debug_port' if str(account or '').lower() == 'bot' else 'remote_debug_port'
        fallback = 9230 if key == 'bot_remote_debug_port' else 9229
        try:
            port = int(settings.get(key) or fallback)
            return port if 1024 <= port <= 65535 else fallback
        except Exception:
            return fallback

    def _find_browser_exe(self, settings: dict[str, Any]) -> str:
        raw = str(settings.get('browser_path') or '').strip().strip('"')
        if raw and Path(raw).exists():
            return raw
        candidates: list[Path] = []
        for env in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(env)
            if not base:
                continue
            candidates.extend([
                Path(base) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
                Path(base) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
                Path(base) / 'Chromium' / 'Application' / 'chrome.exe',
            ])
        for candidate in candidates:
            try:
                if candidate.exists():
                    return str(candidate)
            except Exception:
                pass
        return ''

    def _open_main_live_window(self, host: PluginHost, settings: dict[str, Any], channel: str = '', reason: str = 'start') -> bool:
        if not self._setting_enabled(settings, 'open_main_live_window', True):
            return False
        url = self._live_url_for(settings, channel)
        viewer_account = self._preferred_viewer_account(settings)
        profile_dir = self._account_profile_dir(settings, viewer_account)
        browser = self._find_browser_exe(settings)
        try:
            port = self._debug_port(settings, viewer_account)
            if self._wait_for_debugger(port, timeout_seconds=2.0 if reason == 'live detected' else 0.6):
                tab = self._find_tiktok_browser_tab(port, channel or settings.get('unique_id') or '')
                if tab is not None:
                    ws_url = str(tab.get('webSocketDebuggerUrl') or '').strip()
                    if ws_url:
                        if reason == 'live detected':
                            # A reload only works when the app window already
                            # happens to be on this creator's live page. During
                            # offline watching it can instead be on TikTok's
                            # generic/live landing page, so explicitly point it
                            # at the detected creator before refreshing content.
                            self._cdp_call(ws_url, 'Page.navigate', {'url': url}, timeout=6.0)
                        else:
                            self._cdp_call(ws_url, 'Page.bringToFront', {}, timeout=3.0)
                        self._live_window_opened = True
                        self._live_window_last_url = url
                        if hasattr(host, 'log'):
                            host.log(self.plugin_id, f'TikTok chat window reused as {viewer_account} ({reason}): {url}')
                        return True
            if reason == 'live detected' and self._live_window_opened:
                if hasattr(host, 'log'):
                    host.log(self.plugin_id, f'TikTok chat window reload skipped; existing {viewer_account} window not reachable via debug port: {url}')
                return False
            if not self._claim_live_window_launch(viewer_account):
                self._live_window_opened = True
                if hasattr(host, 'log'):
                    host.log(self.plugin_id, f'TikTok chat window open suppressed; recent {viewer_account} launch already in progress: {url}')
                return False
            if browser:
                Path(profile_dir).mkdir(parents=True, exist_ok=True)
                args = [
                    browser,
                    f'--user-data-dir={profile_dir}',
                    f'--remote-debugging-port={port}',
                    '--remote-debugging-address=127.0.0.1',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--window-size=1100,900',
                    '--window-position=180,80',
                    '--new-window',
                    f'--app={url}',
                ]
                popen_kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'close_fds': True}
                if os.name == 'nt':
                    popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 1
                    popen_kwargs['startupinfo'] = si
                subprocess.Popen(args, **popen_kwargs)
            else:
                webbrowser.open(url, new=1)
            self._live_window_opened = True
            self._live_window_last_url = url
            if hasattr(host, 'log'):
                host.log(self.plugin_id, f'TikTok chat window opened as {viewer_account} ({reason}): {url}')
            return True
        except Exception as exc:
            if hasattr(host, 'log'):
                host.log(self.plugin_id, f'TikTok chat window open failed ({reason}): {exc}')
            return False

    def _reload_main_live_window_on_live(self, host: PluginHost, channel: str) -> None:
        settings = self._settings if isinstance(self._settings, dict) else {}
        if not self._setting_enabled(settings, 'reload_live_window_on_live', True):
            return
        if self._live_reload_done:
            return
        self._live_reload_done = True
        self._open_main_live_window(host, settings, channel, reason='live detected')

    def _debug_url(self, port: int, suffix: str = 'json') -> str:
        return f'http://127.0.0.1:{port}/{suffix}'

    def _wait_for_debugger(self, port: int, timeout_seconds: float = 8.0) -> bool:
        end = time.time() + max(0.5, timeout_seconds)
        while time.time() < end:
            try:
                with urllib.request.urlopen(self._debug_url(port, 'json/version'), timeout=1):
                    return True
            except Exception:
                time.sleep(0.25)
        return False

    def _tabs(self, port: int) -> list[dict[str, Any]]:
        try:
            with urllib.request.urlopen(self._debug_url(port, 'json'), timeout=2) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '[]')
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _open_debug_tab(self, port: int, url: str) -> bool:
        suffix = 'json/new?' + urllib.request.quote(url, safe=':/?&=%@._-')
        for method in ('PUT', 'GET'):
            try:
                req = urllib.request.Request(self._debug_url(port, suffix), method=method)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    return 200 <= getattr(resp, 'status', 200) < 300
            except Exception:
                pass
        return False

    def _find_tiktok_browser_tab(self, port: int, unique_id: str = '') -> dict[str, Any] | None:
        needle = self._normalize_unique_id(unique_id).lower()
        best = None
        for tab in self._tabs(port):
            url = str(tab.get('url') or '').lower()
            title = str(tab.get('title') or '').lower()
            combined = url + ' ' + title
            if 'tiktok.com' not in combined:
                continue
            if '/live' in url and (not needle or f'@{needle}' in url or needle in combined):
                return tab
            best = tab
        return best

    def _ensure_sender_live_tab(self, settings: dict[str, Any], unique_id: str) -> tuple[bool, str, dict[str, Any] | None]:
        account = self._preferred_viewer_account(settings)
        if account == 'main' and not self._as_bool(settings.get('main_login_ok'), False):
            return False, 'TikTok main account is not logged in.', None
        port = self._debug_port(settings, account)
        url = self._live_url_for(settings, unique_id)
        if not self._wait_for_debugger(port, timeout_seconds=0.7):
            browser = self._find_browser_exe(settings)
            if not browser:
                return False, f'No Chrome/Edge browser found for TikTok {account} chat.', None
            profile_dir = self._account_profile_dir(settings, account)
            try:
                Path(profile_dir).mkdir(parents=True, exist_ok=True)
                args = [
                    browser,
                    f'--user-data-dir={profile_dir}',
                    f'--remote-debugging-port={port}',
                    '--remote-debugging-address=127.0.0.1',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--window-size=1000,850',
                    '--window-position=260,90',
                    '--new-window',
                    f'--app={url}',
                ]
                popen_kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'close_fds': True}
                if os.name == 'nt':
                    popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 1
                    popen_kwargs['startupinfo'] = si
                subprocess.Popen(args, **popen_kwargs)
            except Exception as exc:
                return False, f'TikTok {account} browser could not be opened: {exc}', None
            if not self._wait_for_debugger(port, timeout_seconds=10.0):
                return False, f'TikTok {account} browser debug port is not reachable.', None

        tab = self._find_tiktok_browser_tab(port, unique_id)
        if tab is None:
            self._open_debug_tab(port, url)
            end = time.time() + 8.0
            while time.time() < end and tab is None:
                time.sleep(0.35)
                tab = self._find_tiktok_browser_tab(port, unique_id)
        if tab is None:
            return False, f'TikTok chat tab was not found in {account} browser.', None
        return True, account, tab

    def _ws_send_text(self, sock: socket.socket, text: str) -> None:
        payload = text.encode('utf-8')
        header = bytearray([0x81])
        ln = len(payload)
        if ln < 126:
            header.append(0x80 | ln)
        elif ln < 65536:
            header.append(0x80 | 126)
            header += struct.pack('!H', ln)
        else:
            header.append(0x80 | 127)
            header += struct.pack('!Q', ln)
        mask = os.urandom(4)
        header += mask
        sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _ws_recv_text(self, sock: socket.socket) -> str:
        h = sock.recv(2)
        if len(h) < 2:
            return ''
        b1, b2 = h[0], h[1]
        opcode = b1 & 0x0F
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack('!H', sock.recv(2))[0]
        elif ln == 127:
            ln = struct.unpack('!Q', sock.recv(8))[0]
        if b2 & 0x80:
            mask = sock.recv(4)
            data = sock.recv(ln)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        else:
            data = b''
            while len(data) < ln:
                chunk = sock.recv(ln - len(data))
                if not chunk:
                    break
                data += chunk
        if opcode == 8:
            return ''
        return data.decode('utf-8', errors='replace')

    def _cdp_call(self, ws_url: str, method: str, params: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
        parsed = urlparse(ws_url)
        host = parsed.hostname or '127.0.0.1'
        port = int(parsed.port or 80)
        path = (parsed.path or '/') + (('?' + parsed.query) if parsed.query else '')
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            key = base64.b64encode(os.urandom(16)).decode('ascii')
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host}:{port}\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Key: {key}\r\n'
                'Sec-WebSocket-Version: 13\r\n\r\n'
            )
            sock.sendall(req.encode('ascii'))
            header = b''
            while b'\r\n\r\n' not in header:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                header += chunk
            if b' 101 ' not in header.split(b'\r\n', 1)[0]:
                raise RuntimeError('WebSocket handshake failed: ' + header[:200].decode('utf-8', 'replace'))
            msg = {'id': 1, 'method': method, 'params': params or {}}
            self._ws_send_text(sock, json.dumps(msg, ensure_ascii=False))
            end_time = time.time() + timeout
            while time.time() < end_time:
                frame = self._ws_recv_text(sock)
                if not frame:
                    continue
                data = json.loads(frame)
                if data.get('id') == 1:
                    if data.get('error'):
                        raise RuntimeError(str(data.get('error')))
                    return data
            raise TimeoutError('no CDP response from browser')
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _send_tiktok_chat_js(self, text: str) -> str:
        payload = json.dumps({'text': text}, ensure_ascii=False)
        js = r'''
(async () => {
  const payload = __PAYLOAD__;
  const text = String(payload.text || '').trim();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const lower = v => String(v || '').toLowerCase();
  const visible = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0 && r.width > 4 && r.height > 4 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const isEditable = el => {
    const tag = lower(el.tagName);
    const role = lower(el.getAttribute && el.getAttribute('role'));
    const ce = lower(el.getAttribute && el.getAttribute('contenteditable'));
    return tag === 'textarea' || tag === 'input' || role === 'textbox' || ce === 'true' || ce === 'plaintext-only';
  };
  const all = [];
  const walk = root => {
    try {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let n;
      while ((n = w.nextNode())) {
        all.push(n);
        if (n.shadowRoot) walk(n.shadowRoot);
      }
    } catch(e) {}
  };
  walk(document);
  for (const fr of Array.from(document.querySelectorAll('iframe'))) {
    try { if (fr.contentDocument) walk(fr.contentDocument); } catch(e) {}
  }
  const describe = el => lower([
    el.tagName, el.id, el.className,
    el.getAttribute && el.getAttribute('placeholder'),
    el.getAttribute && el.getAttribute('aria-label'),
    el.getAttribute && el.getAttribute('data-e2e'),
    el.getAttribute && el.getAttribute('data-testid'),
    el.getAttribute && el.getAttribute('role'),
    el.innerText
  ].join(' '));
  let fields = all.filter(el => visible(el) && isEditable(el));
  fields = fields.map(el => {
    const r = el.getBoundingClientRect();
    const d = describe(el);
    let score = 0;
    if (/chat|comment|message|nachricht|kommentar|send/.test(d)) score += 120;
    if (lower(el.tagName) === 'textarea') score += 20;
    if (lower(el.getAttribute && el.getAttribute('contenteditable'))) score += 12;
    score += Math.max(0, r.top) * 0.02;
    return {el, score};
  }).sort((a,b) => b.score - a.score);
  const field = fields.length ? fields[0].el : null;
  if (!field) return {ok:false, detail:'TikTok chat input not found'};
  field.scrollIntoView({block:'center', inline:'nearest'});
  field.click();
  field.focus();
  const tag = lower(field.tagName);
  if (tag === 'input' || tag === 'textarea') {
    const proto = tag === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(field, text); else field.value = text;
  } else {
    try { document.execCommand('selectAll', false, null); document.execCommand('insertText', false, text); } catch(e) {}
    if (!String(field.innerText || field.textContent || '').includes(text)) field.textContent = text;
  }
  for (const ev of ['beforeinput','input','change','keyup']) {
    try { field.dispatchEvent(new InputEvent(ev, {bubbles:true, cancelable:true, inputType:'insertText', data:text})); }
    catch(e) { field.dispatchEvent(new Event(ev, {bubbles:true, cancelable:true})); }
  }
  await sleep(250);
  const buttons = all.concat(Array.from(document.querySelectorAll('button,[role="button"]'))).filter(visible);
  const send = buttons.find(b => {
    const d = describe(b);
    if (/disabled/.test(d) || b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
    return /send|senden|post|chat/.test(d);
  });
  if (send) {
    send.click();
  } else {
    for (const ev of ['keydown','keypress','keyup']) {
      field.dispatchEvent(new KeyboardEvent(ev, {bubbles:true, cancelable:true, key:'Enter', code:'Enter', which:13, keyCode:13}));
    }
  }
  await sleep(700);
  return {ok:true, detail:'TikTok chat message submitted'};
})()
'''
        return js.replace('__PAYLOAD__', payload)

    def _focus_tiktok_chat_js(self) -> str:
        js = r'''
(() => {
  const lower = v => String(v || '').toLowerCase();
  const visible = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0 && r.width > 4 && r.height > 4 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const isEditable = el => {
    const tag = lower(el.tagName);
    const role = lower(el.getAttribute && el.getAttribute('role'));
    const ce = lower(el.getAttribute && el.getAttribute('contenteditable'));
    return tag === 'textarea' || tag === 'input' || role === 'textbox' || ce === 'true' || ce === 'plaintext-only';
  };
  const all = [];
  const walk = root => {
    try {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let n;
      while ((n = w.nextNode())) {
        all.push(n);
        if (n.shadowRoot) walk(n.shadowRoot);
      }
    } catch(e) {}
  };
  walk(document);
  for (const fr of Array.from(document.querySelectorAll('iframe'))) {
    try { if (fr.contentDocument) walk(fr.contentDocument); } catch(e) {}
  }
  const describe = el => lower([
    el.tagName, el.id, el.className,
    el.getAttribute && el.getAttribute('placeholder'),
    el.getAttribute && el.getAttribute('aria-label'),
    el.getAttribute && el.getAttribute('data-e2e'),
    el.getAttribute && el.getAttribute('data-testid'),
    el.getAttribute && el.getAttribute('role'),
    el.innerText
  ].join(' '));
  const fields = all.filter(el => visible(el) && isEditable(el)).map(el => {
    const r = el.getBoundingClientRect();
    const d = describe(el);
    let score = 0;
    if (/chat|comment|message|nachricht|kommentar|send|say something|add comment|kommentieren/.test(d)) score += 120;
    if (lower(el.tagName) === 'textarea') score += 20;
    if (lower(el.getAttribute && el.getAttribute('contenteditable'))) score += 12;
    score += Math.max(0, r.top) * 0.02;
    return {el, score, d};
  }).sort((a,b) => b.score - a.score);
  const picked = fields.length ? fields[0] : null;
  if (!picked) return {ok:false, detail:'TikTok chat input not found'};
  const field = picked.el;
  field.scrollIntoView({block:'center', inline:'nearest'});
  field.click();
  field.focus();
  try { document.execCommand('selectAll', false, null); document.execCommand('delete', false, null); } catch(e) {}
  if (lower(field.tagName) === 'input' || lower(field.tagName) === 'textarea') {
    try {
      const proto = lower(field.tagName) === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) setter.call(field, ''); else field.value = '';
      field.dispatchEvent(new Event('input', {bubbles:true}));
    } catch(e) {}
  }
  return {ok:true, detail:'TikTok chat input focused', descriptor:picked.d.slice(0, 180)};
})()
'''
        return js

    def send_message(self, message: str, settings: dict | None = None, host: PluginHost | None = None) -> tuple[bool, str]:
        final_settings = self._merge_platform_settings(settings or self._settings or {}, host or self._host)
        if not self._as_bool(final_settings.get('write_enabled'), True):
            return False, 'TikTok writing is disabled in Platforms.'
        text = self._normalize_chat_text(message)
        if not text:
            return False, 'TikTok message is empty.'
        if len(text) > 240:
            text = text[:237].rstrip() + '...'
        unique_id = self._normalize_unique_id(final_settings.get('unique_id') or final_settings.get('creator_unique_id') or '')
        if not unique_id:
            return False, 'Missing TikTok main account in Platforms.'
        ok, detail, tab = self._ensure_sender_live_tab(final_settings, unique_id)
        if not ok or not tab:
            return False, detail
        ws_url = str(tab.get('webSocketDebuggerUrl') or '').strip()
        if not ws_url:
            return False, 'TikTok bot browser has no debugger websocket.'
        try:
            result = self._cdp_call(ws_url, 'Runtime.evaluate', {
                'expression': self._focus_tiktok_chat_js(),
                'returnByValue': True,
                'awaitPromise': True,
            }, timeout=10.0)
            value = (((result.get('result') or {}).get('result') or {}).get('value'))
            if not (isinstance(value, dict) and value.get('ok')):
                return False, (value or {}).get('detail') if isinstance(value, dict) else 'TikTok chat input not focused.'
            self._cdp_call(ws_url, 'Input.insertText', {'text': text}, timeout=5.0)
            time.sleep(0.15)
            self._cdp_call(ws_url, 'Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13}, timeout=5.0)
            self._cdp_call(ws_url, 'Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13}, timeout=5.0)
            return True, f'TikTok message sent via {detail} browser.'
        except Exception as exc:
            return False, f'TikTok send failed: {exc}'

    def test_connection(self, settings):
        settings = self._merge_platform_settings(settings, getattr(self, '_host', None))
        if not self._as_bool(settings.get('read_enabled'), True):
            return False, 'TikTok reading is disabled in Platforms.'
        candidates = self._candidate_unique_ids(settings.get('unique_id', ''))
        if not candidates:
            return False, 'Missing TikTok main account in Platforms.'

        async def _check():
            last_error = None
            for candidate in candidates:
                try:
                    client = TikTokChatClient(unique_id=candidate)
                    live = await client.is_live()
                    if live:
                        return True, candidate
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            return False, candidates[0]

        try:
            live, resolved = asyncio.run(_check())
        except Exception as exc:
            return False, f'Creator not reachable right now: {exc}'
        return (True, f'Creator is live/reachable ({resolved}).') if live else (False, 'Creator currently not live or not reachable.')

    def _setting_enabled(self, settings: dict[str, Any], key: str, default: bool = True) -> bool:
        value = settings.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() not in {'0', 'false', 'no', 'off', ''}
        return bool(value)

    def _aggregate_window(self, settings: dict[str, Any]) -> float:
        try:
            value = float(settings.get('aggregate_window_seconds', 3) or 3)
        except Exception:
            value = 3.0
        return max(1.0, min(15.0, value))

    def _viewer_check_interval(self, settings: dict[str, Any]) -> float:
        try:
            value = float(settings.get('viewer_check_interval_seconds', 5) or 5)
        except Exception:
            value = 5.0
        return max(1.0, min(60.0, value))

    def _user_name(self, event: Any) -> str:
        user = getattr(event, 'user', None)
        if user is None:
            return 'unknown'
        for attr in ('nickname', 'unique_id', 'uniqueId', 'display_name', 'name'):
            value = getattr(user, attr, None)
            if value:
                return str(value)
        return 'unknown'

    def _user_handle(self, event: Any) -> str:
        user = getattr(event, 'user', None)
        if user is None:
            return 'unknown'
        for attr in ('unique_id', 'uniqueId', 'sec_uid', 'user_id', 'id'):
            value = getattr(user, attr, None)
            if value:
                return str(value)
        return self._user_name(event).lower()

    def _normalize_chat_text(self, value: Any) -> str:
        if value is None:
            return ''
        text = str(value).replace('\r', ' ').replace('\n', ' ')
        text = ' '.join(text.split())
        return text.strip()

    def _looks_like_placeholder_chat(self, text: str) -> bool:
        s = (text or '').strip()
        if not s:
            return True
        if s in {':', '-', '—', '...', '…'}:
            return True
        return False

    def _extract_text(self, event: Any) -> str:
        for attr in ('comment', 'text', 'message', 'content'):
            value = getattr(event, attr, None)
            if value:
                text = self._normalize_chat_text(value)
                if text and not self._looks_like_placeholder_chat(text):
                    return text
        return ''

    def _is_songrequest_command(self, text: str) -> bool:
        lowered = self._normalize_chat_text(text).lower()
        return lowered == '!sr' or lowered.startswith('!sr ') or lowered == '!yt' or lowered.startswith('!yt ')

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
            'platform': 'tiktok',
            'username': username,
            'text': text,
            'message': text,
            'content': text,
            'comment': text,
            'channel': 'tiktok_export_test',
            'message_type': 'chat',
            'type': 'chat',
            'event_type': 'chat',
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': True,
            'show_in_obs': True,
        })
        after = self._songrequest_export_line_count()
        added = after - before if before >= 0 and after >= 0 else 'unknown'
        with contextlib.suppress(Exception):
            host.log(self.plugin_id, f'SR export test {command}: before={before} after={after} added={added}')
        return True

    def _safe_event_timestamp_value(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            raw = float(value)
        except Exception:
            return None
        if raw <= 0:
            return None
        # TikTok/event libraries may expose seconds, milliseconds, microseconds or ns.
        if raw > 1_000_000_000_000_000:
            raw /= 1_000_000_000.0
        elif raw > 1_000_000_000_000:
            raw /= 1_000_000.0
        elif raw > 10_000_000_000:
            raw /= 1000.0
        return raw

    def _extract_event_timestamp_seconds(self, event: Any) -> float | None:
        for attr in (
            'create_time', 'createTime', 'created_at', 'createdAt', 'timestamp',
            'event_time', 'eventTime', 'msg_time', 'msgTime', 'time', 'time_ms',
        ):
            value = getattr(event, attr, None)
            ts = self._safe_event_timestamp_value(value)
            if ts is not None:
                return ts

        for parent_attr in ('comment', 'message', 'data', 'raw_data'):
            parent = getattr(event, parent_attr, None)
            if parent is None:
                continue
            if isinstance(parent, dict):
                for key in (
                    'create_time', 'createTime', 'created_at', 'createdAt', 'timestamp',
                    'event_time', 'eventTime', 'msg_time', 'msgTime', 'time', 'time_ms',
                ):
                    ts = self._safe_event_timestamp_value(parent.get(key))
                    if ts is not None:
                        return ts
            else:
                for attr in (
                    'create_time', 'createTime', 'created_at', 'createdAt', 'timestamp',
                    'event_time', 'eventTime', 'msg_time', 'msgTime', 'time', 'time_ms',
                ):
                    ts = self._safe_event_timestamp_value(getattr(parent, attr, None))
                    if ts is not None:
                        return ts
        return None

    def _should_skip_stale_initial_comment(self, event: Any, username: str, text: str, host: PluginHost) -> bool:
        session_started_at = float(getattr(self, '_current_session_started_at', 0.0) or 0.0)
        connected_at = float(getattr(self, '_connected_at_monotonic', 0.0) or 0.0)
        if session_started_at <= 0:
            return False

        event_ts = self._extract_event_timestamp_seconds(event)
        if event_ts is not None and event_ts < (session_started_at - 1.0):
            with contextlib.suppress(Exception):
                host.log(self.plugin_id, f'Stale TikTok startup comment suppressed: {username}: {text}')
            return True

        # Some client-library versions do not expose a reliable comment timestamp for
        # replayed/buffered events. During the tiny initial catch-up window we drop
        # timestamp-less comments instead of letting old chat history flood the main
        # tool and botalot bridge again.
        if event_ts is None and connected_at > 0:
            if (time.monotonic() - connected_at) <= float(getattr(self, '_initial_comment_grace_seconds', 2.5) or 2.5):
                with contextlib.suppress(Exception):
                    host.log(self.plugin_id, f'Initial TikTok buffered comment suppressed: {username}: {text}')
                return True
        return False

    def _extract_comment_event_id(self, event: Any) -> str:
        for attr in ('message_id', 'msg_id', 'comment_id', 'event_id', 'id'):
            value = getattr(event, attr, None)
            if value:
                return str(value)
        for parent_attr in ('comment', 'message', 'data'):
            parent = getattr(event, parent_attr, None)
            if parent is None or isinstance(parent, str):
                continue
            for attr in ('id', 'message_id', 'msg_id', 'comment_id', 'event_id'):
                value = getattr(parent, attr, None)
                if value:
                    return str(value)
        return ''

    def _should_skip_duplicate_songrequest_comment(self, event: Any, username: str, text: str, channel: str) -> bool:
        if not self._is_songrequest_command(text):
            return False
        now = time.monotonic()
        old_keys = [key for key, seen_at in self._recent_songrequest_comment_keys.items() if (now - seen_at) > 5.0]
        for key in old_keys:
            self._recent_songrequest_comment_keys.pop(key, None)

        event_id = self._extract_comment_event_id(event)
        if event_id:
            key = f'id:{event_id}'
            ttl = 5.0
        else:
            key = f'fallback:{channel.strip().lower()}|{username.strip().lower()}|{self._normalize_chat_text(text).lower()}'
            ttl = 1.5

        seen_at = self._recent_songrequest_comment_keys.get(key)
        self._recent_songrequest_comment_keys[key] = now
        return seen_at is not None and (now - seen_at) <= ttl

    def _int_from_paths(self, obj: Any, *paths: str, default: int = 1) -> int:
        for path in paths:
            current = obj
            ok = True
            for part in path.split('.'):
                current = getattr(current, part, None)
                if current is None:
                    ok = False
                    break
            if ok:
                try:
                    return int(current)
                except Exception:
                    continue
        return default

    def _like_count(self, event: Any, user_key: str = '') -> int:
        # TikTokLive versions expose LikeEvent fields inconsistently. Some builds
        # expose count=0 while the real delta sits in repeat_count/like_count or
        # inside a dict-like payload. Scan all known delta fields and ignore zero
        # values so one heart never becomes "0 Likes" in al3rtalot/desktop alerts.
        def read_int(path: str) -> int:
            current: Any = event
            for part in path.split('.'):
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = getattr(current, part, None)
                if current is None:
                    return 0
            try:
                value = int(current)
            except Exception:
                return 0
            return value if value > 0 else 0

        delta_paths = (
            'repeat_count', 'repeatCount', 'alert_count', 'event_count',
            'increment', 'delta', 'like_delta', 'likeDelta',
            'data.repeat_count', 'data.repeatCount', 'data.increment', 'data.delta',
        )
        for path in delta_paths:
            value = read_int(path)
            if value > 0:
                return value

        total_paths = (
            'total', 'total_likes', 'totalLikes', 'total_like_count',
            'data.total', 'data.total_likes', 'data.totalLikes', 'data.total_like_count',
        )
        user_key = str(user_key or self._user_handle(event) or '').strip().lower()
        if user_key:
            for path in total_paths:
                total = read_int(path)
                if total <= 0:
                    continue
                previous = int(self._last_like_totals.get(user_key) or 0)
                self._last_like_totals[user_key] = max(previous, total)
                if previous > 0 and total > previous:
                    return total - previous

        fallback_paths = (
            'like_count', 'likeCount', 'count', 'likes',
            'data.like_count', 'data.likeCount', 'data.count', 'data.likes',
        )
        for path in fallback_paths:
            value = read_int(path)
            if value > 0:
                return value
        return 1

    def _debug_like_event_fields(self, host: PluginHost, event: Any, username: str, count: int) -> None:
        parts: list[str] = []
        for path in (
            'count', 'likes', 'likeCount', 'like_count', 'repeat_count',
            'repeatCount', 'alert_count', 'event_count', 'increment', 'delta',
            'total', 'total_likes', 'totalLikes', 'total_like_count',
        ):
            current = event
            ok = True
            for part in path.split('.'):
                current = getattr(current, part, None)
                if current is None:
                    ok = False
                    break
            if ok:
                parts.append(f'{path}={current!r}')
        try:
            host.log(self.plugin_id, f'LIKE event: {username} sent {count} like(s)' + ((' | raw: ' + ', '.join(parts)) if parts else ''))
        except Exception:
            pass

    def _gift_name(self, event: Any) -> str:
        def pick(obj: Any, *attrs: str) -> str:
            for attr in attrs:
                current = obj
                ok = True
                for part in attr.split('.'):
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        current = getattr(current, part, None)
                    if current in (None, ''):
                        ok = False
                        break
                if ok:
                    text = self._normalize_chat_text(current)
                    if text:
                        return text
            return ''

        for source in (
            getattr(event, 'gift', None),
            getattr(event, 'data', None),
            event,
        ):
            if source is None:
                continue
            name = pick(
                source,
                'name',
                'gift_name',
                'giftName',
                'display_name',
                'displayName',
                'label',
                'title',
                'describe',
                'description',
                'info.name',
                'info.gift_name',
                'info.giftName',
                'extended_gift.name',
                'extendedGift.name',
                'gift.name',
                'gift.gift_name',
                'gift.giftName',
            )
            if name:
                return name
        return 'Gift'

    def _gift_id(self, event: Any) -> str:
        for source in (getattr(event, 'gift', None), getattr(event, 'data', None), event):
            if source is None:
                continue
            for attr in ('id', 'gift_id', 'giftId', 'diamond_count', 'diamondCount', 'gift.id', 'gift.gift_id', 'gift.giftId'):
                current = source
                ok = True
                for part in attr.split('.'):
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        current = getattr(current, part, None)
                    if current in (None, ''):
                        ok = False
                        break
                if ok:
                    return str(current)
        return ''

    def _resolve_event_key(self, *candidate_names: str, fallback: str) -> Any:
        lib_name = 'TikTok' + 'Live'
        modules = (f'{lib_name}.events', f'{lib_name}.types.events')
        for module_name in modules:
            try:
                module = __import__(module_name, fromlist=['*'])
            except Exception:
                continue
            for candidate in candidate_names:
                value = getattr(module, candidate, None)
                if value is not None:
                    return value
        return fallback

    def _register_listener(self, client: Any, event_key: Any, handler: Any) -> None:
        try:
            client.add_listener(event_key, handler)
        except Exception:
            client.on(event_key)(handler)

    def _emit_message(
        self,
        host: PluginHost,
        *,
        username: str,
        text: str,
        channel: str,
        message_type: str,
        show_in_desktop: bool,
        show_in_obs: bool,
        extra: dict[str, Any] | None = None,
    ) -> None:
        msg_type = str(message_type or '').strip().lower()
        clean_text_value = self._normalize_chat_text(text)

        # Harte Bremse: leere TikTok-Chatframes duerfen nie als Chat/Bridge/AI
        # weiterlaufen. Die Client-Library liefert je nach Version auch technische Events
        # mit leeren Textfeldern; die sind keine echten Chatnachrichten.
        if msg_type in {'chat', 'message', 'comment'} and not clean_text_value:
            return

        alert_bridge_types = {'tiktok_like', 'tiktok_follow', 'tiktok_gift', 'tiktok_share', 'tiktok_join', 'like', 'follow', 'gift', 'share', 'join'}
        should_bridge_alert = msg_type in alert_bridge_types
        metric_only_event = bool((extra or {}).get('metric_only'))
        should_dispatch_chat = msg_type in {'chat', 'message', 'comment'}
        if not show_in_desktop and not show_in_obs and not should_bridge_alert and not metric_only_event and not should_dispatch_chat:
            return

        # Normal TikTok chat must stay a chat row for the desktop/chat/bridge
        # pipeline, but it must not be normalizable as an al3rtalot event.
        # The host dispatches all platform chat input plugins to command/bridge
        # plugins; al3rtalot also receives that stream. Giving normal comments a
        # non-alert event_type keeps them out of the Alert panel while preserving
        # message_type=chat for botalot/bridg3alot/modalot and the chat UI.
        payload_event_type = 'chat_no_alert' if msg_type in {'chat', 'message', 'comment'} else message_type
        payload = {
            'platform': 'tiktok',
            'username': username,
            'text': clean_text_value,
            'message': clean_text_value,
            'content': clean_text_value,
            'comment': clean_text_value,
            'channel': channel,
            'message_type': message_type,
            'type': message_type,
            'event_type': payload_event_type,
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': show_in_desktop,
            'show_in_obs': show_in_obs,
            'show_in_obs_capture': show_in_obs,
        }
        if extra:
            payload.update(extra)
        skip_direct_bridge = bool(payload.pop('_skip_direct_bridge', False))
        if show_in_desktop or show_in_obs or metric_only_event or should_dispatch_chat:
            host.emit_message(self.plugin_id, payload)
        if should_bridge_alert and not skip_direct_bridge:
            self._emit_al3rtalot_bridge(host, payload)

    def _emit_al3rtalot_bridge(self, host: PluginHost, payload: dict[str, Any]) -> None:
        """Send real TikTok alert events directly to al3rtalot.

        The normal host.emit_message path feeds the desktop/overlay, but this tool
        historically did not dispatch alert messages to other plugins. al3rtalot is
        the central alert consumer, so TikTok events are pushed directly into its
        on_message hook as well.
        """
        alert_plugin = None
        try:
            alert_plugin = self._get_plugin_by_ids('al3rtalot')
        except Exception:
            alert_plugin = None

        if alert_plugin is None:
            with contextlib.suppress(Exception):
                registry = getattr(sys.modules.get('builtins'), '_godisalotachat_plugin_registry', None)
                if isinstance(registry, dict):
                    alert_plugin = registry.get('al3rtalot')

        if alert_plugin is None:
            with contextlib.suppress(Exception):
                host.log(self.plugin_id, 'Direct alert bridge skipped: al3rtalot plugin not found')
            return

        on_message = getattr(alert_plugin, 'on_message', None)
        if not callable(on_message):
            with contextlib.suppress(Exception):
                host.log(self.plugin_id, 'Direct alert bridge skipped: al3rtalot has no on_message')
            return

        try:
            bridge_payload = dict(payload or {})
            bridge_payload['source_plugin_id'] = self.plugin_id
            bridge_payload['direct_bridge'] = True
            bridge_payload.setdefault('platform', 'tiktok')
            on_message(bridge_payload)
        except Exception as exc:
            with contextlib.suppress(Exception):
                host.log(self.plugin_id, f'Direct bridge to al3rtalot failed: {exc}')

    def _bridge_alert_event(
        self,
        host: PluginHost,
        *,
        username: str,
        text: str,
        channel: str,
        message_type: str,
        count: int = 1,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Immediate TikTok -> al3rtalot bridge for alert actions.

        This runs before the alert bundler. The bundler is still used for desktop
        overlay output, but Meld actions must not wait until TikTok likes stop.
        """
        try:
            c = max(1, int(count or 1))
        except Exception:
            c = 1
        display_text = text.format(count=c) if isinstance(text, str) else str(text or '')
        payload: dict[str, Any] = {
            'platform': 'tiktok',
            'username': username,
            'text': display_text,
            'message': display_text,
            'content': display_text,
            'comment': display_text,
            'channel': channel,
            'message_type': message_type,
            'type': message_type,
            'event_type': message_type,
            'source_plugin_id': self.plugin_id,
            'direct_bridge': True,
            'alert_count': c,
            'event_count': c,
            'increment': c,
            'count': c,
        }
        if extra:
            payload.update(extra)

        # Keep all counter aliases positive after extra payload merge. al3rtalot
        # uses different keys depending on event type/version; a raw zero from
        # TikTokLive must not overwrite the normalized count.
        for key in ('alert_count', 'event_count', 'increment', 'count'):
            payload[key] = c
        if message_type in {'tiktok_like', 'like'}:
            payload['likes'] = c
            payload['like_count'] = c
            payload['likeCount'] = c
        elif message_type in {'tiktok_gift', 'gift'}:
            payload['gift_count'] = c

        self._emit_al3rtalot_bridge(host, payload)

    def _emit_viewer_count(self, host: PluginHost, channel: str, viewer_count: int, *, force: bool = False) -> None:
        viewer_count = max(0, int(viewer_count))
        self._last_viewer_count = viewer_count
        if viewer_count > 0:
            self._last_valid_live_viewers = viewer_count
        self._emit_message(
            host,
            username='',
            text=str(viewer_count),
            channel=channel,
            message_type='viewer_count',
            show_in_desktop=True,
            show_in_obs=True,
            extra={
                'metric_only': True,
                'viewer_count': viewer_count,
            },
        )

    def _emit_is_live(self, host: PluginHost, channel: str, is_live: bool, *, force: bool = False) -> None:
        # Live status is a metric for the shared viewer display. Keep it out
        # of emit_message (which older hosts treated as an empty chat row), but
        # publish it through the dedicated metric channel like Twitch/Kick.
        try:
            host.emit_metric(self.plugin_id, {
                'platform': 'tiktok',
                'channel': channel,
                'message_type': 'is_live',
                'is_live': bool(is_live),
                'metric_only': True,
            })
        except Exception:
            pass

        if not force and self._last_is_live is is_live:
            return
        self._last_is_live = is_live
        if is_live:
            self._reload_main_live_window_on_live(host, channel)
        else:
            self._live_reload_done = False

        # Nicht ueber host.emit_message senden: das Main-Tool macht daraus eine
        # ChatMessage mit leerem Text. Genau dadurch entstehen die leeren TikTok-
        # Zeilen, besonders beim Offline-Watching. botalot bekommt den Live-Status
        # weiterhin direkt, damit der Live-Reload erhalten bleibt.
        self._notify_botalot_is_live(host, channel, bool(is_live))

    def _notify_botalot_is_live(self, host: PluginHost, channel: str, is_live: bool) -> None:
        botalot_plugin = None
        try:
            botalot_plugin = self._get_plugin_by_ids('botalot')
        except Exception:
            botalot_plugin = None

        if botalot_plugin is None:
            with contextlib.suppress(Exception):
                registry = getattr(sys.modules.get('builtins'), '_godisalotachat_plugin_registry', None)
                if isinstance(registry, dict):
                    botalot_plugin = registry.get('botalot')

        on_message = getattr(botalot_plugin, 'on_message', None) if botalot_plugin is not None else None
        if not callable(on_message):
            return

        payload = SimpleNamespace(
            platform='tiktok',
            username='',
            text='',
            message='',
            content='',
            comment='',
            channel=str(channel or '').strip(),
            message_type='is_live',
            type='is_live',
            event_type='is_live',
            source_plugin_id=self.plugin_id,
            source=self.plugin_id,
            is_live=bool(is_live),
            live=bool(is_live),
            show_in_desktop=False,
            show_in_obs=False,
            metric_only=True,
        )
        try:
            on_message(payload)
        except Exception as exc:
            with contextlib.suppress(Exception):
                host.log(self.plugin_id, f'Direct is_live bridge to botalot failed: {exc}')

    def _coerce_viewer_count(self, candidate: int | None, *, is_live_hint: bool | None) -> int | None:
        if candidate is None:
            return self._last_viewer_count
        candidate = max(0, int(candidate))
        if candidate == 0 and is_live_hint and isinstance(self._last_valid_live_viewers, int) and self._last_valid_live_viewers > 0:
            return self._last_valid_live_viewers
        return candidate

    def _get_attr_or_key(self, obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _walk_value(self, obj: Any, path: str) -> Any:
        current = obj
        for part in path.split('.'):
            current = self._get_attr_or_key(current, part)
            if current is None:
                return None
        return current

    def _safe_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    def _parse_json_maybe(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                return None
        return None

    def _extract_viewer_count_from_stream_blob(self, container: Any) -> int | None:
        candidates = (
            'streamData.pull_data.stream_data',
            'stream_data.pull_data.stream_data',
            'hevcStreamData.pull_data.stream_data',
            'hevc_stream_data.pull_data.stream_data',
            'pull_data.stream_data',
            'stream_data',
        )

        for path in candidates:
            raw = self._walk_value(container, path)
            parsed = self._parse_json_maybe(raw)
            if not isinstance(parsed, dict):
                continue

            for inner_path in (
                'common.user_count',
                'common.userCount',
            ):
                value = self._walk_value(parsed, inner_path)
                viewer_count = self._safe_int(value)
                if viewer_count is not None and viewer_count >= 0:
                    return viewer_count
        return None

    def _extract_viewer_count_from_room_info_dict(self, room_info: Any) -> int | None:
        if room_info is None:
            return None

        preferred_paths = (
            'liveRoom.liveRoomStats.userCount',
            'liveRoom.liveRoomStats.user_count',
            'live_room.live_room_stats.user_count',
            'live_room.live_room_stats.userCount',
            'liveRoomStats.userCount',
            'liveRoomStats.user_count',
            'live_room_stats.user_count',
            'live_room_stats.userCount',
            'stats.userCount',
            'stats.user_count',
            'userCount',
            'user_count',
            'viewerCount',
            'viewer_count',
            'roomViewerCount',
            'room_viewer_count',
        )

        for path in preferred_paths:
            value = self._walk_value(room_info, path)
            viewer_count = self._safe_int(value)
            if viewer_count is not None and viewer_count >= 0:
                return viewer_count

        viewer_count = self._extract_viewer_count_from_stream_blob(room_info)
        if viewer_count is not None and viewer_count >= 0:
            return viewer_count

        return None

    def _extract_viewer_count_from_client(self, client: Any) -> int | None:
        sources = [
            getattr(client, 'room_info', None),
            getattr(client, 'webcast_response', None),
            getattr(client, 'initial_room_info', None),
        ]

        for source in sources:
            viewer_count = self._extract_viewer_count_from_room_info_dict(source)
            if viewer_count is not None and viewer_count >= 0:
                return viewer_count

        cached_http_room_info = getattr(client, '_godis_http_room_info', None)
        viewer_count = self._extract_viewer_count_from_room_info_dict(cached_http_room_info)
        if viewer_count is not None and viewer_count >= 0:
            return viewer_count

        return None

    def _extract_viewer_count_from_event(self, event: Any) -> int | None:
        preferred = (
            'viewer_count',
            'room_viewer_count',
            'user_count',
            'viewerCount',
            'roomViewerCount',
            'userCount',
        )
        for key in preferred:
            value = getattr(event, key, None)
            try:
                if value is not None:
                    parsed = int(value)
                    if parsed >= 0:
                        return parsed
            except Exception:
                pass

        for nested_name in ('viewer_stats', 'roomUserSeq', 'room_user_seq'):
            nested = getattr(event, nested_name, None)
            if nested is None:
                continue
            for key in preferred:
                try:
                    value = getattr(nested, key, None)
                    if value is not None:
                        parsed = int(value)
                        if parsed >= 0:
                            return parsed
                except Exception:
                    pass

        viewer_count = self._extract_viewer_count_from_stream_blob(event)
        if viewer_count is not None and viewer_count >= 0:
            return viewer_count

        return None

    async def _fetch_fresh_room_info(self, client: Any) -> Any:
        web_client = getattr(client, 'web', None)
        if web_client is None:
            return None
        fetch_fn = getattr(web_client, 'fetch_room_info', None)
        if fetch_fn is None:
            return None
        try:
            room_info = await fetch_fn()
        except TypeError:
            try:
                room_info = await fetch_fn(client.unique_id)
            except Exception:
                return None
        except Exception:
            return None

        try:
            setattr(client, '_godis_http_room_info', room_info)
        except Exception:
            pass
        return room_info

    async def _fetch_fresh_viewer_count(self, client: Any) -> int | None:
        room_info = await self._fetch_fresh_room_info(client)
        viewer_count = self._extract_viewer_count_from_room_info_dict(room_info)
        if viewer_count is not None:
            return viewer_count
        return self._extract_viewer_count_from_client(client)

    def _message_type_from_alert_key(self, key: str) -> str:
        kind = str(key or '').split(':', 1)[0].strip().lower()
        if kind in {'join', 'like', 'follow', 'gift', 'share'}:
            return f'tiktok_{kind}'
        return 'alert'

    async def _queue_alert(self, key: str, username: str, text: str, channel: str, increment: int = 1, extra: dict[str, Any] | None = None) -> None:
        message_type = self._message_type_from_alert_key(key)
        if self._pending_lock is None:
            self._pending_lock = asyncio.Lock()
        async with self._pending_lock:
            now = time.monotonic()
            existing = self._pending_alerts.get(key)
            if existing is None:
                if len(self._pending_alerts) >= 250:
                    oldest_key = min(self._pending_alerts.items(), key=lambda item: item[1].last_update)[0]
                    self._pending_alerts.pop(oldest_key, None)
                self._pending_alerts[key] = _PendingAlert(
                    username=username,
                    text=text,
                    channel=channel,
                    created_at=now,
                    last_update=now,
                    count=max(1, int(increment)),
                    message_type=message_type,
                    extra=dict(extra or {}),
                )
            else:
                existing.last_update = now
                existing.count += max(1, int(increment))
                existing.text = text
                existing.username = username
                existing.channel = channel
                existing.message_type = message_type
                if extra:
                    existing.extra.update(extra)

    async def _flush_pending_loop(self, host: PluginHost, aggregate_window: float, *, show_in_desktop: bool = True, show_in_obs: bool = True) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(min(aggregate_window, 0.5))
            await self._flush_ready_alerts(host, aggregate_window, force=False, show_in_desktop=show_in_desktop, show_in_obs=show_in_obs)
        await self._flush_ready_alerts(host, aggregate_window, force=True, show_in_desktop=show_in_desktop, show_in_obs=show_in_obs)

    async def _flush_ready_alerts(self, host: PluginHost, aggregate_window: float, force: bool, *, show_in_desktop: bool = True, show_in_obs: bool = True) -> None:
        if self._pending_lock is None:
            return
        ready: list[_PendingAlert] = []
        async with self._pending_lock:
            now = time.monotonic()
            to_delete: list[str] = []
            for key, pending in self._pending_alerts.items():
                if force or (now - pending.last_update) >= aggregate_window:
                    ready.append(pending)
                    to_delete.append(key)
            for key in to_delete:
                self._pending_alerts.pop(key, None)

        for pending in ready:
            text = pending.text.format(count=pending.count)
            extra_payload = dict(pending.extra or {})
            extra_payload.update({
                'alert_count': int(pending.count),
                'event_count': int(pending.count),
                'increment': int(pending.count),
                'count': int(pending.count),
                'likes': int(pending.count) if pending.message_type in {'tiktok_like', 'like'} else None,
                'like_count': int(pending.count) if pending.message_type in {'tiktok_like', 'like'} else None,
                'likeCount': int(pending.count) if pending.message_type in {'tiktok_like', 'like'} else None,
                '_skip_direct_bridge': True,
            })
            self._emit_message(
                host,
                username=pending.username,
                text=text,
                channel=pending.channel,
                message_type=pending.message_type,
                show_in_desktop=show_in_desktop,
                show_in_obs=show_in_obs,
                extra=extra_payload,
            )

    async def _viewer_refresh_loop(self, host: PluginHost, client: Any, channel: str, interval_seconds: float) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(interval_seconds)
            viewer_count = await self._fetch_fresh_viewer_count(client)
            viewer_count = self._coerce_viewer_count(viewer_count, is_live_hint=True)
            if viewer_count is None:
                continue
            self._emit_is_live(host, channel, True)
            self._emit_viewer_count(host, channel, viewer_count)

    def _is_offline_error(self, exc: Exception | None) -> bool:
        if exc is None:
            return False
        text = str(exc or '').strip().lower()
        if not text:
            return False
        offline_markers = (
            ' is offline',
            ' currently offline',
            ' currently not live',
            ' not live',
            ' user is offline',
            ' creator is offline',
            ' requested tiktok ' + 'live user',
        )
        return any(marker in text for marker in offline_markers)

    def _offline_status_text(self, unique_id: str, exc: Exception | None = None) -> str:
        if exc is not None:
            text = str(exc).strip()
            if text:
                lowered = text.lower()
                if ' is offline' in lowered or 'currently offline' in lowered:
                    return text.replace('The requested TikTok ' + 'LIVE user ', '').replace('The requested user ', '')
        return f'@{unique_id} is currently offline.'


    def _is_transient_tiktok_chat_error(self, exc: Exception | None) -> bool:
        if exc is None:
            return False
        text = str(exc or '').strip().lower()
        if not text:
            return False
        transient_markers = (
            'sign_not_200',
            'failed request to sign api',
            'sign api',
            'status code 500',
            'status code 502',
            'status code 503',
            'status code 504',
            '503 error occurred',
            'fetching the webcast url',
            'webcast url',
            'temporarily unavailable',
            'service unavailable',
            'bad gateway',
            'gateway timeout',
            'timeout',
            'timed out',
        )
        return any(marker in text for marker in transient_markers)

    def _transient_status_text(self, unique_id: str, exc: Exception | None = None) -> str:
        raw = str(exc or '').strip()
        if raw:
            compact = ' '.join(raw.split())
            if len(compact) > 180:
                compact = compact[:177] + '...'
            return f'@{unique_id}: TikTok chat sign/webcast service temporarily failed ({compact})'
        return f'@{unique_id}: TikTok chat sign/webcast service temporarily failed.'

    # --------------------------------------------------------------------------
    # Chat Commands (OBS Hotkey Integration)
    # --------------------------------------------------------------------------
    def _is_user_allowed(self, command_config: dict[str, Any], username: str) -> bool:
        allowed_users_raw = command_config.get('allowed_users', '')
        if not allowed_users_raw:
            return True
        allowed = [u.strip().lower() for u in str(allowed_users_raw).split(',') if u.strip()]
        return username.lower() in allowed

    def _find_plugin_in_container(self, container: Any, plugin_ids: set[str], display_names: set[str]) -> Any:
        if container is None:
            return None

        if isinstance(container, dict):
            for plugin_id in plugin_ids:
                plugin = container.get(plugin_id)
                if plugin is not None:
                    return plugin
            iterable = container.values()
        elif isinstance(container, (list, tuple, set)):
            iterable = container
        else:
            return None

        for plugin in iterable:
            plugin_id = str(getattr(plugin, 'plugin_id', '') or '').strip().lower()
            display_name = str(getattr(plugin, 'display_name', '') or '').strip().lower()
            if plugin_id in plugin_ids or display_name in display_names:
                return plugin

        return None

    def _get_plugin_by_ids(self, *plugin_ids: str) -> Any:
        normalized_ids = {str(x or '').strip().lower() for x in plugin_ids if str(x or '').strip()}
        normalized_names = {x.replace('_', ' ').strip().lower() for x in normalized_ids}
        host_candidates = [
            self._host,
            getattr(self, 'host', None),
            getattr(self, '_plugin_host', None),
        ]

        seen_hosts: set[int] = set()
        for host in host_candidates:
            if host is None:
                continue

            host_id = id(host)
            if host_id in seen_hosts:
                continue
            seen_hosts.add(host_id)

            try:
                if hasattr(host, 'get_plugin'):
                    for plugin_id in normalized_ids:
                        plugin = host.get_plugin(plugin_id)
                        if plugin is not None:
                            return plugin

                direct_containers = (
                    getattr(host, 'plugins', None),
                    getattr(host, '_plugins', None),
                    getattr(host, 'loaded_plugins', None),
                    getattr(host, '_loaded_plugins', None),
                )

                for container in direct_containers:
                    plugin = self._find_plugin_in_container(container, normalized_ids, normalized_names)
                    if plugin is not None:
                        return plugin

                manager = getattr(host, 'plugin_manager', None)
                if manager is not None:
                    manager_containers = (
                        getattr(manager, 'plugins', None),
                        getattr(manager, '_plugins', None),
                        getattr(manager, 'loaded_plugins', None),
                        getattr(manager, '_loaded_plugins', None),
                    )
                    for container in manager_containers:
                        plugin = self._find_plugin_in_container(container, normalized_ids, normalized_names)
                        if plugin is not None:
                            return plugin
            except Exception:
                continue

        return None

    def _get_meld_plugin(self) -> Any:
        return self._get_plugin_by_ids('meld_control')

    def _get_obs_plugin(self) -> Any:
        return self._get_plugin_by_ids('obs_control')

    def _get_obs_settings(self, obs_plugin: Any) -> dict[str, Any]:
        try:
            settings = dict(getattr(obs_plugin, '_settings', {}) or {})
        except Exception:
            settings = {}
        return settings

    def _request_obs_hotkey_trigger(self, hotkey_value: str) -> tuple[bool, str]:
        obs_plugin = self._get_obs_plugin()
        if obs_plugin is None:
            host_name = type(self._host).__name__ if self._host is not None else 'None'
            return False, f'OBS Control plugin not loaded (host={host_name})'
        if not hasattr(obs_plugin, '_connect') or not hasattr(obs_plugin, '_request'):
            return False, 'OBS Control plugin does not expose OBS request helpers'

        key_id, modifiers, parse_error = self._parse_obs_key_sequence(hotkey_value)
        if parse_error:
            return False, parse_error

        obs_settings = self._get_obs_settings(obs_plugin)
        ws = None
        try:
            ws = obs_plugin._connect(obs_settings)
            obs_plugin._request(ws, 'TriggerHotkeyByKeySequence', {
                'keyId': key_id,
                'keyModifiers': modifiers,
            })
            return True, f"OBS-Tastenkombi '{hotkey_value}' wurde ausgelöst."
        except Exception as exc:
            return False, f'OBS-Hotkey konnte nicht ausgelöst werden: {exc}'
        finally:
            try:
                if ws is not None and hasattr(obs_plugin, '_safe_close'):
                    obs_plugin._safe_close(ws)
            except Exception:
                pass

    def _test_obs_hotkey_command(self, host: PluginHost | None, command_config: dict[str, Any]) -> tuple[bool, str]:
        if host is not None:
            self._host = host
        hotkey_value = str(command_config.get('obs_hotkey', command_config.get('obs_hotkey_name', '')) or '').strip()
        command = str(command_config.get('command', '') or '').strip()
        if not hotkey_value:
            return False, 'Keine OBS-Tastenkombi gesetzt.'
        ok, detail = self._request_obs_hotkey_trigger(hotkey_value)
        log_host = host or self._host
        if log_host is not None and hasattr(log_host, 'log'):
            log_host.log(self.plugin_id, f"Manual OBS test for {command or '[leer]'} -> {hotkey_value}: {detail}")
        return ok, detail

    def _is_obs_available(self) -> tuple[bool, str]:
        try:
            obs_plugin = self._get_obs_plugin()
            if obs_plugin is not None:
                return True, "OBS plugin available"
            return False, "OBS Control plugin not loaded"
        except Exception as e:
            return False, f"OBS check failed: {e}"


    def _get_meld_settings(self, meld_plugin: Any) -> dict[str, Any]:
        try:
            settings = dict(getattr(meld_plugin, '_settings', {}) or {})
        except Exception:
            settings = {}
        return settings

    def _qtwebchannel_exec(self, ws: _SimpleMeldWebSocket, payload: dict[str, Any], response_id: int | None = None) -> dict[str, Any] | None:
        ws.send_text(json.dumps(payload))
        if response_id is None:
            return None

        while True:
            text = ws.recv()
            data = json.loads(text)
            if not isinstance(data, dict):
                continue
            if data.get('type') != 10:
                continue
            if data.get('id') != response_id:
                continue
            return data

    def _meld_connect_and_init(self, meld_settings: dict[str, Any]) -> tuple[_SimpleMeldWebSocket, dict[str, Any]]:
        host_name = str(meld_settings.get('host', '127.0.0.1') or '127.0.0.1').strip()
        port = int(str(meld_settings.get('port', '13376') or '13376').strip())

        ws = _SimpleMeldWebSocket(host_name, port, timeout=4)
        ws.connect()

        try:
            response = self._qtwebchannel_exec(ws, {'type': 3, 'id': 1}, response_id=1)
            if not isinstance(response, dict):
                raise RuntimeError('No WebChannel init response received')

            payload = response.get('data')
            if not isinstance(payload, dict):
                raise RuntimeError('Invalid WebChannel init response')

            meld_obj = payload.get('meld')
            if not isinstance(meld_obj, dict):
                raise RuntimeError('WebChannel connected, but no "meld" object was published')

            return ws, meld_obj
        except Exception:
            try:
                ws.close()
            except Exception:
                pass
            raise

    def _find_meld_method_index(self, meld_obj: dict[str, Any], method_names: list[str]) -> int | None:
        raw = meld_obj.get('methods')
        if not isinstance(raw, list):
            return None

        for wanted in method_names:
            wanted_norm = wanted.strip()
            for item in raw:
                if isinstance(item, list) and len(item) >= 2:
                    name = str(item[0] or '').strip()
                    idx = item[1]
                    if name == wanted_norm:
                        try:
                            return int(idx)
                        except Exception:
                            return None
        return None

    def _call_meld_method(self, ws: _SimpleMeldWebSocket, meld_obj: dict[str, Any], method_names: list[str], args: list[Any], response_id: int = 2) -> dict[str, Any] | None:
        method_idx = self._find_meld_method_index(meld_obj, method_names)
        if method_idx is None:
            raise RuntimeError(f"Meld method not found: {method_names[0]}")
        return self._qtwebchannel_exec(
            ws,
            {
                'type': 6,
                'object': 'meld',
                'method': method_idx,
                'args': args,
                'id': response_id,
            },
            response_id=response_id,
        )

    def _parse_meld_scalar(self, value: str) -> Any:
        text = str(value or '').strip()
        if not text:
            return ''
        lowered = text.lower()
        if lowered == 'true':
            return True
        if lowered == 'false':
            return False
        if lowered == 'null':
            return None
        try:
            if text.startswith('{') or text.startswith('['):
                return json.loads(text)
        except Exception:
            pass
        try:
            if '.' in text:
                return float(text)
            return int(text)
        except Exception:
            return text

    def _split_meld_action(self, command_value: str) -> tuple[str, list[str]]:
        text = str(command_value or '').strip()
        if not text:
            raise RuntimeError('Kein Meld-Command gesetzt.')

        if text.endswith('()') and ':' not in text:
            return text[:-2], []
        if ':' not in text:
            return text, []

        name, rest = text.split(':', 1)
        parts: list[str] = []
        current = []
        depth = 0
        for ch in rest:
            if ch == ':' and depth == 0:
                parts.append(''.join(current))
                current = []
                continue
            current.append(ch)
            if ch in '[{':
                depth += 1
            elif ch in ']}':
                depth = max(0, depth - 1)
        parts.append(''.join(current))
        return name, parts

    def _request_meld_action(self, command_value: str) -> tuple[bool, str]:
        meld_plugin = self._get_meld_plugin()
        if meld_plugin is None:
            host_name = type(self._host).__name__ if self._host is not None else 'None'
            return False, f'Meld Control plugin not loaded (host={host_name})'

        meld_settings = self._get_meld_settings(meld_plugin)
        ws = None
        try:
            ws, meld_obj = self._meld_connect_and_init(meld_settings)
            action_name, raw_args = self._split_meld_action(command_value)
            action_norm = action_name.strip()

            if action_norm.startswith('meld.'):
                self._call_meld_method(ws, meld_obj, ['sendCommand(QString)', 'sendCommand'], [action_norm], response_id=2)
                return True, f"Meld-Command '{action_norm}' wurde ausgelöst."

            if action_norm in ('toggleRecord', 'toggleStream', 'showStagedScene'):
                self._call_meld_method(ws, meld_obj, [f'{action_norm}()', action_norm], [], response_id=2)
                return True, f"Meld-Methode '{action_norm}()' wurde ausgelöst."

            if action_norm in ('showScene', 'setStagedScene', 'toggleMute', 'toggleMonitor'):
                if len(raw_args) != 1 or not raw_args[0].strip():
                    return False, f"'{action_norm}' erwartet genau 1 Argument."
                self._call_meld_method(ws, meld_obj, [f'{action_norm}(QString)', action_norm], [raw_args[0].strip()], response_id=2)
                return True, f"Meld-Methode '{action_norm}' wurde ausgelöst."

            if action_norm == 'setMuted':
                if len(raw_args) != 2:
                    return False, "'setMuted' erwartet 2 Argumente: <trackId>:<true|false>."
                self._call_meld_method(ws, meld_obj, ['setMuted(QString,bool)', 'setMuted'], [raw_args[0].strip(), bool(self._parse_meld_scalar(raw_args[1]))], response_id=2)
                return True, "Meld-Methode 'setMuted' wurde ausgelöst."

            if action_norm == 'toggleLayer':
                if len(raw_args) != 2:
                    return False, "'toggleLayer' erwartet 2 Argumente: <sceneId>:<layerId>."
                self._call_meld_method(ws, meld_obj, ['toggleLayer(QString,QString)', 'toggleLayer'], [raw_args[0].strip(), raw_args[1].strip()], response_id=2)
                return True, "Meld-Methode 'toggleLayer' wurde ausgelöst."

            if action_norm == 'toggleEffect':
                if len(raw_args) != 3:
                    return False, "'toggleEffect' erwartet 3 Argumente: <sceneId>:<layerId>:<effectId>."
                self._call_meld_method(ws, meld_obj, ['toggleEffect(QString,QString,QString)', 'toggleEffect'], [raw_args[0].strip(), raw_args[1].strip(), raw_args[2].strip()], response_id=2)
                return True, "Meld-Methode 'toggleEffect' wurde ausgelöst."

            if action_norm == 'setGain':
                if len(raw_args) != 2:
                    return False, "'setGain' erwartet 2 Argumente: <trackId>:<0.0-1.0>."
                self._call_meld_method(ws, meld_obj, ['setGain(QString,double)', 'setGain'], [raw_args[0].strip(), float(raw_args[1].strip())], response_id=2)
                return True, "Meld-Methode 'setGain' wurde ausgelöst."

            if action_norm == 'setProperty':
                if len(raw_args) != 3:
                    return False, "'setProperty' erwartet 3 Argumente: <objectId>:<property>:<value>."
                self._call_meld_method(ws, meld_obj, ['setProperty(QString,QString,QVariant)', 'setProperty'], [raw_args[0].strip(), raw_args[1].strip(), self._parse_meld_scalar(raw_args[2])], response_id=2)
                return True, "Meld-Methode 'setProperty' wurde ausgelöst."

            if action_norm == 'callFunction':
                if len(raw_args) != 2:
                    return False, "'callFunction' erwartet 2 Argumente: <layerId>:<command>."
                self._call_meld_method(ws, meld_obj, ['callFunction(QString,QString)', 'callFunction'], [raw_args[0].strip(), raw_args[1].strip()], response_id=2)
                return True, "Meld-Methode 'callFunction' wurde ausgelöst."

            if action_norm == 'callFunctionWithArgs':
                if len(raw_args) != 3:
                    return False, "'callFunctionWithArgs' erwartet 3 Argumente: <layerId>:<command>:<json-array>."
                try:
                    parsed_args = json.loads(raw_args[2])
                except Exception as exc:
                    return False, f"Ungültige JSON-Args für callFunctionWithArgs: {exc}"
                if not isinstance(parsed_args, list):
                    return False, "Args für callFunctionWithArgs müssen ein JSON-Array sein."
                self._call_meld_method(ws, meld_obj, ['callFunctionWithArgs(QString,QString,QVariantList)', 'callFunctionWithArgs'], [raw_args[0].strip(), raw_args[1].strip(), parsed_args], response_id=2)
                return True, "Meld-Methode 'callFunctionWithArgs' wurde ausgelöst."

            if action_norm == 'sendStreamEvent':
                if len(raw_args) < 1 or not raw_args[0].strip():
                    return False, "'sendStreamEvent' erwartet mindestens 1 Argument: <type>[:<json-payload>]."
                args: list[Any] = [raw_args[0].strip()]
                if len(raw_args) >= 2 and raw_args[1].strip():
                    args.append(self._parse_meld_scalar(raw_args[1]))
                self._call_meld_method(ws, meld_obj, ['sendStreamEvent(QString,QVariant)', 'sendStreamEvent'], args, response_id=2)
                return True, "Meld-Methode 'sendStreamEvent' wurde ausgelöst."

            return False, f"Unbekannte Meld-Aktion: {command_value}"
        except Exception as exc:
            return False, f'Meld-Command konnte nicht ausgelöst werden: {exc}'
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def _test_meld_command(self, host: PluginHost | None, command_config: dict[str, Any]) -> tuple[bool, str]:
        if host is not None:
            self._host = host
        command_value = str(command_config.get('obs_hotkey', command_config.get('obs_hotkey_name', '')) or '').strip()
        command = str(command_config.get('command', '') or '').strip()
        if not command_value:
            return False, 'Kein Meld-Command gesetzt.'
        ok, detail = self._request_meld_action(command_value)
        log_host = host or self._host
        if log_host is not None and hasattr(log_host, 'log'):
            log_host.log(self.plugin_id, f"Manual Meld test for {command or '[leer]'} -> {command_value}: {detail}")
        return ok, detail

    def _is_meld_available(self) -> tuple[bool, str]:
        try:
            meld_plugin = self._get_meld_plugin()
            if meld_plugin is not None:
                return True, 'Meld plugin available'
            return False, 'Meld Control plugin not loaded'
        except Exception as e:
            return False, f"Meld check failed: {e}"

    def _trigger_meld_command(self, command_value: str) -> tuple[bool, str]:
        return self._request_meld_action(command_value)

    def _test_chat_command_action(self, host: PluginHost | None, command_config: dict[str, Any]) -> tuple[bool, str]:
        target_backend = str(command_config.get('target_backend', 'obs') or 'obs').strip().lower()
        if target_backend == 'meld':
            return self._test_meld_command(host, command_config)
        return self._test_obs_hotkey_command(host, command_config)

    def _parse_obs_key_sequence(self, value: str) -> tuple[str | None, dict[str, bool] | None, str | None]:
        text = str(value or '').strip()
        if not text:
            return None, None, 'Empty hotkey.'

        raw_parts = [part.strip() for part in text.replace(' + ', '+').split('+') if part.strip()]
        if not raw_parts:
            return None, None, 'Empty hotkey.'

        modifiers = {
            'shift': False,
            'control': False,
            'alt': False,
            'command': False,
        }

        key_part = None
        for part in raw_parts:
            lowered = part.lower()
            if lowered in ('shift', 'umschalt'):
                modifiers['shift'] = True
            elif lowered in ('ctrl', 'strg', 'control'):
                modifiers['control'] = True
            elif lowered == 'alt':
                modifiers['alt'] = True
            elif lowered in ('cmd', 'command', 'win', 'meta', 'super'):
                modifiers['command'] = True
            elif key_part is None:
                key_part = part
            else:
                return None, None, f"Too many primary keys in hotkey '{text}'."

        if not key_part:
            return None, None, f"Missing primary key in hotkey '{text}'."

        key_norm = key_part.strip().upper()
        special_map = {
            'SPACE': 'OBS_KEY_SPACE',
            'TAB': 'OBS_KEY_TAB',
            'ENTER': 'OBS_KEY_RETURN',
            'RETURN': 'OBS_KEY_RETURN',
            'ESC': 'OBS_KEY_ESCAPE',
            'ESCAPE': 'OBS_KEY_ESCAPE',
            'BACKSPACE': 'OBS_KEY_BACKSPACE',
            'DELETE': 'OBS_KEY_DELETE',
            'DEL': 'OBS_KEY_DELETE',
            'INSERT': 'OBS_KEY_INSERT',
            'INS': 'OBS_KEY_INSERT',
            'HOME': 'OBS_KEY_HOME',
            'END': 'OBS_KEY_END',
            'PAGEUP': 'OBS_KEY_PAGEUP',
            'PGUP': 'OBS_KEY_PAGEUP',
            'PAGEDOWN': 'OBS_KEY_PAGEDOWN',
            'PGDOWN': 'OBS_KEY_PAGEDOWN',
            'LEFT': 'OBS_KEY_LEFT',
            'RIGHT': 'OBS_KEY_RIGHT',
            'UP': 'OBS_KEY_UP',
            'DOWN': 'OBS_KEY_DOWN',
        }

        if len(key_norm) == 1 and 'A' <= key_norm <= 'Z':
            key_id = f'OBS_KEY_{key_norm}'
        elif len(key_norm) == 1 and key_norm.isdigit():
            key_id = f'OBS_KEY_{key_norm}'
        elif key_norm.startswith('F') and key_norm[1:].isdigit() and 1 <= int(key_norm[1:]) <= 24:
            key_id = f'OBS_KEY_{key_norm}'
        else:
            key_id = special_map.get(key_norm)

        if not key_id:
            return None, None, f"Unsupported OBS hotkey '{key_part}'. Use something like Shift+F10 or Ctrl+Alt+F9."

        return key_id, modifiers, None

    def _trigger_obs_hotkey(self, hotkey_value: str) -> tuple[bool, str]:
        return self._request_obs_hotkey_trigger(hotkey_value)

    def _process_chat_command(self, host: PluginHost, username: str, text: str, channel: str) -> None:
        settings = dict(self._settings or {})

        if not self._setting_enabled(settings, 'enable_chat_commands', False):
            return

        text_stripped = text.strip()
        if not text_stripped.startswith('!'):
            return

        parts = text_stripped.split(maxsplit=1)
        cmd = parts[0].lower()

        commands = self._get_chat_commands(settings)

        matching_cmd = None
        for c in commands:
            if c.get('enabled', True) and c.get('command', '').strip().lower() == cmd:
                matching_cmd = c
                break

        if matching_cmd is None:
            return

        if not self._is_user_allowed(matching_cmd, username):
            self._emit_message(
                host,
                username="System",
                text=f"@{username}, du bist nicht berechtigt '{cmd}' zu verwenden.",
                channel=channel,
                message_type="command_response",
                show_in_desktop=True,
                show_in_obs=True,
            )
            return

        target_backend = str(matching_cmd.get('target_backend', 'obs') or 'obs').strip().lower()
        action_value = str(matching_cmd.get('obs_hotkey', matching_cmd.get('obs_hotkey_name', '')) or '').strip()

        if not action_value:
            missing_text = 'keinen konfigurierten Meld-Command' if target_backend == 'meld' else 'keine konfigurierte OBS-Tastenkombi'
            self._emit_message(
                host,
                username="System",
                text=f"@{username}: Befehl '{cmd}' hat {missing_text}.",
                channel=channel,
                message_type="command_response",
                show_in_desktop=True,
                show_in_obs=True,
            )
            return

        if target_backend == 'meld':
            target_ok, target_msg = self._is_meld_available()
            if not target_ok:
                self._emit_message(
                    host,
                    username="System",
                    text=f"@{username}: Meld nicht verfügbar - {target_msg}",
                    channel=channel,
                    message_type="command_response",
                    show_in_desktop=True,
                    show_in_obs=True,
                )
                return
            success, result_msg = self._trigger_meld_command(action_value)
        else:
            target_ok, target_msg = self._is_obs_available()
            if not target_ok:
                self._emit_message(
                    host,
                    username="System",
                    text=f"@{username}: OBS nicht verfügbar - {target_msg}",
                    channel=channel,
                    message_type="command_response",
                    show_in_desktop=True,
                    show_in_obs=True,
                )
                return
            success, result_msg = self._trigger_obs_hotkey(action_value)

        if success:
            self._emit_message(
                host,
                username="System",
                text=f"@{username}: {cmd} wurde ausgeführt!",
                channel=channel,
                message_type="command_response",
                show_in_desktop=True,
                show_in_obs=True,
                extra={"target_backend": target_backend, "action": action_value, "success": True}
            )
            if hasattr(host, 'log'):
                host.log(self.plugin_id, f"Command '{cmd}' by {username} -> {target_backend} '{action_value}'")
        else:
            self._emit_message(
                host,
                username="System",
                text=f"@{username}: Fehler bei '{cmd}' - {result_msg}",
                channel=channel,
                message_type="command_response",
                show_in_desktop=True,
                show_in_obs=True,
                extra={"target_backend": target_backend, "action": action_value, "success": False, "error": result_msg}
            )

    # --------------------------------------------------------------------------
    # End of Chat Commands
    # --------------------------------------------------------------------------

    def run(self, settings, host: PluginHost):
        self._host = host
        settings = self._merge_platform_settings(settings, host)
        try:
            self._settings = dict(settings or {})
        except Exception:
            pass
        if not self._as_bool(settings.get('read_enabled'), True):
            host.set_status(self.plugin_id, PluginStatus('disabled', 'TikTok reading disabled in Platforms'))
            return
        candidates = self._candidate_unique_ids(settings.get('unique_id', ''))
        if not candidates:
            raise RuntimeError('Missing TikTok main account in Platforms.')
        if not self._live_window_opened:
            self._open_main_live_window(host, settings, candidates[0], reason='plugin active')

        autoconnect = self._setting_enabled(settings, 'autoconnect', False)
        aggregate_window = self._aggregate_window(settings)
        viewer_check_interval = self._viewer_check_interval(settings)
        enable_comments = self._setting_enabled(settings, 'enable_comments', True)
        enable_follows = self._setting_enabled(settings, 'enable_follows', True)
        enable_likes = self._setting_enabled(settings, 'enable_likes', True)
        enable_gifts = self._setting_enabled(settings, 'enable_gifts', True)
        enable_shares = self._setting_enabled(settings, 'enable_shares', True)
        enable_joins = self._setting_enabled(settings, 'enable_joins', True)
        show_comments_in_desktop = self._setting_enabled(settings, 'show_comments_in_desktop', True)
        show_comments_in_obs = self._setting_enabled(settings, 'show_comments_in_obs', True)
        show_alerts_in_desktop = self._setting_enabled(settings, 'show_alerts_in_desktop', True)
        show_alerts_in_obs = self._setting_enabled(settings, 'show_alerts_in_obs', True)
        comments_visible_anywhere = enable_comments and (show_comments_in_desktop or show_comments_in_obs)
        alerts_enabled_any = any((enable_follows, enable_likes, enable_gifts, enable_shares, enable_joins))
        alerts_visible_anywhere = (show_alerts_in_desktop or show_alerts_in_obs) and alerts_enabled_any

        async def _wait_for_live_candidate() -> str | None:
            host.set_status(self.plugin_id, PluginStatus('watching', 'Watching for live start'))
            while not self._stop.is_set():
                for candidate in candidates:
                    try:
                        client = TikTokChatClient(unique_id=candidate)
                    except Exception:
                        continue

                    try:
                        is_live = await client.is_live()
                    except Exception:
                        is_live = None

                    if is_live:
                        return candidate

                    self._emit_is_live(host, candidate, False, force=True)

                await asyncio.sleep(viewer_check_interval)
            return None

        async def _run_session(resolved_unique_id: str) -> tuple[str | None, bool]:
            self._pending_alerts.clear()
            self._pending_lock = asyncio.Lock()
            self._last_viewer_count = None
            self._last_is_live = None
            self._last_valid_live_viewers = None

            self._current_session_started_at = time.time()
            self._connected_at_monotonic = 0.0

            client: Any = TikTokChatClient(unique_id=resolved_unique_id)
            flush_task: asyncio.Task | None = None
            task: asyncio.Task | None = None
            viewer_refresh_task: asyncio.Task | None = None
            connected_signal = asyncio.Event()

            connect_event = self._resolve_event_key('ConnectEvent', fallback='connect')
            comment_event = self._resolve_event_key('CommentEvent', fallback='comment')
            follow_event = self._resolve_event_key('FollowEvent', fallback='follow')
            share_event = self._resolve_event_key('ShareEvent', fallback='share')
            join_event = self._resolve_event_key('JoinEvent', fallback='join')
            like_event = self._resolve_event_key('LikeEvent', fallback='like')
            gift_event = self._resolve_event_key('GiftEvent', fallback='gift')
            room_user_seq_event = self._resolve_event_key('RoomUserSeqEvent', fallback='room_user_seq')

            async def _on_connect(event: Any):
                connected_signal.set()
                self._connected_at_monotonic = time.monotonic()
                self._emit_is_live(host, resolved_unique_id, True, force=True)

                viewer_count = await self._fetch_fresh_viewer_count(client)
                if viewer_count is None:
                    viewer_count = self._extract_viewer_count_from_event(event)
                if viewer_count is not None:
                    self._emit_viewer_count(host, resolved_unique_id, viewer_count, force=True)

            async def _on_comment(event: Any):
                username = self._user_name(event)
                text = self._extract_text(event)
                if text and self._should_skip_stale_initial_comment(event, username, text, host):
                    return
                if text and self._should_skip_duplicate_songrequest_comment(event, username, text, resolved_unique_id):
                    with contextlib.suppress(Exception):
                        host.log(self.plugin_id, f'Duplicate TikTok song request event suppressed: {username}: {text}')
                    return
                if text:
                    self._process_chat_command(host, username, text, resolved_unique_id)

                if not comments_visible_anywhere:
                    return
                if not text:
                    return
                self._emit_message(
                    host,
                    username=username,
                    text=text,
                    channel=resolved_unique_id,
                    message_type='chat',
                    show_in_desktop=show_comments_in_desktop,
                    show_in_obs=show_comments_in_obs,
                )

            async def _on_follow(event: Any):
                username = self._user_name(event)
                user_key = self._user_handle(event)
                self._bridge_alert_event(
                    host,
                    username=username,
                    text='followed the stream',
                    channel=resolved_unique_id,
                    message_type='tiktok_follow',
                    count=1,
                    extra={'user_id': user_key, 'unique_id': user_key, 'alert_type': 'follow'},
                )
                if not enable_follows:
                    return
                await self._queue_alert(f'follow:{user_key}', username, 'followed the stream', resolved_unique_id, 1)

            async def _on_share(event: Any):
                username = self._user_name(event)
                user_key = self._user_handle(event)
                self._bridge_alert_event(
                    host,
                    username=username,
                    text='shared the stream',
                    channel=resolved_unique_id,
                    message_type='tiktok_share',
                    count=1,
                    extra={'user_id': user_key, 'unique_id': user_key, 'alert_type': 'share'},
                )
                if not enable_shares:
                    return
                await self._queue_alert(f'share:{user_key}', username, 'shared the stream', resolved_unique_id, 1)

            async def _on_join(event: Any):
                username = self._user_name(event)
                user_key = self._user_handle(event)
                self._bridge_alert_event(
                    host,
                    username=username,
                    text='joined the stream',
                    channel=resolved_unique_id,
                    message_type='tiktok_join',
                    count=1,
                    extra={'user_id': user_key, 'unique_id': user_key, 'alert_type': 'join'},
                )
                if not enable_joins:
                    return
                try:
                    host.log(self.plugin_id, f'JOIN event: {username} joined the stream')
                except Exception:
                    pass
                await self._queue_alert(f'join:{user_key}', username, 'joined the stream', resolved_unique_id, 1)

            async def _on_like(event: Any):
                username = self._user_name(event)
                user_key = self._user_handle(event)
                like_count = self._like_count(event, user_key)
                self._debug_like_event_fields(host, event, username, like_count)
                self._bridge_alert_event(
                    host,
                    username=username,
                    text='sent {count} likes',
                    channel=resolved_unique_id,
                    message_type='tiktok_like',
                    count=like_count,
                    extra={'user_id': user_key, 'unique_id': user_key, 'alert_type': 'like', 'like_count': like_count},
                )
                if not enable_likes:
                    return
                await self._queue_alert(f'like:{user_key}', username, 'sent {count} likes', resolved_unique_id, like_count)

            async def _on_gift(event: Any):
                username = self._user_name(event)
                user_key = self._user_handle(event)
                gift_name = self._gift_name(event)
                gift_id = self._gift_id(event)

                streakable = bool(getattr(getattr(event, 'gift', None), 'streakable', False))
                streaking = bool(getattr(event, 'streaking', False) or getattr(getattr(event, 'gift', None), 'streaking', False))
                repeat_end = self._int_from_paths(event, 'gift.repeat_end', 'repeat_end', default=1)
                if streakable and (streaking or repeat_end == 0):
                    return

                gift_count = self._int_from_paths(event, 'repeat_count', 'gift.repeat_count', default=1)
                self._bridge_alert_event(
                    host,
                    username=username,
                    text=f'sent {{count}} x {gift_name}',
                    channel=resolved_unique_id,
                    message_type='tiktok_gift',
                    count=gift_count,
                    extra={'user_id': user_key, 'unique_id': user_key, 'alert_type': 'gift', 'gift_name': gift_name, 'gift_id': gift_id, 'gift_count': gift_count},
                )
                if not enable_gifts:
                    return
                await self._queue_alert(
                    f'gift:{user_key}:{gift_name.lower()}:{gift_id}',
                    username,
                    f'sent {{count}} x {gift_name}',
                    resolved_unique_id,
                    gift_count,
                    extra={'gift_name': gift_name, 'gift_id': gift_id, 'gift_count': gift_count},
                )

            async def _on_room_user_seq(event: Any):
                viewer_count = self._extract_viewer_count_from_event(event)
                if viewer_count is None:
                    viewer_count = self._extract_viewer_count_from_client(client)
                viewer_count = self._coerce_viewer_count(viewer_count, is_live_hint=True)
                if viewer_count is None:
                    return
                self._emit_is_live(host, resolved_unique_id, True)
                self._emit_viewer_count(host, resolved_unique_id, viewer_count)

            self._register_listener(client, connect_event, _on_connect)
            self._register_listener(client, comment_event, _on_comment)
            self._register_listener(client, follow_event, _on_follow)
            self._register_listener(client, share_event, _on_share)
            self._register_listener(client, join_event, _on_join)
            self._register_listener(client, like_event, _on_like)
            self._register_listener(client, gift_event, _on_gift)
            self._register_listener(client, room_user_seq_event, _on_room_user_seq)
            try:
                self.log('TikTok Chat is running with chat + alert event listeners; al3rtalot receives alert events directly.')
            except Exception:
                pass

            host.set_status(self.plugin_id, PluginStatus('connecting', f'Connecting to {resolved_unique_id}'))
            self._emit_is_live(host, resolved_unique_id, False, force=True)

            flush_task = asyncio.create_task(
                self._flush_pending_loop(
                    host,
                    aggregate_window,
                    show_in_desktop=show_alerts_in_desktop,
                    show_in_obs=show_alerts_in_obs,
                )
            ) if alerts_visible_anywhere else None

            should_watch_again = False
            final_status_text: str | None = None

            try:
                # Keep the connection flow aligned with the central alert pipeline.
                # Some client-library versions fail during connect(fetch_room_info=True)
                # even though the stream can be read normally with a plain connect().
                # We therefore pre-check live status and avoid forcing room-info fetch
                # during the websocket connection itself. Viewer counts are fetched
                # separately after ConnectEvent via _fetch_fresh_viewer_count().
                try:
                    is_live = await client.is_live()
                except Exception as exc:
                    if autoconnect and not self._stop.is_set():
                        self._emit_is_live(host, resolved_unique_id, False, force=True)
                        return f'Connection check failed for @{resolved_unique_id}: {exc}', True
                    raise

                if not is_live:
                    self._emit_is_live(host, resolved_unique_id, False, force=True)
                    if autoconnect and not self._stop.is_set():
                        return f'@{resolved_unique_id} is currently offline.', True
                    return f'@{resolved_unique_id} is currently offline.', False

                task = asyncio.create_task(client.connect())

                connected_announced = False
                while not self._stop.is_set():
                    await asyncio.sleep(0.25)

                    if not connected_announced and connected_signal.is_set():
                        host.set_status(self.plugin_id, PluginStatus('connected', f'Reading {resolved_unique_id}'))
                        connected_announced = True

                        viewer_count = await self._fetch_fresh_viewer_count(client)
                        if viewer_count is not None:
                            self._emit_is_live(host, resolved_unique_id, True, force=True)
                            self._emit_viewer_count(host, resolved_unique_id, viewer_count, force=True)

                        viewer_refresh_task = asyncio.create_task(
                            self._viewer_refresh_loop(
                                host,
                                client,
                                resolved_unique_id,
                                viewer_check_interval,
                            )
                        )

                    if task.done():
                        exc = task.exception()
                        if exc is not None:
                            if self._is_offline_error(exc):
                                self._emit_is_live(host, resolved_unique_id, False, force=True)
                                if autoconnect and not self._stop.is_set():
                                    should_watch_again = True
                                    final_status_text = self._offline_status_text(resolved_unique_id, exc)
                                    break
                                return self._offline_status_text(resolved_unique_id, exc), False

                            if self._is_transient_tiktok_chat_error(exc):
                                self._emit_is_live(host, resolved_unique_id, False, force=True)
                                final_status_text = self._transient_status_text(resolved_unique_id, exc)
                                if hasattr(host, 'log'):
                                    with contextlib.suppress(Exception):
                                        host.log(self.plugin_id, final_status_text)
                                if autoconnect and not self._stop.is_set():
                                    should_watch_again = True
                                    break
                                return final_status_text, False

                            raise exc
                        if autoconnect and not self._stop.is_set():
                            should_watch_again = True
                            final_status_text = f'@{resolved_unique_id} stream ended.'
                        break
            finally:
                if viewer_refresh_task is not None:
                    viewer_refresh_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await viewer_refresh_task
                if flush_task is not None:
                    flush_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await flush_task
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                self._connected_at_monotonic = 0.0
                with contextlib.suppress(Exception):
                    await client.disconnect()

            return final_status_text, should_watch_again

        async def _main():
            last_error: Exception | None = None
            final_status_text: str | None = None

            while not self._stop.is_set():
                resolved_unique_id: str | None = None

                if autoconnect:
                    resolved_unique_id = await _wait_for_live_candidate()
                    if resolved_unique_id is None:
                        break
                else:
                    for candidate in candidates:
                        try:
                            TikTokChatClient(unique_id=candidate)
                            resolved_unique_id = candidate
                            break
                        except Exception as exc:
                            last_error = exc

                    if resolved_unique_id is None:
                        raise RuntimeError(str(last_error or 'Unable to initialize TikTok chat client.'))

                final_status_text, should_watch_again = await _run_session(resolved_unique_id)
                if not autoconnect or not should_watch_again:
                    return final_status_text

                host.set_status(self.plugin_id, PluginStatus('watching', final_status_text or 'Watching for live start'))
                self._emit_is_live(host, resolved_unique_id, False, force=True)

            return final_status_text

        try:
            final_status_text = asyncio.run(_main())
            host.set_status(self.plugin_id, PluginStatus('disconnected', final_status_text or 'Stopped'))
        except Exception as exc:
            if self._is_transient_tiktok_chat_error(exc):
                message = self._transient_status_text(candidates[0] if candidates else 'unknown', exc)
                if hasattr(host, 'log'):
                    with contextlib.suppress(Exception):
                        host.log(self.plugin_id, message)
                host.set_status(self.plugin_id, PluginStatus('watching' if autoconnect else 'error', message))
                return
            raise


def create_plugin():
    return TikTokChatPlugin()
