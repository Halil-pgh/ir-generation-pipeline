"""Picture: the LIR flattened into the frame, with owners, relations and the color behind."""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe import colormath
from irpipe.checks.picture import Picture, beyond
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.frontend.resolve import Resolver
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema.ir import IRDocument

type Make = Callable[..., IRDocument]

DISC: dict[str, Any] = {"id": "c", "type": "circle", "center": [1, 0], "radius": 0.5}


def picture(document: IRDocument) -> Picture:
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    placed, _ = place(normal, measured)
    assert placed is not None
    return Picture(Resolver(placed, measured).resolve(), normal)


def test_primitives_land_in_the_frame_through_their_groups(document: Make) -> None:
    group = {"id": "g", "type": "group", "children": ["c"], "translate": [2, 1]}
    (drawn,) = picture(document([{**DISC, "stroke_width": 12}, group])).drawn
    assert drawn.owner == "c"
    assert drawn.reach == pytest.approx((2.45, 0.45, 3.55, 1.55))  # half of 12 px is 0.05
    assert drawn.fill is None and drawn.line is not None


def test_owners_keep_their_paths_and_drawing_order(document: Make) -> None:
    objects = [DISC, {"id": "t", "type": "text", "text": "x", "at": [0, 0], "z": -1}]
    seen = picture(document(objects))
    assert [(d.owner, d.order, d.is_text) for d in seen.drawn] == [("t", 0, True), ("c", 1, False)]
    assert (seen.path("c"), seen.path("t")) == ("objects[0]", "objects[1]")


def test_relations_come_from_references_groups_and_operands(document: Make) -> None:
    objects = [
        DISC,
        {"id": "t", "type": "text", "text": "x", "at": "c.center"},
        {"id": "u", "type": "text", "text": "y", "next_to": "t"},
        {"id": "r", "type": "region", "shape": {"union": ["c", "d"]}},
        {"id": "d", "type": "circle", "center": [3, 0], "radius": 1},
        {"id": "e", "type": "circle", "center": [5, 0], "radius": 1},
        {"id": "f", "type": "circle", "center": [7, 0], "radius": 1},
        {"id": "g", "type": "group", "children": ["e", "f"]},
    ]
    seen = picture(document(objects))
    for first, second in [("t", "c"), ("u", "t"), ("r", "c"), ("r", "d"), ("e", "f"), ("g", "e")]:
        assert seen.related(first, second) and seen.related(second, first)
    assert not seen.related("c", "d")
    assert not seen.related("t", "e")


def test_the_color_behind_is_the_fills_drawn_earlier_over_the_background(document: Make) -> None:
    under = {**DISC, "id": "a", "center": [0, 0], "radius": 2, "fill": "#FFFFFF", "color": "none"}
    veil = {**DISC, "id": "b", "center": [0, 0], "radius": 1, "fill": "#000000",
            "fill_opacity": 0.5, "color": "none"}  # fmt: skip
    seen = picture(document([under, veil]))
    assert seen.color_at(5, 0, before=2) == colormath.rgb("#0E1117")
    assert seen.color_at(1.5, 0, before=2) == (1, 1, 1)
    assert seen.color_at(0, 0, before=2) == pytest.approx((0.5, 0.5, 0.5))
    assert seen.color_at(0, 0, before=1) == (1, 1, 1)  # the veil is drawn later


def test_beyond_names_each_edge_passed() -> None:
    assert beyond((-1, 0, 5, 2), (0, 0, 4, 4)) == [("left", 1), ("right", 1)]
    assert beyond((0, 0, 4, 4), (0, 0, 4, 4)) == []
