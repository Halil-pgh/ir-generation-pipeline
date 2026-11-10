"""The named points of the IR (anchors), and every point an object holds.

A reference ``"<id>.<name>"`` names one of these points (analysis §2.3):

- every object, zone, ``frame`` and ``safe`` has the points of its box:
  ``left_top``, ``center_top``, ``right_top``, ``left_center``, ``center``,
  ``right_center``, ``left_bottom``, ``center_bottom``, ``right_bottom``;
- texts, formulas and stacks also have ``left_baseline``,
  ``center_baseline`` and ``right_baseline``;
- an object with a ``center`` field (a circle, an arc, a regular polygon…)
  means that field by ``center``, not the middle of its box;
- open shapes (line, polyline, arc, path) have ``start``, ``end`` and
  ``mid`` (halfway along by length); ``tail`` and ``tip`` are the same as
  ``start`` and ``end``, and read better for arrows.

``frame`` is the whole picture and ``safe`` the header's safe area; neither
may be used as an id.
"""

from collections.abc import Callable, Iterator
from typing import Any, Final

from irpipe.schema.ir import (
    XY,
    Arc,
    Circle,
    CubicTo,
    Ellipse,
    Line,
    LineTo,
    Math,
    OnRef,
    Path,
    Point,
    Polygon,
    Polyline,
    QuadTo,
    Rect,
    RegularPolygon,
    Sector,
    Stack,
    Subpath,
    Text,
)
from irpipe.schema.ir.objects import ObjectBase

BOX_ANCHORS: Final = (
    "left_top",
    "center_top",
    "right_top",
    "left_center",
    "center",
    "right_center",
    "left_bottom",
    "center_bottom",
    "right_bottom",
)
BASELINE_ANCHORS: Final = ("left_baseline", "center_baseline", "right_baseline")
PATH_ANCHORS: Final = ("start", "end", "mid", "tail", "tip")
SAME_AS: Final = {"tail": "start", "tip": "end"}
RESERVED: Final = ("frame", "safe")
"""Names of the picture's own boxes, which references may use and ids may not."""

Centered = Circle | Ellipse | Rect | RegularPolygon | Arc | Sector
"""Objects whose ``center`` anchor is their ``center`` field."""

POINT_FIELDS: Final = ("center", "start", "end", "at", "pivot")
"""Fields that hold one point (a group's ``translate`` is a shift, not a point)."""


def anchor_names(obj: ObjectBase) -> tuple[str, ...]:
    """Every anchor name ``obj`` has."""
    names: tuple[str, ...] = BOX_ANCHORS
    if isinstance(obj, Text | Math | Stack):
        names += BASELINE_ANCHORS
    if isinstance(obj, Line | Polyline | Arc | Path):
        names += PATH_ANCHORS
    return names


def split_ref(ref: str) -> tuple[str, str]:
    """``"v.label.center"`` -> (``"v.label"``, ``"center"``): the last part is the anchor."""
    target, _, name = ref.rpartition(".")
    return target, name


def map_points[T: ObjectBase](obj: T, change: Callable[[Point, str], XY]) -> T:
    """``obj`` with ``change(point, path)`` put in place of every point it holds.

    ``path`` is the field's JSON path inside the object (``"points[2]"``).
    """
    update: dict[str, Any] = {}
    for name in POINT_FIELDS:
        value = getattr(obj, name, None)
        if value is not None:
            update[name] = change(value, name)
    if isinstance(obj, Polygon | Polyline):
        update["points"] = tuple(change(p, f"points[{k}]") for k, p in enumerate(obj.points))
    if isinstance(obj, Path):
        update["subpaths"] = tuple(
            _map_subpath(s, change, f"subpaths[{k}]") for k, s in enumerate(obj.subpaths)
        )
    return obj.model_copy(update=update) if update else obj


def points_of(obj: ObjectBase) -> Iterator[tuple[str, Point]]:
    """Every point ``obj`` holds, with its path inside the object."""
    found: list[tuple[str, Point]] = []

    def keep(point: Point, path: str) -> XY:
        found.append((path, point))
        return (0.0, 0.0)

    map_points(obj, keep)
    return iter(found)


def references(obj: ObjectBase) -> Iterator[tuple[str, str | OnRef]]:
    """Every reference among ``obj``'s points, with its path."""
    for path, point in points_of(obj):
        if isinstance(point, str | OnRef):
            yield path, point


def xy(point: Point) -> tuple[float, float]:
    """The numbers of a point the place stage has already resolved."""
    if isinstance(point, str | OnRef):
        raise TypeError(f"unresolved reference {point!r}; the place stage resolves references")
    return (float(point[0]), float(point[1]))


def _map_subpath(subpath: Subpath, change: Callable[[Point, str], XY], path: str) -> Subpath:
    segments: list[LineTo | QuadTo | CubicTo] = []
    for k, segment in enumerate(subpath.segments):
        where = f"{path}.segments[{k}]"
        match segment:
            case LineTo(line=p):
                segments.append(LineTo.model_construct(line=change(p, f"{where}.line")))
            case QuadTo(quad=(c, p)):
                quad = (change(c, f"{where}.quad[0]"), change(p, f"{where}.quad[1]"))
                segments.append(QuadTo.model_construct(quad=quad))
            case CubicTo(cubic=(c1, c2, p)):
                cubic = (
                    change(c1, f"{where}.cubic[0]"),
                    change(c2, f"{where}.cubic[1]"),
                    change(p, f"{where}.cubic[2]"),
                )
                segments.append(CubicTo.model_construct(cubic=cubic))
    return subpath.model_copy(
        update={"start": change(subpath.start, f"{path}.start"), "segments": tuple(segments)}
    )
