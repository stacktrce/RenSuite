"""Decompiler tab: preview and batch-decompile .rpyc scripts."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import rpyc
from ..game import default_decompile_dir
from ..i18n import t
from .widgets import ProgressPanel, open_path, scrolled


class DecompilerTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.game = None
        self.sources = []  # [(display_name, read_bytes)]
        self.extra_files = []

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(panes, text=t("scripts_frame"), padding=6)
        frow = ttk.Frame(left)
        frow.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(frow, text=t("filter")).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.fill_list())
        ttk.Entry(frow, textvariable=self.filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        frame, self.tree = scrolled(left, ttk.Treeview, show="tree", selectmode="browse", height=6)
        self.tree.column("#0", width=300)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.preview_selected())
        self.include_archived = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text=t("include_archived"), variable=self.include_archived,
                        command=self.reload_sources).pack(anchor="w", pady=(6, 0))
        ttk.Button(left, text=t("add_rpyc"), command=self.add_files).pack(anchor="w", pady=(4, 0))
        panes.add(left, weight=1)

        right = ttk.LabelFrame(panes, text=t("preview_frame"), padding=6)
        frame, self.text = scrolled(right, tk.Text, wrap="none", font=("Consolas", 10), undo=False,
                                    height=8, width=60)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Button(right, text=t("save_preview"), command=self.save_preview).pack(anchor="e", pady=(6, 0))
        panes.add(right, weight=3)

        out = ttk.LabelFrame(self, text=t("output_frame"), padding=6)
        out.pack(fill=tk.X, pady=(8, 0))
        orow = ttk.Frame(out)
        orow.pack(fill=tk.X)
        self.output_var = tk.StringVar()
        ttk.Entry(orow, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(orow, text=t("browse"), command=self.browse_output).pack(side=tk.LEFT, padx=6)
        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(out, text=t("overwrite"), variable=self.overwrite).pack(anchor="w", pady=(4, 0))
        ttk.Label(out, text=t("output_hint_decompile"), foreground="gray").pack(anchor="w")

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions, text=t("decompile_all"), command=self.decompile_all).pack(side=tk.LEFT)
        ttk.Button(actions, text=t("open_folder"), command=self.open_output).pack(side=tk.RIGHT)

        self.progress = ProgressPanel(self, app.runner)
        self.progress.pack(fill=tk.X, pady=(8, 0))

    def can_close(self):
        return True

    def set_game(self, game):
        self.game = game
        self.extra_files = []
        self.reload_sources()

    def reload_sources(self):
        sources = []
        if self.game is not None:
            sources = self.game.script_sources(include_archives=self.include_archived.get())
        sources += [(str(p), p.read_bytes) for p in self.extra_files]
        self.sources = sources
        self.fill_list()

    def fill_list(self):
        self.tree.delete(*self.tree.get_children())
        needle = self.filter_var.get().lower()
        for i, (name, _) in enumerate(self.sources):
            if not needle or needle in name.lower():
                self.tree.insert("", tk.END, iid=str(i), text=name)

    def add_files(self):
        files = filedialog.askopenfilenames(title=t("pick_rpyc_files"),
                                            filetypes=[(t("filetype_rpyc"), "*.rpyc *.rpymc"),
                                                       (t("filetype_all"), "*.*")])
        for f in files:
            p = Path(f)
            if p not in self.extra_files:
                self.extra_files.append(p)
        self.reload_sources()

    def preview_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name, read = self.sources[int(sel[0])]
        try:
            text = rpyc.decompile(read(), name)
        except Exception as exc:
            text = t("preview_failed", error=exc)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", text)

    def save_preview(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.sources[int(sel[0])][0]
        target = filedialog.asksaveasfilename(defaultextension=".rpy",
                                              initialfile=rpyc.output_relpath(name).name,
                                              filetypes=[("Ren'Py script", "*.rpy")])
        if target:
            Path(target).write_text(self.text.get("1.0", "end-1c"), "utf-8")

    def browse_output(self):
        d = filedialog.askdirectory(title=t("output_frame").strip())
        if d:
            self.output_var.set(d)

    def output_dir(self):
        if self.output_var.get().strip():
            return Path(self.output_var.get().strip())
        if self.game is not None:
            return default_decompile_dir(self.game)
        return None

    def decompile_all(self):
        if not self.sources:
            messagebox.showinfo(t("app_title"), t("no_scripts"))
            return
        out = self.output_dir()
        if out is None:
            messagebox.showinfo(t("app_title"), t("need_output"))
            return
        if self.progress.busy:
            return
        self.progress.start(t("working"))
        sources = [(Path(n).name if n in {str(p) for p in self.extra_files} else n, r) for n, r in self.sources]

        def work():
            return rpyc.decompile_many(sources, out, overwrite=self.overwrite.get(),
                                       progress=self.progress.progress(t("decompiling")),
                                       cancel=self.progress.cancel_event)

        def done(result):
            written, skipped, errors = result
            self.last_output = out
            msg = t("decompile_done", written=written, skipped=skipped, errors=len(errors))
            self.progress.finish(msg, "red" if errors else "green")
            if errors:
                details = "\n".join("%s: %s" % e for e in errors[:20])
                messagebox.showwarning(t("app_title"), t("decompile_errors") + "\n\n" + details)

        def failed(exc):
            self.progress.finish(str(exc), "red")
            messagebox.showerror(t("error"), str(exc))

        self.app.runner.run(work, done, failed)

    def open_output(self):
        out = self.output_dir()
        if out is not None and out.exists():
            open_path(out)
