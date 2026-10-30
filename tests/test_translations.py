"""Jeder Schritt und Menüpunkt der Einrichtung braucht Texte, auf Deutsch und Englisch gleich."""

import ast
import json
import unittest
from pathlib import Path

BASE = Path(__file__).parents[1] / "custom_components" / "facade_conductor"
LANGS = {lang: json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8")) for lang in ("de", "en")}

# Klasse im config_flow.py → Ort der Texte in der Sprachdatei
SECTIONS = {
    "FacadeConductorConfigFlow": ("config",),
    "HouseOptionsFlow": ("options",),
    "RoomSubentryFlow": ("config_subentries", "room"),
}


def _keys(node, prefix=""):
    out = set()
    for key, value in node.items():
        out.add(prefix + key)
        if isinstance(value, dict):
            out |= _keys(value, prefix + key + ".")
    return out


def _flows():
    """Schritte und Menüpunkte je Klasse, aus dem Quelltext gelesen."""
    tree = ast.parse((BASE / "config_flow.py").read_text(encoding="utf-8"))
    flows = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in SECTIONS):
        steps = {f.name.removeprefix("async_step_") for f in cls.body if isinstance(f, ast.AsyncFunctionDef) and f.name.startswith("async_step_")}
        menus = {}
        for call in (n for n in ast.walk(cls) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "async_show_menu"):
            kw = {k.arg: k.value for k in call.keywords}
            menus[kw["step_id"].value] = [e.value for e in kw["menu_options"].elts]
        flows[cls.name] = (steps, menus)
    return flows


class Uebersetzungen(unittest.TestCase):
    def test_gleiche_schluessel(self):
        self.assertEqual(_keys(LANGS["de"]), _keys(LANGS["en"]))

    def test_jeder_schritt_hat_text(self):
        for cls, (steps, menus) in _flows().items():
            for lang, data in LANGS.items():
                node = data
                for part in SECTIONS[cls]:
                    node = node[part]
                for step in steps:
                    with self.subTest(cls=cls, step=step, lang=lang):
                        self.assertIn(step, node["step"])
                for step, options in menus.items():
                    for option in options:
                        with self.subTest(cls=cls, menu=step, option=option, lang=lang):
                            self.assertIn(option, steps, "Menüpunkt ohne Schritt")
                            self.assertIn(option, node["step"][step]["menu_options"])

    def test_jeder_grund_hat_text(self):
        tree = ast.parse((BASE / "engine.py").read_text(encoding="utf-8"))
        reason_cls = next(c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "Reason")
        reasons = {s.value.value for s in reason_cls.body if isinstance(s, ast.Assign)}
        self.assertGreater(len(reasons), 5)
        for lang, data in LANGS.items():
            with self.subTest(lang=lang):
                self.assertEqual(set(data["entity"]["sensor"]["reason"]["state"]), reasons)


if __name__ == "__main__":
    unittest.main()
