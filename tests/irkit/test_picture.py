"""Building a picture: builders, handles, the body as ir.json holds it, checking and measuring."""

import json
from fractions import Fraction as Frac
from pathlib import Path
from typing import Any

import pytest

from irpipe.irkit import Picture, difference, label, under
from irpipe.irkit.fields import object_models
from irpipe.schema.ir import IRDocument, IRHeader, header_hash


def objects(pic: Picture) -> dict[str, dict[str, Any]]:
    return {obj["id"]: obj for obj in pic.body()["objects"]}


def test_every_object_type_is_a_builder_and_none_hides_a_method_of_the_picture(
    pic: Picture,
) -> None:
    types = set(object_models())  # with the components the picture loaded
    assert {"circle", "line", "path", "text", "math", "stack", "flood_fill"} <= types
    assert {"axes", "graph", "brace", "angle"} <= types  # the components
    assert not types & set(dir(Picture))


def test_geometry_keeps_its_exact_numbers_and_other_fields_get_floats(pic: Picture) -> None:
    s = pic.space("S", origin=(Frac(-22, 10), -1), unit=Frac(11, 10))
    a = pic.line("a", start=(0, 0), end=(Frac(9, 5), Frac(12, 5)), space=s, stroke_width=Frac(7, 2),
                 opacity=Frac(1, 3), arrows=["end"], label=label(tex="a", at="tip", gap=Frac(1, 10),
                 dir=(Frac(3, 5), Frac(4, 5))))  # fmt: skip
    line = objects(pic)["a"]
    assert line == {
        "id": "a", "type": "line", "start": [0, 0], "end": ["9/5", "12/5"], "in": "S",
        "stroke_width": 3.5, "opacity": pytest.approx(1 / 3), "arrows": ["end"],
        "label": {"tex": "a", "at": "tip", "gap": 0.1, "dir": [0.6, 0.8]},
    }  # fmt: skip
    # a label's dir takes no expressions, so the whole label gets floats, and stays valid
    assert pic.body()["spaces"] == [{"id": "S", "origin": ["-11/5", -1], "unit": "11/10"}]
    assert a.tip == "a.tip" and a.label.center == "a.label.center" and str(a) == "a"
    assert pic.check() == []


def test_handles_stand_for_ids_wherever_the_ir_takes_one(pic: Picture) -> None:
    disc = pic.defs.circle("disc", center=(0, 0), radius=1)
    square = pic.defs.rect("square", center=(0, 0), width=3, height=3)
    hole = pic.region("hole", shape=difference(square, disc), fill="a")
    name = pic.text("name", text="area")
    tex = pic.math("tex", tex="x^2")
    row = pic.stack("row", children=[name, tex], arrange="row", next_to=hole, dir="down")
    f = pic.graph("f", function="x**2/4", x_range=[-2, 2])
    pic.region("under_f", shape=under(f, x=(0, Frac(3, 2))), fill="b")
    pic.circle("dot", center=f.at(x=1), radius=0.1, fill="a")
    pic.focus(row, "hole")
    found = objects(pic)
    assert [d["id"] for d in pic.body()["defs"]] == ["disc", "square"]
    assert found["hole"]["shape"] == {"difference": ["square", "disc"]}
    assert (found["row"]["children"], found["row"]["next_to"]) == (["name", "tex"], "hole")
    assert found["under_f"]["shape"] == {"under": "f", "x": [0, "3/2"]}
    assert found["dot"]["center"] == {"on": "f", "x": 1}
    assert pic.body()["focus"] == ["row", "hole"]
    assert pic.check() == []


def test_a_component_is_built_like_any_object_and_its_parts_have_handles(pic: Picture) -> None:
    ax = pic.axes("ax", x_range=[-1, 4], y_range=[-1, 3], x_label="x")
    pic.text("note", text="x", at=ax.part("x_label").left_center, anchor="right_center")
    assert ax.part("x_axis").tip == "ax.x_axis.tip"
    assert objects(pic)["note"]["at"] == "ax.x_label.left_center"
    assert pic.check() == []


def test_mistakes_fail_at_the_scripts_own_line_with_the_closest_name(pic: Picture) -> None:
    with pytest.raises(TypeError, match="line 'a' has no field 'strat'; did you mean 'start'"):
        pic.line("a", strat=(0, 0), end=(1, 1))
    with pytest.raises(TypeError, match="circle 'c' needs center, radius"):
        pic.circle("c")
    with pytest.raises(AttributeError, match="no object type 'cirle'; did you mean 'circle'"):
        pic.cirle("c")
    with pytest.raises(ValueError, match="no object type 'nothing'"):
        pic.add("nothing", "n")
    with pytest.raises(TypeError, match="a label has no field 'colour'; did you mean 'color'"):
        label(tex="a", colour="a")
    a = pic.line("a", start=(0, 0), end=(1, 1))
    with pytest.raises(AttributeError, match="'a' \\(line\\) has no anchor 'tpi'; did you mean"):
        a.tpi  # noqa: B018
    with pytest.raises(AttributeError, match="was given no label"):
        a.label  # noqa: B018
    with pytest.raises(ValueError, match="the id 'a' is taken already \\(by a line\\)"):
        pic.circle("a", center=(0, 0), radius=1)
    with pytest.raises(ValueError, match="taken already"):
        pic.circle("safe", center=(0, 0), radius=1)


def test_values_are_checked_all_at_once_by_validate(pic: Picture) -> None:
    pic.circle("c", center="nothing.center", radius=-1)
    codes = [(issue.code, issue.path) for issue in pic.check()]
    assert codes == [("E-SCHEMA", "objects[0].radius")]
    pic2 = Picture(pic.header.model_dump(mode="json"), metrics="fixed")
    pic2.circle("c", center="nothing.center", radius=1)
    assert [issue.code for issue in pic2.check()] == ["E-REF"]


def test_named_values_extra_colors_zones_and_allows(pic: Picture) -> None:
    k = pic.value("k", Frac(9, 13))
    pic.value("half_k", f"{k}/2")
    ab = pic.color("ab", {"mix": ["a", "b"]})
    plot = pic.zone("plot", (-6, -3, Frac(1, 2), 3))
    pic.circle("c", center=plot.center, radius="half_k", fill=ab)
    pic.allow("W-OFFSCREEN", "it runs off on purpose", objects=["c"])
    body = pic.body()
    assert body["values"] == {"k": "9/13", "half_k": "k/2"}
    assert body["extra_colors"] == {"ab": {"mix": ["a", "b"]}}
    assert body["zones"] == {"plot": [-6, -3, 0.5, 3]}
    assert body["allow"] == [
        {"code": "W-OFFSCREEN", "reason": "it runs off on purpose", "objects": ["c"]}
    ]
    assert objects(pic)["c"]["radius"] == "half_k"
    assert pic.check() == []


def test_the_header_is_written_back_as_it_was_given(
    pic: Picture, header: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "header.json").write_text(json.dumps(header), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    opened = Picture.open(metrics="fixed")
    opened.circle("c", center=(0, 0), radius=1)
    assert opened.write() == Path("ir.json")
    written = json.loads((tmp_path / "ir.json").read_text(encoding="utf-8"))
    assert list(written)[: len(header)] == list(header)
    document = IRDocument.model_validate(written)
    assert header_hash(document.header) == header_hash(IRHeader.model_validate(header))
    with pytest.raises(Exception, match="frozen"):
        opened.header.intent = "something else"  # type: ignore[misc]


def test_texts_and_formulas_are_measured_in_frame_units_or_a_spaces(pic: Picture) -> None:
    # "fixed": a glyph is 0.55 of the size wide; heading is 52 px; 120 px make a unit
    box = pic.measure_text("abcd", size="heading")
    assert (box.width, box.ascent, box.descent) == pytest.approx(
        (4 * 52 * 0.55 / 120, 52 * 0.75 / 120, 52 * 0.25 / 120)
    )
    assert box.height == pytest.approx(52 / 120)
    s = pic.space("S", unit=(2, Frac(1, 2)))
    scaled = pic.measure_tex("x^2", size=60, space=s)
    assert (scaled.width, scaled.height) == pytest.approx((3 * 60 * 0.4 / 120 / 2, 60 / 60))
    with pytest.raises(ValueError, match="there is no space 'T'"):
        pic.measure_text("a", space="T")
