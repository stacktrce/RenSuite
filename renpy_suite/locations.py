"""Where Ren'Py keeps saves on each platform."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def renpy_home_dirs() -> list:
    """Per-user Ren'Py directories that exist on this machine.

    Mirrors ``path_to_saves`` in Ren'Py's launcher script:
    Windows ``%APPDATA%/RenPy``, macOS ``~/Library/RenPy``, Linux ``~/.renpy``.
    """
    candidates = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "RenPy")
        candidates.append(Path.home() / "RenPy")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "RenPy")
    else:
        candidates.append(Path.home() / ".renpy")
    return [p for p in candidates if p.is_dir()]


def global_save_dirs() -> list:
    """Every game's save directory under the per-user Ren'Py directories."""
    dirs = []
    for home in renpy_home_dirs():
        for child in sorted(home.iterdir()):
            if child.is_dir() and child.name != "tokens":
                dirs.append(child)
    return dirs
