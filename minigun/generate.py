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
    "floats",
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


@dataclass(slots=True)
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


def _tiered_int(tiers: _Tiers, signed: bool) -> Generator[int]:
    """Integers with magnitudes drawn from probability tiers, biased small."""
    shrink = s.integer(0)
    bound = tiers[-1][1]
    size = 2 * bound + 1 if signed else bound + 1

    def _impl(rng: a.Rng) -> s.Dissection[int] | None:
        roll = a.probability(rng)
        magnitude = bound
        for threshold, tier_bound in tiers:
            if roll < threshold:
                magnitude = tier_bound
                break
        lower = -magnitude if signed else 0
        return shrink(a.draw_int(rng, lower, magnitude))

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


def _sized_cardinality(
    lower_bound: int, upper_bound: int, item_cardinality: c.Cardinality
) -> c.Cardinality:
    """Cardinality of a sized collection: the sum of ``|item|^size``."""
    total = c.ZERO
    for size in range(lower_bound, upper_bound + 1):
        total = total + (item_cardinality ** c.finite(size))
    return total


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


def _unsized[T](
    sized: Callable[[int], Generator[T]], item_cardinality: c.Cardinality
) -> Generator[T]:
    """A collection generator whose upper size bound is drawn small-biased,
    with the exact cardinality of the full size range."""
    return with_cardinality(
        bind(sized, small_nats()),
        _sized_cardinality(0, _COLLECTION_BOUND, item_cardinality),
    )


###############################################################################
# Strings
###############################################################################
def bounded_strings(
    lower_bound: int, upper_bound: int, alphabet: str
) -> Generator[str]:
    """A generator of strings over ``alphabet`` with length ``l`` where
    ``lower_bound <= l <= upper_bound``.

    :raises ValueError: When the bounds are invalid or the alphabet is empty.
    """
    _check_bounds("bounded_strings", lower_bound, upper_bound)
    if len(alphabet) == 0:
        raise ValueError("bounded_strings requires a non-empty alphabet")
    shrink = s.string()

    def _impl(rng: a.Rng) -> s.Dissection[str] | None:
        length = a.draw_int(rng, lower_bound, upper_bound)
        return shrink("".join(a.choice(rng, alphabet) for _ in range(length)))

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, c.finite(len(alphabet))),
    )


def strings() -> Generator[str]:
    """A generator of strings over the printable ASCII characters."""
    return _unsized(
        lambda bound: bounded_strings(0, bound, string.printable),
        c.finite(len(string.printable)),
    )


def words() -> Generator[str]:
    """A generator of strings over the ASCII letters."""
    return _unsized(
        lambda bound: bounded_strings(0, bound, string.ascii_letters),
        c.finite(len(string.ascii_letters)),
    )


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

    def _rebuild(heads: list[T]) -> list[T]:
        return sorted(heads) if ordered else heads  # type: ignore[type-var]

    def _impl(rng: a.Rng) -> s.Dissection[list[T]] | None:
        length = a.draw_int(rng, lower_bound, upper_bound)
        dissections = _sample_many(rng, generator, length)
        if dissections is None:
            return None
        return _sequence_dissection(dissections, _rebuild, lower_bound)

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
        lambda bound: bounded_lists(0, bound, generator, ordered),
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

    def _pair(key: K, value: V) -> tuple[K, V]:
        return key, value

    def _impl(rng: a.Rng) -> s.Dissection[dict[K, V]] | None:
        size = a.draw_int(rng, lower_bound, upper_bound)
        pairs: list[s.Dissection[tuple[K, V]]] = []
        for _ in range(size):
            dissections = _sample_all(rng, (keys, values))
            if dissections is None:
                return None
            pairs.append(s.map(_pair, *dissections))
        return _sequence_dissection(pairs, dict, lower_bound)

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
        lambda bound: bounded_dicts(0, bound, keys, values),
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
def bounded_sets[T](
    lower_bound: int, upper_bound: int, generator: Generator[T]
) -> Generator[set[T]]:
    """A generator of sets with up to ``upper_bound`` elements drawn, at
    least ``lower_bound`` of them, before duplicates collapse.

    :raises ValueError: When the bounds are invalid.
    """
    _check_bounds("bounded_sets", lower_bound, upper_bound)

    def _impl(rng: a.Rng) -> s.Dissection[set[T]] | None:
        size = a.draw_int(rng, lower_bound, upper_bound)
        dissections = _sample_many(rng, generator, size)
        if dissections is None:
            return None
        return _sequence_dissection(dissections, set, lower_bound)

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, generator.cardinality),
    )


def sets[T](generator: Generator[T]) -> Generator[set[T]]:
    """A generator of sets of up to 100 elements, biased small."""
    return _unsized(
        lambda bound: bounded_sets(0, bound, generator), generator.cardinality
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
