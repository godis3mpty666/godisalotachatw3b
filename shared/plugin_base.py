from __future__ import annotations
from typing import Any

class PluginHost:
    def platform_settings(self, platform: str) -> dict[str, Any]:
        return {}
    def emit_message(self, plugin_id: str, payload: dict[str, Any]) -> None:
        pass
    def emit_metric(self, plugin_id: str, payload: dict[str, Any]) -> None:
        pass
    def set_status(self, plugin_id: str, status) -> None:
        pass
    def log(self, plugin_id: str, message: str) -> None:
        pass
    def send_platform_message(self, platform: str, message: str, **kwargs) -> bool:
        return False

class ProviderPlugin:
    plugin_id = ""
    display_name = ""
    version = ""
    description = ""
    def settings_schema(self):
        return []
    def default_settings(self):
        return {}
    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        pass
    def stop(self, *args, **kwargs) -> None:
        pass
