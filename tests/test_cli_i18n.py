import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from renpy_suite import cli, game, i18n, rpa

from test_core import make_rpyc

ROOT = Path(__file__).resolve().parent.parent


class I18nTest(unittest.TestCase):
    def test_all_languages_have_the_same_keys(self):
        en = set(i18n.STRINGS["en"])
        for code, strings in i18n.STRINGS.items():
            self.assertEqual(set(strings), en, "language %s" % code)

    def test_every_used_key_exists(self):
        used = set()
        for path in (ROOT / "renpy_suite").rglob("*.py"):
            used |= set(re.findall(r"""\bt\(\s*["']([a-z_]+)["']""", path.read_text("utf-8")))
            used |= set(re.findall(r""""(opt_[a-z]+|info_[a-z]+|tab_[a-z]+)\"""", path.read_text("utf-8")))
        missing = used - set(i18n.STRINGS["en"])
        self.assertFalse(missing, missing)

    def test_placeholders_match(self):
        for key, text in i18n.STRINGS["en"].items():
            for code, strings in i18n.STRINGS.items():
                self.assertEqual(set(re.findall(r"{(\w+)}", text)), set(re.findall(r"{(\w+)}", strings[key])),
                                 "%s/%s" % (code, key))


def build_fake_game(root: Path):
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    (root / "renpy" / "vc_version.py").write_text("version = '8.3.4.24120703'\n")
    (root / "lib" / "py3-windows-x86_64").mkdir(parents=True)

    def options(fr):
        a = fr.ast
        return [a.Init(priority=0, block=[a.Define(store="store.config", varname="save_directory",
                                                   code=a.PyCode('"FakeGame-123"'))])]

    def script(fr):
        a = fr.ast
        return [a.Label(name="start", block=[a.Say(who="e", what="Hi!"), a.Return()])]

    staging = root / "staging"
    (staging / "images").mkdir(parents=True)
    (staging / "images" / "bg.png").write_bytes(b"\x89PNG data")
    (staging / "script.rpyc").write_bytes(make_rpyc(script))
    (staging / "options.rpyc").write_bytes(make_rpyc(options))
    rpa.pack(staging, root / "game" / "archive.rpa")


class CliTest(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(list(argv))
        return out.getvalue()

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "FakeGame"
            build_fake_game(root)

            info = self.run_cli("info", str(root))
            self.assertIn("8.3.4.24120703", info)
            self.assertIn("Python 3", info)
            self.assertIn("FakeGame-123", info)

            self.assertIn("images/bg.png", self.run_cli("list", str(root / "game" / "archive.rpa")))
            self.run_cli("unpack", str(root / "game" / "archive.rpa"))
            self.assertTrue((root / "extracted" / "archive" / "images" / "bg.png").is_file())

            self.run_cli("decompile", str(root))
            text = (root / "decompiled" / "script.rpy").read_text("utf-8")
            self.assertIn('label start:\n    e "Hi!"\n    return', text)

            self.run_cli("devmode", str(root), "--options", "console")
            self.assertEqual(game.patch_status(root / "game"), {"console"})
            self.run_cli("devmode", str(root), "--disable")
            self.assertEqual(game.patch_status(root / "game"), set())


if __name__ == "__main__":
    unittest.main()
