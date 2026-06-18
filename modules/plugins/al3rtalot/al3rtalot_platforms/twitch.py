from __future__ import annotations

from .base import BaseAlertPlatform


class TwitchAlerts(BaseAlertPlatform):
    platform = "twitch"
    label = "Twitch"
    default_color = "#9146ff"
    supported_events = ("chat", "follow", "raid", "subscribe")
