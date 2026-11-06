"""Command-line interface. Run without arguments to start the GUI."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__, game, i18n, live, mods, rpa, rpyc, saves, savetoken, values


def _progress(prefix):
    def cb(done, total, name):
        if name:
            print("\r%s [%d/%d] %s" % (prefix, done + 1, total, name[-60:].ljust(60)), end="", flush=True)
        else:
            print("\r%s [%d/%d]%s" % (prefix, done, total, " " * 61))
    return cb


def cmd_gui(args):
    from .gui import run
    run(args.game, args.lang)


def cmd_info(args):
    g = game.GameInfo.load(args.game)
    print("Name:            ", g.name)
    print("Folder:          ", g.root)
    print("Ren'Py version:  ", g.renpy_version or "unknown")
    print("Python:          ", g.python or "unknown")
    print("Archives:        ", len(g.archives))
    print("Compiled scripts:", len(g.rpyc_files))
    print("Script sources:  ", len(g.rpy_files))
    print("Save directory:  ", g.save_directory or "unknown")
    for d in g.save_dirs():
        print("Save folder:     ", d)
    status = game.patch_status(g.game_dir)
    print("Developer patch: ", ", ".join(sorted(status)) if status else "not installed")


def cmd_list(args):
    a = rpa.RPAArchive(args.archive)
    print("# %s, %d files" % (a.version, len(a.index)))
    for name in a.names():
        print("%10d  %s" % (a.size(name), name))


def cmd_unpack(args):
    for path in args.archives:
        path = Path(path)
        if args.output:
            dest = Path(args.output) / path.stem if len(args.archives) > 1 else Path(args.output)
        else:
            dest = rpa.default_output_dir(path)
        n = rpa.RPAArchive(path).extract(dest, progress=_progress(path.name))
        print("%s: %d files -> %s" % (path.name, n, dest))


def cmd_pack(args):
    n = rpa.pack(args.folder, args.output, progress=_progress(Path(args.output).name))
    print("Created %s with %d files" % (args.output, n))


def _script_sources(paths, include_archives):
    sources, out_default = [], None
    for p in map(Path, paths):
        if p.is_file() and p.suffix == ".rpyc":
            sources.append((p.name, p.read_bytes))
            out_default = out_default or p.parent / "decompiled"
            continue
        root = game.find_game_root(p)
        if root is not None:
            g = game.GameInfo.load(root)
            sources += g.script_sources(include_archives)
            out_default = out_default or game.default_decompile_dir(g)
        elif p.is_dir():
            sources += [(str(f.relative_to(p)).replace("\\", "/"), f.read_bytes) for f in sorted(p.rglob("*.rpyc"))]
            out_default = out_default or p / "decompiled"
    return sources, out_default


def cmd_decompile(args):
    sources, out_default = _script_sources(args.paths, not args.no_archives)
    if not sources:
        sys.exit("no .rpyc files found")
    out = Path(args.output) if args.output else out_default
    written, skipped, errors = rpyc.decompile_many(sources, out, args.overwrite, progress=_progress("decompile"))
    print("Wrote %d files to %s (%d skipped, %d errors)" % (written, out, skipped, len(errors)))
    for name, msg in errors:
        print("  error: %s: %s" % (name, msg))


def _save_dirs(arg):
    if arg:
        return saves.default_save_dirs(game.GameInfo.load(arg))
    return saves.default_save_dirs(None)


def cmd_saves(args):
    entries = saves.list_saves(_save_dirs(args.game))
    if not entries:
        sys.exit("no saves found")
    for e in entries[:1] if args.latest else entries:
        print("%s  %s" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(e.mtime)), e.path))


def _open_doc(path):
    path = Path(path)
    return saves.PersistentFile(path) if path.name == "persistent" else saves.SaveFile(path)


def cmd_show(args):
    doc = _open_doc(args.file)
    needle = (args.filter or "").lower()
    for key, value in sorted(doc.variables.items(), key=lambda kv: values.fmt_key(kv[0])):
        name = values.fmt_key(key)
        if not args.all and saves.is_internal(name):
            continue
        if needle and needle not in name.lower():
            continue
        print("%-40s %-16s %s" % (name, values.type_label(value), values.preview(value, 200)))


def cmd_set(args):
    doc = _open_doc(args.file)
    variables = doc.variables
    lookup = {values.fmt_key(k): k for k in variables}
    name = args.name if args.name in lookup else "store." + args.name
    if name not in lookup:
        sys.exit("variable not found: %s" % args.name)
    key = lookup[name]
    old = variables[key]
    variables[key] = values.parse_value(args.value, old)
    keys = savetoken.load_signing_keys() if doc.is_signed else []
    if doc.is_signed and not keys:
        print("warning: file is signed but no signing key was found; Ren'Py may not trust it", file=sys.stderr)
    result = doc.write(backup=not args.no_backup, keys=keys)
    print("%s: %r -> %r%s" % (name, old, variables[key], " (re-signed)" if result.signed else ""))
    if result.backup:
        print("backup:", result.backup)


def cmd_devmode(args):
    g = game.GameInfo.load(args.game)
    if args.disable:
        game.remove_patch(g.game_dir)
        print("Developer patch removed.")
        return
    options = [o.strip() for o in args.options.split(",") if o.strip()]
    unknown = set(options) - set(game.PATCH_OPTIONS)
    if unknown:
        sys.exit("unknown option(s): %s (choose from %s)" % (", ".join(sorted(unknown)), ", ".join(game.PATCH_OPTIONS)))
    path = game.apply_patch(g.game_dir, options)
    print("Patch written to %s (%s)" % (path, ", ".join(sorted(game.patch_status(g.game_dir)))))


def cmd_live(args):
    g = game.GameInfo.load(args.game)
    client = live.LiveGame(g.root)
    if not client.is_running():
        sys.exit("no running game with a live connection (apply the 'live' patch and start the game)")
    if args.set:
        name, value = args.set
        state = client.read_state() or {}
        if name not in state.get("variables", {}):
            sys.exit("unknown or non-plain variable: %s" % name)
        client.set_variable(name, values.parse_value(value, state["variables"][name]))
        print("%s set in the running game" % name)
    if args.reload:
        client.reload()
        print("reload requested")
    if not args.set and not args.reload:
        state = client.read_state() or {}
        needle = (args.filter or "").lower()
        for name, value in sorted(state.get("variables", {}).items()):
            if not needle or needle in name.lower():
                print("%-40s %-16s %s" % (name, state["types"].get(name, ""), values.preview(value, 200)))


def cmd_mod_info(args):
    mod = mods.load(args.mod)
    print("%s %s (%s) by %s" % (mod.name, mod.version, mod.id, mod.author or "?"))
    if mod.description:
        print(mod.description)
    if mod.game:
        print("Made for:", ", ".join("%s=%s" % kv for kv in mod.game.items()))
    for path in sorted(mod.files):
        print("  file        game/%s/%s/%s" % (mods.INSTALL_DIR, mod.id, path))
    for r in mod.replacements:
        print("  replace     %s: %r -> %r" % (r.script, r.find[:60], r.replace[:60]))
    for ch in mod.cheats:
        print("  cheat       %s = %r  (%s)" % (ch.name, ch.value, ch.label))


def cmd_mod_pack(args):
    mod = mods.pack(args.folder, args.output)
    print("Packed %s (%d files) into %s" % (mod.id, len(mod.files), args.output))


def cmd_mod_install(args):
    g = game.GameInfo.load(args.game)
    mod = mods.load(args.mod)
    installer = mods.ModInstaller(g)
    warnings, error = installer.check(mod)
    for w in warnings:
        print("warning:", w)
    if error is not None:
        sys.exit("error: %s" % error)
    if mod.runs_code and not args.yes:
        sys.exit("this mod runs code inside the game; review it with 'mod-info' and re-run with --yes")
    installer.install(mod)
    print("Installed %s %s into %s" % (mod.name, mod.version, g.name))


def cmd_mod_uninstall(args):
    g = game.GameInfo.load(args.game)
    failed = mods.ModInstaller(g).uninstall(args.id)
    for display in failed:
        print("warning: could not revert %s automatically" % display)
    print("Uninstalled", args.id)


def cmd_mod_list(args):
    g = game.GameInfo.load(args.game)
    installed = mods.ModInstaller(g).installed()
    if not installed:
        print("no mods installed")
    for mod_id, entry in sorted(installed.items()):
        print("%-24s %-10s %s" % (mod_id, entry.get("version", ""), entry.get("installed", "")))


def build_parser():
    p = argparse.ArgumentParser(prog="renpy_suite", description="All-in-one toolkit for Ren'Py games.")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    p.add_argument("--lang", help="user interface language (%s)" % ", ".join(sorted(i18n.STRINGS)))
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("gui", help="start the graphical interface (default)")
    s.add_argument("game", nargs="?", help="game folder to open")
    s.set_defaults(func=cmd_gui)

    s = sub.add_parser("info", help="show information about a game")
    s.add_argument("game")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("list", help="list the files in an archive")
    s.add_argument("archive")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("unpack", help="extract archives")
    s.add_argument("archives", nargs="+")
    s.add_argument("-o", "--output", help="output folder (default: <game>/extracted/<archive>)")
    s.set_defaults(func=cmd_unpack)

    s = sub.add_parser("pack", help="create an RPA-3.0 archive from a folder")
    s.add_argument("folder")
    s.add_argument("output")
    s.set_defaults(func=cmd_pack)

    s = sub.add_parser("decompile", help="decompile .rpyc files, folders or whole games")
    s.add_argument("paths", nargs="+")
    s.add_argument("-o", "--output", help="output folder (default: <game>/decompiled)")
    s.add_argument("--overwrite", action="store_true", help="overwrite existing .rpy files")
    s.add_argument("--no-archives", action="store_true", help="skip scripts stored inside .rpa archives")
    s.set_defaults(func=cmd_decompile)

    s = sub.add_parser("saves", help="list save files (newest first)")
    s.add_argument("game", nargs="?", help="limit to this game")
    s.add_argument("--latest", action="store_true", help="only print the most recent save")
    s.set_defaults(func=cmd_saves)

    s = sub.add_parser("show", help="print the variables of a .save or persistent file")
    s.add_argument("file")
    s.add_argument("--filter", help="only variables containing this text")
    s.add_argument("--all", action="store_true", help="include Ren'Py internals (_…)")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("set", help="change a variable in a .save or persistent file")
    s.add_argument("file")
    s.add_argument("name", help="variable name, e.g. money or store.money")
    s.add_argument("value", help="new value; prefix with = for a Python literal (=[1, 2])")
    s.add_argument("--no-backup", action="store_true")
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("devmode", help="enable developer mode / console in a game")
    s.add_argument("game")
    s.add_argument("--options", default="developer,console",
                   help="comma-separated: %s" % ", ".join(game.PATCH_OPTIONS))
    s.add_argument("--disable", action="store_true", help="remove the patch")
    s.set_defaults(func=cmd_devmode)

    s = sub.add_parser("live", help="show or change variables of a running game (needs the 'live' patch)")
    s.add_argument("game")
    s.add_argument("--filter", help="only variables containing this text")
    s.add_argument("--set", nargs=2, metavar=("NAME", "VALUE"), help="change a variable")
    s.add_argument("--reload", action="store_true", help="reload the game (like Shift+R)")
    s.set_defaults(func=cmd_live)

    s = sub.add_parser("mod-info", help="show what a mod (.rsmod, mod.json or folder) contains")
    s.add_argument("mod")
    s.set_defaults(func=cmd_mod_info)

    s = sub.add_parser("mod-pack", help="pack a mod folder into a shareable .rsmod file")
    s.add_argument("folder")
    s.add_argument("output")
    s.set_defaults(func=cmd_mod_pack)

    s = sub.add_parser("mod-install", help="install a mod into a game")
    s.add_argument("game")
    s.add_argument("mod")
    s.add_argument("--yes", action="store_true", help="confirm installing mods that contain code")
    s.set_defaults(func=cmd_mod_install)

    s = sub.add_parser("mod-uninstall", help="uninstall a mod from a game")
    s.add_argument("game")
    s.add_argument("id")
    s.set_defaults(func=cmd_mod_uninstall)

    s = sub.add_parser("mod-list", help="list mods installed in a game")
    s.add_argument("game")
    s.set_defaults(func=cmd_mod_list)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.lang:
        i18n.set_language(args.lang)
    if args.command is None:
        from .gui import run
        run(language=args.lang)
        return
    try:
        args.func(args)
    except (FileNotFoundError, rpa.RPAError, rpyc.RpycError, mods.ModError, ValueError) as exc:
        sys.exit("error: %s" % exc)
