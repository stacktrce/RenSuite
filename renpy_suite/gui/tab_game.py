"""Game tab: game information and the developer patch."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import game as gamemod
from ..i18n import t
from .widgets import open_path

OPTION_KEYS = {
    "developer": "opt_developer",
    "console": "opt_console",
    "skipping": "opt_skipping",
    "rollback": "opt_rollback",
    "live": "opt_live",
}


class GameTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.game = None

        info = ttk.LabelFrame(self, text=t("info_frame"), padding=10)
        info.pack(fill=tk.X)
        self.fields = {}
        for row, key in enumerate(("info_name", "info_root", "info_version", "info_python", "info_archives",
                                   "info_rpyc", "info_rpy", "info_savedir", "info_savefolders")):
            ttk.Label(info, text=t(key) + ":").grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=1)
            var = tk.StringVar(value="—")
            ttk.Label(info, textvariable=var, wraplength=760, justify=tk.LEFT).grid(row=row, column=1, sticky="w", pady=1)
            self.fields[key] = var
        info.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill=tk.X, pady=(8, 12))
        ttk.Button(buttons, text=t("open_game_folder"), command=self.open_game_folder).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("open_save_folder"), command=self.open_save_folder).pack(side=tk.LEFT, padx=6)

        patch = ttk.LabelFrame(self, text=t("patch_frame"), padding=10)
        patch.pack(fill=tk.X)
        ttk.Label(patch, text=t("patch_intro"), foreground="gray").pack(anchor="w", pady=(0, 6))
        self.option_vars = {}
        for opt, key in OPTION_KEYS.items():
            var = tk.BooleanVar(value=opt in ("developer", "console", "live"))
            ttk.Checkbutton(patch, text=t(key), variable=var).pack(anchor="w")
            self.option_vars[opt] = var
        row = ttk.Frame(patch)
        row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(row, text=t("patch_apply"), command=self.apply_patch).pack(side=tk.LEFT)
        ttk.Button(row, text=t("patch_remove"), command=self.remove_patch).pack(side=tk.LEFT, padx=6)
        self.patch_status = ttk.Label(patch, text="", foreground="gray")
        self.patch_status.pack(anchor="w", pady=(6, 0))

    def can_close(self):
        return True

    def set_game(self, game):
        self.game = game
        f = self.fields
        f["info_name"].set(game.name)
        f["info_root"].set(str(game.root))
        f["info_version"].set(game.renpy_version or t("unknown"))
        f["info_python"].set(game.python or t("unknown"))
        f["info_archives"].set(str(len(game.archives)))
        f["info_rpyc"].set(str(len(game.rpyc_files)))
        f["info_rpy"].set(str(len(game.rpy_files)))
        f["info_savedir"].set(game.save_directory or t("unknown"))
        f["info_savefolders"].set("\n".join(str(d) for d in game.save_dirs()) or t("none_found"))
        status = gamemod.patch_status(game.game_dir)
        if status:
            for opt, var in self.option_vars.items():
                var.set(opt in status)
        self.update_patch_status()

    def update_patch_status(self):
        status = gamemod.patch_status(self.game.game_dir)
        if status:
            self.patch_status.config(text=t("patch_installed", options=", ".join(sorted(status))), foreground="green")
        else:
            self.patch_status.config(text=t("patch_not_installed"), foreground="gray")

    def _need_game(self):
        if self.game is None:
            messagebox.showinfo(t("app_title"), t("need_game"))
            return False
        return True

    def apply_patch(self):
        if not self._need_game():
            return
        options = {o for o, v in self.option_vars.items() if v.get()}
        path = gamemod.apply_patch(self.game.game_dir, options)
        for opt in gamemod.patch_status(self.game.game_dir):
            self.option_vars[opt].set(True)
        self.update_patch_status()
        self.app.set_status(t("patch_applied", path=path) if options else t("patch_removed"), "green")

    def remove_patch(self):
        if not self._need_game():
            return
        gamemod.remove_patch(self.game.game_dir)
        self.update_patch_status()
        self.app.set_status(t("patch_removed"), "green")

    def open_game_folder(self):
        if self._need_game():
            open_path(self.game.root)

    def open_save_folder(self):
        if not self._need_game():
            return
        dirs = self.game.save_dirs()
        if dirs:
            open_path(dirs[-1])
        else:
            messagebox.showinfo(t("app_title"), t("no_saves"))
