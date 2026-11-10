"""SVG path data: the commands glyph outlines use, absolute and relative."""

import pytest

from irpipe.metrics.svgpath import PathDataError, parse_path


def test_lines_and_a_closed_square() -> None:
    (square,) = parse_path("M0 0 L1 0 H1 V1 H0 Z")
    assert square.start == (0, 0)
    assert [p for _, (p,) in square.segments] == [(1, 0), (1, 0), (1, 1), (0, 1)]
    assert square.closed


def test_relative_commands_move_from_the_pen() -> None:
    (path,) = parse_path("m1 1 l1 0 0 1 h-1 v-1")
    assert [p for _, (p,) in path.segments] == [(2, 1), (2, 2), (1, 2), (1, 1)]


def test_pairs_after_a_move_are_lines() -> None:
    (path,) = parse_path("M0 0 1 0 1 1")
    assert [kind for kind, _ in path.segments] == ["line", "line"]


def test_a_smooth_cubic_mirrors_the_previous_control() -> None:
    (path,) = parse_path("M0 0 C0 1 1 1 1 0 S2 -1 2 0")
    assert path.segments[1] == ("cubic", ((1, -1), (2, -1), (2, 0)))


def test_a_smooth_quadratic_mirrors_the_previous_control() -> None:
    (path,) = parse_path("m5 5 q1 1 2 0 t2 0")
    assert path.segments == [("quad", ((6, 6), (7, 5))), ("quad", ((8, 4), (9, 5)))]


def test_numbers_may_run_together_as_dvisvgm_writes_them() -> None:
    (path,) = parse_path("M1.5-2.25L.5.75")
    assert path.start == (1.5, -2.25)
    assert path.segments == [("line", ((0.5, 0.75),))]


def test_several_subpaths_and_drawing_on_after_a_close() -> None:
    first, second = parse_path("M0 0 L1 0 Z M5 5 L6 5")
    assert first.closed and not second.closed


@pytest.mark.parametrize(
    ("data", "message"), [("M0 0 A1 1 0 0 1 2 2", "arcs"), ("0 0", "start with")]
)
def test_what_glyphs_never_need_is_refused(data: str, message: str) -> None:
    with pytest.raises(PathDataError, match=message):
        parse_path(data)
