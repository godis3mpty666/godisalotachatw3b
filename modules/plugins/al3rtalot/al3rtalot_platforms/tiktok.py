from __future__ import annotations

from .base import BaseAlertPlatform


class TikTokAlerts(BaseAlertPlatform):
    platform = "tiktok"
    label = "TikTok"
    default_color = "#ff2d55"
    supported_events = ("chat", "follow", "join", "like", "gift", "share", "subscribe")
