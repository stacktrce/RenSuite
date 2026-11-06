import json
import pickle
import tempfile
import unittest
import zipfile
from pathlib import Path

from renpy_suite import game, mods, rpa
from renpy_suite.scriptedit import ScriptEditor

from fake_renpy import fake_renpy
from test_cli_i18n import build_fake_game


def write_mod(folder: Path, **overrides):
    meta = {
        "format": "renpy-suite-mod", "format_version": 1,
        "id": "test-mod", "name": "Test mod", "version": "1.0", "author": "tester",
        "description": "for tests",
        "replacements": [{"script": "script.rpy", "find": 'e "Hi!"', "replace": 'e "Modded!"'}],
        "cheats": [{"name": "money", "value": 9999, "label": "Rich"}],
    }
    meta.update(overrides)
    (folder / "game").mkdir(parents=True, exist_ok=True)
    (folder / "mod.json").write_text(json.dumps(meta), "utf-8")
    (folder / "game" / "cheats.rpy").write_text("init 999 python:\n    config.default_text_cps = 0\n", "utf-8")
    (folder / "game" / "img").mkdir(exist_ok=True)
    (folder / "game" / "img" / "badge.png").write_bytes(b"\x89PNG")
    return folder


class ModFormatTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_folder_and_package_roundtrip(self):
        mod = mods.load(write_mod(self.tmp / "src"))
        self.assertEqual(mod.id, "test-mod")
        self.assertEqual(mod.scripts, ["cheats.rpy"])
        self.assertTrue(mod.runs_code)
        packed = self.tmp / "test.rsmod"
        mods.pack(self.tmp / "src", packed)
        again = mods.load(packed)
        self.assertEqual(again.files, mod.files)
        self.assertEqual(again.cheats[0].value, 9999)

    def test_zip_with_top_folder(self):
        src = write_mod(self.tmp / "src")
        archive = self.tmp / "nested.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for p in src.rglob("*"):
                if p.is_file():
                    zf.write(p, "my-mod/" + p.relative_to(src).as_posix())
        self.assertEqual(mods.load(archive).files.keys(), {"cheats.rpy", "img/badge.png"})

    def test_validation(self):
        bad_cases = ({"id": "Bad ID"}, {"format": "other"}, {"format_version": 99},
                     {"cheats": [{"name": "x y", "value": 1}]}, {"cheats": [{"name": "x"}]},
                     {"replacements": [{"script": "a.rpy", "find": ""}]})
        for i, bad in enumerate(bad_cases):
            with self.assertRaises(mods.ModError, msg=str(bad)):
                mods.load(write_mod(self.tmp / ("bad%d" % i), **bad))
        nested = {"cheats": [{"name": "flags", "value": {"a": True, "b": [1, {"c": None}]}}]}
        self.assertEqual(mods.load(write_mod(self.tmp / "nested", **nested)).cheats[0].name, "flags")

    def test_path_traversal_is_neutralised(self):
        archive = self.tmp / "evil.rsmod"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("mod.json", json.dumps({"format": "renpy-suite-mod", "id": "evil", "name": "Evil"}))
            zf.writestr("game/../../outside.rpy", "x")
        self.assertEqual(list(mods.load(archive).files), ["outside.rpy"])

    def test_library(self):
        lib = mods.ModLibrary(self.tmp / "lib")
        mod = lib.add(write_mod(self.tmp / "src") / "mod.json")
        self.assertTrue((self.tmp / "lib" / "test-mod.rsmod").is_file())
        self.assertEqual([m.id for m in lib.mods()], ["test-mod"])
        lib.remove(mod.id)
        self.assertEqual(lib.mods(), [])


class ExampleAndCliTest(unittest.TestCase):
    def test_example_mod_is_valid(self):
        example = Path(__file__).resolve().parent.parent / "examples" / "quality-of-life"
        mod = mods.load(example)
        self.assertEqual(mod.scripts, ["quality_of_life.rpy"])
        self.assertEqual(len(mod.cheats), 2)

    def test_cli_pack_install_uninstall(self):
        import contextlib
        import io
        from renpy_suite import cli

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            build_fake_game(tmp / "Game")
            src = write_mod(tmp / "src")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli.main(["mod-pack", str(src), str(tmp / "m.rsmod")])
                with self.assertRaises(SystemExit):  # contains code: needs --yes
                    cli.main(["mod-install", str(tmp / "Game"), str(tmp / "m.rsmod")])
                cli.main(["mod-install", str(tmp / "Game"), str(tmp / "m.rsmod"), "--yes"])
                cli.main(["mod-list", str(tmp / "Game")])
                cli.main(["mod-uninstall", str(tmp / "Game"), "test-mod"])
            text = out.getvalue()
            self.assertIn("Installed Test mod", text)
            self.assertIn("test-mod", text)
            self.assertFalse((tmp / "Game" / "game" / "renpy_suite_mods").exists())


class ModInstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "FakeGame"
        build_fake_game(self.root)
        self.game = game.GameInfo.load(self.root)
        self.archive = self.root / "game" / "archive.rpa"
        self.original_member = rpa.RPAArchive(self.archive).read("script.rpyc")

    def tearDown(self):
        self._tmp.cleanup()

    def test_install_and_uninstall(self):
        mod = mods.load(write_mod(self.tmp / "src"))
        installer = mods.ModInstaller(self.game)
        warnings, error = installer.check(mod)
        self.assertIsNone(error)
        installer.install(mod)

        installed = self.root / "game" / "renpy_suite_mods" / "test-mod"
        self.assertTrue((installed / "cheats.rpy").is_file())
        self.assertTrue((installed / "img" / "badge.png").is_file())
        self.assertIn('e "Modded!"', (self.root / "game" / "script.rpy").read_text("utf-8"))
        self.assertNotIn("script.rpyc", rpa.RPAArchive(self.archive).names())
        self.assertIn("test-mod", installer.installed())
        self.assertTrue(ScriptEditor(self.game).is_edited("archive.rpa:script.rpyc"))

        (installed / "cheats.rpyc").write_bytes(b"compiled by renpy")
        self.assertEqual(installer.uninstall("test-mod"), [])
        self.assertFalse((self.root / "game" / "renpy_suite_mods").exists())
        self.assertFalse((self.root / "game" / "script.rpy").exists())
        self.assertEqual(rpa.RPAArchive(self.archive).read("script.rpyc"), self.original_member)
        self.assertEqual(installer.installed(), {})

    def test_reinstall_updates_cleanly(self):
        mod = mods.load(write_mod(self.tmp / "src"))
        installer = mods.ModInstaller(self.game)
        installer.install(mod)
        self.assertEqual(installer.check(mod), ([], None))
        installer.install(mod)  # update: uninstalls first, then patches the original again
        text = (self.root / "game" / "script.rpy").read_text("utf-8")
        self.assertEqual(text.count('e "Modded!"'), 1)
        self.assertEqual(installer.uninstall("test-mod"), [])
        self.assertEqual(rpa.RPAArchive(self.archive).read("script.rpyc"), self.original_member)

    def test_missing_find_text_installs_nothing(self):
        mod = mods.load(write_mod(self.tmp / "src", replacements=[
            {"script": "script.rpy", "find": "this text does not exist", "replace": "x"}]))
        installer = mods.ModInstaller(self.game)
        _, error = installer.check(mod)
        self.assertEqual(error.key, "mod_err_find")
        with self.assertRaises(mods.ModError):
            installer.install(mod)
        self.assertFalse((self.root / "game" / "renpy_suite_mods").exists())
        self.assertIn("script.rpyc", rpa.RPAArchive(self.archive).names())

    def test_uninstall_after_user_edit_reverts_only_the_mod(self):
        mod = mods.load(write_mod(self.tmp / "src"))
        installer = mods.ModInstaller(self.game)
        installer.install(mod)
        rpy = self.root / "game" / "script.rpy"
        rpy.write_text(rpy.read_text("utf-8") + "\nlabel extra:\n    return\n", "utf-8")
        self.assertEqual(installer.uninstall("test-mod"), [])
        text = rpy.read_text("utf-8")
        self.assertIn('e "Hi!"', text)
        self.assertIn("label extra:", text)

    def test_cheats_to_save(self):
        with fake_renpy() as fr:
            log = pickle.dumps(({"store.money": 5}, fr.rollback.RollbackLog()), 2)
        save = self.tmp / "1-1.save"
        with zipfile.ZipFile(save, "w") as zf:
            zf.writestr("log", log)
        cheats = [mods.Cheat("money", 9999), mods.Cheat("unknown", 1)]
        applied, missing, result = mods.apply_cheats_to_save(save, cheats, keys=[])
        self.assertEqual((applied, missing), (["money"], ["unknown"]))
        with fake_renpy(), zipfile.ZipFile(save) as zf:
            self.assertEqual(pickle.loads(zf.read("log"))[0]["store.money"], 9999)


if __name__ == "__main__":
    unittest.main()
