from __future__ import annotations

import threading
import time

from shared.models import PluginStatus
from shared.plugin_base import ProviderPlugin, PluginHost


class ThreadedPlugin(ProviderPlugin):
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._host: PluginHost | None = None
        self._settings = {}

    def start(self, settings, host: PluginHost) -> None:
        self.stop(wait=True)
        self._settings = settings
        self._host = host
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run_wrapper, daemon=True, name=f'{self.plugin_id}-worker')
        self._thread.start()

    def stop(self, wait: bool = False, timeout: float = 3.0) -> None:
        self._stop.set()
        thread = self._thread
        if wait and thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.1, float(timeout)))
            if not thread.is_alive():
                self._thread = None
        elif thread is not None and not thread.is_alive():
            self._thread = None

    def _run_wrapper(self) -> None:
        try:
            self._host.set_status(self.plugin_id, PluginStatus('connecting', 'Starting'))
            self.run(self._settings, self._host)
        except Exception as exc:
            self._host.set_status(self.plugin_id, PluginStatus('error', str(exc)))
            self._host.log(self.plugin_id, f'Worker crashed: {exc}')
        finally:
            self._thread = None

    def run(self, settings, host: PluginHost) -> None:
        raise NotImplementedError
