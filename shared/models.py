from __future__ import annotations
from dataclasses import dataclass

@dataclass
class PluginStatus:
    state: str = "ready"
    message: str = "Bereit"
