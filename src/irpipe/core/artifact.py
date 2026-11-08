"""Names and types of the data that flows between stages.

Stages never call each other. They exchange artifacts (the IR, the LIR, a
report...) through the run context, and every artifact is addressed by an
``ArtifactKey``: a name plus the Python type its value must have. Keys are
module-level constants, so a stage's declaration reads as its data flow:

    IR = ArtifactKey("ir", IRDocument, "the IR as the agent submitted it")

    class Validate(Stage):
        requires = (IR,)
        provides = (IR_VALID,)
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

# T is declared the classic way on purpose. With the newer ``class ArtifactKey[T]``
# syntax, mypy infers this frozen dataclass as covariant and then accepts
# ``ctx.write(COUNT, "three")`` by widening T to ``object``. An invariant T keeps
# writing the wrong type a static error as well as a runtime one.
T = TypeVar("T")


@dataclass(frozen=True)
class ArtifactKey(Generic[T]):  # noqa: UP046
    """The name and value type of one artifact.

    ``value_type`` is checked with ``isinstance`` whenever the artifact is
    written or read, so it must be a plain class (``dict``, not ``dict[str, int]``).
    """

    name: str
    value_type: type[T]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValueError(f"artifact name must be a Python identifier, got {self.name!r}")

    def __str__(self) -> str:
        return self.name
