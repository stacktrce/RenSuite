"""Minimal look-alikes of Ren'Py classes, used to build realistic test pickles.

They are only registered in ``sys.modules`` inside :func:`fake_renpy`, so the
code under test never sees them — exactly like a machine without Ren'Py.
"""

import contextlib
import copyreg
import sys
import types


def _slots_reduce(self, protocol):
    # Mimics renpy.cslots: state is (None, {slot: value}) with defaults omitted.
    return (copyreg.__newobj__, (type(self),), (None, dict(self.__dict__)))


def _build():
    mods = {}

    def module(name):
        m = types.ModuleType(name)
        mods[name] = m
        return m

    module("renpy")
    rev = module("renpy.revertable")
    ast = module("renpy.ast")
    astsupport = module("renpy.astsupport")
    parameter = module("renpy.parameter")
    atl = module("renpy.atl")
    module("renpy.sl2")
    slast = module("renpy.sl2.slast")
    rollback = module("renpy.rollback")
    persistent = module("renpy.persistent")

    def cls(mod, name, bases=(object,), body=None):
        c = type(name, bases, dict(body or {}))
        c.__module__ = mod.__name__
        c.__qualname__ = name
        setattr(mod, name, c)
        return c

    cls(rev, "RevertableList", (list,))
    cls(rev, "RevertableDict", (dict,))
    cls(rev, "RevertableObject")
    cls(rollback, "RollbackLog")
    cls(persistent, "Persistent", body={
        "__getstate__": lambda self: self.__dict__,
        "__setstate__": lambda self, d: self.__dict__.update(d),
    })

    class PyExpr(str):
        def __new__(cls, s, filename="game.rpy", linenumber=1, py=3):
            self = str.__new__(cls, s)
            self.filename, self.linenumber, self.py = filename, linenumber, py
            return self

        def __reduce__(self):
            return (PyExpr, (str(self), self.filename, self.linenumber, self.py))

    PyExpr.__module__ = "renpy.astsupport"
    PyExpr.__qualname__ = "PyExpr"
    astsupport.PyExpr = PyExpr

    class PyCode(object):
        def __init__(self, source):
            self.source = source

        def __getstate__(self):
            return (1, self.source, ("game.rpy", 1), "exec", 3, 0, 0)

        def __setstate__(self, state):
            self.source = state[1]

    PyCode.__module__ = "renpy.ast"
    PyCode.__qualname__ = "PyCode"
    ast.PyCode = PyCode

    def node_class(mod, name):
        def init(self, **kw):
            self.__dict__.update(kw)
        return cls(mod, name, body={"__init__": init, "__reduce_ex__": _slots_reduce})

    for name in ("Label", "Say", "Menu", "If", "While", "Jump", "Call", "Return", "Pass",
                 "Python", "Init", "Define", "Default", "Show", "Scene", "Hide", "With",
                 "Image", "Translate", "EndTranslate", "UserStatement", "Screen"):
        node_class(ast, name)
    for name in ("ArgumentInfo", "Signature", "Parameter"):
        node_class(parameter, name)
    for name in ("RawBlock", "RawMultipurpose", "RawRepeat"):
        node_class(atl, name)
    for name in ("SLScreen", "SLDisplayable", "SLIf", "SLBlock"):
        node_class(slast, name)

    class Text(object):
        pass

    Text.__module__ = "renpy.text.text"
    Text.__qualname__ = "Text"
    module("renpy.text")
    tm = module("renpy.text.text")
    tm.Text = Text
    return mods


@contextlib.contextmanager
def fake_renpy():
    mods = _build()
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        yield types.SimpleNamespace(**{k.split(".")[-1]: v for k, v in mods.items()})
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
