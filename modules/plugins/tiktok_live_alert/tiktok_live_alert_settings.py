from __future__ import annotations

import contextlib
import json
import os
import re
import random
import time
from pathlib import Path


def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets


def _norm_lang(value: str | None) -> str:
    lang = str(value or 'de').strip().lower()
    return lang if lang in {'de', 'en'} else 'de'


_I18N = {
    'en': {
        'Alert-Ausgaben': 'Alert outputs',
        'Test/Reset schreibt TXT und sendet passende aktivierte Meld-Routen direkt mit.': 'Test/Reset writes TXT files and sends matching enabled Meld routes directly.',
        '📋 Open Event Log': '📋 Open Event Log',
        'Meld outputs': 'Meld outputs',
        'Live actions': 'Live actions',
        'Personal like actions': 'Personal actions',
        'Like actions': 'Like actions',
        'Like Milestone Actions': 'Like milestone actions',
        'Ticker-Variablen': 'Ticker variables',
        'Doppelklick auf einen Eintrag oder markiere ihn und drücke Einfügen.': 'Double-click an entry or select it and press Insert.',
        'Variablen': 'Variables',
        'Einfügen': 'Insert',
        'Schließen': 'Close',
        'Test': 'Test',
        'Test +1 Event': 'Test +1 event',
        'Edit': 'Edit',
        'Reset': 'Reset',
        'TXT': 'TXT',
        'Meld Direct Outputs': 'Meld direct outputs',
        'Using active meld_control connection.': 'Using active meld_control connection.',
        'Refresh Meld Session': 'Refresh Meld session',
        '+ New Entry': '+ New entry',
        'Source': 'Source',
        'Scene': 'Scene',
        'Layer': 'Layer',
        'Property': 'Property',
        'Template': 'Template',
        'Timer (sec)': 'Timer (sec)',
        'Duplicate': 'Duplicate',
        'Delete': 'Delete',
    },
    'de': {
        'Alert outputs': 'Alert-Ausgaben',
        'Test/Reset writes TXT files and sends matching enabled Meld routes directly.': 'Test/Reset schreibt TXT und sendet passende aktivierte Meld-Routen direkt mit.',
        'Ticker variables': 'Ticker-Variablen',
        'Variables': 'Variablen',
        'Insert': 'Einfügen',
        'Close': 'Schließen',
        'Meld direct outputs': 'Meld Direct Outputs',
        'Live actions': 'Live-Aktionen',
        'Personal like actions': 'Persönliche Actions',
        'Like actions': 'Like-Aktionen',
        'Like milestone actions': 'Like-Meilenstein-Aktionen',
        'Using active Meld Control connection.': 'Aktive meld_control-Verbindung wird genutzt.',
        'Refresh Meld session': 'Meld-Session aktualisieren',
        '+ New entry': '+ Neuer Eintrag',
        'Duplicate': 'Duplizieren',
        'Delete': 'Löschen',
        'Timer (sec)': 'Timer (Sek.)',
        'Test +1 Event': 'Test +1 Event',
    },
}


def _tr(lang: str | None, text: str) -> str:
    base = str(text or '')
    return _I18N.get(_norm_lang(lang), {}).get(base, base)
from tiktok_live_alert_meld import MeldOutputManager, SOURCE_OPTIONS, PROPERTY_OPTIONS, LIVE_ACTION_SOURCE_OPTIONS, LIVE_ACTION_SOURCE_KEYS, LIVE_ACTION_MILESTONE_KEYS, LEGACY_ACTION_SOURCE_KEYS


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {'0', 'false', 'no', 'off', ''}
    return bool(value)


def _find_main_window() -> QtWidgets.QWidget | None:
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        try:
            if widget.metaObject().className() == 'MainWindow':
                return widget
        except Exception:
            pass
        if hasattr(widget, 'closed'):
            return widget
    return app.activeWindow()


def _qcolor_to_rgba(color: QtGui.QColor) -> str:
    if not color.isValid():
        color = QtGui.QColor('#ffffff')
    return f'rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})'


class _NoWheelComboFilter(QtCore.QObject):
    def eventFilter(self, obj, event) -> bool:
        try:
            if isinstance(obj, QtWidgets.QComboBox) and event.type() == QtCore.QEvent.Type.Wheel:
                view = obj.view()
                if view is not None and view.isVisible():
                    return False
                event.ignore()
                return True
        except Exception:
            pass
        return False


def _disable_combo_wheel(combo: QtWidgets.QComboBox | None) -> None:
    if combo is None:
        return
    if combo.property('tla_no_wheel'):
        return
    filt = _NoWheelComboFilter(combo)
    combo.installEventFilter(filt)
    combo._tla_no_wheel_filter = filt
    combo.setProperty('tla_no_wheel', True)


def _disable_combo_wheel_in(widget: QtWidgets.QWidget | None) -> None:
    if widget is None:
        return
    for combo in widget.findChildren(QtWidgets.QComboBox):
        _disable_combo_wheel(combo)



def _prepare_numeric_input(widget: QtWidgets.QAbstractSpinBox | None) -> None:
    if widget is None:
        return
    with contextlib.suppress(Exception):
        widget.setKeyboardTracking(False)
    with contextlib.suppress(Exception):
        widget.setAccelerated(True)
    with contextlib.suppress(Exception):
        widget.setCorrectionMode(QtWidgets.QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)
    with contextlib.suppress(Exception):
        widget.lineEdit().setClearButtonEnabled(False)
    with contextlib.suppress(Exception):
        widget.lineEdit().setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
    with contextlib.suppress(Exception):
        widget.lineEdit().setCursorPosition(0)


def _fit_dialog_to_screen(
    dialog: QtWidgets.QDialog,
    preferred_width: int,
    preferred_height: int,
    *,
    min_width: int = 420,
    min_height: int = 360,
) -> None:
    with contextlib.suppress(Exception):
        dialog.setSizeGripEnabled(True)
    with contextlib.suppress(Exception):
        dialog.setMinimumSize(min_width, min_height)
    try:
        screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
    except Exception:
        available = None
    if available is None:
        dialog.resize(preferred_width, preferred_height)
        return
    margin_w = 90
    margin_h = 120
    dialog.resize(
        max(min_width, min(preferred_width, max(min_width, available.width() - margin_w))),
        max(min_height, min(preferred_height, max(min_height, available.height() - margin_h))),
    )


class _ColorField(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(str)

    def __init__(self, value: str = '#ffffff', parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QtWidgets.QLineEdit(str(value or '#ffffff'))
        self.button = QtWidgets.QPushButton('Pick')
        self.button.setFixedWidth(56)
        self.button.clicked.connect(self._pick)
        self.edit.textChanged.connect(self.valueChanged)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def _pick(self) -> None:
        color = QtGui.QColor(self.edit.text().strip())
        picked = QtWidgets.QColorDialog.getColor(
            color if color.isValid() else QtGui.QColor('#ffffff'),
            self,
            'Choose color',
        )
        if picked.isValid():
            self.edit.setText(picked.name(QtGui.QColor.NameFormat.HexRgb))

    def value(self) -> str:
        return self.edit.text().strip()




class _TickerHelpDialog(QtWidgets.QDialog):
    TOKENS = [
        '{latest_follower}',
        '{latest_like_user}',
        '{latest_like_count}',
        '{latest_gift_user}',
        '{latest_gift_name}',
        '{latest_gift_count}',
        '{top_liker}',
        '{top_liker_count}',
        '{top_gifter}',
        '{top_gifter_count}',
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Ticker-Variablen')
        _fit_dialog_to_screen(self, 460, 420, min_width=360, min_height=300)
        self.selected_token = ''
        root = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel('Doppelklick auf einen Eintrag oder markiere ihn und drücke Einfügen.')
        info.setWordWrap(True)
        root.addWidget(info)
        self.list = QtWidgets.QListWidget()
        self.list.addItems(self.TOKENS)
        self.list.itemDoubleClicked.connect(lambda *_: self._accept_current())
        root.addWidget(self.list, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText('Einfügen')
        buttons.accepted.connect(self._accept_current)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.selected_token = item.text().strip()
        self.accept()

class _WidgetSettingsEditor(QtWidgets.QDialog):
    def __init__(
        self,
        title: str,
        bindings: dict[str, QtWidgets.QWidget],
        preview_window: _AlertWindow | None = None,
        settings_getter=None,
        sample_state_getter=None,
        live_apply_callback=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f'{title} Settings')
        _fit_dialog_to_screen(self, 560, 720, min_width=460, min_height=500)
        self._bindings = bindings
        self._preview_window = preview_window
        self._settings_getter = settings_getter
        self._sample_state_getter = sample_state_getter
        self._live_apply_callback = live_apply_callback

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QtWidgets.QWidget()
        content.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        content_root = QtWidgets.QVBoxLayout(content)
        content_root.setContentsMargins(2, 2, 10, 2)
        content_root.setSpacing(10)

        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        content_root.addLayout(form)

        self.show_title = QtWidgets.QCheckBox('Title anzeigen')
        self.show_title.setChecked(_as_bool(_widget_get(bindings.get('show_title'), False)))
        self._item_enabled_bindings = dict(bindings.get('item_enabled') or {})
        self._supported_items = list(bindings.get('supported_items') or ['title', 'main'])
        self._item_toggles: dict[str, QtWidgets.QCheckBox] = {}

        self.title_edit = QtWidgets.QLineEdit(_widget_get(bindings.get('title'), ''))
        self.font_box = QtWidgets.QFontComboBox()
        _disable_combo_wheel(self.font_box)
        self.font_box.setCurrentFont(QtGui.QFont(_widget_get(bindings.get('font_family'), 'Segoe UI')))

        self.font_size = QtWidgets.QSpinBox()
        self.font_size.setRange(8, 144)
        self.font_size.setValue(int(_widget_get(bindings.get('font_size'), 18)))
        _prepare_numeric_input(self.font_size)

        self.title_font_size = QtWidgets.QSpinBox()
        self.title_font_size.setRange(8, 144)
        self.title_font_size.setValue(
            int(_widget_get(bindings.get('title_font_size'), max(10, int(_widget_get(bindings.get('font_size'), 18)) + 2)))
        )
        _prepare_numeric_input(self.title_font_size)

        self.text_color = _ColorField(_widget_get(bindings.get('text_color'), '#ffffff'))
        self.bg_color = _ColorField(_widget_get(bindings.get('background_color'), '#151515'))
        self.accent_color = _ColorField(_widget_get(bindings.get('accent_color'), '#ff2d55'))

        self.text_opacity = QtWidgets.QDoubleSpinBox()
        self.text_opacity.setRange(0.0, 1.0)
        self.text_opacity.setSingleStep(0.05)
        self.text_opacity.setValue(float(_widget_get(bindings.get('text_opacity'), 1.0) or 1.0))
        _prepare_numeric_input(self.text_opacity)

        self.bg_opacity = QtWidgets.QDoubleSpinBox()
        self.bg_opacity.setRange(0.0, 1.0)
        self.bg_opacity.setSingleStep(0.05)
        self.bg_opacity.setValue(float(_widget_get(bindings.get('background_opacity'), 0.88) or 0.88))
        _prepare_numeric_input(self.bg_opacity)

        self.radius_spin = QtWidgets.QSpinBox()
        self.radius_spin.setRange(0, 80)
        self.radius_spin.setValue(int(_widget_get(bindings.get('corner_radius'), 16)))
        _prepare_numeric_input(self.radius_spin)

        self.bar_height = QtWidgets.QSpinBox()
        self.bar_height.setRange(8, 160)
        self.bar_height.setValue(int(_widget_get(bindings.get('bar_height'), 22) or 22))
        _prepare_numeric_input(self.bar_height)

        self.bar_style = None

        elements_box = QtWidgets.QGroupBox('Elemente')
        elements_layout = QtWidgets.QVBoxLayout(elements_box)
        elements_layout.setContentsMargins(8, 8, 8, 8)
        elements_layout.setSpacing(4)
        item_labels = {
            'title': 'Titel',
            'main': 'Hauptzeile',
            'secondary': 'Unterzeile',
            'progress': 'Balken',
            'list': 'Liste',
            'ticker': 'Ticker',
        }
        for item_key in self._supported_items:
            if item_key == 'title':
                checkbox = self.show_title
            else:
                checkbox = QtWidgets.QCheckBox(item_labels.get(item_key, item_key.title()))
                checkbox.setChecked(_as_bool(_widget_get(self._item_enabled_bindings.get(item_key), True)))
            self._item_toggles[item_key] = checkbox
            elements_layout.addWidget(checkbox)
        content_root.addWidget(elements_box)

        form.addRow('Titel', self.title_edit)
        form.addRow('Schriftart', self.font_box)
        form.addRow('Textgröße', self.font_size)
        form.addRow('Titelgröße', self.title_font_size)
        form.addRow('Textfarbe', self.text_color)
        form.addRow('Text-Transparenz', self.text_opacity)
        form.addRow('Hintergrund', self.bg_color)
        form.addRow('Hintergrund-Transparenz', self.bg_opacity)
        form.addRow('Accent / Balken', self.accent_color)
        form.addRow('Rundung', self.radius_spin)
        form.addRow('Balkenhöhe', self.bar_height)

        self.goal_spin = None
        self.progress_style = None
        if 'goal_target' in bindings:
            self.bar_style = QtWidgets.QComboBox()
            _disable_combo_wheel(self.bar_style)
            self.bar_style.addItems([
                'default', 'tiktok_clean', 'tiktok_diagonal', 'neon', 'flat',
                'double_border', 'soft_gradient', 'glass', 'candy_stripe', 'minimal_dark'
            ])
            current_bar_style = str(_widget_get(bindings.get('bar_style'), 'default') or 'default')
            idx = self.bar_style.findText(current_bar_style)
            self.bar_style.setCurrentIndex(max(0, idx))
            form.addRow('Balken-Stil', self.bar_style)

            self.goal_spin = QtWidgets.QSpinBox()
            self.goal_spin.setRange(0, 100000000)
            self.goal_spin.setValue(int(_widget_get(bindings.get('goal_target'), 0)))
            _prepare_numeric_input(self.goal_spin)
            form.addRow('Ziel', self.goal_spin)

            self.progress_style = QtWidgets.QComboBox()
            _disable_combo_wheel(self.progress_style)
            self.progress_style.addItems(['value', 'percent'])
            current_style = str(_widget_get(bindings.get('progress_style'), 'value') or 'value')
            idx = self.progress_style.findText(current_style)
            self.progress_style.setCurrentIndex(max(0, idx))
            form.addRow('Progress-Anzeige', self.progress_style)

        self.ticker_direction = None
        self.ticker_speed = None
        self.ticker_text = None
        self.ticker_vars_btn = None
        self.ticker_png_btn = None
        if 'ticker_direction' in bindings:
            self.ticker_direction = QtWidgets.QComboBox()
            _disable_combo_wheel(self.ticker_direction)
            self.ticker_direction.addItems(['left', 'right', 'bounce_left', 'bounce_right'])
            current_dir = str(_widget_get(bindings.get('ticker_direction'), 'left'))
            idx = self.ticker_direction.findText(current_dir)
            self.ticker_direction.setCurrentIndex(max(0, idx))

            self.ticker_speed = QtWidgets.QSpinBox()
            self.ticker_speed.setRange(1, 2000)
            self.ticker_speed.setValue(int(_widget_get(bindings.get('ticker_speed'), 80)))
            _prepare_numeric_input(self.ticker_speed)

            self.ticker_text = QtWidgets.QLineEdit(_widget_get(bindings.get('ticker_text'), ''))
            self.ticker_text.setPlaceholderText('z.B. Folge {twitch.png} godis3mpty auf Twitch! | {latest_follower}')

            ticker_controls = QtWidgets.QHBoxLayout()
            ticker_controls.setContentsMargins(0, 0, 0, 0)
            ticker_controls.setSpacing(6)
            self.ticker_vars_btn = QtWidgets.QPushButton('Variablen')
            self.ticker_vars_btn.setFixedWidth(82)
            self.ticker_vars_btn.clicked.connect(self._show_ticker_help)
            self.ticker_png_btn = QtWidgets.QPushButton('PNG')
            self.ticker_png_btn.setFixedWidth(50)
            self.ticker_png_btn.clicked.connect(self._pick_ticker_png)
            ticker_controls.addWidget(self.ticker_vars_btn)
            ticker_controls.addWidget(self.ticker_png_btn)
            ticker_controls.addStretch(1)

            ticker_box = QtWidgets.QVBoxLayout()
            ticker_box.setContentsMargins(0, 0, 0, 0)
            ticker_box.setSpacing(6)
            ticker_box_widget = QtWidgets.QWidget()
            ticker_box_widget.setLayout(ticker_box)
            ticker_box.addWidget(self.ticker_text)
            ticker_box.addLayout(ticker_controls)

            form.addRow('Ticker-Richtung', self.ticker_direction)
            form.addRow('Ticker-Speed', self.ticker_speed)
            form.addRow('Ticker-Text', ticker_box_widget)
            self.ticker_text.textChanged.connect(self._live_preview)
            self.ticker_text.editingFinished.connect(self._live_preview)

        for checkbox in self._item_toggles.values():
            try:
                checkbox.toggled.connect(self._live_preview)
            except Exception:
                pass

        note = QtWidgets.QLabel(
            'Änderungen an Elemente, Farben und Hintergrund werden direkt live angezeigt. '
            'Gespeichert wird am Ende mit Save.'
        )
        note.setWordWrap(True)
        note.setStyleSheet('color:#888;')
        content_root.addWidget(note)
        content_root.addStretch(1)

        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box = buttons
        self._save_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save)
        self._cancel_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel)

        if self._save_button is not None:
            try:
                self._save_button.clicked.disconnect()
            except Exception:
                pass
            self._save_button.clicked.connect(self._save_and_accept)
            self._save_button.setDefault(True)
            self._save_button.setAutoDefault(True)

        if self._cancel_button is not None:
            try:
                self._cancel_button.clicked.disconnect()
            except Exception:
                pass
            self._cancel_button.clicked.connect(self._cancel_and_close)

        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self._cancel_and_close)
        root.addWidget(buttons)

        self._live_widgets = [
            self.show_title, self.title_edit, self.font_box, self.font_size, self.title_font_size,
            self.text_color, self.text_opacity, self.bg_color, self.bg_opacity, self.accent_color,
            self.radius_spin, self.bar_height, self.bar_style, self.goal_spin, self.progress_style,
            self.ticker_direction, self.ticker_speed, self.ticker_text,
            *self._item_toggles.values(),
        ]
        for widget in self._live_widgets:
            self._connect_live_widget(widget)

    def _connect_live_widget(self, widget: QtWidgets.QWidget | None) -> None:
        if widget is None:
            return

        def _try_connect(obj: QtWidgets.QWidget, signal_names: tuple[str, ...]) -> None:
            for signal_name in signal_names:
                signal = getattr(obj, signal_name, None)
                if signal is None:
                    continue
                try:
                    signal.connect(self._live_preview)
                except Exception:
                    pass

        if isinstance(widget, QtWidgets.QAbstractSpinBox):
            _try_connect(widget, ('editingFinished', 'valueChanged'))
            return

        if isinstance(widget, QtWidgets.QLineEdit):
            _try_connect(widget, ('textChanged', 'editingFinished'))
            return

        if isinstance(widget, _ColorField):
            _try_connect(widget.edit, ('editingFinished',))
            _try_connect(widget.button, ('clicked',))
            return

        if isinstance(widget, QtWidgets.QCheckBox):
            _try_connect(widget, ('toggled', 'clicked'))
            return

        if isinstance(widget, QtWidgets.QComboBox):
            _try_connect(widget, ('currentTextChanged',))
            return

        if isinstance(widget, QtWidgets.QFontComboBox):
            _try_connect(widget, ('currentFontChanged',))
            return

        _try_connect(widget, ('toggled', 'clicked', 'valueChanged', 'currentFontChanged', 'currentTextChanged', 'textChanged', 'editingFinished'))

    def _insert_ticker_text(self, token: str) -> None:
        if self.ticker_text is None:
            return
        cursor = self.ticker_text.cursorPosition()
        current = self.ticker_text.text()
        self.ticker_text.setText(current[:cursor] + token + current[cursor:])
        self.ticker_text.setCursorPosition(cursor + len(token))
        self._live_preview()

    def _show_ticker_help(self) -> None:
        dlg = _TickerHelpDialog(self)
        if dlg.exec() == int(QtWidgets.QDialog.DialogCode.Accepted) and dlg.selected_token:
            self._insert_ticker_text(dlg.selected_token)

    def _pick_ticker_png(self) -> None:
        start_dir = _main_data_dir('tiktok_live_alert') / 'Tickerimage'
        start_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'PNG für Ticker auswählen', str(start_dir), 'PNG Images (*.png)')
        if not file_path:
            return
        src = Path(file_path)
        if not src.exists():
            return
        dest_dir = _main_data_dir('tiktok_live_alert') / 'Tickerimage'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        try:
            if src.resolve() != dest.resolve():
                import shutil
                shutil.copy2(src, dest)
        except Exception:
            return
        self._insert_ticker_text('{' + src.name + '}')

    def _live_preview(self, *args) -> None:
        self.apply()
        settings = self._settings_getter() if callable(self._settings_getter) else dict(getattr(self._preview_window, '_settings', {}) or {})
        sample_state = self._sample_state_getter() if callable(self._sample_state_getter) else None
        if self._preview_window is not None:
            self._preview_window.update_settings(settings, sample_state)
        if callable(self._live_apply_callback):
            self._live_apply_callback(settings, sample_state)

    def _cancel_and_close(self) -> None:
        self.reject()

    def _save_and_accept(self) -> None:
        self.apply()
        settings = self._settings_getter() if callable(self._settings_getter) else dict(getattr(self._preview_window, '_settings', {}) or {})
        sample_state = self._sample_state_getter() if callable(self._sample_state_getter) else None
        if self._preview_window is not None:
            self._preview_window.update_settings(settings, sample_state)
        if callable(self._live_apply_callback):
            self._live_apply_callback(settings, sample_state)
        self.accept()

    def apply(self) -> None:
        _widget_set(self._bindings.get('show_title'), self.show_title.isChecked())
        for item_key, checkbox in self._item_toggles.items():
            if item_key == 'title':
                continue
            _widget_set(self._item_enabled_bindings.get(item_key), checkbox.isChecked())
        _widget_set(self._bindings.get('title'), self.title_edit.text().strip())
        _widget_set(self._bindings.get('font_family'), self.font_box.currentFont().family())
        _widget_set(self._bindings.get('font_size'), self.font_size.value())
        _widget_set(self._bindings.get('title_font_size'), self.title_font_size.value())
        _widget_set(self._bindings.get('text_color'), self.text_color.value())
        _widget_set(self._bindings.get('text_opacity'), self.text_opacity.value())
        _widget_set(self._bindings.get('background_color'), self.bg_color.value())
        _widget_set(self._bindings.get('background_opacity'), self.bg_opacity.value())
        _widget_set(self._bindings.get('accent_color'), self.accent_color.value())
        _widget_set(self._bindings.get('corner_radius'), self.radius_spin.value())
        _widget_set(self._bindings.get('bar_height'), self.bar_height.value())
        if self.bar_style is not None:
            _widget_set(self._bindings.get('bar_style'), self.bar_style.currentText())
        if self.goal_spin is not None:
            _widget_set(self._bindings.get('goal_target'), self.goal_spin.value())
        if self.progress_style is not None:
            _widget_set(self._bindings.get('progress_style'), self.progress_style.currentText())
        if self.ticker_direction is not None:
            _widget_set(self._bindings.get('ticker_direction'), self.ticker_direction.currentText())
            _widget_set(self._bindings.get('ticker_speed'), self.ticker_speed.value())
            _widget_set(self._bindings.get('ticker_text'), self.ticker_text.text().strip())


def _normalize_color_text(value: Any, fallback: str = '#ffffff') -> str:
    text = str(value or '').strip()
    if not text:
        return fallback
    color = QtGui.QColor(text)
    if color.isValid():
        return color.name(QtGui.QColor.NameFormat.HexRgb)
    return text


def _widget_get(widget: QtWidgets.QWidget | None, default: Any = '') -> Any:
    if widget is None:
        return default
    if isinstance(widget, QtWidgets.QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QtWidgets.QPlainTextEdit):
        return widget.toPlainText().strip()
    if isinstance(widget, QtWidgets.QSpinBox):
        return widget.value()
    if isinstance(widget, QtWidgets.QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QtWidgets.QFontComboBox):
        return widget.currentFont().family()
    if isinstance(widget, _ColorField):
        return widget.value()
    if isinstance(widget, QtWidgets.QLineEdit):
        return widget.text().strip()
    if isinstance(widget, QtWidgets.QComboBox):
        return widget.currentText().strip()
    for attr in ('value', 'text', 'currentText', 'color', 'currentColor'):
        meth = getattr(widget, attr, None)
        if callable(meth):
            try:
                result = meth()
                if isinstance(result, QtGui.QColor):
                    return result.name(QtGui.QColor.NameFormat.HexRgb)
                if result is not None:
                    return result
            except Exception:
                pass
    line_edit = widget.findChild(QtWidgets.QLineEdit)
    if line_edit is not None:
        return line_edit.text().strip()
    return default


def _widget_set(widget: QtWidgets.QWidget | None, value: Any) -> None:
    if widget is None:
        return
    if isinstance(widget, QtWidgets.QCheckBox):
        widget.setChecked(_as_bool(value))
        return
    if isinstance(widget, QtWidgets.QPlainTextEdit):
        widget.setPlainText(str(value or ''))
        return
    if isinstance(widget, QtWidgets.QSpinBox):
        widget.setValue(int(float(value or 0)))
        return
    if isinstance(widget, QtWidgets.QDoubleSpinBox):
        widget.setValue(float(value or 0.0))
        return
    if isinstance(widget, QtWidgets.QFontComboBox):
        widget.setCurrentFont(QtGui.QFont(str(value or 'Segoe UI')))
        return
    if isinstance(widget, _ColorField):
        widget.edit.setText(_normalize_color_text(value))
        return
    if isinstance(widget, QtWidgets.QLineEdit):
        widget.setText(str(value or ''))
        return
    if isinstance(widget, QtWidgets.QComboBox):
        idx = widget.findText(str(value or ''))
        if idx >= 0:
            widget.setCurrentIndex(idx)
        return
    color_value = _normalize_color_text(value)
    for attr in ('setValue', 'setText', 'setCurrentText', 'setColor', 'setCurrentColor'):
        meth = getattr(widget, attr, None)
        if callable(meth):
            try:
                if attr in {'setColor', 'setCurrentColor'}:
                    meth(QtGui.QColor(color_value))
                elif attr == 'setValue' and isinstance(value, bool):
                    meth(value)
                else:
                    meth(value if attr == 'setValue' else str(value or ''))
                widget.update()
                return
            except Exception:
                pass
    line_edit = widget.findChild(QtWidgets.QLineEdit)
    if line_edit is not None:
        line_edit.setText(str(value or ''))
        widget.update()




class _MeldRouteRow(QtWidgets.QFrame):
    deleteRequested = QtCore.Signal(object)
    duplicateRequested = QtCore.Signal(object)
    testRequested = QtCore.Signal(object)
    eventTestRequested = QtCore.Signal(object)
    resetRequested = QtCore.Signal(object)
    routeChanged = QtCore.Signal()

    def __init__(
        self,
        route: dict[str, Any],
        parent=None,
        language: str | None = None,
        fixed_source_key: str | None = None,
        show_source: bool = True,
        source_options: list[tuple[str, str]] | None = None,
        show_threshold: bool = False,
        show_target_user: bool = False,
    ) -> None:
        super().__init__(parent)
        self._language = _norm_lang(language)
        self._fixed_source_key = str(fixed_source_key or '').strip()
        self._source_options = list(source_options or SOURCE_OPTIONS)
        self._show_threshold = bool(show_threshold)
        self._show_target_user = bool(show_target_user)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setProperty('routeRow', True)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        self.enabled = QtWidgets.QCheckBox('Enabled')
        self.enabled.setChecked(_as_bool(route.get('enabled', True)))
        self.source = QtWidgets.QComboBox()
        for key, label in self._source_options:
            self.source.addItem(label, key)
        wanted_source = self._fixed_source_key or route.get('source_key', 'latest_follower.txt')
        self._set_combo_data(self.source, wanted_source)
        top.addWidget(self.enabled)
        self.source_label = QtWidgets.QLabel(_tr(self._language, 'Source'))
        top.addWidget(self.source_label)
        top.addWidget(self.source, 1)
        if not show_source:
            self.source_label.hide()
            self.source.hide()
            title = next((label for key, label in self._source_options if str(key) == str(wanted_source)), str(wanted_source or 'Meld action'))
            fixed_label = QtWidgets.QLabel(title)
            fixed_label.setStyleSheet('font-weight: 600;')
            top.addWidget(fixed_label, 1)
        root.addLayout(top)

        mid = QtWidgets.QGridLayout()
        mid.setHorizontalSpacing(6)
        mid.setVerticalSpacing(6)
        self.scene = QtWidgets.QComboBox()
        self.scene.setEditable(True)
        self.layer = QtWidgets.QComboBox()
        self.layer.setEditable(True)
        self._session_scenes: list[dict[str, Any]] = []
        self._session_layers: list[dict[str, Any]] = []
        self.prop = QtWidgets.QComboBox()
        self.prop.setEditable(True)
        for prop_name in PROPERTY_OPTIONS:
            self.prop.addItem(prop_name)
        for combo in (self.source, self.scene, self.layer, self.prop):
            _disable_combo_wheel(combo)
        self.template = QtWidgets.QLineEdit(str(route.get('template', '{value}') or '{value}'))
        self.template.setPlaceholderText('{value}')
        timer_raw = route.get('restore_delay', route.get('restore_delay_seconds', route.get('timer_seconds', '')))
        if timer_raw in (None, ''):
            old_template = str(route.get('template', '') or '').strip()
            if old_template and old_template not in {'{value}', '{}'}:
                timer_raw = old_template
        self.restore_delay = QtWidgets.QLineEdit(str(timer_raw or ''))
        self.restore_delay.setPlaceholderText('0 = no restore, e.g. 10')
        self.threshold_label = QtWidgets.QLabel('Step')
        self.threshold = QtWidgets.QSpinBox()
        self.threshold.setRange(1, 100000000)
        self.threshold.setSingleStep(1)
        default_threshold = int(route.get('threshold') or (200 if str(wanted_source).strip().lower() in {'live_action_like_milestone', 'like_milestone_trigger', 'like_milestone_trigger.txt'} else 10))
        self.threshold.setValue(max(1, default_threshold))
        self.threshold.setVisible(self._show_threshold)
        self.threshold_label.setVisible(self._show_threshold)
        self.target_user_label = QtWidgets.QLabel('Name')
        self.target_user = QtWidgets.QLineEdit(str(route.get('target_user', route.get('user_name', '')) or ''))
        self.target_user.setPlaceholderText('Name exakt wie im Chat')
        self.target_user.setVisible(self._show_target_user)
        self.target_user_label.setVisible(self._show_target_user)
        self._set_combo_text(self.scene, route.get('scene_name', '') or route.get('scene_id', ''))
        self._set_combo_text(self.layer, route.get('layer_name', '') or route.get('layer_id', ''))
        self._set_combo_text(self.prop, route.get('property_name', 'text'))
        mid.addWidget(QtWidgets.QLabel('Scene'), 0, 0)
        mid.addWidget(self.scene, 0, 1)
        mid.addWidget(QtWidgets.QLabel('Layer'), 0, 2)
        mid.addWidget(self.layer, 0, 3)
        mid.addWidget(QtWidgets.QLabel('Property'), 1, 0)
        mid.addWidget(self.prop, 1, 1)
        mid.addWidget(QtWidgets.QLabel('Template'), 1, 2)
        mid.addWidget(self.template, 1, 3)
        self.restore_delay_label = QtWidgets.QLabel(_tr(self._language, 'Timer (sec)'))
        mid.addWidget(self.restore_delay_label, 2, 0)
        mid.addWidget(self.restore_delay, 2, 1)
        mid.addWidget(self.threshold_label, 2, 2)
        mid.addWidget(self.threshold, 2, 3)
        mid.addWidget(self.target_user_label, 3, 0)
        mid.addWidget(self.target_user, 3, 1, 1, 3)
        mid.setColumnStretch(1, 1)
        mid.setColumnStretch(3, 1)
        root.addLayout(mid)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        test_btn = QtWidgets.QPushButton(_tr(self._language, 'Test'))
        event_test_btn = QtWidgets.QPushButton(_tr(self._language, 'Test +1 Event'))
        reset_btn = QtWidgets.QPushButton(_tr(self._language, 'Reset'))
        dup_btn = QtWidgets.QPushButton('Duplicate')
        del_btn = QtWidgets.QPushButton('Delete')
        test_btn.clicked.connect(lambda *_: self.testRequested.emit(self))
        event_test_btn.clicked.connect(lambda *_: self.eventTestRequested.emit(self))
        reset_btn.clicked.connect(lambda *_: self.resetRequested.emit(self))
        dup_btn.clicked.connect(lambda *_: self.duplicateRequested.emit(self))
        del_btn.clicked.connect(lambda *_: self.deleteRequested.emit(self))
        btns.addWidget(test_btn)
        btns.addWidget(event_test_btn)
        btns.addWidget(reset_btn)
        btns.addWidget(dup_btn)
        btns.addWidget(del_btn)
        root.addLayout(btns)

        self.enabled.toggled.connect(lambda *_: self._emit_route_changed())
        self.source.currentIndexChanged.connect(lambda *_: self._source_changed())
        self.scene.currentIndexChanged.connect(lambda *_: self._scene_changed())
        self.scene.editTextChanged.connect(lambda *_: self._scene_changed())
        self.layer.currentIndexChanged.connect(lambda *_: self._emit_route_changed())
        self.layer.editTextChanged.connect(lambda *_: self._emit_route_changed())
        self.prop.currentIndexChanged.connect(lambda *_: self._emit_route_changed())
        self.prop.editTextChanged.connect(lambda *_: self._emit_route_changed())
        self.template.textChanged.connect(lambda *_: self._emit_route_changed())
        self.restore_delay.textChanged.connect(lambda *_: self._emit_route_changed())
        self.threshold.valueChanged.connect(lambda *_: self._emit_route_changed())
        self.target_user.textChanged.connect(lambda *_: self._emit_route_changed())
        self._source_changed(emit=False)

    def _source_changed(self, emit: bool = True) -> None:
        source_key = str(self._fixed_source_key or self.source.currentData() or self.source.currentText() or '').strip().lower()
        is_milestone = source_key in set(LIVE_ACTION_MILESTONE_KEYS) | {'like_milestone_trigger', 'like_milestone_trigger.txt'}
        visible = self._show_threshold and is_milestone
        self.threshold_label.setVisible(visible)
        self.threshold.setVisible(visible)
        target_visible = self._show_target_user or source_key in {'live_action_personal_like_milestone', 'live_action_personal_gift_milestone'}
        self.target_user_label.setVisible(target_visible)
        self.target_user.setVisible(target_visible)
        if emit:
            self._emit_route_changed()

    def _emit_route_changed(self) -> None:
        self.routeChanged.emit()

    def _scene_changed(self) -> None:
        # Beim Wechsel der Szene darf der alte Layer nicht erzwungen werden.
        # Sonst bleibt ein Layer aus der vorherigen Szene im editierbaren Combo hängen
        # und die Dropdown-Auswahl wirkt kaputt.
        self._rebuild_layer_combo(preserve_existing=False)
        self._emit_route_changed()

    def _clean_combo_label(self, text: Any) -> str:
        return str(text or '').replace('  [current]', '').strip()

    def _set_combo_text(self, combo: QtWidgets.QComboBox, value: Any) -> None:
        text = str(value or '').strip()
        if not text:
            return
        clean_text = self._clean_combo_label(text)
        idx = combo.findText(text)
        if idx < 0:
            for i in range(combo.count()):
                if self._clean_combo_label(combo.itemText(i)).casefold() == clean_text.casefold():
                    idx = i
                    break
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.isEditable():
            combo.setEditText(text)
        else:
            combo.addItem(text, '')
            combo.setCurrentIndex(combo.count() - 1)

    def _set_combo_data(self, combo: QtWidgets.QComboBox, value: Any) -> bool:
        wanted = str(value or '')
        for i in range(combo.count()):
            if str(combo.itemData(i) or '') == wanted:
                combo.setCurrentIndex(i)
                return True
        self._set_combo_text(combo, value)
        return False

    def populate_session(self, scenes: list[dict[str, Any]], layers: list[dict[str, Any]]) -> None:
        current_scene_text = self.scene.currentText().strip()
        current_scene_id = str(self.scene.currentData() or '')
        current_layer_text = self.layer.currentText().strip()
        current_layer_id = str(self.layer.currentData() or '')
        self._session_scenes = [dict(scene) for scene in scenes]
        self._session_layers = [dict(layer) for layer in layers]

        # Wichtig: Beim Session-Refresh dürfen ComboBox-Signale nicht zwischendurch autosaven.
        # Sonst wird aus einer vorhandenen Route kurzzeitig der erste Eintrag der neuen Liste
        # und genau dadurch landete wieder nur "Alerts" oder eine kaputte Route in der JSON.
        old_scene_block = self.scene.blockSignals(True)
        old_layer_block = self.layer.blockSignals(True)
        try:
            self.scene.clear()
            self.scene.addItem('', '')
            for scene in self._session_scenes:
                label = str(scene.get('name') or '')
                if scene.get('current'):
                    label += '  [current]'
                self.scene.addItem(label.strip(), str(scene.get('id') or ''))

            if current_scene_id:
                self._set_combo_data(self.scene, current_scene_id)
            elif current_scene_text:
                self._set_combo_text(self.scene, current_scene_text)

            # _rebuild_layer_combo blockt selbst ebenfalls, aber hier bleibt es absichtlich
            # durchgehend geblockt, bis Scene UND Layer wieder restauriert sind.
            self._rebuild_layer_combo(preserve_layer_id=current_layer_id, preserve_layer_text=current_layer_text)
        finally:
            self.layer.blockSignals(old_layer_block)
            self.scene.blockSignals(old_scene_block)

        self._emit_route_changed()

    def _selected_scene_id_or_name(self) -> tuple[str, str]:
        scene_id = str(self.scene.currentData() or '').strip()
        scene_text = self.scene.currentText().strip()
        clean_name = scene_text.replace('  [current]', '').strip()
        return scene_id, clean_name.casefold()

    def _rebuild_layer_combo(self, preserve_layer_id: str = '', preserve_layer_text: str = '', preserve_existing: bool = True) -> None:
        if preserve_existing and not preserve_layer_id:
            preserve_layer_id = str(self.layer.currentData() or '')
        if preserve_existing and not preserve_layer_text:
            preserve_layer_text = self.layer.currentText().strip()

        scene_id, scene_name = self._selected_scene_id_or_name()
        filtered_layers: list[dict[str, Any]] = []
        for layer in self._session_layers:
            parent = str(layer.get('parent') or '')
            layer_scene_id = str(layer.get('_scene_id') or '')
            layer_scene_name = str(layer.get('_scene_name') or '').strip().casefold()
            if scene_id:
                if layer_scene_id:
                    if layer_scene_id != scene_id:
                        continue
                elif parent != scene_id:
                    continue
            elif scene_name:
                if layer_scene_name != scene_name:
                    continue
            filtered_layers.append(layer)

        self.layer.blockSignals(True)
        self.layer.clear()
        self.layer.addItem('', '')
        for layer in filtered_layers:
            # Meld gibt Ordner/Gruppen als echte Hierarchie vor. Deshalb muss die UI
            # den vollständigen Pfad anzeigen und speichern, z. B. Alerts/100likes.
            # Nur der Kurzname 100likes reicht beim Test/Trigger nicht zuverlässig.
            label = str(layer.get('full_path') or layer.get('display_name') or layer.get('name') or '')
            self.layer.addItem(label, str(layer.get('id') or ''))
        self.layer.blockSignals(False)

        restored = False
        if preserve_layer_id:
            restored = self._set_combo_data(self.layer, preserve_layer_id)
        elif preserve_layer_text:
            self._set_combo_text(self.layer, preserve_layer_text)
            restored = bool(self.layer.currentText().strip())

        if not preserve_existing:
            # Nach Szenenwechsel bewusst keinen alten Layer aus einer anderen Szene behalten.
            self.layer.setCurrentIndex(1 if self.layer.count() > 1 else 0)
        elif not restored and not preserve_layer_id and not preserve_layer_text:
            self.layer.setCurrentIndex(0)

    def to_route(self) -> dict[str, Any]:
        scene_idx = self.scene.currentIndex()
        layer_idx = self.layer.currentIndex()
        scene_name = self.scene.currentText().strip().replace('  [current]', '').strip()
        layer_id = str(self.layer.itemData(layer_idx) or '')
        layer_name = self.layer.currentText().strip()
        selected_text = self.layer.itemText(layer_idx).strip() if layer_idx >= 0 else ''

        # Dropdown-Auswahl: echten Meld-Pfad speichern. Manuelle Eingabe: exakt den Text speichern
        # und keine alte ComboBox-ID mitschleppen.
        manual_layer_text = bool(layer_name and selected_text and layer_name != selected_text)
        if manual_layer_text:
            layer_id = ''
        elif layer_id:
            for layer in self._session_layers:
                if str(layer.get('id') or '') == layer_id:
                    layer_name = str(layer.get('full_path') or layer.get('display_name') or layer.get('name') or layer_name).strip()
                    break

        route = {
            'enabled': self.enabled.isChecked(),
            'source_key': self._fixed_source_key or str(self.source.currentData() or self.source.currentText() or 'latest_follower.txt'),
            'scene_id': str(self.scene.itemData(scene_idx) or ''),
            'scene_name': scene_name,
            'layer_id': layer_id,
            'layer_name': layer_name,
            'property_name': self.prop.currentText().strip() or 'text',
            'template': self.template.text().strip() or '{value}',
            'restore_delay': self.restore_delay.text().strip(),
        }
        if self._show_threshold:
            route['threshold'] = int(self.threshold.value())
        if self._show_target_user or str(route.get('source_key') or '').strip().lower() in {'live_action_personal_like_milestone', 'live_action_personal_gift_milestone'}:
            route['target_user'] = self.target_user.text().strip()
        return route

class _MeldOutputsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        plugin,
        settings_getter,
        sample_state_getter,
        parent=None,
        routes_changed_callback=None,
        title: str | None = None,
        default_route: dict[str, Any] | None = None,
        route_filter=None,
        row_fixed_source_key: str | None = None,
        row_show_source: bool = True,
        add_button_text: str | None = None,
        source_options: list[tuple[str, str]] | None = None,
        show_threshold: bool = False,
        show_target_user: bool = False,
    ) -> None:
        super().__init__(parent)
        self.plugin = plugin
        self._settings_getter = settings_getter
        self._sample_state_getter = sample_state_getter
        self._manager = getattr(plugin, '_meld_output_manager', None) or MeldOutputManager(getattr(plugin, 'logger', None), plugin)
        self._test_counter = 0
        self._event_test_counts: dict[int, int] = {}
        self._routes_changed_callback = routes_changed_callback
        self._session_scenes: list[dict[str, Any]] = []
        self._session_layers: list[dict[str, Any]] = []
        self._autosave_ready = False
        self._autosave_timer = QtCore.QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(250)
        self._autosave_timer.timeout.connect(self._autosave_routes_now)
        self._route_filter = route_filter
        self._row_fixed_source_key = str(row_fixed_source_key or '').strip()
        self._row_show_source = bool(row_show_source)
        self._source_options = list(source_options or SOURCE_OPTIONS)
        self._show_threshold = bool(show_threshold)
        self._show_target_user = bool(show_target_user)
        self._default_route = dict(default_route or {'enabled': True, 'source_key': 'latest_follower.txt', 'property_name': 'text', 'template': '{value}'})
        self._base_routes: list[dict[str, Any]] = []
        self.setWindowTitle(_tr(getattr(self.plugin, 'ui_language', 'de'), title or 'Meld Direct Outputs'))
        _fit_dialog_to_screen(self, 1120, 760, min_width=720, min_height=480)
        settings = dict(settings_getter() or {})
        self._rows: list[_MeldRouteRow] = []

        root = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        info = QtWidgets.QLabel(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Using active meld_control connection.'))
        refresh_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Refresh Meld Session'))
        refresh_btn.clicked.connect(self._refresh_session)
        add_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), add_button_text or '+ New Entry'))
        add_btn.clicked.connect(self._add_entry)
        top.addWidget(info)
        top.addStretch(1)
        top.addWidget(refresh_btn)
        top.addWidget(add_btn)
        root.addLayout(top)

        self.status_label = QtWidgets.QLabel('')
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.container = QtWidgets.QWidget()
        self.rows_layout = QtWidgets.QVBoxLayout(self.container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        save_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText('Save')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        loaded_routes = self._manager.load_routes(settings)
        if self._route_filter is not None:
            routes = []
            self._base_routes = []
            for route in loaded_routes:
                if self._route_filter(route):
                    routes.append(route)
                else:
                    self._base_routes.append(route)
        else:
            routes = loaded_routes
            self._base_routes = []
        if not routes:
            route = dict(self._default_route)
            if self._row_fixed_source_key:
                route['source_key'] = self._row_fixed_source_key
            routes = [route]
        for route in routes:
            if self._row_fixed_source_key:
                route = dict(route)
                route['source_key'] = self._row_fixed_source_key
            self._add_entry(route, mark_changed=False)
        self._autosave_ready = True
        QtCore.QTimer.singleShot(0, self._refresh_session)

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        pal = self.status_label.palette()
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor('#ff5c5c' if error else '#b8ffb8'))
        self.status_label.setPalette(pal)

    def _insert_row_widget(self, row: _MeldRouteRow) -> None:
        row.deleteRequested.connect(self._delete_row)
        row.duplicateRequested.connect(self._duplicate_row)
        row.testRequested.connect(self._test_row)
        row.eventTestRequested.connect(self._test_event_row)
        row.resetRequested.connect(self._reset_row)
        row.routeChanged.connect(self._schedule_autosave)
        self._rows.append(row)
        self.rows_layout.insertWidget(max(0, self.rows_layout.count()-1), row)

    def _add_entry(self, route: dict[str, Any] | None = None, mark_changed: bool = True) -> _MeldRouteRow:
        route_data = dict(route or self._default_route)
        if self._row_fixed_source_key:
            route_data['source_key'] = self._row_fixed_source_key
        row = _MeldRouteRow(
            route_data,
            self.container,
            getattr(self.plugin, 'ui_language', 'de'),
            fixed_source_key=self._row_fixed_source_key or None,
            show_source=self._row_show_source,
            source_options=self._source_options,
            show_threshold=self._show_threshold,
            show_target_user=self._show_target_user,
        )
        self._insert_row_widget(row)
        if self._session_scenes or self._session_layers:
            row.populate_session(self._session_scenes, self._session_layers)
        if mark_changed:
            self._schedule_autosave()
        return row

    def _duplicate_row(self, row: _MeldRouteRow) -> None:
        self._add_entry(dict(row.to_route()))
        self._set_status('Entry duplicated. Changes are stored live.')

    def _delete_row(self, row: _MeldRouteRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
        self._event_test_counts.pop(id(row), None)
        row.setParent(None)
        row.deleteLater()
        if not self._rows:
            self._add_entry(mark_changed=False)
        self._schedule_autosave()

    def _refresh_session(self) -> None:
        try:
            snap = self._manager.fetch_session_snapshot()
            scenes = list(snap.get('scenes') or [])
            items = snap.get('items') or {}
            layers = []
            for layer in snap.get('layers') or []:
                row = dict(layer)
                # _split_session_items() already resolved the real scene through any
                # Meld layer groups. Do not replace it with the direct parent name,
                # because the direct parent can be a group/folder like "Alerts".
                if not str(row.get('_scene_name') or '').strip():
                    scene = items.get(str(row.get('parent') or '')) or {}
                    row['_scene_name'] = str(scene.get('name') or '')
                layers.append(row)
            self._session_scenes = scenes
            self._session_layers = layers
            for row in self._rows:
                row.populate_session(scenes, layers)
            self._schedule_autosave()
            self._set_status(f'Meld session loaded: {len(scenes)} scenes, {len(layers)} layers.')
        except Exception as exc:
            self._set_status(f'Meld session refresh failed: {exc}', error=True)

    def _build_meld_test_state(self, source_key: str) -> dict[str, Any]:
        settings = self.current_settings()
        self._test_counter += 1
        n = f'{self._test_counter:03d}'
        state = {
            'channel': settings.get('unique_id') or '@sample',
            'latest': {
                'follower': f'your name here {n}',
                'like_user': f'Latest Like {n}',
                'like_count': 100 + self._test_counter,
                'gift_user': f'Latest Gift {n}',
                'gift_name': f'Rose {n}',
                'gift_count': 1 + (self._test_counter % 9),
                'like_milestone': self._test_counter * 100,
                'like_milestone_total': self._test_counter * 100,
                'gift_milestone': self._test_counter * 10,
                'gift_milestone_total': self._test_counter * 10,
            },
            'goals': {
                'followers': {'current': self._test_counter, 'target': max(1, int(settings.get('follower_goal') or 1000))},
                'likes': {'current': self._test_counter * 100, 'target': max(1, int(settings.get('like_goal') or 10000))},
                'gifts': {'current': self._test_counter, 'target': max(1, int(settings.get('gift_goal') or 100))},
            },
            'rankings': {
                'likers': [
                    {'name': f'sadly not you {n}', 'count': 1000 + self._test_counter},
                    {'name': f'sadly runner up {n}', 'count': 500 + self._test_counter},
                    {'name': f'sadly third place {n}', 'count': 250 + self._test_counter},
                ],
                'gifters': [
                    {'name': f'sadly not you {n}', 'count': 100 + self._test_counter},
                    {'name': f'sadly runner up {n}', 'count': 50 + self._test_counter},
                    {'name': f'sadly third place {n}', 'count': 25 + self._test_counter},
                ],
            },
            'ticker': {
                'text': f'Ticker 1 Test {n}',
                'text_2': f'Ticker 2 Test {n}',
                'text_3': f'Ticker 3 Test {n}',
                'direction': str(settings.get('ticker_direction') or 'left'),
                'direction_2': str(settings.get('ticker_2_direction') or 'right'),
                'direction_3': str(settings.get('ticker_3_direction') or 'bounce_left'),
                'speed': float(settings.get('ticker_speed') or 80),
                'speed_2': float(settings.get('ticker_2_speed') or 80),
                'speed_3': float(settings.get('ticker_3_speed') or 70),
            },
        }
        source_key = str(source_key or '').strip().lower()
        if source_key in {'latest_follower.txt', 'new_follower.txt'}:
            state['latest']['follower'] = f'your name here {n}'
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif source_key == 'latest_like.txt':
            state['latest']['like_user'] = f'Latest Like {n}'
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif source_key == 'latest_gift.txt':
            state['latest']['gift_user'] = f'Latest Gift {n}'
            state['latest']['gift_name'] = f'Galaxy {n}'
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif source_key in {'top_liker.txt', 'top_liker_leader.txt', 'top_liker_list.txt'}:
            state['latest']['follower'] = ''
            state['latest']['like_user'] = ''
            state['latest']['gift_user'] = ''
            state['rankings']['gifters'] = []
        elif source_key in {'top_gifter.txt', 'top_gifter_leader.txt', 'top_gifter_list.txt'}:
            state['latest']['follower'] = ''
            state['latest']['like_user'] = ''
            state['latest']['gift_user'] = ''
            state['rankings']['likers'] = []
        elif source_key.startswith('follower_goal'):
            state['goals']['followers']['current'] = min(state['goals']['followers']['target'], self._test_counter)
        elif source_key.startswith('like_goal'):
            state['goals']['likes']['current'] = min(state['goals']['likes']['target'], self._test_counter * 100)
        elif source_key.startswith('gift_goal'):
            state['goals']['gifts']['current'] = min(state['goals']['gifts']['target'], self._test_counter)
        elif source_key in {'like_milestone_trigger', 'like_milestone_trigger.txt', 'live_action_like_milestone', 'live_action_personal_like_milestone'}:
            state['latest']['like_milestone'] = self._test_counter * 100
            state['latest']['like_milestone_total'] = self._test_counter * 100
        elif source_key in {'live_action_gift_milestone', 'live_action_personal_gift_milestone'}:
            state['latest']['gift_milestone'] = self._test_counter * 10
            state['latest']['gift_milestone_total'] = self._test_counter * 10
        elif source_key == 'summary.txt':
            state['latest']['follower'] = f'Summary Follower {n}'
            state['latest']['like_user'] = f'Summary Like {n}'
            state['latest']['gift_user'] = f'Summary Gift {n}'
        return state


    def _build_meld_reset_state(self, source_key: str) -> dict[str, Any]:
        settings = self.current_settings()
        follower_target = max(0, int(settings.get('follower_goal') or 0))
        like_target = max(0, int(settings.get('like_goal') or 0))
        gift_target = max(0, int(settings.get('gift_goal') or 0))
        source_key = str(source_key or '').strip().lower()
        state = {
            'channel': settings.get('unique_id') or '@sample',
            'latest': {
                'follower': 'your name here',
                'like_user': 'your name here',
                'like_count': 0,
                'gift_user': 'your name here',
                'gift_name': 'gift',
                'gift_count': 0,
            },
            'goals': {
                'followers': {'current': 0, 'target': follower_target},
                'likes': {'current': 0, 'target': like_target},
                'gifts': {'current': 0, 'target': gift_target},
            },
            'rankings': {'likers': [], 'gifters': []},
            'ticker': {
                'text': 'ticker ready',
                'text_2': 'ticker 2 ready',
                'text_3': 'ticker 3 ready',
                'direction': str(settings.get('ticker_direction') or 'left'),
                'direction_2': str(settings.get('ticker_2_direction') or 'right'),
                'direction_3': str(settings.get('ticker_3_direction') or 'bounce_left'),
                'speed': float(settings.get('ticker_speed') or 80),
                'speed_2': float(settings.get('ticker_2_speed') or 80),
                'speed_3': float(settings.get('ticker_3_speed') or 70),
            },
        }
        if source_key in {'top_liker.txt', 'top_liker_leader.txt', 'top_liker_list.txt'}:
            state['rankings']['likers'] = [{'name': 'sadly not you', 'count': 0}]
        elif source_key in {'top_gifter.txt', 'top_gifter_leader.txt', 'top_gifter_list.txt'}:
            state['rankings']['gifters'] = [{'name': 'sadly not you', 'count': 0}]
        elif source_key == 'summary.txt':
            state['latest']['follower'] = 'your name here'
            state['latest']['like_user'] = 'your name here'
            state['latest']['gift_user'] = 'your name here'
        return state

    def _test_row(self, row: _MeldRouteRow) -> None:
        settings = self.current_settings()
        route = row.to_route()
        state = self._build_meld_test_state(route.get('source_key', ''))
        source_key = str(route.get('source_key') or '').strip().lower()
        action_keys = set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)
        if source_key in action_keys:
            settings = dict(settings or {})
            settings['meld_routes_json'] = self._manager.save_routes_text([route])
            settings['__prefer_inline_meld_routes'] = True
            trigger_locked = getattr(self.plugin, 'trigger_live_action_test_route', None)
            if callable(trigger_locked):
                ok_count, failed, msg = trigger_locked(settings, state, route, source_key, f'test:{source_key}')
            else:
                ok_count, failed, msg = self._manager.trigger_routes_for_sources(
                    settings, state, getattr(self.plugin, '_obs_export_writer', None), {source_key}
                )
            self._set_status(f'Live action test: {ok_count} OK, {failed} failed. {msg}', error=failed > 0)
            return
        ok, msg = self._manager.test_route(route, settings, state, getattr(self.plugin, '_obs_export_writer', None))
        self._set_status(msg, error=not ok)

    def _test_event_row(self, row: _MeldRouteRow) -> None:
        settings = self.current_settings()
        route = row.to_route()
        source_key = str(route.get('source_key') or '').strip().lower()
        action_keys = set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)
        if source_key not in action_keys:
            self._set_status('Test +1 Event is only for Live actions.', error=True)
            return

        count_key = id(row)
        total = int(self._event_test_counts.get(count_key, 0)) + 1
        self._event_test_counts[count_key] = total

        state = self._build_meld_test_state(source_key)
        state.setdefault('goals', {}).setdefault('likes', {})['current'] = total
        state.setdefault('goals', {}).setdefault('gifts', {})['current'] = total
        latest = state.setdefault('latest', {})
        latest['like_count'] = total
        latest['gift_count'] = total

        is_milestone = source_key in set(LIVE_ACTION_MILESTONE_KEYS) | {'like_milestone_trigger', 'like_milestone_trigger.txt'}
        if is_milestone:
            try:
                step = int(route.get('threshold') or 1)
            except Exception:
                step = 1
            step = max(1, step)
            next_hit = ((total + step - 1) // step) * step
            if total % step != 0:
                self._set_status(f'Test +1 Event: {total}/{next_hit}. Noch kein Milestone, kein Meld-Trigger.')
                return
            if source_key in {'live_action_like_milestone', 'live_action_personal_like_milestone', 'like_milestone_trigger', 'like_milestone_trigger.txt'}:
                latest['like_milestone'] = str(total)
                latest['like_milestone_total'] = total
            elif source_key in {'live_action_gift_milestone', 'live_action_personal_gift_milestone'}:
                latest['gift_milestone'] = str(total)
                latest['gift_milestone_total'] = total

        temp_settings = dict(settings or {})
        temp_settings['meld_routes_json'] = self._manager.save_routes_text([route])
        temp_settings['__prefer_inline_meld_routes'] = True
        label = f'Test +1 Event #{total}'
        trigger_locked = getattr(self.plugin, 'trigger_live_action_test_route', None)
        if callable(trigger_locked):
            ok_count, failed, msg = trigger_locked(temp_settings, state, route, source_key, f'{label}:{source_key}')
        else:
            ok_count, failed, msg = self._manager.trigger_routes_for_sources(
                temp_settings, state, getattr(self.plugin, '_obs_export_writer', None), {source_key}
            )
        if is_milestone:
            label += f' / Step {int(route.get("threshold") or 1)}'
        self._set_status(f'{label}: {ok_count} OK, {failed} failed. {msg}', error=failed > 0 or ok_count == 0)

    def _reset_row(self, row: _MeldRouteRow) -> None:
        settings = self.current_settings()
        route = row.to_route()
        self._event_test_counts.pop(id(row), None)
        state = self._build_meld_reset_state(route.get('source_key', ''))
        ok, msg = self._manager.test_route(route, settings, state, getattr(self.plugin, '_obs_export_writer', None))
        prefix = 'Reset sent. ' if ok else 'Reset failed. '
        self._set_status(prefix + msg, error=not ok)

    def _schedule_autosave(self) -> None:
        if not self._autosave_ready:
            return
        if self._routes_changed_callback is None:
            return
        self._autosave_timer.start()

    def _autosave_routes_now(self) -> None:
        if self._routes_changed_callback is None:
            return
        routes_json = self.routes_json()
        try:
            self._routes_changed_callback(routes_json, self.all_routes())
        except TypeError:
            self._routes_changed_callback(routes_json)
        except Exception as exc:
            self._set_status(f'Live-save failed: {exc}', error=True)
            return

    def current_settings(self) -> dict[str, Any]:
        settings = dict(self._settings_getter() or {})
        settings['meld_routes_json'] = self.routes_json()
        settings['__prefer_inline_meld_routes'] = True
        return settings

    def routes(self) -> list[dict[str, Any]]:
        return [row.to_route() for row in self._rows]

    def all_routes(self) -> list[dict[str, Any]]:
        if self._route_filter is None:
            return self.routes()
        return [dict(route) for route in self._base_routes] + self.routes()

    def routes_json(self) -> str:
        return self._manager.save_routes_text(self.all_routes())
class _PluginSettingsPatcher(QtCore.QObject):
    def __init__(self, plugin: 'TikTokLiveAlertPlugin') -> None:
        super().__init__()
        self.plugin = plugin
        self._dialog: QtWidgets.QDialog | None = None
        self._preview_bridge: _UiBridge | None = None
        self._preview_windows: dict[str, _AlertWindow] = {}
        self._preview_owned: dict[str, bool] = {}
        self._editor_dialogs: list[QtWidgets.QDialog] = []
        self._logging_toggle_btn: QtWidgets.QPushButton | None = None
        self._log_window: QtWidgets.QDialog | None = None
        self._tries = 0
        self._test_counters: dict[str, int] = {}
        self._alert_status_label: QtWidgets.QLabel | None = None

        app = QtWidgets.QApplication.instance()
        if app is not None:
            with contextlib.suppress(Exception):
                app.aboutToQuit.connect(self._cleanup, QtCore.Qt.ConnectionType.QueuedConnection)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._find_and_patch)

    def start(self) -> None:
        if self._dialog is not None and not bool(getattr(self._dialog, 'isVisible', lambda: False)()):
            self._cleanup()
        self._tries = 0
        self._timer.start()

    def _find_and_patch(self) -> None:
        self._tries += 1
        app = QtWidgets.QApplication.instance()
        if app is None:
            self._timer.stop()
            return
        for widget in app.topLevelWidgets():
            if (
                isinstance(widget, QtWidgets.QDialog)
                and self._is_settings_dialog(widget)
                and not widget.property('tiktok_live_alert_patched')
            ):
                self._timer.stop()
                self._patch_dialog(widget)
                return
        if self._tries > 40:
            self._timer.stop()

    def _is_settings_dialog(self, widget: QtWidgets.QWidget) -> bool:
        if not isinstance(widget, QtWidgets.QDialog):
            return False
        if not hasattr(widget, '_widgets') or not hasattr(widget, '_schema'):
            return False
        title = str(widget.windowTitle() or '').strip().casefold()
        display = str(getattr(self.plugin, 'display_name', 'TikTok LIVE Alert') or 'TikTok LIVE Alert').strip().casefold()
        return title in {
            f'{display} settings',
            f'{display} einstellungen',
        } or (display in title and ('settings' in title or 'einstellungen' in title))

    def _patch_dialog(self, dialog: QtWidgets.QDialog) -> None:
        self._dialog = dialog
        dialog.setProperty('tiktok_live_alert_patched', True)
        widgets = getattr(dialog, '_widgets', {})
        schema = getattr(dialog, '_schema', [])
        if not widgets or not schema:
            return

        form = None
        scroll = None
        for child in dialog.findChildren(QtWidgets.QScrollArea):
            scroll = child
            break
        if scroll is not None and scroll.widget() is not None and isinstance(scroll.widget().layout(), QtWidgets.QFormLayout):
            form = scroll.widget().layout()
        if form is None:
            return

        def hide_key(key: str) -> None:
            widget = widgets.get(key)
            if widget is None:
                return
            try:
                label = form.labelForField(widget)
                if label is not None:
                    label.hide()
                widget.hide()
            except Exception:
                pass

        widget_keys = [
            'latest_follower', 'latest_like', 'latest_gift',
            'top_liker', 'top_gifter', 'follower_goal',
            'like_goal', 'gift_goal', 'ticker', 'ticker_2', 'ticker_3',
        ]
        general_hidden_keys = [
            'unique_id', 'autoconnect', 'aggregate_window_seconds', 'state_emit_interval_seconds', 'ranking_size',
            'always_on_top', 'window_opacity', 'enable_follows', 'enable_likes', 'enable_gifts',
            'enable_shares', 'enable_joins', 'enable_subscribes', 'enable_comments', 'logging_enabled',
            'event_enable_controls_initialized',
            'show_alerts_in_desktop', 'show_alerts_in_obs', 'show_comments_in_desktop', 'show_comments_in_obs',
            'meld_host', 'meld_port', 'meld_routes_json',
        ]
        for key in general_hidden_keys:
            hide_key(key)

        hide_prefixes = []
        for key in widget_keys:
            hide_prefixes.extend([
                f'enable_{key}_window', f'enable_{key}_txt', f'{key}_title', f'{key}_x', f'{key}_y', f'{key}_width', f'{key}_height',
                f'{key}_font_family', f'{key}_font_size', f'{key}_text_color', f'{key}_background_color',
                f'{key}_accent_color', f'{key}_title_font_size', f'{key}_corner_radius', f'{key}_show_title',
                f'{key}_text_opacity', f'{key}_background_opacity', f'{key}_bar_height', f'{key}_bar_style',
            ])
        hide_prefixes.extend([
            'follower_goal', 'like_goal', 'gift_goal',
            'follower_goal_progress_style', 'like_goal_progress_style', 'gift_goal_progress_style',
            'ticker_direction', 'ticker_speed', 'ticker_text',
            'ticker_2_direction', 'ticker_2_speed', 'ticker_2_text',
            'ticker_3_direction', 'ticker_3_speed', 'ticker_3_text',
        ])
        for key in widget_keys:
            for item in ['title', 'main', 'secondary', 'progress', 'list', 'ticker']:
                hide_prefixes.extend([
                    f'{key}_{item}_enabled', f'{key}_{item}_x', f'{key}_{item}_y',
                    f'{key}_{item}_w', f'{key}_{item}_h'
                ])
        for key in hide_prefixes:
            hide_key(key)

        # Die alten kleinen Qt-Capture-Fenster bleiben aus Kompatibilitätsgründen
        # als versteckte Settings erhalten, werden aber konsequent deaktiviert.
        for key in widget_keys:
            _widget_set(widgets.get(f'enable_{key}_window'), False)

        _fit_dialog_to_screen(dialog, 720, 780, min_width=560, min_height=520)

        if scroll is not None:
            with contextlib.suppress(Exception):
                scroll.setWidgetResizable(True)
            with contextlib.suppress(Exception):
                scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            with contextlib.suppress(Exception):
                scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            with contextlib.suppress(Exception):
                scroll.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        container = QtWidgets.QGroupBox(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Alert-Ausgaben'))
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setContentsMargins(10, 14, 10, 10)
        vbox.setSpacing(8)

        titles = {
            'latest_follower': 'Latest follower',
            'latest_like': 'Latest like',
            'latest_gift': 'Latest gift',
            'top_liker': 'Top liker',
            'top_gifter': 'Top gifter',
            'follower_goal': 'Follower goal',
            'like_goal': 'Like goal',
            'gift_goal': 'Gift goal',
            'ticker': 'Ticker banner 1',
            'ticker_2': 'Ticker banner 2',
            'ticker_3': 'Ticker banner 3',
        }

        self._element_support = {
            'latest_follower': ['title', 'main'],
            'latest_like': ['title', 'main', 'secondary'],
            'latest_gift': ['title', 'main', 'secondary'],
            'top_liker': ['title', 'list'],
            'top_gifter': ['title', 'list'],
            'follower_goal': ['title', 'main', 'secondary', 'progress'],
            'like_goal': ['title', 'main', 'secondary', 'progress'],
            'gift_goal': ['title', 'main', 'secondary', 'progress'],
            'ticker': ['title', 'ticker'],
            'ticker_2': ['title', 'ticker'],
            'ticker_3': ['title', 'ticker'],
        }

        action_grid = QtWidgets.QGridLayout()
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)

        log_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), '📋 Open Event Log'))
        log_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        log_btn.clicked.connect(self._open_log_window)

        self._logging_toggle_btn = QtWidgets.QPushButton()
        self._logging_toggle_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._logging_toggle_btn.clicked.connect(self._toggle_logging_enabled)
        self._refresh_logging_button()

        self._meld_outputs_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Meld outputs'))
        self._meld_outputs_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._meld_outputs_btn.clicked.connect(self._open_meld_outputs_dialog)

        self._live_actions_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Live actions'))
        self._live_actions_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._live_actions_btn.clicked.connect(self._open_live_actions_dialog)

        self._personal_like_actions_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Personal like actions'))
        self._personal_like_actions_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._personal_like_actions_btn.clicked.connect(self._open_personal_like_actions_dialog)

        action_grid.addWidget(log_btn, 0, 0)
        action_grid.addWidget(self._logging_toggle_btn, 0, 1)
        action_grid.addWidget(self._meld_outputs_btn, 1, 0, 1, 2)
        action_grid.addWidget(self._live_actions_btn, 2, 0)
        action_grid.addWidget(self._personal_like_actions_btn, 2, 1)
        vbox.addLayout(action_grid)

        self._alert_status_label = QtWidgets.QLabel(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Test/Reset schreibt TXT und sendet passende aktivierte Meld-Routen direkt mit.'))
        self._alert_status_label.setWordWrap(True)
        self._alert_status_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        vbox.addWidget(self._alert_status_label)

        event_keys = [
            ('enable_follows', 'Follows'),
            ('enable_likes', 'Likes'),
            ('enable_gifts', 'Gifts'),
            ('enable_shares', 'Shares'),
            ('enable_joins', 'Joins / new viewers'),
            ('enable_subscribes', 'Subscribes / members'),
            ('enable_comments', 'Comments'),
        ]

        widgets = getattr(dialog, '_widgets', {})
        if not _as_bool(_widget_get(widgets.get('event_enable_controls_initialized'), False)):
            for event_key, _label in event_keys:
                _widget_set(widgets.get(event_key), True)
            _widget_set(widgets.get('show_alerts_in_desktop'), True)
            _widget_set(widgets.get('show_comments_in_desktop'), True)
            _widget_set(widgets.get('event_enable_controls_initialized'), True)

        event_box = QtWidgets.QGroupBox('TikTok event alerts')
        event_box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        event_grid = QtWidgets.QGridLayout(event_box)
        event_grid.setContentsMargins(8, 12, 8, 8)
        event_grid.setHorizontalSpacing(8)
        event_grid.setVerticalSpacing(5)
        event_grid.setColumnStretch(0, 0)
        event_grid.setColumnStretch(1, 1)

        self._event_enable_buttons: dict[str, QtWidgets.QAbstractButton] = {}
        for event_row, (event_key, label_text) in enumerate(event_keys):
            btn = QtWidgets.QCheckBox('Enabled')
            btn.setMinimumWidth(92)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
            btn.setChecked(_as_bool(_widget_get(widgets.get(event_key), True)))
            self._style_enable_button(btn)
            btn.toggled.connect(lambda checked, k=event_key, b=btn: self._toggle_event_enabled(k, checked, b))

            label = QtWidgets.QLabel(label_text)
            label.setWordWrap(True)
            label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

            event_grid.addWidget(btn, event_row, 0)
            event_grid.addWidget(label, event_row, 1)
            self._event_enable_buttons[event_key] = btn

        vbox.addWidget(event_box)

        rows_widget = QtWidgets.QWidget()
        rows_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        rows_grid = QtWidgets.QGridLayout(rows_widget)
        rows_grid.setContentsMargins(0, 0, 0, 0)
        rows_grid.setHorizontalSpacing(8)
        rows_grid.setVerticalSpacing(4)
        rows_grid.setColumnStretch(0, 0)
        rows_grid.setColumnStretch(1, 1)
        rows_grid.setColumnStretch(2, 0)
        rows_grid.setColumnStretch(3, 0)
        rows_grid.setColumnStretch(4, 0)
        rows_grid.setColumnStretch(5, 0)

        self._row_controls: dict[str, dict[str, QtWidgets.QWidget]] = {}

        for row_index, key in enumerate(widget_keys):
            enabled_btn = QtWidgets.QCheckBox('Enabled')
            enabled_btn.setMinimumWidth(92)
            enabled_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
            enabled_btn.setChecked(_as_bool(_widget_get(widgets.get(f'enable_{key}_txt'), True)))
            self._style_enable_button(enabled_btn)

            label = QtWidgets.QLabel(titles[key])
            label.setWordWrap(True)
            label.setMinimumWidth(110)
            label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

            txt_checkbox = QtWidgets.QCheckBox('TXT')
            txt_checkbox.setChecked(_as_bool(_widget_get(widgets.get(f'enable_{key}_txt'), True)))
            txt_checkbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

            test_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Test'))
            test_btn.setMinimumWidth(58)
            test_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

            edit_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Edit'))
            edit_btn.setMinimumWidth(62)
            edit_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
            edit_btn.setEnabled(txt_checkbox.isChecked())

            reset_btn = QtWidgets.QPushButton(_tr(getattr(self.plugin, 'ui_language', 'de'), 'Reset'))
            reset_btn.setMinimumWidth(64)
            reset_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

            enabled_btn.toggled.connect(lambda checked, k=key, b=edit_btn, ebtn=enabled_btn, txt=txt_checkbox: self._toggle_output_enabled(k, checked, b, ebtn, txt))
            txt_checkbox.toggled.connect(lambda checked, k=key, b=edit_btn, ebtn=enabled_btn: self._toggle_output_enabled(k, checked, b, ebtn, None))
            edit_btn.clicked.connect(lambda _=False, k=key: self._edit_widget(k))
            test_btn.clicked.connect(lambda _=False, k=key: self._test_widget(k))
            reset_btn.clicked.connect(lambda _=False, k=key: self._reset_widget(k))

            rows_grid.addWidget(enabled_btn, row_index, 0)
            rows_grid.addWidget(label, row_index, 1)
            rows_grid.addWidget(test_btn, row_index, 2)
            rows_grid.addWidget(reset_btn, row_index, 3)
            rows_grid.addWidget(txt_checkbox, row_index, 4, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
            rows_grid.addWidget(edit_btn, row_index, 5)

            self._row_controls[key] = {
                'enabled': enabled_btn,
                'test': test_btn,
                'reset': reset_btn,
                'txt': txt_checkbox,
                'edit': edit_btn,
            }
            self._sync_hidden_checkbox(key, txt_checkbox.isChecked(), False)

        vbox.addWidget(rows_widget)

        # Wichtig: Der kompakte Alert-Block muss IN die vorhandene ScrollArea.
        # Vorher lag er direkt im Dialog-Root; dadurch konnte er bei kleineren
        # Fenstern nicht mitscrollen und sah aus, als würde der Inhalt nicht skalieren.
        try:
            form.insertRow(0, container)
        except Exception:
            root = dialog.layout()
            if root is not None:
                root.setContentsMargins(8, 8, 8, 8)
                root.setSpacing(6)
                root.insertWidget(1, container)

        root = dialog.layout()
        if root is not None:
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(6)

        _disable_combo_wheel_in(dialog)

        self.plugin.logger.set_enabled(_as_bool(_widget_get(widgets.get('logging_enabled'), False)))
        self._refresh_logging_button()
        self._refresh_meld_outputs_button()
        self._refresh_live_actions_button()
        self._refresh_personal_like_actions_button()
        self._refresh_personal_like_actions_button()

        dialog.destroyed.connect(lambda *args: self._cleanup())
        self._refresh_previews()

    def _style_enable_button(self, button: QtWidgets.QAbstractButton | None) -> None:
        if button is None:
            return
        enabled = bool(button.isChecked())
        button.setText('Enabled' if enabled else 'Disabled')
        # Keep the native checkbox look so it matches the TXT toggle beside Reset.
        # No green/red custom QPushButton styling here.
        with contextlib.suppress(Exception):
            button.setStyleSheet('')
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _toggle_event_enabled(self, key: str, checked: bool, button: QtWidgets.QAbstractButton | None = None) -> None:
        if self._dialog is None:
            return
        widgets = getattr(self._dialog, '_widgets', {})
        _widget_set(widgets.get(key), checked)

        # Keep visible routing alive for the matching event class. Alerts go to the
        # desktop alert area, comments go to the normal chat/comment area.
        if key == 'enable_comments':
            _widget_set(widgets.get('show_comments_in_desktop'), True)
        else:
            _widget_set(widgets.get('show_alerts_in_desktop'), True)

        if button is not None:
            self._style_enable_button(button)

        with contextlib.suppress(Exception):
            self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _open_log_window(self) -> None:
        if not self.plugin.logger:
            return
        if self._log_window is not None:
            with contextlib.suppress(Exception):
                if self._log_window.isVisible():
                    self._log_window.show()
                    self._log_window.raise_()
                    self._log_window.activateWindow()
                    return

        from tiktok_live_alert_logging import _LogWindow

        self._log_window = _LogWindow(self.plugin.logger, self._dialog)
        self._log_window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._log_window.destroyed.connect(lambda *_: setattr(self, '_log_window', None))
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def _refresh_logging_button(self) -> None:
        button = getattr(self, '_logging_toggle_btn', None)
        if button is None:
            return
        enabled = (
            bool(_widget_get(getattr(self._dialog, '_widgets', {}).get('logging_enabled'), False))
            if self._dialog is not None
            else bool(self.plugin.logger.enabled)
        )
        button.setText('Disable logging' if enabled else 'Enable logging')

    def _toggle_logging_enabled(self) -> None:
        if self._dialog is None:
            return
        widgets = getattr(self._dialog, '_widgets', {})
        current = _as_bool(_widget_get(widgets.get('logging_enabled'), False))
        new_value = not current
        _widget_set(widgets.get('logging_enabled'), new_value)
        self.plugin.logger.set_enabled(new_value)
        self._refresh_logging_button()
        self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _refresh_meld_outputs_button(self) -> None:
        button = getattr(self, '_meld_outputs_btn', None)
        if button is None:
            return
        manager = getattr(self.plugin, '_meld_output_manager', None) or MeldOutputManager(getattr(self.plugin, 'logger', None), self.plugin)
        routes = manager.load_routes(self._collect_settings())
        # Important: this button is only for normal Meld text outputs. Live Actions
        # share the same route file, but they must not be counted here, otherwise
        # the number is wrong and it looks like phantom Meld Output entries exist.
        action_keys = set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)
        count = sum(
            1 for route in routes
            if route.get('enabled') and str(route.get('source_key') or '').strip().lower() not in action_keys
        )
        button.setText(f'Meld outputs ({count})')

    def _refresh_live_actions_button(self) -> None:
        button = getattr(self, '_live_actions_btn', None)
        if button is None:
            return
        manager = getattr(self.plugin, '_meld_output_manager', None) or MeldOutputManager(getattr(self.plugin, 'logger', None), self.plugin)
        routes = manager.load_routes(self._collect_settings())
        action_keys = (set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)) - {'live_action_personal_like_milestone', 'live_action_personal_gift_milestone'}
        count = sum(
            1 for route in routes
            if route.get('enabled') and str(route.get('source_key') or '').strip().lower() in action_keys
        )
        button.setText(f"{_tr(getattr(self.plugin, 'ui_language', 'de'), 'Live actions')} ({count})")

    def _refresh_personal_like_actions_button(self) -> None:
        button = getattr(self, '_personal_like_actions_btn', None)
        if button is None:
            return
        manager = getattr(self.plugin, '_meld_output_manager', None) or MeldOutputManager(getattr(self.plugin, 'logger', None), self.plugin)
        routes = manager.load_routes(self._collect_settings())
        count = sum(
            1 for route in routes
            if route.get('enabled') and str(route.get('source_key') or '').strip().lower() in {'live_action_personal_like_milestone', 'live_action_personal_gift_milestone'}
        )
        button.setText(f"{_tr(getattr(self.plugin, 'ui_language', 'de'), 'Personal like actions')} ({count})")

    def _persist_meld_routes_external(self, routes_json: str, routes: list[dict[str, Any]] | None = None) -> str:
        manager = getattr(self.plugin, '_meld_output_manager', None) or MeldOutputManager(getattr(self.plugin, 'logger', None), self.plugin)
        actual_routes = routes
        if actual_routes is None:
            try:
                data = json.loads(str(routes_json or '[]'))
                actual_routes = data if isinstance(data, list) else []
            except Exception:
                actual_routes = []
        with contextlib.suppress(Exception):
            manager.save_routes_to_file(actual_routes, self._collect_settings())
        live_json = manager.save_routes_text(actual_routes)
        setattr(self.plugin, '_live_meld_routes_json', live_json)
        return manager.routes_file_marker(self._collect_settings())

    def _open_meld_outputs_dialog(self) -> None:
        if self._dialog is None:
            return

        def live_routes_changed(routes_json: str, _routes: list[dict[str, Any]] | None = None) -> None:
            widgets = getattr(self._dialog, '_widgets', {}) if self._dialog is not None else {}
            marker = self._persist_meld_routes_external(routes_json, _routes)
            _widget_set(widgets.get('meld_routes_json'), marker)
            with contextlib.suppress(Exception):
                self.plugin._last_state_hash = ''
            self._refresh_meld_outputs_button()
            self._refresh_live_actions_button()
            self._refresh_personal_like_actions_button()

        action_keys = set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)

        def is_regular_meld_output(route: dict[str, Any]) -> bool:
            return str(route.get('source_key') or '').strip().lower() not in action_keys

        dlg = _MeldOutputsDialog(
            self.plugin,
            self._collect_settings,
            self._sample_state,
            self._dialog,
            routes_changed_callback=live_routes_changed,
            route_filter=is_regular_meld_output,
        )
        result = dlg.exec()
        widgets = getattr(self._dialog, '_widgets', {})
        marker = self._persist_meld_routes_external(dlg.routes_json(), dlg.all_routes())
        _widget_set(widgets.get('meld_routes_json'), marker)
        with contextlib.suppress(Exception):
            self.plugin._last_state_hash = ''
        self._refresh_meld_outputs_button()
        self._refresh_live_actions_button()
        self._refresh_personal_like_actions_button()
        self._refresh_personal_like_actions_button()
        if result == int(QtWidgets.QDialog.DialogCode.Accepted):
            self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _open_live_actions_dialog(self) -> None:
        if self._dialog is None:
            return

        action_keys = (set(LIVE_ACTION_SOURCE_KEYS) | set(LEGACY_ACTION_SOURCE_KEYS)) - {'live_action_personal_like_milestone', 'live_action_personal_gift_milestone'}

        def is_live_action_route(route: dict[str, Any]) -> bool:
            return str(route.get('source_key') or '').strip().lower() in action_keys

        def live_routes_changed(routes_json: str, _routes: list[dict[str, Any]] | None = None) -> None:
            widgets = getattr(self._dialog, '_widgets', {}) if self._dialog is not None else {}
            marker = self._persist_meld_routes_external(routes_json, _routes)
            _widget_set(widgets.get('meld_routes_json'), marker)
            with contextlib.suppress(Exception):
                self.plugin._last_state_hash = ''
            self._refresh_meld_outputs_button()
            self._refresh_live_actions_button()
            self._refresh_personal_like_actions_button()

        default_route = {
            'enabled': True,
            'source_key': 'live_action_like_milestone',
            'scene_id': '',
            'scene_name': '',
            'layer_id': '',
            'layer_name': '',
            'property_name': 'show_hide_once',
            'template': '{value}',
            'restore_delay': '8',
            'threshold': 200,
        }
        dlg = _MeldOutputsDialog(
            self.plugin,
            self._collect_settings,
            self._sample_state,
            self._dialog,
            routes_changed_callback=live_routes_changed,
            title='Live actions',
            default_route=default_route,
            route_filter=is_live_action_route,
            row_fixed_source_key=None,
            row_show_source=True,
            add_button_text='+ New Entry',
            source_options=[x for x in LIVE_ACTION_SOURCE_OPTIONS if x[0] != 'live_action_personal_like_milestone'],
            show_threshold=True,
        )
        result = dlg.exec()
        widgets = getattr(self._dialog, '_widgets', {})
        marker = self._persist_meld_routes_external(dlg.routes_json(), dlg.all_routes())
        _widget_set(widgets.get('meld_routes_json'), marker)
        with contextlib.suppress(Exception):
            self.plugin._last_state_hash = ''
        self._refresh_meld_outputs_button()
        self._refresh_live_actions_button()
        self._refresh_personal_like_actions_button()
        self._refresh_personal_like_actions_button()
        if result == int(QtWidgets.QDialog.DialogCode.Accepted):
            self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _open_personal_like_actions_dialog(self) -> None:
        if self._dialog is None:
            return

        def is_personal_like_route(route: dict[str, Any]) -> bool:
            return str(route.get('source_key') or '').strip().lower() in {'live_action_personal_like_milestone', 'live_action_personal_gift_milestone'}

        def personal_routes_changed(routes_json: str, _routes: list[dict[str, Any]] | None = None) -> None:
            widgets = getattr(self._dialog, '_widgets', {}) if self._dialog is not None else {}
            marker = self._persist_meld_routes_external(routes_json, _routes)
            _widget_set(widgets.get('meld_routes_json'), marker)
            with contextlib.suppress(Exception):
                self.plugin._last_state_hash = ''
            self._refresh_meld_outputs_button()
            self._refresh_live_actions_button()
            self._refresh_personal_like_actions_button()

        default_route = {
            'enabled': True,
            'source_key': 'live_action_personal_like_milestone',
            'scene_id': '',
            'scene_name': '',
            'layer_id': '',
            'layer_name': '',
            'property_name': 'show_hide_once',
            'template': '{value}',
            'restore_delay': '8',
            'threshold': 1000,
            'target_user': '',
        }
        dlg = _MeldOutputsDialog(
            self.plugin,
            self._collect_settings,
            self._sample_state,
            self._dialog,
            routes_changed_callback=personal_routes_changed,
            title='Personal actions',
            default_route=default_route,
            route_filter=is_personal_like_route,
            row_fixed_source_key=None,
            row_show_source=True,
            add_button_text='+ New Entry',
            source_options=[('live_action_personal_like_milestone', 'Personal Like Milestone'), ('live_action_personal_gift_milestone', 'Personal Gift Milestone')],
            show_threshold=True,
            show_target_user=True,
        )
        result = dlg.exec()
        widgets = getattr(self._dialog, '_widgets', {})
        marker = self._persist_meld_routes_external(dlg.routes_json(), dlg.all_routes())
        _widget_set(widgets.get('meld_routes_json'), marker)
        with contextlib.suppress(Exception):
            self.plugin._last_state_hash = ''
        self._refresh_meld_outputs_button()
        self._refresh_live_actions_button()
        self._refresh_personal_like_actions_button()
        if result == int(QtWidgets.QDialog.DialogCode.Accepted):
            self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _collect_settings(self) -> dict[str, Any]:
        widgets = getattr(self._dialog, '_widgets', {}) if self._dialog is not None else {}
        out = {}
        for key, widget in widgets.items():
            out[key] = _widget_get(widget, '')
        return out

    def _sample_state(self) -> dict[str, Any]:
        settings = self._collect_settings()
        return {
            'channel': settings.get('unique_id') or '@sample',
            'latest': {
                'follower': 'your name here',
                'like_user': 'your name here',
                'like_count': 42,
                'gift_user': 'your name here',
                'gift_name': 'Rose',
                'gift_count': 7,
            },
            'goals': {
                'followers': {'current': 321, 'target': max(1, int(settings.get('follower_goal') or 1000))},
                'likes': {'current': 6543, 'target': max(1, int(settings.get('like_goal') or 10000))},
                'gifts': {'current': 18, 'target': max(1, int(settings.get('gift_goal') or 100))},
            },
            'rankings': {
                'likers': [],
                'gifters': [],
            },
            'ticker': {
                'text': str(settings.get('ticker_text') or ''),
                'text_2': str(settings.get('ticker_2_text') or ''),
                'text_3': str(settings.get('ticker_3_text') or ''),
                'direction': str(settings.get('ticker_direction') or 'left'),
                'direction_2': str(settings.get('ticker_2_direction') or 'right'),
                'direction_3': str(settings.get('ticker_3_direction') or 'bounce_left'),
                'speed': float(settings.get('ticker_speed') or 80),
                'speed_2': float(settings.get('ticker_2_speed') or 80),
                'speed_3': float(settings.get('ticker_3_speed') or 70),
            },
        }


    def _next_test_number(self, key: str) -> int:
        key = str(key or 'test')
        value = int(self._test_counters.get(key, 0)) + 1
        self._test_counters[key] = value
        return value

    def _reset_test_number(self, key: str) -> None:
        self._test_counters[str(key or 'test')] = 0

    def _format_test_name(self, label: str, number: int) -> str:
        return f'{label} {number:03d}'

    def _set_alert_status(self, text: str, error: bool = False) -> None:
        label = getattr(self, '_alert_status_label', None)
        if label is not None:
            label.setText(str(text or ''))
            pal = label.palette()
            pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor('#ff9a9a' if error else '#b9ffcf'))
            label.setPalette(pal)
        if self.plugin is not None and getattr(self.plugin, 'logger', None) is not None:
            with contextlib.suppress(Exception):
                if error:
                    self.plugin.logger.warning(str(text or ''))
                else:
                    self.plugin.logger.info(str(text or ''))



    def _clear_test_state(self) -> None:
        self._last_test_state = None

    def _build_test_state(self, key: str) -> dict[str, Any]:
        settings = self._collect_settings()
        number = self._next_test_number(key)
        n = f'{number:03d}'
        follower = self._format_test_name('Follower Test', number)
        like_user = self._format_test_name('Like Test', number)
        gift_user = self._format_test_name('Gift Test', number)
        top_liker = f'sadly not you {n}'
        top_gifter = f'sadly not you {n}'
        follower_target = max(1, int(settings.get('follower_goal') or 1000))
        like_target = max(1, int(settings.get('like_goal') or 10000))
        gift_target = max(1, int(settings.get('gift_goal') or 100))
        state = {
            'channel': settings.get('unique_id') or '@sample',
            'latest': {
                'follower': follower,
                'like_user': like_user,
                'like_count': 100 + number,
                'gift_user': gift_user,
                'gift_name': f'Rose {n}',
                'gift_count': 1 + (number % 9),
            },
            'goals': {
                'followers': {'current': min(follower_target, number), 'target': follower_target},
                'likes': {'current': min(like_target, number * 100), 'target': like_target},
                'gifts': {'current': min(gift_target, number), 'target': gift_target},
            },
            'rankings': {
                'likers': [
                    {'name': top_liker, 'count': 1000 + number},
                    {'name': f'sadly runner up {n}', 'count': 500 + number},
                    {'name': f'sadly third place {n}', 'count': 250 + number},
                ],
                'gifters': [
                    {'name': top_gifter, 'count': 100 + number},
                    {'name': f'sadly runner up {n}', 'count': 50 + number},
                    {'name': f'sadly third place {n}', 'count': 25 + number},
                ],
            },
            'ticker': {
                'text': f'Ticker 1 Test {n}',
                'text_2': f'Ticker 2 Test {n}',
                'text_3': f'Ticker 3 Test {n}',
                'direction': str(settings.get('ticker_direction') or 'left'),
                'direction_2': str(settings.get('ticker_2_direction') or 'right'),
                'direction_3': str(settings.get('ticker_3_direction') or 'bounce_left'),
                'speed': float(settings.get('ticker_speed') or 80),
                'speed_2': float(settings.get('ticker_2_speed') or 80),
                'speed_3': float(settings.get('ticker_3_speed') or 70),
            },
        }

        if key == 'latest_follower':
            state['latest']['follower'] = self._format_test_name('your name here', number)
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'latest_like':
            state['latest']['like_user'] = self._format_test_name('Latest Like', number)
            state['latest']['like_count'] = 100 + number
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'latest_gift':
            state['latest']['gift_user'] = self._format_test_name('Latest Gift', number)
            state['latest']['gift_name'] = f'Galaxy {n}'
            state['latest']['gift_count'] = 1 + (number % 9)
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'top_liker':
            state['latest']['follower'] = ''
            state['latest']['like_user'] = ''
            state['latest']['gift_user'] = ''
            state['rankings']['gifters'] = []
        elif key == 'top_gifter':
            state['latest']['follower'] = ''
            state['latest']['like_user'] = ''
            state['latest']['gift_user'] = ''
            state['rankings']['likers'] = []
        elif key == 'follower_goal':
            state['goals']['followers']['current'] = min(follower_target, max(1, number))
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'like_goal':
            state['goals']['likes']['current'] = min(like_target, max(1, number * 100))
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'gift_goal':
            state['goals']['gifts']['current'] = min(gift_target, max(1, number))
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'ticker':
            state['ticker']['text'] = f'Ticker 1 Test {n}'
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'ticker_2':
            state['ticker']['text_2'] = f'Ticker 2 Test {n}'
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []
        elif key == 'ticker_3':
            state['ticker']['text_3'] = f'Ticker 3 Test {n}'
            state['rankings']['likers'] = []
            state['rankings']['gifters'] = []

        return state

    def _build_reset_state(self, key: str) -> dict[str, Any]:
        settings = self._collect_settings()
        follower_target = max(0, int(settings.get('follower_goal') or 0))
        like_target = max(0, int(settings.get('like_goal') or 0))
        gift_target = max(0, int(settings.get('gift_goal') or 0))
        return {
            'channel': settings.get('unique_id') or '@sample',
            'latest': {
                'follower': 'your name here',
                'like_user': 'your name here',
                'like_count': 0,
                'gift_user': 'your name here',
                'gift_name': 'gift',
                'gift_count': 0,
            },
            'goals': {
                'followers': {'current': 0, 'target': follower_target},
                'likes': {'current': 0, 'target': like_target},
                'gifts': {'current': 0, 'target': gift_target},
            },
            'rankings': {'likers': [], 'gifters': []},
            'ticker': {
                'text': 'ticker ready',
                'text_2': 'ticker 2 ready',
                'text_3': 'ticker 3 ready',
                'direction': str(settings.get('ticker_direction') or 'left'),
                'direction_2': str(settings.get('ticker_2_direction') or 'right'),
                'direction_3': str(settings.get('ticker_3_direction') or 'bounce_left'),
                'speed': float(settings.get('ticker_speed') or 80),
                'speed_2': float(settings.get('ticker_2_speed') or 80),
                'speed_3': float(settings.get('ticker_3_speed') or 70),
            },
        }


    def _widget_export_files(self, key: str) -> list[str]:
        mapping = {
            'latest_follower': ['latest_follower.txt', 'new_follower.txt'],
            'latest_like': ['latest_like.txt'],
            'latest_gift': ['latest_gift.txt'],
            'top_liker': ['top_liker.txt', 'top_liker_leader.txt', 'top_liker_list.txt'],
            'top_gifter': ['top_gifter.txt', 'top_gifter_leader.txt', 'top_gifter_list.txt'],
            'follower_goal': ['follower_goal.txt', 'follower_goal_percent.txt', 'follower_goal_current.txt', 'follower_goal_target.txt'],
            'like_goal': ['like_goal.txt', 'like_goal_percent.txt', 'like_goal_current.txt', 'like_goal_target.txt'],
            'gift_goal': ['gift_goal.txt', 'gift_goal_percent.txt', 'gift_goal_current.txt', 'gift_goal_target.txt'],
            'ticker': ['ticker.txt'],
            'ticker_2': ['ticker_2.txt'],
            'ticker_3': ['ticker_3.txt'],
        }
        return list(mapping.get(key, []))

    def _write_widget_test_exports(self, key: str, settings: dict[str, Any], state: dict[str, Any]) -> list[str]:
        writer = getattr(self.plugin, '_obs_export_writer', None)
        written: list[str] = []
        if writer is None:
            return written

        settings_for_export = dict(settings or {})
        settings_for_export[f'enable_{key}_txt'] = True
        if key == 'ticker':
            settings_for_export['ticker_text'] = str((state.get('ticker') or {}).get('text') or 'ticker ready')
        elif key == 'ticker_2':
            settings_for_export['ticker_2_text'] = str((state.get('ticker') or {}).get('text_2') or 'ticker 2 ready')
        elif key == 'ticker_3':
            settings_for_export['ticker_3_text'] = str((state.get('ticker') or {}).get('text_3') or 'ticker 3 ready')

        payloads = writer._build_payloads(state, settings_for_export)
        export_dir = writer.ensure_dir()
        for name in self._widget_export_files(key):
            content = payloads.get(name, '')
            with contextlib.suppress(Exception):
                writer._write_text_atomic(export_dir / name, content)
                written.append(name)
        return written

    def _send_widget_to_meld(self, key: str, settings: dict[str, Any], state: dict[str, Any]) -> tuple[int, int, str]:
        writer = getattr(self.plugin, '_obs_export_writer', None)
        manager = getattr(self.plugin, '_meld_output_manager', None)
        if writer is None or manager is None:
            return 0, 0, 'Meld manager/writer not ready'
        files = set(self._widget_export_files(key))
        settings_for_meld = dict(settings or {})
        if key == 'ticker':
            settings_for_meld['ticker_text'] = str((state.get('ticker') or {}).get('text') or 'ticker ready')
        elif key == 'ticker_2':
            settings_for_meld['ticker_2_text'] = str((state.get('ticker') or {}).get('text_2') or 'ticker 2 ready')
        elif key == 'ticker_3':
            settings_for_meld['ticker_3_text'] = str((state.get('ticker') or {}).get('text_3') or 'ticker 3 ready')
        try:
            return manager.apply_routes_for_sources(settings_for_meld, state, writer, files)
        except Exception as exc:
            return 0, 1, str(exc)

    def _apply_widget_test_preview(self, key: str, settings: dict[str, Any], state: dict[str, Any]) -> None:
        preview = self._preview_windows.get(key)
        if preview is not None:
            with contextlib.suppress(Exception):
                preview.update_settings(settings, state)
                preview.show()

    def _test_widget(self, key: str) -> None:
        state = self._build_test_state(key)
        settings = self._collect_settings()
        self._clear_test_state()
        self._apply_widget_test_preview(key, settings, state)
        written = self._write_widget_test_exports(key, settings, state)
        ok_count, failed_count, meld_msg = self._send_widget_to_meld(key, settings, state)
        if ok_count:
            self._set_alert_status(f'Test {key}: TXT geschrieben ({len(written)} Datei(en)); Meld gesendet {ok_count} Route(n). {meld_msg}')
        elif failed_count:
            self._set_alert_status(f'Test {key}: TXT geschrieben ({len(written)} Datei(en)); Meld Fehler: {meld_msg}', error=True)
        else:
            self._set_alert_status(f'Test {key}: TXT geschrieben ({len(written)} Datei(en)); Meld: {meld_msg}')

    def _reset_widget(self, key: str) -> None:
        self._reset_test_number(key)
        state = self._build_reset_state(key)
        settings = self._collect_settings()
        self._clear_test_state()
        self._apply_widget_test_preview(key, settings, state)
        written = self._write_widget_test_exports(key, settings, state)
        ok_count, failed_count, meld_msg = self._send_widget_to_meld(key, settings, state)
        if ok_count:
            self._set_alert_status(f'Reset {key}: TXT zurückgesetzt ({len(written)} Datei(en)); Meld gesendet {ok_count} Route(n). {meld_msg}')
        elif failed_count:
            self._set_alert_status(f'Reset {key}: TXT zurückgesetzt ({len(written)} Datei(en)); Meld Fehler: {meld_msg}', error=True)
        else:
            self._set_alert_status(f'Reset {key}: TXT zurückgesetzt ({len(written)} Datei(en)); Meld: {meld_msg}')

    def _sync_hidden_checkbox(self, key: str, txt_checked: bool | None = None, window_checked: bool | None = None) -> None:
        widgets = getattr(self._dialog, '_widgets', {}) if self._dialog is not None else {}
        if txt_checked is not None:
            _widget_set(widgets.get(f'enable_{key}_txt'), txt_checked)
        if window_checked is not None:
            _widget_set(widgets.get(f'enable_{key}_window'), window_checked)

    def _update_row_edit_enabled(self, key: str) -> None:
        controls = getattr(self, '_row_controls', {}).get(key, {})
        edit_btn = controls.get('edit')
        txt_checkbox = controls.get('txt')
        if edit_btn is None:
            return
        txt_enabled = bool(txt_checkbox.isChecked()) if txt_checkbox is not None else False
        edit_btn.setEnabled(txt_enabled)

    def _toggle_widget_txt(self, key: str, checked: bool, button: QtWidgets.QPushButton) -> None:
        self._clear_test_state()
        self._sync_hidden_checkbox(key, txt_checked=checked)
        self._update_row_edit_enabled(key)
        self._refresh_previews()

        with contextlib.suppress(Exception):
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.processEvents()

        QtCore.QTimer.singleShot(0, lambda: self._apply_live_settings(self._collect_settings(), self._sample_state()))

    def _toggle_output_enabled(
        self,
        key: str,
        checked: bool,
        edit_button: QtWidgets.QPushButton | None,
        enable_button: QtWidgets.QAbstractButton | None,
        txt_checkbox: QtWidgets.QCheckBox | None,
    ) -> None:
        if enable_button is not None and enable_button.isChecked() != checked:
            with contextlib.suppress(Exception):
                enable_button.blockSignals(True)
                enable_button.setChecked(checked)
                enable_button.blockSignals(False)
        if txt_checkbox is not None and txt_checkbox.isChecked() != checked:
            with contextlib.suppress(Exception):
                txt_checkbox.blockSignals(True)
                txt_checkbox.setChecked(checked)
                txt_checkbox.blockSignals(False)
        if enable_button is not None:
            self._style_enable_button(enable_button)
        self._toggle_widget_txt(key, checked, edit_button)

    def _toggle_widget_window(self, key: str, checked: bool, button: QtWidgets.QPushButton) -> None:
        self._clear_test_state()
        self._sync_hidden_checkbox(key, window_checked=False)
        self._close_preview(key)
        self._refresh_previews()

        with contextlib.suppress(Exception):
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.processEvents()

        QtCore.QTimer.singleShot(0, lambda: self._apply_live_settings(self._collect_settings(), self._sample_state()))

    def _bindings_for(self, key: str) -> dict[str, QtWidgets.QWidget]:
        widgets = getattr(self._dialog, '_widgets', {}) if self._dialog is not None else {}
        bindings = {
            'title': widgets.get(f'{key}_title'),
            'font_family': widgets.get(f'{key}_font_family'),
            'font_size': widgets.get(f'{key}_font_size'),
            'title_font_size': widgets.get(f'{key}_title_font_size'),
            'text_color': widgets.get(f'{key}_text_color'),
            'background_color': widgets.get(f'{key}_background_color'),
            'accent_color': widgets.get(f'{key}_accent_color'),
            'x': widgets.get(f'{key}_x'),
            'y': widgets.get(f'{key}_y'),
            'width': widgets.get(f'{key}_width'),
            'height': widgets.get(f'{key}_height'),
            'corner_radius': widgets.get(f'{key}_corner_radius'),
            'show_title': widgets.get(f'{key}_show_title'),
            'text_opacity': widgets.get(f'{key}_text_opacity'),
            'background_opacity': widgets.get(f'{key}_background_opacity'),
            'bar_height': widgets.get(f'{key}_bar_height'),
            'bar_style': widgets.get(f'{key}_bar_style'),
        }
        bindings['item_enabled'] = {
            item: widgets.get(f'{key}_{item}_enabled')
            for item in ['title', 'main', 'secondary', 'progress', 'list', 'ticker']
        }
        bindings['supported_items'] = list(self._element_support.get(key, ['title', 'main']))

        if key.startswith('ticker'):
            suffix = '' if key == 'ticker' else key.replace('ticker', '')
            bindings['ticker_direction'] = widgets.get(f'ticker{suffix}_direction')
            bindings['ticker_speed'] = widgets.get(f'ticker{suffix}_speed')
            bindings['ticker_text'] = widgets.get(f'ticker{suffix}_text')

        if key == 'follower_goal':
            bindings['goal_target'] = widgets.get('follower_goal')
            bindings['progress_style'] = widgets.get('follower_goal_progress_style')
        elif key == 'like_goal':
            bindings['goal_target'] = widgets.get('like_goal')
            bindings['progress_style'] = widgets.get('like_goal_progress_style')
        elif key == 'gift_goal':
            bindings['goal_target'] = widgets.get('gift_goal')
            bindings['progress_style'] = widgets.get('gift_goal_progress_style')

        return bindings

    def _edit_widget(self, key: str) -> None:
        if self._dialog is None:
            return

        controls = getattr(self, '_row_controls', {}).get(key, {})
        txt_checkbox = controls.get('txt')
        self._sync_hidden_checkbox(key, txt_checkbox.isChecked() if txt_checkbox is not None else None, False)
        title = key.replace('_', ' ').title()

        preview = None

        for existing in list(self._editor_dialogs):
            try:
                existing_key = existing.property('widget_key')
                if existing_key == key and existing.isVisible():
                    existing.show()
                    existing.raise_()
                    existing.activateWindow()
                    return
                if existing.isVisible():
                    existing.close()
            except Exception:
                pass

        self._editor_dialogs = [dlg for dlg in self._editor_dialogs if bool(getattr(dlg, 'isVisible', lambda: False)())]

        try:
            dlg = _WidgetSettingsEditor(
                title,
                self._bindings_for(key),
                preview,
                self._collect_settings,
                self._sample_state,
                self._apply_live_settings,
                None,  # absichtlich unabhängig, damit Preview weiter anklickbar bleibt
            )
            dlg.setProperty('widget_key', key)
            dlg.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dlg.setWindowFlags(
                QtCore.Qt.WindowType.Window
                | QtCore.Qt.WindowType.WindowTitleHint
                | QtCore.Qt.WindowType.CustomizeWindowHint
                | QtCore.Qt.WindowType.WindowCloseButtonHint
            )
            dlg.setWindowModality(QtCore.Qt.WindowModality.NonModal)
            dlg.setModal(False)

            parent_geo = self._dialog.frameGeometry()
            dlg.adjustSize()
            target = parent_geo.center() - dlg.rect().center()
            dlg.move(max(0, target.x()), max(0, target.y()))
        except Exception as exc:
            if preview is not None:
                preview.set_edit_mode(False)
            QtWidgets.QMessageBox.critical(
                self._dialog,
                'TikTok LIVE Alert',
                'Could not open settings for {}.\n\n{}'.format(title, exc),
            )
            return

        def _finish(result: int) -> None:
            if preview is not None:
                with contextlib.suppress(Exception):
                    preview.set_edit_mode(False)
            if result == int(QtWidgets.QDialog.DialogCode.Accepted):
                self._clear_test_state()
            self._refresh_previews()
            with contextlib.suppress(Exception):
                if dlg in self._editor_dialogs:
                    self._editor_dialogs.remove(dlg)

        self._editor_dialogs = [dlg for dlg in self._editor_dialogs if bool(getattr(dlg, 'isVisible', lambda: False)())]
        self._editor_dialogs.append(dlg)
        dlg.finished.connect(_finish)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _find_runtime_window(self, key: str):
        for win in list(getattr(self.plugin, '_windows', []) or []):
            if getattr(win, 'widget_key', None) == key:
                return win
        return None

    def _ensure_preview(self, key: str, refresh: bool = False) -> None:
        # Legacy preview/capture windows are disabled. Editing now updates TXT/Meld
        # output settings directly without opening an additional floating window.
        if refresh:
            self._close_preview(key)
        return

    def _close_preview(self, key: str) -> None:
        win = self._preview_windows.pop(key, None)
        owned = self._preview_owned.pop(key, False)
        if win is not None:
            with contextlib.suppress(Exception):
                win.set_edit_mode(False)
            if owned:
                with contextlib.suppress(Exception):
                    win.close()
                    win.deleteLater()

    def _preview_geometry_changed(self, key: str, x: int, y: int, w: int, h: int) -> None:
        if self._dialog is None:
            return
        widgets = getattr(self._dialog, '_widgets', {}) or {}
        _widget_set(widgets.get(f'{key}_x'), x)
        _widget_set(widgets.get(f'{key}_y'), y)
        _widget_set(widgets.get(f'{key}_width'), w)
        _widget_set(widgets.get(f'{key}_height'), h)
        self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _preview_item_geometry_changed(self, key: str, item_key: str, x: int, y: int, w: int, h: int) -> None:
        if self._dialog is None:
            return
        widgets = getattr(self._dialog, '_widgets', {}) or {}
        _widget_set(widgets.get(f'{key}_{item_key}_x'), x)
        _widget_set(widgets.get(f'{key}_{item_key}_y'), y)
        _widget_set(widgets.get(f'{key}_{item_key}_w'), w)
        _widget_set(widgets.get(f'{key}_{item_key}_h'), h)
        self._apply_live_settings(self._collect_settings(), self._sample_state())

    def _refresh_previews(self) -> None:
        settings = self._collect_settings()
        sample = self._sample_state()
        for win in list(self._preview_windows.values()):
            with contextlib.suppress(Exception):
                win.update_settings(settings, sample)
        if self._preview_bridge is not None:
            self._preview_bridge.state_updated.emit(sample)
        self._apply_live_settings(settings, sample)

    def _write_all_exports_for_settings(self, settings: dict[str, Any], sample_state: dict[str, Any]) -> None:
        writer = getattr(self.plugin, '_obs_export_writer', None)
        if writer is None:
            return
        with contextlib.suppress(Exception):
            writer.write_exports(sample_state, settings)

    def _apply_live_settings(self, settings: dict[str, Any] | None = None, sample_state: dict[str, Any] | None = None) -> None:
        settings = dict(settings or self._collect_settings())
        sample_state = sample_state if sample_state is not None else self._sample_state()

        for key in list(self._preview_windows.keys()):
            with contextlib.suppress(Exception):
                self._close_preview(key)

        self._preview_bridge = None
        self._write_all_exports_for_settings(settings, sample_state)

    def _cleanup(self, *args) -> None:
        self._timer.stop()

        for dlg in list(self._editor_dialogs):
            with contextlib.suppress(Exception):
                dlg.hide()
                dlg.close()
                dlg.deleteLater()
        self._editor_dialogs.clear()

        if self._log_window is not None:
            with contextlib.suppress(Exception):
                self._log_window.hide()
                self._log_window.close()
                self._log_window.deleteLater()
            self._log_window = None

        for key in list(self._preview_windows.keys()):
            with contextlib.suppress(Exception):
                self._close_preview(key)
        self._preview_windows.clear()
        self._preview_owned.clear()

        self._preview_bridge = None
        self._dialog = None
