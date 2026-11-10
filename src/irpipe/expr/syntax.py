"""Reading an expression: text -> tokens -> a small syntax tree.

    expr    := term (("+" | "-") term)*
    term    := unary (("*" | "/") unary)*
    unary   := ("+" | "-") unary | power
    power   := atom ("**" unary)?           right-associative: 2**3**2 = 2**9
    atom    := number | name | name "(" args ")" | "(" expr ")"
    args    := expr ("," expr)*

Numbers are written ``12``, ``0.5`` or ``1.5e-3``. Nothing else is read: no
attribute access, no strings, no assignment, so evaluating can never run code.
"""

import re
from dataclasses import dataclass
from fractions import Fraction

from irpipe.expr.errors import ExprError

_TOKEN = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>\*\*|[-+*/(),])|(?P<other>\S))"
)


@dataclass(frozen=True)
class Number:
    value: Fraction


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: "Node"


@dataclass(frozen=True)
class Binary:
    op: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Call:
    function: str
    args: tuple["Node", ...]


type Node = Number | Name | Unary | Binary | Call


@dataclass(frozen=True)
class Token:
    kind: str  # "number", "name", "op" or "end"
    text: str
    at: int  # character position, from 1


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:  # only trailing whitespace is left
            break
        kind = match.lastgroup or "other"
        token = match.group(kind)
        at = match.start(kind) + 1
        if kind == "other":
            hint = "write powers with **" if token == "^" else None
            raise ExprError(f"unexpected '{token}' at character {at}", hint=hint)
        tokens.append(Token(kind, token, at))
        position = match.end()
    tokens.append(Token("end", "", len(text) + 1))
    return tokens


def parse(text: str) -> Node:
    """The syntax tree of ``text``; ExprError says where reading failed."""
    if not text.strip():
        raise ExprError("the expression is empty")
    parser = _Parser(tokenize(text))
    node = parser.expr()
    parser.expect_end()
    return node


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    @property
    def token(self) -> Token:
        return self.tokens[self.index]

    def take(self, *texts: str) -> Token | None:
        if self.token.kind == "op" and self.token.text in texts:
            self.index += 1
            return self.tokens[self.index - 1]
        return None

    def expect(self, text: str) -> None:
        if self.take(text) is None:
            raise self.unexpected(f"'{text}'")

    def expect_end(self) -> None:
        if self.token.kind != "end":
            raise self.unexpected("the end of the expression")

    def unexpected(self, wanted: str) -> ExprError:
        found = "the end" if self.token.kind == "end" else f"'{self.token.text}'"
        return ExprError(f"expected {wanted} at character {self.token.at}, found {found}")

    def expr(self) -> Node:
        node = self.term()
        while op := self.take("+", "-"):
            node = Binary(op.text, node, self.term())
        return node

    def term(self) -> Node:
        node = self.unary()
        while op := self.take("*", "/"):
            node = Binary(op.text, node, self.unary())
        return node

    def unary(self) -> Node:
        if op := self.take("+", "-"):
            return Unary(op.text, self.unary())
        return self.power()

    def power(self) -> Node:
        base = self.atom()
        if self.take("**"):
            return Binary("**", base, self.unary())
        return base

    def atom(self) -> Node:
        token = self.token
        if token.kind == "number":
            self.index += 1
            return Number(Fraction(token.text))
        if token.kind == "name":
            self.index += 1
            if self.take("("):
                args = [self.expr()]
                while self.take(","):
                    args.append(self.expr())
                self.expect(")")
                return Call(token.text, tuple(args))
            return Name(token.text)
        if self.take("("):
            node = self.expr()
            self.expect(")")
            return node
        raise self.unexpected("a number, a name or '('")
