"""Reading, editing and writing Ren'Py save files and persistent data."""

from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from . import locations, savetoken
from . import stubpickle as sp

SAVE_SUFFIX = ".save"


@dataclass
class SaveEntry:
    path: Path
    mtime: float

    @property
    def slot(self) -> str:
        return self.path.stem


def list_saves(dirs) -> list:
    """All ``*.save`` files in ``dirs``, newest first."""
    seen = set()
    out = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for p in d.glob("*" + SAVE_SUFFIX):
            key = os.path.normcase(str(p.resolve()))
            if key in seen or not p.is_file():
                continue
            seen.add(key)
            out.append(SaveEntry(p, p.stat().st_mtime))
    out.sort(key=lambda e: e.mtime, reverse=True)
    return out


def find_persistent(dirs) -> list:
    """``persistent`` files in ``dirs``, newest first."""
    found = [Path(d) / "persistent" for d in dirs if (Path(d) / "persistent").is_file()]
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


def default_save_dirs(game=None) -> list:
    """Save directories for ``game`` (a GameInfo), or every known game."""
    if game is not None:
        dirs = game.save_dirs()
        if dirs:
            return dirs
    return locations.global_save_dirs()


def _backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name("%s.%s.bak" % (path.name, stamp))
    shutil.copy2(path, backup)
    return backup


@dataclass
class WriteResult:
    path: Path
    backup: Path | None
    signed: bool
    needs_signature: bool


class SaveFile:
    """A ``.save`` file: a zip with a pickled ``(roots, log)`` member."""

    def __init__(self, path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as zf:
            self._infos = zf.infolist()
            self.members = {info.filename: zf.read(info) for info in self._infos}
        if "log" not in self.members:
            raise ValueError("not a Ren'Py save (no 'log' member)")
        self.roots, self.log = sp.loads(self.members["log"])

    @property
    def variables(self) -> dict:
        return self.roots

    @property
    def extra_info(self) -> str:
        return self.members.get("extra_info", b"").decode("utf-8", "replace")

    @property
    def renpy_version(self) -> str:
        return self.members.get("renpy_version", b"").decode("utf-8", "replace")

    @property
    def screenshot(self):
        return self.members.get("screenshot.png")

    @property
    def metadata(self) -> dict:
        try:
            return json.loads(self.members.get("json", b"{}").decode("utf-8"))
        except ValueError:
            return {}

    @property
    def is_signed(self) -> bool:
        return bool(self.members.get("signatures", b"").strip())

    def write(self, path=None, backup=True, keys=None) -> WriteResult:
        """Write the (edited) save. Re-signs it if the original was signed."""
        path = Path(path) if path else self.path
        log = sp.dumps((self.roots, self.log))
        if keys is None:
            keys = savetoken.load_signing_keys() if self.is_signed else []
        signatures = savetoken.sign_data(log, keys) if self.is_signed and keys else ""

        tmp = path.with_name(path.name + ".new")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for info in self._infos:
                if info.filename in ("log", "signatures"):
                    continue
                zf.writestr(info, self.members[info.filename])
            zf.writestr("log", log)
            if signatures:
                zf.writestr("signatures", signatures)

        backup_path = _backup(path) if backup and path.exists() else None
        os.replace(tmp, path)
        return WriteResult(path, backup_path, bool(signatures), self.is_signed)


class PersistentFile:
    """The ``persistent`` file: zlib-compressed pickle + optional signatures."""

    def __init__(self, path):
        self.path = Path(path)
        decomp = zlib.decompressobj()
        self.data = decomp.decompress(self.path.read_bytes())
        self.signatures = decomp.unused_data.decode("utf-8", "replace")
        self.obj = sp.loads(self.data)

    @property
    def variables(self) -> dict:
        if sp.is_stub(self.obj):
            st = sp.state(self.obj)
            if isinstance(st, dict):
                return st
        if isinstance(self.obj, dict):
            return self.obj
        raise ValueError("unexpected persistent data layout")

    @property
    def is_signed(self) -> bool:
        return bool(self.signatures.strip())

    def write(self, path=None, backup=True, keys=None) -> WriteResult:
        path = Path(path) if path else self.path
        data = sp.dumps(self.obj)
        if keys is None:
            keys = savetoken.load_signing_keys() if self.is_signed else []
        signatures = savetoken.sign_data(data, keys) if self.is_signed and keys else ""
        tmp = path.with_name(path.name + ".suite-tmp")
        tmp.write_bytes(zlib.compress(data, 3) + signatures.encode("utf-8"))
        backup_path = _backup(path) if backup and path.exists() else None
        os.replace(tmp, path)
        return WriteResult(path, backup_path, bool(signatures), self.is_signed)


def is_internal(name: str) -> bool:
    """True for Ren'Py's own bookkeeping variables (``store._foo``)."""
    return name.rpartition(".")[2].startswith("_")
