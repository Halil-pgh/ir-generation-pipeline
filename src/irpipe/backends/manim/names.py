"""Python names for the objects of a scene: the IR id wherever it can be one.

scene.py names every object after its IR id (analysis §3), so ``a`` is drawn
by ``make_a()`` into the variable ``a``. An id is already almost a Python
name: letters, digits and ``_``, starting with a letter. What is left:

    a.label      -> a_label        a part of an object; the dot cannot stay
    class        -> class_         a Python keyword
    Circle       -> Circle_        a name scene.py itself uses (``reserved``)
    a_label      -> a_label_2      when ``a.label`` already took ``a_label``

    names = Names(["a", "a.label", "class"], reserved={"Circle"})
    names.variable("a.label"), names.function("a.label")   # "a_label", "make_a_label"
"""

import keyword
from collections.abc import Iterable


class Names:
    """A variable and a ``make_`` function name for each id, all distinct."""

    def __init__(self, ids: Iterable[str], reserved: Iterable[str] = ()) -> None:
        ids = list(ids)
        blocked = {"self", *reserved}
        wanted = [_python_name(gid, blocked) for gid in ids]
        taken: set[str] = set()
        self._variables: dict[str, str] = {}
        # Ids that are already plain names keep them; the changed ones give way.
        order = sorted(range(len(ids)), key=lambda k: wanted[k] != ids[k])
        for k in order:
            name, count = wanted[k], 1
            while name in taken or f"make_{name}" in taken:
                count += 1
                name = f"{wanted[k]}_{count}"
            taken.update((name, f"make_{name}"))
            self._variables[ids[k]] = name

    def variable(self, gid: str) -> str:
        """The variable the object is kept in."""
        return self._variables[gid]

    def function(self, gid: str) -> str:
        """The function that builds the object."""
        return f"make_{self._variables[gid]}"


def _python_name(gid: str, blocked: set[str]) -> str:
    name = gid.replace(".", "_")
    if keyword.iskeyword(name) or name in blocked:
        name += "_"
    return name
