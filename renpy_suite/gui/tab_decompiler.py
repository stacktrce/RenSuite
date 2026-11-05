"""Scripts tab: decompile, edit and save scripts back into the game."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import rpyc
from ..game import default_decompile_dir
from ..scriptedit import ScriptEditor
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

        right = ttk.LabelFrame(panes, text=t("editor_frame"), padding=6)
        find = ttk.Frame(right)
        find.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(find, text=t("find")).pack(side=tk.LEFT)
        self.find_var = tk.StringVar()
        find_entry = ttk.Entry(find, textvariable=self.find_var)
        find_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        find_entry.bind("<Return>", lambda e: self.find_next())
        ttk.Button(find, text=t("find_next"), command=self.find_next).pack(side=tk.LEFT)
        self.edit_status = ttk.Label(find, text="", foreground="gray")
        self.edit_status.pack(side=tk.RIGHT, padx=(12, 0))

        frame, self.text = scrolled(right, tk.Text, wrap="none", font=("Consolas", 10), undo=True,
                                    height=8, width=60)
        frame.pack(fill=tk.BOTH, expand=True)
        self.text.tag_configure("found", background="#ffe58a")
        self.text.bind("<<Modified>>", lambda e: self.update_edit_status())
        self.text.bind("<Control-s>", lambda e: (self.save_to_game(), "break")[1])
        self.text.bind("<Control-f>", lambda e: (find_entry.focus_set(), "break")[1])

        erow = ttk.Frame(right)
        erow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(erow, text=t("save_to_game"), command=self.save_to_game).pack(side=tk.LEFT)
        ttk.Button(erow, text=t("restore_original"), command=self.restore_original).pack(side=tk.LEFT, padx=6)
        ttk.Button(erow, text=t("save_preview"), command=self.save_preview).pack(side=tk.RIGHT)
        ttk.Label(right, text=t("editor_hint"), foreground="gray", wraplength=640,
                  justify=tk.LEFT).pack(anchor="w", pady=(4, 0))
        panes.add(right, weight=3)
        self.editor = None
        self.current = None  # index into self.sources shown in the editor
        self._switching = False

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
        return not self.text.edit_modified() or messagebox.askyesno(t("app_title"), t("unsaved_script"))

    def set_game(self, game):
        self.game = game
        self.editor = ScriptEditor(game)
        self.extra_files = []
        self.current = None
        self.text.delete("1.0", tk.END)
        self.text.edit_modified(False)
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
                edited = self.editor is not None and self.editor.is_edited(name)
                self.tree.insert("", tk.END, iid=str(i), text=("✎ " if edited else "") + name)
        if self.current is not None and self.tree.exists(str(self.current)):
            self._switching = True
            self.tree.selection_set(str(self.current))
            self._switching = False

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
        if self._switching or not sel or int(sel[0]) == self.current:
            return
        if self.text.edit_modified() and not messagebox.askyesno(t("app_title"), t("unsaved_script")):
            self._switching = True
            self.tree.selection_set(str(self.current))
            self._switching = False
            return
        self.current = int(sel[0])
        name, read = self.sources[self.current]
        try:
            if self._is_game_source(name):
                text, _ = self.editor.load_text(name, read)
            else:
                text = rpyc.decompile(read(), name)
        except Exception as exc:
            text = t("preview_failed", error=exc)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", text)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.update_edit_status()

    def _is_game_source(self, name):
        return self.editor is not None and name not in {str(p) for p in self.extra_files}

    def update_edit_status(self):
        if self.current is None:
            self.edit_status.config(text="")
        elif self.text.edit_modified():
            self.edit_status.config(text=t("status_unsaved"), foreground="orange")
        elif self.editor is not None and self.editor.is_edited(self.sources[self.current][0]):
            self.edit_status.config(text=t("status_edited"), foreground="green")
        else:
            self.edit_status.config(text=t("status_original"), foreground="gray")

    def find_next(self):
        needle = self.find_var.get()
        self.text.tag_remove("found", "1.0", tk.END)
        if not needle:
            return
        start = self.text.index("insert +1c")
        pos = self.text.search(needle, start, nocase=True, stopindex=tk.END) or \
            self.text.search(needle, "1.0", nocase=True, stopindex=tk.END)
        if pos:
            end = "%s+%dc" % (pos, len(needle))
            self.text.tag_add("found", pos, end)
            self.text.mark_set("insert", pos)
            self.text.see(pos)

    def save_to_game(self):
        if self.current is None:
            return
        name, read = self.sources[self.current]
        if not self._is_game_source(name):
            messagebox.showinfo(t("app_title"), t("need_game"))
            return
        try:
            path = self.editor.apply(name, read, self.text.get("1.0", "end-1c"))
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        self.text.edit_modified(False)
        self.fill_list()
        self.update_edit_status()
        self.app.set_status(t("script_saved", path=path), "green")

    def restore_original(self):
        if self.current is None:
            return
        name, read = self.sources[self.current]
        if not self._is_game_source(name) or not self.editor.is_edited(name):
            return
        if not messagebox.askyesno(t("app_title"), t("confirm_restore")):
            return
        try:
            self.editor.restore(name)
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        self.text.edit_modified(False)
        current, self.current = self.current, None
        self.fill_list()
        self.tree.selection_set(str(current))
        self.app.set_status(t("script_restored"), "green")

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
