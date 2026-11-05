"""Safe, round-trip capable pickle handling for Ren'Py data — without Ren'Py.

Ren'Py stores saves, persistent data, script files (.rpyc) and archive
indexes as Python pickles that reference Ren'Py's own classes. Loading such
a pickle with the standard library would try to import (and execute) those
classes, which is both impossible without Ren'Py and unsafe for files from
untrusted sources.

Instead, every class or function a pickle references is replaced with a
:class:`Stub`. Stubs record exactly how they were constructed (constructor
arguments, state, list items, dict items) so the object graph can be
inspected, edited and written back producing a pickle that Ren'Py loads as
if it had written it itself. No code from the pickle is ever executed: only
a small whitelist of harmless standard-library types is resolved for real.
"""

from __future__ import annotations

import codecs
import collections
import copyreg
import datetime
import io
import pickle

_MISSING = object()


class Stub:
    """Stand-in for a class referenced by a pickle."""

    _rs_module = ""
    _rs_name = ""

    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls)
        self._rs_args = list(args)
        self._rs_kwargs = dict(kwargs)
        self._rs_called = False
        self._rs_state = _MISSING
        self._rs_items = None
        self._rs_dict = None
        return self

    def __init__(self, *args, **kwargs):
        # Only reached when the pickle *calls* the class (REDUCE opcode);
        # NEWOBJ creates instances through __new__ alone.
        self._rs_called = True

    def __setstate__(self, state):
        self._rs_state = state

    def append(self, value):
        if self._rs_items is None:
            self._rs_items = []
        self._rs_items.append(value)

    def extend(self, values):
        for v in values:
            self.append(v)

    def __setitem__(self, key, value):
        if self._rs_dict is None:
            self._rs_dict = {}
        self._rs_dict[key] = value

    def __reduce_ex__(self, protocol):
        state = None if self._rs_state is _MISSING else self._rs_state
        items = iter(self._rs_items) if self._rs_items is not None else None
        ditems = iter(self._rs_dict.items()) if self._rs_dict is not None else None
        cls = type(self)
        if self._rs_called:
            return (cls, tuple(self._rs_args), state, items, ditems)
        if self._rs_kwargs:
            return (copyreg.__newobj_ex__, (cls, tuple(self._rs_args), self._rs_kwargs), state, items, ditems)
        return (copyreg.__newobj__, (cls,) + tuple(self._rs_args), state, items, ditems)

    def __repr__(self):
        return "<%s.%s stub>" % (self._rs_module, self._rs_name)


_registry: dict = {}


def stub_class(module: str, name: str) -> type:
    """Return the (cached) stub class standing in for ``module.name``."""
    key = (module, name)
    cls = _registry.get(key)
    if cls is None:
        cls = type(
            name.rpartition(".")[2] or name,
            (Stub,),
            {"__module__": module, "__qualname__": name, "_rs_module": module, "_rs_name": name},
        )
        _registry[key] = cls
    return cls


_SAFE_BUILTINS = {
    "set": set, "frozenset": frozenset, "list": list, "dict": dict, "tuple": tuple,
    "object": object, "int": int, "float": float, "complex": complex, "bool": bool,
    "str": str, "bytes": bytes, "bytearray": bytearray, "slice": slice, "range": range,
}

SAFE_GLOBALS = {}
for _mod in ("builtins", "__builtin__"):
    for _name, _value in _SAFE_BUILTINS.items():
        SAFE_GLOBALS[(_mod, _name)] = _value
SAFE_GLOBALS.update({
    ("__builtin__", "unicode"): str,
    ("__builtin__", "long"): int,
    ("__builtin__", "xrange"): range,
    ("_codecs", "encode"): codecs.encode,
    ("collections", "OrderedDict"): collections.OrderedDict,
    ("collections", "defaultdict"): collections.defaultdict,
    ("collections", "deque"): collections.deque,
    ("collections", "Counter"): collections.Counter,
    ("datetime", "datetime"): datetime.datetime,
    ("datetime", "date"): datetime.date,
    ("datetime", "time"): datetime.time,
    ("datetime", "timedelta"): datetime.timedelta,
    ("datetime", "timezone"): datetime.timezone,
})


class StubUnpickler(pickle.Unpickler):
    def __init__(self, file, *, allow_stubs=True, **kwargs):
        super().__init__(file, **kwargs)
        self.allow_stubs = allow_stubs

    def find_class(self, module, name):
        safe = SAFE_GLOBALS.get((module, name))
        if safe is not None:
            return safe
        if not self.allow_stubs:
            raise pickle.UnpicklingError("unexpected global %s.%s" % (module, name))
        return stub_class(module, name)

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("persistent ids are not supported")


def loads(data: bytes, *, allow_stubs: bool = True):
    """Unpickle without executing anything.

    ``encoding="bytes"`` keeps Python 2 ``str`` objects as ``bytes`` so they
    are written back byte-for-byte identical.
    """
    return StubUnpickler(io.BytesIO(data), allow_stubs=allow_stubs, encoding="bytes").load()


class StubPickler(pickle._Pickler):
    """Pure-Python pickler that writes stub classes under their original names."""

    def save_global(self, obj, name=None):
        if isinstance(obj, type) and issubclass(obj, Stub) and obj is not Stub:
            if self.proto >= 4:
                self.save(obj._rs_module)
                self.save(obj._rs_name)
                self.write(pickle.STACK_GLOBAL)
            else:
                self.write(pickle.GLOBAL + obj._rs_module.encode("utf-8") + b"\n"
                           + obj._rs_name.encode("utf-8") + b"\n")
            self.memoize(obj)
            return
        super().save_global(obj, name)


def dumps(obj, protocol: int = 2) -> bytes:
    """Pickle ``obj`` (protocol 2 by default, as Ren'Py does)."""
    buf = io.BytesIO()
    StubPickler(buf, protocol, fix_imports=True).dump(obj)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------

def is_stub(value) -> bool:
    return isinstance(value, Stub)


def class_path(value) -> str:
    if isinstance(value, Stub):
        return "%s.%s" % (value._rs_module, value._rs_name)
    if isinstance(value, type) and issubclass(value, Stub):
        return "%s.%s" % (value._rs_module, value._rs_name)
    t = type(value)
    return "%s.%s" % (t.__module__, t.__qualname__)


def short_name(value) -> str:
    """Last component of the class name (``RevertableList``, ``Say`` …)."""
    if isinstance(value, Stub):
        return value._rs_name.rpartition(".")[2]
    if isinstance(value, type) and issubclass(value, Stub):
        return value._rs_name.rpartition(".")[2]
    return type(value).__name__


def state(value):
    return None if value._rs_state is _MISSING else value._rs_state


def args(value) -> list:
    return value._rs_args


def items(value):
    return value._rs_items


def dict_items(value):
    return value._rs_dict


def _key(k):
    return k.decode("utf-8", "replace") if isinstance(k, bytes) else k


def attrs(value) -> dict:
    """Merged, read-only view of a stub's attributes (dict / slots state)."""
    out = {}
    st = state(value)
    if isinstance(st, dict):
        parts = [st]
    elif isinstance(st, tuple) and all(p is None or isinstance(p, dict) for p in st):
        parts = st
    else:
        parts = ()
    for part in parts:
        if part:
            for k, v in part.items():
                out[_key(k)] = v
    return out


def text(value):
    """Best-effort conversion of Ren'Py string-like values to ``str``.

    Handles ``bytes`` (Python 2 strings) and stubbed ``str`` subclasses such
    as ``PyExpr`` whose text is their first constructor argument.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1")
    if isinstance(value, Stub) and value._rs_args:
        return text(value._rs_args[0])
    return str(value)
