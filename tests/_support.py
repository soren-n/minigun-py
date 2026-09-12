"""Shared machinery for Minigun's self tests.

Minigun is tested the way its tutorial teaches: by modeling. A small AST of
generator programs is interpreted into real generators, and a denotation
function decides membership of a value in a program's domain. Properties
then quantify over programs, so counterexamples are readable programs and
shrink through the ordinary combinators.
"""

import math
import string
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, assert_never

import minigun.generate as g
import minigun.shrink as s

###############################################################################
# Generator programs
###############################################################################


@dataclass(frozen=True)
class Bools:
    pass


@dataclass(frozen=True)
class Ints:
    pass


@dataclass(frozen=True)
class Floats:
    pass


@dataclass(frozen=True)
class Strings:
    pass


@dataclass(frozen=True)
class IntRange:
    lower: int
    upper: int


@dataclass(frozen=True)
class Const:
    value: int


@dataclass(frozen=True)
class OneOf:
    values: tuple[int, ...]


@dataclass(frozen=True)
class Lists:
    inner: "Program"


@dataclass(frozen=True)
class BoundedLists:
    lower: int
    upper: int
    inner: "Program"


@dataclass(frozen=True)
class Sets:
    inner: "Program"


@dataclass(frozen=True)
class Dicts:
    keys: "Program"
    values: "Program"


@dataclass(frozen=True)
class Tuples:
    items: tuple["Program", ...]


@dataclass(frozen=True)
class Optional:
    inner: "Program"


@dataclass(frozen=True)
class Choice:
    branches: tuple["Program", ...]


@dataclass(frozen=True)
class Filtered:
    predicate: str
    inner: "Program"


@dataclass(frozen=True)
class Mapped:
    function: str
    inner: "Program"


type Program = (
    Bools
    | Ints
    | Floats
    | Strings
    | IntRange
    | Const
    | OneOf
    | Lists
    | BoundedLists
    | Sets
    | Dicts
    | Tuples
    | Optional
    | Choice
    | Filtered
    | Mapped
)

PREDICATES: dict[str, Callable[[int], bool]] = {
    "even": lambda x: x % 2 == 0,
    "positive": lambda x: x > 0,
    "small": lambda x: abs(x) < 50,
}

FUNCTIONS: dict[str, Callable[[int], int]] = {
    "double": lambda x: x * 2,
    "negate": lambda x: -x,
    "succ": lambda x: x + 1,
}

# Inverse images of the mapping functions, for the denotation.
_INVERSES: dict[str, Callable[[int], int | None]] = {
    "double": lambda y: y // 2 if y % 2 == 0 else None,
    "negate": lambda y: -y,
    "succ": lambda y: y - 1,
}


###############################################################################
# Interpretation
###############################################################################
def interpret(program: Program) -> g.Generator[Any]:
    """The generator denoted by a program."""
    match program:
        case Bools():
            return g.bools()
        case Ints():
            return g.ints()
        case Floats():
            return g.floats()
        case Strings():
            return g.strings()
        case IntRange(lower, upper):
            return g.int_range(lower, upper)
        case Const(value):
            return g.constant(value)
        case OneOf(values):
            return g.one_of(list(values))
        case Lists(inner):
            return g.lists(interpret(inner))
        case BoundedLists(lower, upper, inner):
            return g.bounded_lists(lower, upper, interpret(inner))
        case Sets(inner):
            return g.sets(interpret(inner))
        case Dicts(keys, values):
            return g.dicts(interpret(keys), interpret(values))
        case Tuples(items):
            return g.tuples(*[interpret(item) for item in items])
        case Optional(inner):
            return g.optional(interpret(inner))
        case Choice(branches):
            return g.choice(*[interpret(branch) for branch in branches])
        case Filtered(predicate, inner):
            return g.filter(PREDICATES[predicate], interpret(inner))
        case Mapped(function, inner):
            return g.map(FUNCTIONS[function], interpret(inner))
        case _:
            assert_never(program)


def member(program: Program, value: Any) -> bool:
    """Whether a value lies in the domain denoted by a program."""
    match program:
        case Bools():
            return isinstance(value, bool)
        case Ints():
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and -10000 <= value <= 10000
            )
        case Floats():
            return isinstance(value, float) and math.isfinite(value)
        case Strings():
            return (
                isinstance(value, str)
                and len(value) <= 100
                and all(char in string.printable for char in value)
            )
        case IntRange(lower, upper):
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and lower <= value <= upper
            )
        case Const(constant):
            return value == constant
        case OneOf(values):
            return value in values
        case Lists(inner):
            return (
                isinstance(value, list)
                and len(value) <= 100
                and all(member(inner, item) for item in value)
            )
        case BoundedLists(lower, upper, inner):
            return (
                isinstance(value, list)
                and lower <= len(value) <= upper
                and all(member(inner, item) for item in value)
            )
        case Sets(inner):
            return isinstance(value, set) and all(
                member(inner, item) for item in value
            )
        case Dicts(keys, values):
            return isinstance(value, dict) and all(
                member(keys, key) and member(values, val)
                for key, val in value.items()
            )
        case Tuples(items):
            return (
                isinstance(value, tuple)
                and len(value) == len(items)
                and all(
                    member(item, element)
                    for item, element in zip(items, value, strict=True)
                )
            )
        case Optional(inner):
            return value is None or member(inner, value)
        case Choice(branches):
            return any(member(branch, value) for branch in branches)
        case Filtered(predicate, inner):
            return member(inner, value) and PREDICATES[predicate](value)
        case Mapped(function, inner):
            if not isinstance(value, int):
                return False
            preimage = _INVERSES[function](value)
            return preimage is not None and member(inner, preimage)
        case _:
            assert_never(program)


###############################################################################
# Generators of programs
###############################################################################
def _int_range() -> g.Generator[Program]:
    def _make(a: int, b: int) -> Program:
        return IntRange(min(a, b), max(a, b))

    return g.map(_make, g.small_ints(), g.small_ints())


def _one_of() -> g.Generator[Program]:
    def _make(first: int, rest: list[int]) -> Program:
        return OneOf((first, *rest))

    return g.map(_make, g.small_ints(), g.bounded_lists(0, 4, g.small_ints()))


def int_programs() -> g.Generator[Program]:
    """Programs whose values are integers."""
    base: g.Generator[Program] = g.choice(
        g.constant(Ints()),
        _int_range(),
        g.map(Const, g.small_ints()),
        _one_of(),
    )

    def _filtered(predicate: str, inner: Program) -> Program:
        return Filtered(predicate, inner)

    def _mapped(function: str, inner: Program) -> Program:
        return Mapped(function, inner)

    return g.weighted_choice(
        (4, base),
        (1, g.map(_filtered, g.one_of(list(PREDICATES)), base)),
        (1, g.map(_mapped, g.one_of(list(FUNCTIONS)), base)),
    )


def hashable_programs() -> g.Generator[Program]:
    """Programs whose values are hashable, fit for set elements and keys."""
    leaves: g.Generator[Program] = g.choice(
        g.constant(Bools()), g.constant(Strings()), int_programs()
    )

    def _tuple(a: Program, b: Program) -> Program:
        return Tuples((a, b))

    return g.weighted_choice(
        (4, leaves),
        (1, g.map(Optional, leaves)),
        (1, g.map(_tuple, leaves, leaves)),
    )


def _sized(depth: int) -> g.Generator[Program]:
    leaves: g.Generator[Program] = g.choice(
        hashable_programs(), g.constant(Floats())
    )
    if depth == 0:
        return leaves
    sub = _sized(depth - 1)

    def _bounded(a: int, b: int, inner: Program) -> Program:
        return BoundedLists(min(a, b), max(a, b), inner)

    def _tuple(a: Program, b: Program) -> Program:
        return Tuples((a, b))

    def _choice(a: Program, b: Program) -> Program:
        return Choice((a, b))

    small = g.int_range(0, 5)
    return g.weighted_choice(
        (4, leaves),
        (1, g.map(Lists, sub)),
        (1, g.map(_bounded, small, small, sub)),
        (1, g.map(Sets, hashable_programs())),
        (1, g.map(Dicts, hashable_programs(), sub)),
        (1, g.map(_tuple, sub, sub)),
        (1, g.map(Optional, sub)),
        (1, g.map(_choice, sub, sub)),
    )


def programs() -> g.Generator[Program]:
    """Generator programs of bounded nesting depth."""
    return _sized(2)


###############################################################################
# Walking dissections
###############################################################################
def breadth_first[T](
    dissection: s.Dissection[T], limit: int
) -> Iterator[s.Dissection[T]]:
    """The first ``limit`` nodes of a shrink tree in breadth-first order,
    starting with the root."""
    frontier = [dissection]
    seen = 0
    while frontier and seen < limit:
        node = frontier.pop(0)
        yield node
        seen += 1
        for child in node.shrinks():
            if len(frontier) + seen >= limit:
                break
            frontier.append(child)


def greedy_descent[T](dissection: s.Dissection[T], limit: int) -> int:
    """Follow first children until a leaf; the number of steps taken, or
    ``limit`` when the descent did not end within ``limit`` steps."""
    steps = 0
    node = dissection
    while steps < limit:
        child = next(node.shrinks(), None)
        if child is None:
            return steps
        node = child
        steps += 1
    return limit
