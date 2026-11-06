"""Persistent user settings (JSON in the per-user config folder)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "language": "system",  # "system" or a language code from i18n.STRINGS
    "theme": "system",     # "system", "light" or "dark"
    "export_dir": "",      # where single archive files are saved; empty = ask every time
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "RenPySuite"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RenPySuite"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "renpy-suite"


class Settings(dict):
    def __init__(self, path=None):
        super().__init__(DEFAULTS)
        self.path = Path(path) if path else config_dir() / "settings.json"
        try:
            data = json.loads(self.path.read_text("utf-8"))
            if isinstance(data, dict):
                self.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dict(self), indent=2), "utf-8")
