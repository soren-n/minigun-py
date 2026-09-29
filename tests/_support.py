"""Shared machinery for Minigun's self tests.

Minigun is tested the way its tutorial teaches: by modeling. A small AST of
generator programs is interpreted into real generators, and a denotation
function decides membership of a value in a program's domain. Properties
then quantify over programs, so counterexamples are readable programs and
shrink through the ordinary combinators.
"""

import datetime
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
class Tiered:
    name: str


@dataclass(frozen=True)
class Floats:
    pass


@dataclass(frozen=True)
class FloatRange:
    lower: float
    upper: float
    edges: bool


@dataclass(frozen=True)
class Dates:
    first: datetime.date
    last: datetime.date


@dataclass(frozen=True)
class Strings:
    alphabet: str


@dataclass(frozen=True)
class IntRange:
    lower: int
    upper: int


@dataclass(frozen=True)
class NonzeroRange:
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


@dataclass(frozen=True)
class Replicate:
    count: "Program"
    inner: "Program"


@dataclass(frozen=True)
class ListAppend:
    items: "Program"
    item: "Program"


@dataclass(frozen=True)
class DictInsert:
    entries: "Program"
    key: "Program"
    value: "Program"


@dataclass(frozen=True)
class SetAdd:
    items: "Program"
    item: "Program"


@dataclass(frozen=True)
class MapList:
    items: tuple["Program", ...]
    ordered: bool


@dataclass(frozen=True)
class MapDict:
    items: tuple["Program", ...]


@dataclass(frozen=True)
class MapSet:
    items: tuple["Program", ...]


type Program = (
    Bools
    | Tiered
    | Floats
    | FloatRange
    | Dates
    | Strings
    | IntRange
    | NonzeroRange
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
    | Replicate
    | ListAppend
    | DictInsert
    | SetAdd
    | MapList
    | MapDict
    | MapSet
)

#: The tiered integer generators by name, with their documented bounds.
TIERED: dict[str, tuple[Callable[[], g.Generator[int]], int, int]] = {
    "small_nats": (g.small_nats, 0, 100),
    "nats": (g.nats, 0, 10000),
    "big_nats": (g.big_nats, 0, 1000000),
    "small_ints": (g.small_ints, -100, 100),
    "ints": (g.ints, -10000, 10000),
    "big_ints": (g.big_ints, -1000000, 1000000),
}

#: Largest list a Replicate program draws: its count modulo this plus one.
REPLICATE_MODULUS = 4

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
        case Tiered(name):
            return TIERED[name][0]()
        case Floats():
            return g.floats()
        case FloatRange(lower, upper, edges):
            return g.float_range(lower, upper, edges)
        case Dates(first, last):
            return g.dates(first, last)
        case Strings(alphabet):
            return g.strings(alphabet)
        case IntRange(lower, upper):
            return g.int_range(lower, upper)
        case NonzeroRange(lower, upper):
            return g.nonzero_int_range(lower, upper)
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
        case Replicate(count, inner):
            element = interpret(inner)

            def _replicate(n: int) -> g.Generator[list[Any]]:
                length = abs(n) % REPLICATE_MODULUS
                return g.bounded_lists(length, length, element)

            return g.bind(_replicate, interpret(count))
        case ListAppend(items, item):
            return g.list_append(interpret(items), interpret(item))
        case DictInsert(entries, key, value):
            return g.dict_insert(
                interpret(entries), interpret(key), interpret(value)
            )
        case SetAdd(items, item):
            return g.set_add(interpret(items), interpret(item))
        case MapList(items, ordered):
            return g.map_list([interpret(item) for item in items], ordered)
        case MapDict(items):
            return g.map_dict(
                {f"k{i}": interpret(item) for i, item in enumerate(items)}
            )
        case MapSet(items):
            return g.map_set({interpret(item) for item in items})
        case _:
            assert_never(program)


def _without[K](entries: dict[K, Any], key: K) -> dict[K, Any]:
    return {k: v for k, v in entries.items() if k != key}


def _assigns(items: tuple["Program", ...], values: list[Any]) -> bool:
    """Whether the values can be drawn one from each program, in some
    order: a matching of values to programs."""
    if not values:
        return True
    first, rest = values[0], values[1:]
    return any(
        member(item, first) and _assigns(items[:i] + items[i + 1 :], rest)
        for i, item in enumerate(items)
    )


def member(program: Program, value: Any) -> bool:
    """Whether a value lies in the domain denoted by a program."""
    match program:
        case Bools():
            return isinstance(value, bool)
        case Tiered(name):
            _, lower, upper = TIERED[name]
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and lower <= value <= upper
            )
        case Floats():
            return isinstance(value, float) and math.isfinite(value)
        case FloatRange(lower, upper, _):
            return isinstance(value, float) and lower <= value <= upper
        case Dates(first, last):
            return (
                isinstance(value, datetime.date)
                and not isinstance(value, datetime.datetime)
                and first <= value <= last
            )
        case Strings(alphabet):
            return (
                isinstance(value, str)
                and len(value) <= 100
                and all(char in alphabet for char in value)
            )
        case IntRange(lower, upper):
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and lower <= value <= upper
            )
        case NonzeroRange(lower, upper):
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value != 0
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
        case Replicate(_, inner):
            return (
                isinstance(value, list)
                and len(value) < REPLICATE_MODULUS
                and all(member(inner, item) for item in value)
            )
        case ListAppend(items, item):
            return (
                isinstance(value, list)
                and len(value) >= 1
                and member(item, value[-1])
                and member(items, value[:-1])
            )
        case DictInsert(entries, key, value_program):
            return isinstance(value, dict) and any(
                member(key, k)
                and member(value_program, v)
                and member(entries, _without(value, k))
                for k, v in value.items()
            )
        case SetAdd(items, item):
            return isinstance(value, set) and any(
                member(item, x) and member(items, value - {x}) for x in value
            )
        case MapList(items, ordered):
            if not isinstance(value, list) or len(value) != len(items):
                return False
            if ordered:
                return _assigns(items, value) and value == sorted(value)
            return all(
                member(item, x) for item, x in zip(items, value, strict=True)
            )
        case MapDict(items):
            return (
                isinstance(value, dict)
                and list(value) == [f"k{i}" for i in range(len(items))]
                and all(
                    member(item, value[f"k{i}"]) for i, item in enumerate(items)
                )
            )
        case MapSet(items):
            # Equal draws collapse, so the set may be smaller than the
            # number of generators; every element came from one of them.
            return (
                isinstance(value, set)
                and 1 <= len(value) <= len(items)
                and all(any(member(item, x) for item in items) for x in value)
            )
        case _:
            assert_never(program)


###############################################################################
# Generators of programs
###############################################################################
def _int_range() -> g.Generator[Program]:
    def _make(a: int, b: int) -> Program:
        return IntRange(min(a, b), max(a, b))

    return g.map(_make, g.small_ints(), g.small_ints())


def _nonzero_range() -> g.Generator[Program]:
    def _make(a: int, b: int) -> Program:
        lower, upper = min(a, b), max(a, b)
        # The one range without a non-zero value is widened to hold one.
        return NonzeroRange(lower, upper if (lower, upper) != (0, 0) else 1)

    return g.map(_make, g.small_ints(), g.small_ints())


def _float_range() -> g.Generator[Program]:
    def _make(a: float, b: float, edges: bool) -> Program:
        return FloatRange(min(a, b), max(a, b), edges)

    return g.map(_make, g.floats(), g.floats(), g.bools())


_EPOCH = datetime.date(2000, 1, 1)


def _dates() -> g.Generator[Program]:
    def _make(offset: int, span: int) -> Program:
        first = _EPOCH + datetime.timedelta(days=offset)
        return Dates(first, first + datetime.timedelta(days=span))

    return g.map(_make, g.int_range(-20000, 20000), g.int_range(0, 1000))


#: Alphabets of string programs: the default, a narrow one, and one letter.
ALPHABETS = (string.printable, string.ascii_uppercase, "a")


def _strings() -> g.Generator[Program]:
    return g.map(Strings, g.one_of(list(ALPHABETS)))


def _one_of() -> g.Generator[Program]:
    def _make(first: int, rest: list[int]) -> Program:
        return OneOf((first, *rest))

    return g.map(_make, g.small_ints(), g.bounded_lists(0, 4, g.small_ints()))


def int_programs() -> g.Generator[Program]:
    """Programs whose values are integers, filtered and mapped up to twice,
    so discards propagate through ``filter`` and ``map``."""
    base: g.Generator[Program] = g.choice(
        g.map(Tiered, g.one_of(list(TIERED))),
        _int_range(),
        _nonzero_range(),
        g.map(Const, g.small_ints()),
        _one_of(),
    )

    def _filtered(predicate: str, inner: Program) -> Program:
        return Filtered(predicate, inner)

    def _mapped(function: str, inner: Program) -> Program:
        return Mapped(function, inner)

    def _wrapped(inner: g.Generator[Program]) -> g.Generator[Program]:
        return g.weighted_choice(
            (4, inner),
            (1, g.map(_filtered, g.one_of(list(PREDICATES)), inner)),
            (1, g.map(_mapped, g.one_of(list(FUNCTIONS)), inner)),
        )

    return _wrapped(_wrapped(base))


def hashable_programs() -> g.Generator[Program]:
    """Programs whose values are hashable, fit for set elements and keys."""
    leaves: g.Generator[Program] = g.choice(
        g.constant(Bools()), _strings(), _dates(), int_programs()
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
        hashable_programs(), g.constant(Floats()), _float_range()
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

    def _append(items: Program, item: Program) -> Program:
        return ListAppend(Lists(items), item)

    def _insert(key: Program, value: Program) -> Program:
        return DictInsert(Dicts(key, value), key, value)

    def _add(item: Program) -> Program:
        return SetAdd(Sets(item), item)

    def _map_list(items: list[Program], ordered: bool) -> Program:
        return MapList(tuple(items), ordered)

    def _map_dict(items: list[Program]) -> Program:
        return MapDict(tuple(items))

    def _map_set(items: list[Program]) -> Program:
        return MapSet(tuple(items))

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
        (1, g.map(Replicate, int_programs(), sub)),
        (1, g.map(_append, sub, sub)),
        (1, g.map(_insert, hashable_programs(), sub)),
        (1, g.map(_add, hashable_programs())),
        (1, g.map(_map_list, g.bounded_lists(1, 3, int_programs()), g.bools())),
        (1, g.map(_map_dict, g.bounded_lists(0, 3, sub))),
        (1, g.map(_map_set, g.bounded_lists(1, 3, hashable_programs()))),
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


def greedy_leaf[T](dissection: s.Dissection[T]) -> T:
    """The value reached by following first children to a leaf."""
    node = dissection
    while (child := next(node.shrinks(), None)) is not None:
        node = child
    return node.head
