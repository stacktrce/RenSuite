"""Main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import __version__
from ..game import GameInfo
from ..i18n import t
from .tab_archives import ArchivesTab
from .tab_decompiler import DecompilerTab
from .tab_game import GameTab
from .tab_saves import SavesTab
from .widgets import TaskRunner


class SuiteApp:
    def __init__(self, root: tk.Tk, initial_game=None):
        self.root = root
        self.runner = TaskRunner(root)
        self.game = None

        root.title("%s %s" % (t("app_title"), __version__))
        root.geometry("1100x760")
        root.minsize(860, 600)
        style = ttk.Style()
        for theme in ("vista", "aqua", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        top = ttk.Frame(root, padding=(10, 8, 10, 4))
        top.pack(fill=tk.X)
        ttk.Label(top, text=t("game_label")).pack(side=tk.LEFT)
        self.game_var = tk.StringVar(value=t("no_game"))
        ttk.Label(top, textvariable=self.game_var, font=("", 10, "bold")).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(top, text=t("reload"), command=self.reload_game).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(top, text=t("choose_game"), command=self.choose_game).pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))
        self.tabs = [
            (GameTab(self.notebook, self), "tab_game"),
            (ArchivesTab(self.notebook, self), "tab_archives"),
            (DecompilerTab(self.notebook, self), "tab_decompiler"),
            (SavesTab(self.notebook, self), "tab_saves"),
        ]
        for tab, key in self.tabs:
            self.notebook.add(tab, text="  %s  " % t(key))

        self.status = ttk.Label(root, text="", foreground="gray", padding=(10, 4))
        self.status.pack(fill=tk.X)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if initial_game:
            self.load_game(initial_game)

    def set_status(self, text, color="gray"):
        self.status.config(text=text, foreground=color)

    def choose_game(self):
        path = filedialog.askdirectory(title=t("choose_game"))
        if path:
            self.load_game(path)

    def reload_game(self):
        if self.game is not None:
            self.load_game(self.game.root)

    def load_game(self, path):
        self.set_status(t("loading_game"))
        self.root.config(cursor="watch")

        def done(game):
            self.root.config(cursor="")
            self.game = game
            self.game_var.set("%s  —  %s" % (game.name, game.root))
            self.set_status(t("game_loaded", name=game.name), "green")
            for tab, _ in self.tabs:
                tab.set_game(game)

        def failed(exc):
            self.root.config(cursor="")
            self.set_status("")
            messagebox.showerror(t("error"), t("not_a_game") if isinstance(exc, FileNotFoundError) else str(exc))

        self.runner.run(lambda: GameInfo.load(path), done, failed)

    def on_close(self):
        for tab, _ in self.tabs:
            if not tab.can_close():
                return
        self.root.destroy()


def run(initial_game=None):
    root = tk.Tk()
    SuiteApp(root, initial_game)
    root.mainloop()
