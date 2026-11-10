"""Remembering measurements, in memory and, for formulas, on disk.

Typesetting a formula runs latex and dvisvgm (a few tenths of a second), and
the agent measures the same formulas again on every turn. ``CachedMetrics``
wraps any provider: every answer is kept in memory, and formulas also in a
folder, so a later run on the same machine does not typeset them again.

A file is written under a temporary name and renamed into place, which is
atomic: two runs writing the same formula at once cannot leave a half
file, so the folder can be shared without a lock.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from irpipe.metrics.base import MathBox, TextBox, TextMetrics
from irpipe.metrics.svgpath import Subpath

FORMAT = 1
"""Bump when MathBox changes, so old cache files are not read."""


class CachedMetrics(TextMetrics):
    """``inner``, answering repeated questions from memory and formulas from ``folder``."""

    name = "cached"

    def __init__(self, inner: TextMetrics, folder: Path | None = None) -> None:
        self.inner = inner
        self.folder = folder
        self._texts: dict[tuple[Any, ...], TextBox] = {}
        self._formulas: dict[tuple[Any, ...], MathBox] = {}

    def text(
        self,
        text: str,
        *,
        font: str,
        size: float,
        weight: Literal["regular", "bold"],
        italic: bool,
    ) -> TextBox:
        key = (text, font, size, weight, italic)
        if key not in self._texts:
            self._texts[key] = self.inner.text(
                text, font=font, size=size, weight=weight, italic=italic
            )
        return self._texts[key]

    def math(self, tex: str, *, math_font: str, size: float) -> MathBox:
        key = (tex, math_font, size)
        if key not in self._formulas:
            self._formulas[key] = self._from_disk(key) or self._typeset(key)
        return self._formulas[key]

    def missing_fonts(self, families: Any) -> list[str]:
        return self.inner.missing_fonts(families)

    def file_for(self, key: tuple[Any, ...]) -> Path | None:
        if self.folder is None:
            return None
        text = json.dumps([FORMAT, self.inner.name, *key], ensure_ascii=False)
        return self.folder / f"{hashlib.sha256(text.encode()).hexdigest()}.json"

    def _typeset(self, key: tuple[Any, ...]) -> MathBox:
        tex, math_font, size = key
        box = self.inner.math(tex, math_font=math_font, size=size)
        path = self.file_for(key)
        if path is not None:
            _write_atomically(path, _dump(box))
        return box

    def _from_disk(self, key: tuple[Any, ...]) -> MathBox | None:
        path = self.file_for(key)
        if path is None or not path.exists():
            return None
        try:
            return _load(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError):
            return None  # a damaged file is typeset again and replaced


def _dump(box: MathBox) -> dict[str, Any]:
    return {
        "width": box.width,
        "ascent": box.ascent,
        "descent": box.descent,
        "outlines": [
            {"start": s.start, "segments": s.segments, "closed": s.closed} for s in box.outlines
        ],
    }


def _load(data: dict[str, Any]) -> MathBox:
    def point(p: list[float]) -> tuple[float, float]:
        return (float(p[0]), float(p[1]))

    outlines = tuple(
        Subpath(
            point(s["start"]),
            [(kind, tuple(point(p) for p in pts)) for kind, pts in s["segments"]],
            bool(s["closed"]),
        )
        for s in data["outlines"]
    )
    return MathBox(
        width=float(data["width"]),
        ascent=float(data["ascent"]),
        descent=float(data["descent"]),
        outlines=outlines,
    )


def _write_atomically(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        json.dump(data, file)
    os.replace(temporary, path)


def default_folder() -> Path:
    """$XDG_CACHE_HOME/irpipe/metrics, or ~/.cache/irpipe/metrics."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "irpipe" / "metrics"
