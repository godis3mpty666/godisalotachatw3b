from __future__ import annotations

from .base import BaseAlertPlatform


class TwitchAlerts(BaseAlertPlatform):
    platform = "twitch"
    label = "Twitch"
    default_color = "#9146ff"
    # chat bleibt technisch unterstützt, ist aber in den Default-Settings aus.
    # join ist wichtig für "User betritt Stream/Chat" aus twitch_chat.
    supported_events = ("chat", "join", "viewer_streak", "follow", "raid", "subscribe", "gift", "donation", "bits")
