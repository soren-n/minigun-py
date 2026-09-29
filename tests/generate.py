"""Properties of generators, quantified over generator programs."""

import collections.abc
import dataclasses
import datetime
import math
import random
import sys
import typing
from collections.abc import Callable
from typing import Any

import minigun.arbitrary as a
import minigun.cardinality as c
import minigun.generate as g
import minigun.shrink as s
from minigun import assume, check
from minigun.specify import conj, context, prop
from tests._support import (
    TIERED,
    Choice,
    Lists,
    Optional,
    Program,
    Tuples,
    breadth_first,
    greedy_descent,
    greedy_leaf,
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
    # Products are compared up to rounding: map_set multiplies its
    # generators in set order, which differs between interpretations.
    def _same(x: c.Cardinality, y: c.Cardinality) -> bool:
        if x.is_finite != y.is_finite:
            return False
        return not x.is_finite or math.isclose(x.size, y.size, rel_tol=1e-9)

    l_card, r_card = interpret(left).cardinality, interpret(right).cardinality
    return (
        _same(interpret(Tuples((left, right))).cardinality, l_card * r_card)
        and _same(interpret(Choice((left, right))).cardinality, l_card + r_card)
        and _same(interpret(Optional(left)).cardinality, l_card + c.ONE)
    )


###############################################################################
# Specific generators
###############################################################################


@context(
    g.int_range(0, 100),
    g.int_range(0, 100),
)
@prop("a sized collection's cardinality is the sum over its sizes")
def _sized_cardinality(lower: int, upper: int) -> bool:
    # Every item domain is checked on every attempt: each takes its own
    # path through the computation, and a property drawing one of them
    # would see some too rarely under a time budget.
    lower, upper = min(lower, upper), max(lower, upper)

    def _agrees(item: g.Generator[Any], lower: int, upper: int) -> bool:
        expected = c.ZERO
        for size in range(lower, upper + 1):
            expected = expected + item.cardinality ** c.finite(size)
        actual = g.bounded_lists(lower, upper, item).cardinality
        if actual.is_finite != expected.is_finite:
            return False
        return not actual.is_finite or math.isclose(
            actual.size, expected.size, rel_tol=1e-9
        )

    # Tiny bounds, where each term of the geometric series shows, are
    # checked on every attempt beside the drawn ones.
    tiny = [(low, high) for high in range(3) for low in range(high + 1)]
    return all(
        _agrees(item, low, high)
        for item in _ITEMS
        for low, high in [(lower, upper), *tiny]
    )


#: Item generators whose domains are unbounded, of one value, of none,
#: and finite of several sizes.
_ITEMS: list[g.Generator[Any]] = [
    g.ints(),
    g.bools(),
    g.constant(0),
    g.floats(),
    g.big_ints(),
    g.int_range(0, 9),
    g.with_cardinality(g.constant(0), c.ZERO),
]


@prop("unsized collections are sized over lengths zero to one hundred")
def _collection_cardinality(seed: int) -> bool:
    def _sized(item: g.Generator[Any]) -> bool:
        expected = g.bounded_lists(0, 100, item).cardinality
        return (
            g.lists(item).cardinality == expected
            and g.sets(item).cardinality == expected
            and not g.bind(lambda n: g.constant(n), item).cardinality.is_finite
        )

    return all(map(_sized, _ITEMS))


@context(g.small_ints(), g.small_ints(), g.bounded_sets(0, 12, g.ints()))
@prop("integer, boolean and subset generators report their exact size")
def _exact_cardinality(lower: int, upper: int, values: set[int]) -> bool:
    lower, upper = min(lower, upper), max(lower, upper)
    return (
        g.int_range(lower, upper).cardinality.size == upper - lower + 1
        and g.bools().cardinality.size == 2
        and g.biased_bool(0.5).cardinality.size == 2
        and g.subset_of(values).cardinality.size == 2 ** len(values)
        and all(
            make().cardinality.size == high - low + 1
            for make, low, high in TIERED.values()
        )
        and (
            (lower, upper) == (0, 0)
            or g.nonzero_int_range(lower, upper).cardinality.size
            == upper - lower + 1 - (lower <= 0 <= upper)
        )
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


def _rejects(action: Callable[[], Any], error: type[BaseException]) -> bool:
    try:
        action()
    except error:
        return True
    return False


###############################################################################
# Float ranges
###############################################################################

_MAX = sys.float_info.max


def _float_bounds() -> g.Generator[tuple[float, float]]:
    def _ordered(x: float, y: float) -> tuple[float, float]:
        return min(x, y), max(x, y)

    return g.choice(
        g.map(_ordered, g.floats(), g.floats()),
        g.map(_ordered, g.float_range(-_MAX, _MAX), g.float_range(-_MAX, _MAX)),
    )


@context(_float_bounds())
@prop("float_range offers its shrink target first")
def _float_range_target(
    bounds: tuple[float, float], rng: random.Random
) -> bool:
    lower, upper = bounds
    target = max(lower, min(0.0, upper))
    dissection = g.float_range(lower, upper).sample(rng)
    if dissection is None:
        return False
    if dissection.head == target:
        return True
    return next(dissection.shrinks()).head == target


def _drawn_edges(lower: float, upper: float, rng: random.Random) -> bool:
    """Whether 2000 draws of a range hold its bounds, zero, and the
    smallest subnormal on each side of zero the range extends to."""
    expected = {lower, upper, 0.0}
    if upper > 0.0:
        expected.add(math.ulp(0.0))
    if lower < 0.0:
        expected.add(-math.ulp(0.0))
    generator = g.float_range(lower, upper)
    drawn = set()
    for _ in range(2000):
        dissection = generator.sample(rng)
        if dissection is None:
            return False
        drawn.add(dissection.head)
    return expected <= drawn


@context(g.float_range(-10.0, -1.0), g.float_range(1.0, 10.0))
@prop(
    "float_range draws its bounds and tiny magnitudes down to 5e-324",
    attempts=20,
)
def _float_range_edges(lower: float, upper: float, rng: random.Random) -> bool:
    # Every attempt also checks the ranges that start and end at zero,
    # which draw tiny magnitudes on their open side only. Each expected
    # value is drawn with probability at least 1/60 per draw, so all of
    # them appear in 2000 draws but for a 1e-14 chance.
    return (
        _drawn_edges(lower, upper, rng)
        and _drawn_edges(0.0, upper, rng)
        and _drawn_edges(lower, 0.0, rng)
    )


@context(g.float_range(-1e-300, 0.0), g.float_range(0.0, 1e-300))
@prop(
    "float ranges narrower than the tiny magnitudes keep every draw inside",
    attempts=50,
)
def _float_range_tiny(lower: float, upper: float, rng: random.Random) -> bool:
    # Most tiny magnitudes exceed such a range; they must be clamped to
    # the bound on their own side.
    assume(lower < upper)
    generator = g.float_range(lower, upper)
    for _ in range(200):
        dissection = generator.sample(rng)
        if dissection is None or not lower <= dissection.head <= upper:
            return False
    return True


@prop(
    "float_range without edges does not favour zero or its bounds",
    attempts=20,
)
def _float_range_plain(rng: random.Random) -> bool:
    generator = g.float_range(-1.0, 1.0, edges=False)
    for _ in range(2000):
        dissection = generator.sample(rng)
        if dissection is None or dissection.head in (-1.0, 1.0):
            return False
        if abs(dissection.head) < 1e-12:
            return False
    return True


@context(_float_bounds())
@prop("float_range rejects inverted and non-finite bounds")
def _float_range_rejects(bounds: tuple[float, float]) -> bool:
    lower, upper = bounds
    invalid = [(lower, math.nan), (math.nan, upper), (-math.inf, upper)]
    invalid.append((lower, math.inf))
    if lower < upper:
        invalid.append((upper, lower))
    return all(
        _rejects(lambda b=pair: g.float_range(*b), ValueError)
        for pair in invalid
    )


###############################################################################
# Dates and times
###############################################################################

_EPOCH = datetime.datetime(2000, 1, 1)


@context(g.int_range(-10000, 10000), g.int_range(0, 1000))
@prop("dates lie in their range and shrink to the first")
def _dates(offset: int, span: int, rng: random.Random) -> bool:
    first = _EPOCH.date() + datetime.timedelta(days=offset)
    last = first + datetime.timedelta(days=span)
    dissection = g.dates(first, last).sample(rng)
    if dissection is None:
        return False
    nodes = [node.head for node in breadth_first(dissection, 30)]
    return all(first <= day <= last for day in nodes) and (
        greedy_leaf(dissection) == first
    )


@context(g.int_range(0, 10**6), g.int_range(1, 10**4), g.int_range(0, 10**7))
@prop("datetimes lie on their resolution grid and shrink to the first")
def _datetimes(
    offset: int, resolution_s: int, span_s: int, rng: random.Random
) -> bool:
    first = _EPOCH + datetime.timedelta(seconds=offset)
    last = first + datetime.timedelta(seconds=span_s)
    resolution = datetime.timedelta(seconds=resolution_s)
    dissection = g.datetimes(first, last, resolution).sample(rng)
    if dissection is None:
        return False
    return (
        all(
            first <= node.head <= last
            and (node.head - first) % resolution == datetime.timedelta(0)
            for node in breadth_first(dissection, 30)
        )
        and greedy_leaf(dissection) == first
    )


@context(g.int_range(-10000, 10000))
@prop("single-point date and datetime ranges draw their one value", attempts=50)
def _dates_single(offset: int, rng: random.Random) -> bool:
    first = _EPOCH + datetime.timedelta(days=offset)
    day = g.dates(first.date(), first.date()).sample(rng)
    moment = g.datetimes(first, first).sample(rng)
    # With the default resolution of one second, a one second range holds
    # two values; both appear in 64 draws but for a 2^-63 chance.
    step = g.datetimes(first, first + datetime.timedelta(seconds=1))
    seconds = set()
    for _ in range(64):
        dissection = step.sample(rng)
        if dissection is None:
            return False
        seconds.add(dissection.head)
    return (
        day is not None
        and day.head == first.date()
        and moment is not None
        and moment.head == first
        and seconds == {first, first + datetime.timedelta(seconds=1)}
    )


@prop("dates and datetimes reject invalid arguments")
def _dates_reject(seed: int) -> bool:
    day = datetime.timedelta(days=1)
    return (
        _rejects(
            lambda: g.dates(_EPOCH.date() + day, _EPOCH.date()), ValueError
        )
        and _rejects(lambda: g.dates(_EPOCH, _EPOCH), TypeError)
        and _rejects(lambda: g.dates(_EPOCH.date(), _EPOCH), TypeError)
        and _rejects(lambda: g.dates(_EPOCH, _EPOCH.date()), TypeError)
        and _rejects(lambda: g.datetimes(_EPOCH + day, _EPOCH), ValueError)
        and _rejects(
            lambda: g.datetimes(_EPOCH, _EPOCH, datetime.timedelta(0)),
            ValueError,
        )
    )


###############################################################################
# Strings, variance
###############################################################################


@prop("string generators reject an empty alphabet")
def _empty_alphabet(seed: int) -> bool:
    return _rejects(lambda: g.strings(""), ValueError) and _rejects(
        lambda: g.bounded_strings(0, 3, ""), ValueError
    )


@prop("generators and dissections are immutable")
def _immutable(rng: random.Random) -> bool:
    # Immutability is what makes both covariant in their value type.
    generator = g.ints()
    dissection = s.singleton(0)
    return _rejects(
        lambda: setattr(generator, "cardinality", c.ONE),
        dataclasses.FrozenInstanceError,
    ) and _rejects(
        lambda: setattr(dissection, "head", 1),
        dataclasses.FrozenInstanceError,
    )


###############################################################################
# Integers
###############################################################################


@context(g.one_of([name for name in TIERED if TIERED[name][1] == 0]))
@prop("unsigned tiered integers draw zero itself", attempts=20)
def _tiered_zero(name: str, rng: random.Random) -> bool:
    # Zero is drawn with probability at least one in fifty, so it appears
    # in 1000 draws but for a 1e-9 chance.
    generator = TIERED[name][0]()
    return any(
        (d := generator.sample(rng)) is not None and d.head == 0
        for _ in range(1000)
    )


@prop("floats draws both signed zeros", attempts=20)
def _float_zeros(rng: random.Random) -> bool:
    # Each zero is drawn one time in forty; both appear in 1000 draws but
    # for a 1e-10 chance.
    signs = set()
    for _ in range(1000):
        dissection = g.floats().sample(rng)
        if dissection is not None and dissection.head == 0.0:
            signs.add(math.copysign(1.0, dissection.head))
    return signs == {-1.0, 1.0}


@context(g.one_of(list(TIERED)))
@prop("tiered integers and floats shrink toward zero")
def _tiered(name: str, rng: random.Random) -> bool:
    dissection = TIERED[name][0]().sample(rng)
    real = g.floats().sample(rng)
    return (
        dissection is not None
        and greedy_leaf(dissection) == 0
        and real is not None
        and greedy_leaf(real) == 0.0
    )


@context(
    g.choice(g.constant(0), g.small_ints()),
    g.choice(g.constant(0), g.small_ints()),
)
@prop("non-zero ranges never draw zero and shrink toward one on their side")
def _nonzero_shrinks(a: int, b: int, rng: random.Random) -> bool:
    # A bound at zero is drawn often: it is where zero is easiest to let in.
    lower, upper = min(a, b), max(a, b)
    assume((lower, upper) != (0, 0))
    dissection = g.nonzero_int_range(lower, upper).sample(rng)
    if dissection is None:
        return False
    value = dissection.head
    target = max(1, lower) if value > 0 else min(-1, upper)
    return greedy_leaf(dissection) == target and all(
        node.head != 0
        and lower <= node.head <= upper
        and (node.head > 0) == (value > 0)
        for node in breadth_first(dissection, 30)
    )


@context(g.bounded_lists(0, 30, g.small_ints()), g.small_ints(), g.small_ints())
@prop("collections of non-zero values are never discarded")
def _nonzero_collections(
    lengths: list[int], a: int, b: int, rng: random.Random
) -> bool:
    lower, upper = min(a, b), max(a, b)
    assume((lower, upper) != (0, 0))
    generator = g.bounded_lists(0, 30, g.nonzero_int_range(lower, upper))
    return all(generator.sample(rng) is not None for _ in lengths)


###############################################################################
# Invalid arguments
###############################################################################


@context(g.choice(g.float_range(-1.0, 2.0), g.float_range(0.0, 1.0)))
@prop("biased_bool rejects exactly the biases outside the unit interval")
def _biased_bool_rejects(bias: float) -> bool:
    # float_range draws its bounds and zero often, so the edges of the
    # unit interval are exercised on both sides.
    invalid = not 0.0 <= bias <= 1.0
    return _rejects(lambda: g.biased_bool(bias), ValueError) == invalid


@context(g.bounded_lists(1, 4, g.int_range(-3, 3)))
@prop("weighted_choice rejects exactly negative or all-zero weights")
def _weighted_rejects(weights: list[int]) -> bool:
    def _rejected(ws: list[int]) -> bool:
        return _rejects(
            lambda: g.weighted_choice(*[(w, g.ints()) for w in ws]),
            ValueError,
        )

    # A zero weight beside positive ones is valid; it is forced on every
    # attempt, since the draw holds it only one time in thirteen.
    invalid = min(weights) < 0 or sum(weights) == 0
    return _rejected(weights) == invalid and not _rejected(
        [0, *[abs(w) + 1 for w in weights]]
    )


@prop("choice, weighted_choice and one_of reject nothing to choose from")
def _empty_choices(seed: int) -> bool:
    return (
        _rejects(lambda: g.choice(), ValueError)
        and _rejects(lambda: g.weighted_choice(), ValueError)
        and _rejects(lambda: g.one_of([]), ValueError)
    )


@context(
    g.choice(g.constant(0), g.int_range(-5, 5)),
    g.choice(g.constant(0), g.int_range(-5, 5)),
)
@prop("nonzero_int_range rejects exactly inverted and zero-only ranges")
def _nonzero_rejects(lower: int, upper: int) -> bool:
    invalid = lower > upper or lower == upper == 0
    return (
        _rejects(lambda: g.nonzero_int_range(lower, upper), ValueError)
        == invalid
    )


_BOUNDED: list[Callable[[int, int], Any]] = [
    lambda lower, upper: g.bounded_lists(lower, upper, g.ints()),
    lambda lower, upper: g.bounded_sets(lower, upper, g.ints()),
    lambda lower, upper: g.bounded_dicts(lower, upper, g.ints(), g.ints()),
    lambda lower, upper: g.bounded_strings(lower, upper),
]


@context(g.one_of(_BOUNDED), g.int_range(-5, 20), g.int_range(-5, 20))
@prop("bounded collections reject exactly negative or inverted bounds")
def _bounded_rejects(
    make: Callable[[int, int], Any], lower: int, upper: int
) -> bool:
    invalid = lower < 0 or lower > upper
    return _rejects(lambda: make(lower, upper), ValueError) == invalid


###############################################################################
# Other generators
###############################################################################


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


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _all[T](check: Callable[[Any], bool]) -> Callable[[list[Any]], bool]:
    return lambda values: all(check(value) for value in values)


def _optional_ints(values: list[Any]) -> bool:
    # None is drawn one time in twenty, so an int appears among 50 draws
    # but for a 1e-65 chance.
    return all(v is None or _int(v) for v in values) and any(map(_int, values))


#: Annotations with a check over 50 drawn values, or None when the
#: annotation is unsupported and must not be inferred.
_INFERENCE: list[tuple[Any, Callable[[list[Any]], bool] | None]] = [
    (int, _all(_int)),
    (bool, _all(lambda v: isinstance(v, bool))),
    (float, _all(lambda v: isinstance(v, float))),
    (str, _all(lambda v: isinstance(v, str))),
    (None, _all(lambda v: v is None)),
    (type(None), _all(lambda v: v is None)),
    (random.Random, _all(lambda v: isinstance(v, random.Random))),
    (int | None, _optional_ints),
    (typing.Optional[int], _optional_ints),  # noqa: UP045
    (list[int], _all(lambda v: isinstance(v, list) and all(map(_int, v)))),
    (
        set[bool],
        _all(
            lambda v: isinstance(v, set) and all(isinstance(x, bool) for x in v)
        ),
    ),
    (
        dict[str, int],
        _all(
            lambda v: (
                isinstance(v, dict)
                and all(isinstance(k, str) and _int(x) for k, x in v.items())
            )
        ),
    ),
    (
        tuple[int, str],
        _all(
            lambda v: (
                isinstance(v, tuple)
                and len(v) == 2
                and _int(v[0])
                and isinstance(v[1], str)
            )
        ),
    ),
    (tuple[int, ...], None),
    (list, None),
    (int | str, None),
    (int | str | None, None),
    (frozenset[int], None),
    (collections.abc.Mapping[str, int], None),
]


@prop("inferred generators produce instances of their annotation")
def _infer(rng: random.Random) -> bool:
    # Every annotation is checked on every attempt, since a property
    # drawing one of eighteen would see some too rarely under a budget.
    def _inferred(
        annotation: Any, accepts: Callable[[list[Any]], bool] | None
    ) -> bool:
        generator = g.infer(annotation)
        if accepts is None or generator is None:
            return accepts is None and generator is None
        values = []
        for _ in range(50):
            dissection = generator.sample(rng)
            if dissection is None:
                return False
            values.append(dissection.head)
        return accepts(values)

    return all(_inferred(*case) for case in _INFERENCE)


spec = conj(
    _heads_in_domain,
    _tree_in_domain,
    _deterministic,
    _cardinality_bounds,
    _terminates,
    _monotone,
    _arithmetic,
    _sized_cardinality,
    _collection_cardinality,
    _exact_cardinality,
    _int_range_rejects,
    _float_range_target,
    _float_range_edges,
    _float_range_tiny,
    _float_range_plain,
    _float_range_rejects,
    _dates,
    _datetimes,
    _dates_single,
    _dates_reject,
    _empty_alphabet,
    _immutable,
    _tiered,
    _tiered_zero,
    _float_zeros,
    _nonzero_shrinks,
    _nonzero_collections,
    _nonzero_rejects,
    _biased_bool_rejects,
    _weighted_rejects,
    _empty_choices,
    _bounded_rejects,
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
