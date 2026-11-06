# Making mods for RenPy Suite

RenPy Suite mods work a bit like Cheat Engine tables. A modder puts their changes for a game into one
file, and other players import that file and install it with a click. Uninstalling undoes everything.

A mod can contain three kinds of things:

| Part | What it does | When it takes effect |
|------|--------------|----------------------|
| **Files** (`game/` folder) | New scripts (`.rpy`) and assets are copied into the game. | Next game start, or right away with the live connection. |
| **Replacements** | Find & replace in the game's own scripts. | Next game start, or right away with the live connection. |
| **Cheats** | Variable values the player applies on demand to the running game or to a save. | Immediately |

## Layout

```
my-mod/
  mod.json
  game/                     optional
    my_mod.rpy              → installed as game/renpy_suite_mods/my-mod/my_mod.rpy
    images/badge.png        → game/renpy_suite_mods/my-mod/images/badge.png
```

Share it as a single file:

```bash
python -m renpy_suite mod-pack my-mod/ my-mod.rsmod
```

A `.rsmod` file is a normal zip, so a zipped folder works too. Players import it with
**Mods → Import mod…**. A `mod.json` or a mod folder can be imported directly as well.

## mod.json

```json
{
  "format": "renpy-suite-mod",
  "format_version": 1,
  "id": "my-mod",
  "name": "My mod",
  "version": "1.0",
  "author": "your name",
  "description": "One or two sentences about what the mod does.",
  "game": { "name": "Some Game", "save_directory": "SomeGame-1234567" },
  "replacements": [
    {
      "script": "script.rpy",
      "find": "    if money >= 500:",
      "replace": "    if True:"
    }
  ],
  "cheats": [
    { "name": "money", "value": 99999, "label": "Lots of money", "description": "optional" },
    { "name": "met_alice", "value": true, "label": "Unlock Alice's route" }
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `format`, `format_version` | yes | Always `"renpy-suite-mod"` and `1`. |
| `id` | yes | Lowercase letters, digits, `-`, `_`, `.`. Must be unique. It is also the install folder name. |
| `name` | yes | Shown in the mod library. |
| `version`, `author`, `description` | no | Shown to players. |
| `game` | no | `name` and/or `save_directory` of the target game. A mismatch shows a warning but doesn't block installing. The **Game** tab shows both values for any game. |
| `replacements` | no | See below. |
| `cheats` | no | See below. |

### Replacements

Each replacement changes **every** occurrence of `find` in `script` to `replace`.

- `script` is the path inside the game's `game/` folder, with or without extension (`script.rpy`,
  `chapters/day1`). Scripts inside `.rpa` archives work too.
- `find` must match the script text **exactly**, including indentation. For games that ship only
  compiled scripts, that text is RenPy Suite's decompiled output. To find it, open the script in the
  **Scripts** tab and copy the line from there.
- If any `find` text is missing, the mod is **not** installed at all, so a game is never left half-modded.
  The Mods tab shows this check before you click Install.
- Keep `find` short but unique, typically a single line.
- Uninstalling restores the scripts. If the player edited the same script afterwards, only the mod's
  replacements are reverted.

Script changes work like editing a script in the Scripts tab. Ren'Py recompiles the script at the next
start, and existing saves keep working.

### Cheats

A cheat sets a store variable (`name`) to a JSON value: a number, text, `true`/`false`, `null`, or a
list/object of those. Players select cheats and apply them

- **to the running game**, which needs the *Live connection* option of the developer patch, or
- **to a save file**. The save is backed up and re-signed automatically.

Cheats only change variables that already exist in the game or save, so a cheat for a variable the game
doesn't have does nothing.

Tip: to make a change that happens on its own instead of on demand, use a script file:

```renpy
# game/my_mod.rpy
init 999 python:
    config.allow_skipping = True

    def my_mod_after_load():
        # Runs after every load. Prefix names with your mod id to avoid clashes.
        if hasattr(store, "money"):
            store.money = max(store.money, 1000)

    config.after_load_callbacks.append(my_mod_after_load)
```

Don't define labels that the game might already have (such as `after_load` or `splashscreen`). Ren'Py
refuses to start when a label is defined twice.

## Writing good mods

- Use a high init priority (`init 999 python:`) so your settings win over the game's own.
- Reference your assets by their installed path, e.g. `"renpy_suite_mods/my-mod/images/badge.png"`.
- Prefer new `.rpy` files over replacements when possible. They don't depend on exact script text and
  survive game updates better.
- Test with the live connection: install, change, and the running game reloads.

## Security

Scripts and replacements run inside the game with the same rights as the game, which means full
access to the player's computer. RenPy Suite therefore

- shows a clear warning before installing a mod that contains code,
- lets players read every file and change first (**View contents**), and
- never runs anything from a mod itself. Cheats are plain values, and archive paths are sanitised.

Only install mods from people you trust, just as with any other game mod.

See [`examples/quality-of-life`](../examples/quality-of-life) for a complete example.
