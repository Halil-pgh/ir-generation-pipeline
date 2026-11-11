"""The picture a build_ir.py builds: the locked header, and the body the script adds to it.

    pic = Picture.open()                               # header.json, in the run folder
    P = pic.space("P", origin=(-2, -1), unit=Fraction(11, 10))
    a = pic.line("a", start=(0, 0), end=(2, 3), space=P, arrows=["end"], covers=["vectors"])
    pic.defs.circle("disc", center=(0, 0), radius=1)  # an operand of a region; not drawn
    pic.focus(a)
    pic.write()                                        # ir.json: the header as given, the body

Every object type is a method named after it (``pic.circle``, ``pic.text``,
``pic.axes``…), the registered components included; ``pic.add("circle",
"c", ...)`` is the same call. The id comes first, then the fields as
keywords, named as the IR's models name them (``space`` for ``"in"``);
each call returns a handle (handles.py). Objects are written in the order
they were made, which is the order they are drawn in (``z`` reorders).

The header belongs to the orchestrator: it is read from header.json and
written back as it was, and ``pic.header`` is a frozen model. ``check()``
runs the validate stage over what the script built and returns its issues
with their JSON paths, as the pipeline will report them.
"""

import difflib
import functools
import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from irpipe.artifacts import IR_SOURCE
from irpipe.components.base import Component
from irpipe.core import Issue, Pipeline
from irpipe.core.allow import Allow
from irpipe.core.plugins import load_plugins
from irpipe.expr import CycleError, TableError, Value, evaluate_table
from irpipe.frontend.anchors import BASELINE_ANCHORS, BOX_ANCHORS, PATH_ANCHORS, RESERVED
from irpipe.irkit.fields import checked, object_models, to_json
from irpipe.irkit.handles import Handle
from irpipe.irkit.measure import DEFAULT_PROVIDER, Box, Measurer
from irpipe.irkit.numbers import plain, render
from irpipe.schema.ir import IRHeader, Size, Space
from irpipe.schema.ir.objects import Arc, Line, Math, ObjectBase, Polyline, Stack, Text
from irpipe.schema.ir.objects import Path as PathObject

DEFAULT_PLUGINS = ("irpipe.components",)
"""Packages whose object types the builders offer, as in pipeline.toml's plugins."""
CHECK_PLUGINS = (
    "irpipe.frontend", "irpipe.components", "irpipe.checks", "irpipe.backends",
    "irpipe.orchestrator",
)  # fmt: skip
"""What check() loads: the validate stage, and every issue code a run knows, so an allow
entry for a check's warning (or W-UNCOVERED) is not taken for an unknown code."""
HEADER = "header.json"
IR = "ir.json"


class Builder:
    """Makes objects into one list of the body: ``pic`` draws them, ``pic.defs`` only defines."""

    def __init__(self, picture: "Picture", into: list[dict[str, Any]]) -> None:
        self._picture = picture
        self._into = into

    def add(self, type_name: str, id: str, /, **fields: Any) -> Handle:
        """An object of ``type_name`` with id ``id``; TypeError for a field it does not take."""
        return self._picture._make(self._into, type_name, id, fields)

    def __getattr__(self, name: str) -> Callable[..., Handle]:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in object_models():
            raise AttributeError(_unknown_type(name))
        return functools.partial(self.add, name)


class Picture:
    """The locked header and the body a script builds; see the module's docstring."""

    def __init__(
        self,
        header: Mapping[str, Any],
        *,
        metrics: str = DEFAULT_PROVIDER,
        plugins: Iterable[str] = DEFAULT_PLUGINS,
    ) -> None:
        load_plugins(plugins)
        self.header = IRHeader.model_validate(header)
        self._header = dict(header)
        self._objects: list[dict[str, Any]] = []
        self._defs: list[dict[str, Any]] = []
        self._handles: dict[str, Handle] = {}
        self._values: dict[str, Any] = {}
        self._focus: list[Any] = []
        self._colors: dict[str, Any] = {}
        self._zones: dict[str, Any] = {}
        self._spaces: dict[str, dict[str, Any]] = {}
        self._allow: list[dict[str, Any]] = []
        self._measurer = Measurer(self.header, metrics)
        self._draw = Builder(self, self._objects)
        self.defs = Builder(self, self._defs)
        """Objects that are only operands (of a region, say) and are not drawn."""
        self.frame = Handle("frame", "frame", BOX_ANCHORS)
        self.safe = Handle("safe", "safe", BOX_ANCHORS)

    @classmethod
    def open(cls, path: str | Path = HEADER, **options: Any) -> "Picture":
        """The picture whose header is the file ``path`` (header.json in the run folder)."""
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), **options)

    # Objects

    def add(self, type_name: str, id: str, /, **fields: Any) -> Handle:
        """A drawn object of ``type_name``; ``pic.<type_name>(id, ...)`` is the same."""
        return self._draw.add(type_name, id, **fields)

    def __getattr__(self, name: str) -> Callable[..., Handle]:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._draw, name)  # type: ignore[no-any-return]

    def __getitem__(self, id: str) -> Handle:
        """The handle of the object ``id`` made earlier (for objects made in a loop)."""
        return self._handles[id]

    def _make(
        self, into: list[dict[str, Any]], type_name: str, oid: str, fields: Mapping[str, Any]
    ) -> Handle:
        model = object_models().get(type_name)
        if model is None:
            raise ValueError(_unknown_type(type_name))
        if oid in self._handles or oid in RESERVED:
            taken = self._handles[oid].kind if oid in self._handles else "the picture"
            raise ValueError(f"the id '{oid}' is taken already (by a {taken})")
        given = checked(model, f"{type_name} '{oid}'", fields)
        into.append({"id": oid, "type": type_name, **to_json(model, given, self._computed())})
        self._handles[oid] = Handle(oid, type_name, _anchors(model), labelled="label" in given)
        return self._handles[oid]

    # The rest of the body

    def space(self, id: str, *, origin: Any = (0, 0), unit: Any = 1) -> Handle:
        """A coordinate space: its point (x, y) is drawn at ``origin + (x, y) * unit``."""
        if id in self._spaces:
            raise ValueError(f"there is a space '{id}' already")
        given = checked(Space, f"space '{id}'", {"origin": origin, "unit": unit})
        self._spaces[id] = {"id": id, **to_json(Space, given, self._computed())}
        return Handle(id, "space")

    def zone(self, name: str, box: Any) -> Handle:
        """A named box ``[left, bottom, right, top]`` (frame units) others may refer to."""
        self._zones[name] = render(plain(box), exact=False)
        return Handle(name, "zone", BOX_ANCHORS)

    def value(self, name: str, number: Any) -> str:
        """A named number in the IR's ``values``; geometry may use it in expressions
        (``"k/2"``). Returns the name."""
        self._values[name] = plain(number)
        return name

    def color(self, name: str, color: Any) -> str:
        """An extra color, ``"#RRGGBB"``, ``[r, g, b]`` or ``mix(a, b)``. Returns its name."""
        self._colors[name] = render(plain(color), exact=False)
        return name

    def focus(self, *objects: Any) -> None:
        """The objects the eye should go to first."""
        self._focus.extend(objects)

    def allow(self, code: str, reason: str, objects: Iterable[Any] = ()) -> None:
        """Accept a warning on purpose: its code, why, and the objects it is about."""
        entry = checked(Allow, f"allow '{code}'", {"code": code, "reason": reason})
        self._allow.append({**entry, "objects": [plain(obj) for obj in objects]})

    # Measuring

    def measure_text(
        self,
        text: str,
        *,
        size: Size = "body",
        weight: Literal["regular", "bold"] = "regular",
        italic: bool = False,
        space: Handle | str | None = None,
    ) -> Box:
        """The box ``text`` will have, in frame units (or ``space``'s)."""
        return self._measurer.text(text, size, weight, italic, self._units(space))

    def measure_tex(
        self, tex: str, *, size: Size = "body", space: Handle | str | None = None
    ) -> Box:
        """The box the formula ``tex`` will have; TexError when it cannot be typeset."""
        return self._measurer.tex(tex, size, self._units(space))

    # Writing

    def body(self) -> dict[str, Any]:
        """The body as ir.json holds it; empty fields left out."""
        body = {
            "values": render(self._values, exact=True),
            "focus": [plain(obj) for obj in self._focus],
            "extra_colors": self._colors,
            "zones": self._zones,
            "spaces": list(self._spaces.values()),
            "defs": self._defs,
            "objects": self._objects,
            "allow": self._allow,
        }
        return {name: value for name, value in body.items() if value}

    def document(self) -> dict[str, Any]:
        """The whole ir.json: the header as it was given, then the body."""
        return {**self._header, **self.body()}

    def json_text(self) -> str:
        """ir.json as the text write() puts in the file."""
        return json.dumps(self.document(), indent=2, ensure_ascii=False) + "\n"

    def write(self, path: str | Path = IR) -> Path:
        """Write ir.json (in the run folder, unless told otherwise); returns its path."""
        target = Path(path)
        target.write_text(self.json_text(), encoding="utf-8")
        return target

    def check(self) -> list[Issue]:
        """What the validate stage says about the IR built so far (nothing when it is valid)."""
        load_plugins(CHECK_PLUGINS)
        pipeline = Pipeline.build(["validate"], inputs=[IR_SOURCE])
        return list(pipeline.run({IR_SOURCE: self.json_text()}).issues)

    def _computed(self) -> dict[str, Value]:
        """The values table computed so far, for expressions that name its entries."""
        try:
            return evaluate_table(render(self._values, exact=True))
        except (TableError, CycleError):
            return {}

    def _units(self, space: Handle | str | None) -> tuple[float, float]:
        if space is None:
            return (1.0, 1.0)
        name = str(space)
        if name not in self._spaces:
            raise ValueError(f"there is no space '{name}'; make it with pic.space first")
        return Space.model_validate(self._spaces[name], context={"values": self._computed()}).units


def _anchors(model: type[ObjectBase]) -> tuple[str, ...]:
    """The anchors an object of ``model`` has; a component, opening into an object not known
    yet, may have a box's and an open shape's (validate checks the name)."""
    if issubclass(model, Component):
        return BOX_ANCHORS + PATH_ANCHORS
    names: tuple[str, ...] = BOX_ANCHORS
    if issubclass(model, Text | Math | Stack):
        names += BASELINE_ANCHORS
    if issubclass(model, Line | Polyline | Arc | PathObject):
        names += PATH_ANCHORS
    return names


def _unknown_type(name: str) -> str:
    known = list(object_models())
    close = difflib.get_close_matches(name, known, n=1)
    hint = f"did you mean '{close[0]}'?" if close else f"the types: {', '.join(known)}"
    return f"there is no object type '{name}'; {hint}"
