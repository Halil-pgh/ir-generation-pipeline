"""Imports plugin packages so that their ``@register`` decorators run.

A plugin registers itself when its module is imported. ``load_plugins``
imports every module inside the given packages, recursively, so adding a
plugin means adding a file to such a package; nothing else has to import it.
Packages outside irpipe are listed in pipeline.toml in the same way.
"""

import importlib
import pkgutil
from collections.abc import Iterable
from types import ModuleType

from irpipe.core.errors import PluginLoadError


def load_plugins(packages: Iterable[str]) -> list[str]:
    """Import each package and every module below it; return the imported module names."""
    loaded: list[str] = []
    for package_name in packages:
        package = _import(package_name)
        loaded.append(package_name)
        search_path = getattr(package, "__path__", None)
        if search_path is None:  # a single module, not a package: importing it was enough
            continue
        for module in pkgutil.walk_packages(search_path, prefix=f"{package_name}.", onerror=_fail):
            _import(module.name)
            loaded.append(module.name)
    return loaded


def _import(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except Exception as exc:
        raise PluginLoadError(
            f"could not import plugin module '{name}': {type(exc).__name__}: {exc}"
        ) from exc


def _fail(name: str) -> None:
    """walk_packages calls this when it cannot import a subpackage it found."""
    raise PluginLoadError(f"could not import plugin package '{name}'")
