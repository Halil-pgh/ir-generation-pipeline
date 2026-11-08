"""A named collection of plugins of one kind: stages, checks, backends...

Every plug-in point in irpipe is a ``Registry``. A plugin joins by decorating
its class with ``@REGISTRY.register``; the pipeline later looks it up by the
name written in ``pipeline.toml``. Every kind of plugin follows this one pattern.
"""

import difflib
from collections.abc import Callable

from irpipe.core.errors import DuplicatePluginError, UnknownPluginError


class Registry[T]:
    """Maps names to plugins of one kind.

    ``kind`` is used in error messages ("unknown stage 'x'"). ``key`` tells the
    registry how to read an item's name. ``check``, if given, runs on every
    item before it is accepted and raises when the item is declared wrongly.
    """

    def __init__(
        self,
        kind: str,
        key: Callable[[T], str],
        check: Callable[[T], None] | None = None,
    ) -> None:
        self.kind = kind
        self._key = key
        self._check = check
        self._items: dict[str, T] = {}

    def register(self, item: T) -> T:
        """Add ``item`` and return it unchanged, so this works as a class decorator."""
        if self._check is not None:
            self._check(item)
        name = self._key(item)
        existing = self._items.get(name)
        if existing is not None and existing is not item:
            raise DuplicatePluginError(f"two different {self.kind}s are registered as '{name}'")
        self._items[name] = item
        return item

    def get(self, name: str) -> T:
        """Return the plugin called ``name``; the error lists close matches when there is none."""
        try:
            return self._items[name]
        except KeyError:
            raise UnknownPluginError(self._unknown_message(name)) from None

    def names(self) -> list[str]:
        """All registered names, sorted."""
        return sorted(self._items)

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    def _unknown_message(self, name: str) -> str:
        message = f"unknown {self.kind} '{name}'"
        close = difflib.get_close_matches(name, self._items, n=1)
        if close:
            message += f"; did you mean '{close[0]}'?"
        known = ", ".join(self.names()) or "none"
        return f"{message} (registered {self.kind}s: {known})"
