"""Reading and writing Ren'Py archives (.rpa).

Supported: RPA-3.x (including variants whose header carries several XOR
key fields, such as RPA-3.2), RPA-2.0 and RPA-1.0 (separate .rpi index).
"""

from __future__ import annotations

import os
import secrets
import zlib
from pathlib import Path, PurePosixPath

from . import stubpickle


class RPAError(Exception):
    pass


def safe_relpath(name: str) -> Path:
    """Turn an archive member name into a relative path that cannot escape."""
    parts = [p for p in PurePosixPath(name.replace("\\", "/")).parts if p not in ("", ".", "..", "/")]
    parts = [p.replace(":", "_") for p in parts]
    if not parts:
        raise RPAError("invalid member name: %r" % name)
    return Path(*parts)


def _member_name(name) -> str:
    if isinstance(name, bytes):
        try:
            return name.decode("utf-8")
        except UnicodeDecodeError:
            return name.decode("latin-1")
    return str(name)


def _prefix_bytes(prefix) -> bytes:
    if not prefix:
        return b""
    if isinstance(prefix, bytes):
        return prefix
    return str(prefix).encode("latin-1")


def locate_index(path):
    """``(version, xor_key, index_offset)``; offset is None for RPA-1.0 (.rpi file)."""
    path = Path(path)
    with open(path, "rb") as f:
        header = f.read(256).split(b"\n", 1)[0]
    if header.startswith(b"RPA-3."):
        fields = header.split()
        key = 0
        for field in fields[2:]:
            key ^= int(field, 16)
        return fields[0].decode("ascii", "replace"), key, int(fields[1], 16)
    if header.startswith(b"RPA-2.0"):
        return "RPA-2.0", 0, int(header.split()[1], 16)
    if path.with_suffix(".rpi").is_file():
        return "RPA-1.0", 0, None
    raise RPAError("unknown archive format (header %r)" % header[:16])


def read_index_bytes(path) -> bytes:
    """The compressed index exactly as stored in the archive."""
    path = Path(path)
    _, _, offset = locate_index(path)
    if offset is None:
        return path.with_suffix(".rpi").read_bytes()
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read()


def parse_index_bytes(data: bytes) -> dict:
    """The raw (still obfuscated) index: ``{name: [(offset, length[, prefix])]}``."""
    try:
        raw = stubpickle.loads(zlib.decompress(data), allow_stubs=False)
    except Exception as exc:
        raise RPAError("archive index is damaged or obfuscated: %s" % exc) from exc
    if not isinstance(raw, dict):
        raise RPAError("archive index has an unexpected type")
    return raw


def load_raw_index(path) -> dict:
    return parse_index_bytes(read_index_bytes(path))


def save_raw_index(path, raw: dict):
    """Replace an archive's index in place. File data is left untouched."""
    path = Path(path)
    _, _, offset = locate_index(path)
    data = zlib.compress(stubpickle.dumps(raw), 9)
    if offset is None:
        path.with_suffix(".rpi").write_bytes(data)
        return
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(data)
        f.truncate()


def find_raw_key(raw: dict, member: str):
    for k in raw:
        if _member_name(k) == member:
            return k
    return None


class RPAArchive:
    """A Ren'Py archive opened for reading."""

    def __init__(self, path):
        self.path = Path(path)
        self.version, self.index = self._read_index()

    def _read_index(self):
        version, key, _ = locate_index(self.path)
        raw = load_raw_index(self.path)
        index = {}
        for name, entries in raw.items():
            parts = []
            for entry in entries:
                offset, length = entry[0] ^ key, entry[1] ^ key
                prefix = _prefix_bytes(entry[2]) if len(entry) > 2 else b""
                parts.append((offset, length, prefix))
            index[_member_name(name)] = parts
        return version, index

    def names(self) -> list:
        return sorted(self.index)

    def size(self, name: str) -> int:
        return sum(length + len(prefix) for _, length, prefix in self.index[name])

    def read(self, name: str) -> bytes:
        with open(self.path, "rb") as f:
            return self._read(f, name)

    def _read(self, f, name: str) -> bytes:
        chunks = []
        for offset, length, prefix in self.index[name]:
            f.seek(offset)
            chunks.append(prefix + f.read(length))
        return b"".join(chunks)

    def extract(self, dest, names=None, progress=None, cancel=None) -> int:
        """Extract ``names`` (default: everything) into ``dest``.

        ``progress(done, total, name)`` is called before each file;
        ``cancel`` is an optional ``threading.Event``.
        """
        dest = Path(dest)
        names = self.names() if names is None else list(names)
        total = len(names)
        done = 0
        with open(self.path, "rb") as f:
            for name in names:
                if cancel is not None and cancel.is_set():
                    break
                if progress:
                    progress(done, total, name)
                target = dest / safe_relpath(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self._read(f, name))
                done += 1
        if progress:
            progress(done, total, "")
        return done


def pack(source_dir, archive_path, progress=None, cancel=None) -> int:
    """Create an RPA-3.0 archive from every file below ``source_dir``."""
    source_dir = Path(source_dir)
    archive_path = Path(archive_path)
    files = sorted(p for p in source_dir.rglob("*") if p.is_file() and p.resolve() != archive_path.resolve())
    key = secrets.randbits(32)
    header_len = len(b"RPA-3.0 %016x %08x\n" % (0, 0))
    index = {}
    tmp = archive_path.with_name(archive_path.name + ".tmp")
    total = len(files)
    with open(tmp, "wb") as out:
        out.write(b"\0" * header_len)
        for i, path in enumerate(files):
            if cancel is not None and cancel.is_set():
                break
            name = path.relative_to(source_dir).as_posix()
            if progress:
                progress(i, total, name)
            data = path.read_bytes()
            offset = out.tell()
            out.write(data)
            index[name] = [(offset ^ key, len(data) ^ key, b"")]
        index_offset = out.tell()
        out.write(zlib.compress(stubpickle.dumps(index), 9))
        out.seek(0)
        out.write(b"RPA-3.0 %016x %08x\n" % (index_offset, key))
    if cancel is not None and cancel.is_set():
        tmp.unlink()
        return 0
    os.replace(tmp, archive_path)
    if progress:
        progress(len(index), total, "")
    return len(index)


def default_output_dir(archive_path) -> Path:
    """Where to extract an archive without breaking the game.

    Extracting scripts back into ``game/`` makes Ren'Py load them twice, so
    archives inside a game's ``game`` folder are extracted next to it into
    ``<game root>/extracted/<archive name>``.
    """
    archive_path = Path(archive_path).resolve()
    for parent in archive_path.parents:
        if parent.name.lower() == "game":
            return parent.parent / "extracted" / archive_path.stem
    return archive_path.with_name(archive_path.stem + "_extracted")
