"""Browsing and editing unpickled Ren'Py values (used by the save editor)."""

from __future__ import annotations

import ast

from . import stubpickle as sp

SCALARS = (bool, int, float, str, bytes, type(None))


class Ref:
    """An editable slot: ``container[key]``."""

    __slots__ = ("container", "key")

    def __init__(self, container, key):
        self.container = container
        self.key = key

    def get(self):
        return self.container[self.key]

    def set(self, value):
        self.container[self.key] = value


def fmt_key(key) -> str:
    if isinstance(key, bytes):
        return sp.text(key)
    if isinstance(key, str):
        return key
    return repr(key)


def children(value) -> list:
    """``[(label, Ref or None, child_value), …]`` — Ref is None when read-only."""
    out = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.append((fmt_key(k), Ref(value, k), v))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.append(("[%d]" % i, Ref(value, i), v))
    elif isinstance(value, (tuple, set, frozenset)):
        for i, v in enumerate(value):
            out.append(("[%d]" % i, None, v))
    elif sp.is_stub(value):
        for i, v in enumerate(sp.args(value)):
            out.append(("(arg %d)" % i, Ref(sp.args(value), i), v))
        st = sp.state(value)
        if isinstance(st, dict):
            for k, v in st.items():
                out.append(("." + fmt_key(k), Ref(st, k), v))
        elif isinstance(st, tuple):
            for i, part in enumerate(st):
                if isinstance(part, dict):
                    for k, v in part.items():
                        out.append(("." + fmt_key(k), Ref(part, k), v))
                elif part is not None:
                    out.append(("(state %d)" % i, None, part))
        elif st is not None:
            out.append(("(state)", None, st))
        lst = sp.items(value)
        if lst is not None:
            for i, v in enumerate(lst):
                out.append(("[%d]" % i, Ref(lst, i), v))
        dct = sp.dict_items(value)
        if dct is not None:
            for k, v in dct.items():
                out.append((fmt_key(k), Ref(dct, k), v))
    return out


def has_children(value) -> bool:
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        return len(value) > 0
    return sp.is_stub(value)


def type_label(value) -> str:
    if sp.is_stub(value):
        return sp.short_name(value)
    return type(value).__name__


def preview(value, limit: int = 120) -> str:
    if isinstance(value, bytes):
        s = repr(sp.text(value))
    elif isinstance(value, (bool, int, float, str, type(None))):
        s = repr(value)
    elif sp.is_stub(value):
        lst, dct = sp.items(value), sp.dict_items(value)
        if lst is not None:
            s = "%d items" % len(lst)
        elif dct is not None:
            s = "%d entries" % len(dct)
        elif sp.args(value) and isinstance(sp.args(value)[0], (str, bytes)):
            s = repr(sp.text(sp.args(value)[0]))
        else:
            s = "<%s>" % sp.class_path(value)
    elif isinstance(value, (list, tuple, set, frozenset, dict)):
        s = "%d items" % len(value)
    else:
        s = repr(value)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def is_editable(value) -> bool:
    return isinstance(value, SCALARS)


def edit_text(value) -> str:
    """Text shown in the edit box for ``value``."""
    if isinstance(value, bytes):
        return sp.text(value)
    if value is None:
        return "None"
    return str(value)


def parse_value(text: str, old):
    """Parse user input as a value of the same type as ``old``.

    A leading ``=`` evaluates a Python literal instead, which also allows
    changing the type (``=[1, 2]``, ``="text"``, ``=None``).
    """
    if text.startswith("="):
        return ast.literal_eval(text[1:].strip())
    if isinstance(old, bool):
        t = text.strip().lower()
        if t in ("true", "1", "yes", "on"):
            return True
        if t in ("false", "0", "no", "off"):
            return False
        raise ValueError("expected true or false")
    if isinstance(old, int):
        return int(text.strip())
    if isinstance(old, float):
        return float(text.strip())
    if isinstance(old, str):
        return text
    if isinstance(old, bytes):
        return text.encode("utf-8")
    if old is None:
        return ast.literal_eval(text.strip()) if text.strip() else None
    raise TypeError("this value cannot be edited")
