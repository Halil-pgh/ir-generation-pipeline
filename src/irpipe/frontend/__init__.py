"""The front-end: the library-independent half of the compiler (analysis §3).

Each stage is one module and registers itself in ``STAGES``; listing
``irpipe.frontend`` under ``plugins`` in ``pipeline.toml`` loads them all.

Module map:
    validate.py       stage "validate": ir.json text -> checked IR
    schema_errors.py  E-JSON, E-SCHEMA: JSON and schema errors in the agent's terms
    references.py     E-ID, E-REF, E-GROUP: every name points at something
    expressions.py    E-EXPR, E-CYCLE: the IR's named values and expressions
    header_lock.py    stage "check_header": E-HEADER when the locked header was changed
    normalize.py      stage "normalize": labels as objects, every object's paint written out;
                      W-UNDECLARED-COLOR
    paint.py          the paint cascade: theme, then style classes, then the object
    labels.py         a shape's label as an object of its own; JSON paths of objects
    measure.py        stage "measure": every text's and formula's box; E-TEX
    place.py          stage "place": references, boxes, stacks, spaces and areas as
                      numbers and paths; E-PLACE, E-CYCLE
    regions.py        region expressions and clips in IR terms; E-REGION, W-EMPTY-REGION,
                      W-CLIP-TEXT
    anchors.py        the named points of objects, and every point an object holds
    layout.py         box points, placing beside a point or box, grids
    resolve.py        stage "resolve": placed, measured IR -> LIR; spaces, arrowheads, clips
    shapes.py         shapes, group transforms and arrowheads as LIR geometry
    lower.py          the LIR lowered to a backend's capabilities (called by "render")
    geometry/         affine maps; paths measured and cut; areas, flood fill and clipping
"""
