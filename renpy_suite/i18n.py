"""User-interface translations. The language follows the operating system.

Override with the ``RENPY_SUITE_LANG`` environment variable or ``--lang``.
To add a language, copy the ``"en"`` block, translate the values and add it
to ``STRINGS`` under its two-letter code.
"""

from __future__ import annotations

import locale
import os
import sys

STRINGS = {
    "en": {
        "app_title": "RenPy Suite",
        "game_label": "Game:",
        "no_game": "No game selected — choose a game folder to get started.",
        "choose_game": "Choose game folder…",
        "reload": "Reload",
        "loading_game": "Reading game…",
        "game_loaded": "Loaded {name}.",
        "not_a_game": "No Ren'Py game found in this folder (it needs a 'game' subfolder).",
        "error": "Error",
        "done": "Done",
        "cancel": "Cancel",
        "cancelled": "Cancelled.",
        "browse": "Browse…",
        "open_folder": "Open folder",
        "working": "Working…",

        "tab_game": "Game",
        "tab_archives": "Archives",
        "tab_decompiler": "Decompiler",
        "tab_saves": "Save Editor",

        "info_frame": " Game information ",
        "info_name": "Name",
        "info_root": "Folder",
        "info_version": "Ren'Py version",
        "info_python": "Python",
        "info_archives": "Archives (.rpa)",
        "info_rpyc": "Compiled scripts (.rpyc)",
        "info_rpy": "Script sources (.rpy)",
        "info_savedir": "Save directory name",
        "info_savefolders": "Save folders",
        "unknown": "unknown",
        "none_found": "none found",
        "open_game_folder": "Open game folder",
        "open_save_folder": "Open save folder",
        "patch_frame": " Developer patch ",
        "patch_intro": "Writes a small script into the game folder. Takes effect the next time the game starts.",
        "opt_developer": "Developer mode (Shift+D menu, Shift+R reload, Shift+I inspector)",
        "opt_console": "Developer console (Shift+O)",
        "opt_skipping": "Always allow skipping, including fast skip (Ctrl / Tab / >)",
        "opt_rollback": "Enable rollback (mouse wheel / PageUp) with a long history",
        "patch_apply": "Apply patch",
        "patch_remove": "Remove patch",
        "patch_installed": "Patch installed: {options}",
        "patch_not_installed": "Patch not installed.",
        "patch_applied": "Patch written to {path}.",
        "patch_removed": "Patch removed.",
        "need_game": "Please choose a game folder first.",

        "archives_frame": " Archives ",
        "add_archives": "Add…",
        "remove_selected": "Remove",
        "contents_frame": " Contents ",
        "filter": "Filter:",
        "col_name": "Name",
        "col_size": "Size",
        "archive_summary": "{version} · {count} files · {size}",
        "output_frame": " Output folder ",
        "output_hint_archives": "Leave empty to extract to <game>/extracted/<archive name> (outside the game's own folder).",
        "extract_selected": "Extract selected files",
        "extract_all": "Extract all archives",
        "pack_folder": "Create archive from folder…",
        "pick_archive_files": "Select Ren'Py archives",
        "filetype_rpa": "Ren'Py archive",
        "filetype_all": "All files",
        "extracting": "Extracting {name}",
        "extract_done": "Extracted {count} files.",
        "no_archive_selected": "Select an archive first.",
        "no_files_selected": "Select one or more files in the contents list first.",
        "no_archives": "No archives to extract.",
        "pack_source": "Choose the folder to pack",
        "pack_target": "Save archive as",
        "packing": "Packing {name}",
        "pack_done": "Created {path} with {count} files.",
        "archive_error": "Could not read {name}: {error}",

        "scripts_frame": " Compiled scripts ",
        "include_archived": "Include scripts inside archives",
        "add_rpyc": "Add .rpyc files…",
        "pick_rpyc_files": "Select compiled Ren'Py scripts",
        "filetype_rpyc": "Compiled Ren'Py script",
        "preview_frame": " Preview ",
        "save_preview": "Save as…",
        "overwrite": "Overwrite existing .rpy files",
        "output_hint_decompile": "Leave empty to write to <game>/decompiled. Never write into the game folder: the game would load the decompiled copies.",
        "decompile_all": "Decompile all",
        "decompiling": "Decompiling",
        "decompile_done": "Wrote {written} files, skipped {skipped} existing, {errors} errors.",
        "decompile_errors": "Some scripts could not be decompiled:",
        "no_scripts": "No compiled scripts found.",
        "need_output": "Please choose an output folder.",
        "preview_failed": "# Could not decompile this file:\n# {error}",

        "saves_frame": " Saves ",
        "refresh": "Refresh",
        "open_latest": "Open latest save",
        "open_save_file": "Open file…",
        "open_persistent": "Persistent data",
        "col_slot": "Slot",
        "col_modified": "Modified",
        "col_folder": "Folder",
        "scanning_all": "Showing saves of all Ren'Py games on this computer.",
        "scanning_game": "Showing saves of {name}.",
        "no_saves": "No saves found.",
        "no_persistent": "No persistent data found.",
        "variables_frame": " Variables ",
        "hide_internal": "Hide Ren'Py internals (_…)",
        "col_variable": "Variable",
        "col_type": "Type",
        "col_value": "Value",
        "edit_value": "Edit value…",
        "save_changes": "Save changes",
        "revert": "Revert",
        "loading_save": "Loading {name}…",
        "save_header": "{name}   ·   Ren'Py {version}   ·   {signed}",
        "persistent_header": "Persistent data   ·   {signed}",
        "signed": "signed",
        "unsigned": "not signed",
        "edit_title": "Edit {name}",
        "edit_prompt": "New value for {name} ({type}).\nStart with = to enter a Python literal, e.g. =[1, 2] or =None.",
        "not_editable": "Only text, numbers, true/false and None can be edited. Expand containers to edit their contents.",
        "invalid_value": "Invalid value: {error}",
        "unsaved_changes": "Discard unsaved changes?",
        "pick_save_file": "Select a save file",
        "filetype_save": "Ren'Py save",
        "close_game_hint": "Close the game before saving changes — it overwrites persistent data when it quits.",
        "no_key_save": "This save is signed, but no signing key was found on this computer. The game will ask whether you trust the edited save. Continue?",
        "no_key_persistent": "This persistent file is signed, but no signing key was found on this computer. Ren'Py would discard the edited file. Continue anyway?",
        "write_done": "Saved. Backup: {backup}",
        "write_done_signed": "Saved and re-signed. Backup: {backup}",
        "nothing_open": "Open a save first.",
        "screenshot_none": "(no screenshot)",
    },
    "de": {
        "app_title": "RenPy Suite",
        "game_label": "Spiel:",
        "no_game": "Kein Spiel gewählt — wähle einen Spielordner, um loszulegen.",
        "choose_game": "Spielordner wählen…",
        "reload": "Neu laden",
        "loading_game": "Spiel wird gelesen…",
        "game_loaded": "{name} geladen.",
        "not_a_game": "In diesem Ordner wurde kein Ren'Py-Spiel gefunden (es braucht einen Unterordner 'game').",
        "error": "Fehler",
        "done": "Fertig",
        "cancel": "Abbrechen",
        "cancelled": "Abgebrochen.",
        "browse": "Durchsuchen…",
        "open_folder": "Ordner öffnen",
        "working": "Arbeite…",

        "tab_game": "Spiel",
        "tab_archives": "Archive",
        "tab_decompiler": "Decompiler",
        "tab_saves": "Spielstand-Editor",

        "info_frame": " Spielinformationen ",
        "info_name": "Name",
        "info_root": "Ordner",
        "info_version": "Ren'Py-Version",
        "info_python": "Python",
        "info_archives": "Archive (.rpa)",
        "info_rpyc": "Kompilierte Skripte (.rpyc)",
        "info_rpy": "Skript-Quellen (.rpy)",
        "info_savedir": "Name des Speicherordners",
        "info_savefolders": "Speicherordner",
        "unknown": "unbekannt",
        "none_found": "keine gefunden",
        "open_game_folder": "Spielordner öffnen",
        "open_save_folder": "Speicherordner öffnen",
        "patch_frame": " Entwickler-Patch ",
        "patch_intro": "Legt ein kleines Skript im Spielordner an. Wirkt beim nächsten Spielstart.",
        "opt_developer": "Entwicklermodus (Shift+D Menü, Shift+R Neu laden, Shift+I Inspektor)",
        "opt_console": "Entwicklerkonsole (Shift+O)",
        "opt_skipping": "Überspringen immer erlauben, inkl. Schnellvorlauf (Strg / Tab / >)",
        "opt_rollback": "Zurückspulen aktivieren (Mausrad / Bild↑) mit langem Verlauf",
        "patch_apply": "Patch anwenden",
        "patch_remove": "Patch entfernen",
        "patch_installed": "Patch installiert: {options}",
        "patch_not_installed": "Patch nicht installiert.",
        "patch_applied": "Patch geschrieben nach {path}.",
        "patch_removed": "Patch entfernt.",
        "need_game": "Bitte zuerst einen Spielordner wählen.",

        "archives_frame": " Archive ",
        "add_archives": "Hinzufügen…",
        "remove_selected": "Entfernen",
        "contents_frame": " Inhalt ",
        "filter": "Filter:",
        "col_name": "Name",
        "col_size": "Größe",
        "archive_summary": "{version} · {count} Dateien · {size}",
        "output_frame": " Ausgabeordner ",
        "output_hint_archives": "Leer lassen = Entpacken nach <Spiel>/extracted/<Archivname> (außerhalb des Spielordners).",
        "extract_selected": "Ausgewählte Dateien entpacken",
        "extract_all": "Alle Archive entpacken",
        "pack_folder": "Archiv aus Ordner erstellen…",
        "pick_archive_files": "Ren'Py-Archive auswählen",
        "filetype_rpa": "Ren'Py-Archiv",
        "filetype_all": "Alle Dateien",
        "extracting": "Entpacke {name}",
        "extract_done": "{count} Dateien entpackt.",
        "no_archive_selected": "Bitte zuerst ein Archiv auswählen.",
        "no_files_selected": "Bitte zuerst Dateien in der Inhaltsliste auswählen.",
        "no_archives": "Keine Archive zum Entpacken.",
        "pack_source": "Ordner zum Packen wählen",
        "pack_target": "Archiv speichern unter",
        "packing": "Packe {name}",
        "pack_done": "{path} mit {count} Dateien erstellt.",
        "archive_error": "{name} konnte nicht gelesen werden: {error}",

        "scripts_frame": " Kompilierte Skripte ",
        "include_archived": "Skripte in Archiven einbeziehen",
        "add_rpyc": ".rpyc-Dateien hinzufügen…",
        "pick_rpyc_files": "Kompilierte Ren'Py-Skripte auswählen",
        "filetype_rpyc": "Kompiliertes Ren'Py-Skript",
        "preview_frame": " Vorschau ",
        "save_preview": "Speichern unter…",
        "overwrite": "Vorhandene .rpy-Dateien überschreiben",
        "output_hint_decompile": "Leer lassen = Ausgabe nach <Spiel>/decompiled. Niemals in den Spielordner schreiben: Das Spiel würde die dekompilierten Kopien laden.",
        "decompile_all": "Alle dekompilieren",
        "decompiling": "Dekompiliere",
        "decompile_done": "{written} Dateien geschrieben, {skipped} vorhandene übersprungen, {errors} Fehler.",
        "decompile_errors": "Einige Skripte konnten nicht dekompiliert werden:",
        "no_scripts": "Keine kompilierten Skripte gefunden.",
        "need_output": "Bitte einen Ausgabeordner wählen.",
        "preview_failed": "# Diese Datei konnte nicht dekompiliert werden:\n# {error}",

        "saves_frame": " Spielstände ",
        "refresh": "Aktualisieren",
        "open_latest": "Neuesten Spielstand öffnen",
        "open_save_file": "Datei öffnen…",
        "open_persistent": "Persistente Daten",
        "col_slot": "Platz",
        "col_modified": "Geändert",
        "col_folder": "Ordner",
        "scanning_all": "Zeige Spielstände aller Ren'Py-Spiele auf diesem Computer.",
        "scanning_game": "Zeige Spielstände von {name}.",
        "no_saves": "Keine Spielstände gefunden.",
        "no_persistent": "Keine persistenten Daten gefunden.",
        "variables_frame": " Variablen ",
        "hide_internal": "Ren'Py-Interna ausblenden (_…)",
        "col_variable": "Variable",
        "col_type": "Typ",
        "col_value": "Wert",
        "edit_value": "Wert bearbeiten…",
        "save_changes": "Änderungen speichern",
        "revert": "Verwerfen",
        "loading_save": "Lade {name}…",
        "save_header": "{name}   ·   Ren'Py {version}   ·   {signed}",
        "persistent_header": "Persistente Daten   ·   {signed}",
        "signed": "signiert",
        "unsigned": "nicht signiert",
        "edit_title": "{name} bearbeiten",
        "edit_prompt": "Neuer Wert für {name} ({type}).\nMit = beginnen, um ein Python-Literal einzugeben, z. B. =[1, 2] oder =None.",
        "not_editable": "Nur Text, Zahlen, true/false und None sind bearbeitbar. Container aufklappen, um ihren Inhalt zu bearbeiten.",
        "invalid_value": "Ungültiger Wert: {error}",
        "unsaved_changes": "Ungespeicherte Änderungen verwerfen?",
        "pick_save_file": "Spielstand auswählen",
        "filetype_save": "Ren'Py-Spielstand",
        "close_game_hint": "Spiel vor dem Speichern schließen — es überschreibt persistente Daten beim Beenden.",
        "no_key_save": "Dieser Spielstand ist signiert, aber auf diesem Computer wurde kein Signaturschlüssel gefunden. Das Spiel fragt dann, ob du dem bearbeiteten Spielstand vertraust. Fortfahren?",
        "no_key_persistent": "Diese persistente Datei ist signiert, aber auf diesem Computer wurde kein Signaturschlüssel gefunden. Ren'Py würde die bearbeitete Datei verwerfen. Trotzdem fortfahren?",
        "write_done": "Gespeichert. Sicherung: {backup}",
        "write_done_signed": "Gespeichert und neu signiert. Sicherung: {backup}",
        "nothing_open": "Bitte zuerst einen Spielstand öffnen.",
        "screenshot_none": "(kein Screenshot)",
    },
}


def detect_language() -> str:
    candidates = [os.environ.get("RENPY_SUITE_LANG", "")]
    if sys.platform == "win32":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            candidates.append(locale.windows_locale.get(lang_id, ""))
        except (AttributeError, OSError):
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        candidates.append(os.environ.get(var, ""))
    try:
        candidates.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    for c in candidates:
        code = c.replace("-", "_").split("_")[0].split(":")[0].lower()
        if code in STRINGS:
            return code
    return "en"


_language = detect_language()


def set_language(code: str):
    global _language
    if code in STRINGS:
        _language = code


def t(key: str, **kwargs) -> str:
    text = STRINGS[_language].get(key) or STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
