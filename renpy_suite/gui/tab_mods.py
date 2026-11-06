"""Mods tab: a library of shareable mods, installing them and applying cheats."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import live, mods, savetoken, saves
from ..i18n import t
from .theme import c, style_window
from .widgets import open_path, scrolled


class ModsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.game = None
        self.installer = None
        self.library = mods.ModLibrary()
        self.mod_list = []
        self.current = None

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(panes, text=t("mods_library"), padding=6)
        frame, self.tree = scrolled(left, ttk.Treeview, columns=("version", "status"), selectmode="browse", height=6)
        self.tree.heading("#0", text=t("col_name"))
        self.tree.heading("version", text=t("col_version"))
        self.tree.heading("status", text=t("col_status"))
        self.tree.column("#0", width=200)
        self.tree.column("version", width=70, stretch=False)
        self.tree.column("status", width=90, stretch=False)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_selected())
        row = ttk.Frame(left)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(row, text=t("mods_import"), command=self.import_mod).pack(side=tk.LEFT)
        ttk.Button(row, text=t("mods_remove"), command=self.remove_mod).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text=t("open_folder"), command=self.open_library).pack(side=tk.LEFT)
        panes.add(left, weight=2)

        right = ttk.LabelFrame(panes, text=t("mods_details"), padding=10)
        self.title = ttk.Label(right, text="", font=("", 13, "bold"))
        self.title.pack(anchor="w")
        self.meta = ttk.Label(right, text="", foreground=c("gray"))
        self.meta.pack(anchor="w")
        self.description = ttk.Label(right, text=t("mods_none"), wraplength=560, justify=tk.LEFT)
        self.description.pack(anchor="w", fill=tk.X, pady=(8, 4))
        self.contents = ttk.Label(right, text="", foreground=c("gray"))
        self.contents.pack(anchor="w")
        self.check_label = ttk.Label(right, text="", wraplength=560, justify=tk.LEFT)
        self.check_label.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=(10, 8))
        self.install_btn = ttk.Button(buttons, text=t("mod_install"), command=self.install, state=tk.DISABLED)
        self.install_btn.pack(side=tk.LEFT)
        self.uninstall_btn = ttk.Button(buttons, text=t("mod_uninstall"), command=self.uninstall, state=tk.DISABLED)
        self.uninstall_btn.pack(side=tk.LEFT, padx=6)
        self.view_btn = ttk.Button(buttons, text=t("mod_view"), command=self.view, state=tk.DISABLED)
        self.view_btn.pack(side=tk.LEFT)

        cheats = ttk.LabelFrame(right, text=t("mods_cheats"), padding=6)
        cheats.pack(fill=tk.BOTH, expand=True)
        frame, self.cheat_tree = scrolled(cheats, ttk.Treeview, columns=("variable", "value"),
                                          selectmode="extended", height=5)
        self.cheat_tree.heading("#0", text=t("col_label"))
        self.cheat_tree.heading("variable", text=t("col_variable"))
        self.cheat_tree.heading("value", text=t("col_value"))
        self.cheat_tree.column("#0", width=220)
        self.cheat_tree.column("variable", width=140)
        self.cheat_tree.column("value", width=140)
        frame.pack(fill=tk.BOTH, expand=True)
        crow = ttk.Frame(cheats)
        crow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(crow, text=t("cheat_apply_live"), command=self.apply_live).pack(side=tk.LEFT)
        ttk.Button(crow, text=t("cheat_freeze_live"),
                   command=lambda: self.apply_live(freeze=True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(crow, text=t("cheat_apply_save"), command=self.apply_save).pack(side=tk.LEFT)
        panes.add(right, weight=3)

        self.refresh()

    def can_close(self):
        return True

    def set_game(self, game):
        self.game = game
        self.installer = mods.ModInstaller(game)
        self.refresh()

    # -- library ----------------------------------------------------------

    def refresh(self, select=None):
        select = select or (self.current.id if self.current else None)
        self.mod_list = self.library.mods()
        installed = self.installer.installed() if self.installer else {}
        self.tree.delete(*self.tree.get_children())
        for mod in self.mod_list:
            status = t("mod_installed") if mod.id in installed else ""
            self.tree.insert("", tk.END, iid=mod.id, text=mod.name, values=(mod.version, status))
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
        elif self.mod_list:
            self.tree.selection_set(self.mod_list[0].id)
        else:
            self.current = None
            self.show(None)

    def import_mod(self):
        path = filedialog.askopenfilename(title=t("pick_mod_file"), filetypes=[
            (t("filetype_mod"), "*.rsmod *.zip mod.json"), (t("filetype_all"), "*.*")])
        if not path:
            return
        try:
            mod = self.library.add(path)
        except (mods.ModError, OSError) as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        self.app.notebook.select(self)
        self.refresh(select=mod.id)
        self.app.set_status(t("mod_imported", name=mod.name), "green")

    def remove_mod(self):
        if self.current is not None:
            self.library.remove(self.current.id)
            self.current = None
            self.refresh()

    def open_library(self):
        self.library.path.mkdir(parents=True, exist_ok=True)
        open_path(self.library.path)

    # -- details ----------------------------------------------------------

    def show_selected(self):
        sel = self.tree.selection()
        mod = next((m for m in self.mod_list if sel and m.id == sel[0]), None)
        self.current = mod
        self.show(mod)

    def show(self, mod):
        self.cheat_tree.delete(*self.cheat_tree.get_children())
        state = tk.NORMAL if mod is not None else tk.DISABLED
        for b in (self.install_btn, self.uninstall_btn, self.view_btn):
            b.config(state=state)
        if mod is None:
            self.title.config(text="")
            self.meta.config(text="")
            self.description.config(text=t("mods_none"))
            self.contents.config(text="")
            self.check_label.config(text="")
            return
        self.title.config(text=mod.name)
        self.meta.config(text=t("mod_by", version=mod.version or "?", author=mod.author or "?"))
        target = mod.game.get("name") or mod.game.get("save_directory")
        self.description.config(text=(mod.description or "") + ("\n" + t("mod_target", game=target) if target else ""))
        self.contents.config(text=t("mod_contents", scripts=len(mod.scripts), files=len(mod.files),
                                    replacements=len(mod.replacements), cheats=len(mod.cheats)))
        for i, cheat in enumerate(mod.cheats):
            self.cheat_tree.insert("", tk.END, iid=str(i), text=cheat.label,
                                   values=(cheat.name, repr(cheat.value)))
        installed = self.installer is not None and mod.id in self.installer.installed()
        self.uninstall_btn.config(state=tk.NORMAL if installed else tk.DISABLED)
        self.run_check(mod)

    def run_check(self, mod):
        if self.installer is None:
            self.check_label.config(text=t("mod_need_game_check"), foreground=c("gray"))
            self.install_btn.config(state=tk.DISABLED)
            return
        installer = self.installer
        entry = installer.installed().get(mod.id)
        if entry is not None:
            self.check_label.config(text=t("mod_is_installed", date=entry.get("installed", "?")),
                                    foreground=c("green"))
            self.install_btn.config(state=tk.NORMAL)
            return
        self.check_label.config(text=t("mod_checking"), foreground=c("gray"))

        def done(result):
            if self.current is not mod:
                return
            warnings, error = result
            lines = ["⚠ " + str(w) for w in warnings]
            if error is not None:
                lines.append("✖ " + str(error))
                self.install_btn.config(state=tk.DISABLED)
                color = "red"
            else:
                lines.append(t("mod_compatible"))
                self.install_btn.config(state=tk.NORMAL)
                color = "orange" if warnings else "green"
            self.check_label.config(text="\n".join(lines), foreground=c(color))

        self.app.runner.run(lambda: installer.check(mod), done)

    # -- install / uninstall ------------------------------------------------

    def install(self):
        mod = self.current
        if mod is None or self.installer is None:
            messagebox.showinfo(t("app_title"), t("need_game"))
            return
        text = t("mod_confirm_install", name=mod.name, game=self.game.name)
        if mod.runs_code:
            text += "\n\n" + t("mod_code_warning")
        if not messagebox.askyesno(t("app_title"), text, icon="warning" if mod.runs_code else "question"):
            return
        installer = self.installer

        def done(_):
            client = live.LiveGame(self.game.root)
            if client.is_running():
                client.reload()
                self.app.set_status(t("mod_installed_reload", name=mod.name), "green")
            else:
                self.app.set_status(t("mod_installed_msg", name=mod.name), "green")
            self.refresh(select=mod.id)

        def failed(exc):
            messagebox.showerror(t("error"), str(exc))

        self.app.runner.run(lambda: installer.install(mod), done, failed)

    def uninstall(self):
        mod = self.current
        if mod is None or self.installer is None:
            return
        if not messagebox.askyesno(t("app_title"), t("mod_confirm_uninstall", name=mod.name)):
            return
        try:
            failed = self.installer.uninstall(mod.id)
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        if failed:
            messagebox.showwarning(t("app_title"), t("mod_uninstall_failed", scripts=", ".join(failed)))
        self.app.set_status(t("mod_uninstalled", name=mod.name), "green")
        self.refresh(select=mod.id)

    def view(self):
        if self.current is not None:
            ContentsWindow(self, self.current)

    # -- cheats -------------------------------------------------------------

    def selected_cheats(self):
        if self.current is None:
            return []
        return [self.current.cheats[int(i)] for i in self.cheat_tree.selection()]

    def apply_live(self, freeze=False):
        cheats = self.selected_cheats()
        if not cheats:
            messagebox.showinfo(t("app_title"), t("no_cheats_selected"))
            return
        if self.game is None:
            messagebox.showinfo(t("app_title"), t("need_game"))
            return
        try:
            count = mods.apply_cheats_live(self.game, cheats, freeze=freeze)
        except (mods.ModError, OSError, ValueError) as exc:
            messagebox.showinfo(t("app_title"), str(exc))
            return
        self.app.set_status(t("cheats_frozen_live" if freeze else "cheats_applied_live", count=count), "green")

    def apply_save(self):
        cheats = self.selected_cheats()
        if not cheats:
            messagebox.showinfo(t("app_title"), t("no_cheats_selected"))
            return
        dirs = saves.default_save_dirs(self.game)
        entries = saves.list_saves(dirs)
        path = filedialog.askopenfilename(
            title=t("pick_save_file"), filetypes=[(t("filetype_save"), "*.save")],
            initialdir=str(entries[0].path.parent) if entries else (str(dirs[0]) if dirs else None))
        if not path:
            return
        try:
            signed = saves.SaveFile(path).is_signed
            keys = savetoken.load_signing_keys() if signed else []
            if signed and not keys and not messagebox.askyesno(t("app_title"), t("no_key_save"), icon="warning"):
                return
            applied, missing, _ = mods.apply_cheats_to_save(path, cheats, keys=keys)
        except Exception as exc:
            messagebox.showerror(t("error"), str(exc))
            return
        if not applied:
            messagebox.showinfo(t("app_title"), t("cheats_none_applied"))
            return
        msg = t("cheats_applied_save", path=path, applied=", ".join(applied))
        if missing:
            msg += " " + t("cheats_missing", missing=", ".join(missing))
        self.app.set_status(msg, "green" if not missing else "orange")


class ContentsWindow(tk.Toplevel):
    """Read-only view of everything a mod contains, so users can review it first."""

    def __init__(self, master, mod):
        super().__init__(master)
        self.title(t("view_title", name=mod.name))
        self.geometry("820x600")
        frame, text = scrolled(self, tk.Text, wrap="none", font=("Consolas", 10))
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        out = []
        out.append("# " + t("view_files", id=mod.id))
        for path in sorted(mod.files):
            out.append("#   " + path)
        for path in mod.scripts:
            out += ["", "# ===== %s =====" % path, mod.files[path].decode("utf-8", "replace")]
        if mod.replacements:
            out += ["", "# ===== " + t("view_replacements") + " ====="]
            for r in mod.replacements:
                out += ["", "# %s" % r.script, "- " + r.find.replace("\n", "\n- "), "+ " + r.replace.replace("\n", "\n+ ")]
        if mod.cheats:
            out += ["", "# ===== " + t("view_cheats") + " ====="]
            out += ["%s = %r    # %s" % (ch.name, ch.value, ch.label) for ch in mod.cheats]
        text.insert("1.0", "\n".join(out))
        text.config(state=tk.DISABLED)
        ttk.Button(self, text=t("close"), command=self.destroy).pack(pady=(0, 8))
        self.transient(master.winfo_toplevel())
        style_window(self)
