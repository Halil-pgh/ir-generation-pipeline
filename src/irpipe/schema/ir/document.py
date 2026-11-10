"""The IR body, and the whole document that puts header and body side by side.

``ir.json`` is one flat object, as in the analysis's draft: the header's
fields (version, intent, frame, typography, colors, styles) and the body's
(values, focus, extra_colors, zones, spaces, defs, objects, allow) next to each
other. They are still two models: ``IRHeader`` belongs to the orchestrator,
``IRBody`` to the agent, and no field belongs to both.

    document = IRDocument.model_validate_json(text)
    document.header      # IRHeader
    document.body        # IRBody
    IRDocument.join(header, body)
"""

from typing import Literal, Self

from pydantic import Field

from irpipe.core.allow import Allow
from irpipe.schema.base import StrictModel
from irpipe.schema.color import Color, ColorName, Mix
from irpipe.schema.ir.common import Box, Id, Name, Number, Point, PositiveNumber
from irpipe.schema.ir.header import IRHeader
from irpipe.schema.ir.objects import IRObject


class Space(StrictModel):
    """A coordinate system objects can be drawn in with ``"in": "<id>"`` (analysis §2.3).

    A point (x, y) of the space is drawn at ``origin + (x * ux, y * uy)``,
    where ``unit`` is ``ux`` (and ``uy``) frame units per space unit; lengths
    scale the same way. Stroke widths and type sizes do not. ``origin`` may
    be a reference (``"safe.center"``). ``kind`` leaves room for 3D later
    (analysis §5).
    """

    id: Id
    kind: Literal["cartesian2d"] = "cartesian2d"
    origin: Point = (0, 0)
    unit: PositiveNumber | tuple[PositiveNumber, PositiveNumber] = 1

    @property
    def units(self) -> tuple[float, float]:
        return self.unit if isinstance(self.unit, tuple) else (self.unit, self.unit)


class IRBody(StrictModel):
    """What the agent writes.

    ``values`` are named numbers the geometry's expressions may use
    (``"k": "44/17"``, then ``"radius": "k/2"``); they may use each other, but
    not in a loop. ``focus`` names the objects the eye should go to first. ``defs`` are
    shapes that are only operands (of a region, say) and are not drawn.
    ``zones`` are named boxes other objects may refer to (``"plot.left_top"``).
    ``allow`` accepts warnings on purpose (core/allow.py).
    """

    values: dict[Name, Number] = Field(default_factory=dict)
    focus: tuple[Id, ...] = ()
    extra_colors: dict[ColorName, Color | Mix] = Field(default_factory=dict)
    zones: dict[Name, Box] = Field(default_factory=dict)
    spaces: tuple[Space, ...] = ()
    defs: tuple[IRObject, ...] = ()
    objects: tuple[IRObject, ...] = ()
    allow: tuple[Allow, ...] = ()


HEADER_FIELDS = tuple(IRHeader.model_fields)
BODY_FIELDS = tuple(IRBody.model_fields)


class IRDocument(IRBody, IRHeader):  # this base order puts the header fields first
    """A whole ``ir.json``: header fields first, then body fields."""

    @property
    def header(self) -> IRHeader:
        return IRHeader(**{name: getattr(self, name) for name in HEADER_FIELDS})

    @property
    def body(self) -> IRBody:
        return IRBody(**{name: getattr(self, name) for name in BODY_FIELDS})

    @classmethod
    def join(cls, header: IRHeader, body: IRBody) -> Self:
        return cls(**dict(header), **dict(body))
