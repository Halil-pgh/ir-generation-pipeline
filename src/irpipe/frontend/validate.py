"""Stage "validate": reads ir.json, checks it, and hands on the IR.

    requires  ir_source   ir.json as text
    provides  ir          the parsed IRDocument

The checks run in order, and the first kind that finds a problem stops the
run, because resolve cannot draw what does not exist:

    E-JSON    the text is not JSON
    E-EXPR, E-CYCLE   the named ``values`` cannot be computed, or loop
    E-SCHEMA  a field is unknown, missing or of the wrong form
    E-EXPR    an expression in the geometry cannot be read or computed
    E-ID, E-REF, E-GROUP   names point at nothing, or groups are built wrongly

Expressions are computed here: the IR handed on holds plain numbers. The
schema is checked strictly: a number written as text (``"0.5"``) is only an
expression where geometry allows one, and true/false are the only booleans.

A malformed ``allow`` entry (E-ALLOW) is reported but does not stop the run:
the picture can still be drawn, it just cannot be READY.
"""

from typing import Any

from pydantic import ValidationError

from irpipe.artifacts import IR, IR_SOURCE
from irpipe.core import STAGES, Stage, StageContext, check_allows
from irpipe.frontend.expressions import computed_values
from irpipe.frontend.references import body_objects, reference_issues
from irpipe.frontend.schema_errors import parse_json, schema_issues
from irpipe.schema.ir import IRDocument


def _field_names(schema: dict[str, Any]) -> frozenset[str]:
    """Every property name anywhere in a JSON Schema; the pool for "did you mean"."""
    names: set[str] = set()
    for node in [schema, *schema.get("$defs", {}).values()]:
        names.update(node.get("properties", {}))
    return frozenset(names)


IR_FIELD_NAMES = _field_names(IRDocument.model_json_schema())


@STAGES.register
class Validate(Stage):
    name = "validate"
    requires = (IR_SOURCE,)
    provides = (IR,)

    def run(self, ctx: StageContext) -> None:
        text = ctx.read(IR_SOURCE)
        raw, problems = parse_json(text)
        if problems:
            ctx.report(*problems)
            return
        values, problems = computed_values(raw)
        if problems:
            ctx.report(*problems)
            return
        try:
            document = IRDocument.model_validate_json(text, strict=True, context={"values": values})
        except ValidationError as error:
            ctx.report(*schema_issues(raw, error, IR_FIELD_NAMES))
            return
        problems = reference_issues(document)
        if problems:
            ctx.report(*problems)
            return
        known_ids = {obj.id for _, obj in body_objects(document)}
        ctx.report(*check_allows(document.allow, known_ids=known_ids))
        ctx.write(IR, document)
