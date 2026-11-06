"""Light and dark themes for the Tk interface."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from tkinter import ttk

PALETTES = {
    "light": {
        "bg": "#f3f3f3", "panel": "#ffffff", "field": "#ffffff", "fg": "#1b1b1b", "border": "#c8c8c8",
        "select": "#cce4f7", "selectfg": "#000000", "button": "#e6e6e6", "button_active": "#dadada",
        "accent": "#6b4ce6", "gray": "#6b6b6b", "green": "#1a7f37", "red": "#c62828", "orange": "#a35f00",
        "highlight": "#ffe58a",
    },
    "dark": {
        "bg": "#1f2023", "panel": "#26282c", "field": "#2b2e33", "fg": "#e4e4e4", "border": "#3d4047",
        "select": "#35588f", "selectfg": "#ffffff", "button": "#33363c", "button_active": "#41454c",
        "accent": "#8b6dff", "gray": "#9aa0a6", "green": "#5cc67a", "red": "#ff7070", "orange": "#f0a550",
        "highlight": "#6d5a12",
    },
}

_mode = "light"


def system_prefers_dark() -> bool:
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                 capture_output=True, text=True, timeout=2)
            return "dark" in out.stdout.lower()
    except Exception:
        return False
    import os
    return "dark" in os.environ.get("GTK_THEME", "").lower()


def resolve(setting: str) -> str:
    if setting in PALETTES:
        return setting
    return "dark" if system_prefers_dark() else "light"


def mode() -> str:
    return _mode


def c(name: str) -> str:
    """Theme color by role: gray, green, red, orange, fg, bg, accent …"""
    return PALETTES[_mode].get(name, name)


def apply(root: tk.Tk, setting: str) -> str:
    """Style ``root`` for the given setting ("system", "light", "dark")."""
    global _mode
    _mode = resolve(setting)
    p = PALETTES[_mode]
    style = ttk.Style(root)

    if _mode == "light":
        for native in ("vista", "aqua"):
            if native in style.theme_names():
                style.theme_use(native)
                break
        else:
            style.theme_use("clam")
    else:
        style.theme_use("clam")
        style.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                        bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"],
                        troughcolor=p["field"], selectbackground=p["select"], selectforeground=p["selectfg"],
                        insertcolor=p["fg"], focuscolor=p["accent"])
        style.map(".", foreground=[("disabled", p["gray"])])
        style.configure("TButton", background=p["button"], padding=(10, 3))
        style.map("TButton", background=[("pressed", p["border"]), ("active", p["button_active"])])
        style.configure("TMenubutton", background=p["bg"], padding=(8, 2))
        style.map("TMenubutton", background=[("active", p["button_active"])])
        style.configure("TCheckbutton", indicatorbackground=p["field"], indicatorforeground=p["fg"])
        style.map("TCheckbutton", background=[("active", p["bg"])],
                  indicatorbackground=[("selected", p["accent"]), ("active", p["button_active"])])
        style.configure("TEntry", fieldbackground=p["field"])
        style.configure("TCombobox", fieldbackground=p["field"], background=p["button"], arrowcolor=p["fg"])
        style.map("TCombobox", fieldbackground=[("readonly", p["field"])],
                  selectbackground=[("readonly", p["field"])], selectforeground=[("readonly", p["fg"])])
        style.configure("TNotebook", background=p["bg"])
        style.configure("TNotebook.Tab", background=p["panel"], padding=(10, 4))
        style.map("TNotebook.Tab", background=[("selected", p["bg"]), ("active", p["button_active"])])
        style.configure("TLabelframe", background=p["bg"])
        style.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"])
        style.configure("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"])
        style.map("Treeview", background=[("selected", p["select"])], foreground=[("selected", p["selectfg"])])
        style.configure("Treeview.Heading", background=p["panel"], foreground=p["fg"])
        style.map("Treeview.Heading", background=[("active", p["button_active"])])
        style.configure("TScrollbar", background=p["button"], arrowcolor=p["fg"], troughcolor=p["bg"])
        style.map("TScrollbar", background=[("active", p["button_active"])])
        style.configure("TProgressbar", background=p["accent"], troughcolor=p["field"])
        style.configure("TPanedwindow", background=p["bg"])

    # Classic Tk widgets read their colors from the option database.
    for cls in ("Text", "Listbox"):
        root.option_add("*%s.background" % cls, p["field"])
        root.option_add("*%s.foreground" % cls, p["fg"])
        root.option_add("*%s.selectBackground" % cls, p["select"])
        root.option_add("*%s.selectForeground" % cls, p["selectfg"])
        root.option_add("*%s.highlightColor" % cls, p["accent"])
        root.option_add("*%s.highlightBackground" % cls, p["border"])
    root.option_add("*Text.insertBackground", p["fg"])
    root.option_add("*TCombobox*Listbox.background", p["field"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*Menu.background", p["panel"])
    root.option_add("*Menu.foreground", p["fg"])
    root.option_add("*Menu.activeBackground", p["select"])
    root.option_add("*Menu.activeForeground", p["selectfg"])
    root.configure(background=p["bg"])
    style_window(root)
    return _mode


def style_window(win):
    """Dark or light title bar on Windows 10/11; no-op elsewhere."""
    win.configure(background=PALETTES[_mode]["bg"])
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1 if _mode == "dark" else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / pre-20H1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                           ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass
