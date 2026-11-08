"""Registry: the one lookup pattern behind every kind of plugin."""

from dataclasses import dataclass

import pytest

from irpipe.core import DuplicatePluginError, Registry, UnknownPluginError


@dataclass(frozen=True)
class Tool:
    name: str


def make_registry() -> Registry[Tool]:
    return Registry("tool", key=lambda tool: tool.name)


def test_register_returns_the_item_and_get_finds_it() -> None:
    tools = make_registry()
    hammer = Tool("hammer")
    assert tools.register(hammer) is hammer
    assert tools.get("hammer") is hammer
    assert "hammer" in tools
    assert len(tools) == 1


def test_names_are_sorted() -> None:
    tools = make_registry()
    for name in ("saw", "drill", "hammer"):
        tools.register(Tool(name))
    assert tools.names() == ["drill", "hammer", "saw"]


def test_registering_the_same_item_again_is_harmless() -> None:
    tools = make_registry()
    hammer = Tool("hammer")
    tools.register(hammer)
    tools.register(hammer)
    assert len(tools) == 1


def test_two_items_under_one_name_are_refused() -> None:
    tools = make_registry()
    tools.register(Tool("hammer"))
    with pytest.raises(DuplicatePluginError, match="two different tools are registered as"):
        tools.register(Tool("hammer"))


def test_unknown_name_lists_the_registered_ones_and_suggests_a_close_one() -> None:
    tools = make_registry()
    tools.register(Tool("hammer"))
    tools.register(Tool("saw"))
    with pytest.raises(UnknownPluginError) as err:
        tools.get("hamer")
    assert str(err.value) == (
        "unknown tool 'hamer'; did you mean 'hammer'? (registered tools: hammer, saw)"
    )


def test_check_runs_before_an_item_is_accepted() -> None:
    def no_blunt_tools(tool: Tool) -> None:
        if tool.name == "spoon":
            raise ValueError("a spoon is not a tool")

    tools = Registry("tool", key=lambda tool: tool.name, check=no_blunt_tools)
    with pytest.raises(ValueError, match="spoon"):
        tools.register(Tool("spoon"))
    assert "spoon" not in tools


def test_closest_finds_a_near_name_or_nothing() -> None:
    tools = make_registry()
    tools.register(Tool("hammer"))
    assert tools.closest("hamer") == "hammer"
    assert tools.closest("screwdriver") is None
