import tempfile
import unittest
from pathlib import Path

from renpy_suite import game, rpa
from renpy_suite.scriptedit import ScriptEditor

from test_cli_i18n import build_fake_game
from test_core import make_rpyc


def loose_script(fr):
    a = fr.ast
    return [a.Init(priority=0, block=[a.Default(store="store", varname="cheat", code=a.PyCode("False"))])]


class ScriptEditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "FakeGame"
        build_fake_game(self.root)
        (self.root / "game" / "vars.rpyc").write_bytes(make_rpyc(loose_script))
        self.game = game.GameInfo.load(self.root)
        self.sources = dict(self.game.script_sources())

    def tearDown(self):
        self._tmp.cleanup()

    def test_loose_script_apply_and_restore(self):
        ed = ScriptEditor(self.game)
        original_rpyc = (self.root / "game" / "vars.rpyc").read_bytes()
        text, from_source = ed.load_text("vars.rpyc", self.sources["vars.rpyc"])
        self.assertFalse(from_source)
        self.assertIn("default cheat = False", text)

        ed.apply("vars.rpyc", self.sources["vars.rpyc"], text.replace("False", "True"))
        rpy = self.root / "game" / "vars.rpy"
        self.assertIn("default cheat = True", rpy.read_text("utf-8"))
        self.assertTrue(ScriptEditor(self.game).is_edited("vars.rpyc"))  # manifest persisted
        text, from_source = ed.load_text("vars.rpyc", self.sources["vars.rpyc"])
        self.assertTrue(from_source)
        self.assertIn("cheat = True", text)

        # Ren'Py would overwrite the .rpyc when it recompiles.
        (self.root / "game" / "vars.rpyc").write_bytes(b"recompiled")
        self.assertTrue(ed.restore("vars.rpyc"))
        self.assertFalse(rpy.exists())
        self.assertEqual((self.root / "game" / "vars.rpyc").read_bytes(), original_rpyc)
        self.assertFalse(ed.is_edited("vars.rpyc"))

    def test_archived_script_is_taken_out_of_the_archive(self):
        ed = ScriptEditor(self.game)
        name = "archive.rpa:script.rpyc"
        archived = self.sources[name]()
        ed.apply(name, self.sources[name], 'label start:\n    "Edited!"\n    return\n')

        archive = self.root / "game" / "archive.rpa"
        names = rpa.RPAArchive(archive).names()
        self.assertNotIn("script.rpyc", names)
        self.assertIn("images/bg.png", names)
        self.assertEqual(rpa.RPAArchive(archive).read("images/bg.png"), b"\x89PNG data")
        self.assertEqual((self.root / "game" / "script.rpyc").read_bytes(), archived)
        self.assertTrue((self.root / "game" / "script.rpy").is_file())

        self.assertTrue(ed.restore(name))
        restored = rpa.RPAArchive(archive)
        self.assertIn("script.rpyc", restored.names())
        self.assertEqual(restored.read("script.rpyc"), archived)
        self.assertFalse((self.root / "game" / "script.rpyc").exists())
        self.assertFalse((self.root / "game" / "script.rpy").exists())


if __name__ == "__main__":
    unittest.main()
