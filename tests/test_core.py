import pickle
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from renpy_suite import game, rpa, rpyc, saves, savetoken, values
from renpy_suite import stubpickle as sp

from fake_renpy import fake_renpy


class TmpDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class RPATest(TmpDirTest):
    def test_pack_and_unpack_roundtrip(self):
        src = self.tmp / "src"
        (src / "images" / "bg").mkdir(parents=True)
        (src / "images" / "bg" / "room.png").write_bytes(b"\x89PNG" + bytes(range(256)) * 10)
        (src / "script.rpyc").write_bytes(b"compiled")
        archive = self.tmp / "archive.rpa"
        self.assertEqual(rpa.pack(src, archive), 2)

        a = rpa.RPAArchive(archive)
        self.assertEqual(a.version, "RPA-3.0")
        self.assertEqual(a.names(), ["images/bg/room.png", "script.rpyc"])
        out = self.tmp / "out"
        self.assertEqual(a.extract(out), 2)
        self.assertEqual((out / "images/bg/room.png").read_bytes(), (src / "images/bg/room.png").read_bytes())

    def _write_archive(self, path, header_fmt, entries, key=0):
        data = b""
        body_start = 64
        index = {}
        for name, content, prefix in entries:
            offset = body_start + len(data)
            data += content
            index[name] = [(offset ^ key, len(content) ^ key, prefix)]
        index_offset = body_start + len(data)
        header = header_fmt(index_offset, key).ljust(body_start, b"\0")
        path.write_bytes(header + data + zlib.compress(pickle.dumps(index, 2)))

    def test_rpa2_prefix_and_traversal(self):
        path = self.tmp / "old.rpa"
        self._write_archive(path, lambda off, key: b"RPA-2.0 %016x\n" % off, [
            ("../../evil.txt", b"payload", b""),
            (b"a/b.txt", b"rest", b"PRE-"),
        ])
        a = rpa.RPAArchive(path)
        self.assertEqual(a.read("a/b.txt"), b"PRE-rest")
        out = self.tmp / "out"
        a.extract(out)
        self.assertTrue((out / "evil.txt").exists())
        self.assertFalse((self.tmp / "evil.txt").exists())

    def test_rpa32_multiple_keys(self):
        path = self.tmp / "v32.rpa"
        k1, k2 = 0x12345678, 0x0F0F0F0F
        self._write_archive(path, lambda off, key: b"RPA-3.2 %016x %08x %08x\n" % (off, k1, k2),
                            [("x.txt", b"hello", b"")], key=k1 ^ k2)
        self.assertEqual(rpa.RPAArchive(path).read("x.txt"), b"hello")

    def test_save_members_flat_without_overwriting(self):
        src = self.tmp / "src"
        (src / "images" / "a").mkdir(parents=True)
        (src / "images" / "b").mkdir(parents=True)
        (src / "images" / "a" / "bg.png").write_bytes(b"A")
        (src / "images" / "b" / "bg.png").write_bytes(b"B")
        rpa.pack(src, self.tmp / "images.rpa")
        archive = rpa.RPAArchive(self.tmp / "images.rpa")
        out = self.tmp / "out"
        out.mkdir()
        (out / "bg.png").write_bytes(b"existing")
        written = rpa.save_members(archive, ["images/a/bg.png", "images/b/bg.png"], out)
        self.assertEqual([p.name for p in written], ["bg (2).png", "bg (3).png"])
        self.assertEqual((out / "bg.png").read_bytes(), b"existing")
        self.assertEqual((out / "bg (3).png").read_bytes(), b"B")

    def test_default_output_outside_game_dir(self):
        p = self.tmp / "MyGame" / "game" / "images.rpa"
        self.assertEqual(rpa.default_output_dir(p), (self.tmp / "MyGame" / "extracted" / "images").resolve())


class StubPickleTest(unittest.TestCase):
    def test_roundtrip_preserves_renpy_objects(self):
        with fake_renpy() as fr:
            inv = fr.revertable.RevertableList(["sword", "potion"])
            flags = fr.revertable.RevertableDict(met_alice=True)
            obj = fr.revertable.RevertableObject()
            obj.hp = 10
            obj.inventory = inv
            roots = {"store.money": 100, "store.name": "Bob", "store.inv": inv,
                     "store.flags": flags, "store.player": obj}
            data = pickle.dumps((roots, fr.rollback.RollbackLog()), 2)

        loaded_roots, log = sp.loads(data)
        self.assertEqual(sp.class_path(loaded_roots["store.inv"]), "renpy.revertable.RevertableList")
        self.assertIs(sp.state(loaded_roots["store.player"])["inventory"], loaded_roots["store.inv"])

        loaded_roots["store.money"] = 99999
        sp.items(loaded_roots["store.inv"]).append("key")
        sp.state(loaded_roots["store.player"])["hp"] = 50
        out = sp.dumps((loaded_roots, log))

        with fake_renpy() as fr:
            roots2, log2 = pickle.loads(out)
            self.assertEqual(roots2["store.money"], 99999)
            self.assertIsInstance(roots2["store.inv"], fr.revertable.RevertableList)
            self.assertEqual(list(roots2["store.inv"]), ["sword", "potion", "key"])
            self.assertEqual(roots2["store.flags"], {"met_alice": True})
            self.assertEqual(roots2["store.player"].hp, 50)
            self.assertIs(roots2["store.player"].inventory, roots2["store.inv"])
            self.assertIsInstance(log2, fr.rollback.RollbackLog)

    def test_no_code_execution(self):
        class Evil:
            def __reduce__(self):
                import os
                return (os.system, ("echo pwned",))

        loaded = sp.loads(pickle.dumps(Evil(), 2))
        self.assertTrue(sp.is_stub(loaded))
        self.assertEqual(sp.args(loaded), ["echo pwned"])

    def test_python2_strings_roundtrip_as_bytes(self):
        # Protocol-2 pickle with a Python 2 str (SHORT_BINSTRING) holding UTF-8.
        py2 = b"\x80\x02}q\x00U\x05storeq\x01U\x04\xc3\xa4bcq\x02s."
        loaded = sp.loads(py2)
        self.assertEqual(loaded, {b"store": b"\xc3\xa4bc"})
        again = pickle.loads(sp.dumps(loaded), encoding="bytes")
        self.assertEqual(again, loaded)


class ValuesTest(unittest.TestCase):
    def test_parse_value(self):
        self.assertIs(values.parse_value("yes", False), True)
        self.assertEqual(values.parse_value("42", 1), 42)
        self.assertEqual(values.parse_value("1.5", 0.0), 1.5)
        self.assertEqual(values.parse_value("hi", "x"), "hi")
        self.assertEqual(values.parse_value("=[1, 2]", 0), [1, 2])
        self.assertEqual(values.parse_value("äö", b"x"), "äö".encode("utf-8"))
        with self.assertRaises(ValueError):
            values.parse_value("abc", 1)


class SaveTest(TmpDirTest):
    def _make_save(self, path, signed=False, keys=()):
        with fake_renpy() as fr:
            roots = {"store.money": 10, "store._internal": 1,
                     "store.inv": fr.revertable.RevertableList(["a"])}
            log = pickle.dumps((roots, fr.rollback.RollbackLog()), 2)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("screenshot.png", b"\x89PNG fake")
            zf.writestr("extra_info", "Chapter 1".encode("utf-8"))
            zf.writestr("json", b'{"_save_name": "Chapter 1"}')
            zf.writestr("renpy_version", "8.3.4")
            zf.writestr("log", log)
            if signed:
                zf.writestr("signatures", savetoken.sign_data(log, keys))

    def test_edit_save(self):
        path = self.tmp / "1-1-LT1.save"
        self._make_save(path)
        s = saves.SaveFile(path)
        self.assertEqual(s.extra_info, "Chapter 1")
        self.assertFalse(s.is_signed)
        s.variables["store.money"] = 5000
        result = s.write()
        self.assertIsNotNone(result.backup)
        self.assertTrue(result.backup.exists())

        with zipfile.ZipFile(path) as zf:
            self.assertEqual(zf.read("screenshot.png"), b"\x89PNG fake")
            self.assertNotIn("signatures", zf.namelist())
            with fake_renpy() as fr:
                roots, _ = pickle.loads(zf.read("log"))
                self.assertEqual(roots["store.money"], 5000)
                self.assertIsInstance(roots["store.inv"], fr.revertable.RevertableList)

    def test_resign_signed_save(self):
        secret = 0x1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF
        keys = [(secret, savetoken.public_der(savetoken.public_key(secret)))]
        path = self.tmp / "auto-1-LT1.save"
        self._make_save(path, signed=True, keys=keys)
        s = saves.SaveFile(path)
        self.assertTrue(s.is_signed)
        s.variables["store.money"] = 1
        result = s.write(keys=keys)
        self.assertTrue(result.signed)
        with zipfile.ZipFile(path) as zf:
            self.assertTrue(savetoken.verify_signatures(zf.read("log"), zf.read("signatures").decode()))

    def test_list_saves_newest_first(self):
        import os
        a, b = self.tmp / "1-1.save", self.tmp / "1-2.save"
        self._make_save(a)
        self._make_save(b)
        os.utime(a, (1000, 1000))
        self.assertEqual([e.path for e in saves.list_saves([self.tmp])], [b, a])

    def test_persistent(self):
        secret = 987654321
        keys = [(secret, savetoken.public_der(savetoken.public_key(secret)))]
        with fake_renpy() as fr:
            p = fr.persistent.Persistent()
            p._seen_ever = {"start": True}
            p.gallery_unlocked = False
            data = pickle.dumps(p, 2)
        path = self.tmp / "persistent"
        path.write_bytes(zlib.compress(data, 3) + savetoken.sign_data(data, keys).encode())

        pf = saves.PersistentFile(path)
        self.assertTrue(pf.is_signed)
        pf.variables["gallery_unlocked"] = True
        pf.write(keys=keys)

        d = zlib.decompressobj()
        new_data = d.decompress(path.read_bytes())
        self.assertTrue(savetoken.verify_signatures(new_data, d.unused_data.decode()))
        with fake_renpy():
            self.assertTrue(pickle.loads(new_data).gallery_unlocked)


class SaveTokenTest(unittest.TestCase):
    def test_sign_verify_and_der(self):
        secret = 0xC0FFEE
        der = savetoken.private_der(secret)
        self.assertEqual(len(der), 121)
        self.assertEqual(savetoken.parse_private_der(der), secret)
        pub = savetoken.public_key(secret)
        self.assertEqual(savetoken.parse_public_der(savetoken.public_der(pub)), pub)
        sig = savetoken.sign(secret, b"data")
        self.assertTrue(savetoken.verify(pub, b"data", sig))
        self.assertFalse(savetoken.verify(pub, b"other", sig))

    def test_curve_constants(self):
        p, n, (gx, gy) = savetoken._P, savetoken._N, savetoken._G
        b = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
        self.assertEqual((gy * gy - (gx ** 3 - 3 * gx + b)) % p, 0)
        self.assertIsNone(savetoken._mul(n, savetoken._G))

    def test_against_cryptography_if_available(self):
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        except ImportError:
            self.skipTest("cryptography not installed")
        key = ec.generate_private_key(ec.SECP256R1())
        secret = key.private_numbers().private_value
        der_pub = key.public_key().public_bytes(serialization.Encoding.DER,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
        self.assertEqual(savetoken.public_der(savetoken.public_key(secret)), der_pub)
        sig = savetoken.sign(secret, b"hello")
        r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
        key.public_key().verify(encode_dss_signature(r, s), b"hello", ec.ECDSA(hashes.SHA1()))


def make_rpyc(stmts_factory):
    with fake_renpy() as fr:
        stmts = stmts_factory(fr)
        payload = zlib.compress(pickle.dumps(({"version": 5003000, "key": "unlocked"}, stmts), 2))
    header = rpyc.RPYC2_HEADER
    table_len = 12 * 2
    start = len(header) + table_len
    return header + struct.pack("<III", 1, start, len(payload)) + struct.pack("<III", 0, 0, 0) + payload


class DecompilerTest(unittest.TestCase):
    def test_script(self):
        def build(fr):
            a, p = fr.ast, fr.parameter
            E = fr.astsupport.PyExpr
            menu = a.Menu(items=[
                ("Go left", "True", [a.Jump(target="left")]),
                ("Go right", E("money > 5"), [a.Python(code=fr.ast.PyCode("money -= 5")),
                                              a.Return()]),
            ])
            return [
                a.Init(priority=0, block=[a.Define(store="store", varname="e",
                                                   code=fr.ast.PyCode('Character("Eileen")'))]),
                a.Init(priority=0, block=[a.Default(store="store", varname="money",
                                                    code=fr.ast.PyCode("10"))]),
                a.Init(priority=-5, block=[a.Python(code=fr.ast.PyCode("x = 1\ny = 2"))]),
                a.Label(name="start", block=[
                    a.Scene(imspec=(("bg", "room"), None, None, [], None, None, []), layer="master"),
                    a.With(expr="None", paired="dissolve"),
                    a.Show(imspec=(("eileen", "happy"), None, None, ["left"], None, None, [])),
                    a.With(expr="dissolve"),
                    a.Say(who="e", what='Hello "world"\nbye'),
                    a.Say(what="Narration."),
                    a.Label(name="choice", block=[]),
                    a.Say(who="e", what="Where?", interact=False),
                    menu,
                    a.If(entries=[(E("money > 100"), [a.Say(what="Rich!")]),
                                  ("True", [a.Pass()])]),
                    a.Call(label="ending", arguments=p.ArgumentInfo(arguments=[(None, "1"), ("good", "True")])),
                    a.Label(name="_call_ending_1", block=[]),
                ]),
                a.Label(name="ending", parameters=p.Signature(parameters={
                    "n": p.Parameter(name="n", kind=1, default=None),
                    "good": p.Parameter(name="good", kind=1, default="False")}), block=[
                    a.Return(),
                ]),
                a.UserStatement(line='play music "theme.ogg" fadein 1.0'),
            ]

        out = rpyc.decompile(make_rpyc(build), "script.rpyc")
        expected = [
            'define e = Character("Eileen")',
            "default money = 10",
            "init -5 python:",
            "    x = 1",
            "    y = 2",
            "label start:",
            "    scene bg room",
            "    show eileen happy at left with dissolve",
            '    e "Hello \\"world\\"\\nbye"',
            '    "Narration."',
            "    menu choice:",
            '        e "Where?"',
            '        "Go left":',
            "            jump left",
            '        "Go right" if money > 5:',
            "            $ money -= 5",
            "            return",
            "    if money > 100:",
            '        "Rich!"',
            "    else:",
            "        pass",
            "    call ending(1, good=True) from _call_ending_1",
            "label ending(n, good=False):",
            "    return",
            'play music "theme.ogg" fadein 1.0',
        ]
        body = [l for l in out.splitlines()[1:] if l.strip()]
        self.assertEqual(body, expected, "\n" + out)

    def test_atl_and_screen(self):
        def build(fr):
            a, atl, sl = fr.ast, fr.atl, fr.slast
            block = atl.RawBlock(statements=[
                atl.RawMultipurpose(warper="linear", duration="1.0",
                                    properties=[("xalign", "1.0")], expressions=[], splines=[]),
                atl.RawRepeat(),
            ])
            screen = sl.SLScreen(name="hud", tag="hud", children=[
                sl.SLDisplayable(displayable=fr.text.Text, style="text", positional=['"[money]"'],
                                 keyword=[("xalign", "0.5")], children=[]),
                sl.SLIf(entries=[("money > 0", sl.SLBlock(keyword=[], children=[
                    sl.SLDisplayable(displayable=fr.text.Text, style="text", positional=['"Rich"'],
                                     keyword=[], children=[])]))]),
            ])
            return [a.Image(imgname=("logo",), code=None, atl=block),
                    a.Init(priority=-500, block=[a.Screen(screen=screen)])]

        out = rpyc.decompile(make_rpyc(build))
        self.assertIn("image logo:\n    linear 1.0 xalign 1.0\n    repeat", out)
        self.assertIn('screen hud:\n    tag hud\n    text "[money]":\n        xalign 0.5\n'
                      '    if money > 0:\n        text "Rich"', out)

    def test_save_directory_detection(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "game").mkdir()

            def build(fr):
                a = fr.ast
                return [a.Init(priority=0, block=[a.Define(store="store.config", varname="save_directory",
                                                           code=fr.ast.PyCode('"MyGame-1234"'))])]

            (root / "game" / "options.rpyc").write_bytes(make_rpyc(build))
            info = game.GameInfo.load(root / "game")
            self.assertEqual(info.root, root.resolve())
            self.assertEqual(info.save_directory, "MyGame-1234")


class PatchTest(TmpDirTest):
    def test_apply_and_remove(self):
        game.apply_patch(self.tmp, {"console", "developer"})
        self.assertEqual(game.patch_status(self.tmp), {"console", "developer"})
        text = game.patch_path(self.tmp).read_text()
        self.assertIn("config.console = True", text)
        game.patch_path(self.tmp).with_suffix(".rpyc").write_bytes(b"x")
        self.assertTrue(game.remove_patch(self.tmp))
        self.assertEqual(game.patch_status(self.tmp), set())
        self.assertFalse(game.patch_path(self.tmp).with_suffix(".rpyc").exists())


if __name__ == "__main__":
    unittest.main()
