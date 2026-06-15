from __future__ import annotations
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def data_dir(plugin_name: str | None = None) -> Path:
    base = app_root() / "data"
    if plugin_name:
        base = base / plugin_name
    base.mkdir(parents=True, exist_ok=True)
    return base
