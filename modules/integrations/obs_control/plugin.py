from __future__ import annotations

import time
from typing import Any

from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin


class OBSControlPlugin(ThreadedPlugin):
    plugin_id = "obs_control"
    display_name = "OBS Control"
    version = "1.2.0"
    description = "Controls OBS through the main tool OBS connection. No own OBS login or second websocket."

    def __init__(self) -> None:
        super().__init__()
        self._last_trigger_ts = 0.0
        self._source_visible = False
        self._last_status_ts = 0.0

    def settings_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "source_name", "label": "OBS Source/SceneItem Name", "default": "", "help": "Name der OBS-Quelle, die bei Nachrichten ein-/ausgeblendet wird."},
            {"key": "scene_name", "label": "OBS Source/SceneItem Name (alt)", "type": "hidden", "default": ""},
            {"key": "timeout_seconds", "label": "Hide after inactivity (seconds)", "type": "number", "default": 5, "min": 0, "max": 3600, "step": 1},
            {"key": "show_on_chat", "label": "Trigger on chat messages", "type": "bool", "default": True},
            {"key": "show_on_alerts", "label": "Trigger on alerts / system messages", "type": "bool", "default": True},
            {"key": "disable_on_start", "label": "Hide source on plugin start", "type": "bool", "default": True},
            {"key": "log_events", "label": "Log OBS events", "type": "hidden", "default": False},
            {"key": "host", "label": "OBS host", "type": "hidden", "default": ""},
            {"key": "port", "label": "OBS port", "type": "hidden", "default": ""},
            {"key": "password", "label": "OBS password", "type": "hidden", "default": ""},
            {"key": "autoconnect", "label": "Auto connect", "type": "hidden", "default": True},
        ]

    def default_settings(self) -> dict[str, Any]:
        return {
            "source_name": "",
            "scene_name": "",
            "timeout_seconds": 5,
            "show_on_chat": True,
            "show_on_alerts": True,
            "disable_on_start": True,
            "log_events": False,
            "host": "",
            "port": "",
            "password": "",
            "autoconnect": True,
        }

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        return True, "OBS Control nutzt die zentrale OBS-Verbindung vom Haupttool. Bitte OBS im Haupttool prüfen/verbinden."

    def run(self, settings: dict[str, Any], host: PluginHost) -> None:
        settings = self._effective_settings(settings)
        host.set_status(self.plugin_id, PluginStatus("connecting", "Waiting for main OBS connection"))

        did_start_hide = False
        while not self._stop.wait(0.25):
            connected = self._host_obs_connected(host)
            target = self._target_name(settings)

            if not connected:
                host.set_status(self.plugin_id, PluginStatus("disconnected", "OBS not connected in main tool"))
                did_start_hide = False
                continue

            if not did_start_hide:
                did_start_hide = True
                if self._bool_setting(settings, "disable_on_start", True) and target:
                    ok, detail = self.set_source_visible(target, False)
                    if not ok:
                        host.log(self.plugin_id, detail)

            self._handle_timeout(settings, host)
            now = time.monotonic()
            if now - self._last_status_ts >= 5.0:
                self._last_status_ts = now
                detail = "Using main OBS connection"
                if target:
                    detail += f" / target: {target}"
                host.set_status(self.plugin_id, PluginStatus("connected", detail))

    def stop(self, *args, **kwargs) -> None:
        try:
            settings = self._effective_settings(self._settings or {})
            target = self._target_name(settings)
            if target:
                self.set_source_visible(target, False)
        except Exception:
            pass
        super().stop()

    def disconnect(self) -> None:
        self.stop()

    def is_connected(self) -> bool:
        return self._host_obs_connected(self._host)

    def on_message(self, msg: Any) -> None:
        if self._stop.is_set():
            return

        settings = self._effective_settings(self._settings or {})
        if not self._message_matches(settings, msg):
            return

        target = self._target_name(settings)
        if not target:
            return

        self._last_trigger_ts = time.time()
        ok, detail = self.set_source_visible(target, True)

        if self._host is not None:
            if ok:
                self._host.set_status(self.plugin_id, PluginStatus("connected", f"Visible: {target}"))
            else:
                self._host.log(self.plugin_id, detail)
                self._host.set_status(self.plugin_id, PluginStatus("error", detail))

    def _effective_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(settings or {})
        if not str(merged.get("source_name", "") or "").strip():
            old_scene_name = str(merged.get("scene_name", "") or "").strip()
            if old_scene_name:
                merged["source_name"] = old_scene_name
        return merged

    def _host_obs_connected(self, host: PluginHost | None) -> bool:
        if host is None or not hasattr(host, "obs_is_connected"):
            return False
        try:
            return bool(host.obs_is_connected())
        except Exception:
            return False

    def _obs_request(self, request_type: str, request_data: dict[str, Any] | None = None, timeout: float = 5.0) -> tuple[bool, dict[str, Any] | str]:
        host = self._host
        if host is None or not hasattr(host, "obs_request"):
            return False, "Main tool OBS requester is missing"
        try:
            return host.obs_request(request_type, request_data or {}, timeout)
        except Exception as exc:
            return False, str(exc)

    def _message_matches(self, settings: dict[str, Any], msg: Any) -> bool:
        msg_type = str(getattr(msg, "message_type", "chat") or "chat").strip().lower()
        if msg_type == "chat":
            return self._bool_setting(settings, "show_on_chat", True)
        return self._bool_setting(settings, "show_on_alerts", True)

    def _target_name(self, settings: dict[str, Any]) -> str:
        return str(settings.get("source_name", settings.get("scene_name", "")) or "").strip()

    def _handle_timeout(self, settings: dict[str, Any], host: PluginHost | None) -> None:
        timeout_seconds = self._float_setting(settings, "timeout_seconds", 5.0)
        if timeout_seconds <= 0:
            return

        if self._source_visible and self._last_trigger_ts > 0 and (time.time() - self._last_trigger_ts) >= timeout_seconds:
            target = self._target_name(settings)
            if not target:
                return
            ok, detail = self.set_source_visible(target, False)
            if host is not None:
                if ok:
                    host.set_status(self.plugin_id, PluginStatus("connected", "Idle / hidden"))
                else:
                    host.log(self.plugin_id, detail)
                    host.set_status(self.plugin_id, PluginStatus("error", detail))

    def request(self, request_type: str, request_data: dict[str, Any] | None = None, timeout: float = 5.0) -> tuple[bool, dict[str, Any] | str]:
        return self._obs_request(request_type, request_data or {}, timeout)

    def get_scene_list(self) -> tuple[bool, list[dict[str, Any]] | str]:
        ok, data = self.request("GetSceneList", {})
        if not ok:
            return False, str(data)
        return True, list((data or {}).get("scenes", []) or [])

    def find_matching_scene_items(self, target_name: str) -> tuple[bool, list[dict[str, Any]] | str]:
        target = str(target_name or "").strip().casefold()
        if not target:
            return False, "Source/SceneItem name is missing"

        ok, scenes_or_error = self.get_scene_list()
        if not ok:
            return False, str(scenes_or_error)

        matches: list[dict[str, Any]] = []
        for scene in scenes_or_error:
            scene_name = str(scene.get("sceneName", "") or "").strip()
            if not scene_name:
                continue

            ok_items, items_or_error = self.request("GetSceneItemList", {"sceneName": scene_name})
            if not ok_items:
                continue

            for item in list((items_or_error or {}).get("sceneItems", []) or []):
                source_name = str(item.get("sourceName", "") or "").strip()
                scene_item_id = item.get("sceneItemId")
                if source_name.casefold() == target:
                    matches.append({
                        "sceneName": scene_name,
                        "sceneItemId": int(scene_item_id),
                        "sourceName": source_name,
                    })

        return True, matches

    def get_scene_item_enabled(self, scene_name: str, scene_item_id: int) -> tuple[bool, bool | str]:
        ok, data = self.request("GetSceneItemEnabled", {
            "sceneName": scene_name,
            "sceneItemId": int(scene_item_id),
        })
        if not ok:
            return False, str(data)
        return True, bool((data or {}).get("sceneItemEnabled", False))

    def set_source_visible(self, target_name: str, visible: bool) -> tuple[bool, str]:
        target = str(target_name or "").strip()
        if not target:
            return False, "Source/SceneItem name is missing"

        if not self._host_obs_connected(self._host):
            return False, "OBS is not connected in main tool"

        ok, matches_or_error = self.find_matching_scene_items(target)
        if not ok:
            return False, f"OBS control failed: {matches_or_error}"

        matches = list(matches_or_error or [])
        if not matches:
            return False, f"No matching OBS source/scene item found: {target}"

        changed = 0
        for match in matches:
            ok_set, data_or_error = self.request("SetSceneItemEnabled", {
                "sceneName": match["sceneName"],
                "sceneItemId": int(match["sceneItemId"]),
                "sceneItemEnabled": bool(visible),
            })
            if not ok_set:
                return False, f"OBS control failed: {data_or_error}"
            changed += 1

        self._source_visible = bool(visible)
        return True, f"{'Shown' if visible else 'Hidden'}: {target} ({changed} item(s))"

    def trigger_hotkey_by_key_sequence(self, key_sequence: str, settings: dict[str, Any] | None = None) -> tuple[bool, str]:
        parsed = self._parse_key_sequence(key_sequence)
        if not parsed:
            return False, f"Invalid hotkey sequence: {key_sequence}"

        ok, data_or_error = self.request("TriggerHotkeyByKeySequence", parsed)
        if not ok:
            return False, f"OBS hotkey failed: {data_or_error}"

        return True, f"Hotkey triggered: {key_sequence}"

    def _parse_key_sequence(self, key_sequence: str) -> dict[str, Any] | None:
        text = str(key_sequence or "").strip()
        if not text:
            return None

        parts = [part.strip() for part in text.replace(" ", "").split("+") if part.strip()]
        if not parts:
            return None

        key_id: str | None = None
        modifiers = {"shift": False, "control": False, "alt": False, "command": False}
        alias_map = {
            "CTRL": "CONTROL", "STRG": "CONTROL", "CMD": "COMMAND", "WIN": "COMMAND",
            "META": "COMMAND", "SUPER": "COMMAND", "ESC": "ESCAPE", "DEL": "DELETE",
            "INS": "INSERT", "PGUP": "PAGEUP", "PGDN": "PAGEDOWN", "SPACEBAR": "SPACE",
            "RETURN": "ENTER",
        }
        special_keys = {
            "ENTER": "OBS_KEY_RETURN", "TAB": "OBS_KEY_TAB", "ESCAPE": "OBS_KEY_ESCAPE",
            "SPACE": "OBS_KEY_SPACE", "BACKSPACE": "OBS_KEY_BACKSPACE", "DELETE": "OBS_KEY_DELETE",
            "INSERT": "OBS_KEY_INSERT", "HOME": "OBS_KEY_HOME", "END": "OBS_KEY_END",
            "PAGEUP": "OBS_KEY_PAGEUP", "PAGEDOWN": "OBS_KEY_PAGEDOWN", "UP": "OBS_KEY_UP",
            "DOWN": "OBS_KEY_DOWN", "LEFT": "OBS_KEY_LEFT", "RIGHT": "OBS_KEY_RIGHT",
            "CAPSLOCK": "OBS_KEY_CAPSLOCK", "NUMLOCK": "OBS_KEY_NUMLOCK",
            "SCROLLLOCK": "OBS_KEY_SCROLLLOCK", "PRINTSCREEN": "OBS_KEY_PRINT",
            "PAUSE": "OBS_KEY_PAUSE", "MENU": "OBS_KEY_MENU",
        }

        for raw_part in parts:
            part = alias_map.get(raw_part.upper(), raw_part.upper())
            if part == "SHIFT":
                modifiers["shift"] = True
                continue
            if part == "CONTROL":
                modifiers["control"] = True
                continue
            if part == "ALT":
                modifiers["alt"] = True
                continue
            if part == "COMMAND":
                modifiers["command"] = True
                continue
            if part in special_keys:
                key_id = special_keys[part]
                continue
            if len(part) == 1 and "A" <= part <= "Z":
                key_id = f"OBS_KEY_{part}"
                continue
            if len(part) == 1 and "0" <= part <= "9":
                key_id = f"OBS_KEY_{part}"
                continue
            if part.startswith("F") and part[1:].isdigit():
                number = int(part[1:])
                if 1 <= number <= 24:
                    key_id = f"OBS_KEY_F{number}"
                    continue
            return None

        if not key_id:
            return None
        return {"keyId": key_id, "keyModifiers": modifiers}

    def _float_setting(self, settings: dict[str, Any], key: str, default: float) -> float:
        try:
            return float(str(settings.get(key, default)).strip())
        except Exception:
            return default

    def _bool_setting(self, settings: dict[str, Any], key: str, default: bool) -> bool:
        value = settings.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}


def create_plugin() -> OBSControlPlugin:
    return OBSControlPlugin()
