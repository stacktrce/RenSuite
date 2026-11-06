"""Main window."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from .. import __url__, __version__, i18n
from ..game import GameInfo
from ..i18n import t
from ..settings import Settings
from . import theme
from .dialogs import AboutDialog, SettingsDialog, load_icon
from .tab_archives import ArchivesTab
from .tab_decompiler import DecompilerTab
from .tab_game import GameTab
from .tab_mods import ModsTab
from .tab_saves import SavesTab
from .theme import c
from .widgets import TaskRunner


class SuiteApp:
    def __init__(self, root: tk.Tk, initial_game=None, language_override=None):
        self.root = root
        self.runner = TaskRunner(root)
        self.game = None
        self.settings = Settings()
        self.language_override = language_override
        self.tabs = []

        root.geometry("1100x780")
        root.minsize(860, 600)
        self.icons = [img for img in (load_icon(s) for s in (256, 64, 32, 16)) if img is not None]
        if self.icons:
            root.iconphoto(True, *self.icons)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build()
        if initial_game:
            self.load_game(initial_game)

    # -- construction --------------------------------------------------------

    def build(self):
        i18n.set_language(self.language_override or self.settings["language"])
        theme.apply(self.root, self.settings["theme"])
        root = self.root
        root.title("%s %s" % (t("app_title"), __version__))

        self.menubar = ttk.Frame(root, padding=(4, 2, 4, 0))
        self.menubar.pack(fill=tk.X)
        self._menu("menu_file", [
            ("choose_game", self.choose_game, "Ctrl+O"),
            ("reload", self.reload_game, "F5"),
            None,
            ("menu_settings", self.open_settings, None),
            None,
            ("menu_exit", self.on_close, None),
        ])
        self._menu("menu_mods", [
            ("menu_import_mod", lambda: self.mods_tab.import_mod(), None),
            ("menu_mod_folder", lambda: self.mods_tab.open_library(), None),
            None,
            ("menu_mod_format", lambda: webbrowser.open(__url__ + "/blob/main/docs/MODDING.md"), None),
        ])
        self._menu("menu_help", [
            ("menu_docs", lambda: webbrowser.open(__url__ + "#readme"), None),
            ("menu_github", lambda: webbrowser.open(__url__), None),
            None,
            ("menu_about", lambda: AboutDialog(self), None),
        ])
        ttk.Separator(root).pack(fill=tk.X)

        top = ttk.Frame(root, padding=(10, 8, 10, 4))
        top.pack(fill=tk.X)
        ttk.Label(top, text=t("game_label")).pack(side=tk.LEFT)
        self.game_var = tk.StringVar(value=t("no_game") if self.game is None else self._game_title())
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
            (ModsTab(self.notebook, self), "tab_mods"),
        ]
        self.mods_tab = self.tabs[-1][0]
        for tab, key in self.tabs:
            self.notebook.add(tab, text="  %s  " % t(key))

        self.status = ttk.Label(root, text="", foreground=c("gray"), padding=(10, 4))
        self.status.pack(fill=tk.X)

        root.bind("<Control-o>", lambda e: self.choose_game())
        root.bind("<F5>", lambda e: self.reload_game())
        if self.game is not None:
            for tab, _ in self.tabs:
                tab.set_game(self.game)

    def _menu(self, title_key, items):
        style = ttk.Style(self.root)
        style.configure("MenuBar.TLabel", background=style.lookup("TFrame", "background"), padding=(9, 3))
        style.configure("MenuBarHover.TLabel", background=c("button_active"), padding=(9, 3))
        label = ttk.Label(self.menubar, text=t(title_key), style="MenuBar.TLabel")
        menu = tk.Menu(label, tearoff=False)
        for item in items:
            if item is None:
                menu.add_separator()
            else:
                key, command, accel = item
                menu.add_command(label=t(key), command=command, accelerator=accel or "")

        def popup(_event=None):
            menu.tk_popup(label.winfo_rootx(), label.winfo_rooty() + label.winfo_height())

        label.bind("<Button-1>", popup)
        label.bind("<Enter>", lambda e: label.configure(style="MenuBarHover.TLabel"))
        label.bind("<Leave>", lambda e: label.configure(style="MenuBar.TLabel"))
        label.pack(side=tk.LEFT)
        return menu

    def apply_settings(self):
        """Rebuild the interface after the language or theme changed."""
        if not all(tab.can_close() for tab, _ in self.tabs):
            return
        selected = self.notebook.index("current") if self.tabs else 0
        for child in self.root.winfo_children():
            child.destroy()
        self.build()
        self.notebook.select(selected)

    # -- actions -------------------------------------------------------------

    def set_status(self, text, color="gray"):
        self.status.config(text=text, foreground=c(color))

    def open_settings(self):
        SettingsDialog(self)

    def choose_game(self):
        path = filedialog.askdirectory(title=t("choose_game"))
        if path:
            self.load_game(path)

    def reload_game(self):
        if self.game is not None:
            self.load_game(self.game.root)

    def _game_title(self):
        return "%s  —  %s" % (self.game.name, self.game.root)

    def load_game(self, path):
        self.set_status(t("loading_game"))
        self.root.config(cursor="watch")

        def done(game):
            self.root.config(cursor="")
            self.game = game
            self.game_var.set(self._game_title())
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


def run(initial_game=None, language=None):
    root = tk.Tk()
    SuiteApp(root, initial_game, language)
    root.mainloop()
