import csv
import tempfile
import unittest
from pathlib import Path

from renpy_suite import game, translate

from test_cli_i18n import build_fake_game
from test_core import make_rpyc


def story(fr):
    a = fr.ast
    return [a.Label(name="start", block=[
        a.Translate(identifier="start_a1b2c3d4", language=None, block=[a.Say(who="e", what='Hello "you"')]),
        a.EndTranslate(),
        a.Translate(identifier="start_e5f6a7b8", language=None, block=[a.Say(what="Narration.")]),
        a.EndTranslate(),
        a.Menu(items=[("Go left", "True", [a.Jump(target="left")]), ("Go right", "True", [a.Return()])]),
        a.Say(who="e", what="Old style line without id"),
    ])]


class TranslateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        root = self.tmp / "Game"
        build_fake_game(root)
        (root / "game" / "story.rpyc").write_bytes(make_rpyc(story))
        self.lines, self.errors = translate.extract(game.GameInfo.load(root))

    def tearDown(self):
        self._tmp.cleanup()

    def test_extract(self):
        self.assertEqual(self.errors, [])
        story_lines = [(l.kind, l.identifier, l.who, l.original) for l in self.lines if l.script == "story.rpy"]
        self.assertEqual(story_lines, [
            ("say", "start_a1b2c3d4", "e", 'Hello "you"'),
            ("say", "start_e5f6a7b8", "", "Narration."),
            ("string", "", "", "Go left"),
            ("string", "", "", "Go right"),
            ("say", "", "e", "Old style line without id"),
        ])

    def test_csv_roundtrip_into_tl_files(self):
        csv_path = self.tmp / "dialogue.csv"
        translate.write_csv(self.lines, csv_path)
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            if row["original"] == 'Hello "you"':
                row["translation"] = 'Hallo "du"'
            if row["original"] == "Go left":
                row["translation"] = "Nach links"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, translate.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        counts = translate.write_tl(self.lines, "german", self.tmp / "out", translate.read_translations(csv_path))
        self.assertEqual(counts["translated"], 2)
        text = (self.tmp / "out" / "tl" / "german" / "story.rpy").read_text("utf-8")
        self.assertIn('translate german start_a1b2c3d4:\n\n    # e "Hello \\"you\\""\n    e "Hallo \\"du\\""', text)
        self.assertIn('    "Narration."', text)
        self.assertIn('translate german strings:', text)
        self.assertIn('    old "Go left"\n    new "Nach links"', text)
        self.assertGreaterEqual(counts["skipped"], 1)

    def test_cli(self):
        import contextlib
        import io
        from renpy_suite import cli
        root = self.tmp / "Game"
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["translate", str(root), "--language", "french"])
            cli.main(["translate", str(root), "--language", "french", "--into-game", "--no-csv"])
            with self.assertRaises(SystemExit):  # already exists now
                cli.main(["translate", str(root), "--language", "french", "--into-game"])
        self.assertTrue((root / "translations" / "dialogue.csv").is_file())
        self.assertTrue((root / "translations" / "tl" / "french" / "story.rpy").is_file())
        self.assertTrue((root / "game" / "tl" / "french" / "story.rpy").is_file())

    def test_language_name_is_validated(self):
        with self.assertRaises(ValueError):
            translate.write_tl(self.lines, "../evil", self.tmp / "out")


if __name__ == "__main__":
    unittest.main()
