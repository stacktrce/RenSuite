"""Settings and About dialogs."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from .. import __url__, __version__, i18n
from ..i18n import t
from .theme import c, style_window
from .widgets import open_path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def load_icon(size: int):
    path = ASSETS / ("icon-%d.png" % size)
    try:
        return tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None


class _Dialog(tk.Toplevel):
    def __init__(self, master, title):
        super().__init__(master)
        self.withdraw()
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.body = ttk.Frame(self, padding=16)
        self.body.pack(fill=tk.BOTH, expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def show(self):
        self.update_idletasks()
        master = self.master.winfo_toplevel()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        self.deiconify()
        style_window(self)
        self.grab_set()
        self.focus_set()


class SettingsDialog(_Dialog):
    THEMES = ("system", "light", "dark")

    def __init__(self, app):
        super().__init__(app.root, t("settings_title"))
        self.app = app
        settings = app.settings

        system_name = dict(i18n.languages()).get(i18n.detect_language(), "English")
        self.lang_codes = ["system"] + [code for code, _ in i18n.languages()]
        lang_names = [t("lang_system", name=system_name)] + [name for _, name in i18n.languages()]
        theme_names = [t("theme_" + m) for m in self.THEMES]

        ttk.Label(self.body, text=t("settings_language")).grid(row=0, column=0, sticky="w", pady=4)
        self.lang = ttk.Combobox(self.body, values=lang_names, state="readonly", width=32)
        self.lang.current(self.lang_codes.index(settings["language"]) if settings["language"] in self.lang_codes else 0)
        self.lang.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)

        ttk.Label(self.body, text=t("settings_theme")).grid(row=1, column=0, sticky="w", pady=4)
        self.theme = ttk.Combobox(self.body, values=theme_names, state="readonly", width=32)
        self.theme.current(self.THEMES.index(settings["theme"]) if settings["theme"] in self.THEMES else 0)
        self.theme.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)

        ttk.Label(self.body, text=t("settings_export")).grid(row=2, column=0, sticky="w", pady=(12, 0))
        export_row = ttk.Frame(self.body)
        export_row.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))
        self.export_var = tk.StringVar(value=settings.get("export_dir", ""))
        ttk.Entry(export_row, textvariable=self.export_var, width=34).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(export_row, text=t("browse"), command=self.browse_export).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(self.body, text=t("settings_export_hint"), foreground=c("gray")).grid(
            row=3, column=1, sticky="w", padx=(12, 0))

        ttk.Label(self.body, text=t("settings_folder")).grid(row=4, column=0, sticky="w", pady=(12, 4))
        folder = settings.path.parent
        link = ttk.Label(self.body, text=str(folder), foreground=c("accent"), cursor="hand2")
        link.grid(row=4, column=1, sticky="w", padx=(12, 0), pady=(12, 4))
        link.bind("<Button-1>", lambda e: (folder.mkdir(parents=True, exist_ok=True), open_path(folder)))

        buttons = ttk.Frame(self.body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text=t("ok"), command=self.accept).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("cancel"), command=self.destroy).pack(side=tk.LEFT, padx=(6, 0))
        self.bind("<Return>", lambda e: self.accept())
        self.show()

    def browse_export(self):
        folder = filedialog.askdirectory(parent=self, title=t("settings_export"),
                                         initialdir=self.export_var.get() or None)
        if folder:
            self.export_var.set(folder)

    def accept(self):
        settings = self.app.settings
        new = {"language": self.lang_codes[self.lang.current()], "theme": self.THEMES[self.theme.current()]}
        changed = any(settings[k] != v for k, v in new.items())
        settings.update(new)
        settings["export_dir"] = self.export_var.get().strip()
        try:
            settings.save()
        except OSError:
            pass
        self.destroy()
        if changed:
            self.app.apply_settings()


class AboutDialog(_Dialog):
    def __init__(self, app):
        super().__init__(app.root, t("about_title"))
        self.icon = load_icon(128)
        if self.icon is not None:
            ttk.Label(self.body, image=self.icon).pack(pady=(0, 10))
        ttk.Label(self.body, text=t("app_title"), font=("", 16, "bold")).pack()
        ttk.Label(self.body, text=t("about_version", version=__version__), foreground=c("gray")).pack(pady=(2, 10))
        ttk.Label(self.body, text=t("about_tagline"), wraplength=360, justify=tk.CENTER).pack()
        link = ttk.Label(self.body, text=__url__, foreground=c("accent"), cursor="hand2")
        link.pack(pady=(10, 10))
        link.bind("<Button-1>", lambda e: webbrowser.open(__url__))
        ttk.Label(self.body, text=t("about_license"), foreground=c("gray")).pack()
        ttk.Label(self.body, text=t("about_disclaimer"), foreground=c("gray"), wraplength=360,
                  justify=tk.CENTER).pack(pady=(2, 0))
        ttk.Button(self.body, text=t("close"), command=self.destroy).pack(pady=(14, 0))
        self.show()
