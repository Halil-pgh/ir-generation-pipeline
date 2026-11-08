"""Small types the IR's header and body share: ids, points, boxes and sizes.

Positions and lengths are in units of the frame (short side 9, origin at the
center, y up). Type sizes, stroke widths and dashes are in reference pixels
(short side 1080), as in the render profile.
"""

from typing import Annotated, Literal

from pydantic import Field, PositiveFloat

from irpipe.schema.color import NAME_PATTERN

Id = Annotated[str, Field(pattern=NAME_PATTERN)]
"""An object id: a letter, then letters, digits or ``_``. Dots are kept for parts (``v.label``)."""

Name = Id
"""The name of a style, zone or space in the header or body."""

Point = tuple[float, float]
Box = tuple[float, float, float, float]
"""Left, bottom, right, top, in units."""

Role = Literal["title", "heading", "body", "label", "caption"]
Size = Role | PositiveFloat
"""A text role from the header's type scale, or a size in reference pixels."""
