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


if __name__ == "__main__":
    unittest.main()
