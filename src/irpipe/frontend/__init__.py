"""The front-end: the library-independent half of the compiler (analysis §3).

Each stage is one module and registers itself in ``STAGES``; listing
``irpipe.frontend`` under ``plugins`` in ``pipeline.toml`` loads them all.

Module map:
    validate.py       stage "validate": ir.json text -> checked IR
    schema_errors.py  E-JSON, E-SCHEMA: JSON and schema errors in the agent's terms
    references.py     E-ID, E-REF, E-GROUP: every name points at something
    expressions.py    E-EXPR, E-CYCLE: the IR's named values and expressions
    header_lock.py    stage "check_header": E-HEADER when the locked header was changed
    resolve.py        stage "resolve": IR with absolute positions -> LIR
    paint.py          the paint cascade: theme, then style classes, then the object
    shapes.py         circles, rectangles and group transforms as LIR geometry
"""
