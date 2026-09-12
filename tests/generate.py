"""Properties of generators, quantified over generator programs."""

import random
from collections.abc import Callable
from typing import Any

import minigun.arbitrary as a
import minigun.cardinality as c
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop
from tests._support import (
    Choice,
    Lists,
    Optional,
    Program,
    Tuples,
    breadth_first,
    greedy_descent,
    hashable_programs,
    interpret,
    member,
    programs,
)

###############################################################################
# Universal properties over programs
###############################################################################


@context(programs())
@prop("drawn values lie in the program's domain")
def _heads_in_domain(program: Program, rng: random.Random) -> bool:
    dissection = interpret(program).sample(rng)
    return dissection is None or member(program, dissection.head)


@context(programs())
@prop("every shrink tree node lies in the program's domain")
def _tree_in_domain(program: Program, rng: random.Random) -> bool:
    dissection = interpret(program).sample(rng)
    if dissection is None:
        return True
    return all(
        member(program, node.head) for node in breadth_first(dissection, 30)
    )


@context(programs())
@prop("sampling is a function of the random source")
def _deterministic(program: Program, seed: int) -> bool:
    generator = interpret(program)
    first = generator.sample(a.seed(seed))
    second = generator.sample(a.seed(seed))
    if first is None or second is None:
        return first is None and second is None
    return first.head == second.head and [
        node.head for node in breadth_first(first, 10)
    ] == [node.head for node in breadth_first(second, 10)]


@context(programs())
@prop("a finite cardinality bounds the number of distinct values")
def _cardinality_bounds(program: Program, rng: random.Random) -> bool:
    generator = interpret(program)
    if not generator.cardinality.is_finite or generator.cardinality.size > 64:
        return True
    size = int(generator.cardinality.size)
    seen: set[Any] = set()
    for _ in range(4 * size + 8):
        dissection = generator.sample(rng)
        if dissection is not None:
            seen.add(repr(dissection.head))
    return len(seen) <= size


@context(programs())
@prop("greedy shrinking terminates")
def _terminates(program: Program, rng: random.Random) -> bool:
    dissection = interpret(program).sample(rng)
    if dissection is None:
        return True
    return greedy_descent(dissection, 5000) < 5000


@context(programs())
@prop("cardinality is monotone under wrapping in a collection")
def _monotone(program: Program) -> bool:
    inner = interpret(program).cardinality
    outer = interpret(Lists(program)).cardinality
    return outer.size >= inner.size


@context(programs(), programs())
@prop("cardinality of tuples multiplies and of choice adds")
def _arithmetic(left: Program, right: Program) -> bool:
    l_card, r_card = interpret(left).cardinality, interpret(right).cardinality
    return (
        interpret(Tuples((left, right))).cardinality == l_card * r_card
        and interpret(Choice((left, right))).cardinality == l_card + r_card
        and interpret(Optional(left)).cardinality == l_card + c.ONE
    )


###############################################################################
# Specific generators
###############################################################################


@prop("unsized collections are not sized by their length draw")
def _collection_cardinality(rng: random.Random) -> bool:
    return (
        g.lists(g.ints()).cardinality.size > g.ints().cardinality.size
        and g.strings().cardinality.size > 101
        and not g.bind(
            lambda n: g.constant(n), g.small_nats()
        ).cardinality.is_finite
    )


@prop("int_range rejects inverted bounds")
def _int_range_rejects(lower: int, upper: int) -> bool:
    if lower >= upper:
        return True
    try:
        g.int_range(upper, lower)
    except ValueError:
        return True
    return False


@context(g.bounded_lists(1, 10, g.ints()))
@prop("one_of draws from its values and shrinks toward the first")
def _one_of(values: list[int], rng: random.Random) -> bool:
    dissection = g.one_of(values).sample(rng)
    if dissection is None:
        return False
    candidates = [node.head for node in dissection.shrinks()]
    return dissection.head in values and (
        dissection.head == values[0] or candidates[0] == values[0]
    )


@context(g.bounded_sets(0, 8, g.ints()))
@prop("subset_of draws subsets")
def _subset_of(values: set[int], rng: random.Random) -> bool:
    dissection = g.subset_of(values).sample(rng)
    return dissection is not None and dissection.head <= values


@prop("biased_bool honours certain biases")
def _biased_bool(rng: random.Random) -> bool:
    never = g.biased_bool(0.0).sample(rng)
    always = g.biased_bool(1.0).sample(rng)
    return (
        never is not None
        and always is not None
        and never.head is False
        and always.head is True
    )


@prop("rngs draws independent sources")
def _rngs(rng: random.Random) -> bool:
    first = g.rngs().sample(rng)
    second = g.rngs().sample(rng)
    return (
        first is not None
        and second is not None
        and first.head is not second.head
        and first.head.getrandbits(64) != second.head.getrandbits(64)
    )


@prop("optional offers None as the last alternative of any value")
def _optional_none(rng: random.Random) -> bool:
    dissection = g.optional(g.int_range(1, 100)).sample(rng)
    if dissection is None or dissection.head is None:
        return True
    return [node.head for node in dissection.shrinks()][-1] is None


@context(g.small_nats())
@prop("filter discards rejected draws and prunes rejected alternatives")
def _filter(seed: int) -> bool:
    generator = g.filter(lambda x: x % 3 == 0, g.int_range(0, 300))
    dissection = generator.sample(a.seed(seed))
    if dissection is None:
        return True
    return all(node.head % 3 == 0 for node in breadth_first(dissection, 40))


@context(g.small_nats())
@prop("lazy builds its generator once, on first draw")
def _lazy(seed: int) -> bool:
    builds = 0

    def _build() -> g.Generator[int]:
        nonlocal builds
        builds += 1
        return g.int_range(1, 10)

    generator = g.lazy(_build)
    if builds != 0:
        return False
    rng = a.seed(seed)
    for _ in range(3):
        dissection = generator.sample(rng)
        if dissection is None or not 1 <= dissection.head <= 10:
            return False
    return builds == 1


@context(g.tuples(g.int_range(0, 5), g.int_range(0, 5)), hashable_programs())
@prop("bounded collections respect their bounds and shrink no shorter")
def _bounded(
    bounds: tuple[int, int], element: Program, rng: random.Random
) -> bool:
    lower, upper = min(bounds), max(bounds)
    generator = g.bounded_lists(lower, upper, interpret(element))
    dissection = generator.sample(rng)
    if dissection is None:
        return True
    return all(
        lower <= len(node.head) <= upper
        for node in breadth_first(dissection, 30)
    )


_INFERENCE: list[tuple[Any, Callable[[Any], bool]]] = [
    (int, lambda v: isinstance(v, int)),
    (bool, lambda v: isinstance(v, bool)),
    (float, lambda v: isinstance(v, float)),
    (str, lambda v: isinstance(v, str)),
    (None, lambda v: v is None),
    (random.Random, lambda v: isinstance(v, random.Random)),
    (int | None, lambda v: v is None or isinstance(v, int)),
    (list[int], lambda v: isinstance(v, list)),
    (set[bool], lambda v: isinstance(v, set)),
    (dict[str, int], lambda v: isinstance(v, dict)),
    (tuple[int, str], lambda v: isinstance(v, tuple) and len(v) == 2),
    (tuple[int, ...], lambda v: v is None),
    (list, lambda v: v is None),
]


@context(g.one_of(_INFERENCE))
@prop("inferred generators produce instances of their annotation")
def _infer(case: tuple[Any, Callable[[Any], bool]], rng: random.Random) -> bool:
    annotation, accepts = case
    generator = g.infer(annotation)
    if generator is None:
        return accepts(None)
    dissection = generator.sample(rng)
    return dissection is not None and accepts(dissection.head)


spec = conj(
    _heads_in_domain,
    _tree_in_domain,
    _deterministic,
    _cardinality_bounds,
    _terminates,
    _monotone,
    _arithmetic,
    _collection_cardinality,
    _int_range_rejects,
    _one_of,
    _subset_of,
    _biased_bool,
    _rngs,
    _optional_none,
    _filter,
    _lazy,
    _bounded,
    _infer,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
