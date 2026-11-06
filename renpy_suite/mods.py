"""Shareable mods for Ren'Py games — a bit like Cheat Engine tables.

A mod is a ``.rsmod`` file (a zip) or a folder containing ``mod.json``::

    my-mod/
      mod.json          metadata, replacements and cheats
      game/             optional: files copied into the game
        cheats.rpy        → game/renpy_suite_mods/<id>/cheats.rpy

``mod.json``::

    {
      "format": "renpy-suite-mod", "format_version": 1,
      "id": "my-mod", "name": "My mod", "version": "1.0", "author": "me",
      "description": "What it does",
      "game": {"name": "Some Game", "save_directory": "SomeGame-123"},
      "replacements": [{"script": "script.rpy", "find": "...", "replace": "..."}],
      "cheats": [{"name": "money", "value": 9999, "label": "Lots of money"}]
    }

Files and replacements are installed into a game (and can be uninstalled
exactly). Cheats are variable values the user applies on demand to the
running game or to a save. See docs/MODDING.md for the full description.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import live, saves, savetoken, settings
from .rpa import RPAError, safe_relpath
from .scriptedit import BACKUP_DIR, ScriptEditor, script_rel

FORMAT = "renpy-suite-mod"
FORMAT_VERSION = 1
MOD_SUFFIX = ".rsmod"
INSTALL_DIR = "renpy_suite_mods"  # inside game/
MAX_TOTAL_SIZE = 200 * 1024 * 1024
MAX_FILES = 5000

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_VAR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class ModError(Exception):
    """An error with an i18n key and parameters, so the GUI can translate it."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params

    def __str__(self):
        from .i18n import t
        return t(self.key, **self.params)


@dataclass
class Replacement:
    script: str
    find: str
    replace: str


@dataclass
class Cheat:
    name: str
    value: object
    label: str = ""
    description: str = ""


@dataclass
class Mod:
    id: str
    name: str
    version: str = ""
    author: str = ""
    description: str = ""
    game: dict = field(default_factory=dict)
    replacements: list = field(default_factory=list)
    cheats: list = field(default_factory=list)
    files: dict = field(default_factory=dict)  # posix path below game/ -> bytes
    source: Path | None = None

    @property
    def scripts(self) -> list:
        return sorted(p for p in self.files if p.endswith(".rpy"))

    @property
    def runs_code(self) -> bool:
        return bool(self.scripts or self.replacements)

    def to_json(self) -> dict:
        return {
            "format": FORMAT, "format_version": FORMAT_VERSION,
            "id": self.id, "name": self.name, "version": self.version, "author": self.author,
            "description": self.description, "game": self.game,
            "replacements": [r.__dict__ for r in self.replacements],
            "cheats": [c.__dict__ for c in self.cheats],
        }

    def package(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mod.json", json.dumps(self.to_json(), indent=2, ensure_ascii=False))
            for path, data in sorted(self.files.items()):
                zf.writestr("game/" + path, data)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# loading & validation
# ---------------------------------------------------------------------------

def _text(data: dict, key: str, default="") -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ModError("mod_err_field", field=key)
    return value


def parse(meta, files: dict, source=None) -> Mod:
    if not isinstance(meta, dict) or meta.get("format") != FORMAT:
        raise ModError("mod_err_format")
    version = meta.get("format_version", 1)
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise ModError("mod_err_newer")
    mod_id = _text(meta, "id")
    if not _ID_RE.match(mod_id):
        raise ModError("mod_err_field", field="id")
    name = _text(meta, "name") or mod_id
    game = meta.get("game") or {}
    if not isinstance(game, dict) or not all(isinstance(v, str) for v in game.values()):
        raise ModError("mod_err_field", field="game")

    replacements = []
    for item in meta.get("replacements") or []:
        if not isinstance(item, dict):
            raise ModError("mod_err_field", field="replacements")
        r = Replacement(_text(item, "script"), _text(item, "find"), _text(item, "replace"))
        if not r.script or not r.find:
            raise ModError("mod_err_field", field="replacements")
        replacements.append(r)

    cheats = []
    for item in meta.get("cheats") or []:
        if not isinstance(item, dict) or not _VAR_RE.match(str(item.get("name", ""))) or "value" not in item:
            raise ModError("mod_err_field", field="cheats")
        try:
            live.check_plain(item["value"])
        except ValueError:
            raise ModError("mod_err_field", field="cheats.value") from None
        cheats.append(Cheat(item["name"], item["value"], _text(item, "label") or item["name"],
                            _text(item, "description")))

    clean = {}
    total = 0
    for path, data in files.items():
        try:
            rel = safe_relpath(path).as_posix()
        except RPAError:
            raise ModError("mod_err_path", path=path) from None
        total += len(data)
        clean[rel] = data
    if len(clean) > MAX_FILES or total > MAX_TOTAL_SIZE:
        raise ModError("mod_err_size")

    return Mod(mod_id, name, _text(meta, "version"), _text(meta, "author"), _text(meta, "description"),
               game, replacements, cheats, clean, Path(source) if source else None)


def load(path) -> Mod:
    """Load a mod from a ``.rsmod``/``.zip`` file, a ``mod.json`` or a folder."""
    path = Path(path)
    if path.is_dir() or path.name.lower() == "mod.json":
        root = path if path.is_dir() else path.parent
        try:
            meta = json.loads((root / "mod.json").read_text("utf-8-sig"))
        except (OSError, ValueError):
            raise ModError("mod_err_format") from None
        game_dir = root / "game"
        files = {}
        if game_dir.is_dir():
            files = {p.relative_to(game_dir).as_posix(): p.read_bytes()
                     for p in sorted(game_dir.rglob("*")) if p.is_file()}
        return parse(meta, files, path)

    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise ModError("mod_err_format") from None
    with zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        candidates = sorted((n for n in names if PurePosixPath(n).name == "mod.json"), key=lambda n: n.count("/"))
        if not candidates:
            raise ModError("mod_err_format")
        prefix = candidates[0][: -len("mod.json")]
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_TOTAL_SIZE:
            raise ModError("mod_err_size")
        try:
            meta = json.loads(zf.read(candidates[0]).decode("utf-8-sig"))
        except ValueError:
            raise ModError("mod_err_format") from None
        files = {}
        game_prefix = prefix + "game/"
        for n in names:
            if n.startswith(game_prefix) and len(n) > len(game_prefix):
                files[n[len(game_prefix):]] = zf.read(n)
    return parse(meta, files, path)


def pack(folder, output) -> Mod:
    mod = load(folder)
    Path(output).write_bytes(mod.package())
    return mod


# ---------------------------------------------------------------------------
# library
# ---------------------------------------------------------------------------

class ModLibrary:
    """Imported mods, kept as ``<id>.rsmod`` in the user's config folder."""

    def __init__(self, path=None):
        self.path = Path(path) if path else settings.config_dir() / "mods"

    def mods(self) -> list:
        out = []
        if self.path.is_dir():
            for p in sorted(self.path.glob("*" + MOD_SUFFIX)):
                try:
                    out.append(load(p))
                except ModError:
                    continue
        return sorted(out, key=lambda m: m.name.lower())

    def add(self, source) -> Mod:
        mod = load(source)
        self.path.mkdir(parents=True, exist_ok=True)
        target = self.path / (mod.id + MOD_SUFFIX)
        target.write_bytes(mod.package())
        mod.source = target
        return mod

    def remove(self, mod_id: str):
        target = self.path / (mod_id + MOD_SUFFIX)
        if target.exists():
            target.unlink()


# ---------------------------------------------------------------------------
# installing into a game
# ---------------------------------------------------------------------------

def _norm_script(name: str) -> str:
    name = name.replace("\\", "/").lstrip("/")
    if name.startswith("game/"):
        name = name[5:]
    for suffix in (".rpyc", ".rpy"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _no_read():
    raise ModError("mod_err_script", script="?")


class ModInstaller:
    def __init__(self, game):
        self.game = game
        self.editor = ScriptEditor(game)
        self.state_dir = game.root / BACKUP_DIR / "mods"
        self.manifest_path = self.state_dir / "installed.json"

    # -- manifest ---------------------------------------------------------

    def installed(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, manifest):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2), "utf-8")

    def install_dir(self, mod_id: str) -> Path:
        return self.game.game_dir / INSTALL_DIR / mod_id

    # -- checks -----------------------------------------------------------

    def _find_script(self, script: str):
        rel = _norm_script(script)
        for name, read in self.game.script_sources(include_archives=True):
            if script_rel(name) == rel:
                return name, read
        if (self.game.game_dir / (rel + ".rpy")).is_file():
            return rel + ".rpyc", _no_read
        return None

    def _prepare(self, mod: Mod) -> dict:
        """``{display: (read, before, after)}`` or raise ModError if a replacement can't apply."""
        result = {}
        for r in mod.replacements:
            handle = self._find_script(r.script)
            if handle is None:
                raise ModError("mod_err_script", script=r.script)
            display, read = handle
            if display not in result:
                text, _ = self.editor.load_text(display, read)
                result[display] = [read, text, text]
            entry = result[display]
            if r.find not in entry[2]:
                raise ModError("mod_err_find", script=r.script, find=r.find.strip().splitlines()[0][:80])
            entry[2] = entry[2].replace(r.find, r.replace)
        return {k: tuple(v) for k, v in result.items()}

    def check(self, mod: Mod) -> tuple:
        """``(warnings, error)``: warnings are ModErrors; error is a ModError or None."""
        warnings = []
        want = mod.game.get("name")
        if want and want.lower() not in (self.game.name.lower(), self.game.root.name.lower()):
            warnings.append(ModError("mod_warn_game", game=want))
        want_dir = mod.game.get("save_directory")
        if want_dir and self.game.save_directory and want_dir != self.game.save_directory:
            warnings.append(ModError("mod_warn_game", game=want_dir))
        if mod.id in self.installed():
            # Reinstalling uninstalls first, so the current (modded) scripts are not what it will patch.
            return warnings, None
        try:
            self._prepare(mod)
        except ModError as exc:
            return warnings, exc
        return warnings, None

    # -- install / uninstall ----------------------------------------------

    def install(self, mod: Mod):
        if mod.id in self.installed():
            self.uninstall(mod.id)
        prepared = self._prepare(mod)

        target = self.install_dir(mod.id)
        written = []
        for rel, data in mod.files.items():
            path = target / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            written.append(path.relative_to(self.game.game_dir).as_posix())

        snapshot = self.state_dir / mod.id
        scripts = []
        for i, (display, (read, before, after)) in enumerate(prepared.items()):
            was_edited = self.editor.is_edited(display)
            snapshot.mkdir(parents=True, exist_ok=True)
            (snapshot / ("%d.before.rpy" % i)).write_text(before, "utf-8")
            (snapshot / ("%d.after.rpy" % i)).write_text(after, "utf-8")
            self.editor.apply(display, read, after)
            scripts.append({"display": display, "snapshot": i, "was_edited": was_edited})

        manifest = self.installed()
        manifest[mod.id] = {
            "name": mod.name, "version": mod.version, "files": written, "scripts": scripts,
            "replacements": [r.__dict__ for r in mod.replacements],
            "installed": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save(manifest)

    def uninstall(self, mod_id: str) -> list:
        """Remove a mod. Returns scripts that couldn't be reverted automatically."""
        manifest = self.installed()
        entry = manifest.get(mod_id)
        if entry is None:
            return []
        for rel in entry["files"]:
            path = self.game.game_dir / rel
            for p in (path, path.with_suffix(".rpyc") if path.suffix == ".rpy" else None):
                if p is not None and p.exists():
                    p.unlink()
        mod_dir = self.install_dir(mod_id)
        if mod_dir.exists():
            shutil.rmtree(mod_dir, ignore_errors=True)
        root = self.game.game_dir / INSTALL_DIR
        if root.is_dir() and not any(root.iterdir()):
            root.rmdir()

        failed = []
        snapshot = self.state_dir / mod_id
        replacements = [Replacement(**r) for r in entry.get("replacements", [])]
        for script in entry["scripts"]:
            display = script["display"]
            before = (snapshot / ("%d.before.rpy" % script["snapshot"])).read_text("utf-8")
            after = (snapshot / ("%d.after.rpy" % script["snapshot"])).read_text("utf-8")
            try:
                current, _ = self.editor.load_text(display, _no_read)
            except ModError:
                continue  # the user already restored the original script
            if current == after:
                if script["was_edited"]:
                    self.editor.apply(display, _no_read, before)
                else:
                    self.editor.restore(display)
                continue
            # Edited after installing: undo just this mod's replacements if possible.
            mine = [r for r in replacements if script_rel(_norm_script(r.script) + ".rpyc") == script_rel(display)]
            if all(r.replace in current for r in mine):
                for r in reversed(mine):
                    current = current.replace(r.replace, r.find)
                self.editor.apply(display, _no_read, current)
            else:
                failed.append(display)

        shutil.rmtree(snapshot, ignore_errors=True)
        del manifest[mod_id]
        self._save(manifest)
        return failed


# ---------------------------------------------------------------------------
# cheats
# ---------------------------------------------------------------------------

def apply_cheats_live(game, cheats, freeze=False) -> int:
    client = live.LiveGame(game.root)
    if not client.is_running():
        raise ModError("live_not_running")
    if freeze and not client.supports_freeze():
        raise ModError("freeze_old_patch")
    for cheat in cheats:
        if freeze:
            client.freeze(cheat.name, cheat.value)
        else:
            client.set_variable(cheat.name, cheat.value)
    return len(cheats)


def apply_cheats_to_save(path, cheats, keys=None):
    """Set cheat values in a save. Returns ``(applied, missing, write_result)``."""
    doc = saves.SaveFile(path)
    applied, missing = [], []
    for cheat in cheats:
        key = next((k for k in doc.variables if (k.decode("utf-8", "replace") if isinstance(k, bytes) else k)
                    == "store." + cheat.name), None)
        if key is None:
            missing.append(cheat.name)
            continue
        doc.variables[key] = cheat.value
        applied.append(cheat.name)
    result = None
    if applied:
        if keys is None:
            keys = savetoken.load_signing_keys() if doc.is_signed else []
        result = doc.write(keys=keys)
    return applied, missing, result
