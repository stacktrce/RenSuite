"""'Search all scripts' window for the Scripts tab."""

from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import ttk

from ..i18n import t
from ..search import MAX_HITS
from .theme import c, style_window
from .widgets import scrolled


class SearchWindow(tk.Toplevel):
    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.hits = []
        self.cancel = threading.Event()
        self.title(t("search_title"))
        self.geometry("900x520")
        self.transient(tab.winfo_toplevel())

        body = ttk.Frame(self, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        row = ttk.Frame(body)
        row.pack(fill=tk.X)
        self.query = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.query)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda e: self.run())
        self.regex = tk.BooleanVar(value=False)
        self.case = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text=t("search_regex"), variable=self.regex).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(row, text=t("search_case"), variable=self.case).pack(side=tk.LEFT, padx=(8, 0))
        self.button = ttk.Button(row, text=t("search_go"), command=self.run)
        self.button.pack(side=tk.LEFT, padx=(8, 0))

        self.status = ttk.Label(body, text=t("search_hint"), foreground=c("gray"))
        self.status.pack(anchor="w", pady=6)
        frame, self.tree = scrolled(body, ttk.Treeview, columns=("line", "text"), selectmode="browse", height=10)
        self.tree.heading("#0", text=t("search_col_script"))
        self.tree.heading("line", text=t("search_col_line"))
        self.tree.heading("text", text=t("search_col_text"))
        self.tree.column("#0", width=220)
        self.tree.column("line", width=60, anchor="e", stretch=False)
        self.tree.column("text", width=560)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self.jump())
        self.tree.bind("<Return>", lambda e: self.jump())
        self.protocol("WM_DELETE_WINDOW", self.close)
        style_window(self)
        self.entry.focus_set()

    def close(self):
        self.cancel.set()
        self.destroy()

    def run(self):
        query = self.query.get()
        if not query:
            return
        if self.regex.get():
            try:
                re.compile(query)
            except re.error as exc:
                self.status.config(text=t("search_bad_regex", error=exc), foreground=c("red"))
                return
        self.cancel = threading.Event()
        self.button.config(state=tk.DISABLED)
        index, runner = self.tab.index, self.tab.app.runner

        def progress(done, total, name):
            runner.call(lambda: self.winfo_exists() and self.status.config(
                text=t("search_progress", done=done, total=total), foreground=c("gray")))

        def done(hits):
            if not self.winfo_exists():
                return
            self.button.config(state=tk.NORMAL)
            self.hits = hits
            self.tree.delete(*self.tree.get_children())
            for i, hit in enumerate(hits):
                self.tree.insert("", tk.END, iid=str(i), text=hit.script, values=(hit.line, hit.text[:300]))
            text = t("search_done", count=len(hits))
            if len(hits) >= MAX_HITS:
                text += " " + t("search_limit", limit=MAX_HITS)
            self.status.config(text=text, foreground=c("green") if hits else c("gray"))

        def failed(exc):
            if self.winfo_exists():
                self.button.config(state=tk.NORMAL)
                self.status.config(text=str(exc), foreground=c("red"))

        regex, case, cancel = self.regex.get(), self.case.get(), self.cancel
        runner.run(lambda: index.search(query, regex, case, progress, cancel), done, failed)

    def jump(self):
        sel = self.tree.selection()
        if sel:
            hit = self.hits[int(sel[0])]
            self.tab.open_at(hit.script, hit.line)
