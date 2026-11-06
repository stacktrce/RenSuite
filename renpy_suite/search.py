"""Search the text of every script in a game (decompiled where needed)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .scriptedit import ScriptEditor, script_rel

MAX_HITS = 5000


@dataclass
class Hit:
    script: str  # display name as used by GameInfo.script_sources()
    line: int    # 1-based
    text: str


class ScriptIndex:
    """Caches decompiled scripts so repeated searches are fast."""

    def __init__(self, game):
        self.game = game
        self.editor = ScriptEditor(game)
        self._cache = {}
        self.errors = []

    def texts(self, progress=None, cancel=None):
        sources = self.game.script_sources(include_archives=True)
        self.errors = []
        for i, (name, read) in enumerate(sources):
            if cancel is not None and cancel.is_set():
                return
            if progress:
                progress(i, len(sources), name)
            has_source = self.editor.paths(script_rel(name))[0].is_file()
            text = None if has_source else self._cache.get(name)
            if text is None:
                try:
                    text, from_source = self.editor.load_text(name, read)
                except Exception as exc:
                    self.errors.append((name, str(exc)))
                    continue
                if not from_source:  # .rpy files may be edited meanwhile; only cache decompiled ones
                    self._cache[name] = text
            yield name, text
        if progress:
            progress(len(sources), len(sources), "")

    def search(self, query: str, regex=False, case=False, progress=None, cancel=None) -> list:
        if not query:
            return []
        flags = 0 if case else re.IGNORECASE
        pattern = re.compile(query if regex else re.escape(query), flags)
        hits = []
        for name, text in self.texts(progress, cancel):
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append(Hit(name, number, line.strip()))
                    if len(hits) >= MAX_HITS:
                        return hits
        return hits
