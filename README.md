<p align="center"><img src="renpy_suite/assets/icon-128.png" width="112" alt="RenPy Suite icon"></p>

# RenPy Suite

An all-in-one toolkit for inspecting and modding [Ren'Py](https://www.renpy.org/) games:
unpack and create archives, decompile scripts, edit save games and persistent data,
and switch on the developer console. It comes with a GUI and a command-line interface.

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

- **Pure Python standard library.** No `pip install` needed.
- **Safe by design.** Ren'Py files are Python pickles, and RenPy Suite never executes code from them (see [Safety](#safety)).
- **Multilingual UI.** It ships in English and German and follows your system language unless you pick one in the settings.
- **Light and dark mode.** It follows the system theme or a choice in the settings, including a dark title bar on Windows.

---

## Features

| Tool | What it does |
|------|--------------|
| **Game overview** | Detects the Ren'Py version, Python 2/3 runtime, archives, scripts, the game's save directory name and all of its save folders. |
| **Archive tool** | Browse `.rpa` archives with a filter, extract everything or only selected files, and pack a folder into a new RPA‑3.0 archive. Supports RPA‑3.x (including multi-key variants such as RPA‑3.2), RPA‑2.0 and RPA‑1.0 (`.rpi`). |
| **Decompiler** | Turns compiled `.rpyc` scripts back into readable `.rpy`. It reads loose files and scripts inside archives, and can export everything in one batch. |
| **Script editor** | Edit any script right in the preview and save it into the game with Ctrl+S, e.g. to flip a boolean. The game uses your version on its next start. **Restore original** undoes it. |
| **Save editor** | Finds every save on the machine and opens the most recent one with one click. Shows the screenshot and save name, browses all variables as a tree (including nested objects, lists and dicts), and edits values. |
| **Persistent editor** | Edits `persistent` data such as gallery and ending unlocks, or seen-text flags. |
| **Save signing** | Ren'Py 8.1+ signs saves and persistent data. Edited files are re-signed with **your own** local key, so the game accepts them without warnings. |
| **Developer patch** | One click enables developer mode, the console (Shift+O), always-allowed skipping and rollback. Removing it is just as easy. |
| **Live connection** | Change variables of the *running* game instantly, and have the game reload automatically when you save an edited script. |
| **Value search** | Find the variable behind a value (money, affection …) with first/next scans, like Cheat Engine, then set or freeze it. |
| **Mods** | Share and import mods, a bit like Cheat Engine tables. One `.rsmod` file can carry new scripts, script changes and one-click cheats. Uninstalling is clean. |
| **CLI** | Every feature is scriptable from the command line. |

## Requirements

- Python **3.8 or newer**, from [python.org](https://www.python.org/downloads/).
- Tkinter for the GUI. It is included with the python.org installers for Windows and macOS. On Debian/Ubuntu: `sudo apt install python3-tk`.

## Getting started

```bash
git clone https://github.com/<your-name>/renpy-suite.git
cd renpy-suite
python -m renpy_suite
```

On Windows you can also double-click **`RenPySuite.pyw`** to start the GUI without a console window.

Then click **Choose game folder…** and select the folder that contains the game's `.exe` (or its `game` folder).

## Using the GUI

The menu bar in the top-left corner holds **File** (choose a game with Ctrl+O, reload with F5, open
**Settings…**), **Mods** (import a mod, open the mod library, mod format) and **Help** (documentation,
GitHub page, **About**).

### Settings
**File → Settings…** lets you choose the **language** (system default, English or Deutsch) and the **theme**
(system default, light or dark). Changes apply immediately. **Save archive files to** sets the folder used
by right-click → *Save to …* in the Archives tab. Leave it empty to be asked every time. Settings are stored in
`%APPDATA%\RenPySuite\settings.json` (Windows), `~/Library/Application Support/RenPySuite/` (macOS) or
`~/.config/renpy-suite/` (Linux).

### Game
Shows what was detected about the game. The **Developer patch** section writes a small file,
`game/zz_renpy_suite_patch.rpy`, that enables the selected options the next time the game starts:

| Option | Effect |
|--------|--------|
| Developer mode | `config.developer = True`: Shift+D developer menu, Shift+R reload, Shift+I style inspector |
| Developer console | `config.console = True`: Shift+O opens a Python console inside the game |
| Always allow skipping | `config.allow_skipping` / `config.fast_skipping` |
| Rollback | `config.rollback_enabled` with a long rollback history |
| Live connection | Lets RenPy Suite talk to the running game (see below). Turns on developer mode as well. |

**Remove patch** deletes the file and its compiled `.rpyc` again.

#### Live connection
With this option the game checks a folder (`<game folder>/renpy_suite_live/`) a few times per second. Through
it, RenPy Suite can:

- **Change variables instantly.** In the Save Editor, click **Running game** to see the game's current
  variables. Edits take effect immediately, with no reload or save needed. To keep them, save inside the game.
- **Freeze values**, like in Cheat Engine. Select a variable and click **Freeze / unfreeze** (or
  **Freeze in running game** for mod cheats). The game keeps the variable at that value, even if it tries
  to change it, until you unfreeze it. Freezes survive reloads and restarts, and are marked with ❄.
- **Reload after saving a script.** When you save an edited script in the Scripts tab, the running game
  reloads, just like pressing Shift+R. Ren'Py saves your position, recompiles the changed script and continues
  where you were.

The connection only carries plain values (numbers, text, true/false, None, lists and dicts) and never code. It
can only replace variables that already exist and already hold such a value. Removing the patch also deletes
the folder.

> **Tip:** A reload keeps your current game state. Changing `default x = False` to `True` in a script
> therefore does **not** affect a game that is already running or saved, because the variable already exists.
> Change values of a running game in the Save Editor (**Running game**), and use script edits for logic and
> `define` values.

### Archives
All archives of the selected game are listed on the left, and you can add others with **Add…**.
Select an archive to see its contents, filter by name, then use **Extract selected files** or **Extract all archives**.

To grab just a few files, such as a single image:

- **Click** a PNG or GIF to see a preview with its size next to the list. Other formats such as JPG and WebP
  have no built-in preview, because that would need an extra library.
- **Double-click** a file to open it in your default app (images, audio, video, text, fonts).
- **Right-click** → **Save as…** to pick a location, or **Save to “…”** to save straight into the folder
  set in the settings. **Ctrl+S** does the same for the selection. Files are saved by name, and an existing
  file is never overwritten: a second `bg.png` becomes `bg (2).png`.
- **Copy name** copies the archive path, e.g. for use in a mod script.

By default, files are extracted to `<game folder>/extracted/<archive name>`, **outside** the game's own
`game` directory. Extracting scripts into `game/` would make Ren'Py load them twice and break the game.

**Create archive from folder…** packs any folder into an RPA‑3.0 archive that Ren'Py can load.

### Scripts (decompiler & editor)
Lists every script: compiled `.rpyc` (loose or inside archives) and plain `.rpy`. Click one to open its
(decompiled) source in the editor. Use **Find** (Ctrl+F) to search the open script, or **Search all
scripts…** (Ctrl+Shift+F) to search every script of the game at once, e.g. where `affection` is changed.
Plain text and regular expressions are supported. Double-click a result to jump to the line in the editor.

To change the game, edit the code (for example `default unlocked_all = False` → `True`) and press
**Save to game** (Ctrl+S). The game uses your version the next time it starts. With the
[live connection](#live-connection), a running game reloads right away instead. Edited scripts are marked with ✎.

What happens behind the scenes:
- Your text is saved as `game/<script>.rpy` next to the compiled `.rpyc`. Ren'Py notices the source changed
  and recompiles it at startup. It reuses statement names from the old `.rpyc`, so **existing saves keep working**.
- If the script was inside an archive, Ren'Py would otherwise load both copies (duplicate labels). So the
  entry is removed from the archive's *index*. The data itself stays in the archive, and the original
  `.rpyc` is placed next to your `.rpy`.
- Originals (scripts and archive indexes) are backed up to `<game folder>/renpy_suite_backup/`.
  **Restore original** puts everything back exactly as it was.

Because decompilation is best-effort, check a script you edit for `# [renpy-suite]` comments. If the game
shows an error after your change, use **Restore original**.

**Export translations…** creates the basis for a fan translation:

1. Enter a language name (e.g. `german`) and export. You get `dialogue.csv`, with every dialogue line
   and menu choice, plus Ren'Py translation files in `tl/german/`.
2. Translate the `translation` column of the CSV in Excel, LibreOffice or Google Sheets.
3. Export again with **Use translations from CSV** to fill the translations into the `tl` files.
4. Copy the `tl` folder into the game's `game` folder, or choose **write directly into the game**. Then
   pick the language in the game's language menu, or run `renpy.change_language("german")` in the
   developer console.

Lines from very old games (before Ren'Py 6.15) have no translation IDs. They appear in the CSV but not in
the `tl` files.

**Decompile all** writes `.rpy` files to `<game folder>/decompiled`, keeping the folder structure. These are
read-only copies for browsing and searching, and the game doesn't use them.

### Save Editor
1. Click **Open latest save**, or pick any save from the list. Without a game selected, saves of *all*
   Ren'Py games on the computer are listed.
2. Use the filter to find a variable (e.g. `money`, `affection`). Ren'Py's internal `_…` variables are hidden by default.
3. Double-click a value to edit it. Text, numbers, `True`/`False` and `None` can be edited directly. Expand
   lists, dicts and objects to edit what is inside them.
   To enter any Python literal (or change a value's type), start with `=`, e.g. `=[1, 2, 3]` or `="text"`.
4. Click **Save changes**. A timestamped backup (`<file>.<date>-<time>.bak`) is created next to the original.

**Persistent data** opens the game's `persistent` file in the same editor.

> **Close the game first.** Ren'Py rewrites its persistent data when it quits and would overwrite your changes.

### Value search
Find the variable behind a number on screen, the same way Cheat Engine's scanner works:

1. Pick where snapshots come from: the **running game** (live connection), the **newest save**, or a save
   you choose.
2. **First scan.** Optionally keep only values *equal to* what you see, e.g. your money `100`.
3. Change the value in the game, e.g. buy something. If you scan saves, save the game now.
4. **Next scan** with the matching filter: *decreased*, *increased*, *changed*, *unchanged* or
   *equal to*. Repeat until only a few results are left.
5. **Set in running game…** or **Freeze in running game…** on a result.

It looks inside lists, dicts and objects too (`player.hp`, `inventory[2]`). Results inside objects can be
copied by name and edited in the Save Editor.

### Mods
Mods are shared as `.rsmod` files, much like Cheat Engine tables. **Mods → Import mod…** adds one to your
mod library, which is kept per user, so you can install it into any game. When you select a mod you see:

- what it contains (scripts, script changes, cheats) and who made it,
- whether it can be installed into the selected game. Script changes are checked before anything is written,
  so a game is never left half-modded.
- **View contents** to read every file and change. Mods with code show a warning before installing,
  because mod code runs inside the game.

**Install** copies the mod's files to `game/renpy_suite_mods/<mod id>/` and applies its script changes,
with backups. With the live connection, a running game reloads right away. **Uninstall** undoes
everything.

**Cheats** are one-click variable values. Select them and click **Apply to running game** (needs the live
connection) or **Apply to save…** (backed up and re-signed).

Want to make mods? See **[docs/MODDING.md](docs/MODDING.md)** and the example in
[`examples/quality-of-life`](examples/quality-of-life).

## Command line

Run `python -m renpy_suite <command> --help` for all options.

```bash
python -m renpy_suite                       # start the GUI
python -m renpy_suite gui "C:/Games/MyGame" # start the GUI with a game opened

python -m renpy_suite info "C:/Games/MyGame"

python -m renpy_suite list   game/images.rpa
python -m renpy_suite unpack game/*.rpa                 # -> <game>/extracted/<archive>
python -m renpy_suite unpack game/images.rpa -o out/
python -m renpy_suite pack   my_mod_folder/ my_mod.rpa

python -m renpy_suite decompile "C:/Games/MyGame"       # whole game, incl. archives
python -m renpy_suite decompile script.rpyc -o out/ --overwrite

python -m renpy_suite saves "C:/Games/MyGame" --latest  # path of the newest save
python -m renpy_suite show  path/to/1-1-LT1.save --filter money
python -m renpy_suite set   path/to/1-1-LT1.save money 99999
python -m renpy_suite set   path/to/persistent gallery_unlocked true

python -m renpy_suite devmode "C:/Games/MyGame" --options developer,console,skipping,rollback
python -m renpy_suite devmode "C:/Games/MyGame" --disable

python -m renpy_suite devmode "C:/Games/MyGame" --options live   # then start the game
python -m renpy_suite live "C:/Games/MyGame" --filter affection  # show variables of the running game
python -m renpy_suite live "C:/Games/MyGame" --set money 5000
python -m renpy_suite live "C:/Games/MyGame" --freeze money 5000   # --unfreeze money
python -m renpy_suite live "C:/Games/MyGame" --reload

python -m renpy_suite translate "C:/Games/MyGame" --language german            # CSV + tl files
python -m renpy_suite translate "C:/Games/MyGame" --language german --from-csv dialogue.csv --into-game

python -m renpy_suite mod-pack examples/quality-of-life qol.rsmod  # share a mod folder as one file
python -m renpy_suite mod-info qol.rsmod
python -m renpy_suite mod-install "C:/Games/MyGame" qol.rsmod --yes
python -m renpy_suite mod-list "C:/Games/MyGame"
python -m renpy_suite mod-uninstall "C:/Games/MyGame" quality-of-life
```

Use `--lang en` or `--lang de` (or the `RENPY_SUITE_LANG` environment variable) to override the interface language.

## Where saves are stored

Ren'Py keeps saves in two places and syncs between them:

| Platform | Location |
|----------|----------|
| All | `<game folder>/game/saves/` |
| Windows | `%APPDATA%\RenPy\<save directory>\` |
| macOS | `~/Library/RenPy/<save directory>/` |
| Linux | `~/.renpy/<save directory>/` |

`<save directory>` is the game's `config.save_directory`. RenPy Suite reads it from the game's scripts,
including compiled and archived ones.

## Safety

- **No code execution.** Ren'Py data files are Python pickles, which can run arbitrary code when loaded the normal way.
  RenPy Suite uses its own unpickler. It never imports or calls anything from a file. Every referenced class
  becomes an inert placeholder that records its data so it can be written back unchanged. You can open saves
  from strangers safely.
- **Backups.** Every save or persistent write first copies the original to a timestamped `.bak` file.
- **Your own key only.** Re-signing uses the signing key that Ren'Py already created on *your* computer
  (`<RenPy dir>/tokens/security_keys.txt`). RenPy Suite never creates, exports or changes keys. If no key is
  found, you are warned before saving.
- **The game folder is only changed on request.** Extraction and decompilation go to separate folders. The
  game itself is only changed by the developer patch and by **Save to game** in the script editor. Both can
  be undone with one click.

## Supported formats

| Format | Versions |
|--------|----------|
| Archives | RPA‑1.0 (`.rpi` + `.rpa`), RPA‑2.0, RPA‑3.0, RPA‑3.x with multiple key fields |
| Compiled scripts | `RENPY RPC2` (Ren'Py 6.18 – 8.x) and legacy zlib `.rpyc` |
| Saves | Ren'Py 6 – 8 (`.save` zip with pickled log), signed or unsigned |
| Persistent | zlib-compressed pickle, signed or unsigned |
| Games | Python 2 (Ren'Py ≤ 7) and Python 3 (Ren'Py 8) |

## Limitations

- **The decompiler is best-effort.** It covers labels, dialogue, menus, control flow, Python blocks,
  define/default, images, show/scene/hide with ATL, transforms, styles, translations, user statements and
  screen language (SL2). It does not preserve comments, formatting or line numbers. Anything it doesn't
  understand is kept as a `# [renpy-suite] …` comment instead of being dropped. Legacy (pre-SL2) screens are
  not decompiled.
- **Obfuscated games are not supported.** Some games deliberately encrypt or alter their archives or scripts.
  These are not handled.
- **Python 2 games.** Strings from Python 2 games are kept as raw bytes, so they are written back exactly. In
  the editor they show the type `bytes`, and new text is stored as UTF‑8.
- If a signed save is edited on a computer without a Ren'Py signing key, the game asks once whether you trust
  the file. Answer *Yes*. Edited **persistent** data cannot be loaded at all in that case.

## Project layout

```
renpy_suite/
  rpa.py          archive reading / writing
  rpyc.py         .rpyc decompiler
  scriptedit.py   saving edited scripts into a game, with backup/restore
  live.py         live connection to a running game (in-game bridge + client)
  mods.py         mod format, mod library, installer and cheats
  scan.py         Cheat-Engine style value search over snapshots
  search.py       full-text search over all scripts
  translate.py    dialogue export (CSV + Ren'Py tl files)
  saves.py        save + persistent files
  savetoken.py    Ren'Py 8.1+ signatures (pure-Python ECDSA P-256)
  stubpickle.py   safe, round-trip capable unpickler
  values.py       browsing / editing unpickled values
  game.py         game detection, developer patch
  locations.py    platform save locations
  i18n.py         UI translations
  settings.py     persistent user settings
  cli.py          command-line interface
  gui/            Tkinter user interface (theme.py: light/dark themes)
  assets/         application icon
docs/MODDING.md   how to make mods
examples/         example mod
tests/            unit and end-to-end tests (stdlib unittest)
tools/make_icon.py  draws the icon from code (original artwork, no third-party rights)
RenPySuite.pyw    double-click launcher
```

## Development

```bash
python -m unittest discover -s tests
```

The tests build realistic fixtures (archives, compiled scripts, signed saves) from look-alike Ren'Py
classes, so Ren'Py itself is not needed.

### Adding a language
Open `renpy_suite/i18n.py`, copy the `"en"` block, translate the values and add it under the language's
two-letter code (e.g. `"fr"`). The tests check that every language has all keys and placeholders.

## Disclaimer

RenPy Suite is meant for personal modding, translation, accessibility, learning and recovering your own
data. Respect the licenses and terms of the games you open, and don't redistribute other people's
assets without permission. This project is not affiliated with or endorsed by the Ren'Py project.

## License

[MIT](LICENSE)
