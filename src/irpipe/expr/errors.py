"""The two ways an expression can fail: it cannot be read or computed, or values loop."""


class ExprError(ValueError):
    """An expression that cannot be read or computed; ``hint`` suggests a fix."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class CycleError(ExprError):
    """Named values that refer to each other in a loop; ``loop`` lists them in order."""

    def __init__(self, loop: list[str]) -> None:
        super().__init__(
            "values refer to each other in a loop: " + " -> ".join([*loop, loop[0]]),
            hint="give one of them a value that does not depend on the others",
        )
        self.loop = loop
