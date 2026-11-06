"""Live script editing: put an edited .rpy into a game, and undo it again.

How Ren'Py picks a script: if ``game/foo.rpy`` exists and its MD5 doesn't
match the digest stored in ``game/foo.rpyc``, Ren'Py recompiles the .rpy on
the next start. It reuses statement names from the old .rpyc, so existing
saves keep working.

Scripts stored inside an archive are a special case. Ren'Py would load the
archived copy *and* the loose .rpy as two scripts (duplicate labels). So the
member is removed from the archive's index (the data stays in the file),
and the original .rpyc is placed next to the new .rpy instead.

Everything that is changed is backed up to ``<game root>/renpy_suite_backup``
and recorded in a manifest, so :meth:`ScriptEditor.restore` can undo it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import rpa, rpyc

BACKUP_DIR = "renpy_suite_backup"


def script_rel(display_name: str) -> str:
    """``archive.rpa:dir/x.rpyc`` or ``dir/x.rpyc`` → ``dir/x`` (relative to game/)."""
    return rpyc.output_relpath(display_name).with_suffix("").as_posix()


class ScriptEditor:
    def __init__(self, game):
        self.game = game
        self.backup_root = game.root / BACKUP_DIR
        self.manifest_path = self.backup_root / "manifest.json"

    # -- manifest ----------------------------------------------------------
    # Always read from disk: the Scripts tab and the mod installer share it.

    @property
    def manifest(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_manifest(self, manifest: dict):
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2), "utf-8")

    # -- queries -----------------------------------------------------------

    def paths(self, rel: str):
        base = self.game.game_dir / rel
        return base.with_name(base.name + ".rpy"), base.with_name(base.name + ".rpyc")

    def is_edited(self, display_name: str) -> bool:
        return script_rel(display_name) in self.manifest

    def load_text(self, display_name: str, read) -> tuple:
        """``(text, from_source)``: the .rpy if one exists next to it, else decompiled code."""
        rpy, _ = self.paths(script_rel(display_name))
        if rpy.is_file():
            return rpy.read_text("utf-8-sig", "replace"), True
        return rpyc.decompile(read(), display_name), False

    # -- apply / restore ---------------------------------------------------

    def _archive_for(self, display_name: str):
        if ".rpa:" not in display_name:
            return None, None
        archive_name, member = display_name.split(":", 1)
        for path in self.game.archives:
            if path.name == archive_name:
                return path, member
        return None, None

    def _backup_file(self, src: Path, rel_name: str) -> str:
        dest = self.backup_root / "files" / rel_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest.relative_to(self.backup_root).as_posix()

    def apply(self, display_name: str, read, text: str) -> Path:
        """Write ``text`` as the game's version of this script."""
        rel = script_rel(display_name)
        rpy, rpyc_path = self.paths(rel)
        manifest = self.manifest
        if rel not in manifest:
            entry = {"rpy_backup": None, "rpyc_backup": None, "archive": None, "member": None}
            if rpy.is_file():
                entry["rpy_backup"] = self._backup_file(rpy, rel + ".rpy")
            if rpyc_path.is_file():
                entry["rpyc_backup"] = self._backup_file(rpyc_path, rel + ".rpyc")
            archive, member = self._archive_for(display_name)
            if archive is not None:
                raw = rpa.load_raw_index(archive)
                key = rpa.find_raw_key(raw, member)
                if key is not None:
                    original = read()
                    index_backup = self.backup_root / "archives" / (archive.relative_to(self.game.game_dir).as_posix() + ".index")
                    if not index_backup.exists():
                        index_backup.parent.mkdir(parents=True, exist_ok=True)
                        index_backup.write_bytes(rpa.read_index_bytes(archive))
                    if not rpyc_path.exists():
                        rpyc_path.parent.mkdir(parents=True, exist_ok=True)
                        rpyc_path.write_bytes(original)
                    del raw[key]
                    rpa.save_raw_index(archive, raw)
                    entry["archive"] = archive.relative_to(self.game.game_dir).as_posix()
                    entry["member"] = member
            manifest[rel] = entry
            self._save_manifest(manifest)
        rpy.parent.mkdir(parents=True, exist_ok=True)
        rpy.write_text(text, "utf-8")
        return rpy

    def restore(self, display_name: str) -> bool:
        """Undo :meth:`apply` for this script. Returns False if it wasn't edited."""
        rel = script_rel(display_name)
        manifest = self.manifest
        entry = manifest.get(rel)
        if entry is None:
            return False
        rpy, rpyc_path = self.paths(rel)
        for path, backup in ((rpy, entry["rpy_backup"]), (rpyc_path, entry["rpyc_backup"])):
            if path.exists():
                path.unlink()
            if backup:
                shutil.copy2(self.backup_root / backup, path)
        if entry["archive"]:
            archive = self.game.game_dir / entry["archive"]
            index_backup = self.backup_root / "archives" / (entry["archive"] + ".index")
            original = rpa.parse_index_bytes(index_backup.read_bytes())
            key = rpa.find_raw_key(original, entry["member"])
            raw = rpa.load_raw_index(archive)
            if key is not None and rpa.find_raw_key(raw, entry["member"]) is None:
                raw[key] = original[key]
                rpa.save_raw_index(archive, raw)
        del manifest[rel]
        self._save_manifest(manifest)
        return True

    def edited(self) -> list:
        return sorted(self.manifest)
