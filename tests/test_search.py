import re
import tempfile
import unittest
from pathlib import Path

from renpy_suite import game, search

from test_cli_i18n import build_fake_game
from test_core import make_rpyc


class SearchTest(unittest.TestCase):
    def test_search_loose_archived_and_edited(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Game"
            build_fake_game(root)

            def vars_script(fr):
                a = fr.ast
                return [a.Init(priority=0, block=[a.Default(store="store", varname="affection",
                                                            code=a.PyCode("0"))])]

            (root / "game" / "vars.rpyc").write_bytes(make_rpyc(vars_script))
            index = search.ScriptIndex(game.GameInfo.load(root))

            hits = index.search("AFFECTION")
            self.assertEqual([(h.script, h.line) for h in hits], [("vars.rpyc", 3)])
            self.assertEqual(hits[0].text, "default affection = 0")
            self.assertEqual(index.search("affection", case=True)[0].script, "vars.rpyc")
            self.assertEqual(index.search("AFFECTION", case=True), [])

            archived = index.search(r'e\s+"Hi', regex=True)
            self.assertEqual(archived[0].script, "archive.rpa:script.rpyc")

            (root / "game" / "vars.rpy").write_text("default affection = 50\n", "utf-8")
            self.assertEqual(index.search("affection = 50")[0].line, 1)

            with self.assertRaises(re.error):
                index.search("(", regex=True)


if __name__ == "__main__":
    unittest.main()
