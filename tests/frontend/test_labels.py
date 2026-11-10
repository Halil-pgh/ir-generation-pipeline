"""labels: a shape's label becomes a text or formula of its own, in its owner's color."""

from collections.abc import Callable
from typing import Any

from irpipe.frontend.labels import owner_of, source_paths
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize, undeclared_colors
from irpipe.metrics import TexError, TextMetrics
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema.ir import Group, IRDocument, Math, Text

type Make = Callable[..., IRDocument]

V = {"id": "v", "type": "line", "start": [0, 0], "end": [2, 1], "color": "a"}


def labelled(**label: Any) -> dict[str, Any]:
    return {**V, "label": {"text": "v", **label}}


def find(document: IRDocument, oid: str) -> Any:
    return next(obj for obj in document.objects if obj.id == oid)


def test_a_label_becomes_a_text_at_its_owners_anchor(document: Make) -> None:
    doc = normalize(document([labelled(at="tip", dir="up_left", gap=0.1)]))
    label = find(doc, "v.label")
    assert isinstance(label, Text)
    assert (label.text, label.at, label.dir, label.gap) == ("v", "v.tip", "up_left", 0.1)
    assert (label.color, label.size) == ("#FFD43B", 38)  # the owner's color, the label size
    assert find(doc, "v").label is None  # the owner no longer carries it


def test_a_tex_label_is_a_formula_centered_on_the_owner_by_default(document: Make) -> None:
    label = find(normalize(document([{**V, "label": {"tex": "\\vec v"}}])), "v.label")
    assert isinstance(label, Math)
    assert (label.tex, label.at, label.dir) == ("\\vec v", "v.center", None)


def test_a_label_takes_the_color_a_class_gives_its_owner(document: Make) -> None:
    owner = {"id": "r", "type": "rect", "center": [0, 0], "width": 1, "height": 1,
             "style": "boxed", "color": "none", "label": {"text": "R"}}  # fmt: skip
    assert find(normalize(document([owner])), "r.label").color == "#FFD43B"  # boxed's fill


def test_a_label_may_set_its_own_color_and_size(document: Make) -> None:
    label = find(normalize(document([labelled(color="b", size="title")])), "v.label")
    assert (label.color, label.size) == ("#58C4DD", 64)


def test_a_muted_owner_has_a_muted_label_at_its_z(document: Make) -> None:
    owner = {**labelled(), "style": "muted", "z": 3}
    label = find(normalize(document([owner])), "v.label")
    assert (label.opacity, label.z) == (0.5, 3)


def test_a_label_joins_its_owners_group_right_after_it(document: Make) -> None:
    group = {"id": "g", "type": "group", "children": ["v", "w"]}
    w = {"id": "w", "type": "circle", "center": [0, 0], "radius": 1}
    doc = normalize(document([labelled(), w, group]))
    g = find(doc, "g")
    assert isinstance(g, Group)
    assert g.children == ("v", "v.label", "w")
    assert [obj.id for obj in doc.objects] == ["v", "w", "g", "v.label"]


def test_a_labels_path_is_its_owners(document: Make) -> None:
    doc = normalize(document([{"id": "c", "type": "circle", "center": [0, 0], "radius": 1},
                              labelled()]))  # fmt: skip
    assert source_paths(doc)["v.label"] == "objects[1].label"
    assert (owner_of("v.label"), owner_of("v")) == ("v", None)


def test_a_literal_label_color_is_reported_on_the_label(document: Make) -> None:
    (issue,) = undeclared_colors(document([labelled(color="#FF0000")]))
    assert (issue.code, issue.path) == ("W-UNDECLARED-COLOR", "objects[0].label.color")


class FailingTex(FixedMetrics):
    name = "failing_tex"

    def math(self, tex: str, *, math_font: str, size: float) -> Any:
        raise TexError("Undefined control sequence")


def test_a_broken_tex_label_is_reported_at_the_label(document: Make) -> None:
    metrics: TextMetrics = FailingTex()
    measured, problems = measure(normalize(document([{**V, "label": {"tex": "\\x"}}])), metrics)
    assert measured is None
    (issue,) = problems
    assert (issue.code, issue.path, issue.objects) == (
        "E-TEX",
        "objects[0].label.tex",
        ("v.label",),
    )
