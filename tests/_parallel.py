"""Specifications for the parallel evaluation tests, rebuilt in worker
processes from plain data.

A worker process is spawned and unpickles each module's loader by its
qualified name, so the loaders here are module-level functions, given
their shapes through ``functools.partial``.
"""

import functools
import io
import os
import sys
import time
from typing import Any

import minigun.fixture as fixture
import minigun.generate as g
from minigun.search import assume
from minigun.specify import Conj, Neg, Prop, Spec

###############################################################################
# Values that do not survive pickling
###############################################################################


class Twofold(Exception):
    """An exception that pickles but does not unpickle: its constructor
    takes two arguments, its ``args`` hold one."""

    def __init__(self, left: int, right: int):
        super().__init__(f"{left} over {right}")


class Opaque:
    """A value that refuses to be pickled, shown by its number."""

    def __init__(self, n: int):
        self.n = n

    def __repr__(self) -> str:
        return f"Opaque({self.n})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Opaque) and other.n == self.n

    def __hash__(self) -> int:
        return hash(self.n)

    def __reduce__(self) -> tuple[Any, ...]:
        raise TypeError("Opaque values do not pickle")


###############################################################################
# The menu of laws
###############################################################################
def _holds(x: int) -> bool:
    return x >= 0


def _fails(x: int) -> bool:
    return x < 300


def _raises(x: int) -> bool:
    if x >= 300:
        raise ValueError(f"too large: {x}")
    return True


def _raises_twofold(x: int) -> bool:
    if x >= 300:
        raise Twofold(x, 3)
    return True


def _fails_opaque(x: Opaque) -> bool:
    return x.n < 300


def _discards(x: int) -> bool:
    assume(x < 5)
    return True


def _exits(x: int) -> bool:
    os._exit(3)


def _marks(token: str, x: int) -> bool:
    (fixture.temporary_path() / token).write_text(str(x))
    return True


def _fails_slowly(x: int) -> bool:
    time.sleep(0.03)
    return x < 300


#: Law kinds, each a law and the generator of its one argument.
LAWS: dict[str, tuple[Any, g.Generator[Any]]] = {
    "holds": (_holds, g.int_range(0, 1000)),
    "fails": (_fails, g.int_range(0, 1000)),
    "raises": (_raises, g.int_range(0, 1000)),
    "twofold": (_raises_twofold, g.int_range(0, 1000)),
    "opaque": (_fails_opaque, g.map(Opaque, g.int_range(0, 1000))),
    "discards": (_discards, g.int_range(0, 1000)),
}

#: The kinds a specification shape may draw.
KINDS = list(LAWS)

#: Kinds named in a shape only on purpose: ``exits`` ends its worker
#: process, ``slow`` is ``fails`` taking a while for each evaluation,
#: so its shrinking takes a while, and ``marks <token>`` holds, creating a
#: temporary fixture holding a file named ``token`` on every attempt.
SPECIAL: dict[str, tuple[Any, g.Generator[Any]]] = {
    "exits": (_exits, g.int_range(0, 9)),
    "slow": (_fails_slowly, g.int_range(0, 1000)),
}


###############################################################################
# Shapes
###############################################################################
#: A property: its law kind and declared attempts.
type Leaf = tuple[str, int]

#: A term of a module: whether it is negated, and a property alone (one
#: leaf, not nested) or a conjunction of the leaves.
type Term = tuple[bool, bool, list[Leaf]]

#: A module: its terms, possibly none.
type Shape = list[Term]


def _prop(desc: str, leaf: Leaf) -> Prop:
    kind, attempts = leaf
    law: Any
    if kind.startswith("marks "):
        law = functools.partial(_marks, kind.split()[1])
        generator: g.Generator[Any] = g.int_range(0, 9)
    else:
        law, generator = SPECIAL[kind] if kind in SPECIAL else LAWS[kind]
    return Prop(desc, law, {"x": generator}, attempts)


def build(index: int, shape: Shape) -> Spec:
    """The specification of the module at ``index`` of a run, its
    properties described by module and position so descriptions are
    unique across the run and the same in every process."""
    terms: list[Spec] = []
    count = 0
    for negated, alone, leaves in shape:
        props: list[Spec] = []
        for leaf in leaves:
            props.append(_prop(f"m{index} p{count} {leaf[0]}", leaf))
            count += 1
        term: Spec = (
            props[0] if alone and len(props) == 1 else Conj(tuple(props))
        )
        terms.append(Neg(term) if negated else term)
    return Conj(tuple(terms))


#: A module holding every kind of law, plain and negated, so each kind is
#: seen on every attempt.
EVERY_KIND: Shape = [(False, False, [(kind, 3) for kind in KINDS])] + [
    (True, True, [(kind, 3)]) for kind in KINDS
]


def fails_to_load(message: str) -> Spec:
    """A loader that raises, silencing the worker's report of it."""
    sys.stderr = io.StringIO()
    raise RuntimeError(message)
