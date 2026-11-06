import unittest

from renpy_suite import scan
from renpy_suite import stubpickle as sp


def snap(**variables):
    return scan.Snapshot("test", scan.flatten({"store." + k: v for k, v in variables.items()}))


class ScanTest(unittest.TestCase):
    def test_flatten_nested_and_stubs(self):
        obj = sp.stub_class("renpy.revertable", "RevertableObject")()
        obj.__setstate__({"hp": 5, "name": "Alex"})
        lst = sp.stub_class("renpy.revertable", "RevertableList")()
        lst.extend(["sword", 3])
        flat = scan.flatten({"store.player": obj, "store.inv": lst, "store.flags": {"met": True},
                             "store._internal": 1, "store.achievement.x": 1})
        self.assertEqual(flat, {"player.hp": 5, "player.name": "Alex", "inv[0]": "sword", "inv[1]": 3,
                                "flags['met']": True})

    def test_cheat_engine_workflow(self):
        s = scan.Scan()
        rows = s.first(snap(money=100, gold=100, hp=50, day=1), "equals", "100")
        self.assertEqual([r[0] for r in rows], ["gold", "money"])
        rows = s.next(snap(money=80, gold=100, hp=40, day=1), "decreased")
        self.assertEqual(rows, [("money", 100, 80)])
        rows = s.next(snap(money=80, gold=200, hp=40, day=2), "unchanged")
        self.assertEqual([r[0] for r in rows], ["money"])

    def test_changed_without_first_filter(self):
        s = scan.Scan()
        s.first(snap(a=1, b="x", c=True))
        rows = s.next(snap(a=1, b="y", c=False, d=5), "changed")
        self.assertEqual([r[0] for r in rows], ["b", "c", "d"])
        self.assertIs(rows[2][1], scan.MISSING)

    def test_equals_and_numbers(self):
        self.assertTrue(scan.equals(5, "5.0"))
        self.assertTrue(scan.equals(True, "true"))
        self.assertFalse(scan.equals(1, "true"))
        self.assertTrue(scan.equals(b"Alex", "Alex"))
        self.assertFalse(scan.matches("increased", True, False))
        self.assertEqual(scan.top_level("money"), "money")
        self.assertIsNone(scan.top_level("player.hp"))


if __name__ == "__main__":
    unittest.main()
