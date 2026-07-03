from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from .browser_server import RouteHttpServer
except Exception:
    import importlib.util
    _browser_server_path = Path(__file__).with_name("browser_server.py")
    _spec = importlib.util.spec_from_file_location("meld_control_browser_server", _browser_server_path)
    if _spec is None or _spec.loader is None:
        raise
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    RouteHttpServer = _mod.RouteHttpServer

try:
    from PySide6 import QtCore, QtWidgets, QtGui
except Exception:
    QtCore = None
    QtWidgets = None
    QtGui = None

def _norm_lang(value: str | None) -> str:
    lang = str(value or 'de').strip().lower()
    return lang if lang in {'de', 'en'} else 'de'


_I18N = {
    'en': {
        'Meld Browser-Route': 'Meld browser route',
        'Route aktiv': 'Route enabled',
        'Datei': 'File',
        'Datei wählen': 'Choose file',
        'Alle Dateien (*.*)': 'All files (*.*)',
        'Typ': 'Type',
        'z. B. artist -> /artist': 'e.g. artist -> /artist',
        'Text-Browserquelle': 'Text browser source',
        'Farbe': 'Color',
        'Textfarbe': 'Text color',
        'transparent oder #000000': 'transparent or #000000',
        'Transparent': 'Transparent',
        'Hintergrund': 'Background',
        'Schriftart': 'Font family',
        'Schriftgröße': 'Font size',
        'Ausrichtung': 'Alignment',
        'Vertikal': 'Vertical',
        'Schriftstärke': 'Font weight',
        'Die Datei wird nur noch als Browserquelle bereitgestellt. Browser-URL ohne Slash eintragen, also z. B. artist für /artist.': 'The file is served as a browser source only. Enter the browser URL without a slash, e.g. artist for /artist.',
        'Meld Browser-Routen': 'Meld browser routes',
        'Hier legst du fest, welche Datei als Browserquelle bereitgestellt wird. Direkte Meld-Datei-Ausgabe ist entfernt.': 'Set which file is served as a browser source. Direct Meld file output has been removed.',
        'Aktiv': 'Enabled',
        'URL': 'URL',
        'Größe': 'Size',
        'Hinzufügen': 'Add',
        'Bearbeiten': 'Edit',
        'Entfernen': 'Remove',
        'Qt/PySide6 ist nicht verfügbar, Routen-Editor kann nicht geöffnet werden.': 'Qt/PySide6 is not available; the route editor cannot be opened.',
        'Ja': 'Yes',
        'Nein': 'No',
    },
    'de': {
        'Meld browser route': 'Meld Browser-Route',
        'Route enabled': 'Route aktiv',
        'File': 'Datei',
        'Type': 'Typ',
        'Text browser source': 'Text-Browserquelle',
        'Color': 'Farbe',
        'Text color': 'Textfarbe',
        'Background': 'Hintergrund',
        'Font family': 'Schriftart',
        'Font size': 'Schriftgröße',
        'Alignment': 'Ausrichtung',
        'Vertical': 'Vertikal',
        'Font weight': 'Schriftstärke',
        'Meld browser routes': 'Meld Browser-Routen',
        'Enabled': 'Aktiv',
        'Size': 'Größe',
        'Add': 'Hinzufügen',
        'Edit': 'Bearbeiten',
        'Remove': 'Entfernen',
    },
}


def _tr(lang: str | None, text: str) -> str:
    base = str(text or '')
    return _I18N.get(_norm_lang(lang), {}).get(base, base)

from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin


def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'


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

    def send_ping(self, payload: bytes = b'meld') -> None:
        self._send_frame(0x9, payload)

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


class _RouteEditorDialog(QtWidgets.QDialog if QtWidgets is not None else object):
    def __init__(self, route: dict[str, Any] | None = None, parent=None, language: str = "de") -> None:
        if QtWidgets is None:
            raise RuntimeError('Qt is not available')
        super().__init__(parent)
        self.language = _norm_lang(language)
        self.setWindowTitle(_tr(self.language, "Meld Browser-Route"))
        self.resize(780, 540)
        route = dict(route or {})
        root = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        root.addLayout(form)

        self.enabled = QtWidgets.QCheckBox(_tr(self.language, "Route aktiv"))
        self.enabled.setChecked(bool(route.get('enabled', True)))
        form.addRow('', self.enabled)

        file_row = QtWidgets.QHBoxLayout()
        self.file_edit = QtWidgets.QLineEdit(str(route.get('file_path', '') or ''))
        browse_btn = QtWidgets.QPushButton('+')
        browse_btn.setFixedWidth(34)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(browse_btn)
        file_wrap = QtWidgets.QWidget()
        file_wrap.setLayout(file_row)
        form.addRow(_tr(self.language, "Datei"), file_wrap)

        self.value_type = QtWidgets.QComboBox()
        self.value_type.addItems(['text', 'image'])
        idx = self.value_type.findText(str(route.get('value_type', 'text') or 'text'))
        self.value_type.setCurrentIndex(max(0, idx))
        form.addRow(_tr(self.language, "Typ"), self.value_type)

        self.url_slug_edit = QtWidgets.QLineEdit(str(route.get('url_slug', '') or ''))
        self.url_slug_edit.setPlaceholderText(_tr(self.language, "z. B. artist -> /artist"))
        form.addRow('Browser-URL', self.url_slug_edit)

        self.style_group = QtWidgets.QGroupBox(_tr(self.language, "Text-Browserquelle"))
        style_form = QtWidgets.QFormLayout(self.style_group)

        color_row = QtWidgets.QHBoxLayout()
        self.text_color_edit = QtWidgets.QLineEdit(str(route.get('text_color', '#FFFFFF') or '#FFFFFF'))
        self.text_color_edit.setPlaceholderText('#FFFFFF')
        color_btn = QtWidgets.QPushButton(_tr(self.language, "Farbe"))
        color_btn.clicked.connect(self._pick_text_color)
        color_row.addWidget(self.text_color_edit, 1)
        color_row.addWidget(color_btn)
        color_wrap = QtWidgets.QWidget()
        color_wrap.setLayout(color_row)
        style_form.addRow(_tr(self.language, "Textfarbe"), color_wrap)

        bg_row = QtWidgets.QHBoxLayout()
        self.background_edit = QtWidgets.QLineEdit(str(route.get('background_color', 'transparent') or 'transparent'))
        self.background_edit.setPlaceholderText(_tr(self.language, "transparent oder #000000"))
        bg_btn = QtWidgets.QPushButton(_tr(self.language, "Farbe"))
        bg_btn.clicked.connect(self._pick_background_color)
        transparent_btn = QtWidgets.QPushButton(_tr(self.language, "Transparent"))
        transparent_btn.clicked.connect(lambda: self.background_edit.setText('transparent'))
        bg_row.addWidget(self.background_edit, 1)
        bg_row.addWidget(bg_btn)
        bg_row.addWidget(transparent_btn)
        bg_wrap = QtWidgets.QWidget()
        bg_wrap.setLayout(bg_row)
        style_form.addRow(_tr(self.language, "Hintergrund"), bg_wrap)

        self.font_family_combo = QtWidgets.QComboBox()
        self.font_family_combo.setEditable(True)
        font_names = []
        if QtGui is not None:
            try:
                db = QtGui.QFontDatabase()
                font_names = sorted(set(db.families()))
            except Exception:
                font_names = []
        if not font_names:
            font_names = ['Arial', 'Segoe UI', 'Roboto', 'Inter']
        self.font_family_combo.addItems(font_names)
        font_value = str(route.get('font_family', 'Arial') or 'Arial')
        idx = self.font_family_combo.findText(font_value)
        if idx >= 0:
            self.font_family_combo.setCurrentIndex(idx)
        else:
            self.font_family_combo.setEditText(font_value)
        style_form.addRow(_tr(self.language, "Schriftart"), self.font_family_combo)

        self.font_size_spin = QtWidgets.QSpinBox()
        self.font_size_spin.setRange(8, 300)
        self.font_size_spin.setValue(int(route.get('font_size', 48) or 48))
        style_form.addRow(_tr(self.language, "Schriftgröße"), self.font_size_spin)

        self.text_align_combo = QtWidgets.QComboBox()
        self.text_align_combo.addItems(['left', 'center', 'right'])
        align_value = str(route.get('text_align', 'left') or 'left')
        align_idx = self.text_align_combo.findText(align_value)
        self.text_align_combo.setCurrentIndex(max(0, align_idx))
        style_form.addRow(_tr(self.language, "Ausrichtung"), self.text_align_combo)

        self.vertical_align_combo = QtWidgets.QComboBox()
        self.vertical_align_combo.addItems(['top', 'center', 'bottom'])
        v_align_value = str(route.get('vertical_align', 'center') or 'center')
        v_align_idx = self.vertical_align_combo.findText(v_align_value)
        self.vertical_align_combo.setCurrentIndex(max(0, v_align_idx))
        style_form.addRow(_tr(self.language, "Vertikal"), self.vertical_align_combo)

        self.font_weight_combo = QtWidgets.QComboBox()
        self.font_weight_combo.addItems(['normal', 'bold'])
        weight_value = str(route.get('font_weight', 'normal') or 'normal')
        weight_idx = self.font_weight_combo.findText(weight_value)
        self.font_weight_combo.setCurrentIndex(max(0, weight_idx))
        style_form.addRow(_tr(self.language, "Schriftstärke"), self.font_weight_combo)

        root.addWidget(self.style_group)

        help_label = QtWidgets.QLabel(_tr(self.language, "Die Datei wird nur noch als Browserquelle bereitgestellt. Browser-URL ohne Slash eintragen, also z. B. artist für /artist."))
        help_label.setWordWrap(True)
        root.addWidget(help_label)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.value_type.currentTextChanged.connect(self._update_style_visibility)
        self._update_style_visibility()

    def _browse_file(self) -> None:
        if QtWidgets is None:
            return
        start_dir = str(Path(self.file_edit.text().strip() or '.').expanduser().resolve().parent) if self.file_edit.text().strip() else str(Path.cwd())
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, _tr(self.language, "Datei wählen"), start_dir, _tr(self.language, "Alle Dateien (*.*)"))
        if file_path:
            self.file_edit.setText(file_path)

    def _pick_text_color(self) -> None:
        if QtWidgets is None:
            return
        color = QtWidgets.QColorDialog.getColor(parent=self)
        if color.isValid():
            self.text_color_edit.setText(color.name())

    def _pick_background_color(self) -> None:
        if QtWidgets is None:
            return
        color = QtWidgets.QColorDialog.getColor(parent=self)
        if color.isValid():
            self.background_edit.setText(color.name())

    def _update_style_visibility(self, *_args) -> None:
        is_text = (self.value_type.currentText().strip().lower() == 'text')
        self.style_group.setVisible(is_text)

    def value(self) -> dict[str, Any]:
        return {
            'enabled': self.enabled.isChecked(),
            'file_path': self.file_edit.text().strip(),
            'value_type': self.value_type.currentText().strip() or 'text',
            'url_slug': self.url_slug_edit.text().strip().strip('/'),
            'text_color': self.text_color_edit.text().strip() or '#FFFFFF',
            'background_color': self.background_edit.text().strip() or 'transparent',
            'font_family': self.font_family_combo.currentText().strip() or 'Arial',
            'font_size': int(self.font_size_spin.value()),
            'text_align': self.text_align_combo.currentText().strip() or 'left',
            'vertical_align': self.vertical_align_combo.currentText().strip() or 'center',
            'font_weight': self.font_weight_combo.currentText().strip() or 'normal',
        }

class _RouteListDialog(QtWidgets.QDialog if QtWidgets is not None else object):
    def __init__(self, routes: list[dict[str, Any]], parent=None, language: str = "de") -> None:
        if QtWidgets is None:
            raise RuntimeError('Qt is not available')
        super().__init__(parent)
        self.language = _norm_lang(language)
        self.setWindowTitle(_tr(self.language, "Meld Browser-Routen"))
        self.resize(980, 520)
        self._routes = [dict(x) for x in routes]

        root = QtWidgets.QVBoxLayout(self)
        top_note = QtWidgets.QLabel(_tr(self.language, "Hier legst du fest, welche Datei als Browserquelle bereitgestellt wird. Direkte Meld-Datei-Ausgabe ist entfernt."))
        top_note.setWordWrap(True)
        root.addWidget(top_note)

        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([_tr(self.language, x) for x in ["Aktiv", "Datei", "Typ", "URL", "Textfarbe", "Hintergrund", "Font", "Größe", "Align"]])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.table, 1)

        controls = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton(_tr(self.language, "Hinzufügen"))
        edit_btn = QtWidgets.QPushButton(_tr(self.language, "Bearbeiten"))
        remove_btn = QtWidgets.QPushButton(_tr(self.language, "Entfernen"))
        controls.addWidget(add_btn)
        controls.addWidget(edit_btn)
        controls.addWidget(remove_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        add_btn.clicked.connect(self._add_route)
        edit_btn.clicked.connect(self._edit_selected)
        remove_btn.clicked.connect(self._remove_selected)
        self.table.doubleClicked.connect(lambda *_: self._edit_selected())

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._reload_table()

    def _reload_table(self) -> None:
        self.table.setRowCount(len(self._routes))
        for row, route in enumerate(self._routes):
            values = [
                _tr(self.language, "Ja") if bool(route.get("enabled", True)) else _tr(self.language, "Nein"),
                str(route.get('file_path', '') or ''),
                str(route.get('value_type', 'text') or 'text'),
                '/' + str(route.get('url_slug', '') or '').strip().strip('/'),
                str(route.get('text_color', '#FFFFFF') or '#FFFFFF'),
                str(route.get('background_color', 'transparent') or 'transparent'),
                str(route.get('font_family', 'Arial') or 'Arial'),
                str(route.get('font_size', 48) or 48),
                f"{str(route.get('text_align', 'left') or 'left')}/{str(route.get('vertical_align', 'center') or 'center')}",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        self.table.resizeRowsToContents()

    def _selected_index(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._routes):
            return None
        return row

    def _add_route(self) -> None:
        dlg = _RouteEditorDialog(parent=self, language=self.language)
        if dlg.exec() == int(QtWidgets.QDialog.DialogCode.Accepted):
            route = dlg.value()
            if route.get('file_path'):
                self._routes.append(route)
                self._reload_table()

    def _edit_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        dlg = _RouteEditorDialog(self._routes[idx], parent=self, language=self.language)
        if dlg.exec() == int(QtWidgets.QDialog.DialogCode.Accepted):
            self._routes[idx] = dlg.value()
            self._reload_table()

    def _remove_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self._routes.pop(idx)
        self._reload_table()

    def routes(self) -> list[dict[str, Any]]:
        return [dict(x) for x in self._routes]




class MeldControlPlugin(ThreadedPlugin):
    plugin_id = 'meld_control'
    display_name = 'Meld Control'
    version = '1.2.1'
    description = 'Maintains the Meld Studio WebSocket/WebChannel connection and exposes cached session + generic Meld RPC helpers for other plugins.'

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._response_cond = threading.Condition(self._lock)
        self._ws: _SimpleMeldWebSocket | None = None
        self._connected = False
        self._last_detail = 'Disconnected'
        self._session_items: dict[str, dict[str, Any]] = {}
        self._meld_descriptor: dict[str, Any] = {}
        self._meld_methods: dict[str, int] = {}
        self._meld_properties: dict[str, int] = {}
        self._meld_property_indexes: dict[int, str] = {}
        self._next_request_id = 1000
        self._responses: dict[int, dict[str, Any]] = {}
        self._route_last_state: dict[str, tuple[float, str]] = {}
        self._log_throttle_state: dict[str, tuple[float, str]] = {}
        self._last_route_poll_ts = 0.0
        self._browser_server: RouteHttpServer | None = None
        self._browser_server_key: tuple[str, int] | None = None
        self._latest_settings_for_routes: dict[str, Any] = {}
        self._routes_store_path = _main_data_dir(self.plugin_id) / 'file_routes.json'
        self.ui_language = 'de'

    def set_ui_language(self, language: str) -> None:
        self.ui_language = _norm_lang(language)

    def _platform_settings(self, host: PluginHost | None = None) -> dict[str, Any]:
        if host is None or not hasattr(host, 'platform_settings'):
            return {}
        try:
            data = host.platform_settings('meld')
            return dict(data or {}) if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _effective_settings(self, settings: dict[str, Any] | None, host: PluginHost | None = None) -> dict[str, Any]:
        merged = dict(settings or {})
        platform = self._platform_settings(host)
        for key in ('host', 'port', 'autoconnect'):
            if key in platform and platform.get(key) not in (None, ''):
                merged[key] = platform.get(key)
        if 'enabled' in platform:
            merged['platform_enabled'] = platform.get('enabled')
        return merged

    @staticmethod
    def _is_connection_refused(exc: BaseException) -> bool:
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, ConnectionRefusedError):
                return True
            if getattr(current, 'winerror', None) == 10061 or getattr(current, 'errno', None) in {61, 111, 10061}:
                return True
            current = current.__cause__ or current.__context__
        return False


    def _log_throttled(self, host: PluginHost | None, key: str, message: str, interval_seconds: float = 60.0) -> None:
        if host is None:
            return
        now = time.monotonic()
        last_ts, last_message = self._log_throttle_state.get(key, (0.0, ''))
        if message != last_message or (now - last_ts) >= interval_seconds:
            try:
                host.log(self.plugin_id, message)
            except Exception:
                return
            self._log_throttle_state[key] = (now, message)

    def _clear_throttled_log(self, key: str | None = None) -> None:
        if key is None:
            self._log_throttle_state.clear()
            return
        self._log_throttle_state.pop(key, None)


    def _load_routes_from_store(self) -> list[dict[str, Any]]:
        try:
            if self._routes_store_path.exists():
                raw = json.loads(self._routes_store_path.read_text(encoding='utf-8'))
                if isinstance(raw, list):
                    return raw
        except Exception:
            pass
        return []

    def _save_routes_to_store(self, routes: list[dict[str, Any]]) -> None:
        try:
            self._routes_store_path.write_text(json.dumps(routes, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def settings_schema(self) -> list[dict[str, Any]]:
        return [
            {'key': 'log_keepalive', 'label': 'Log keepalive traffic', 'type': 'bool', 'default': False},
            {'key': 'log_methods', 'label': 'Log published Meld methods', 'type': 'bool', 'default': True},
            {'key': 'log_session_updates', 'label': 'Log session updates', 'type': 'bool', 'default': False},
            {'key': 'route_separator', 'label': 'Browser-Routen', 'type': 'separator'},
            {'key': 'route_poll_interval_ms', 'label': 'Browser-Refresh Hinweis (ms)', 'type': 'number', 'default': 700, 'min': 150, 'max': 10000, 'step': 50},
            {'key': 'browser_enable', 'label': 'Lokale Browserquelle aktivieren', 'type': 'bool', 'default': True},
            {'key': 'browser_host', 'label': 'Browserquelle Host', 'default': '127.0.0.1'},
            {'key': 'browser_port', 'label': 'Browserquelle Port', 'type': 'number', 'default': 18766, 'min': 1024, 'max': 65535, 'step': 1},
            {'key': 'route_summary', 'label': 'Aktive Routen', 'type': 'multiline', 'default': '', 'help': 'Wird vom Editor gepflegt. Nicht manuell nötig. Browser-URLs stehen ebenfalls hier.'},
            {'key': 'edit_routes', 'label': 'Datei-Routen bearbeiten', 'type': 'button', 'button_text': 'Datei-Routen bearbeiten'},
            {'key': 'file_routes_json', 'label': 'file_routes_json', 'type': 'hidden', 'default': '[]'},
            {'key': 'host', 'label': 'Meld host', 'type': 'hidden', 'default': '127.0.0.1'},
            {'key': 'port', 'label': 'Meld port', 'type': 'hidden', 'default': '13376'},
            {'key': 'autoconnect', 'label': 'Auto connect', 'type': 'hidden', 'default': True},
        ]

    def default_settings(self) -> dict[str, Any]:
        return {
            'host': '127.0.0.1',
            'port': '13376',
            'autoconnect': True,
            'log_keepalive': False,
            'log_methods': True,
            'log_session_updates': False,
            'route_poll_interval_ms': 700,
            'browser_enable': True,
            'browser_host': '127.0.0.1',
            'browser_port': 18766,
            'route_summary': '',
            'file_routes_json': '[]',
        }

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent=None) -> bool:
        if key != 'edit_routes':
            return False
        if QtWidgets is None:
            if host is not None:
                host.log(self.plugin_id, _tr(self.ui_language, "Qt/PySide6 ist nicht verfügbar, Routen-Editor kann nicht geöffnet werden."))
            return True
        try:
            settings_dialog = parent
            settings_values = {}
            if settings_dialog is not None and hasattr(settings_dialog, 'values'):
                try:
                    settings_values = dict(settings_dialog.values() or {})
                except Exception:
                    settings_values = {}
            if not settings_values:
                settings_values = dict(getattr(self, '_settings', {}) or {})

            routes = self._parse_file_routes(settings_values)
            dlg = _RouteListDialog(routes, parent=parent, language=self.ui_language)
            if dlg.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
                return True

            updated_routes = dlg.routes()
            routes_json = json.dumps(updated_routes, ensure_ascii=False, indent=2)
            merged_settings = dict(settings_values)
            merged_settings['file_routes_json'] = routes_json
            summary = self._routes_summary_text(updated_routes, merged_settings)

            self._save_routes_to_store(updated_routes)
            self._settings = dict(getattr(self, '_settings', {}) or {})
            self._settings['file_routes_json'] = routes_json
            self._settings['route_summary'] = summary
            if settings_dialog is not None:
                if hasattr(settings_dialog, '_hidden_values'):
                    settings_dialog._hidden_values['file_routes_json'] = routes_json
                widgets = getattr(settings_dialog, '_widgets', {}) or {}
                summary_widget = widgets.get('route_summary')
                if summary_widget is not None and hasattr(summary_widget, 'setPlainText'):
                    summary_widget.setPlainText(summary)
                json_widget = widgets.get('file_routes_json')
                if json_widget is not None:
                    if hasattr(json_widget, 'setPlainText'):
                        json_widget.setPlainText(routes_json)
                    elif hasattr(json_widget, 'setText'):
                        json_widget.setText(routes_json)
            if host is not None:
                host.log(self.plugin_id, f'Routen aktualisiert: {len(updated_routes)} Einträge.')
        except Exception as exc:
            if host is not None:
                host.log(self.plugin_id, f'Routen-Editor fehlgeschlagen: {exc}')
        return True

    def _routes_summary_text(self, routes: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> str:
        lines: list[str] = []
        base_url = self._browser_base_url(settings or getattr(self, '_settings', {}) or {})
        browser_enabled = self._bool_setting(settings or getattr(self, '_settings', {}) or {}, 'browser_enable', True)
        for idx, route in enumerate(routes):
            if not bool(route.get('enabled', True)):
                continue
            file_path = str(route.get('file_path', '') or '').strip()
            value_type = str(route.get('value_type', 'text') or 'text').strip()
            slug = str(route.get('url_slug', '') or '').strip().strip('/')
            browser_path = f'/{slug}' if slug else f'/route/{idx}/browser'
            line = f'{value_type}: {Path(file_path).name or file_path}'
            if value_type == 'text':
                line += (
                    f" | Style: {str(route.get('text_color', '#FFFFFF') or '#FFFFFF')}, "
                    f"{str(route.get('font_family', 'Arial') or 'Arial')} {int(route.get('font_size', 48) or 48)}px, "
                    f"{str(route.get('font_weight', 'normal') or 'normal')}, "
                    f"{str(route.get('text_align', 'left') or 'left')}/{str(route.get('vertical_align', 'center') or 'center')}"
                )
            if browser_enabled and base_url:
                line += f' | Browser: {base_url}{browser_path}'
            lines.append(line)
        return '\n'.join(lines)

    def _parse_file_routes(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
        raw = settings.get('file_routes_json', '[]')
        if isinstance(raw, list):
            rows = raw
        else:
            try:
                rows = json.loads(str(raw or '[]'))
            except Exception:
                rows = []
        if not isinstance(rows, list) or not rows:
            rows = self._load_routes_from_store()
        out: list[dict[str, Any]] = []
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            file_path = str(row.get('file_path', '') or '').strip()
            if not file_path:
                continue
            out.append({
                'enabled': bool(row.get('enabled', True)),
                'file_path': file_path,
                'value_type': str(row.get('value_type', 'text') or 'text').strip().lower(),
                'url_slug': str(row.get('url_slug', '') or '').strip().strip('/'),
                'text_color': str(row.get('text_color', '#FFFFFF') or '#FFFFFF').strip() or '#FFFFFF',
                'background_color': str(row.get('background_color', 'transparent') or 'transparent').strip() or 'transparent',
                'font_family': str(row.get('font_family', 'Arial') or 'Arial').strip() or 'Arial',
                'font_size': max(8, min(300, int(float(row.get('font_size', 48) or 48)))),
                'text_align': str(row.get('text_align', 'left') or 'left').strip().lower() or 'left',
                'vertical_align': str(row.get('vertical_align', 'center') or 'center').strip().lower() or 'center',
                'font_weight': str(row.get('font_weight', 'normal') or 'normal').strip().lower() or 'normal',
            })
        return out

    def _browser_base_url(self, settings: dict[str, Any]) -> str:
        if not self._bool_setting(settings, 'browser_enable', True):
            return ''
        host = str(settings.get('browser_host', '127.0.0.1') or '127.0.0.1').strip()
        port = max(1, min(65535, int(float(settings.get('browser_port', 18766) or 18766))))
        return f'http://{host}:{port}'

    def _get_routes_for_http(self) -> list[dict[str, Any]]:
        return self._parse_file_routes(self._latest_settings_for_routes or getattr(self, '_settings', {}) or {})

    def _ensure_browser_server(self, settings: dict[str, Any], host: PluginHost) -> None:
        enabled = self._bool_setting(settings, 'browser_enable', True)
        if not enabled:
            self._stop_browser_server()
            return
        server_host = str(settings.get('browser_host', '127.0.0.1') or '127.0.0.1').strip()
        server_port = max(1, min(65535, int(float(settings.get('browser_port', 18766) or 18766))))
        server_key = (server_host, server_port)
        if self._browser_server is not None and self._browser_server_key == server_key:
            return
        self._stop_browser_server()
        try:
            self._browser_server = RouteHttpServer(server_host, server_port, self._get_routes_for_http, self._read_route_payload, logger=None)
            self._browser_server.start()
            self._browser_server_key = server_key
            host.log(self.plugin_id, f'Browserquelle aktiv: http://{server_host}:{server_port}')
        except Exception as exc:
            self._browser_server = None
            self._browser_server_key = None
            host.log(self.plugin_id, f'Browserquelle konnte nicht gestartet werden: {exc}')

    def _stop_browser_server(self) -> None:
        if self._browser_server is None:
            self._browser_server_key = None
            return
        try:
            self._browser_server.stop()
        finally:
            self._browser_server = None
            self._browser_server_key = None

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        ws = None
        try:
            settings = self._effective_settings(settings, None)
            ws, detail = self._connect_and_verify(settings, None)
            return True, detail
        except Exception as exc:
            if self._is_connection_refused(exc):
                return False, 'Meld ist nicht gestartet oder nicht erreichbar.'
            return False, f'Meld test failed: {exc}'
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def run(self, settings: dict[str, Any], host: PluginHost) -> None:
        settings = self._effective_settings(settings, host)
        if not self._bool_setting(settings, 'platform_enabled', True):
            host.set_status(self.plugin_id, PluginStatus('disconnected', 'Meld disabled in platforms'))
            while not self._stop.wait(0.5):
                pass
            return
        if not self._bool_setting(settings, 'autoconnect', True):
            host.set_status(self.plugin_id, PluginStatus('disconnected', 'Auto connect disabled'))
            while not self._stop.wait(0.5):
                pass
            return

        log_keepalive = self._bool_setting(settings, 'log_keepalive', False)
        log_session_updates = self._bool_setting(settings, 'log_session_updates', False)
        self._latest_settings_for_routes = dict(settings or {})
        self._ensure_browser_server(settings, host)
        self._route_last_state.clear()
        self._last_route_poll_ts = 0.0

        while not self._stop.wait(0.15):
            with self._lock:
                ws = self._ws
                connected = self._connected
                detail = self._last_detail

            if not connected or ws is None:
                try:
                    ws, detail = self._connect_and_verify(settings, host)
                    with self._lock:
                        self._ws = ws
                        self._connected = True
                        self._last_detail = detail
                    host.set_status(self.plugin_id, PluginStatus('connected', detail))
                    self._clear_throttled_log('meld_connecting')
                    self._clear_throttled_log('meld_connect_failed')
                    self._clear_throttled_log('meld_offline')
                except Exception as exc:
                    offline = self._is_connection_refused(exc)
                    status_detail = 'Meld ist nicht gestartet oder nicht erreichbar.' if offline else f'Meld connect failed: {exc}'
                    with self._lock:
                        self._ws = None
                        self._connected = False
                        self._last_detail = status_detail
                    if offline:
                        self._log_throttled(host, 'meld_offline', status_detail, 60.0)
                        host.set_status(self.plugin_id, PluginStatus('disconnected', status_detail))
                    else:
                        self._log_throttled(host, 'meld_connect_failed', status_detail, 60.0)
                        host.set_status(self.plugin_id, PluginStatus('error', status_detail))
                continue

            try:
                msg = ws.recv()
                self._handle_incoming_text_message(msg, host, log_session_updates)
                if log_keepalive:
                    trimmed = msg if len(msg) <= 300 else msg[:300] + ' ...[trimmed]'
                    host.log(self.plugin_id, f'RX keepalive: {trimmed}')
                host.set_status(self.plugin_id, PluginStatus('connected', detail))
            except socket.timeout:
                try:
                    ws.send_ping()
                    host.set_status(self.plugin_id, PluginStatus('connected', detail))
                except Exception as exc:
                    if self._stop.is_set():
                        host.set_status(self.plugin_id, PluginStatus('disconnected', 'Disconnected'))
                        break
                    self._log_throttled(host, 'meld_disconnected_ping', f'Meld disconnected (ping failed): {exc}', 60.0)
                    self._drop_connection()
                    host.set_status(self.plugin_id, PluginStatus('error', f'Meld disconnected: {exc}'))
            except OSError as exc:
                if self._stop.is_set() or getattr(exc, 'winerror', None) == 10038:
                    self._drop_connection()
                    host.set_status(self.plugin_id, PluginStatus('disconnected', 'Disconnected'))
                    if self._stop.is_set():
                        break
                    continue
                self._log_throttled(host, 'meld_disconnected_socket', f'Meld disconnected (socket error): {exc}', 60.0)
                self._drop_connection()
                host.set_status(self.plugin_id, PluginStatus('error', f'Meld disconnected: {exc}'))
            except Exception as exc:
                if self._stop.is_set():
                    self._drop_connection()
                    host.set_status(self.plugin_id, PluginStatus('disconnected', 'Disconnected'))
                    break
                self._log_throttled(host, 'meld_disconnected_recv', f'Meld disconnected (recv failed): {exc}', 60.0)
                self._drop_connection()
                host.set_status(self.plugin_id, PluginStatus('error', f'Meld disconnected: {exc}'))

    def stop(self, *args, **kwargs) -> None:
        super().stop()
        self._stop_browser_server()
        self._drop_connection()

    def disconnect(self) -> None:
        self._drop_connection()

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected and self._ws is not None

    def get_session_items(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._session_items.items()}

    def get_meld_descriptor(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._meld_descriptor)

    def get_meld_methods(self) -> list[str]:
        with self._lock:
            return list(self._meld_methods.keys())

    def get_meld_properties(self) -> list[str]:
        with self._lock:
            return list(self._meld_properties.keys())

    def get_session_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                'items': {k: dict(v) for k, v in self._session_items.items()},
                'descriptor': dict(self._meld_descriptor),
                'methods': list(self._meld_methods.keys()),
                'properties': list(self._meld_properties.keys()),
            }

    def find_session_items(self, item_type: str | None = None, name_contains: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = [(item_id, dict(data)) for item_id, data in self._session_items.items()]

        needle = str(name_contains or '').strip().casefold()
        want_type = str(item_type or '').strip().casefold()

        matches: list[dict[str, Any]] = []
        for item_id, data in items:
            item_name = str(data.get('name', '') or '')
            item_kind = str(data.get('type', '') or '')
            if want_type and item_kind.casefold() != want_type:
                continue
            if needle and needle not in item_name.casefold():
                continue
            row = dict(data)
            row['id'] = item_id
            matches.append(row)
        return matches

    def get_text_layer_candidates(self, name_contains: str | None = None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in self.find_session_items(item_type='layer', name_contains=name_contains):
            keys = {str(k).casefold() for k in item.keys()}
            name_text = str(item.get('name', '') or '').casefold()
            if (
                any(k in keys for k in ('text', 'content', 'value', 'html', 'caption', 'label'))
                or any(token in name_text for token in ('text', 'label', 'caption', 'title', 'name'))
            ):
                candidates.append(item)
        return candidates

    def send_raw_text(self, text: str) -> tuple[bool, str]:
        with self._lock:
            ws = self._ws

        if ws is None:
            return False, 'Meld is not connected'

        try:
            ws.send_text(text)
            return True, 'Sent to Meld'
        except Exception as exc:
            self._drop_connection()
            return False, f'Meld send failed: {exc}'

    def send_json(self, payload: dict[str, Any]) -> tuple[bool, str]:
        try:
            return self.send_raw_text(json.dumps(payload))
        except Exception as exc:
            return False, f'JSON send failed: {exc}'

    def invoke_meld_method(self, method_name: str, args: list[Any] | None = None, timeout: float = 3.0) -> tuple[bool, Any]:
        method_id = None
        clean_name = str(method_name or '').strip()
        with self._lock:
            if not self._connected or self._ws is None:
                return False, 'Meld is not connected'
            method_id = self._resolve_method_id_locked(clean_name)
            if method_id is None:
                return False, f'Unknown Meld method: {clean_name}'
            request_id = self._next_request_id
            self._next_request_id += 1
            ws = self._ws

        payload = {
            'type': 6,
            'object': 'meld',
            'method': method_id,
            'args': list(args or []),
            'id': request_id,
        }

        try:
            ws.send_text(json.dumps(payload))
        except Exception as exc:
            self._drop_connection()
            return False, f'Meld send failed: {exc}'

        return self._wait_for_response(request_id, timeout)

    def send_command(self, command: str, timeout: float = 3.0) -> tuple[bool, Any]:
        return self.invoke_meld_method('sendCommand', [str(command or '')], timeout=timeout)

    def set_session_property(self, object_id: str, property_name: str, value: Any, timeout: float = 3.0) -> tuple[bool, Any]:
        return self.invoke_meld_method('setProperty', [str(object_id), str(property_name), value], timeout=timeout)

    def call_layer_function(self, layer_id: str, command: str, timeout: float = 3.0) -> tuple[bool, Any]:
        return self.invoke_meld_method('callFunction', [str(layer_id), str(command)], timeout=timeout)

    def call_layer_function_with_args(self, layer_id: str, command: str, args: list[Any], timeout: float = 3.0) -> tuple[bool, Any]:
        return self.invoke_meld_method('callFunctionWithArgs', [str(layer_id), str(command), list(args)], timeout=timeout)

    def send_stream_event(self, event_type: str, data: Any = None, timeout: float = 3.0) -> tuple[bool, Any]:
        if data is None:
            return self.invoke_meld_method('sendStreamEvent', [str(event_type)], timeout=timeout)
        return self.invoke_meld_method('sendStreamEvent', [str(event_type), data], timeout=timeout)

    def _poll_file_routes(self, settings: dict[str, Any], host: PluginHost, force: bool = False) -> None:
        self._latest_settings_for_routes = dict(settings or {})
        routes = self._parse_file_routes(settings)
        if not routes:
            return
        interval_ms = max(150, int(float(settings.get('route_poll_interval_ms', 700) or 700)))
        now = time.monotonic()
        if not force and (now - self._last_route_poll_ts) * 1000.0 < interval_ms:
            return
        self._last_route_poll_ts = now
        for idx, route in enumerate(routes):
            if not bool(route.get('enabled', True)):
                continue
            file_path = str(route.get('file_path', '') or '').strip()
            if not file_path:
                continue
            route_key = f'{idx}:{file_path}:{route.get("scene_name", "")}:{route.get("layer_name", "")}'
            path = Path(file_path).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            except Exception as exc:
                host.log(self.plugin_id, f'Route-Datei kann nicht gelesen werden: {path} ({exc})')
                continue
            try:
                payload = self._read_route_payload(path, str(route.get('value_type', 'text') or 'text'))
            except Exception as exc:
                host.log(self.plugin_id, f'Route-Datei konnte nicht verarbeitet werden: {path} ({exc})')
                continue
            state = (float(stat.st_mtime_ns), payload)
            if not force and self._route_last_state.get(route_key) == state:
                continue
            ok, detail = self._send_route_to_meld(route, payload, host)
            if ok:
                self._route_last_state[route_key] = state
                host.log(self.plugin_id, f'Route gesendet: {path.name} -> {route.get("scene_name", "") or "(any scene)"} / {route.get("layer_name", "")}')
            else:
                host.log(self.plugin_id, f'Route fehlgeschlagen: {path.name} -> {route.get("layer_name", "")}: {detail}')

    def _path_to_file_url(self, path: Path) -> str:
        resolved = path.resolve()
        return f"file:///{quote(resolved.as_posix(), safe='/:')}"

    def _read_route_payload(self, path: Path, value_type: str) -> str:
        if value_type == 'image':
            return self._path_to_file_url(path)
        raw = path.read_bytes()
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                return raw.decode(enc).strip()
            except Exception:
                continue
        return raw.decode('utf-8', 'ignore').strip()

    def _send_route_to_meld(self, route: dict[str, Any], payload: str, host: PluginHost) -> tuple[bool, str]:
        return False, 'Direkte Meld-Datei-Ausgabe ist deaktiviert. Bitte Browser-URL verwenden.'

    def _layer_full_path(self, item_id: str, item: dict[str, Any], items: dict[str, dict[str, Any]]) -> str:
        names: list[str] = []
        current_id = str(item_id or '')
        current = dict(item or {})
        leaf = str(current.get('name', '') or '').strip()
        visited: set[str] = set()
        parent_id = str(current.get('parentId') or current.get('parent_id') or current.get('parent') or current.get('groupId') or current.get('group_id') or '')
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = items.get(parent_id)
            if not isinstance(parent, dict):
                break
            ptype = str(parent.get('type', '') or '').strip().casefold()
            if ptype == 'scene':
                break
            pname = str(parent.get('name', '') or '').strip()
            if pname:
                names.append(pname)
            parent_id = str(parent.get('parentId') or parent.get('parent_id') or parent.get('parent') or parent.get('groupId') or parent.get('group_id') or '')
        names.reverse()
        if leaf:
            names.append(leaf)
        collapsed: list[str] = []
        for name in names:
            if collapsed and collapsed[-1].casefold() == name.casefold():
                continue
            collapsed.append(name)
        return '/'.join(collapsed).strip('/')

    def _find_target_layer(self, scene_name: str, layer_name: str) -> dict[str, Any] | None:
        items = self.get_session_items()
        needle_layer = str(layer_name or '').strip().strip('/').casefold()
        needle_leaf = needle_layer.rsplit('/', 1)[-1] if needle_layer else ''
        needle_scene = str(scene_name or '').replace('  [current]', '').strip().casefold()
        if not needle_layer:
            return None

        candidates: list[dict[str, Any]] = []
        for item_id, item in items.items():
            if str(item.get('type', '') or '').casefold() != 'layer':
                continue
            row = dict(item)
            row['id'] = item_id
            row['_full_path'] = self._layer_full_path(str(item_id), row, items)
            candidates.append(row)

        def in_scene(row: dict[str, Any]) -> bool:
            return not needle_scene or self._item_matches_scene(row, needle_scene, items)

        # First exact full path, then legacy leaf-name matching.
        matches = [r for r in candidates if in_scene(r) and str(r.get('_full_path') or '').strip('/').casefold() == needle_layer]
        if matches:
            return matches[0]
        matches = [r for r in candidates if in_scene(r) and str(r.get('name', '') or '').strip().casefold() == needle_leaf]
        if len(matches) == 1:
            return matches[0]
        if matches:
            # Prefer paths that end with the requested leaf.
            for row in matches:
                if str(row.get('_full_path') or '').strip('/').casefold().endswith('/' + needle_leaf):
                    return row
            return matches[0]

        # Last fallback if no scene was found in the snapshot.
        matches = [r for r in candidates if str(r.get('_full_path') or '').strip('/').casefold() == needle_layer]
        if len(matches) == 1:
            return matches[0]
        matches = [r for r in candidates if str(r.get('name', '') or '').strip().casefold() == needle_leaf]
        if len(matches) == 1:
            return matches[0]
        return None

    def _item_matches_scene(self, item: dict[str, Any], scene_name: str, items: dict[str, dict[str, Any]]) -> bool:
        direct_keys = ('scene', 'sceneName', 'scene_name', 'sceneTitle')
        for key in direct_keys:
            if str(item.get(key, '') or '').strip().casefold() == scene_name:
                return True
        queue = [str(item.get(k, '') or '') for k in ('sceneId', 'scene_id', 'parentId', 'parent_id', 'parent', 'groupId', 'group_id', 'ownerId', 'owner_id') if str(item.get(k, '') or '').strip()]
        seen: set[str] = set()
        while queue:
            current = queue.pop(0)
            if not current or current in seen:
                continue
            seen.add(current)
            parent = items.get(current)
            if not isinstance(parent, dict):
                continue
            if str(parent.get('name', '') or '').strip().casefold() == scene_name and str(parent.get('type', '') or '').strip().casefold() == 'scene':
                return True
            for key in direct_keys:
                if str(parent.get(key, '') or '').strip().casefold() == scene_name:
                    return True
            for next_key in ('sceneId', 'scene_id', 'parentId', 'parent_id', 'parent', 'groupId', 'group_id', 'ownerId', 'owner_id'):
                next_id = str(parent.get(next_key, '') or '').strip()
                if next_id and next_id not in seen:
                    queue.append(next_id)
        return False

    def _get_scene_and_layer_names(self) -> tuple[list[str], list[str]]:
        items = self.get_session_items()
        scenes: list[str] = []
        layers: list[str] = []
        for item_id, item in items.items():
            item_type = str(item.get('type', '') or '').strip().casefold()
            name = str(item.get('name', '') or '').strip()
            if not name:
                continue
            if item_type == 'scene':
                scenes.append(name)
            elif item_type == 'layer':
                layers.append(self._layer_full_path(str(item_id), item, items) or name)
        return sorted(set(scenes)), sorted(set(layers))

    def _wait_for_response(self, request_id: int, timeout: float) -> tuple[bool, Any]:
        with self._response_cond:
            ok = self._response_cond.wait_for(
                lambda: request_id in self._responses or not self._connected,
                timeout=timeout,
            )
            if not ok:
                return False, f'Meld response timed out for request {request_id}'
            if request_id not in self._responses:
                return False, 'Meld disconnected before response arrived'
            response = self._responses.pop(request_id)
            return True, response.get('data')

    def _drop_connection(self) -> None:
        with self._response_cond:
            ws = self._ws
            self._ws = None
            self._connected = False
            self._last_detail = 'Disconnected'
            self._session_items = {}
            self._meld_descriptor = {}
            self._meld_methods = {}
            self._meld_properties = {}
            self._meld_property_indexes = {}
            self._responses.clear()
            self._response_cond.notify_all()
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _connect_and_verify(self, settings: dict[str, Any], host: PluginHost | None) -> tuple[_SimpleMeldWebSocket, str]:
        host_name = str(settings.get('host', '127.0.0.1') or '127.0.0.1').strip()
        port = int(str(settings.get('port', '13376') or '13376').strip())
        log_methods = self._bool_setting(settings, 'log_methods', True)

        ws = _SimpleMeldWebSocket(host_name, port, timeout=4)

        if host is not None:
            self._log_throttled(host, 'meld_connecting', f'Connecting to Meld WS {host_name}:{port}...', 60.0)
        ws.connect()

        if ws.sock is not None:
            try:
                ws.sock.settimeout(0.35)
            except Exception:
                pass

        if host is not None:
            host.log(self.plugin_id, 'WebSocket handshake OK.')

        try:
            init_payload = {'type': 3, 'id': 1}
            if host is not None:
                host.log(self.plugin_id, f'Sending WebChannel init: {json.dumps(init_payload)}')
            ws.send_text(json.dumps(init_payload))

            while True:
                text = ws.recv()
                data = json.loads(text)

                if not isinstance(data, dict):
                    continue

                msg_type = data.get('type')
                if msg_type not in (3, 10):
                    continue
                if msg_type == 10 and data.get('id') != 1:
                    continue

                payload = data.get('data')
                if not isinstance(payload, dict):
                    continue

                object_names = sorted(str(k) for k in payload.keys())
                if host is not None:
                    host.log(self.plugin_id, f'Published WebChannel objects: {", ".join(object_names) if object_names else "(none)"}')

                if 'meld' not in payload:
                    raise RuntimeError('WebChannel connected, but no "meld" object was published')

                meld_obj = payload.get('meld')
                detail = 'Connected to Meld'
                session_items: dict[str, dict[str, Any]] = {}
                method_map: dict[str, int] = {}
                property_map: dict[str, int] = {}

                if isinstance(meld_obj, dict):
                    version = meld_obj.get('version')
                    if version not in (None, ''):
                        detail += f' v{version}'

                    method_map = self._build_method_map(meld_obj.get('methods'))
                    property_map, property_indexes = self._build_property_map(meld_obj.get('properties'))

                    extracted_values = self._extract_property_values(meld_obj.get('properties'))
                    session_obj = extracted_values.get('session')
                    if isinstance(session_obj, dict):
                        items = session_obj.get('items')
                        if isinstance(items, dict):
                            session_items = {
                                str(item_id): dict(item_data)
                                for item_id, item_data in items.items()
                                if isinstance(item_data, dict)
                            }

                    if host is not None and log_methods:
                        methods = list(method_map.keys())
                        if methods:
                            host.log(self.plugin_id, f'Published Meld methods: {", ".join(methods)}')

                        properties = list(property_map.keys())
                        if properties:
                            host.log(self.plugin_id, f'Published Meld properties: {", ".join(properties)}')

                        if session_items:
                            host.log(self.plugin_id, f'Cached session items: {len(session_items)}')

                with self._lock:
                    self._meld_descriptor = dict(meld_obj) if isinstance(meld_obj, dict) else {}
                    self._meld_descriptor.update(extracted_values)
                    self._meld_methods = method_map
                    self._meld_properties = property_map
                    self._meld_property_indexes = property_indexes
                    self._session_items = session_items

                if host is not None:
                    host.log(self.plugin_id, detail)
                return ws, detail
        except Exception:
            try:
                ws.close()
            except Exception:
                pass
            raise

    def _handle_incoming_text_message(self, text: str, host: PluginHost | None, log_session_updates: bool) -> None:
        try:
            data = json.loads(text)
        except Exception:
            return

        if not isinstance(data, dict):
            return

        msg_type = data.get('type')

        if msg_type == 10:
            with self._response_cond:
                request_id = data.get('id')
                if isinstance(request_id, int):
                    self._responses[request_id] = data
                    self._response_cond.notify_all()
            return

        if msg_type != 2:
            return

        payload = data.get('data')
        if not isinstance(payload, list):
            return

        session_changed = False

        with self._lock:
            for entry in payload:
                if not isinstance(entry, dict):
                    continue
                if entry.get('object') != 'meld':
                    continue

                signals = entry.get('signals')
                if isinstance(signals, dict):
                    # nothing to do yet, but keep parsing future-safe
                    pass

                properties = entry.get('properties')
                resolved_properties = self._normalize_property_updates(properties)
                if not resolved_properties:
                    continue

                if 'session' in resolved_properties:
                    session = resolved_properties.get('session')
                    if isinstance(session, dict):
                        items = session.get('items')
                        if isinstance(items, dict):
                            self._session_items = {
                                str(item_id): dict(item_data)
                                for item_id, item_data in items.items()
                                if isinstance(item_data, dict)
                            }
                            session_changed = True

                if isinstance(self._meld_descriptor, dict):
                    self._meld_descriptor.update(resolved_properties)

        if session_changed and host is not None and log_session_updates:
            host.log(self.plugin_id, f'Session cache updated: {len(self.get_session_items())} items')

    def _build_method_map(self, raw: Any) -> dict[str, int]:
        result: dict[str, int] = {}
        if not isinstance(raw, list):
            return result
        for item in raw:
            if not isinstance(item, list) or len(item) < 2:
                continue
            raw_name = item[0]
            raw_index = item[1]
            if not isinstance(raw_index, int):
                continue
            name = str(raw_name or '').strip()
            if not name:
                continue
            base_name = name.split('(', 1)[0].strip()
            if base_name and base_name not in result:
                result[base_name] = raw_index
            if name not in result:
                result[name] = raw_index
        return result

    def _build_property_map(self, raw: Any) -> tuple[dict[str, int], dict[int, str]]:
        result: dict[str, int] = {}
        indexes: dict[int, str] = {}
        if not isinstance(raw, list):
            return result, indexes
        for item in raw:
            name = ''
            index = None
            if isinstance(item, list):
                if len(item) >= 2 and isinstance(item[0], int) and isinstance(item[1], str):
                    index = item[0]
                    name = item[1]
                elif len(item) >= 2 and isinstance(item[0], str) and isinstance(item[1], int):
                    name = item[0]
                    index = item[1]
                elif len(item) >= 1 and isinstance(item[0], str):
                    name = item[0]
            elif isinstance(item, dict):
                name = str(item.get('name', '')).strip()
                idx = item.get('index')
                if isinstance(idx, int):
                    index = idx
            if not name:
                continue
            if isinstance(index, int):
                result[name] = index
                indexes[index] = name
            elif name not in result:
                result[name] = -1
        return result, indexes

    def _extract_property_values(self, raw: Any) -> dict[str, Any]:
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
                values[name] = value
        return values

    def _normalize_property_updates(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            normalized: dict[str, Any] = {}
            for key, value in raw.items():
                name = None
                if isinstance(key, int):
                    name = self._meld_property_indexes.get(key)
                else:
                    key_str = str(key)
                    if key_str.isdigit():
                        name = self._meld_property_indexes.get(int(key_str))
                    else:
                        name = key_str
                if name:
                    normalized[name] = value
            return normalized
        if isinstance(raw, list):
            normalized: dict[str, Any] = {}
            for idx, value in enumerate(raw):
                name = self._meld_property_indexes.get(idx)
                if name:
                    normalized[name] = value
            return normalized
        return {}

    def _resolve_method_id_locked(self, method_name: str) -> int | None:
        if method_name in self._meld_methods:
            return self._meld_methods[method_name]
        base_name = method_name.split('(', 1)[0].strip()
        if base_name in self._meld_methods:
            return self._meld_methods[base_name]
        return None

    def _bool_setting(self, settings: dict[str, Any], key: str, default: bool) -> bool:
        value = settings.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def create_plugin() -> MeldControlPlugin:
    return MeldControlPlugin()
