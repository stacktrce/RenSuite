"""Export a game's dialogue for fan translations.

* ``dialogue.csv`` — one row per line (open it in Excel / LibreOffice / Google Sheets),
* ``tl/<language>/…`` — Ren'Py translation files, ready to copy into ``game/tl``.

Translated text can be filled in from the CSV's ``translation`` column, so the
workflow is: export CSV → translate it → build the tl files from it.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from . import rpyc
from . import stubpickle as sp
from .scriptedit import script_rel

LANG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CSV_FIELDS = ("script", "kind", "identifier", "who", "original", "translation")


@dataclass
class Line:
    script: str          # game-relative .rpy path, e.g. "script.rpy"
    kind: str            # "say" or "string" (menu choices and other strings)
    identifier: str      # Ren'Py translation id for "say", "" for strings
    who: str
    original: str

    @property
    def key(self):
        return self.identifier if self.kind == "say" else "string:" + self.original


def _say_line(node, script, identifier) -> Line:
    get = rpyc.get
    return Line(script, "say", identifier or "", rpyc.T(get(node, "who")) or "", rpyc.T(get(node, "what")) or "")


def _walk(nodes, script, out, identifier=None):
    for node in nodes or []:
        if not sp.is_stub(node):
            continue
        k = rpyc.kind(node)
        get = rpyc.get
        if k == "Translate":
            if get(node, "language") is None:
                _walk(get(node, "block"), script, out, rpyc.T(get(node, "identifier")))
            continue
        if k == "TranslateSay":
            if get(node, "language") is None:
                out.append(_say_line(node, script, rpyc.T(get(node, "identifier"))))
            continue
        if k == "Say":
            out.append(_say_line(node, script, identifier))
            continue
        if k == "Menu":
            for label, _cond, block in get(node, "items") or []:
                text = rpyc.T(label)
                if text:
                    out.append(Line(script, "string", "", "", text))
                if block:
                    _walk(block, script, out)
            continue
        if k in ("TranslateString", "TranslateBlock", "TranslateEarlyBlock", "TranslatePython", "EndTranslate"):
            continue
        if isinstance(get(node, "block"), list):
            _walk(get(node, "block"), script, out)
        for entry in get(node, "entries") or []:
            if isinstance(entry, (tuple, list)) and len(entry) == 2:
                _walk(entry[1], script, out)


def extract(game, progress=None, cancel=None) -> tuple:
    """``(lines, errors)`` for every compiled script of ``game``."""
    lines, errors = [], []
    sources = [s for s in game.script_sources(include_archives=True) if not s[0].endswith(".rpy")]
    for i, (name, read) in enumerate(sources):
        if cancel is not None and cancel.is_set():
            break
        if progress:
            progress(i, len(sources), name)
        try:
            _, stmts = rpyc.read_rpyc(read())
        except Exception as exc:
            errors.append((name, str(exc)))
            continue
        _walk(stmts, script_rel(name) + ".rpy", lines)
    if progress:
        progress(len(sources), len(sources), "")
    return lines, errors


def write_csv(lines, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_FIELDS)
        for line in lines:
            writer.writerow((line.script, line.kind, line.identifier, line.who, line.original, ""))


def read_translations(path) -> dict:
    """``{key: translated text}`` from a filled-in CSV (empty translations are skipped)."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            text = (row.get("translation") or "").strip("\r\n")
            if not text:
                continue
            if row.get("kind") == "say" and row.get("identifier"):
                out[row["identifier"]] = text
            elif row.get("kind") == "string":
                out["string:" + (row.get("original") or "")] = text
    return out


def write_tl(lines, language: str, out_dir, translations=None) -> dict:
    """Write ``out_dir/tl/<language>/<script>.rpy`` files. Returns counts."""
    if not LANG_RE.match(language):
        raise ValueError("language must be a simple name like 'german' or 'french'")
    translations = translations or {}
    root = Path(out_dir) / "tl" / language
    by_script = {}
    for line in lines:
        by_script.setdefault(line.script, []).append(line)

    seen_ids, seen_strings = set(), set()
    counts = {"say": 0, "string": 0, "translated": 0, "skipped": 0}
    for script, items in sorted(by_script.items()):
        say_blocks, string_blocks = [], []
        for line in items:
            if line.kind == "say":
                if not line.identifier or line.identifier in seen_ids:
                    counts["skipped"] += 1  # pre-6.15 scripts have no translation ids
                    continue
                seen_ids.add(line.identifier)
                original = ((line.who + " ") if line.who else "") + rpyc.encode_say_string(line.original)
                new_text = translations.get(line.key)
                translated = ((line.who + " ") if line.who else "") + rpyc.encode_say_string(new_text or line.original)
                counts["translated"] += bool(new_text)
                say_blocks.append("# game/%s\ntranslate %s %s:\n\n    # %s\n    %s\n"
                                  % (script, language, line.identifier, original, translated))
                counts["say"] += 1
            else:
                if line.original in seen_strings:
                    continue
                seen_strings.add(line.original)
                new_text = translations.get(line.key)
                counts["translated"] += bool(new_text)
                string_blocks.append("    # game/%s\n    old %s\n    new %s\n"
                                     % (script, rpyc.encode_say_string(line.original),
                                        rpyc.encode_say_string(new_text or line.original)))
                counts["string"] += 1
        if not say_blocks and not string_blocks:
            continue
        target = root / script
        target.parent.mkdir(parents=True, exist_ok=True)
        parts = ["# Translation template generated by RenPy Suite.\n"] + say_blocks
        if string_blocks:
            parts.append("translate %s strings:\n\n%s" % (language, "\n".join(string_blocks)))
        target.write_text("\n".join(parts), "utf-8")
    return counts
