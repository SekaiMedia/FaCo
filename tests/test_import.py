"""Alle Module der Integration importieren, mit nachgebautem Home Assistant.

Fängt Fehler, die erst beim Laden auffallen (Beta 13: Feldreihenfolge einer Dataclass), auch ohne
installiertes Home Assistant. Ob die echten Schnittstellen passen, prüft das nicht.
"""

import importlib
import importlib.abc
import importlib.machinery
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
STUBBED = ("homeassistant", "voluptuous")


class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return mock.MagicMock(name=f"{cls.__name__}.{name}")


class _Base(metaclass=_Meta):
    """Ersatz für alles Großgeschriebene: erbbar (auch mit domain=), aufrufbar, mit beliebigen Attributen."""

    def __init__(self, *args, **kwargs):
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()

    def __class_getitem__(cls, item):
        return cls

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return mock.MagicMock(name=name)

    def __call__(self, *args, **kwargs):
        return mock.MagicMock()


class _Module(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        # Großgeschriebenes kann eine Basisklasse sein, der Rest wird nur aufgerufen
        value = type(name, (_Base,), {}) if name[:1].isupper() else mock.MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, value)
        return value


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in STUBBED:
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        module = _Module(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        pass


class ImportOhneHomeAssistant(unittest.TestCase):
    def test_alle_module_laden(self):
        finder = _Finder()
        saved = dict(sys.modules)
        sys.meta_path.insert(0, finder)
        sys.path.insert(0, str(ROOT))
        try:
            for path in sorted((ROOT / "custom_components" / "facade_conductor").glob("*.py")):
                name = "custom_components.facade_conductor" + ("" if path.stem == "__init__" else f".{path.stem}")
                with self.subTest(module=name):
                    importlib.import_module(name)
        finally:
            sys.meta_path.remove(finder)
            sys.path.remove(str(ROOT))
            for name in set(sys.modules) - set(saved):
                del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
