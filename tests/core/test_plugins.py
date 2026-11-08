"""load_plugins: importing a package imports every module in it, so new files register."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from irpipe.core import PluginLoadError, load_plugins


@pytest.fixture
def plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A directory on sys.path for throwaway plugin packages; forgotten afterwards."""
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in list(sys.modules):
        if name.split(".")[0] in {"toyplugins", "toymodule"}:
            del sys.modules[name]


def make_files(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_every_module_in_the_package_is_imported(plugin_root: Path) -> None:
    make_files(
        plugin_root,
        {
            "toyplugins/__init__.py": "",
            "toyplugins/first.py": "LOADED = True\n",
            "toyplugins/nested/__init__.py": "",
            "toyplugins/nested/second.py": "LOADED = True\n",
        },
    )
    loaded = load_plugins(["toyplugins"])
    assert sorted(loaded) == [
        "toyplugins",
        "toyplugins.first",
        "toyplugins.nested",
        "toyplugins.nested.second",
    ]
    assert "toyplugins.nested.second" in sys.modules


def test_a_single_module_can_be_a_plugin(plugin_root: Path) -> None:
    make_files(plugin_root, {"toymodule.py": "LOADED = True\n"})
    assert load_plugins(["toymodule"]) == ["toymodule"]


def test_a_broken_module_is_named(plugin_root: Path) -> None:
    make_files(
        plugin_root,
        {"toyplugins/__init__.py": "", "toyplugins/broken.py": "import does_not_exist\n"},
    )
    with pytest.raises(PluginLoadError, match=r"'toyplugins\.broken'.*ModuleNotFoundError"):
        load_plugins(["toyplugins"])


def test_a_missing_package_is_named(plugin_root: Path) -> None:
    with pytest.raises(PluginLoadError, match="'toyplugins'"):
        load_plugins(["toyplugins"])
