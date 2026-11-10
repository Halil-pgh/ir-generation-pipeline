"""CachedMetrics: one question asked once; formulas kept on disk between runs."""

from pathlib import Path
from typing import Any, Literal

from irpipe.metrics import CachedMetrics, MathBox, TextBox, TextMetrics
from irpipe.metrics.svgpath import Subpath


class Counting(TextMetrics):
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def text(
        self, text: str, *, font: str, size: float, weight: Literal["regular", "bold"], italic: bool
    ) -> TextBox:
        self.calls += 1
        return TextBox(len(text) * size, size, 0)

    def math(self, tex: str, *, math_font: str, size: float) -> MathBox:
        self.calls += 1
        line = Subpath((0, 0), [("cubic", ((1, 1), (2, 1), (3, 0)))], closed=False)
        return MathBox(width=size, ascent=size / 2, descent=size / 4, outlines=(line,))


def ask(metrics: CachedMetrics) -> Any:
    return metrics.math("x^2", math_font="latin-modern", size=40)


def test_a_repeated_question_is_answered_from_memory() -> None:
    inner = Counting()
    metrics = CachedMetrics(inner)
    for _ in range(3):
        metrics.text("a", font="Inter", size=10, weight="regular", italic=False)
    assert inner.calls == 1


def test_a_formula_typeset_once_is_read_from_disk_by_the_next_run(tmp_path: Path) -> None:
    first = Counting()
    box = ask(CachedMetrics(first, tmp_path))
    second = Counting()
    again = ask(CachedMetrics(second, tmp_path))
    assert (first.calls, second.calls) == (1, 0)
    assert again == box
    assert [p.suffix for p in tmp_path.iterdir()] == [".json"]  # no temporary file left


def test_a_damaged_file_is_typeset_again(tmp_path: Path) -> None:
    metrics = CachedMetrics(Counting(), tmp_path)
    ask(metrics)
    (cached,) = tmp_path.iterdir()
    cached.write_text("{ not json")
    inner = Counting()
    assert ask(CachedMetrics(inner, tmp_path)).width == 40
    assert inner.calls == 1


def test_without_a_folder_nothing_is_written(tmp_path: Path) -> None:
    metrics = CachedMetrics(Counting(), None)
    ask(metrics)
    assert metrics.file_for(("x", "y", 1)) is None
