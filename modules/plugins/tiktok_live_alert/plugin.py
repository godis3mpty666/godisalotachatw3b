from __future__ import annotations

import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR and _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from tiktok_live_alert_core import TikTokLiveAlertPlugin


def create_plugin():
    return TikTokLiveAlertPlugin()
