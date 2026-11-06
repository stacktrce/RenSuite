import tempfile
import types
import unittest
from pathlib import Path

from renpy_suite import game, live


class RevertableList(list):
    pass


class RevertableDict(dict):
    pass


def fake_game_namespace(basedir):
    """Just enough of Ren'Py's store namespace to run the bridge."""
    store = types.ModuleType("store")
    store.money = 10
    store.cheat = False
    store.name = "Alex"
    store.inventory = RevertableList(["sword"])
    store.e = object()  # e.g. a Character: not plain, must be skipped
    events = []
    restarts = []
    renpy = types.SimpleNamespace(store=store, queue_event=events.append,
                                  restart_interaction=lambda: restarts.append(1))
    config = types.SimpleNamespace(basedir=str(basedir), periodic_callbacks=[])
    ns = {"renpy": renpy, "config": config, "list": RevertableList, "dict": RevertableDict}
    return ns, store, events, restarts


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ns, self.store, self.events, self.restarts = fake_game_namespace(self.root)
        exec(compile(live.BRIDGE_CODE, "zz_renpy_suite_patch.rpy", "exec"), self.ns)
        self.tick = self.ns["config"].periodic_callbacks[0]
        self.client = live.LiveGame(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def run_tick(self):
        fn = self.ns["_rs_periodic"]
        fn.last = fn.last_state = 0.0
        self.tick()

    def test_state_is_published(self):
        self.assertFalse(self.client.is_running())
        self.run_tick()
        self.assertTrue(self.client.is_running())
        state = self.client.read_state()
        self.assertEqual(state["variables"]["money"], 10)
        self.assertEqual(state["variables"]["inventory"], ["sword"])
        self.assertEqual(state["types"]["inventory"], "RevertableList")
        self.assertNotIn("e", state["variables"])

    def test_set_variables_and_reload(self):
        self.client.set_variable("cheat", True)
        self.client.set_variable("inventory", ["sword", "key"])
        self.client.set_variable("e", 1)            # not a plain value: refused
        self.client.set_variable("missing", 1)      # unknown variable: refused
        self.client.send("set", name="__class__", value=1)
        self.client.reload()
        self.run_tick()
        self.assertIs(self.store.cheat, True)
        self.assertIsInstance(self.store.inventory, RevertableList)
        self.assertEqual(self.store.inventory, ["sword", "key"])
        self.assertIsInstance(self.store.e, object)
        self.assertFalse(hasattr(self.store, "missing"))
        self.assertEqual(self.events, ["reload_game"])
        self.assertTrue(self.restarts)
        self.assertEqual(list(self.client.commands.iterdir()), [])

    def test_freeze_keeps_value_and_survives_restart(self):
        self.client.freeze("money", 9999)
        self.run_tick()
        self.assertEqual(self.store.money, 9999)
        self.store.money = 5  # the game spends money …
        self.run_tick()
        self.assertEqual(self.store.money, 9999)  # … and the freeze puts it back
        self.assertEqual(self.client.frozen(), {"money"})
        self.assertTrue(self.client.supports_freeze())

        # A reload/restart runs the bridge again: the freeze is restored from frozen.json.
        ns, store, _, _ = fake_game_namespace(self.root)
        exec(compile(live.BRIDGE_CODE, "bridge", "exec"), ns)
        store.money = 1
        fn = ns["_rs_periodic"]
        fn.last = fn.last_state = 0.0
        fn()
        self.assertEqual(store.money, 9999)

        self.client.unfreeze("money")
        self.run_tick()
        self.store.money = 3
        self.run_tick()
        self.assertEqual(self.store.money, 3)
        self.assertEqual(self.client.frozen(), set())

    def test_client_rejects_non_plain_values(self):
        with self.assertRaises(ValueError):
            self.client.set_variable("money", (1, 2))


class PatchLiveTest(unittest.TestCase):
    def test_live_implies_developer_and_is_valid_python(self):
        with tempfile.TemporaryDirectory() as d:
            game.apply_patch(d, {"live"})
            self.assertEqual(game.patch_status(d), {"live", "developer"})
            text = game.patch_path(d).read_text("utf-8")
            body = "\n".join(l[4:] for l in text.splitlines()[2:])
            compile(body, "patch", "exec")
            (Path(d).parent / live.LIVE_DIR).mkdir(exist_ok=True)
            game.remove_patch(d)
            self.assertFalse((Path(d).parent / live.LIVE_DIR).exists())


if __name__ == "__main__":
    unittest.main()
