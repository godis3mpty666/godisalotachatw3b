from __future__ import annotations

from .base import BaseAlertPlatform


class YouTubeAlerts(BaseAlertPlatform):
    platform = "youtube"
    label = "YouTube"
    default_color = "#ff0000"
    supported_events = ("chat", "subscribe", "member", "superchat")
