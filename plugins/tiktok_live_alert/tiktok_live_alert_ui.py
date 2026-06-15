from __future__ import annotations

from typing import Any
import contextlib
import time
import re

from PySide6 import QtCore, QtGui, QtWidgets

from tiktok_live_alert_logging import PluginLogger
from tiktok_live_alert_settings import _find_main_window, _normalize_color_text, _qcolor_to_rgba, _as_bool
from pathlib import Path

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'plugins':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'

_TICKER_IMAGE_DIR = _main_data_dir('tiktok_live_alert') / 'Tickerimage'

class _UiBridge(QtCore.QObject):
    state_updated = QtCore.Signal(dict)
    close_all = QtCore.Signal()


class _TickerLabel(QtWidgets.QLabel):
    _token_re = re.compile(r'\{([^{}]+\.png)\}', re.IGNORECASE)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)
        self._full_text = ''
        self._offset = 0.0
        self._direction = 'left'
        self._speed = 80.0
        self._delta = -1.0
        self._text_width = 0
        self._pause_until = 0.0
        self._segments: list[tuple[str, object]] = []
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _build_segments(self, text: str) -> list[tuple[str, object]]:
        segments: list[tuple[str, object]] = []
        pos = 0
        for match in self._token_re.finditer(text or ''):
            if match.start() > pos:
                segments.append(('text', text[pos:match.start()]))
            name = match.group(1)
            path = _TICKER_IMAGE_DIR / name
            pixmap = QtGui.QPixmap(str(path)) if path.exists() else QtGui.QPixmap()
            if pixmap.isNull():
                segments.append(('text', match.group(0)))
            else:
                segments.append(('image', pixmap))
            pos = match.end()
        if pos < len(text or ''):
            segments.append(('text', text[pos:]))
        return segments

    def _measure_segments(self) -> int:
        fm = self.fontMetrics()
        height = max(1, self.height() - 4)
        total = 0
        for kind, value in self._segments:
            if kind == 'text':
                total += fm.horizontalAdvance(str(value))
            else:
                pixmap = value
                if isinstance(pixmap, QtGui.QPixmap) and not pixmap.isNull():
                    ratio = pixmap.width() / max(1.0, float(pixmap.height()))
                    total += int(height * ratio) + 6
        return max(1, total)

    def set_ticker(self, text: str, direction: str, speed: float) -> None:
        self._full_text = text or ''
        self._direction = direction or 'left'
        self._speed = max(1.0, float(speed or 80.0))
        self._segments = self._build_segments(self._full_text)
        self._text_width = self._measure_segments()
        if self._direction.startswith('right'):
            self._offset = -float(self._text_width)
            self._delta = 1.0
        elif self._direction.startswith('bounce_right'):
            self._offset = 0.0
            self._delta = 1.0
        else:
            self._offset = float(self.width())
            self._delta = -1.0
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._full_text:
            self.set_ticker(self._full_text, self._direction, self._speed)

    def _tick(self) -> None:
        if not self._full_text:
            return
        now = time.monotonic()
        if now < self._pause_until:
            return
        step = max(1.0, self._speed / 60.0)
        if self._direction in {'bounce_left', 'bounce_right'}:
            self._offset += self._delta * step
            max_x = max(0, self.width() - self._text_width)
            if self._offset <= 0:
                self._offset = 0
                self._delta = 1.0
                self._pause_until = now + 0.35
            elif self._offset >= max_x:
                self._offset = max_x
                self._delta = -1.0
                self._pause_until = now + 0.35
        elif self._direction == 'right':
            self._offset += step
            if self._offset > self.width():
                self._offset = -float(self._text_width)
        else:
            self._offset -= step
            if self._offset < -float(self._text_width):
                self._offset = float(self.width())
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if not self._full_text:
            return super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        fm = painter.fontMetrics()
        baseline = int((self.height() + fm.ascent() - fm.descent()) / 2)
        x = int(self._offset)
        draw_h = max(1, self.height() - 4)
        for kind, value in self._segments:
            if kind == 'text':
                text = str(value)
                painter.drawText(x, baseline, text)
                x += fm.horizontalAdvance(text)
            else:
                pixmap = value
                if isinstance(pixmap, QtGui.QPixmap) and not pixmap.isNull():
                    ratio = pixmap.width() / max(1.0, float(pixmap.height()))
                    draw_w = max(1, int(draw_h * ratio))
                    y = int((self.height() - draw_h) / 2)
                    painter.drawPixmap(QtCore.QRect(x, y, draw_w, draw_h), pixmap)
                    x += draw_w + 6
        painter.end()


class _StyledProgressBar(QtWidgets.QProgressBar):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._bar_style = 'default'
        self._accent_color = QtGui.QColor('#ff2d55')
        self._text_color = QtGui.QColor('#ffffff')
        self._bg_color = QtGui.QColor('#151515')
        self._radius = 11

    def set_bar_appearance(self, style_name: str, accent: QtGui.QColor, text: QtGui.QColor, bg: QtGui.QColor, radius: int) -> None:
        self._bar_style = str(style_name or 'default').strip().lower()
        self._accent_color = QtGui.QColor(accent) if isinstance(accent, QtGui.QColor) else QtGui.QColor(str(accent or '#ff2d55'))
        self._text_color = QtGui.QColor(text) if isinstance(text, QtGui.QColor) else QtGui.QColor(str(text or '#ffffff'))
        self._bg_color = QtGui.QColor(bg) if isinstance(bg, QtGui.QColor) else QtGui.QColor(str(bg or '#151515'))
        self._radius = max(3, int(radius or 11))
        self.update()

    def _mix(self, a: QtGui.QColor, b: QtGui.QColor, factor: float) -> QtGui.QColor:
        factor = max(0.0, min(1.0, float(factor)))
        return QtGui.QColor(
            int(a.red() + (b.red() - a.red()) * factor),
            int(a.green() + (b.green() - a.green()) * factor),
            int(a.blue() + (b.blue() - a.blue()) * factor),
            int(a.alpha() + (b.alpha() - a.alpha()) * factor),
        )

    def _lighter(self, c: QtGui.QColor, factor: float = 0.35) -> QtGui.QColor:
        return self._mix(c, QtGui.QColor(255, 255, 255, c.alpha()), factor)

    def _darker(self, c: QtGui.QColor, factor: float = 0.35) -> QtGui.QColor:
        return self._mix(c, QtGui.QColor(0, 0, 0, c.alpha()), factor)

    def _display_text(self) -> str:
        fmt = self.format() or ''
        minimum = self.minimum()
        maximum = self.maximum()
        value = self.value()
        percent = 0
        if maximum > minimum:
            percent = int(round((value - minimum) * 100.0 / max(1, maximum - minimum)))
        return fmt.replace('%p', str(percent)).replace('%v', str(value)).replace('%m', str(maximum))

    def _progress_ratio(self) -> float:
        minimum = self.minimum()
        maximum = self.maximum()
        if maximum <= minimum:
            return 0.0
        return max(0.0, min(1.0, (self.value() - minimum) / float(maximum - minimum)))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = min(self._radius, rect.height() // 2)
        ratio = self._progress_ratio()
        fill_width = int(rect.width() * ratio)
        bg = QtGui.QColor(self._bg_color)
        accent = QtGui.QColor(self._accent_color)
        text_color = QtGui.QColor(self._text_color)
        border = self._lighter(accent, 0.25)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, radius, radius)

        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(QtCore.QRectF(rect), radius, radius)
        painter.save()
        painter.setClipPath(clip_path)

        fill_rect = QtCore.QRect(rect.x(), rect.y(), max(0, fill_width), rect.height())
        style_name = self._bar_style

        if fill_rect.width() > 0:
            if style_name == 'tiktok_clean':
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
                grad.setColorAt(0.0, self._lighter(accent, 0.55))
                grad.setColorAt(1.0, self._lighter(accent, 0.2))
                painter.fillRect(fill_rect, grad)
            elif style_name == 'tiktok_diagonal':
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
                grad.setColorAt(0.0, self._lighter(accent, 0.55))
                grad.setColorAt(1.0, self._lighter(accent, 0.15))
                painter.fillRect(fill_rect, grad)
                stripe = self._lighter(accent, 0.75)
                stripe.setAlpha(85)
                painter.setPen(QtGui.QPen(stripe, 8))
                step = 24
                start = fill_rect.x() - fill_rect.height()
                end = fill_rect.x() + fill_rect.width() + fill_rect.height()
                for x in range(start, end, step):
                    painter.drawLine(x, fill_rect.bottom(), x + fill_rect.height(), fill_rect.top())
            elif style_name == 'neon':
                glow = self._lighter(accent, 0.65)
                glow.setAlpha(90)
                painter.fillRect(fill_rect.adjusted(0, 2, 0, -2), glow)
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
                grad.setColorAt(0.0, self._lighter(accent, 0.5))
                grad.setColorAt(1.0, self._darker(accent, 0.1))
                painter.fillRect(fill_rect.adjusted(0, 4, 0, -4), grad)
            elif style_name == 'flat':
                painter.fillRect(fill_rect, accent)
            elif style_name == 'double_border':
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
                grad.setColorAt(0.0, self._lighter(accent, 0.4))
                grad.setColorAt(1.0, accent)
                painter.fillRect(fill_rect, grad)
                painter.setPen(QtGui.QPen(self._lighter(accent, 0.7), 2))
                painter.drawRect(fill_rect.adjusted(1, 1, -1, -1))
            elif style_name == 'soft_gradient':
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
                grad.setColorAt(0.0, self._lighter(accent, 0.55))
                grad.setColorAt(1.0, self._darker(accent, 0.1))
                painter.fillRect(fill_rect, grad)
            elif style_name == 'glass':
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
                grad.setColorAt(0.0, self._lighter(accent, 0.65))
                grad.setColorAt(0.48, self._lighter(accent, 0.2))
                grad.setColorAt(0.49, self._darker(accent, 0.05))
                grad.setColorAt(1.0, self._darker(accent, 0.2))
                painter.fillRect(fill_rect, grad)
            elif style_name == 'candy_stripe':
                painter.fillRect(fill_rect, self._lighter(accent, 0.35))
                stripe = self._lighter(accent, 0.7)
                stripe.setAlpha(120)
                painter.setBrush(stripe)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                band = 18
                x = fill_rect.x() - fill_rect.height()
                while x < fill_rect.right() + fill_rect.height():
                    poly = QtGui.QPolygon([
                        QtCore.QPoint(x, fill_rect.bottom()),
                        QtCore.QPoint(x + band, fill_rect.bottom()),
                        QtCore.QPoint(x + band + fill_rect.height(), fill_rect.top()),
                        QtCore.QPoint(x + fill_rect.height(), fill_rect.top()),
                    ])
                    painter.drawPolygon(poly)
                    x += band * 2
            elif style_name == 'minimal_dark':
                painter.fillRect(fill_rect, self._lighter(accent, 0.12))
                painter.fillRect(fill_rect.adjusted(0, fill_rect.height()//3, 0, -fill_rect.height()//3), accent)
            else:
                grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
                grad.setColorAt(0.0, self._lighter(accent, 0.25))
                grad.setColorAt(1.0, accent)
                painter.fillRect(fill_rect, grad)

            if style_name in {'default', 'tiktok_clean', 'tiktok_diagonal', 'soft_gradient', 'glass'}:
                shine = QtGui.QColor(255, 255, 255, 40)
                painter.fillRect(fill_rect.adjusted(0, 0, 0, -max(2, fill_rect.height() // 2)), shine)

        painter.restore()

        if style_name in {'tiktok_clean', 'tiktok_diagonal'}:
            painter.setPen(QtGui.QPen(QtGui.QColor(240, 240, 240, 200), 2))
        elif style_name == 'neon':
            painter.setPen(QtGui.QPen(self._lighter(accent, 0.7), 2))
        elif style_name == 'double_border':
            painter.setPen(QtGui.QPen(self._lighter(accent, 0.55), 2))
        else:
            painter.setPen(QtGui.QPen(border, 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(text_color)
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, self._display_text())
        painter.end()


class _EditableItem(QtWidgets.QWidget):
    def __init__(self, owner: "_AlertWindow", item_key: str, inner: QtWidgets.QWidget, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.item_key = item_key
        self.inner = inner
        self.inner.setParent(self)
        self.inner.show()
        self._drag_start: QtCore.QPoint | None = None
        self._start_geom: QtCore.QRect | None = None
        self._mode = ''
        self._handle_size = 14
        self.setMouseTracking(True)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.inner.setGeometry(self.rect())

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.owner.edit_mode:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor('#4da3ff'))
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        hs = self._handle_size
        handle = QtCore.QRect(self.width() - hs, self.height() - hs, hs - 1, hs - 1)
        painter.fillRect(handle, QtGui.QColor('#4da3ff'))
        painter.end()

    def _hit_mode(self, pos: QtCore.QPoint) -> str:
        hs = self._handle_size
        if pos.x() >= self.width() - hs and pos.y() >= self.height() - hs:
            return 'resize'
        return 'move'

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.owner.edit_mode or event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._mode = self._hit_mode(event.position().toPoint())
        self._drag_start = event.globalPosition().toPoint()
        self._start_geom = self.geometry()
        event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.owner.edit_mode:
            return super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        if self._drag_start is None or self._start_geom is None:
            self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor if self._hit_mode(pos) == 'resize' else QtCore.Qt.CursorShape.SizeAllCursor)
            return
        delta = event.globalPosition().toPoint() - self._drag_start
        geom = QtCore.QRect(self._start_geom)
        if self._mode == 'resize':
            geom.setWidth(max(40, geom.width() + delta.x()))
            geom.setHeight(max(24, geom.height() + delta.y()))
        else:
            geom.moveTo(geom.x() + delta.x(), geom.y() + delta.y())
            if self.parentWidget() is not None:
                max_x = max(0, self.parentWidget().width() - geom.width())
                max_y = max(0, self.parentWidget().height() - geom.height())
                geom.moveLeft(max(0, min(geom.x(), max_x)))
                geom.moveTop(max(0, min(geom.y(), max_y)))
        self.setGeometry(geom)
        self.owner.item_geometry_changed(self.item_key, geom)
        event.accept()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        with contextlib.suppress(Exception):
            self.hide()
        return super().closeEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.owner.edit_mode and self._drag_start is not None:
            self._drag_start = None
            self._start_geom = None
            self._mode = ''
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _AlertWindow(QtWidgets.QWidget):
    def __init__(self, bridge: _UiBridge, widget_key: str, settings: dict[str, Any], geometry_callback=None, item_geometry_callback=None, owner_window: QtWidgets.QWidget | None = None, logger: PluginLogger | None = None) -> None:
        owner_window = owner_window or _find_main_window()
        super().__init__(None)
        self._owner_window = owner_window
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.widget_key = widget_key
        self._settings = settings
        self._geometry_callback = geometry_callback
        self._item_geometry_callback = item_geometry_callback
        self._drag_pos: QtCore.QPoint | None = None
        self.edit_mode = False
        self._last_state: dict[str, Any] = {}
        self._logger = logger
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
        flags = QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.FramelessWindowHint
        if _as_bool(settings.get('always_on_top', False)):
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowTitle(f'TikTok LIVE Alert - {widget_key}')
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        self.setMinimumSize(140, 60)

        self._frame = QtWidgets.QFrame(self)
        self._frame.setObjectName('frame')
        self._frame.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._canvas = QtWidgets.QWidget(self._frame)
        self._canvas.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        app = QtWidgets.QApplication.instance()
        if app is not None:
            with contextlib.suppress(Exception):
                app.aboutToQuit.connect(self.close, QtCore.Qt.ConnectionType.QueuedConnection)
        if owner_window is not None:
            with contextlib.suppress(Exception):
                owner_window.destroyed.connect(self.close, QtCore.Qt.ConnectionType.QueuedConnection)
            with contextlib.suppress(Exception):
                owner_window.closed.connect(self.close, QtCore.Qt.ConnectionType.QueuedConnection)

        self.title_label = QtWidgets.QLabel('')
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.main_label = QtWidgets.QLabel('Waiting for data...')
        self.main_label.setWordWrap(True)
        self.main_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.secondary_label = QtWidgets.QLabel('')
        self.secondary_label.setWordWrap(True)
        self.secondary_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.progress = _StyledProgressBar()
        self.progress.setTextVisible(True)
        self.list_widget = QtWidgets.QListWidget()
        self.ticker = _TickerLabel()

        self._items = {
            'title': _EditableItem(self, 'title', self.title_label, self._canvas),
            'main': _EditableItem(self, 'main', self.main_label, self._canvas),
            'secondary': _EditableItem(self, 'secondary', self.secondary_label, self._canvas),
            'progress': _EditableItem(self, 'progress', self.progress, self._canvas),
            'list': _EditableItem(self, 'list', self.list_widget, self._canvas),
            'ticker': _EditableItem(self, 'ticker', self.ticker, self._canvas),
        }
        for item in self._items.values():
            item.show()

        bridge.state_updated.connect(self.apply_state, QtCore.Qt.ConnectionType.QueuedConnection)
        bridge.close_all.connect(self.close, QtCore.Qt.ConnectionType.QueuedConnection)
        self._apply_geometry()
        self._apply_style()
        self.apply_state({'latest': {}, 'goals': {}, 'rankings': {}})
        with contextlib.suppress(Exception):
            self.show()

    def _prefix(self) -> str:
        return self.widget_key + '_'

    def _g(self, key: str, fallback: Any) -> Any:
        return self._settings.get(self._prefix() + key, fallback)

    def _ig(self, item_key: str, suffix: str, fallback: Any) -> Any:
        return self._settings.get(f'{self.widget_key}_{item_key}_{suffix}', fallback)


    def _item_enabled(self, item_key: str, fallback: bool = True) -> bool:
        if item_key == 'title':
            return _as_bool(self._g('show_title', False))
        return _as_bool(self._settings.get(f'{self.widget_key}_{item_key}_enabled', fallback))

    def _set_item_visible(self, item_key: str, visible: bool) -> None:
        item = self._items.get(item_key)
        if item is not None:
            item.setVisible(bool(visible))

    def _clear_item_content(self, item_key: str) -> None:
        if item_key == 'title':
            self.title_label.clear()
        elif item_key == 'main':
            self.main_label.clear()
        elif item_key == 'secondary':
            self.secondary_label.clear()
        elif item_key == 'progress':
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setFormat('')
        elif item_key == 'list':
            self.list_widget.clear()
        elif item_key == 'ticker':
            self.ticker.set_ticker('', 'left', 0)

    def _show_item(self, item_key: str, desired: bool) -> None:
        enabled = bool(desired) and self._item_enabled(item_key, True)
        if not enabled:
            self._clear_item_content(item_key)
        self._set_item_visible(item_key, enabled)

    def _template_text(self, template: str, state: dict[str, Any]) -> str:
        latest = state.get('latest', {}) or {}
        rankings = state.get('rankings', {}) or {}
        goals = state.get('goals', {}) or {}
        top_liker = rankings.get('likers', [{}])[0] if rankings.get('likers') else {}
        top_gifter = rankings.get('gifters', [{}])[0] if rankings.get('gifters') else {}
        values = {
            'latest_follower': latest.get('follower') or '---',
            'latest_like_user': latest.get('like_user') or '---',
            'latest_like_count': latest.get('like_count') or 0,
            'latest_gift_user': latest.get('gift_user') or '---',
            'latest_gift_name': latest.get('gift_name') or 'gift',
            'latest_gift_count': latest.get('gift_count') or 0,
            'top_liker': top_liker.get('name') or '---',
            'top_liker_count': top_liker.get('count') or 0,
            'top_gifter': top_gifter.get('name') or '---',
            'top_gifter_count': top_gifter.get('count') or 0,
            'followers_current': (goals.get('followers') or {}).get('current', 0),
            'followers_target': (goals.get('followers') or {}).get('target', 0),
            'likes_current': (goals.get('likes') or {}).get('current', 0),
            'likes_target': (goals.get('likes') or {}).get('target', 0),
            'gifts_current': (goals.get('gifts') or {}).get('current', 0),
            'gifts_target': (goals.get('gifts') or {}).get('target', 0),
        }
        template_text = str(template or '')
        mapping: dict[str, str] = {}
        def _repl(match):
            key = f'__TICKERIMG_{len(mapping)}__'
            mapping[key] = match.group(0)
            return key
        protected = re.sub(r'\{[^{}]+\.png\}', _repl, template_text, flags=re.IGNORECASE)
        try:
            rendered = protected.format(**values)
        except Exception:
            rendered = protected
        for key, token in mapping.items():
            rendered = rendered.replace(key, token)
        return rendered


    def _clamp_to_visible_screen(self, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        screens = []
        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                screens = list(app.screens())
            except Exception:
                screens = []
        if not screens:
            return x, y, w, h

        for screen in screens:
            try:
                geo = screen.availableGeometry()
                if geo.intersects(QtCore.QRect(x, y, max(1, w), max(1, h))):
                    return x, y, w, h
            except Exception:
                pass

        try:
            geo = screens[0].availableGeometry()
            w = min(max(140, w), geo.width())
            h = min(max(60, h), geo.height())
            x = max(geo.left(), min(x, geo.right() - w + 1))
            y = max(geo.top(), min(y, geo.bottom() - h + 1))
            if x + w < geo.left() or x > geo.right() or y + h < geo.top() or y > geo.bottom():
                x = geo.left() + 40
                y = geo.top() + 40
            return x, y, w, h
        except Exception:
            return x, y, w, h

    def _default_item_geometries(self, w: int, h: int) -> dict[str, tuple[int, int, int, int]]:
        return {
            'title': (12, 10, max(100, w - 24), 28),
            'main': (18, 44, max(100, w - 36), 40),
            'secondary': (18, 88, max(100, w - 36), 28),
            'progress': (18, max(40, h - 44), max(100, w - 36), 22),
            'list': (16, 40, max(100, w - 32), max(60, h - 56)),
            'ticker': (16, max(16, (h - 40) // 2), max(100, w - 32), 32),
        }

    def _apply_geometry(self) -> None:
        w = int(self._g('width', 360))
        h = int(self._g('height', 140))
        x = int(self._g('x', 60))
        y = int(self._g('y', 60))
        x, y, w, h = self._clamp_to_visible_screen(x, y, w, h)
        x, y, w, h = self._clamp_to_visible_screen(x, y, w, h)
        self.setGeometry(x, y, w, h)
        self._frame.setGeometry(self.rect())
        self._canvas.setGeometry(10, 10, max(40, w - 20), max(40, h - 20))
        defaults = self._default_item_geometries(self._canvas.width(), self._canvas.height())
        for item_key, item in self._items.items():
            dx, dy, dw, dh = defaults[item_key]
            geom = QtCore.QRect(int(self._ig(item_key, 'x', dx)), int(self._ig(item_key, 'y', dy)), int(self._ig(item_key, 'w', dw)), int(self._ig(item_key, 'h', dh)))
            geom.setWidth(max(40, min(geom.width(), self._canvas.width())))
            geom.setHeight(max(24, min(geom.height(), self._canvas.height())))
            geom.moveLeft(max(0, min(geom.x(), max(0, self._canvas.width() - geom.width()))))
            geom.moveTop(max(0, min(geom.y(), max(0, self._canvas.height() - geom.height()))))
            item.setGeometry(geom)

    def _apply_style(self) -> None:
        font_family = str(self._g('font_family', 'Segoe UI') or 'Segoe UI')
        font_size = int(self._g('font_size', 18))
        title_size = max(10, int(self._g('title_font_size', font_size + 2)))
        text_color = QtGui.QColor()
        text_color.setNamedColor(str(self._g('text_color', '#ffffff')) or '#ffffff')
        if not text_color.isValid():
            text_color = QtGui.QColor('#ffffff')
        bg_color = QtGui.QColor()
        bg_color.setNamedColor(str(self._g('background_color', '#1f1f1f')) or '#1f1f1f')
        if not bg_color.isValid():
            bg_color = QtGui.QColor('#1f1f1f')
        accent_color = QtGui.QColor()
        accent_color.setNamedColor(str(self._g('accent_color', '#ff2d55')) or '#ff2d55')
        if not accent_color.isValid():
            accent_color = QtGui.QColor('#ff2d55')
        radius = int(self._g('corner_radius', 16))
        text_opacity = max(0.0, min(1.0, float(self._g('text_opacity', 1.0) or 1.0)))
        bg_opacity = max(0.0, min(1.0, float(self._g('background_opacity', 0.88) or 0.88)))
        bar_height = max(8, int(self._g('bar_height', 22) or 22))
        bar_style = str(self._g('bar_style', 'default') or 'default').strip().lower()

        text_color.setAlphaF(text_opacity)
        bg_color.setAlphaF(bg_opacity)

        bg_rgba = _qcolor_to_rgba(bg_color)
        text_rgba = _qcolor_to_rgba(text_color)
        accent_rgba = _qcolor_to_rgba(accent_color)

        title_font = QtGui.QFont(font_family, title_size)
        title_font.setBold(True)
        body_font = QtGui.QFont(font_family, font_size)

        self.title_label.setFont(title_font)
        self.main_label.setFont(body_font)
        self.secondary_label.setFont(QtGui.QFont(font_family, max(8, font_size - 2)))
        self.list_widget.setFont(QtGui.QFont(font_family, max(8, font_size - 1)))
        self.ticker.setFont(body_font)
        self.progress.setFixedHeight(bar_height)

        self._frame.setStyleSheet(
            f"QFrame#frame {{background-color:{bg_rgba}; border:2px solid {accent_rgba}; border-radius:{radius}px;}}"
        )
        label_style = f"background: transparent; color: {text_rgba};"
        for lbl in (self.title_label, self.main_label, self.secondary_label):
            lbl.setStyleSheet(label_style)
            pal = lbl.palette()
            pal.setColor(QtGui.QPalette.ColorRole.WindowText, text_color)
            lbl.setPalette(pal)
        pal = self.list_widget.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Text, text_color)
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, text_color)
        self.list_widget.setPalette(pal)
        self.list_widget.setStyleSheet(label_style + 'border:none; outline:none;')
        self.progress.setStyleSheet('background: transparent; border: none;')
        self.progress.set_bar_appearance(bar_style, accent_color, text_color, bg_color, max(4, bar_height // 2))
        pal = self.progress.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Text, text_color)
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, text_color)
        self.progress.setPalette(pal)
        pal = self.ticker.palette()
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, text_color)
        self.ticker.setPalette(pal)
        self.ticker.setStyleSheet(label_style)
        self.title_label.setText(str(self._g('title', self.widget_key.replace('_', ' ').title())))
        for item in self._items.values():
            item.raise_()
            item.update()
        self._frame.update()
        self._canvas.update()
        self.update()

    def _ranking_lines(self, items: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for idx, item in enumerate(items or [], 1):
            name = str(item.get('name') or 'unknown')
            lines.append(f'{idx}. {name}')
        return lines

    @QtCore.Slot(dict)
    def apply_state(self, state: dict[str, Any]) -> None:
        self._last_state = dict(state or {})
        mode = self.widget_key
        for item in self._items.values():
            item.setVisible(False)
        latest = state.get('latest', {}) or {}
        goals = state.get('goals', {}) or {}
        rankings = state.get('rankings', {}) or {}

        for item_key in self._items:
            self._show_item(item_key, False)

        show_title = self._item_enabled('title', False)
        self.title_label.setText(str(self._g('title', self.widget_key.replace('_', ' ').title()) or '') if show_title else '')
        self._show_item('title', show_title)

        if mode == 'latest_follower':
            follower = str(latest.get('follower') or 'Newest follower')
            self.main_label.setText(follower)
            self.secondary_label.clear()
            self._show_item('main', True)
            self._show_item('secondary', False)
        elif mode == 'latest_like':
            name = str(latest.get('like_user') or 'Latest like')
            count = int(latest.get('like_count') or 0)
            self.main_label.setText(name)
            self.secondary_label.setText(f'{count} Likes' if count > 0 else '')
            self._show_item('main', True)
            self._show_item('secondary', bool(self.secondary_label.text()))
        elif mode == 'latest_gift':
            name = str(latest.get('gift_user') or 'Latest gift')
            gift = str(latest.get('gift_name') or '')
            count = int(latest.get('gift_count') or 0)
            self.main_label.setText(name)
            self.secondary_label.setText(f'{gift} x{count}' if gift or count else '')
            self._show_item('main', True)
            self._show_item('secondary', bool(self.secondary_label.text()))
        elif mode == 'top_liker':
            items = self._ranking_lines(rankings.get('likers', []))
            self.list_widget.clear(); self.list_widget.addItems(items or ['No likes yet'])
            self._show_item('list', True)
        elif mode == 'top_gifter':
            items = self._ranking_lines(rankings.get('gifters', []))
            self.list_widget.clear(); self.list_widget.addItems(items or ['No gifts yet'])
            self._show_item('list', True)
        elif mode == 'follower_goal':
            goal = goals.get('followers', {}) or {}
            cur = int(goal.get('current') or 0); target = max(1, int(goal.get('target') or 1000))
            self.main_label.setText(f'{cur} / {target}')
            self.secondary_label.setText(f'{max(0, target - cur)} remaining')
            self.progress.setRange(0, target); self.progress.setValue(min(cur, target)); self.progress.setFormat('%p%' if str(self._settings.get('follower_goal_progress_style','value')).lower() == 'percent' else '%v / %m')
            self._show_item('main', True); self._show_item('secondary', True); self._show_item('progress', True)
        elif mode == 'like_goal':
            goal = goals.get('likes', {}) or {}
            cur = int(goal.get('current') or 0); target = max(1, int(goal.get('target') or 10000))
            self.main_label.setText(f'{cur} / {target}')
            self.secondary_label.setText(f'{max(0, target - cur)} remaining')
            self.progress.setRange(0, target); self.progress.setValue(min(cur, target)); self.progress.setFormat('%p%' if str(self._settings.get('like_goal_progress_style','value')).lower() == 'percent' else '%v / %m')
            self._show_item('main', True); self._show_item('secondary', True); self._show_item('progress', True)
        elif mode == 'gift_goal':
            goal = goals.get('gifts', {}) or {}
            cur = int(goal.get('current') or 0); target = max(1, int(goal.get('target') or 100))
            self.main_label.setText(f'{cur} / {target}')
            self.secondary_label.setText(f'{max(0, target - cur)} remaining')
            self.progress.setRange(0, target); self.progress.setValue(min(cur, target)); self.progress.setFormat('%p%' if str(self._settings.get('gift_goal_progress_style','value')).lower() == 'percent' else '%v / %m')
            self._show_item('main', True); self._show_item('secondary', True); self._show_item('progress', True)
        elif mode in {'ticker', 'ticker_2', 'ticker_3'}:
            if mode == 'ticker':
                direction = str(self._settings.get('ticker_direction', 'left') or 'left')
                speed = float(self._settings.get('ticker_speed', 80) or 80)
                template = str(self._settings.get('ticker_text', 'Latest follower: {latest_follower}') or '')
            else:
                direction = str(self._settings.get(f'{mode}_direction', 'left') or 'left')
                speed = float(self._settings.get(f'{mode}_speed', 80) or 80)
                template = str(self._settings.get(f'{mode}_text', 'Latest follower: {latest_follower}') or '')
            self.ticker.set_ticker(self._template_text(template, state), direction, speed)
            self._show_item('ticker', True)
        self._apply_style()
        
    def update_settings(self, settings: dict[str, Any], sample_state: dict[str, Any] | None = None) -> None:
        self._settings = dict(settings or {})
        self._apply_geometry()
        self._apply_style()
        self.apply_state(sample_state if sample_state is not None else self._last_state)

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        for item in self._items.values():
            item.inner.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, self.edit_mode)
            item.update()
        self.update()

    def item_geometry_changed(self, item_key: str, geom: QtCore.QRect) -> None:
        if self._item_geometry_callback is not None:
            self._item_geometry_callback(self.widget_key, item_key, geom.x(), geom.y(), geom.width(), geom.height())

    def _sync_geometry(self) -> None:
        if self._geometry_callback is None:
            return
        geo = self.geometry()
        self._geometry_callback(self.widget_key, geo.x(), geo.y(), geo.width(), geo.height())

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        super().moveEvent(event)
        self._sync_geometry()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._frame.setGeometry(self.rect())
        self._canvas.setGeometry(10, 10, max(40, self.width() - 20), max(40, self.height() - 20))
        self._sync_geometry()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.edit_mode:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor('#8ab4ff'))
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        handle = QtCore.QRect(self.width() - 16, self.height() - 16, 12, 12)
        painter.fillRect(handle, QtGui.QColor('#8ab4ff'))
        painter.end()

    def _window_hit_mode(self, pos: QtCore.QPoint) -> str:
        if pos.x() >= self.width() - 18 and pos.y() >= self.height() - 18:
            return 'resize'
        return 'move'

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.edit_mode or event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._drag_pos = event.globalPosition().toPoint()
        self._start_geometry = self.geometry()
        self._window_mode = self._window_hit_mode(event.position().toPoint())
        event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.edit_mode:
            return super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        if not hasattr(self, '_start_geometry') or self._drag_pos is None:
            self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor if self._window_hit_mode(pos) == 'resize' else QtCore.Qt.CursorShape.SizeAllCursor)
            return
        delta = event.globalPosition().toPoint() - self._drag_pos
        geom = QtCore.QRect(self._start_geometry)
        if getattr(self, '_window_mode', 'move') == 'resize':
            geom.setWidth(max(self.minimumWidth(), geom.width() + delta.x()))
            geom.setHeight(max(self.minimumHeight(), geom.height() + delta.y()))
        else:
            geom.moveTo(geom.x() + delta.x(), geom.y() + delta.y())
        self.setGeometry(geom)
        event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.edit_mode and self._drag_pos is not None:
            self._drag_pos = None
            if hasattr(self, '_start_geometry'):
                delattr(self, '_start_geometry')
            event.accept()
            return
        super().mouseReleaseEvent(event)