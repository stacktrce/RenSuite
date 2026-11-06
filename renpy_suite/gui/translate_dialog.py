"""'Export translations' dialog."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import translate
from ..i18n import t
from .theme import c, style_window
from .widgets import open_path


def write_tl_exists(game, language) -> bool:
    return (game.game_dir / "tl" / language).exists()


class TranslateDialog(tk.Toplevel):
    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.game = tab.game
        self.title(t("tr_title"))
        self.resizable(False, False)
        self.transient(tab.winfo_toplevel())
        body = ttk.Frame(self, padding=16)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=t("tr_language")).grid(row=0, column=0, sticky="w")
        self.language = tk.StringVar(value="german")
        ttk.Entry(body, textvariable=self.language, width=24).grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(body, text=t("tr_language_hint"), foreground=c("gray"), wraplength=480,
                  justify=tk.LEFT).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(2, 10))

        self.write_csv = tk.BooleanVar(value=True)
        self.write_tl = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text=t("tr_csv"), variable=self.write_csv).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(body, text=t("tr_tl"), variable=self.write_tl).grid(row=3, column=0, columnspan=2, sticky="w")

        ttk.Label(body, text=t("tr_fill")).grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.fill = tk.StringVar()
        frow = ttk.Frame(body)
        frow.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))
        ttk.Entry(frow, textvariable=self.fill, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(frow, text=t("browse"), command=self.pick_csv).pack(side=tk.LEFT, padx=(6, 0))

        self.target = tk.StringVar(value="folder")
        ttk.Radiobutton(body, text=t("tr_target_folder"), value="folder", variable=self.target).grid(
            row=5, column=0, sticky="w", pady=(10, 0))
        self.folder = tk.StringVar(value=str(self.game.root / "translations"))
        orow = ttk.Frame(body)
        orow.grid(row=5, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))
        ttk.Entry(orow, textvariable=self.folder, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(orow, text=t("browse"), command=self.pick_folder).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Radiobutton(body, text=t("tr_target_game"), value="game", variable=self.target).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.status = ttk.Label(body, text="", foreground=c("gray"), wraplength=560, justify=tk.LEFT)
        self.status.grid(row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.go = ttk.Button(buttons, text=t("tr_export_go"), command=self.run)
        self.go.pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("close"), command=self.destroy).pack(side=tk.LEFT, padx=(6, 0))
        style_window(self)

    def pick_csv(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("CSV", "*.csv")])
        if path:
            self.fill.set(path)

    def pick_folder(self):
        path = filedialog.askdirectory(parent=self)
        if path:
            self.folder.set(path)
            self.target.set("folder")

    def run(self):
        language = self.language.get().strip()
        if not translate.LANG_RE.match(language):
            messagebox.showinfo(t("app_title"), t("tr_bad_language"), parent=self)
            return
        if not (self.write_csv.get() or self.write_tl.get()):
            messagebox.showinfo(t("app_title"), t("tr_nothing"), parent=self)
            return
        into_game = self.target.get() == "game"
        if into_game and write_tl_exists(self.game, language):
            messagebox.showinfo(t("app_title"), t("tr_exists", language=language), parent=self)
            return
        out_dir = self.game.game_dir if into_game else Path(self.folder.get().strip() or self.game.root / "translations")
        fill = self.fill.get().strip()
        write_csv, write_tl = self.write_csv.get(), self.write_tl.get()
        runner = self.tab.app.runner
        game = self.game
        self.go.config(state=tk.DISABLED)

        def progress(done, total, name):
            runner.call(lambda: self.winfo_exists() and self.status.config(
                text=t("tr_working", done=done, total=total), foreground=c("gray")))

        def work():
            lines, errors = translate.extract(game, progress)
            messages = []
            csv_dir = game.root / "translations" if into_game else out_dir
            if write_csv:
                csv_dir.mkdir(parents=True, exist_ok=True)
                translate.write_csv(lines, csv_dir / "dialogue.csv")
                messages.append(t("tr_done_csv", count=len(lines), path=csv_dir / "dialogue.csv"))
            if write_tl:
                translations = translate.read_translations(fill) if fill else None
                counts = translate.write_tl(lines, language, out_dir, translations)
                messages.append(t("tr_done", say=counts["say"], strings=counts["string"],
                                  translated=counts["translated"], path=out_dir / "tl" / language))
            return messages, errors, (csv_dir if write_csv and not write_tl else out_dir)

        def done(result):
            messages, errors, folder = result
            if not self.winfo_exists():
                return
            self.go.config(state=tk.NORMAL)
            if errors:
                messages.append(t("decompile_errors") + " " + ", ".join(name for name, _ in errors[:5]))
            self.status.config(text="\n".join(messages), foreground=c("orange" if errors else "green"))
            if not into_game:
                open_path(folder)

        def failed(exc):
            if self.winfo_exists():
                self.go.config(state=tk.NORMAL)
                self.status.config(text=str(exc), foreground=c("red"))

        runner.run(work, done, failed)
