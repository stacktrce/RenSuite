"""Game detection, metadata and the developer-mode patch."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import live, locations, rpa, rpyc

PATCH_FILE = "zz_renpy_suite_patch.rpy"

# option id -> lines inside "init 999 python:"
PATCH_OPTIONS = {
    "developer": ["config.developer = True"],
    "console": ["config.console = True"],
    "skipping": ["config.allow_skipping = True", "config.fast_skipping = True"],
    "rollback": ["config.rollback_enabled = True", "config.hard_rollback_limit = 1000"],
    "live": live.BRIDGE_CODE.splitlines(),
}
# Reloading a running game is a developer-mode feature.
PATCH_REQUIRES = {"live": {"developer"}}

_SAVE_DIR_RE = re.compile(r"""config\.save_directory\s*=\s*[rRuU]?(["'])(.+?)\1""")


def find_game_root(path) -> Path | None:
    """Locate the folder that contains ``game/`` starting from any path inside a game."""
    p = Path(path).resolve()
    if p.is_file():
        p = p.parent
    for cand in [p, *p.parents][:5]:
        if (cand / "game").is_dir():
            return cand
        if cand.name.lower() == "game" and cand.parent.exists():
            return cand.parent
    return None


@dataclass
class GameInfo:
    root: Path
    game_dir: Path
    name: str
    renpy_version: str | None = None
    python: str | None = None
    archives: list = field(default_factory=list)
    rpyc_files: list = field(default_factory=list)
    rpy_files: list = field(default_factory=list)
    save_directory: str | None = None

    @classmethod
    def load(cls, path) -> "GameInfo":
        root = find_game_root(path)
        if root is None:
            raise FileNotFoundError("no Ren'Py game found at %s (expected a 'game' folder)" % path)
        game_dir = root / "game"
        info = cls(root=root, game_dir=game_dir, name=_game_name(root))
        info.renpy_version = _renpy_version(root)
        info.python = _python_flavour(root, info.renpy_version)
        info.archives = sorted(game_dir.rglob("*.rpa"))
        skip = {game_dir / "cache", game_dir / "saves"}
        info.rpyc_files = sorted(p for p in game_dir.rglob("*.rpyc") if not any(s in p.parents for s in skip))
        info.rpy_files = sorted(p for p in game_dir.rglob("*.rpy") if not any(s in p.parents for s in skip))
        info.save_directory = detect_save_directory(info)
        return info

    def save_dirs(self) -> list:
        dirs = [self.game_dir / "saves"]
        if self.save_directory:
            dirs += [home / self.save_directory for home in locations.renpy_home_dirs()]
        return [d for d in dirs if d.is_dir()]

    def script_sources(self, include_archives=True) -> list:
        """``[(display_name, read_bytes)]`` for every .rpyc, loose or archived."""
        out = [(str(p.relative_to(self.game_dir)).replace("\\", "/"), p.read_bytes) for p in self.rpyc_files]
        compiled = {p.with_suffix("") for p in self.rpyc_files}
        out += [(str(p.relative_to(self.game_dir)).replace("\\", "/"), p.read_bytes)
                for p in self.rpy_files
                if p.with_suffix("") not in compiled and p.name != PATCH_FILE
                and live.LIVE_DIR not in p.parts and "renpy_suite_mods" not in p.parts]
        if include_archives:
            for archive_path in self.archives:
                try:
                    archive = rpa.RPAArchive(archive_path)
                except rpa.RPAError:
                    continue
                for name in archive.names():
                    if name.endswith(".rpyc"):
                        out.append(("%s:%s" % (archive_path.name, name), lambda a=archive, n=name: a.read(n)))
        return out


def _game_name(root: Path) -> str:
    exes = sorted(p.stem for p in root.glob("*.exe") if not p.stem.endswith("-32"))
    return exes[0] if exes else root.name


def _renpy_version(root: Path):
    vc = root / "renpy" / "vc_version.py"
    if vc.is_file():
        m = re.search(r"""^version\s*=\s*u?['"]([^'"]+)['"]""", vc.read_text("utf-8", "replace"), re.M)
        if m:
            return m.group(1)
    init = root / "renpy" / "__init__.py"
    if init.is_file():
        m = re.search(r"version_tuple\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", init.read_text("utf-8", "replace"))
        if m:
            return ".".join(m.groups())
    return None


def _python_flavour(root: Path, version):
    lib = root / "lib"
    if lib.is_dir():
        names = [p.name for p in lib.iterdir()]
        if any(n.startswith("py3") for n in names):
            return "Python 3"
        if any(n.startswith("py2") for n in names) or names:
            return "Python 2"
    if version and version.split(".")[0].isdigit():
        return "Python 3" if int(version.split(".")[0]) >= 8 else "Python 2"
    return None


def _save_dir_from_stmts(stmts):
    for node in rpyc.iter_nodes(stmts):
        k = rpyc.kind(node)
        if k == "Define" and rpyc.T(rpyc.get(node, "varname")) == "save_directory" \
                and rpyc.T(rpyc.get(node, "store")) in ("store.config", "config"):
            try:
                value = ast.literal_eval(rpyc.pycode_source(rpyc.get(node, "code")))
                if isinstance(value, str):
                    return value
            except (ValueError, SyntaxError):
                pass
        elif k in ("Python", "EarlyPython"):
            m = _SAVE_DIR_RE.search(rpyc.pycode_source(rpyc.get(node, "code")))
            if m:
                return m.group(2)
    return None


def detect_save_directory(info: GameInfo, limit: int = 40):
    """Find ``config.save_directory`` in scripts, compiled scripts or archives."""
    def options_first(items, name_of):
        return sorted(items, key=lambda x: (not name_of(x).lower().endswith(("options.rpy", "options.rpyc")), name_of(x)))

    for path in options_first(info.rpy_files, lambda p: p.name):
        m = _SAVE_DIR_RE.search(path.read_text("utf-8", "replace"))
        if m:
            return m.group(2)

    sources = options_first(info.script_sources(include_archives=True), lambda s: s[0])
    for _name, read in sources[:limit]:
        try:
            _, stmts = rpyc.read_rpyc(read())
        except Exception:
            continue
        found = _save_dir_from_stmts(stmts)
        if found:
            return found
    return None


# ---------------------------------------------------------------------------
# developer patch
# ---------------------------------------------------------------------------

def patch_path(game_dir) -> Path:
    return Path(game_dir) / PATCH_FILE


def patch_status(game_dir) -> set:
    """Options currently enabled by the patch file (empty set: not installed)."""
    path = patch_path(game_dir)
    if not path.is_file():
        return set()
    text = path.read_text("utf-8", "replace")
    return {opt for opt in PATCH_OPTIONS if "# option: %s" % opt in text}


def apply_patch(game_dir, options) -> Path:
    options = set(options)
    for opt in list(options):
        options |= PATCH_REQUIRES.get(opt, set())
    options = [o for o in PATCH_OPTIONS if o in options]
    if not options:
        remove_patch(game_dir)
        return patch_path(game_dir)
    lines = [
        "# Generated by RenPy Suite. Delete this file and its .rpyc to undo.",
        "init 999 python:",
    ]
    for opt in options:
        lines.append("    # option: %s" % opt)
        lines += [("    " + l) if l.strip() else "" for l in PATCH_OPTIONS[opt]]
    path = patch_path(game_dir)
    path.write_text("\n".join(lines) + "\n", "utf-8")
    # A stale .rpyc from an older patch would otherwise be preferred if newer.
    compiled = path.with_suffix(".rpyc")
    if compiled.exists():
        compiled.unlink()
    return path


def remove_patch(game_dir) -> bool:
    live.LiveGame(Path(game_dir).parent).cleanup()
    removed = False
    for suffix in (".rpy", ".rpyc"):
        p = patch_path(game_dir).with_suffix(suffix)
        if p.exists():
            p.unlink()
            removed = True
    return removed


def default_decompile_dir(info: GameInfo) -> Path:
    return info.root / "decompiled"
