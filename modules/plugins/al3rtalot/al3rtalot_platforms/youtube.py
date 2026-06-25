from __future__ import annotations

from .base import BaseAlertPlatform


class YouTubeAlerts(BaseAlertPlatform):
    platform = "youtube"
    label = "YouTube"
    default_color = "#ff0000"
    # YouTube Live liefert vor allem Member/Subscribe/Superchat/Supersticker und Membership-Gifts.
    supported_events = ("chat", "subscribe", "member", "gift", "superchat", "supersticker", "donation")
