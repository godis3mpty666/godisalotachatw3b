from __future__ import annotations

import datetime
import logging
import time
from collections import deque
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'modules':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'

class PluginLogger:
    """Centralized logging for the TikTok Live Alert plugin"""
    
    def __init__(self, plugin_id: str, enabled: bool = False):
        self.plugin_id = plugin_id
        self.logger = logging.getLogger(f"plugin.{plugin_id}")
        self.logger.setLevel(logging.DEBUG)
        self.enabled = bool(enabled)
        
        # Create logs directory
        log_dir = _main_data_dir('tiktok_live_alert') / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # File handler
        log_file = log_dir / f"tiktok_live_alert_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
        
        # Console handler for debug output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('[TikTokAlert] %(levelname)s: %(message)s')
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        self.log_file = log_file
        self.log_messages: deque = deque(maxlen=1000)

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        changed = self.enabled != enabled
        self.enabled = enabled
        if changed:
            msg = 'Event logging enabled' if enabled else 'Event logging disabled'
            self.logger.info(msg)
            self.log_messages.append(('INFO', msg, time.time()))

    def _record(self, level: str, msg: str) -> None:
        if level not in {'WARNING', 'ERROR'} and not self.enabled:
            return
        getattr(self.logger, level.lower())(msg)
        self.log_messages.append((level, msg, time.time()))

    def debug(self, msg: str):
        self._record('DEBUG', msg)

    def info(self, msg: str):
        self._record('INFO', msg)

    def warning(self, msg: str):
        self._record('WARNING', msg)

    def error(self, msg: str):
        self._record('ERROR', msg)

    def get_recent(self, count: int = 100) -> list:
        return list(self.log_messages)[-count:]


class _LogWindow(QtWidgets.QDialog):
    """Log viewer window for the plugin"""
    
    def __init__(self, logger: PluginLogger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.setWindowTitle("TikTok LIVE Alert - Event Log")
        self.resize(900, 500)
        
        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        
        self.level_combo = QtWidgets.QComboBox()
        self.level_combo.addItems(['ALL', 'INFO', 'WARNING', 'ERROR', 'DEBUG'])
        self.level_combo.currentTextChanged.connect(self.refresh)
        
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Filter...")
        self.filter_edit.textChanged.connect(self.refresh)
        
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_log)
        
        self.save_btn = QtWidgets.QPushButton("Save to File")
        self.save_btn.clicked.connect(self.save_log)
        
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        
        toolbar.addWidget(QtWidgets.QLabel("Level:"))
        toolbar.addWidget(self.level_combo)
        toolbar.addWidget(QtWidgets.QLabel("Filter:"))
        toolbar.addWidget(self.filter_edit)
        toolbar.addStretch()
        toolbar.addWidget(self.clear_btn)
        toolbar.addWidget(self.save_btn)
        toolbar.addWidget(self.refresh_btn)
        
        layout.addLayout(toolbar)
        
        # Log text area
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QtGui.QFont("Consolas", 10))
        layout.addWidget(self.log_text)
        
        # Status bar
        self.status_label = QtWidgets.QLabel()
        layout.addWidget(self.status_label)
        
        # Timer for auto-refresh
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(2000)  # Refresh every 2 seconds
        
        self.refresh()
        
    def refresh(self):
        """Refresh the log display"""
        level = self.level_combo.currentText()
        filter_text = self.filter_edit.text().lower()
        
        self.log_text.clear()
        
        messages = self.logger.get_recent(500)
        count = 0
        
        for lvl, msg, timestamp in reversed(messages):
            # Apply level filter
            if level != 'ALL' and lvl != level:
                continue
            # Apply text filter
            if filter_text and filter_text not in msg.lower():
                continue
                
            time_str = datetime.datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
            
            # Color coding
            color = '#ffffff'
            if lvl == 'ERROR':
                color = '#ff6b6b'
            elif lvl == 'WARNING':
                color = '#ffd93d'
            elif lvl == 'DEBUG':
                color = '#888888'
                
            self.log_text.append(f'<span style="color:{color}">[{time_str}] [{lvl}] {msg}</span>')
            count += 1
            
        status = 'enabled' if self.logger.enabled else 'disabled'
        self.status_label.setText(f"Logging {status} • Showing {count} log entries (of {len(messages)} total)")
        
    def clear_log(self):
        """Clear the log display"""
        self.logger.log_messages.clear()
        self.refresh()
        
    def save_log(self):
        """Save log to file"""
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Log", str(self.logger.log_file), "Log Files (*.log);;All Files (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"TikTok LIVE Alert Log - {datetime.datetime.now()}\n")
                    f.write("=" * 50 + "\n\n")
                    for lvl, msg, timestamp in self.logger.get_recent(1000):
                        time_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        f.write(f"[{time_str}] [{lvl}] {msg}\n")
                QtWidgets.QMessageBox.information(self, "Success", f"Log saved to:\n{file_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Could not save log: {e}")

