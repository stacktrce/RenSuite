"""Live connection to a running game.

The developer patch can install a small bridge into the game. A few times
per second it

* writes the game's current simple variables to ``renpy_suite_live/state.json``,
* executes commands dropped into ``renpy_suite_live/commands/``:
  ``set`` (assign a variable) and ``reload`` (the same as pressing Shift+R:
  save, recompile changed scripts, and continue where you were).

Commands only carry JSON values and never code. A variable can only be
replaced if it already exists and holds a plain value (number, text, bool,
None, or lists/dicts of those).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import textwrap
import time
from pathlib import Path

LIVE_DIR = "renpy_suite_live"

# Runs inside the game (Ren'Py 6.99 – 8.x, Python 2 or 3), within "init 999 python:".
BRIDGE_CODE = textwrap.dedent(r'''
    import json as _rs_json, os as _rs_os, re as _rs_re, time as _rs_time
    try:
        import __builtin__ as _rs_builtins
    except ImportError:
        import builtins as _rs_builtins
    # In the store, list/dict are Ren'Py's revertable subclasses; type checks need the real ones.
    _rs_list, _rs_dict, _rs_tuple = _rs_builtins.list, _rs_builtins.dict, _rs_builtins.tuple
    try:
        _rs_text = (basestring,)
        _rs_ints = (int, long)
    except NameError:
        _rs_text = (str,)
        _rs_ints = (int,)
    _rs_dir = _rs_os.path.join(config.basedir, "renpy_suite_live")
    _rs_cmd_dir = _rs_os.path.join(_rs_dir, "commands")
    _rs_name_re = _rs_re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

    def _rs_plain(v, depth=0):
        if v is None or isinstance(v, (bool, float) + _rs_ints):
            return v
        if isinstance(v, _rs_text):
            if len(v) > 5000:
                raise ValueError("too long")
            return v
        if depth < 4 and isinstance(v, (_rs_list, _rs_tuple)) and len(v) <= 200:
            return [_rs_plain(x, depth + 1) for x in v]
        if depth < 4 and isinstance(v, _rs_dict) and len(v) <= 200:
            out = {}
            for k, x in v.items():
                if not isinstance(k, _rs_text):
                    raise ValueError("key")
                out[k] = _rs_plain(x, depth + 1)
            return out
        raise ValueError("not plain")

    def _rs_revertable(v):
        if isinstance(v, _rs_list):
            return list(_rs_revertable(x) for x in v)
        if isinstance(v, _rs_dict):
            return dict((k, _rs_revertable(x)) for k, x in v.items())
        return v

    def _rs_write(path, text):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        try:
            _rs_os.replace(tmp, path)
        except AttributeError:
            if _rs_os.path.exists(path):
                _rs_os.remove(path)
            _rs_os.rename(tmp, path)

    def _rs_write_state():
        variables, types = {}, {}
        for name, value in list(renpy.store.__dict__.items()):
            if not _rs_name_re.match(name):
                continue
            try:
                variables[name] = _rs_plain(value)
            except ValueError:
                continue
            types[name] = type(value).__name__
        state = {"time": _rs_time.time(), "variables": variables, "types": types}
        _rs_write(_rs_os.path.join(_rs_dir, "state.json"), _rs_json.dumps(state, ensure_ascii=True, sort_keys=True))

    def _rs_run_commands():
        try:
            names = sorted(_rs_os.listdir(_rs_cmd_dir))
        except OSError:
            return
        for fn in names:
            if not fn.endswith(".json"):
                continue
            path = _rs_os.path.join(_rs_cmd_dir, fn)
            try:
                with open(path) as f:
                    cmd = _rs_json.load(f)
            except Exception:
                cmd = None
            try:
                _rs_os.remove(path)
            except OSError:
                pass
            if not isinstance(cmd, _rs_dict):
                continue
            if cmd.get("op") == "set":
                name = cmd.get("name")
                if not (isinstance(name, _rs_text) and _rs_name_re.match(name) and hasattr(renpy.store, name)):
                    continue
                try:
                    _rs_plain(getattr(renpy.store, name))
                    value = _rs_revertable(_rs_plain(cmd.get("value")))
                except ValueError:
                    continue
                setattr(renpy.store, name, value)
                renpy.restart_interaction()
            elif cmd.get("op") == "reload":
                renpy.queue_event("reload_game")

    def _rs_periodic():
        now = _rs_time.time()
        if now - _rs_periodic.last < 0.25:
            return
        _rs_periodic.last = now
        try:
            _rs_run_commands()
            if now - _rs_periodic.last_state >= 1.0:
                _rs_periodic.last_state = now
                _rs_write_state()
        except Exception:
            pass

    _rs_periodic.last = 0.0
    _rs_periodic.last_state = 0.0
    try:
        _rs_os.makedirs(_rs_cmd_dir)
    except OSError:
        pass
    if hasattr(config, "periodic_callbacks"):
        config.periodic_callbacks.append(_rs_periodic)
    else:
        _rs_previous = config.periodic_callback

        def _rs_chained():
            if _rs_previous is not None:
                _rs_previous()
            _rs_periodic()

        config.periodic_callback = _rs_chained
''').strip("\n")


def check_plain(value, depth=0):
    """Raise ValueError unless ``value`` is something the bridge accepts."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if depth < 4 and isinstance(value, list):
        for v in value:
            check_plain(v, depth + 1)
        return
    if depth < 4 and isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError("dict keys must be text")
            check_plain(v, depth + 1)
        return
    raise ValueError("only numbers, text, true/false, None, lists and dicts can be sent to a running game")


class LiveGame:
    """The Suite's side of the bridge for one game folder."""

    def __init__(self, game_root):
        self.dir = Path(game_root) / LIVE_DIR
        self.state_path = self.dir / "state.json"
        self.commands = self.dir / "commands"

    def is_running(self, max_age: float = 4.0) -> bool:
        try:
            return time.time() - self.state_path.stat().st_mtime < max_age
        except OSError:
            return False

    def read_state(self):
        try:
            return json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def send(self, op: str, **payload):
        self.commands.mkdir(parents=True, exist_ok=True)
        name = "%020d-%s.json" % (time.time() * 1e6, secrets.token_hex(3))
        tmp = self.commands / (name + ".tmp")
        tmp.write_text(json.dumps(dict(payload, op=op)), "utf-8")
        os.replace(tmp, self.commands / name)

    def set_variable(self, name: str, value):
        check_plain(value)
        self.send("set", name=name, value=value)

    def reload(self):
        self.send("reload")

    def cleanup(self):
        if self.dir.is_dir():
            shutil.rmtree(self.dir, ignore_errors=True)


class LiveDoc:
    """Variables of a running game, shaped like a save document for the editor."""

    is_signed = False

    def __init__(self, live: LiveGame):
        state = live.read_state()
        if not state:
            raise ValueError("no live state available")
        self.live = live
        self.path = live.state_path
        self.variables = state.get("variables", {})
        self.types = state.get("types", {})
