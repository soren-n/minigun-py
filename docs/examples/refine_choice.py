"""Refining generators with choice: an arithmetic expression AST."""

from dataclasses import dataclass

import minigun.generate as g
from minigun import check
from minigun.specify import context, prop


# -- start: ast --
@dataclass
class Number:
    value: int


@dataclass
class Plus:
    left: "Arith"
    right: "Arith"


@dataclass
class Minus:
    left: "Arith"
    right: "Arith"


@dataclass
class Times:
    left: "Arith"
    right: "Arith"


@dataclass
class Divide:
    left: "Arith"
    right: "Arith"


type Arith = Number | Plus | Minus | Times | Divide
# -- end: ast --


# -- start: generators --
def sized_arith(size: int) -> g.Generator[Arith]:
    if size == 0:
        return g.map(Number, g.ints())
    half = size // 2
    sub: g.Generator[Arith] = g.lazy(lambda: sized_arith(half))
    return g.weighted_choice(
        (1, g.map(Number, g.ints())),
        (half, g.map(Plus, sub, sub)),
        (half, g.map(Minus, sub, sub)),
        (half, g.map(Times, sub, sub)),
        (half, g.map(Divide, sub, sub)),
    )


def arith() -> g.Generator[Arith]:
    return g.bind(sized_arith, g.small_nats())


# -- end: generators --


def leaves(expr: Arith) -> int:
    match expr:
        case Number():
            return 1
        case (
            Plus(left, right)
            | Minus(left, right)
            | Times(left, right)
            | Divide(left, right)
        ):
            return leaves(left) + leaves(right)


@context(arith())
@prop("An arithmetic expression has at least one number")
def _has_a_number(expr: Arith) -> bool:
    return leaves(expr) >= 1


spec = _has_a_number

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
