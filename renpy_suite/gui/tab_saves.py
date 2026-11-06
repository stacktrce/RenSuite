"""Save editor tab: find saves, browse and edit variables, write back safely."""

from __future__ import annotations

import base64
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import saves, savetoken, values
from ..i18n import t
from ..live import LiveDoc, LiveGame
from .widgets import scrolled
from .theme import c

DUMMY = "__dummy__"


class SavesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.game = None
        self.entries = []
        self.doc = None  # SaveFile or PersistentFile
        self.dirty = False
        self.nodes = {}  # tree iid -> (Ref | None, value)
        self.photo = None

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        # -- left: save list ------------------------------------------------
        left = ttk.LabelFrame(panes, text=t("saves_frame"), padding=6)
        brow = ttk.Frame(left)
        brow.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(brow, text=t("open_latest"), command=self.open_latest).pack(side=tk.LEFT)
        ttk.Button(brow, text=t("refresh"), command=self.refresh).pack(side=tk.LEFT, padx=6)
        frame, self.save_tree = scrolled(left, ttk.Treeview, columns=("modified", "folder"),
                                         selectmode="browse", height=6)
        self.save_tree.heading("#0", text=t("col_slot"))
        self.save_tree.heading("modified", text=t("col_modified"))
        self.save_tree.heading("folder", text=t("col_folder"))
        self.save_tree.column("#0", width=110)
        self.save_tree.column("modified", width=130, stretch=False)
        self.save_tree.column("folder", width=160)
        frame.pack(fill=tk.BOTH, expand=True)
        self.save_tree.bind("<<TreeviewSelect>>", lambda e: self.open_selected())
        self.scan_label = ttk.Label(left, text="", foreground=c("gray"), wraplength=380)
        self.scan_label.pack(anchor="w", pady=(6, 0))
        orow = ttk.Frame(left)
        orow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(orow, text=t("open_save_file"), command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(orow, text=t("open_persistent"), command=self.open_persistent).pack(side=tk.LEFT, padx=6)
        ttk.Button(orow, text=t("open_live"), command=self.open_live).pack(side=tk.LEFT)
        panes.add(left, weight=2)

        # -- right: variables ----------------------------------------------
        right = ttk.LabelFrame(panes, text=t("variables_frame"), padding=6)
        head = ttk.Frame(right)
        head.pack(fill=tk.X)
        self.shot = ttk.Label(head, text="")
        self.shot.pack(side=tk.LEFT, padx=(0, 10))
        self.header = ttk.Label(head, text=t("nothing_open"), font=("", 10, "bold"), wraplength=520,
                                justify=tk.LEFT)
        self.header.pack(side=tk.LEFT, fill=tk.X, expand=True, anchor="w")

        frow = ttk.Frame(right)
        frow.pack(fill=tk.X, pady=6)
        ttk.Label(frow, text=t("filter")).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.fill_variables())
        ttk.Entry(frow, textvariable=self.filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.hide_internal = tk.BooleanVar(value=True)
        ttk.Checkbutton(frow, text=t("hide_internal"), variable=self.hide_internal,
                        command=self.fill_variables).pack(side=tk.LEFT)

        frame, self.var_tree = scrolled(right, ttk.Treeview, columns=("type", "value"), selectmode="browse",
                                        height=6)
        self.var_tree.heading("#0", text=t("col_variable"))
        self.var_tree.heading("type", text=t("col_type"))
        self.var_tree.heading("value", text=t("col_value"))
        self.var_tree.column("#0", width=260)
        self.var_tree.column("type", width=110, stretch=False)
        self.var_tree.column("value", width=320)
        frame.pack(fill=tk.BOTH, expand=True)
        self.var_tree.bind("<<TreeviewOpen>>", self.on_open)
        self.var_tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.var_tree.bind("<Return>", lambda e: self.edit_selected())

        arow = ttk.Frame(right)
        arow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(arow, text=t("edit_value"), command=self.edit_selected).pack(side=tk.LEFT)
        ttk.Button(arow, text=t("freeze_toggle"), command=self.toggle_freeze).pack(side=tk.LEFT, padx=6)
        ttk.Button(arow, text=t("revert"), command=self.revert).pack(side=tk.RIGHT)
        ttk.Button(arow, text=t("save_changes"), command=self.write).pack(side=tk.RIGHT, padx=6)
        ttk.Label(right, text=t("close_game_hint"), foreground=c("gray")).pack(anchor="w", pady=(6, 0))
        panes.add(right, weight=3)

        self.refresh()

    # -- save list --------------------------------------------------------

    def can_close(self):
        return not self.dirty or messagebox.askyesno(t("app_title"), t("unsaved_changes"))

    def set_game(self, game):
        self.game = game
        self.refresh()

    def save_dirs(self):
        return saves.default_save_dirs(self.game)

    def refresh(self):
        dirs = self.save_dirs()
        self.entries = saves.list_saves(dirs)
        self.save_tree.delete(*self.save_tree.get_children())
        for i, e in enumerate(self.entries):
            self.save_tree.insert("", tk.END, iid=str(i), text=e.slot, values=(
                time.strftime("%Y-%m-%d %H:%M", time.localtime(e.mtime)), e.path.parent.name))
        if self.game is not None and self.game.save_dirs():
            text = t("scanning_game", name=self.game.name)
        else:
            text = t("scanning_all")
        if not self.entries:
            text += "  " + t("no_saves")
        self.scan_label.config(text=text)

    def open_latest(self):
        self.refresh()
        if not self.entries:
            messagebox.showinfo(t("app_title"), t("no_saves"))
            return
        self.save_tree.selection_set("0")
        self.save_tree.see("0")

    def open_selected(self):
        sel = self.save_tree.selection()
        if sel:
            self.load(self.entries[int(sel[0])].path, persistent=False)

    def open_file(self):
        f = filedialog.askopenfilename(title=t("pick_save_file"),
                                       filetypes=[(t("filetype_save"), "*.save"), ("persistent", "persistent"),
                                                  (t("filetype_all"), "*.*")])
        if f:
            self.load(Path(f), persistent=Path(f).name == "persistent")

    def open_persistent(self):
        found = saves.find_persistent(self.save_dirs())
        if not found:
            messagebox.showinfo(t("app_title"), t("no_persistent"))
            return
        self.load(found[0], persistent=True)

    def open_live(self):
        if self.game is None:
            messagebox.showinfo(t("app_title"), t("need_game"))
            return
        game_live = LiveGame(self.game.root)
        if not game_live.is_running():
            messagebox.showinfo(t("app_title"), t("live_not_running"))
            return
        if not self.can_close():
            return
        try:
            self.doc = LiveDoc(game_live)
        except ValueError as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        self.dirty = False
        self.save_tree.selection_remove(self.save_tree.selection())
        self.show_header()
        self.fill_variables()

    # -- loading ----------------------------------------------------------

    def load(self, path, persistent):
        if self.doc is not None and Path(self.doc.path) == Path(path):
            return
        if not self.can_close():
            return
        self.app.set_status(t("loading_save", name=Path(path).name))
        cls = saves.PersistentFile if persistent else saves.SaveFile

        def done(doc):
            self.doc = doc
            self.dirty = False
            self.app.set_status("")
            self.show_header()
            self.fill_variables()

        def failed(exc):
            self.app.set_status("")
            messagebox.showerror(t("error"), "%s\n\n%s" % (path, exc))

        self.app.runner.run(lambda: cls(path), done, failed)

    def show_header(self):
        doc = self.doc
        signed = t("signed") if doc.is_signed else t("unsigned")
        if isinstance(doc, saves.SaveFile):
            name = doc.extra_info or doc.path.name
            text = t("save_header", name=name, version=doc.renpy_version or "?", signed=signed)
        elif isinstance(doc, LiveDoc):
            text = t("live_header")
        else:
            text = t("persistent_header", signed=signed)
        text += "\n" + str(doc.path)
        self.header.config(text=("● " if self.dirty else "") + text)
        self.photo = None
        shot = getattr(doc, "screenshot", None)
        if shot:
            try:
                img = tk.PhotoImage(data=base64.b64encode(shot).decode("ascii"))
                factor = max(1, img.width() // 160)
                self.photo = img.subsample(factor, factor)
            except tk.TclError:
                self.photo = None
        self.shot.config(image=self.photo or "", text="" if self.photo or not isinstance(doc, saves.SaveFile)
                         else t("screenshot_none"))

    # -- variables tree ---------------------------------------------------

    def fill_variables(self):
        self.var_tree.delete(*self.var_tree.get_children())
        self.nodes = {}
        if self.doc is None:
            return
        needle = self.filter_var.get().lower()
        variables = self.doc.variables
        for key, value in sorted(variables.items(), key=lambda kv: values.fmt_key(kv[0]).lower()):
            name = values.fmt_key(key)
            if self.hide_internal.get() and saves.is_internal(name):
                continue
            if needle and needle not in name.lower():
                continue
            type_name = None
            if isinstance(self.doc, LiveDoc):
                type_name = self.doc.types.get(name)
                if name in self.doc.frozen:
                    type_name = "❄ " + (type_name or "")
            self.add_node("", name, values.Ref(variables, key), value, type_name)

    def toggle_freeze(self):
        if not isinstance(self.doc, LiveDoc):
            messagebox.showinfo(t("app_title"), t("freeze_live_only"))
            return
        sel = self.var_tree.selection()
        if not sel or self.var_tree.parent(sel[0]):
            messagebox.showinfo(t("app_title"), t("freeze_top_level"))
            return
        name = self.var_tree.item(sel[0], "text")
        client = self.doc.live
        if not client.supports_freeze():
            messagebox.showinfo(t("app_title"), t("freeze_old_patch"))
            return
        try:
            if name in self.doc.frozen:
                client.unfreeze(name)
                self.doc.frozen.discard(name)
                self.app.set_status(t("unfrozen", name=name), "green")
            else:
                client.freeze(name, self.doc.variables[name])
                self.doc.frozen.add(name)
                self.app.set_status(t("frozen", name=name), "green")
        except (OSError, ValueError) as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        type_name = (("❄ " if name in self.doc.frozen else "") + (self.doc.types.get(name) or ""))
        self.var_tree.item(sel[0], values=(type_name, self.var_tree.item(sel[0], "values")[1]))

    def add_node(self, parent, label, ref, value, type_name=None):
        iid = self.var_tree.insert(parent, tk.END, text=label,
                                   values=(type_name or values.type_label(value), values.preview(value)))
        self.nodes[iid] = (ref, value)
        if values.has_children(value):
            self.var_tree.insert(iid, tk.END, iid=iid + DUMMY)
        return iid

    def on_open(self, _event):
        iid = self.var_tree.focus()
        if self.var_tree.exists(iid + DUMMY):
            self.var_tree.delete(iid + DUMMY)
            _, value = self.nodes[iid]
            for label, ref, child in values.children(value):
                self.add_node(iid, label, ref, child)

    def edit_selected(self):
        sel = self.var_tree.selection()
        if not sel or sel[0] not in self.nodes:
            return
        iid = sel[0]
        ref, value = self.nodes[iid]
        if ref is None or not values.is_editable(value):
            messagebox.showinfo(t("app_title"), t("not_editable"))
            return
        top = iid
        while self.var_tree.parent(top):
            top = self.var_tree.parent(top)
        top_name = self.var_tree.item(top, "text")
        if isinstance(self.doc, LiveDoc) and self.doc.types.get(top_name) == "tuple":
            messagebox.showinfo(t("app_title"), t("live_not_editable"))
            return
        name = self.var_tree.item(iid, "text")
        text = simpledialog.askstring(t("edit_title", name=name),
                                      t("edit_prompt", name=name, type=values.type_label(value)),
                                      initialvalue=values.edit_text(value), parent=self)
        if text is None:
            return
        try:
            new = values.parse_value(text, value)
        except (ValueError, SyntaxError, TypeError) as exc:
            messagebox.showerror(t("error"), t("invalid_value", error=exc))
            return
        old = ref.get()
        ref.set(new)
        if isinstance(self.doc, LiveDoc):
            try:
                self.doc.live.set_variable(top_name, self.doc.variables[top_name])
            except (OSError, ValueError) as exc:
                ref.set(old)
                messagebox.showerror(t("error"), str(exc))
                return
            self.app.set_status(t("live_applied", name=top_name), "green")
        self.nodes[iid] = (ref, new)
        self.var_tree.item(iid, values=(values.type_label(new), values.preview(new)))
        for child in self.var_tree.get_children(iid):
            self.var_tree.delete(child)
        if values.has_children(new):
            self.var_tree.insert(iid, tk.END, iid=iid + DUMMY)
        if not isinstance(self.doc, LiveDoc):
            self.dirty = True
            self.show_header()

    # -- writing ------------------------------------------------------------

    def write(self):
        if self.doc is None:
            messagebox.showinfo(t("app_title"), t("nothing_open"))
            return
        if isinstance(self.doc, LiveDoc):
            messagebox.showinfo(t("app_title"), t("live_instant"))
            return
        keys = savetoken.load_signing_keys() if self.doc.is_signed else []
        if self.doc.is_signed and not keys:
            msg = t("no_key_persistent") if isinstance(self.doc, saves.PersistentFile) else t("no_key_save")
            if not messagebox.askyesno(t("app_title"), msg, icon="warning"):
                return
        try:
            result = self.doc.write(keys=keys)
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        self.dirty = False
        self.show_header()
        key = "write_done_signed" if result.signed else "write_done"
        self.app.set_status(t(key, backup=result.backup), "green")
        self.refresh()

    def revert(self):
        if self.doc is None:
            return
        if isinstance(self.doc, LiveDoc):
            self.doc = None
            self.open_live()
            return
        path, persistent = self.doc.path, isinstance(self.doc, saves.PersistentFile)
        self.dirty = False
        self.doc = None
        self.load(path, persistent)
