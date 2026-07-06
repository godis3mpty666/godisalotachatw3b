from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from shared.models import PluginStatus
from shared.plugin_base import PluginHost, ProviderPlugin

PLUGIN_ID = "tutorials"
PLUGIN_VERSION = "0.05"
PLUGIN_NAME = f"tutorials ver. {PLUGIN_VERSION}"
SPOTIFY_DEV_URL = "https://developer.spotify.com/dashboard"


class TutorialsPlugin(ProviderPlugin):
    plugin_id = PLUGIN_ID
    display_name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = "Guided setup tutorials for godisalotachat. Start: Spotify."

    def __init__(self) -> None:
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}

    def settings_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "section_intro", "type": "separator", "label": "Tutorials - Spotify setup"},
            {"key": "spotify_status", "label": "Status", "readonly": True, "placeholder": "Spotify tutorial ready"},
            {"key": "step_1", "label": "1. Open the dashboard", "readonly": True, "placeholder": "Open the Spotify Developer Dashboard and click Create app."},
            {"key": "button_open_spotify_dashboard", "type": "button", "label": "Spotify Developer Dashboard", "button_text": "Open developer page"},
            {"key": "step_2", "label": "2. Create the app", "readonly": True, "placeholder": "Enter an app name and description, then create the app."},
            {"key": "step_3", "label": "3. Redirect URI", "readonly": True, "placeholder": "Add the Redirect URI from godisalotachat under Redirect URIs."},
            {"key": "spotify_redirect_hint", "label": "Redirect URL", "readonly": True, "placeholder": "Standard: http://127.0.0.1:5173/callback"},
            {"key": "step_4", "label": "4. Copy credentials", "readonly": True, "placeholder": "Copy the Client ID and Client Secret from your Spotify app."},
            {"key": "spotify_client_id_note", "label": "Client ID Check", "readonly": True, "placeholder": "Im Plattformen-Reiter eintragen oder später über den Tutorial-Reiter verbinden."},
            {"key": "spotify_client_secret_note", "label": "Client Secret Check", "readonly": True, "placeholder": "Im Plattformen-Reiter eintragen oder später über den Tutorial-Reiter verbinden."},
            {"key": "step_5", "label": "5. Connect", "readonly": True, "placeholder": "Save the credentials and connect Spotify."},
            {"key": "next_platforms", "label": "Tutorial status", "readonly": True, "placeholder": "Spotify, Twitch, KICK, TikTok, and GPT are available. YouTube, OBS, and MELD are planned."},
        ]

    def default_settings(self) -> dict[str, Any]:
        return {
            "spotify_status": "Spotify-Tutorial bereit",
            "spotify_redirect_hint": "Standard: http://127.0.0.1:5173/callback",
            "spotify_client_id_note": "Noch nicht geprüft",
            "spotify_client_secret_note": "Noch nicht geprüft",
        }

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._settings = dict(settings or {})
        self._host = host
        try:
            host.set_status(PLUGIN_ID, PluginStatus(True, "bereit", "Spotify-Tutorial verfügbar"))
            host.log(PLUGIN_ID, f"{PLUGIN_NAME} gestartet")
        except Exception:
            pass

    def stop(self, *args, **kwargs) -> None:
        try:
            if self._host:
                self._host.set_status(PLUGIN_ID, PluginStatus(False, "gestoppt", "Tutorials gestoppt"))
        except Exception:
            pass

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent=None) -> bool:
        if key == "button_open_spotify_dashboard":
            try:
                webbrowser.open(SPOTIFY_DEV_URL)
                if host:
                    host.log(PLUGIN_ID, "Spotify Developer Dashboard geöffnet")
                return True
            except Exception as exc:
                if host:
                    host.log(PLUGIN_ID, f"Spotify Developer Dashboard konnte nicht geöffnet werden: {exc}")
                return False
        return False


def create_plugin() -> TutorialsPlugin:
    return TutorialsPlugin()
