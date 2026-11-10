"""Components: helper objects with their own schema that open into core objects (analysis §2.7).

An agent writes ``{"type": "axes", ...}`` or ``{"type": "graph", ...}`` in
ir.json like any object. The validate stage reads them with the schema of
every registered component and opens them into core objects before it
checks names, so the rest of the pipeline only ever sees core objects.
Listing ``irpipe.components`` under ``plugins`` in pipeline.toml loads them
all; a new component is one more file here.

Module map:
    base.py     Component, COMPONENTS, Expansion, Context, make(); E-COMPONENT
    expand.py   document_model(): IRDocument that also takes components;
                expand_components(): components -> core objects
    axes.py     "axes": two number lines with ticks, numbers and names
    graph.py    "graph": the curve y = f(x) of an expression
    brace.py    "brace": a curly brace along a segment, with a label
    angle.py    "angle": the arc (or square) of an angle, with a label
"""
