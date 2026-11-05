"""Archives tab: browse, extract and create .rpa archives."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import rpa
from ..i18n import t
from .widgets import ProgressPanel, human_size, open_path, scrolled


class ArchivesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.paths = []
        self.archive = None
        self.last_output = None

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(panes, text=t("archives_frame"), padding=6)
        frame, self.listbox = scrolled(left, tk.Listbox, selectmode=tk.BROWSE, activestyle="none",
                                       exportselection=False, width=34, height=6)
        frame.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.show_selected())
        row = ttk.Frame(left)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(row, text=t("add_archives"), command=self.add_archives).pack(side=tk.LEFT)
        ttk.Button(row, text=t("remove_selected"), command=self.remove_archive).pack(side=tk.LEFT, padx=6)
        panes.add(left, weight=1)

        right = ttk.LabelFrame(panes, text=t("contents_frame"), padding=6)
        frow = ttk.Frame(right)
        frow.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(frow, text=t("filter")).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.fill_contents())
        ttk.Entry(frow, textvariable=self.filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.summary = ttk.Label(frow, text="", foreground="gray")
        self.summary.pack(side=tk.RIGHT)
        frame, self.tree = scrolled(right, ttk.Treeview, columns=("size",), selectmode="extended", height=6)
        self.tree.heading("#0", text=t("col_name"))
        self.tree.heading("size", text=t("col_size"))
        self.tree.column("#0", width=420)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        frame.pack(fill=tk.BOTH, expand=True)
        panes.add(right, weight=3)

        out = ttk.LabelFrame(self, text=t("output_frame"), padding=6)
        out.pack(fill=tk.X, pady=(8, 0))
        orow = ttk.Frame(out)
        orow.pack(fill=tk.X)
        self.output_var = tk.StringVar()
        ttk.Entry(orow, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(orow, text=t("browse"), command=self.browse_output).pack(side=tk.LEFT, padx=6)
        ttk.Label(out, text=t("output_hint_archives"), foreground="gray").pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions, text=t("extract_all"), command=self.extract_all).pack(side=tk.LEFT)
        ttk.Button(actions, text=t("extract_selected"), command=self.extract_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text=t("pack_folder"), command=self.pack_folder).pack(side=tk.LEFT)
        ttk.Button(actions, text=t("open_folder"), command=self.open_output).pack(side=tk.RIGHT)

        self.progress = ProgressPanel(self, app.runner)
        self.progress.pack(fill=tk.X, pady=(8, 0))

    def can_close(self):
        return True

    def set_game(self, game):
        self.paths = list(game.archives)
        self.refresh_list()

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.paths:
            self.listbox.insert(tk.END, p.name)
        if self.paths:
            self.listbox.selection_set(0)
        self.show_selected()

    def add_archives(self):
        files = filedialog.askopenfilenames(title=t("pick_archive_files"),
                                            filetypes=[(t("filetype_rpa"), "*.rpa"), (t("filetype_all"), "*.*")])
        for f in files:
            p = Path(f)
            if p not in self.paths:
                self.paths.append(p)
        self.refresh_list()

    def remove_archive(self):
        sel = self.listbox.curselection()
        if sel:
            del self.paths[sel[0]]
            self.refresh_list()

    def show_selected(self):
        sel = self.listbox.curselection()
        self.archive = None
        if sel:
            path = self.paths[sel[0]]
            try:
                self.archive = rpa.RPAArchive(path)
            except (OSError, rpa.RPAError) as exc:
                self.summary.config(text=t("archive_error", name=path.name, error=exc))
        self.fill_contents()

    def fill_contents(self):
        self.tree.delete(*self.tree.get_children())
        if self.archive is None:
            if not self.listbox.curselection():
                self.summary.config(text="")
            return
        needle = self.filter_var.get().lower()
        total = 0
        for name in self.archive.names():
            size = self.archive.size(name)
            total += size
            if needle and needle not in name.lower():
                continue
            self.tree.insert("", tk.END, iid=name, text=name, values=(human_size(size),))
        self.summary.config(text=t("archive_summary", version=self.archive.version,
                                   count=len(self.archive.index), size=human_size(total)))

    def browse_output(self):
        d = filedialog.askdirectory(title=t("output_frame").strip())
        if d:
            self.output_var.set(d)

    def output_for(self, archive_path: Path) -> Path:
        base = self.output_var.get().strip()
        if base:
            return Path(base) / archive_path.stem if len(self.paths) > 1 else Path(base)
        return rpa.default_output_dir(archive_path)

    def _start(self):
        if self.progress.busy:
            return False
        self.progress.start(t("working"))
        return True

    def extract_all(self):
        if not self.paths:
            messagebox.showinfo(t("app_title"), t("no_archives"))
            return
        if not self._start():
            return
        paths = list(self.paths)
        cancel = self.progress.cancel_event

        def work():
            count, errors = 0, []
            for path in paths:
                if cancel.is_set():
                    break
                try:
                    dest = self.output_for(path)
                    count += rpa.RPAArchive(path).extract(
                        dest, progress=self.progress.progress(t("extracting", name=path.name)), cancel=cancel)
                    self.last_output = dest
                except (OSError, rpa.RPAError) as exc:
                    errors.append(t("archive_error", name=path.name, error=exc))
            return count, errors

        self.app.runner.run(work, self._extract_done, self._failed)

    def extract_selected(self):
        if self.archive is None:
            messagebox.showinfo(t("app_title"), t("no_archive_selected"))
            return
        names = list(self.tree.selection())
        if not names:
            messagebox.showinfo(t("app_title"), t("no_files_selected"))
            return
        if not self._start():
            return
        archive = self.archive
        dest = self.output_for(archive.path)

        def work():
            n = archive.extract(dest, names, progress=self.progress.progress(t("extracting", name=archive.path.name)),
                                cancel=self.progress.cancel_event)
            self.last_output = dest
            return n, []

        self.app.runner.run(work, self._extract_done, self._failed)

    def _extract_done(self, result):
        count, errors = result
        if errors:
            self.progress.finish(t("extract_done", count=count), "red")
            messagebox.showerror(t("error"), "\n".join(errors))
        else:
            self.progress.finish(t("extract_done", count=count))

    def _failed(self, exc):
        self.progress.finish(str(exc), "red")
        messagebox.showerror(t("error"), str(exc))

    def pack_folder(self):
        src = filedialog.askdirectory(title=t("pack_source"))
        if not src:
            return
        target = filedialog.asksaveasfilename(title=t("pack_target"), defaultextension=".rpa",
                                              initialfile=Path(src).name + ".rpa",
                                              filetypes=[(t("filetype_rpa"), "*.rpa")])
        if not target or not self._start():
            return
        target = Path(target)

        def work():
            return rpa.pack(src, target, progress=self.progress.progress(t("packing", name=target.name)),
                            cancel=self.progress.cancel_event)

        def done(count):
            self.last_output = target.parent
            self.progress.finish(t("pack_done", path=target, count=count))

        self.app.runner.run(work, done, self._failed)

    def open_output(self):
        if self.last_output and Path(self.last_output).exists():
            open_path(self.last_output)
        elif self.output_var.get().strip():
            open_path(self.output_var.get().strip())
