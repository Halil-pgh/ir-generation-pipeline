"""IR 1.0: the library-independent description of one picture.

    from irpipe.schema.ir import IRDocument
    document = IRDocument.model_validate_json(path.read_text())

Module map:
    document.py  IRDocument (the whole ir.json), IRBody (what the agent writes)
    header.py    IRHeader (what the orchestrator writes and locks)
    objects.py   the core objects: basic shapes, path, text, group
    common.py    ids, points, boxes, sizes
"""

from irpipe.schema.ir.common import Box, Id, Number, Point, Role, Size
from irpipe.schema.ir.document import BODY_FIELDS, HEADER_FIELDS, IRBody, IRDocument, Space
from irpipe.schema.ir.header import (
    IR_VERSION,
    FrameHeader,
    IRHeader,
    Style,
    SubtitleHeader,
    ThemeHeader,
    TypographyHeader,
    header_hash,
)
from irpipe.schema.ir.objects import (
    Anchor,
    Arc,
    Circle,
    CubicTo,
    Ellipse,
    Group,
    IRObject,
    Line,
    LineTo,
    Path,
    Polygon,
    Polyline,
    QuadTo,
    Rect,
    RegularPolygon,
    Sector,
    Segment,
    Shape,
    Subpath,
    Text,
)

__all__ = [
    "BODY_FIELDS",
    "HEADER_FIELDS",
    "IR_VERSION",
    "Anchor",
    "Arc",
    "Box",
    "Circle",
    "CubicTo",
    "Ellipse",
    "FrameHeader",
    "Group",
    "IRBody",
    "IRDocument",
    "IRHeader",
    "IRObject",
    "Id",
    "Line",
    "LineTo",
    "Number",
    "Path",
    "Point",
    "Polygon",
    "Polyline",
    "QuadTo",
    "Rect",
    "RegularPolygon",
    "Role",
    "Sector",
    "Segment",
    "Shape",
    "Size",
    "Space",
    "Style",
    "Subpath",
    "SubtitleHeader",
    "Text",
    "ThemeHeader",
    "TypographyHeader",
    "header_hash",
]
