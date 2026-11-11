"""irkit: the builder SDK a build_ir.py is written with (analysis §4).

The agent does not write ir.json by hand: it writes a Python script that
computes the numbers and builds the IR with this SDK, so no number is ever
copied or rounded on the way. The script is the one source of truth; to
change the picture, change the script and run it again. ir.json stays the
contract: the SDK only writes it.

    from fractions import Fraction
    from irpipe.irkit import Picture, label, geometry as g

    pic = Picture.open()                               # the locked header, header.json
    O, P_, r = (0, 0), (5, 0), 3
    T1, T2 = g.tangent_points(P_, O, r)                # exactly (9/5, 12/5), (9/5, -12/5)
    S = pic.space("S", origin=(-4, 0), unit=Fraction(3, 4))
    c = pic.circle("c", center=O, radius=r, space=S, color="circle")
    t = pic.line("t1", start=P_, end=T1, space=S, label=label(tex="T_1", at="end", dir="up"))
    pic.math("f", tex=f"PT_1 = {g.distance(P_, T1)}", next_to=c, dir="right")
    pic.write()                                        # ir.json, "9/5" and all

What it gives:

- **Builders** (picture.py): ``pic.<type>(id, **fields)`` for every object
  type, components included; fields named as in the IR, checked as they
  are given; ``pic.defs.<type>`` for shapes that are only operands; spaces,
  zones, values, extra colors, focus and allow entries.
- **Handles** (handles.py): what a builder returns; ``a.tip``,
  ``f.at(x=2)``, ``a.label``, ``ax.part("x_axis")``; anywhere an id goes.
- **Exact numbers** (numbers.py): Fractions and sympy numbers reach the IR
  as expressions (``"44/17"``, ``"sqrt(2)/2"``) where geometry takes them.
- **Pieces** (shapes.py): ``label``, ``mix``, region expressions
  (``difference``, ``union``…, ``under``, ``between``, ``half_plane``) and
  path shortcuts (``through``, ``smooth``).
- **Geometry** (geometry.py): intersections, tangents, feet,
  ``crossings`` of two functions, a seed point inside a polygon.
- **Measuring** (measure.py): ``pic.measure_text`` and ``pic.measure_tex``,
  in IR units, with the provider and font the pipeline measures with.
- **Checking**: ``pic.check()`` returns the validate stage's issues.
- **Mistakes** (errors.py): a wrong field, type or id raises at the
  script's own line, and the traceback ends there, so E-SCRIPT shows it.

Module map: picture.py, handles.py, fields.py, numbers.py, shapes.py,
geometry.py, measure.py, errors.py.
"""

from irpipe.irkit import geometry as geometry
from irpipe.irkit.handles import Handle
from irpipe.irkit.measure import Box
from irpipe.irkit.picture import Builder, Picture
from irpipe.irkit.shapes import (
    between,
    difference,
    half_plane,
    intersection,
    label,
    mix,
    smooth,
    through,
    under,
    union,
    xor,
)

__all__ = [
    "Box",
    "Builder",
    "Handle",
    "Picture",
    "between",
    "difference",
    "geometry",
    "half_plane",
    "intersection",
    "label",
    "mix",
    "smooth",
    "through",
    "under",
    "union",
    "xor",
]
