"""Was erst beim Import in Home Assistant auffiele; die Tests laufen ohne Home Assistant."""

import ast
import unittest
from pathlib import Path

BASE = Path(__file__).parents[1] / "custom_components" / "facade_conductor"


class Struktur(unittest.TestCase):
    def test_dataclass_felder_in_erlaubter_reihenfolge(self):
        # ein Feld ohne Vorgabe nach einem mit Vorgabe lässt den Import scheitern (Beta 13)
        for path in BASE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                if not any(getattr(d, "id", getattr(d, "func", None) and getattr(d.func, "id", None)) == "dataclass" for d in cls.decorator_list):
                    continue
                seen_default = None
                for stmt in cls.body:
                    if not isinstance(stmt, ast.AnnAssign):
                        continue
                    name = stmt.target.id
                    with self.subTest(file=path.name, cls=cls.name, field=name):
                        if stmt.value is None:
                            self.assertIsNone(seen_default, f"{name} ohne Vorgabe nach {seen_default}")
                        else:
                            seen_default = name


    def test_kein_via_device(self):
        # via_device ist seit Home Assistant 2026.8 abgekündigt und bricht in 2027.8; via_device_id ersetzt es
        for path in BASE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = [k.arg for n in ast.walk(tree) if isinstance(n, ast.Call) for k in n.keywords if k.arg == "via_device"]
            with self.subTest(file=path.name):
                self.assertEqual(used, [])


    def test_kein_bereich_am_geraet(self):
        # ein Bereich am Raumgerät steht seit HA 2026.8 vor jeder neuen Entitäts-ID: aus „Büro“ würde buro_buro_…
        for path in BASE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            calls = [
                n.func.attr
                for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "async_update_device"
                and any(k.arg == "area_id" for k in n.keywords)
            ]
            with self.subTest(file=path.name):
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
