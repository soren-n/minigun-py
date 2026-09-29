"""
Generators

A ``Generator[T]`` pairs a sampler with the cardinality of its domain. A
sampler draws from a random source and returns a dissection of the drawn
value, or None when the draw was discarded (a filtered generator rejected
it). Generators for the built-in types are provided, together with
combinators for composing generators of user types.

Example::

        import minigun.arbitrary as a
        import minigun.generate as g

        person = g.map(
            lambda name, age: {"name": name, "age": age},
            g.strings(),
            g.small_nats(),
        )
        dissection = person.sample(a.seed(42))
"""

from __future__ import annotations

import datetime
import math
import random
import string
import types
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, cast, get_args, get_origin

from minigun import arbitrary as a
from minigun import cardinality as c
from minigun import shrink as s

__all__ = [
    "Sampler",
    "Generator",
    "map",
    "bind",
    "lazy",
    "filter",
    "with_cardinality",
    "constant",
    "none",
    "rngs",
    "bools",
    "biased_bool",
    "small_nats",
    "nats",
    "big_nats",
    "small_ints",
    "ints",
    "big_ints",
    "int_range",
    "nonzero_int_range",
    "floats",
    "float_range",
    "dates",
    "datetimes",
    "bounded_strings",
    "strings",
    "words",
    "tuples",
    "bounded_lists",
    "lists",
    "map_list",
    "list_append",
    "bounded_dicts",
    "dicts",
    "map_dict",
    "dict_insert",
    "bounded_sets",
    "sets",
    "map_set",
    "set_add",
    "optional",
    "argument_pack",
    "choice",
    "weighted_choice",
    "one_of",
    "subset_of",
    "infer",
]


###############################################################################
# Generator
###############################################################################

#: A sampler over a type ``T``: draws a dissection, or None on a discard.
type Sampler[T] = Callable[[a.Rng], s.Dissection[T] | None]


@dataclass(frozen=True, slots=True)
class Generator[T]:
    """A generator over a type ``T``.

    :param sample: The sampler drawing dissected values of type ``T``.
    :param cardinality: The cardinality of the generator's domain; an upper
        bound when the exact size is unknown.
    """

    sample: Sampler[T]
    cardinality: c.Cardinality


def _product(generators: tuple[Generator[Any], ...]) -> c.Cardinality:
    total = c.ONE
    for generator in generators:
        total = total * generator.cardinality
    return total


def _sum(generators: tuple[Generator[Any], ...]) -> c.Cardinality:
    total = c.ZERO
    for generator in generators:
        total = total + generator.cardinality
    return total


def _sample_all(
    rng: a.Rng, generators: tuple[Generator[Any], ...]
) -> list[s.Dissection[Any]] | None:
    """Draw one dissection from each generator, or None on any discard."""
    dissections: list[s.Dissection[Any]] = []
    for generator in generators:
        dissection = generator.sample(rng)
        if dissection is None:
            return None
        dissections.append(dissection)
    return dissections


def _sample_many[T](
    rng: a.Rng, generator: Generator[T], count: int
) -> list[s.Dissection[T]] | None:
    """Draw ``count`` dissections from a generator, or None on any discard."""
    dissections: list[s.Dissection[T]] = []
    for _ in range(count):
        dissection = generator.sample(rng)
        if dissection is None:
            return None
        dissections.append(dissection)
    return dissections


###############################################################################
# Combinators
###############################################################################
def map[*Ts, R](
    func: Callable[[*Ts], R], *generators: Generator[Any]
) -> Generator[R]:
    """Combine generators with a function.

    :param func: Maps one value from each generator to a result.
    :param generators: The input generators.
    """

    def _impl(rng: a.Rng) -> s.Dissection[R] | None:
        dissections = _sample_all(rng, generators)
        if dissections is None:
            return None
        return s.map(func, *dissections)

    return Generator(_impl, _product(generators))


def bind[*Ts, R](
    func: Callable[[*Ts], Generator[R]], *generators: Generator[Any]
) -> Generator[R]:
    """Choose a generator from drawn values, then draw from it.

    The resulting domain depends on the chosen generators and is not known
    up front, so the cardinality is reported as unbounded.

    :param func: Maps one value from each generator to a generator.
    :param generators: The input generators.
    """

    def _impl(rng: a.Rng) -> s.Dissection[R] | None:
        dissections = _sample_all(rng, generators)
        if dissections is None:
            return None
        values = cast(
            "tuple[*Ts]", tuple(dissection.head for dissection in dissections)
        )
        return func(*values).sample(rng)

    return Generator(_impl, c.INFINITE)


def lazy[T](thunk: Callable[[], Generator[T]]) -> Generator[T]:
    """Defer construction of a generator until the first draw.

    Needed for recursive generator definitions, where eager construction
    would recurse without end. The inner generator is built once and then
    reused. The cardinality is reported as unbounded since the inner
    generator is unknown at construction time.
    """
    cache: list[Generator[T]] = []

    def _impl(rng: a.Rng) -> s.Dissection[T] | None:
        if not cache:
            cache.append(thunk())
        return cache[0].sample(rng)

    return Generator(_impl, c.INFINITE)


def filter[T](
    predicate: Callable[[T], bool], generator: Generator[T]
) -> Generator[T]:
    """Restrict a generator to values satisfying a predicate.

    Draws failing the predicate are discarded; shrunk alternatives failing
    it are pruned. The cardinality is the inner generator's, an upper bound.

    A discard propagates: a collection, tuple or mapped value with a
    discarded part is discarded whole, so a predicate that rejects one
    element in fifty discards a list of twenty elements a third of the
    time. Prefer a generator of exactly the wanted values, such as
    ``nonzero_int_range`` or a ``map`` onto the domain, for elements.
    """

    def _impl(rng: a.Rng) -> s.Dissection[T] | None:
        dissection = generator.sample(rng)
        if dissection is None:
            return None
        return s.filter(predicate, dissection)

    return Generator(_impl, generator.cardinality)


def with_cardinality[T](
    generator: Generator[T], cardinality: c.Cardinality
) -> Generator[T]:
    """The same generator with a known cardinality.

    For use when a generator built with ``bind`` or ``lazy`` has a domain
    the author can size exactly.
    """
    return Generator(generator.sample, cardinality)


###############################################################################
# Constants
###############################################################################
def constant[T](value: T) -> Generator[T]:
    """A generator of one value."""

    def _impl(rng: a.Rng) -> s.Dissection[T] | None:
        return s.singleton(value)

    return Generator(_impl, c.ONE)


def none() -> Generator[None]:
    """A generator of None."""
    return constant(None)


###############################################################################
# Random sources
###############################################################################
def rngs() -> Generator[random.Random]:
    """A generator of independent random sources.

    Each draw forks a child of the sampling source, so a law that needs
    randomness of its own gets a source that is reproducible from the run
    seed. Sources do not shrink.
    """

    def _impl(rng: a.Rng) -> s.Dissection[random.Random] | None:
        return s.singleton(a.fork(rng))

    return Generator(_impl, c.INFINITE)


###############################################################################
# Booleans
###############################################################################
def bools() -> Generator[bool]:
    """A generator of booleans."""
    shrink = s.boolean()

    def _impl(rng: a.Rng) -> s.Dissection[bool] | None:
        return shrink(a.draw_bool(rng))

    return Generator(_impl, c.finite(2))


def biased_bool(bias: float) -> Generator[bool]:
    """A generator of booleans that are True with probability ``bias``.

    :raises ValueError: When ``bias`` is outside ``[0.0, 1.0]``.
    """
    if not 0.0 <= bias <= 1.0:
        raise ValueError(f"biased_bool requires 0.0 <= bias <= 1.0, got {bias}")
    shrink = s.boolean()

    def _impl(rng: a.Rng) -> s.Dissection[bool] | None:
        return shrink(a.probability(rng) < bias)

    return Generator(_impl, c.finite(2))


###############################################################################
# Integers
###############################################################################

#: Cumulative probability tiers: (chance threshold, magnitude bound).
type _Tiers = tuple[tuple[float, int], ...]

_SMALL_TIERS: _Tiers = ((0.75, 10), (1.0, 100))
_MEDIUM_TIERS: _Tiers = ((0.5, 10), (0.75, 100), (0.95, 1000), (1.0, 10000))
_BIG_TIERS: _Tiers = (
    (0.25, 10),
    (0.5, 100),
    (0.75, 1000),
    (0.95, 10000),
    (1.0, 1000000),
)


def _draw_tiered(rng: a.Rng, tiers: _Tiers, signed: bool) -> int:
    """Draw an integer with a magnitude from probability tiers."""
    roll = a.probability(rng)
    magnitude = tiers[-1][1]
    for threshold, tier_bound in tiers:
        if roll < threshold:
            magnitude = tier_bound
            break
    lower = -magnitude if signed else 0
    return a.draw_int(rng, lower, magnitude)


def _tiered_int(tiers: _Tiers, signed: bool) -> Generator[int]:
    """Integers with magnitudes drawn from probability tiers, biased small."""
    shrink = s.integer(0)
    bound = tiers[-1][1]
    size = 2 * bound + 1 if signed else bound + 1

    def _impl(rng: a.Rng) -> s.Dissection[int] | None:
        return shrink(_draw_tiered(rng, tiers, signed))

    return Generator(_impl, c.finite(size))


def small_nats() -> Generator[int]:
    """A generator of integers ``n`` with ``0 <= n <= 100``."""
    return _tiered_int(_SMALL_TIERS, signed=False)


def nats() -> Generator[int]:
    """A generator of integers ``n`` with ``0 <= n <= 10000``."""
    return _tiered_int(_MEDIUM_TIERS, signed=False)


def big_nats() -> Generator[int]:
    """A generator of integers ``n`` with ``0 <= n <= 1000000``."""
    return _tiered_int(_BIG_TIERS, signed=False)


def small_ints() -> Generator[int]:
    """A generator of integers ``n`` with ``-100 <= n <= 100``."""
    return _tiered_int(_SMALL_TIERS, signed=True)


def ints() -> Generator[int]:
    """A generator of integers ``n`` with ``-10000 <= n <= 10000``."""
    return _tiered_int(_MEDIUM_TIERS, signed=True)


def big_ints() -> Generator[int]:
    """A generator of integers ``n`` with ``-1000000 <= n <= 1000000``."""
    return _tiered_int(_BIG_TIERS, signed=True)


def int_range(lower_bound: int, upper_bound: int) -> Generator[int]:
    """A generator of integers ``n`` with ``lower_bound <= n <= upper_bound``.

    Values shrink toward zero, or toward the bound nearest zero when zero
    is outside the range.

    :raises ValueError: When ``lower_bound > upper_bound``.
    """
    if lower_bound > upper_bound:
        raise ValueError(
            f"int_range requires lower_bound <= upper_bound, got "
            f"{lower_bound} > {upper_bound}"
        )
    shrink = s.integer(max(lower_bound, min(0, upper_bound)))

    def _impl(rng: a.Rng) -> s.Dissection[int] | None:
        return shrink(a.draw_int(rng, lower_bound, upper_bound))

    return Generator(_impl, c.finite(upper_bound - lower_bound + 1))


def nonzero_int_range(lower_bound: int, upper_bound: int) -> Generator[int]:
    """A generator of integers ``n`` with ``lower_bound <= n <= upper_bound``
    and ``n != 0``, each equally likely.

    For divisors, step counts and other parameters where zero is outside
    the domain. Unlike filtering zero out of ``int_range``, nothing is
    discarded, so a collection of such values is never discarded either.
    A value shrinks toward the non-zero value nearest zero on its own side
    of zero, and so never shrinks to zero or across it.

    :raises ValueError: When ``lower_bound > upper_bound`` or the range
        holds no value other than zero.
    """
    if lower_bound > upper_bound:
        raise ValueError(
            f"nonzero_int_range requires lower_bound <= upper_bound, got "
            f"{lower_bound} > {upper_bound}"
        )
    if lower_bound == upper_bound == 0:
        raise ValueError("nonzero_int_range requires a non-zero value in range")
    holds_zero = lower_bound <= 0 <= upper_bound
    shrink_positive = s.integer(max(1, lower_bound))
    shrink_negative = s.integer(min(-1, upper_bound))

    def _impl(rng: a.Rng) -> s.Dissection[int] | None:
        # Drawn from a range one shorter, skipping over zero, so every
        # non-zero value is equally likely.
        value = a.draw_int(rng, lower_bound, upper_bound - holds_zero)
        if holds_zero and value >= 0:
            value += 1
        return shrink_positive(value) if value > 0 else shrink_negative(value)

    return Generator(
        _impl, c.finite(upper_bound - lower_bound + 1 - holds_zero)
    )


###############################################################################
# Floats
###############################################################################
def floats() -> Generator[float]:
    """A generator of finite floats.

    Draws mix zero and negative zero, small integral values, and values
    spread log-uniformly in magnitude between ``e^-15`` and ``e^15`` of
    either sign. Infinities and NaN are never drawn.
    """
    shrink = s.floating(0.0)

    def _impl(rng: a.Rng) -> s.Dissection[float] | None:
        roll = a.probability(rng)
        if roll < 0.05:
            return shrink(0.0 if a.draw_bool(rng) else -0.0)
        if roll < 0.20:
            return shrink(float(a.draw_int(rng, -100, 100)))
        magnitude = math.exp(a.draw_float(rng, -15.0, 15.0))
        return shrink(magnitude if a.draw_bool(rng) else -magnitude)

    return Generator(_impl, c.INFINITE)


#: Chance of drawing each bound of a float range.
_BOUND_CHANCE = 0.05

#: Chance of drawing zero or a tiny magnitude from a range holding zero.
_TINY_CHANCE = 0.10

#: Binary exponents between which tiny magnitudes are spread, from the
#: smallest subnormal float up.
_TINY_EXPONENTS = (-1074.0, -20.0)


def _draw_tiny(rng: a.Rng, lower_bound: float, upper_bound: float) -> float:
    """Draw zero, the smallest subnormal, or a tiny magnitude spread
    log-uniformly above it, with a sign the range allows.

    The range holds zero and is more than one point, so it extends to at
    least one side of zero.
    """
    signs = [
        sign
        for sign, side in ((-1.0, lower_bound), (1.0, upper_bound))
        if sign * side > 0
    ]
    sign = a.choice(rng, signs)
    kind = a.draw_int(rng, 0, 2)
    if kind == 0:
        return sign * 0.0
    if kind == 1:
        magnitude = math.ulp(0.0)
    else:
        magnitude = 2.0 ** a.draw_float(rng, *_TINY_EXPONENTS)
    limit = upper_bound if sign > 0 else -lower_bound
    return sign * min(magnitude, limit)


def float_range(
    lower_bound: float, upper_bound: float, edges: bool = True
) -> Generator[float]:
    """A generator of floats ``x`` with ``lower_bound <= x <= upper_bound``.

    Numerical code tends to fail at the limits of its parameters and near
    zero, where products underflow and special functions lose precision.
    With ``edges`` a draw is therefore each bound with probability 5%, and,
    when the range holds zero, zero or a tiny magnitude with probability
    10%: zero, the smallest subnormal float (``5e-324``), or a magnitude
    spread log-uniformly between it and ``2^-20``. Every other draw is
    uniform over the range. Without ``edges`` every draw is uniform.

    Values shrink toward zero, or toward the bound nearest zero when zero
    is outside the range, and never leave the range.

    :raises ValueError: When a bound is NaN or infinite, or when
        ``lower_bound > upper_bound``.
    """
    if not (math.isfinite(lower_bound) and math.isfinite(upper_bound)):
        raise ValueError(
            f"float_range requires finite bounds, got {lower_bound} and "
            f"{upper_bound}"
        )
    if lower_bound > upper_bound:
        raise ValueError(
            f"float_range requires lower_bound <= upper_bound, got "
            f"{lower_bound} > {upper_bound}"
        )
    if lower_bound == upper_bound:
        # Drawn as is, so a range of one signed zero keeps its sign.
        return constant(lower_bound)
    shrink = s.floating(max(lower_bound, min(0.0, upper_bound)))
    holds_zero = lower_bound <= 0.0 <= upper_bound

    def _impl(rng: a.Rng) -> s.Dissection[float] | None:
        if edges:
            roll = a.probability(rng)
            if roll < _BOUND_CHANCE:
                return shrink(lower_bound)
            if roll < 2 * _BOUND_CHANCE:
                return shrink(upper_bound)
            if holds_zero and roll < 2 * _BOUND_CHANCE + _TINY_CHANCE:
                return shrink(_draw_tiny(rng, lower_bound, upper_bound))
        return shrink(a.draw_float(rng, lower_bound, upper_bound))

    return Generator(_impl, c.INFINITE)


###############################################################################
# Dates and times
###############################################################################
def dates(
    first: datetime.date, last: datetime.date
) -> Generator[datetime.date]:
    """A generator of dates ``d`` with ``first <= d <= last``, each equally
    likely, shrinking toward ``first``.

    :raises TypeError: When a bound is a ``datetime``; use ``datetimes``.
    :raises ValueError: When ``first > last``.
    """
    if isinstance(first, datetime.datetime) or isinstance(
        last, datetime.datetime
    ):
        raise TypeError("dates requires date bounds; use datetimes")
    if first > last:
        raise ValueError(f"dates requires first <= last, got {first} > {last}")

    def _date(days: int) -> datetime.date:
        return first + datetime.timedelta(days=days)

    return map(_date, int_range(0, (last - first).days))


def datetimes(
    first: datetime.datetime,
    last: datetime.datetime,
    resolution: datetime.timedelta = datetime.timedelta(seconds=1),
) -> Generator[datetime.datetime]:
    """A generator of datetimes ``first + k * resolution`` with
    ``first <= d <= last``, each equally likely, shrinking toward
    ``first``.

    Both bounds must be naive, or both aware; aware bounds are stepped in
    their own time zones as ``datetime`` arithmetic does.

    :raises TypeError: When one bound is naive and the other aware.
    :raises ValueError: When ``first > last`` or ``resolution`` is not
        positive.
    """
    if resolution <= datetime.timedelta(0):
        raise ValueError(
            f"datetimes requires a positive resolution, got {resolution}"
        )
    if first > last:
        raise ValueError(
            f"datetimes requires first <= last, got {first} > {last}"
        )

    def _datetime(steps: int) -> datetime.datetime:
        return first + steps * resolution

    return map(_datetime, int_range(0, (last - first) // resolution))


###############################################################################
# Sequences
###############################################################################
def _sequence_dissection[R](
    dissections: list[s.Dissection[Any]],
    rebuild: Callable[[list[Any]], R],
    min_length: int | None = None,
) -> s.Dissection[R]:
    """A dissection of a composite built from element dissections.

    Shrinks by removing chunks of elements, largest first, while the
    length stays at or above ``min_length`` (None disables removal), then
    by shrinking elements one at a time.
    """

    def _node(elements: list[s.Dissection[Any]]) -> s.Dissection[R]:
        def _iterate() -> Iterator[s.Dissection[R]]:
            if min_length is not None and len(elements) > min_length:
                removable = len(elements) - min_length
                for start, end in s.chunk_removals(len(elements), removable):
                    yield _node(elements[:start] + elements[end:])
            for index, element in enumerate(elements):
                for child in element.shrinks():
                    replaced = list(elements)
                    replaced[index] = child
                    yield _node(replaced)

        heads = [element.head for element in elements]
        return s.Dissection(rebuild(heads), _iterate)

    return _node(dissections)


#: Bits beyond which a term of a sized cardinality cannot be a float.
_FLOAT_BITS_MARGIN = 1100


def _sized_cardinality(
    lower_bound: int, upper_bound: int, item_cardinality: c.Cardinality
) -> c.Cardinality:
    """Cardinality of a sized collection: the sum of ``|item|^size`` over
    ``lower_bound <= size <= upper_bound``.

    Computed as a geometric series in exact integers, so small results
    are exact (they are truncated to ``int`` by their users) and the cost
    does not grow with the size range. The result is unbounded exactly
    when summing the terms in floats would overflow, and the integers
    involved never exceed the float range by more than a small margin.
    """
    if not item_cardinality.is_finite:
        return c.ONE if upper_bound == 0 else c.INFINITE
    ratio = int(item_cardinality.size)
    if ratio == 0:
        return c.ONE if lower_bound == 0 else c.ZERO
    if ratio == 1:
        return c.finite(upper_bound - lower_bound + 1)
    if upper_bound * math.log2(ratio) > _FLOAT_BITS_MARGIN:
        return c.INFINITE
    total = (ratio ** (upper_bound + 1) - ratio**lower_bound) // (ratio - 1)
    try:
        return c.finite(total)
    except OverflowError:
        return c.INFINITE


def _check_bounds(name: str, lower_bound: int, upper_bound: int) -> None:
    if lower_bound < 0:
        raise ValueError(f"{name} requires lower_bound >= 0, got {lower_bound}")
    if lower_bound > upper_bound:
        raise ValueError(
            f"{name} requires lower_bound <= upper_bound, got "
            f"{lower_bound} > {upper_bound}"
        )


#: Upper length bound of the unsized collection generators.
_COLLECTION_BOUND = 100

#: Draws a collection of at most a given length from a random source.
type _SizedDraw[T] = Callable[[a.Rng, int], s.Dissection[T] | None]


def _unsized[T](
    draw: _SizedDraw[T], item_cardinality: c.Cardinality
) -> Generator[T]:
    """A collection generator whose upper length bound is drawn like a
    small natural, with the exact cardinality of the full size range.

    The bounded draw is a plain function rather than a generator
    constructor, so a draw builds no generator: constructing one validates
    its bounds and sizes its domain, which is work per generator, not per
    value.
    """

    def _impl(rng: a.Rng) -> s.Dissection[T] | None:
        return draw(rng, _draw_tiered(rng, _SMALL_TIERS, signed=False))

    return Generator(
        _impl, _sized_cardinality(0, _COLLECTION_BOUND, item_cardinality)
    )


###############################################################################
# Strings
###############################################################################
_shrink_string = s.string()


def _draw_string(
    rng: a.Rng, lower_bound: int, upper_bound: int, alphabet: str
) -> s.Dissection[str]:
    length = a.draw_int(rng, lower_bound, upper_bound)
    return _shrink_string(
        "".join(a.choice(rng, alphabet) for _ in range(length))
    )


def _check_alphabet(name: str, alphabet: str) -> None:
    if len(alphabet) == 0:
        raise ValueError(f"{name} requires a non-empty alphabet")


def bounded_strings(
    lower_bound: int, upper_bound: int, alphabet: str = string.printable
) -> Generator[str]:
    """A generator of strings over ``alphabet`` with length ``l`` where
    ``lower_bound <= l <= upper_bound``.

    Ticker symbols, for example, are
    ``bounded_strings(1, 5, string.ascii_uppercase)``.

    :param alphabet: The characters to draw from, each equally likely;
        the printable ASCII characters by default.

    :raises ValueError: When the bounds are invalid or the alphabet is empty.
    """
    _check_bounds("bounded_strings", lower_bound, upper_bound)
    _check_alphabet("bounded_strings", alphabet)

    def _impl(rng: a.Rng) -> s.Dissection[str] | None:
        return _draw_string(rng, lower_bound, upper_bound, alphabet)

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, c.finite(len(alphabet))),
    )


def strings(alphabet: str = string.printable) -> Generator[str]:
    """A generator of strings of up to 100 characters, biased short.

    :param alphabet: The characters to draw from, each equally likely;
        the printable ASCII characters by default.

    :raises ValueError: When the alphabet is empty.
    """
    _check_alphabet("strings", alphabet)
    return _unsized(
        lambda rng, bound: _draw_string(rng, 0, bound, alphabet),
        c.finite(len(alphabet)),
    )


def words() -> Generator[str]:
    """A generator of strings over the ASCII letters."""
    return strings(string.ascii_letters)


###############################################################################
# Tuples
###############################################################################
def tuples(*generators: Generator[Any]) -> Generator[tuple[Any, ...]]:
    """A generator of tuples with one element from each generator."""

    def _impl(rng: a.Rng) -> s.Dissection[tuple[Any, ...]] | None:
        dissections = _sample_all(rng, generators)
        if dissections is None:
            return None
        return _sequence_dissection(dissections, tuple)

    return Generator(_impl, _product(generators))


###############################################################################
# Lists
###############################################################################
def _sorted[T](heads: list[T]) -> list[T]:
    return sorted(heads)  # type: ignore[type-var]


def _as_is[T](heads: list[T]) -> list[T]:
    return heads


def _draw_list[T](
    rng: a.Rng,
    lower_bound: int,
    upper_bound: int,
    generator: Generator[T],
    ordered: bool,
) -> s.Dissection[list[T]] | None:
    length = a.draw_int(rng, lower_bound, upper_bound)
    dissections = _sample_many(rng, generator, length)
    if dissections is None:
        return None
    return _sequence_dissection(
        dissections, _sorted if ordered else _as_is, lower_bound
    )


def bounded_lists[T](
    lower_bound: int,
    upper_bound: int,
    generator: Generator[T],
    ordered: bool = False,
) -> Generator[list[T]]:
    """A generator of lists with length ``l`` where
    ``lower_bound <= l <= upper_bound``.

    :param ordered: Whether drawn lists are sorted.

    :raises ValueError: When the bounds are invalid.
    """
    _check_bounds("bounded_lists", lower_bound, upper_bound)

    def _impl(rng: a.Rng) -> s.Dissection[list[T]] | None:
        return _draw_list(rng, lower_bound, upper_bound, generator, ordered)

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, generator.cardinality),
    )


def lists[T](
    generator: Generator[T], ordered: bool = False
) -> Generator[list[T]]:
    """A generator of lists of up to 100 elements, biased short.

    :param ordered: Whether drawn lists are sorted.
    """
    return _unsized(
        lambda rng, bound: _draw_list(rng, 0, bound, generator, ordered),
        generator.cardinality,
    )


def map_list[T](
    generators: list[Generator[T]], ordered: bool = False
) -> Generator[list[T]]:
    """A generator of lists with one element from each generator in order.

    :param ordered: Whether drawn lists are sorted.
    """

    def _compose(*values: T) -> list[T]:
        result = list(values)
        return sorted(result) if ordered else result  # type: ignore[type-var]

    return map(_compose, *generators)


def list_append[T](
    items: Generator[list[T]], item: Generator[T]
) -> Generator[list[T]]:
    """A generator of lists from ``items`` with a value from ``item``
    appended."""

    def _append(values: list[T], value: T) -> list[T]:
        return [*values, value]

    return map(_append, items, item)


###############################################################################
# Dictionaries
###############################################################################
def _pair[K, V](key: K, value: V) -> tuple[K, V]:
    return key, value


def _draw_dict[K, V](
    rng: a.Rng,
    lower_bound: int,
    upper_bound: int,
    keys: Generator[K],
    values: Generator[V],
) -> s.Dissection[dict[K, V]] | None:
    size = a.draw_int(rng, lower_bound, upper_bound)
    pairs: list[s.Dissection[tuple[K, V]]] = []
    for _ in range(size):
        dissections = _sample_all(rng, (keys, values))
        if dissections is None:
            return None
        pairs.append(s.map(_pair, *dissections))
    return _sequence_dissection(pairs, dict, lower_bound)


def bounded_dicts[K, V](
    lower_bound: int,
    upper_bound: int,
    keys: Generator[K],
    values: Generator[V],
) -> Generator[dict[K, V]]:
    """A generator of dicts with up to ``upper_bound`` entries drawn, at
    least ``lower_bound`` of them, before duplicate keys collapse.

    :raises ValueError: When the bounds are invalid.
    """
    _check_bounds("bounded_dicts", lower_bound, upper_bound)

    def _impl(rng: a.Rng) -> s.Dissection[dict[K, V]] | None:
        return _draw_dict(rng, lower_bound, upper_bound, keys, values)

    return Generator(
        _impl,
        _sized_cardinality(
            lower_bound, upper_bound, keys.cardinality * values.cardinality
        ),
    )


def dicts[K, V](
    keys: Generator[K], values: Generator[V]
) -> Generator[dict[K, V]]:
    """A generator of dicts of up to 100 entries, biased small."""
    return _unsized(
        lambda rng, bound: _draw_dict(rng, 0, bound, keys, values),
        keys.cardinality * values.cardinality,
    )


def map_dict[K, V](generators: dict[K, Generator[V]]) -> Generator[dict[K, V]]:
    """A generator of dicts with fixed keys and one value per generator."""
    keys = list(generators)

    def _compose(*values: V) -> dict[K, V]:
        return dict(zip(keys, values, strict=True))

    return map(_compose, *[generators[key] for key in keys])


def dict_insert[K, V](
    entries: Generator[dict[K, V]], key: Generator[K], value: Generator[V]
) -> Generator[dict[K, V]]:
    """A generator of dicts from ``entries`` with an entry from ``key`` and
    ``value`` inserted."""

    def _insert(kvs: dict[K, V], k: K, v: V) -> dict[K, V]:
        return {**kvs, k: v}

    return map(_insert, entries, key, value)


###############################################################################
# Sets
###############################################################################
def _draw_set[T](
    rng: a.Rng, lower_bound: int, upper_bound: int, generator: Generator[T]
) -> s.Dissection[set[T]] | None:
    size = a.draw_int(rng, lower_bound, upper_bound)
    dissections = _sample_many(rng, generator, size)
    if dissections is None:
        return None
    return _sequence_dissection(dissections, set, lower_bound)


def bounded_sets[T](
    lower_bound: int, upper_bound: int, generator: Generator[T]
) -> Generator[set[T]]:
    """A generator of sets with up to ``upper_bound`` elements drawn, at
    least ``lower_bound`` of them, before duplicates collapse.

    :raises ValueError: When the bounds are invalid.
    """
    _check_bounds("bounded_sets", lower_bound, upper_bound)

    def _impl(rng: a.Rng) -> s.Dissection[set[T]] | None:
        return _draw_set(rng, lower_bound, upper_bound, generator)

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, generator.cardinality),
    )


def sets[T](generator: Generator[T]) -> Generator[set[T]]:
    """A generator of sets of up to 100 elements, biased small."""
    return _unsized(
        lambda rng, bound: _draw_set(rng, 0, bound, generator),
        generator.cardinality,
    )


def map_set[T](generators: set[Generator[T]]) -> Generator[set[T]]:
    """A generator of sets with one element from each generator."""

    def _compose(*values: T) -> set[T]:
        return set(values)

    return map(_compose, *generators)


def set_add[T](
    items: Generator[set[T]], item: Generator[T]
) -> Generator[set[T]]:
    """A generator of sets from ``items`` with a value from ``item`` added."""

    def _add(values: set[T], value: T) -> set[T]:
        return {*values, value}

    return map(_add, items, item)


###############################################################################
# Optional
###############################################################################
def optional[T](generator: Generator[T]) -> Generator[T | None]:
    """A generator of values from ``generator`` or None, with None drawn
    with a small probability and offered as the last shrink of any value."""

    def _some(value: T) -> T | None:
        return value

    def _with_none(
        dissection: s.Dissection[T | None],
    ) -> s.Dissection[T | None]:
        def _iterate() -> Iterator[s.Dissection[T | None]]:
            for child in dissection.shrinks():
                yield _with_none(child)
            yield s.singleton(None)

        return s.Dissection(dissection.head, _iterate)

    def _impl(rng: a.Rng) -> s.Dissection[T | None] | None:
        if a.probability(rng) < 0.05:
            return s.singleton(None)
        dissection = generator.sample(rng)
        if dissection is None:
            return None
        return _with_none(s.map(_some, dissection))

    return Generator(_impl, generator.cardinality + c.ONE)


###############################################################################
# Argument packs
###############################################################################
def argument_pack(
    generators: dict[str, Generator[Any]],
) -> Generator[dict[str, Any]]:
    """A generator of keyword argument dicts, one value per named
    generator, shrinking the arguments one at a time."""
    names = list(generators)

    def _rebuild(heads: list[Any]) -> dict[str, Any]:
        return dict(zip(names, heads, strict=True))

    def _impl(rng: a.Rng) -> s.Dissection[dict[str, Any]] | None:
        dissections = _sample_all(
            rng, tuple(generators[name] for name in names)
        )
        if dissections is None:
            return None
        return _sequence_dissection(dissections, _rebuild)

    return Generator(_impl, _product(tuple(generators.values())))


###############################################################################
# Choice
###############################################################################
def choice[T](*generators: Generator[T]) -> Generator[T]:
    """A generator drawing from one of the given generators, each equally
    likely.

    Generators are covariant, so generators of different types combine
    into a generator of a common supertype, a union or a protocol, when
    the expected type is annotated::

        def commands() -> g.Generator[Push | Pop]:
            return g.choice(g.map(Push, g.ints()), g.constant(Pop()))

    :raises ValueError: When no generators are given.
    """
    if len(generators) == 0:
        raise ValueError("choice requires at least one generator")

    def _impl(rng: a.Rng) -> s.Dissection[T] | None:
        return a.choice(rng, generators).sample(rng)

    return Generator(_impl, _sum(generators))


def weighted_choice[T](
    *weighted: tuple[int, Generator[T]],
) -> Generator[T]:
    """A generator drawing from one of the given generators with
    probability proportional to its weight.

    :raises ValueError: When no generators are given or the weights are
        invalid.
    """
    if len(weighted) == 0:
        raise ValueError("weighted_choice requires at least one generator")
    weights = [weight for weight, _ in weighted]
    generators = tuple(generator for _, generator in weighted)
    if any(weight < 0 for weight in weights):
        raise ValueError("weighted_choice weights must be non-negative")
    if sum(weights) == 0:
        raise ValueError("weighted_choice requires a positive total weight")

    def _impl(rng: a.Rng) -> s.Dissection[T] | None:
        return a.weighted_choice(rng, weights, generators).sample(rng)

    return Generator(_impl, _sum(generators))


def one_of[T](values: list[T]) -> Generator[T]:
    """A generator drawing one of the given values, shrinking toward the
    first.

    :raises ValueError: When ``values`` is empty.
    """
    if len(values) == 0:
        raise ValueError("one_of requires at least one value")
    snapshot = list(values)

    def _select(index: int) -> T:
        return snapshot[index]

    return map(_select, int_range(0, len(snapshot) - 1))


def subset_of[T](values: set[T]) -> Generator[set[T]]:
    """A generator of subsets of the given set."""
    snapshot = list(values)

    def _select(indices: set[int]) -> set[T]:
        return {snapshot[index] for index in indices}

    if len(snapshot) == 0:
        return constant(set())
    count = len(snapshot)
    return with_cardinality(
        map(_select, bounded_sets(0, count, int_range(0, count - 1))),
        c.finite(2) ** c.finite(count),
    )


###############################################################################
# Inference
###############################################################################
def _optional_inner(T: Any) -> Any | None:
    """The inner type of an ``X | None`` annotation, or None."""
    origin = get_origin(T)
    if origin is not types.UnionType and origin is not typing.Union:
        return None
    args = get_args(T)
    if type(None) not in args:
        return None
    inner = [arg for arg in args if arg is not type(None)]
    if len(inner) != 1:
        return None
    return inner[0]


def infer(T: Any) -> Generator[Any] | None:
    """Infer a generator from a type annotation.

    Supports ``bool``, ``int``, ``float``, ``str``, ``None``,
    ``random.Random``, ``X | None``, and ``tuple``, ``list``, ``dict`` and
    ``set`` of supported types.

    :return: The generator, or None when the annotation is not supported.
    """

    def _all(annotations: tuple[Any, ...]) -> list[Generator[Any]] | None:
        generators: list[Generator[Any]] = []
        for annotation in annotations:
            generator = infer(annotation)
            if generator is None:
                return None
            generators.append(generator)
        return generators

    if T is bool:
        return bools()
    if T is int:
        return ints()
    if T is float:
        return floats()
    if T is str:
        return strings()
    if T is None or T is type(None):
        return none()
    if T is random.Random:
        return rngs()

    inner = _optional_inner(T)
    if inner is not None:
        inner_generator = infer(inner)
        return None if inner_generator is None else optional(inner_generator)

    origin = get_origin(T)
    args = get_args(T)
    if origin is tuple:
        if Ellipsis in args:
            return None
        items = _all(args)
        return None if items is None else tuples(*items)
    if origin is list and len(args) == 1:
        items = _all(args)
        return None if items is None else lists(items[0])
    if origin is set and len(args) == 1:
        items = _all(args)
        return None if items is None else sets(items[0])
    if origin is dict and len(args) == 2:
        items = _all(args)
        return None if items is None else dicts(items[0], items[1])
    return None
