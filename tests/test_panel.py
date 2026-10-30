"""Die Einstellungsseite: Texte auf Deutsch und Englisch gleich, Auswahllisten passend zu const.py."""

import ast
import json
import re
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

    def test_listen_wie_in_const(self):
        self.assertEqual(_js_list("MODES"), _const("MODES"))
        self.assertEqual(_js_list("DIRECTIONS"), _const("DIRECTION_OPTIONS"))
        self.assertEqual(_js_list("POSITIONS"), list(_const("POSITION_KEYS")))

    def test_jeder_text_vorhanden(self):
        used = set(re.findall(r'_t\("(\w+)"', PANEL))
        used |= {f"mode_{m}" for m in _js_list("MODES")}
        used |= {f"dir_{d}" for d in _js_list("DIRECTIONS")}
        used |= {f"pos_{p}" for p in _js_list("POSITIONS")}
        used |= {f"means_{m}" for m in _const("WINDOW_MEANS_OPTIONS")}
        used |= {f"tab_{t}" for t in ("overview", "rooms")}
        used |= {f"phase_{p}" for p in ("day", "dusk", "night")}
        self.assertGreater(len(used), 40)
        for lang in ("de", "en"):
            with self.subTest(lang=lang):
                self.assertEqual(used - set(STRINGS[lang]), set())


if __name__ == "__main__":
    unittest.main()
