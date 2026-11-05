"""Best-effort decompiler for compiled Ren'Py scripts (.rpyc → .rpy).

Covers the statements that make up nearly all game scripts: labels,
dialogue, menus, control flow, python blocks, define/default, image and
scene/show/hide (with ATL), transforms, styles, translations, user-defined
statements and screen language (SL2). Anything unknown is emitted as a
comment so no content is silently dropped.

The output is meant for reading and modding. It is not guaranteed to
recompile byte-identical, and line numbers are not preserved.
"""

from __future__ import annotations

import re
import struct
import zlib
from contextlib import contextmanager
from pathlib import Path

from . import stubpickle as sp
from .rpa import safe_relpath

RPYC2_HEADER = b"RENPY RPC2"


class RpycError(Exception):
    pass


def read_rpyc(raw: bytes):
    """Return ``(data, statements)`` from the bytes of a .rpyc file."""
    if raw.startswith(RPYC2_HEADER):
        slots = {}
        pos = len(RPYC2_HEADER)
        while pos + 12 <= len(raw):
            slot, start, length = struct.unpack("<III", raw[pos:pos + 12])
            if slot == 0:
                break
            slots[slot] = (start, length)
            pos += 12
        # Slot 1 holds the statements before static transforms — closest to the source.
        for slot in (1, 2):
            if slot in slots:
                start, length = slots[slot]
                return sp.loads(zlib.decompress(raw[start:start + length]))
        raise RpycError("no script data found in .rpyc")
    try:
        payload = zlib.decompress(raw)
    except zlib.error as exc:
        raise RpycError("not a .rpyc file, or it is obfuscated") from exc
    return sp.loads(payload)


def decompile(raw: bytes, source_name: str = "") -> str:
    _, stmts = read_rpyc(raw)
    return Decompiler().decompile(stmts, source_name)


def output_relpath(display_name: str):
    """``archive.rpa:dir/x.rpyc`` or ``dir/x.rpyc`` → ``dir/x.rpy``."""
    name = display_name.split(":", 1)[1] if ".rpa:" in display_name else display_name
    rel = safe_relpath(name)
    return rel.with_suffix(".rpy")


def decompile_many(sources, out_dir, overwrite=False, progress=None, cancel=None):
    """Decompile ``[(display_name, read_bytes)]`` into ``out_dir``.

    Returns ``(written, skipped, errors)`` where errors is ``[(name, message)]``.
    """
    out_dir = Path(out_dir)
    written = skipped = 0
    errors = []
    total = len(sources)
    for i, (name, read) in enumerate(sources):
        if cancel is not None and cancel.is_set():
            break
        if progress:
            progress(i, total, name)
        target = out_dir / output_relpath(name)
        if target.exists() and not overwrite:
            skipped += 1
            continue
        try:
            text = decompile(read(), name)
        except Exception as exc:
            errors.append((name, str(exc)))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, "utf-8")
        written += 1
    if progress:
        progress(total, total, "")
    return written, skipped, errors


def iter_nodes(stmts):
    """Yield every statement node, recursing into blocks."""
    stack = list(stmts or [])[::-1]
    while stack:
        node = stack.pop()
        if not sp.is_stub(node):
            continue
        yield node
        a = sp.attrs(node)
        blocks = []
        if isinstance(a.get("block"), list):
            blocks.append(a["block"])
        for entry in a.get("entries") or []:
            if isinstance(entry, (tuple, list)) and len(entry) == 2 and isinstance(entry[1], list):
                blocks.append(entry[1])
        for item in a.get("items") or []:
            if isinstance(item, (tuple, list)) and len(item) == 3 and isinstance(item[2], list):
                blocks.append(item[2])
        for block in reversed(blocks):
            stack.extend(reversed(block))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

T = sp.text


def kind(node) -> str:
    return sp.short_name(node) if sp.is_stub(node) else type(node).__name__


def get(node, name, default=None):
    if not sp.is_stub(node):
        return default
    v = sp.attrs(node).get(name, default)
    return default if v is None and default is not None else v


def pycode_source(code) -> str:
    """Source text of a ``PyCode`` (or plain string / PyExpr)."""
    if code is None:
        return ""
    if sp.is_stub(code) and sp.short_name(code) == "PyCode":
        st = sp.state(code)
        if isinstance(st, tuple) and len(st) > 1 and not isinstance(st[1], dict):
            return T(st[1]) or ""
        return T(sp.attrs(code).get("source")) or ""
    return T(code) or ""


def encode_say_string(s: str) -> str:
    s = s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    s = re.sub(r"(?<= ) ", "\\ ", s)
    return '"' + s + '"'


def fmt_args(info) -> str:
    if info is None:
        return ""
    a = sp.attrs(info)
    starred = a.get("starred_indexes") or ()
    dstarred = a.get("doublestarred_indexes") or ()
    out = []
    for i, (keyword, expr) in enumerate(a.get("arguments") or []):
        expr = T(expr)
        if i in starred:
            out.append("*" + expr)
        elif i in dstarred:
            out.append("**" + expr)
        elif keyword:
            out.append("%s=%s" % (T(keyword), expr))
        else:
            out.append(expr)
    if a.get("extrapos"):
        out.append("*" + T(a["extrapos"]))
    if a.get("extrakw"):
        out.append("**" + T(a["extrakw"]))
    return "(" + ", ".join(out) + ")"


def fmt_params(info) -> str:
    if info is None:
        return ""
    a = sp.attrs(info)
    params = a.get("parameters")
    if params is None:
        return ""
    if isinstance(params, dict):
        params = list(params.values())
    params = list(params)

    if params and isinstance(params[0], (tuple, list)):
        # Legacy layout: [(name, default)], positional names, extrapos, extrakw.
        positional = [T(p) for p in a.get("positional") or []]
        pos, kw = [], []
        for name, default in params:
            s = T(name) + ("=" + T(default) if default is not None else "")
            (pos if T(name) in positional else kw).append(s)
        out = pos
        if a.get("extrapos"):
            out.append("*" + T(a["extrapos"]))
        elif kw:
            out.append("*")
        out += kw
        if a.get("extrakw"):
            out.append("**" + T(a["extrakw"]))
        return "(" + ", ".join(out) + ")"

    out = []
    pos_only_pending = False
    need_kw_marker = True
    for p in params:
        pa = sp.attrs(p)
        name = T(pa.get("name"))
        k = pa.get("kind", 1)
        default = pa.get("default")
        if k == 0:
            pos_only_pending = True
        elif pos_only_pending:
            out.append("/")
            pos_only_pending = False
        if k == 2:
            need_kw_marker = False
            name = "*" + name
        elif k == 3 and need_kw_marker:
            out.append("*")
            need_kw_marker = False
        elif k == 4:
            name = "**" + name
        if default is not None:
            name += "=" + T(default)
        out.append(name)
    if pos_only_pending:
        out.append("/")
    return "(" + ", ".join(out) + ")"


def fmt_imspec(spec) -> str:
    if not spec:
        return ""
    spec = list(spec)
    expression = tag = zorder = None
    behind = []
    if len(spec) == 3:
        name, at_list, layer = spec
    elif len(spec) == 6:
        name, expression, tag, at_list, layer, zorder = spec
    else:
        name, expression, tag, at_list, layer, zorder, behind = spec[:7]
    parts = ["expression " + T(expression)] if expression else [" ".join(T(n) for n in name or ())]
    if tag:
        parts.append("as " + T(tag))
    if at_list:
        parts.append("at " + ", ".join(T(x) for x in at_list))
    if layer:
        parts.append("onlayer " + T(layer))
    if zorder:
        parts.append("zorder " + T(zorder))
    if behind:
        parts.append("behind " + ", ".join(T(x) for x in behind))
    return " ".join(parts)


def store_prefix(store) -> str:
    store = T(store) or "store"
    if store == "store":
        return ""
    return (store[6:] if store.startswith("store.") else store) + "."


# Screen-language keywords that cannot be derived from the default style.
SL_NAMES = {
    "_textbutton": "textbutton", "_imagebutton": "imagebutton", "_label": "label",
    "sl2add": "add", "_add": "add", "_key": "key", "keymap": "key", "_timer": "timer",
    "timer": "timer", "_imagemap": "imagemap", "_hotspot": "hotspot", "_hotbar": "hotbar",
    "sl2bar": "bar", "sl2vbar": "vbar", "sl2viewport": "viewport", "sl2vpgrid": "vpgrid",
    "_mousearea": "mousearea", "mousearea": "mousearea", "_dismiss": "dismiss",
    "dismiss": "dismiss", "onevent": "on", "_onevent": "on", "drag": "drag",
    "draggroup": "draggroup", "areapicker": "areapicker", "nearrect": "nearrect",
    "_input": "input", "input": "input", "null": "null", "_null": "null",
    "transform": "transform", "_image": "image", "grid": "grid", "side": "side",
}
SL_STYLE_NAMES = {"image_button": "imagebutton", "say_label": "label"}


class Decompiler:
    def __init__(self, indent: str = "    "):
        self.indent = indent
        self.level = 0
        self.lines = []
        self.with_suffix = None
        self.line_prefix = ""
        self.menu_label = None
        self.menu_caption = None

    # -- output ----------------------------------------------------------

    def line(self, text: str = ""):
        if self.with_suffix:
            if text.endswith(":"):
                text = text[:-1] + " with " + self.with_suffix + ":"
            else:
                text = text + " with " + self.with_suffix
            self.with_suffix = None
        if self.line_prefix:
            text = self.line_prefix + text
            self.line_prefix = ""
        self.lines.append((self.indent * self.level + text) if text else "")

    @contextmanager
    def block(self):
        self.level += 1
        try:
            yield
        finally:
            self.level -= 1

    def body(self, nodes):
        with self.block():
            if nodes:
                self.nodes(nodes)
            else:
                self.line("pass")

    def code_lines(self, source: str):
        with self.block():
            lines = source.splitlines() or ["pass"]
            for l in lines:
                self.lines.append((self.indent * self.level + l) if l.strip() else "")

    # -- driver ----------------------------------------------------------

    def decompile(self, stmts, source_name: str = "") -> str:
        header = "# Decompiled by RenPy Suite (best-effort)"
        if source_name:
            header += " from " + source_name
        self.lines = [header, ""]
        self.nodes(stmts or [])
        return "\n".join(self.lines).rstrip() + "\n"

    def nodes(self, nodes):
        i = 0
        while i < len(nodes):
            i = self.node(nodes, i)

    def node(self, nodes, i) -> int:
        n = nodes[i]
        handler = getattr(self, "n_" + kind(n), None)
        if handler is None:
            self.line("# [renpy-suite] unsupported statement: %s" % sp.class_path(n))
            return i + 1
        try:
            r = handler(n, nodes, i)
        except Exception as exc:  # keep going; one odd node must not lose the file
            self.line("# [renpy-suite] could not decompile %s: %s" % (kind(n), exc))
            return i + 1
        return i + 1 if r is None else r

    # -- statements ------------------------------------------------------

    def n_Label(self, n, nodes, i):
        name = T(get(n, "name"))
        block = get(n, "block") or []
        if not block:
            j = i + 1
            if j < len(nodes) and kind(nodes[j]) == "Say" and not get(nodes[j], "interact", True):
                j += 1
            if j < len(nodes) and kind(nodes[j]) == "Menu":
                self.menu_label = name
                return
        head = "label %s%s%s:" % (name, fmt_params(get(n, "parameters")), " hide" if get(n, "hide") else "")
        self.line(head)
        if block:
            with self.block():
                self.nodes(block)

    def say_code(self, n, for_menu=False) -> str:
        rv = []
        who = get(n, "who")
        if who:
            rv.append(T(who))
        if get(n, "attributes"):
            rv.extend(T(a) for a in get(n, "attributes"))
        if get(n, "temporary_attributes"):
            rv.append("@")
            rv.extend(T(a) for a in get(n, "temporary_attributes"))
        rv.append(encode_say_string(T(get(n, "what")) or ""))
        if not get(n, "interact", True) and not for_menu:
            rv.append("nointeract")
        if get(n, "explicit_identifier") and get(n, "identifier"):
            rv.append("id " + T(get(n, "identifier")))
        if get(n, "arguments") is not None:
            rv.append(fmt_args(get(n, "arguments")))
        if get(n, "with_"):
            rv.append("with " + T(get(n, "with_")))
        return " ".join(rv)

    def n_Say(self, n, nodes, i):
        if not get(n, "interact", True) and i + 1 < len(nodes) and kind(nodes[i + 1]) == "Menu":
            self.menu_caption = n
            return
        self.line(self.say_code(n))

    def n_TranslateSay(self, n, nodes, i):
        language = get(n, "language")
        if language is None:
            return self.n_Say(n, nodes, i)
        self.line("translate %s %s:" % (T(language), T(get(n, "identifier"))))
        with self.block():
            self.line(self.say_code(n))

    def n_Menu(self, n, nodes, i):
        head = "menu"
        if self.menu_label:
            head += " " + self.menu_label
        if get(n, "arguments") is not None:
            head += fmt_args(get(n, "arguments"))
        self.line(head + ":")
        caption, self.menu_label, self.menu_caption = self.menu_caption, None, None
        item_args = get(n, "item_arguments") or []
        with self.block():
            if get(n, "set"):
                self.line("set " + T(get(n, "set")))
            if caption is not None:
                self.line(self.say_code(caption, for_menu=True))
            for idx, item in enumerate(get(n, "items") or []):
                label, condition, block = item
                text = encode_say_string(T(label) or "")
                if block is None:
                    self.line(text)
                    continue
                if idx < len(item_args) and item_args[idx] is not None:
                    text += " " + fmt_args(item_args[idx])
                cond = T(condition)
                if cond and cond != "True":
                    text += " if " + cond
                self.line(text + ":")
                self.body(block)

    def n_Jump(self, n, nodes, i):
        if get(n, "expression"):
            self.line("jump expression " + T(get(n, "target")))
        else:
            self.line("jump " + T(get(n, "target")))

    def n_Call(self, n, nodes, i):
        label = T(get(n, "label"))
        args = get(n, "arguments")
        if get(n, "expression"):
            s = "call expression " + label
            if args is not None:
                s += " pass " + fmt_args(args)
        else:
            s = "call " + label + (fmt_args(args) if args is not None else "")
        nxt = nodes[i + 1] if i + 1 < len(nodes) else None
        if nxt is not None and kind(nxt) == "Label" and not get(nxt, "block"):
            self.line(s + " from " + T(get(nxt, "name")))
            return i + 2
        self.line(s)
        if nxt is not None and kind(nxt) == "Pass":
            return i + 2

    def n_Return(self, n, nodes, i):
        expr = T(get(n, "expression"))
        self.line("return " + expr if expr else "return")

    def n_Pass(self, n, nodes, i):
        self.line("pass")

    def n_While(self, n, nodes, i):
        self.line("while %s:" % T(get(n, "condition")))
        self.body(get(n, "block") or [])

    def n_If(self, n, nodes, i):
        entries = get(n, "entries") or []
        for idx, (cond, block) in enumerate(entries):
            cond = T(cond)
            if idx == 0:
                self.line("if %s:" % cond)
            elif cond == "True" and idx == len(entries) - 1:
                self.line("else:")
            else:
                self.line("elif %s:" % cond)
            self.body(block or [])

    def python_header(self, n, early=False) -> str:
        parts = ["python"]
        if early:
            parts.append("early")
        if get(n, "hide"):
            parts.append("hide")
        prefix = store_prefix(get(n, "store"))
        if prefix:
            parts.append("in " + prefix[:-1])
        return " ".join(parts)

    def n_Python(self, n, nodes, i):
        source = pycode_source(get(n, "code"))
        header = self.python_header(n)
        if header == "python" and "\n" not in source.strip():
            self.line("$ " + source.strip())
            return
        self.line(header + ":")
        self.code_lines(source)

    def n_EarlyPython(self, n, nodes, i):
        self.line(self.python_header(n, early=True) + ":")
        self.code_lines(pycode_source(get(n, "code")))

    def n_Init(self, n, nodes, i):
        block = get(n, "block") or []
        prio = get(n, "priority", 0) or 0
        if len(block) == 1:
            child = block[0]
            k = kind(child)
            if k == "Python":
                head = "init %d " % prio if prio else "init "
                self.line(head + self.python_header(child) + ":")
                self.code_lines(pycode_source(get(child, "code")))
                return
            if k == "Define" and prio:
                self.n_Define(child, block, 0, prio)
                return
            if k in ("Define", "Image", "Transform", "Screen", "Style", "Testcase",
                     "TranslateString", "TranslateBlock", "TranslateEarlyBlock",
                     "TranslatePython", "UserStatement") or (k == "Default" and not prio):
                self.nodes(block)
                return
        self.line("init %d:" % prio if prio else "init:")
        self.body(block)

    def n_Define(self, n, nodes, i, prio=0):
        index = get(n, "index")
        idx = "[%s]" % pycode_source(index) if index is not None else ""
        op = T(get(n, "operator")) or "="
        self.line("define %s%s%s%s %s %s" % (
            "%d " % prio if prio else "", store_prefix(get(n, "store")), T(get(n, "varname")),
            idx, op, pycode_source(get(n, "code"))))

    def n_Default(self, n, nodes, i):
        self.line("default %s%s = %s" % (store_prefix(get(n, "store")), T(get(n, "varname")),
                                         pycode_source(get(n, "code"))))

    def n_Image(self, n, nodes, i):
        name = " ".join(T(x) for x in get(n, "imgname") or ())
        if get(n, "code") is not None:
            self.line("image %s = %s" % (name, pycode_source(get(n, "code"))))
        else:
            self.line("image %s:" % name)
            self.atl_body(get(n, "atl"))

    def n_Transform(self, n, nodes, i):
        self.line("transform %s%s%s:" % (store_prefix(get(n, "store")), T(get(n, "varname")),
                                        fmt_params(get(n, "parameters"))))
        self.atl_body(get(n, "atl"))

    def _show_like(self, keyword, n, spec_text):
        s = (keyword + " " + spec_text).rstrip()
        if get(n, "atl") is not None:
            self.line(s + ":")
            self.atl_body(get(n, "atl"))
        else:
            self.line(s)

    def n_Show(self, n, nodes, i):
        self._show_like("show", n, fmt_imspec(get(n, "imspec")))

    def n_Scene(self, n, nodes, i):
        spec = get(n, "imspec")
        if spec:
            text = fmt_imspec(spec)
        else:
            layer = T(get(n, "layer"))
            text = "onlayer " + layer if layer and layer != "master" else ""
        self._show_like("scene", n, text)

    def n_Hide(self, n, nodes, i):
        self.line("hide " + fmt_imspec(get(n, "imspec")))

    def n_ShowLayer(self, n, nodes, i):
        s = "layer " + (T(get(n, "layer")) or "master")
        if get(n, "at_list"):
            s += " at " + ", ".join(T(x) for x in get(n, "at_list"))
        self._show_like("show", n, s)

    def n_Camera(self, n, nodes, i):
        layer = T(get(n, "layer")) or "master"
        s = "" if layer == "master" else layer
        if get(n, "at_list"):
            s += " at " + ", ".join(T(x) for x in get(n, "at_list"))
        self._show_like("camera", n, s.strip())

    def n_With(self, n, nodes, i):
        expr = T(get(n, "expr"))
        paired = T(get(n, "paired"))
        if expr == "None" and paired and i + 2 < len(nodes):
            closing = nodes[i + 2]
            if kind(closing) == "With" and T(get(closing, "expr")) == paired:
                self.with_suffix = paired
                self.node(nodes, i + 1)
                self.with_suffix = None
                return i + 3
        self.line("with " + expr)

    def n_UserStatement(self, n, nodes, i):
        self.line(T(get(n, "line")) or "")
        block = get(n, "block")
        if block:
            self.raw_block(block)

    def raw_block(self, block):
        with self.block():
            for entry in block:
                if isinstance(entry, (tuple, list)) and len(entry) >= 4:
                    self.line(T(entry[2]))
                    if entry[3]:
                        self.raw_block(entry[3])

    def n_PostUserStatement(self, n, nodes, i):
        pass

    def n_EndTranslate(self, n, nodes, i):
        pass

    def n_Translate(self, n, nodes, i):
        language = get(n, "language")
        block = get(n, "block") or []
        if language is None:
            self.nodes(block)
            return
        self.line("translate %s %s:" % (T(language), T(get(n, "identifier"))))
        self.body(block)

    def n_TranslateString(self, n, nodes, i):
        language = T(get(n, "language")) or "None"
        self.line("translate %s strings:" % language)
        j = i
        with self.block():
            while j < len(nodes) and kind(nodes[j]) == "TranslateString" \
                    and (T(get(nodes[j], "language")) or "None") == language:
                self.line("old " + encode_say_string(T(get(nodes[j], "old")) or ""))
                self.line("new " + encode_say_string(T(get(nodes[j], "new")) or ""))
                self.line()
                j += 1
        if self.lines and not self.lines[-1]:
            self.lines.pop()
        return j

    def n_TranslatePython(self, n, nodes, i):
        self.line("translate %s python:" % T(get(n, "language")))
        self.code_lines(pycode_source(get(n, "code")))

    def n_TranslateBlock(self, n, nodes, i):
        language = T(get(n, "language")) or "None"
        for child in get(n, "block") or []:
            self.line_prefix = "translate %s " % language
            self.node([child], 0)

    n_TranslateEarlyBlock = n_TranslateBlock

    def n_Style(self, n, nodes, i):
        head = "style " + T(get(n, "style_name"))
        if get(n, "parent"):
            head += " is " + T(get(n, "parent"))
        if get(n, "variant"):
            head += " variant " + T(get(n, "variant"))
        body = []
        if get(n, "clear"):
            body.append("clear")
        if get(n, "take"):
            body.append("take " + T(get(n, "take")))
        for d in get(n, "delattr") or ():
            body.append("del " + T(d))
        for k, v in (get(n, "properties") or {}).items():
            body.append("%s %s" % (T(k), T(v)))
        if not body:
            self.line(head)
            return
        self.line(head + ":")
        with self.block():
            for b in body:
                self.line(b)

    def n_RPY(self, n, nodes, i):
        self.line("rpy " + " ".join(T(x) for x in get(n, "rest") or ()))

    def n_Testcase(self, n, nodes, i):
        self.line("testcase %s:" % T(get(n, "name")))
        with self.block():
            self.line("# [renpy-suite] testcase bodies are not decompiled")
            self.line("pass")

    def n_Screen(self, n, nodes, i):
        screen = get(n, "screen")
        if kind(screen) == "SLScreen":
            self.sl_screen(screen)
        else:
            name = T(get(screen, "name")) or "?"
            self.line("# [renpy-suite] screen %s uses legacy screen language (not supported)" % name)

    # -- ATL ---------------------------------------------------------------

    def atl_body(self, atl):
        with self.block():
            stmts = get(atl, "statements") if atl is not None else None
            if get(atl, "animation"):
                self.line("animation")
            if stmts:
                for s in stmts:
                    self.atl_stmt(s)
            elif not get(atl, "animation"):
                self.line("pass")

    def atl_stmt(self, s):
        k = kind(s)
        if k == "RawBlock":
            self.line("block:")
            self.atl_body(s)
        elif k == "RawMultipurpose":
            self.line(self.atl_multipurpose(s))
        elif k == "RawRepeat":
            r = T(get(s, "repeats"))
            self.line("repeat " + r if r else "repeat")
        elif k == "RawParallel":
            for b in get(s, "blocks") or []:
                self.line("parallel:")
                self.atl_body(b)
        elif k == "RawChoice":
            for chance, b in get(s, "choices") or []:
                chance = T(chance)
                self.line("choice %s:" % chance if chance and chance != "1.0" else "choice:")
                self.atl_body(b)
        elif k == "RawOn":
            for name, b in (get(s, "handlers") or {}).items():
                self.line("on %s:" % T(name))
                self.atl_body(b)
        elif k == "RawTime":
            self.line("time " + T(get(s, "time")))
        elif k == "RawFunction":
            self.line("function " + T(get(s, "expr")))
        elif k == "RawEvent":
            self.line("event " + T(get(s, "name")))
        elif k == "RawContainsExpr":
            self.line("contains " + T(get(s, "expression")))
        elif k == "RawChild":
            for child in get(s, "children") or []:
                self.line("contains:")
                self.atl_body(child)
        else:
            self.line("# [renpy-suite] unsupported ATL: %s" % sp.class_path(s))

    def atl_multipurpose(self, s) -> str:
        parts = []
        warp_function = T(get(s, "warp_function"))
        warper = T(get(s, "warper"))
        duration = T(get(s, "duration")) or "0"
        if warp_function:
            parts.append("warp %s %s" % (warp_function, duration))
        elif warper:
            parts.append("%s %s" % (warper, duration))
        elif duration != "0":
            parts.append("pause " + duration)
        for expr, with_ in get(s, "expressions") or []:
            parts.append(T(expr) + (" with " + T(with_) if with_ else ""))
        for name, expr in get(s, "properties") or []:
            parts.append("%s %s" % (T(name), T(expr)))
        for name, exprs in get(s, "splines") or []:
            exprs = [T(e) for e in exprs]
            spline = "%s %s" % (T(name), exprs[-1])
            for knot in exprs[:-1]:
                spline += " knot " + knot
            parts.append(spline)
        if get(s, "revolution"):
            parts.append(T(get(s, "revolution")))
        circles = T(get(s, "circles"))
        if circles and circles != "0":
            parts.append("circles " + circles)
        return " ".join(parts) or "pass"

    # -- screen language ---------------------------------------------------

    def sl_screen(self, s):
        self.line("screen %s%s:" % (T(get(s, "name")), fmt_params(get(s, "parameters"))))
        with self.block():
            defaults = {"modal": "False", "zorder": "0", "variant": "None", "predict": "None",
                        "sensitive": "True", "roll_forward": "None", "layer": "'screens'"}
            if get(s, "tag"):
                self.line("tag " + T(get(s, "tag")))
            for prop, default in defaults.items():
                v = T(get(s, prop))
                if v is not None and v != default:
                    self.line("%s %s" % (prop, v))
            for k, v in get(s, "keyword") or []:
                self.line("%s %s" % (T(k), T(v)))
            children = get(s, "children") or []
            for c in children:
                self.sl_node(c)
            if not children:
                self.line("pass")

    def sl_name(self, n) -> str:
        disp = get(n, "displayable")
        style = T(get(n, "style"))
        dn = (sp.short_name(disp) if sp.is_stub(disp) or isinstance(disp, type) else "").lower()
        if dn in SL_NAMES:
            return SL_NAMES[dn]
        if style:
            return SL_STYLE_NAMES.get(style, style)
        return dn.lstrip("_") or "fixed"

    def sl_block_contents(self, n):
        for k, v in get(n, "keyword") or []:
            self.line("%s %s" % (T(k), T(v)))
        for c in get(n, "children") or []:
            self.sl_node(c)

    def sl_has_contents(self, n) -> bool:
        return bool(get(n, "keyword") or get(n, "children"))

    def sl_node(self, n):
        k = kind(n)
        if k == "SLDisplayable":
            head = self.sl_name(n)
            positional = [T(p) for p in get(n, "positional") or []]
            if positional:
                head += " " + " ".join(positional)
            if get(n, "variable"):
                head += " as " + T(get(n, "variable"))
            if self.sl_has_contents(n):
                self.line(head + ":")
                with self.block():
                    self.sl_block_contents(n)
            else:
                self.line(head)
        elif k in ("SLIf", "SLShowIf"):
            word = "if" if k == "SLIf" else "showif"
            entries = get(n, "entries") or []
            for idx, (cond, block) in enumerate(entries):
                cond = T(cond)
                if idx == 0:
                    self.line("%s %s:" % (word, cond))
                elif cond in (None, "True") and idx == len(entries) - 1:
                    self.line("else:")
                else:
                    self.line("elif %s:" % cond)
                with self.block():
                    if block is not None and self.sl_has_contents(block):
                        self.sl_block_contents(block)
                    else:
                        self.line("pass")
        elif k == "SLFor":
            self.line("for %s in %s:" % (T(get(n, "variable")), T(get(n, "expression"))))
            with self.block():
                if self.sl_has_contents(n):
                    self.sl_block_contents(n)
                else:
                    self.line("pass")
        elif k == "SLPython":
            source = pycode_source(get(n, "code"))
            if "\n" in source.strip():
                self.line("python:")
                self.code_lines(source)
            else:
                self.line("$ " + source.strip())
        elif k == "SLPass":
            self.line("pass")
        elif k == "SLBreak":
            self.line("break")
        elif k == "SLContinue":
            self.line("continue")
        elif k == "SLDefault":
            self.line("default %s = %s" % (T(get(n, "variable")), T(get(n, "expression"))))
        elif k == "SLUse":
            target = T(get(n, "target"))
            args = get(n, "args")
            head = "use " + target + (fmt_args(args) if args is not None else "")
            if get(n, "id"):
                head += " id " + T(get(n, "id"))
            block = get(n, "block")
            if block is not None and self.sl_has_contents(block):
                self.line(head + ":")
                with self.block():
                    self.sl_block_contents(block)
            else:
                self.line(head)
        elif k == "SLTransclude":
            self.line("transclude")
        elif k == "SLBlock":
            self.sl_block_contents(n)
        else:
            self.line("# [renpy-suite] unsupported screen statement: %s" % sp.class_path(n))
