"""Cheat-Engine style value search across snapshots of a game's variables.

1. Take a snapshot (from the running game or a save).
2. Do something in the game (spend money, raise affection …).
3. Take the next snapshot and keep only the values that changed the way you
   expect (increased, decreased, equal to a number …).
4. Repeat until only the variable you are looking for is left.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import live, saves, values

SCALARS = (bool, int, float, str, bytes, type(None))
MISSING = object()

FILTERS = ("changed", "unchanged", "increased", "decreased", "equals", "all")


@dataclass
class Snapshot:
    source: str
    values: dict  # path -> scalar
    taken: float = field(default_factory=time.time)


def flatten(variables: dict, max_depth: int = 5, limit: int = 50000, include_internal: bool = False) -> dict:
    """``{"money": 10, "player.hp": 5, "inventory[0]": "sword", …}`` for every scalar."""
    out = {}

    def walk(path, value, depth):
        if len(out) >= limit:
            return
        if isinstance(value, SCALARS):
            out[path] = value
            return
        if depth >= max_depth:
            return
        for label, _ref, child in values.children(value):
            if label.startswith(("[", ".")):
                sub = path + label
            elif label.startswith("("):
                continue  # constructor arguments: not game state
            else:
                sub = "%s[%r]" % (path, label)
            walk(sub, child, depth + 1)

    for key, value in variables.items():
        name = values.fmt_key(key)
        if name.startswith("store."):
            name = name[6:]
        if "." in name:
            continue  # named stores (e.g. store.achievement.*) are rarely what you search for
        if not include_internal and name.startswith("_"):
            continue
        walk(name, value, 0)
    return out


def snapshot_live(game_root) -> Snapshot:
    client = live.LiveGame(game_root)
    state = client.read_state() if client.is_running() else None
    if not state:
        raise ValueError("live_not_running")
    return Snapshot("live", flatten(state.get("variables", {})))


def snapshot_save(path) -> Snapshot:
    return Snapshot(str(path), flatten(saves.SaveFile(path).variables))


def _number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def matches(mode: str, old, new, wanted=None) -> bool:
    if mode == "all":
        return True
    if mode == "changed":
        return old is MISSING or new is MISSING or old != new or type(old) is not type(new)
    if mode == "unchanged":
        return old is not MISSING and new is not MISSING and old == new and type(old) is type(new)
    if mode in ("increased", "decreased"):
        a, b = _number(old), _number(new)
        if a is None or b is None:
            return False
        return b > a if mode == "increased" else b < a
    if mode == "equals":
        return equals(new, wanted)
    raise ValueError(mode)


def equals(value, wanted: str) -> bool:
    if value is MISSING or wanted is None:
        return False
    text = wanted.strip()
    if isinstance(value, bool):
        return text.lower() in (("true", "1", "yes") if value else ("false", "0", "no"))
    if _number(value) is not None:
        try:
            return float(text) == float(value)
        except ValueError:
            return False
    if isinstance(value, bytes):
        value = values.edit_text(value)
    return str(value) == text


class Scan:
    """One search session: a previous snapshot plus the remaining candidate paths."""

    def __init__(self):
        self.previous = None
        self.candidates = None  # None = everything

    def first(self, snap: Snapshot, mode="all", wanted=None) -> list:
        self.previous = snap
        rows = [(p, MISSING, v) for p, v in snap.values.items()]
        if mode == "equals":
            rows = [r for r in rows if equals(r[2], wanted)]
            self.candidates = {r[0] for r in rows}
        else:
            self.candidates = None
        return sorted(rows)

    def next(self, snap: Snapshot, mode="changed", wanted=None) -> list:
        if self.previous is None:
            return self.first(snap, mode, wanted)
        before, after = self.previous.values, snap.values
        paths = self.candidates if self.candidates is not None else set(before) | set(after)
        rows = []
        for p in paths:
            old, new = before.get(p, MISSING), after.get(p, MISSING)
            if matches(mode, old, new, wanted):
                rows.append((p, old, new))
        self.previous = snap
        self.candidates = {r[0] for r in rows}
        return sorted(rows)


def top_level(path: str):
    """The variable name if ``path`` is a whole top-level variable, else None."""
    return path if path.isidentifier() else None
