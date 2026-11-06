"""Value search tab: find the variable behind a value, Cheat-Engine style."""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import live, saves, scan, values
from ..i18n import t
from .theme import c
from .widgets import scrolled

MAX_ROWS = 2000
SOURCES = ("live", "latest", "pick")


class ScanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.game = None
        self.scan = scan.Scan()
        self.rows = []

        ttk.Label(self, text=t("scan_hint"), foreground=c("gray"), wraplength=1000,
                  justify=tk.LEFT).pack(anchor="w", pady=(0, 8))

        src = ttk.Frame(self)
        src.pack(fill=tk.X)
        ttk.Label(src, text=t("scan_source")).pack(side=tk.LEFT)
        self.source = tk.StringVar(value="live")
        for key in SOURCES:
            ttk.Radiobutton(src, text=t("scan_src_" + key), value=key, variable=self.source).pack(side=tk.LEFT, padx=(10, 0))

        ctl = ttk.Frame(self)
        ctl.pack(fill=tk.X, pady=8)
        ttk.Label(ctl, text=t("scan_filter")).pack(side=tk.LEFT)
        self.filter_names = [t("filter_" + f) for f in scan.FILTERS]
        self.filter_box = ttk.Combobox(ctl, values=self.filter_names, state="readonly", width=16)
        self.filter_box.current(0)
        self.filter_box.pack(side=tk.LEFT, padx=6)
        self.filter_box.bind("<<ComboboxSelected>>", lambda e: self._update_value_state())
        ttk.Label(ctl, text=t("scan_value")).pack(side=tk.LEFT, padx=(6, 0))
        self.value_var = tk.StringVar()
        self.value_entry = ttk.Entry(ctl, textvariable=self.value_var, width=14)
        self.value_entry.pack(side=tk.LEFT, padx=6)
        self.first_btn = ttk.Button(ctl, text=t("scan_first"), command=lambda: self.take(first=True))
        self.first_btn.pack(side=tk.LEFT, padx=(12, 0))
        self.next_btn = ttk.Button(ctl, text=t("scan_next"), command=lambda: self.take(first=False), state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=6)
        ttk.Button(ctl, text=t("scan_new"), command=self.reset).pack(side=tk.LEFT)
        self._update_value_state()

        self.status = ttk.Label(self, text=t("scan_none_yet"), foreground=c("gray"))
        self.status.pack(anchor="w")

        frame, self.tree = scrolled(self, ttk.Treeview, columns=("before", "after"), selectmode="browse", height=8)
        self.tree.heading("#0", text=t("col_variable"))
        self.tree.heading("before", text=t("col_before"))
        self.tree.heading("after", text=t("col_after"))
        self.tree.column("#0", width=380)
        self.tree.column("before", width=220)
        self.tree.column("after", width=220)
        frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", lambda e: self.set_live(freeze=False))

        act = ttk.Frame(self)
        act.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(act, text=t("scan_set_live"), command=lambda: self.set_live(freeze=False)).pack(side=tk.LEFT)
        ttk.Button(act, text=t("scan_freeze"), command=lambda: self.set_live(freeze=True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(act, text=t("ctx_copy_name"), command=self.copy_name).pack(side=tk.LEFT)

    def can_close(self):
        return True

    def set_game(self, game):
        self.game = game
        self.reset()

    def _mode(self):
        return scan.FILTERS[self.filter_box.current()]

    def _update_value_state(self):
        self.value_entry.config(state=tk.NORMAL if self._mode() == "equals" else tk.DISABLED)

    def reset(self):
        self.scan = scan.Scan()
        self.rows = []
        self.tree.delete(*self.tree.get_children())
        self.next_btn.config(state=tk.DISABLED)
        self.status.config(text=t("scan_none_yet"), foreground=c("gray"))

    # -- snapshots ----------------------------------------------------------

    def _snapshot_source(self):
        """A callable producing a Snapshot (runs in the background), or None if cancelled."""
        if self.game is None and self.source.get() != "pick":
            messagebox.showinfo(t("app_title"), t("need_game"))
            return None
        kind = self.source.get()
        if kind == "live":
            root = self.game.root
            return lambda: scan.snapshot_live(root)
        if kind == "latest":
            entries = saves.list_saves(saves.default_save_dirs(self.game))
            if not entries:
                messagebox.showinfo(t("app_title"), t("no_saves"))
                return None
            path = entries[0].path
            return lambda: scan.snapshot_save(path)
        dirs = saves.default_save_dirs(self.game)
        path = filedialog.askopenfilename(title=t("pick_save_file"), filetypes=[(t("filetype_save"), "*.save")],
                                          initialdir=str(dirs[0]) if dirs else None)
        if not path:
            return None
        return lambda: scan.snapshot_save(Path(path))

    def take(self, first: bool):
        make = self._snapshot_source()
        if make is None:
            return
        mode, wanted = self._mode(), self.value_var.get()
        if mode == "equals" and not wanted.strip():
            messagebox.showinfo(t("app_title"), t("scan_need_value"))
            return
        self.status.config(text=t("scan_working"), foreground=c("gray"))
        self.first_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.DISABLED)
        session = self.scan if not first else scan.Scan()

        def work():
            snap = make()
            rows = session.first(snap, mode, wanted) if first else session.next(snap, mode, wanted)
            return session, snap, rows

        def done(result):
            self.scan, snap, rows = result
            self.rows = rows
            self.first_btn.config(state=tk.NORMAL)
            self.next_btn.config(state=tk.NORMAL)
            self.show_rows(snap)

        def failed(exc):
            self.first_btn.config(state=tk.NORMAL)
            self.next_btn.config(state=tk.NORMAL if self.scan.previous else tk.DISABLED)
            msg = t("live_not_running") if str(exc) == "live_not_running" else str(exc)
            self.status.config(text=msg.splitlines()[0], foreground=c("red"))
            messagebox.showinfo(t("app_title"), msg)

        self.app.runner.run(work, done, failed)

    def show_rows(self, snap):
        self.tree.delete(*self.tree.get_children())
        fmt = lambda v: "—" if v is scan.MISSING else values.preview(v, 80)  # noqa: E731
        for i, (path, old, new) in enumerate(self.rows[:MAX_ROWS]):
            self.tree.insert("", tk.END, iid=str(i), text=path, values=(fmt(old), fmt(new)))
        source = t("scan_src_live") if snap.source == "live" else Path(snap.source).name
        text = t("scan_status", count=len(self.rows), source=source,
                 time=time.strftime("%H:%M:%S", time.localtime(snap.taken)))
        if len(self.rows) > MAX_ROWS:
            text += "  " + t("scan_more", shown=MAX_ROWS)
        self.status.config(text=text, foreground=c("green") if 0 < len(self.rows) <= 20 else c("gray"))

    # -- actions --------------------------------------------------------------

    def _selected(self):
        sel = self.tree.selection()
        return self.rows[int(sel[0])] if sel else None

    def set_live(self, freeze: bool):
        row = self._selected()
        if row is None or self.game is None:
            return
        path, _old, new = row
        name = scan.top_level(path)
        if name is None:
            messagebox.showinfo(t("app_title"), t("scan_need_top"))
            return
        client = live.LiveGame(self.game.root)
        if not client.is_running():
            messagebox.showinfo(t("app_title"), t("live_not_running"))
            return
        if freeze and not client.supports_freeze():
            messagebox.showinfo(t("app_title"), t("freeze_old_patch"))
            return
        current = None if new is scan.MISSING else new
        text = simpledialog.askstring(t("edit_title", name=name), t("edit_prompt", name=name,
                                      type=values.type_label(current)),
                                      initialvalue=values.edit_text(current), parent=self)
        if text is None:
            return
        try:
            value = values.parse_value(text, current)
            if isinstance(value, bytes):
                value = values.edit_text(value)
            (client.freeze if freeze else client.set_variable)(name, value)
        except (ValueError, SyntaxError, TypeError, OSError) as exc:
            messagebox.showerror(t("error"), t("invalid_value", error=exc))
            return
        self.app.set_status(t("frozen", name=name) if freeze else t("live_applied", name=name), "green")

    def copy_name(self):
        row = self._selected()
        if row is not None:
            self.clipboard_clear()
            self.clipboard_append(row[0])
