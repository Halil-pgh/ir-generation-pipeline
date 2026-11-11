"""build_ir.py for the frame "tangents", written with the irkit SDK.

The two tangents from P = (5, 0) to the circle of radius 3 around O touch
it at T1 and T2; they are equally long and meet the radii at right angles.
Every number is worked out here, exactly where it can be: the touching
points are (9/5, 12/5) and (9/5, -12/5), the chord crosses OP at
M = (9/5, 0), the tangents are 4 long. They reach ir.json as "9/5", "12/5"
and so on, not as rounded decimals. The layout is worked out too, from the
header's safe area and the measured sizes of the title and the formula.

    irpipe run examples/tangents/brief.json examples/tangents/build_ir.py
"""

from fractions import Fraction

from irpipe.irkit import Picture, label
from irpipe.irkit import geometry as g

pic = Picture.open()  # the header the orchestrator locked, from header.json
left, bottom, right, top = pic.header.frame.safe

# The geometry, in the drawing's own units
center, P, r = (0, 0), (5, 0), 3  # O, P and the radius
T1, T2 = g.tangent_points(P, center, r)  # (9/5, 12/5) and (9/5, -12/5)
M = g.line_line(T1, T2, center, P)  # where the chord crosses OP: (9/5, 0)
assert M is not None
length = g.distance(P, T1)  # 4, exactly
near = g.line_circle(center, P, center, r)[-1]  # the circle's point nearest P: (3, 0)
seed = g.midpoint(near, P)  # inside the area between the tangents and the circle

# The layout: the formula's box on the right, the drawing left of it, both
# centered in the room the title leaves.
tex = rf"PT_1 = PT_2 = \sqrt{{OP^2 - r^2}} = {length}"
formula = pic.measure_tex(tex, size="body")
title = pic.measure_text("Tangents from a point", size="heading", weight="bold")
pad, gap = Fraction(3, 10), Fraction(1, 2)
box_w, box_h = formula.width + 2 * pad, formula.height + 2 * pad
box_x = right - Fraction(1, 10) - box_w / 2
middle = (bottom + top - title.height) / 2  # halfway between the title and the bottom
unit = Fraction(9, 10)
reach = Fraction(28, 5)  # the drawing's right end, P's label included, in its units
S = pic.space("S", origin=(box_x - box_w / 2 - gap - reach * unit, middle), unit=unit)
assert box_x - box_w / 2 - gap - (reach + r) * unit > left, "the drawing does not fit"

ink = pic.color("ink", "#FFFFFF")
pic.text("title", text="Tangents from a point", at=pic.safe.center_top, anchor="center_top",
         size="heading", weight="bold")  # fmt: skip
circle = pic.circle("circle", center=center, radius=r, space=S, color="circle", stroke_width=5,
                    covers=["circle"])  # fmt: skip
pic.line("op", start=center, end=P, space=S, stroke_width=3)
pic.line("chord", start=T1, end=T2, space=S, style="construction", covers=["chord"])
for name, touch in (("r1", T1), ("r2", T2)):
    pic.line(name, start=center, end=touch, space=S, color="radius", covers=["radii"])
tangents = [  # from P to a little past the circle
    pic.line(name, start=P, end=g.along(P, touch, Fraction(6, 5)), space=S, color="tangent",
             stroke_width=6, covers=["tangents"])
    for name, touch in (("t1", T1), ("t2", T2))
]  # fmt: skip
pic.flood_fill("region", seed=seed, bounded_by=[*tangents, circle], space=S, fill="tangent",
               fill_opacity=0.2, z=-1, covers=["region"])  # fmt: skip
# The right angles open from the radius to the tangent, counterclockwise
pic.angle("right1", vertex=T1, arms=[center, P], space=S, color="radius", covers=["radii"])
pic.angle("right2", vertex=T2, arms=[P, center], space=S, color="radius", covers=["radii"])

points = [  # name, where, which way its label goes, what it covers
    ("O", center, "left", "circle"),
    ("P", P, "right", "point"),
    ("T1", T1, T1, "tangents"),  # straight out from the center
    ("T2", T2, T2, "tangents"),
    ("M", M, "down_right", "chord"),
]
for name, where, way, item in points:
    tex_name = name if len(name) == 1 else f"{name[0]}_{name[1]}"
    pic.circle(name, center=where, radius=Fraction(2, 25), space=S, fill=ink, color="none",
               z=2, covers=[item], label=label(tex=tex_name, dir=way))  # fmt: skip

pic.rect("formula_box", center=(box_x, middle), width=box_w, height=box_h,
         corner_radius=Fraction(3, 20), color="tangent", stroke_width=3,
         covers=["formula"])  # fmt: skip
pic.math("formula", tex=tex, at=(box_x, middle), covers=["formula"])
pic.focus(*tangents)
pic.allow("W-FILL-OVERLAP", "P's dot sits on the tip of the shaded area, where the tangents meet",
          objects=["region", "P"])  # fmt: skip
pic.write()
