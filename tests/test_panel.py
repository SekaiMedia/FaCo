"""Die Einstellungsseite: Texte auf Deutsch und Englisch gleich, Auswahllisten passend zu const.py."""

import ast
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

BASE = Path(__file__).parents[1] / "custom_components" / "facade_conductor"
PANEL = (BASE / "frontend" / "panel.js").read_text(encoding="utf-8")
STRINGS = json.loads((BASE / "frontend" / "strings.json").read_text(encoding="utf-8"))


def _const(name):
    tree = ast.parse((BASE / "const.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == name)
    if isinstance(node.value, ast.List | ast.Tuple):
        return [e.value if isinstance(e, ast.Constant) else _const_value(tree, e.id) for e in node.value.elts]
    return node.value.value


def _const_value(tree, name):
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == name)
    return node.value.value


def _js_list(name):
    match = re.search(rf"const {name} = \[(.*?)\];", PANEL)
    return re.findall(r'"(\w+)"', match.group(1))


class Einstellungsseite(unittest.TestCase):
    def test_gleiche_schluessel(self):
        self.assertEqual(set(STRINGS["de"]), set(STRINGS["en"]))

    def test_texte_mit_version_laden(self):
        # ohne die Versionsnummer zeigte der Browser nach einem Update Schlüssel statt Texte
        self.assertIn("strings.json${new URL(import.meta.url).search}", PANEL)

    def test_listen_wie_in_const(self):
        self.assertEqual(_js_list("MODES"), _const("MODES"))
        self.assertEqual(_js_list("DIRECTIONS"), _const("DIRECTION_OPTIONS"))
        self.assertEqual(_js_list("POSITIONS"), list(_const("POSITION_KEYS")))

    def test_jeder_reiter_hat_seite(self):
        for tab in _js_list("TABS"):
            with self.subTest(tab=tab):
                self.assertRegex(PANEL, rf"\n  _{tab}\(")

    def test_jede_rubrik_hat_inhalt(self):
        self.assertGreaterEqual(len(_js_list("SECTIONS")), 6)
        for section in _js_list("SECTIONS"):
            with self.subTest(section=section):
                self.assertRegex(PANEL, rf"\n  _sec_{section}\(")

    @unittest.skipUnless(shutil.which("node"), "Node.js fehlt")
    def test_uhrzeit_lesen(self):
        source = re.search(r"const parseTime = .*?\n\};\n", PANEL, re.S).group(0)
        cases = {"7": "07:00", "730": "07:30", "7:30": "07:30", "07:30": "07:30", "23:59": "23:59", "0": "00:00",
                 "24:00": None, "7:60": None, "7.30": None, "": None, "abc": None}
        script = source + f"console.log(JSON.stringify({json.dumps(list(cases))}.map((t) => parseTime(t) ?? null)));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(dict(zip(cases, json.loads(out))), cases)

    @unittest.skipUnless(shutil.which("node"), "Node.js fehlt")
    def test_suche(self):
        source = re.search(r"const matches = .*?;\n", PANEL, re.S).group(0)
        text = "tyds 08 binary_sensor.tyds_08_kuche_contact küche"
        cases = {"": True, "küche": True, "KÜCHE tyds": True, "08 küche": True, "büro": False, "küche büro": False}
        script = source + f"console.log(JSON.stringify({json.dumps(list(cases))}.map((q) => matches(q, {json.dumps(text)}))));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(dict(zip(cases, json.loads(out))), cases)

    def test_jeder_text_vorhanden(self):
        used = set(re.findall(r'_t\("(\w+)"', PANEL))
        used |= {f"mode_{m}" for m in _js_list("MODES")}
        used |= {f"dir_{d}" for d in _js_list("DIRECTIONS")}
        used |= {f"pos_{p}" for p in _js_list("POSITIONS")}
        used |= {f"means_{m}" for m in _const("WINDOW_MEANS_OPTIONS")}
        used |= {f"tab_{t}" for t in _js_list("TABS")}
        used |= {f"sec_{s}" for s in _js_list("SECTIONS")}
        used |= {f"mode_{m}_text" for m in _js_list("MODES")}
        used |= {f"phase_{p}" for p in ("day", "dusk", "night")}
        self.assertGreater(len(used), 40)
        for lang in ("de", "en"):
            with self.subTest(lang=lang):
                self.assertEqual(used - set(STRINGS[lang]), set())


if __name__ == "__main__":
    unittest.main()
