from __future__ import annotations

from .base import BaseAlertPlatform


class KickAlerts(BaseAlertPlatform):
    platform = "kick"
    label = "Kick"
    default_color = "#53fc18"
    supported_events = ("chat", "follow", "subscribe")
