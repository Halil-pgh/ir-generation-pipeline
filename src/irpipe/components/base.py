"""The component interface: a helper object with its own schema that opens into core objects.

A component (axes, graph, brace, angle...) is written in the IR like any
object, with its own ``type`` and fields (analysis §2.7). Before anything
else looks at the IR, it is opened into core objects; after that, nothing
in the pipeline knows it was ever there.

    @COMPONENTS.register
    class Graph(Component):
        type: Literal["graph"] = "graph"
        function: str
        ...
        def expand(self, context: Context) -> Expansion:
            return Expansion(root=Path...)

Adding a component is one file in ``irpipe/components``: its model and its
``expand``. Taking ``irpipe.components`` out of ``plugins`` in
pipeline.toml switches every component off.

An expansion keeps the component's id on one core object, ``root``, in the
component's own place in the list, so whatever refers to the component
(``"ax.center"``, ``{"on": "f", "x": 2}``, a group's children) still finds
it. ``parts``, when there are some, are objects with dotted ids
(``ax.x_tick_3``) that the root, a group, holds. A part's JSON path is its
component's.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from irpipe.core import ISSUE_CODES, IssueCode, Origin, PluginDefinitionError, Registry
from irpipe.expr import Value
from irpipe.schema.ir import Group
from irpipe.schema.ir.objects import InSpace, ObjectBase

E_COMPONENT = ISSUE_CODES.register(
    IssueCode(
        "E-COMPONENT",
        Origin.IR,
        "a component cannot be opened with the values it was given",
    )
)

PLACEHOLDER_ID = "part"
"""The id parts are checked under before they get their dotted one (ids have no dots)."""


class ComponentError(ValueError):
    """A component's fields do not make sense together: reported as E-COMPONENT (or ``code``),
    at the component's path plus ``field``."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        hint: str | None = None,
        code: IssueCode = E_COMPONENT,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.hint = hint
        self.code = code


@dataclass(frozen=True)
class Context:
    """What a component may know about the IR around it."""

    values: Mapping[str, Value]
    """The IR's computed ``values``, for expressions a component evaluates itself."""
    space_units: Mapping[str, tuple[float, float]]
    """Frame units per unit of each space, along x and y."""

    def units(self, space: str | None) -> tuple[float, float]:
        """Frame units per unit of ``space`` (1, 1 for the frame itself)."""
        return (1.0, 1.0) if space is None else self.space_units.get(space, (1.0, 1.0))

    def length(self, frame_units: float, space: str | None) -> float:
        """A length given in frame units, in the units of ``space`` (by their mean scale)."""
        ux, uy = self.units(space)
        return frame_units / math.sqrt(ux * uy)


@dataclass(frozen=True)
class Expansion:
    """The core objects a component opens into: ``root`` keeps its id, ``parts`` are dotted."""

    root: ObjectBase
    parts: Sequence[ObjectBase] = field(default_factory=tuple)


class Component(InSpace):
    """Fields every component has: those of every object (id, style, opacity, z, clip...) and
    ``in``, the space its numbers are read in."""

    def expand(self, context: Context) -> Expansion:
        """The core objects this component stands for; raise ComponentError if it cannot."""
        raise NotImplementedError

    @classmethod
    def type_name(cls) -> str:
        default = cls.model_fields["type"].default
        return str(default)

    def shared(self) -> dict[str, Any]:
        """Fields the root takes over as they are: what every object has, but its tags."""
        return {
            "style": self.style,
            "opacity": self.opacity,
            "z": self.z,
            "covers": self.covers,
            "clip": self.clip,
            "clip_out": self.clip_out,
        }

    def made_tags(self) -> tuple[str, ...]:
        """The tags of what it opens into: its own, and its type, so the meaning stays
        (analysis §2.7: a path the axes made says "axes")."""
        return (*self.tags, self.type)


def make(model: type[ObjectBase], oid: str, values: Mapping[str, Value], **fields: Any) -> Any:
    """A core object of ``model``, checked by its own schema, then given the id ``oid``.

    Parts have dotted ids, which an IR id may not have, so the object is
    checked under a placeholder id first.
    """
    checked = model.model_validate(
        {"id": PLACEHOLDER_ID, **fields}, context={"values": dict(values)}
    )
    return checked.model_copy(update={"id": oid})


def group_of(
    component: Component, children: Sequence[ObjectBase], values: Mapping[str, Value]
) -> Group:
    """The root of a component made of parts: a group with its id, holding them in order."""
    placeholders = [PLACEHOLDER_ID] * len(children)
    shared = {k: v for k, v in component.shared().items() if k != "style"}
    tags = component.made_tags()
    root: Group = make(Group, component.id, values, children=placeholders, tags=tags, **shared)
    return root.model_copy(update={"children": tuple(child.id for child in children)})


def _check_component(cls: type[Component]) -> None:
    if not isinstance(cls, type) or not issubclass(cls, Component):
        raise PluginDefinitionError(f"{cls!r} is not a Component")
    name = cls.model_fields.get("type")
    if name is None or not isinstance(name.default, str) or not name.default:
        raise PluginDefinitionError(f"component {cls.__name__} needs a literal `type`")
    if cls.expand is Component.expand:
        raise PluginDefinitionError(f"component '{name.default}' does not implement expand()")


COMPONENTS: Registry[type[Component]] = Registry(
    "component", key=lambda cls: cls.type_name(), check=_check_component
)
"""The components pipeline.toml's plugins have registered, by type name."""
