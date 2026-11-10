"""Stage "normalize": every object's paint written out in full (analysis §2.4, §2.5, §2.8).

    requires  ir
    provides  ir_normal   the same IR, each object's paint written out

After normalize no later stage needs the header's styles, color names or
type scale: every object carries its own hex colors (or ``"none"``),
opacity, stroke width and dash, and every text its size in reference pixels.
The cascade itself is in paint.py. Each shape's ``label`` becomes an object
of its own first (labels.py), so it goes through the cascade too.

It also reports W-UNDECLARED-COLOR where an object writes a color directly
instead of naming one: "one concept, one color" holds only while colors have
names (analysis §2.4). A literal color is not wrong, so the warning can be
accepted with an ``allow`` entry.
"""

import json
from collections.abc import Iterator

from irpipe.artifacts import IR, IR_NORMAL
from irpipe.core import ISSUE_CODES, STAGES, Issue, IssueCode, Origin, Stage, StageContext
from irpipe.frontend.labels import with_labels
from irpipe.frontend.paint import PaintResolver, to_hex
from irpipe.schema.ir import IRDocument

W_UNDECLARED_COLOR = ISSUE_CODES.register(
    IssueCode(
        "W-UNDECLARED-COLOR",
        Origin.IR,
        "an object writes a color directly instead of naming it",
        allowable=True,
    )
)


@STAGES.register
class Normalize(Stage):
    name = "normalize"
    requires = (IR,)
    provides = (IR_NORMAL,)

    def run(self, ctx: StageContext) -> None:
        document = ctx.read(IR)
        ctx.report(*undeclared_colors(document))
        ctx.write(IR_NORMAL, normalize(document))


def normalize(document: IRDocument) -> IRDocument:
    """``document`` with labels as objects, and the paint of every object and def written out."""
    resolver = PaintResolver(document)
    document = with_labels(document, resolver)
    return document.model_copy(
        update={
            "objects": tuple(resolver.normalized(obj) for obj in document.objects),
            "defs": tuple(resolver.normalized(obj) for obj in document.defs),
        }
    )


def undeclared_colors(document: IRDocument) -> Iterator[Issue]:
    """A W-UNDECLARED-COLOR for every literal color an object writes."""
    for k, obj in enumerate(document.objects):
        label = getattr(obj, "label", None)
        fields = [("color", obj), ("fill", obj), ("label.color", label)]
        for field, owner in fields:
            value = getattr(owner, field.rpartition(".")[2], None)
            if isinstance(value, tuple) or (isinstance(value, str) and value.startswith("#")):
                written = json.dumps(value) if isinstance(value, str) else json.dumps(list(value))
                yield W_UNDECLARED_COLOR(
                    f"{field} {written} is written directly instead of naming a color",
                    path=f"objects[{k}].{field}",
                    objects=[obj.id],
                    hint=f'name it in extra_colors (such as "ink": "{to_hex(value)}") '
                    "and use the name here",
                )
