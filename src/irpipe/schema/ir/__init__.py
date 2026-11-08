"""IR 1.0: the library-independent description of one picture.

    from irpipe.schema.ir import IRDocument
    document = IRDocument.model_validate_json(path.read_text())

Module map:
    document.py  IRDocument (the whole ir.json), IRBody (what the agent writes)
    header.py    IRHeader (what the orchestrator writes and locks)
    objects.py   the core objects: circle, rect, line, path, text, group
    common.py    ids, points, boxes, sizes
"""

from irpipe.schema.ir.common import Box, Id, Point, Role, Size
from irpipe.schema.ir.document import BODY_FIELDS, HEADER_FIELDS, IRBody, IRDocument, Space
from irpipe.schema.ir.header import (
    IR_VERSION,
    FrameHeader,
    IRHeader,
    Style,
    SubtitleHeader,
    TypographyHeader,
)
from irpipe.schema.ir.objects import (
    Anchor,
    Circle,
    CubicTo,
    Group,
    IRObject,
    Line,
    LineTo,
    Path,
    QuadTo,
    Rect,
    Segment,
    Subpath,
    Text,
)

__all__ = [
    "BODY_FIELDS",
    "HEADER_FIELDS",
    "IR_VERSION",
    "Anchor",
    "Box",
    "Circle",
    "CubicTo",
    "FrameHeader",
    "Group",
    "IRBody",
    "IRDocument",
    "IRHeader",
    "IRObject",
    "Id",
    "Line",
    "LineTo",
    "Path",
    "Point",
    "QuadTo",
    "Rect",
    "Role",
    "Segment",
    "Size",
    "Space",
    "Style",
    "Subpath",
    "SubtitleHeader",
    "Text",
    "TypographyHeader",
]
