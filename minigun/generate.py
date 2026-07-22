"""
Data Generators and Combinators

This module provides the core data generation system for property-based testing.
It implements generators for all Python built-in types and combinators for
composing complex data structures with proper shrinking support.

Architecture:
    - Generator[T]: A sampler paired with the cardinality of its domain
    - Sample[T]: State-threaded generation with shrinking info
    - Combinators: map, bind, filter, choice for composition

Built-in Generators:
    - Primitives: bool, nat, int, float, str
    - Collections: list, dict, set, tuple
    - Utilities: constant, one_of, weighted_choice

Example::

        import minigun.generate as g
        import minigun.arbitrary as a

        # Create generators for custom data
        person_gen = g.map(
            lambda name, age: {"name": name, "age": age},
            g.str(),
            g.small_nat()
        )

        # Sample values
        state = a.seed(42)
        state, maybe_person = person_gen.sample(state)
"""

# External module dependencies
import math
import string

###############################################################################
# Localizing builtins
###############################################################################
from builtins import bool as _bool
from builtins import dict as _dict
from builtins import float as _float
from builtins import int as _int
from builtins import list as _list
from builtins import set as _set
from builtins import str as _str
from builtins import tuple as _tuple
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache, partial
from typing import Any, cast, get_args, get_origin

# Internal module dependencies
from minigun import arbitrary as a
from minigun import cardinality as c
from minigun import shrink as s
from minigun import stream as fs
from minigun import util as u

###############################################################################
# Generator
###############################################################################

#: A sample taken from a generator over a type `T`. The dissection is None
#: when generation failed (e.g. a filter rejected the drawn value).
type Sample[T] = _tuple[a.State, s.Dissection[T] | None]

#: A sampler over a type `T`
type Sampler[T] = Callable[[a.State], Sample[T]]


@dataclass(slots=True)
class Generator[T]:
    """A generator over a type `T`.

    :param sample: The sampler drawing dissected values of type `T`.
    :param cardinality: The cardinality of the generator's domain.
    """

    sample: Sampler[T]
    cardinality: c.Cardinality


###############################################################################
# Generator Combinators
###############################################################################
def map[*P, R](
    func: Callable[[*P], R], *generators: Generator[Any]
) -> Generator[R]:
    """A variadic map function of given input generators over types `A`, `B`, etc. to an output generator over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param generators: Input generators over types `A`, `B`, etc. to map from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A mapped output generator.
    :rtype: `Generator[R]`
    """

    def _impl(state: a.State) -> Sample[R]:
        dissections: _list[s.Dissection[Any]] = []
        for generator in generators:
            state, dissection = generator.sample(state)
            if dissection is None:
                return state, None
            dissections.append(dissection)
        return state, s.map(func, *dissections)

    combined_cardinality = c.ONE
    for generator in generators:
        combined_cardinality = combined_cardinality * generator.cardinality
    return Generator(_impl, combined_cardinality)


def bind[*P, R](
    func: Callable[[*P], Generator[R]],
    *generators: Generator[Any],
) -> Generator[R]:
    """A variadic bind function of given input generators over types `A`, `B`, etc. to an output generator over type `R`.

    :param func: A function creating a generator of type `R`, parameterized by generated instances of type `A`, `B`, etc.
    :type func: `A x B x ... -> Generator[R]`
    :param generators: Input generators over types `A`, `B`, etc. to instance from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A bound output generator.
    :rtype: `Generator[R]`
    """

    def _impl(state: a.State) -> Sample[R]:
        values: _list[Any] = []
        for generator in generators:
            state, dissection = generator.sample(state)
            if dissection is None:
                return state, None
            values.append(dissection.head)
        _values: _tuple[*P] = cast(_tuple[*P], _tuple(values))
        return func(*_values).sample(state)

    combined_cardinality = c.ONE
    for generator in generators:
        combined_cardinality = combined_cardinality * generator.cardinality
    return Generator(_impl, combined_cardinality)


def lazy[T](thunk: Callable[[], Generator[T]]) -> Generator[T]:
    """Defer construction of a generator until the first sample is drawn.

    Useful for recursive generator definitions where eager construction
    (including cardinality arithmetic performed by combinators such as
    ``map``, ``bind`` and ``choice``) would otherwise blow up construction
    time exponentially in the recursion depth. The inner generator is
    built once and then reused.

    Cardinality is reported as ``Infinite`` since the inner generator
    is unknown at construction time.

    :param thunk: A zero-argument callable returning a generator of type `T`.
    :type thunk: `() -> Generator[T]`

    :return: A generator of type `T` that builds its inner generator on demand.
    :rtype: `Generator[T]`
    """
    cached: _list[Generator[T]] = []

    def _impl(state: a.State) -> Sample[T]:
        if not cached:
            cached.append(thunk())
        return cached[0].sample(state)

    return Generator(_impl, c.INFINITE)


def filter[T](
    predicate: Callable[[T], _bool], generator: Generator[T]
) -> Generator[T]:
    """Filter a generator of type `T`. Both drawn values and their shrunk
    alternatives satisfy the predicate.

    :param predicate: A predicate on type `T`.
    :type predicate: `A -> bool`
    :param generator: A generator of type `T` to be filtered.
    :type generator: `Generator[T]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """

    def _impl(state: a.State) -> Sample[T]:
        state, dissection = generator.sample(state)
        if dissection is None:
            return state, None
        return state, s.filter(predicate, dissection)

    # Filtering reduces cardinality, but we don't know by how much;
    # use the original cardinality as an upper bound.
    return Generator(_impl, generator.cardinality)


###############################################################################
# Constant
###############################################################################
def constant[T](value: T) -> Generator[T]:
    """A generator that samples a constant value.

    :param value: The constant value to be sampled.
    :type value: `T`

    :return: A constant generator.
    :rtype: `Generator[T]`
    """

    def _impl(state: a.State) -> Sample[T]:
        return state, s.singleton(value)

    return Generator(_impl, c.ONE)


###############################################################################
# None
###############################################################################
def none() -> Generator[None]:
    """A constant generator for None.

    :return: A constant generator of None.
    :rtype: `Generator[None]`
    """
    return constant(None)


###############################################################################
# Boolean
###############################################################################
def bool() -> Generator[_bool]:
    """A generator for booleans.

    :return: A generator of bool.
    :rtype: `Generator[bool]`
    """
    _shrink = s.bool()

    def _impl(state: a.State) -> Sample[_bool]:
        state, result = a.bool(state)
        return state, _shrink(result)

    return Generator(_impl, c.finite(2))


###############################################################################
# Numbers
###############################################################################

#: Cumulative probability tiers: (chance threshold, magnitude bound).
type _Tiers = _tuple[_tuple[_float, _int], ...]


def _tiered_int(
    tiers: _Tiers, signed: _bool, cardinality: _int
) -> Generator[_int]:
    """An integer generator drawing magnitudes from probability tiers,
    biased towards small values."""

    def _impl(state: a.State) -> Sample[_int]:
        state, prob = a.probability(state)
        bound = tiers[-1][1]
        for threshold, tier_bound in tiers:
            if prob < threshold:
                bound = tier_bound
                break
        if signed:
            state, result = a.int(state, -bound, bound)
        else:
            state, result = a.nat(state, 0, bound)
        return state, s.int(0)(result)

    return Generator(_impl, c.finite(cardinality))


def small_nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    return _tiered_int(((0.75, 10), (1.0, 100)), False, 101)


def nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    return _tiered_int(
        ((0.5, 10), (0.75, 100), (0.95, 1000), (1.0, 10000)), False, 10001
    )


def big_nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    return _tiered_int(
        ((0.25, 10), (0.5, 100), (0.75, 1000), (0.95, 10000), (1.0, 1000000)),
        False,
        1000001,
    )


def small_int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-100 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    return _tiered_int(((0.75, 10), (1.0, 100)), True, 201)


def int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-10000 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    return _tiered_int(
        ((0.5, 10), (0.75, 100), (0.95, 1000), (1.0, 10000)), True, 20001
    )


def big_int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-1000000 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    return _tiered_int(
        ((0.25, 10), (0.5, 100), (0.75, 1000), (0.95, 10000), (1.0, 1000000)),
        True,
        2000001,
    )


def float() -> Generator[_float]:
    """A generator for floats :code:`n` in the range :code:`-e^15 <= n <= e^15`.

    :return: A generator of float.
    :rtype: `Generator[float]`
    """
    _shrink = s.float(0.0)

    def _impl(state: a.State) -> Sample[_float]:
        state, exponent = a.float(state, -15.0, 15.0)
        state, sign = a.bool(state)
        result = (1.0 if sign else -1.0) * math.exp(exponent)
        return state, _shrink(result)

    # Floats are effectively unbounded for coverage purposes
    return Generator(_impl, c.INFINITE)


###############################################################################
# Ranges
###############################################################################
def int_range(lower_bound: _int, upper_bound: _int) -> Generator[_int]:
    """A generator for integers :code:`i` in the range :code:`lower_bound <= i <= upper_bound`.

    :param lower_bound: A min bound for the sampled value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the sampled value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    assert lower_bound <= upper_bound
    target = max(lower_bound, min(0, upper_bound))
    _shrink = s.int(target)

    def _impl(state: a.State) -> Sample[_int]:
        state, result = a.int(state, lower_bound, upper_bound)
        return state, _shrink(result)

    return Generator(_impl, c.finite(upper_bound - lower_bound + 1))


###############################################################################
# Probability
###############################################################################
def prop(bias: _float) -> Generator[_bool]:
    """A generator for booleans which are True with the given bias.

    :param bias: The probability of sampling True, in the range 0.0 to 1.0.
    :type bias: `float`

    :return: A generator of bool.
    :rtype: `Generator[bool]`
    """
    assert 0.0 <= bias and bias <= 1.0, "Invariant"
    _shrink = s.bool()

    def _impl(state: a.State) -> Sample[_bool]:
        state, roll = a.float(state, 0.0, 1.0)
        return state, _shrink(roll <= bias)

    return Generator(_impl, c.finite(2))


###############################################################################
# Sequence dissection
###############################################################################
def _sequence_dissection[R](
    dissections: _list[s.Dissection[Any]],
    rebuild: Callable[[_list[Any]], R],
    min_length: _int | None = None,
) -> s.Dissection[R]:
    """Dissect a sequence of element dissections into a dissection of the
    rebuilt composite value.

    Shrinking proceeds by element removal (when `min_length` is given and
    the sequence is longer than it), then by element-wise shrinking.

    :param dissections: The element dissections making up the composite.
    :param rebuild: Rebuilds the composite value from element values.
    :param min_length: Minimum sequence length to preserve while removing
        elements, or None when element removal is not a valid shrink.
    """

    def _shrink_length(
        index: _int, dissections: _list[s.Dissection[Any]]
    ) -> fs.StreamResult[s.Dissection[R]]:
        if min_length is None or len(dissections) <= min_length:
            raise StopIteration
        if index == len(dissections):
            raise StopIteration
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(
            _shrink_length, index + 1, dissections
        )

    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[Any]],
        streams: _list[fs.Stream[s.Dissection[Any]]],
    ) -> fs.StreamResult[s.Dissection[R]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        try:
            next_dissect, next_stream = streams[index]()
        except StopIteration:
            return _shrink_value(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = next_dissect
        _streams[index] = next_stream
        return _dist(_dissections), fs.concat(
            partial(_shrink_value, index, dissections, _streams),
            partial(_shrink_value, _index, dissections, streams),
        )

    def _dist(dissections: _list[s.Dissection[Any]]) -> s.Dissection[R]:
        heads = [dissection.head for dissection in dissections]
        tails = [dissection.shrinks for dissection in dissections]
        return s.Dissection(
            rebuild(heads),
            fs.concat(
                partial(_shrink_length, 0, dissections),
                partial(_shrink_value, 0, dissections, tails),
            ),
        )

    return _dist(dissections)


def _sample_many[T](
    state: a.State, sampler: Sampler[T], count: _int
) -> _tuple[a.State, _list[s.Dissection[T]] | None]:
    """Draw `count` dissections from a sampler, or None if any draw fails."""
    dissections: _list[s.Dissection[T]] = []
    for _ in range(count):
        state, dissection = sampler(state)
        if dissection is None:
            return state, None
        dissections.append(dissection)
    return state, dissections


def _sized_cardinality(
    lower_bound: _int, upper_bound: _int, item_cardinality: c.Cardinality
) -> c.Cardinality:
    """Cardinality of a sized collection: sum of |item|^size over sizes."""
    total = c.ZERO
    for size in range(lower_bound, upper_bound + 1):
        total = total + (item_cardinality ** c.finite(size))
    return total


###############################################################################
# Strings
###############################################################################
@cache
def _bounded_str_cardinality(
    lower_bound: _int, upper_bound: _int, alphabet_size: _int
) -> c.Cardinality:
    """Cardinality for bounded strings: sum of |alphabet|^l for l in [lo, hi]."""
    return _sized_cardinality(lower_bound, upper_bound, c.finite(alphabet_size))


def bounded_str(
    lower_bound: _int, upper_bound: _int, alphabet: _str
) -> Generator[_str]:
    """A generator for strings over a given alphabet with bounded length :code:`l` in the range :code:`lower_bound <= l <= upper_bound`.

    :param lower_bound: A min bound for the length of the sampled value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the length of the sampled value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param alphabet: A string representing the alphabet to be sampled from.
    :type alphabet: `str`

    :return: A generator of str.
    :rtype: `Generator[str]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound
    _shrink = s.str()

    def _impl(state: a.State) -> Sample[_str]:
        state, length = a.int(state, lower_bound, upper_bound)
        result = ""
        for _ in range(length):
            state, index = a.int(state, 0, len(alphabet) - 1)
            result += alphabet[index]
        return state, _shrink(result)

    return Generator(
        _impl,
        _bounded_str_cardinality(lower_bound, upper_bound, len(alphabet)),
    )


def str() -> Generator[_str]:
    """A generator for strings over all printable ascii characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """

    def _impl(upper_bound: _int) -> Generator[_str]:
        return bounded_str(0, upper_bound, string.printable)

    return bind(_impl, small_nat())


def word() -> Generator[_str]:
    """A generator for strings over ascii alphabet characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """

    def _impl(upper_bound: _int) -> Generator[_str]:
        return bounded_str(0, upper_bound, string.ascii_letters)

    return bind(_impl, small_nat())


###############################################################################
# Tuples
###############################################################################
def tuple(*generators: Generator[Any]) -> Generator[_tuple[Any, ...]]:
    """A generator of tuples over given value generators of type `A`, `B`, etc.

    :param generators: Value generators over types `A`, `B`, etc. to generate tuple values from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A generator of tuples over types `A`, `B`, etc.
    :rtype: `Generator[Tuple[A, B, ...]]`
    """

    def _impl(state: a.State) -> Sample[_tuple[Any, ...]]:
        dissections: _list[s.Dissection[Any]] = []
        for generator in generators:
            state, dissection = generator.sample(state)
            if dissection is None:
                return state, None
            dissections.append(dissection)
        return state, _sequence_dissection(dissections, _tuple)

    combined_cardinality = c.ONE
    for generator in generators:
        combined_cardinality = combined_cardinality * generator.cardinality
    return Generator(_impl, combined_cardinality)


###############################################################################
# List
###############################################################################
def bounded_list[T](
    lower_bound: _int,
    upper_bound: _int,
    generator: Generator[T],
    ordered: _bool = False,
) -> Generator[_list[T]]:
    """A generator for lists over a given type `T` with bounded length :code:`l` in the range :code:`0 <= lower_bound <= l <= upper_bound`.

    :param lower_bound: A min bound for the length of the sampled list, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the length of the sampled list, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param generator: A value generator from which list items are sampled.
    :type generator: `Generator[T]`
    :param ordered: Whether items of sampled lists should be sorted.
    :type ordered: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound

    def _rebuild(heads: _list[T]) -> _list[T]:
        return sorted(heads) if ordered else heads  # type: ignore[type-var]

    def _impl(state: a.State) -> Sample[_list[T]]:
        state, length = a.nat(state, lower_bound, upper_bound)
        state, dissections = _sample_many(state, generator.sample, length)
        if dissections is None:
            return state, None
        return state, _sequence_dissection(
            dissections, _rebuild, min_length=lower_bound
        )

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, generator.cardinality),
    )


def list[T](
    generator: Generator[T], ordered: _bool = False
) -> Generator[_list[T]]:
    """A generator for lists over a given type `T`.

    :param generator: A value generator from which list items are sampled.
    :type generator: `Generator[T]`
    :param ordered: Whether items of sampled lists should be sorted.
    :type ordered: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """

    def _impl(upper_bound: _int) -> Generator[_list[T]]:
        return bounded_list(0, upper_bound, generator, ordered)

    return bind(_impl, small_nat())


def map_list[T](
    generators: _list[Generator[T]], ordered: _bool = False
) -> Generator[_list[T]]:
    """Composes lists of generators over a given type `T`, resulting in a generator of lists over the given type `T`.

    :param generators: A list of value generators from which value lists are sampled.
    :type generators: `List[Generator[T]]`
    :param ordered: Whether items of sampled lists should be sorted.
    :type ordered: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """

    def _compose(*values: T) -> _list[T]:
        result = _list(values)
        if ordered:
            result = sorted(result)  # type: ignore[type-var]
        return result

    return map(_compose, *generators)


def list_append[T](
    items_gen: Generator[_list[T]], item_gen: Generator[T]
) -> Generator[_list[T]]:
    """Compose a lists generator over type `T` with a value generator of
    type `T`, resulting in a list generator over the given type `T`, where a value has been sampled from the later generator and guaranteed to have been appended to output sampled lists.

    :param items_gen: A generator from which lists are sampled.
    :type items_gen: `Generator[List[T]]`
    :param item_gen: A generator from which values are sampled.
    :type item_gen: `Generator[T]`

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """

    def _append(items: _list[T], item: T) -> _list[T]:
        result = items.copy()
        result.append(item)
        return result

    return map(_append, items_gen, item_gen)


###############################################################################
# Dictionary
###############################################################################
def bounded_dict[K, V](
    lower_bound: _int,
    upper_bound: _int,
    key_generator: Generator[K],
    value_generator: Generator[V],
) -> Generator[_dict[K, V]]:
    """A generator for dicts over a given key type `K` and value type `V` with bounded size :code:`s` in the range :code:`0 <= lower_bound <= s <= upper_bound`.

    :param lower_bound: A min bound for the size of the sampled dict, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the size of the sampled dict, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param key_generator: A key generator from which dict keys are sampled.
    :type key_generator: `Generator[K]`
    :param value_generator: A value generator from which dict values are sampled.
    :type value_generator: `Generator[V]`

    :return: A generator of dicts over key type `K` and value type `V`.
    :rtype: `Generator[Dict[K, V]]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound

    def _pair(key: K, value: V) -> _tuple[K, V]:
        return key, value

    def _impl(state: a.State) -> Sample[_dict[K, V]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        pairs: _list[s.Dissection[_tuple[K, V]]] = []
        for _ in range(size):
            state, key_dissection = key_generator.sample(state)
            if key_dissection is None:
                return state, None
            state, value_dissection = value_generator.sample(state)
            if value_dissection is None:
                return state, None
            pairs.append(s.map(_pair, key_dissection, value_dissection))
        return state, _sequence_dissection(pairs, _dict, min_length=lower_bound)

    pair_cardinality = key_generator.cardinality * value_generator.cardinality
    return Generator(
        _impl, _sized_cardinality(lower_bound, upper_bound, pair_cardinality)
    )


def dict[K, V](
    key_generator: Generator[K], value_generator: Generator[V]
) -> Generator[_dict[K, V]]:
    """A generator for dicts over a given key type `K` and value type `V`.

    :param key_generator: A key generator from which dict keys are sampled.
    :type key_generator: `Generator[K]`
    :param value_generator: A value generator from which dict values are sampled.
    :type value_generator: `Generator[V]`

    :return: A generator of dicts over key type `K` and value type `V`.
    :rtype: `Generator[Dict[K, V]]`
    """

    def _impl(upper_bound: _int) -> Generator[_dict[K, V]]:
        return bounded_dict(0, upper_bound, key_generator, value_generator)

    return bind(_impl, small_nat())


def map_dict[K, V](
    generators: _dict[K, Generator[V]],
) -> Generator[_dict[K, V]]:
    """Composes dicts of generators over given types `K` and `V`, resulting in a generator of dicts over the given types `K` and `V`.

    :param generators: A dict of value generators from which value dicts are sampled.
    :type generators: `Dict[K, Generator[V]]`

    :return: A generator of dicts over types `K` and `V`.
    :rtype: `Generator[Dict[K, V]]`
    """
    keys = _list(generators.keys())

    def _compose(*values: V) -> _dict[K, V]:
        return {keys[index]: value for index, value in enumerate(values)}

    return map(_compose, *[generators[key] for key in keys])


def dict_insert[K, V](
    kvs_gen: Generator[_dict[K, V]],
    key_gen: Generator[K],
    value_gen: Generator[V],
) -> Generator[_dict[K, V]]:
    """Compose a dict generator over types `K` and `V` with a key generator of the given type `K` and a value generator of the given type `V`, resulting in a generator of dicts over the types `K` and `V`, where a key and value has been sampled from the later generators and guaranteed to have been inserted into the output sampled dicts.

    :param kvs_gen: A generator from which dicts are sampled.
    :type kvs_gen: `Generator[Dict[K, V]]`
    :param key_gen: A generator from which keys are sampled.
    :type key_gen: `Generator[K]`
    :param value_gen: A generator from which values are sampled.
    :type value_gen: `Generator[V]`

    :return: A generator of dicts over types `K` and `V`.
    :rtype: `Generator[Dict[K, V]]`
    """

    def _insert(kvs: _dict[K, V], key: K, value: V) -> _dict[K, V]:
        result = kvs.copy()
        result[key] = value
        return result

    return map(_insert, kvs_gen, key_gen, value_gen)


###############################################################################
# Sets
###############################################################################
def bounded_set[T](
    lower_bound: _int, upper_bound: _int, generator: Generator[T]
) -> Generator[_set[T]]:
    """A generator for sets over a given type `T` with bounded size :code:`s` in the range :code:`0 <= lower_bound <= s <= upper_bound`.

    :param lower_bound: A min bound for the size of the sampled set, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the size of the sampled set, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param generator: A value generator from which set items are sampled.
    :type generator: `Generator[T]`

    :return: A generator of sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound

    def _impl(state: a.State) -> Sample[_set[T]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        state, dissections = _sample_many(state, generator.sample, size)
        if dissections is None:
            return state, None
        return state, _sequence_dissection(
            dissections, _set, min_length=lower_bound
        )

    return Generator(
        _impl,
        _sized_cardinality(lower_bound, upper_bound, generator.cardinality),
    )


def set[T](generator: Generator[T]) -> Generator[_set[T]]:
    """A generator for sets over a given type `T`.

    :param generator: A value generator from which set items are sampled.
    :type generator: `Generator[T]`

    :return: A generator of sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """

    def _impl(upper_bound: _int) -> Generator[_set[T]]:
        return bounded_set(0, upper_bound, generator)

    return bind(_impl, small_nat())


def map_set[T](generators: _set[Generator[T]]) -> Generator[_set[T]]:
    """Composes sets of generators over a given type `T`, resulting in a generator of sets over the given type `T`.

    :param generators: A set of value generators from which value sets are sampled.
    :type generators: `Set[Generator[T]]`

    :return: A generator of sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """

    def _mapping(*values: T) -> _set[T]:
        return _set(values)

    return map(_mapping, *generators)


def set_add[T](
    items_gen: Generator[_set[T]], item_gen: Generator[T]
) -> Generator[_set[T]]:
    """Compose a set generator over a type `T` with a value generator of type `T`, resulting in a generator of sets over the given type `T`, where a value has been sampled from the later generator and guaranteed to have been added to the output sampled sets.

    :param items_gen: A generator from which sets are sampled.
    :type items_gen: `Generator[Set[T]]`
    :param item_gen: A generator from which values are sampled.
    :type item_gen: `Generator[T]`

    :return: A generator of output sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """

    def _add(items: _set[T], item: T) -> _set[T]:
        result = items.copy()
        result.add(item)
        return result

    return map(_add, items_gen, item_gen)


###############################################################################
# Optional
###############################################################################
def optional[T](generator: Generator[T]) -> Generator[T | None]:
    """A generator of optional values over a given type `T`, sampling None
    with a small probability.

    :param generator: A value generator to make optional.
    :type generator: `Generator[T]`

    :return: A generator of optional values over type `T`.
    :rtype: `Generator[T | None]`
    """

    def _some(value: T) -> T | None:
        return value

    def _append_none(
        dissection: s.Dissection[T | None],
    ) -> s.Dissection[T | None]:
        return s.append(dissection, None)

    def _impl(state: a.State) -> Sample[T | None]:
        state, p = a.probability(state)
        if p < 0.05:
            return state, s.singleton(None)
        state, dissection = generator.sample(state)
        if dissection is None:
            return state, None
        _dissection = s.map(_some, dissection)
        return state, s.Dissection(
            _dissection.head, fs.map(_append_none, _dissection.shrinks)
        )

    return Generator(_impl, generator.cardinality + c.ONE)


###############################################################################
# Argument pack
###############################################################################
def argument_pack(
    generators: _dict[_str, Generator[Any]],
) -> Generator[_dict[_str, Any]]:
    """A generator for argument packs.

    :param generators: Generator from which the arguments are sampled.
    :type generators: `Dict[str, Generator[Any]]`

    :return: A generator for argument packs.
    :rtype: `Generator[Dict[str, Any]]`
    """
    names = _list(generators.keys())

    def _rebuild(heads: _list[Any]) -> _dict[_str, Any]:
        return _dict(zip(names, heads, strict=True))

    def _impl(state: a.State) -> Sample[_dict[_str, Any]]:
        dissections: _list[s.Dissection[Any]] = []
        for name in names:
            state, dissection = generators[name].sample(state)
            if dissection is None:
                return state, None
            dissections.append(dissection)
        return state, _sequence_dissection(dissections, _rebuild)

    total_cardinality = c.ONE
    for generator in generators.values():
        total_cardinality = total_cardinality * generator.cardinality
    return Generator(_impl, total_cardinality)


###############################################################################
# Choice combinators
###############################################################################
def choice[T](*generators: Generator[T]) -> Generator[T]:
    """A generator of a type `T` composed of other generators of type `T`.

    :param generators: generators of type `T`.
    :type generators: `Tuple[Generator[T], ...]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    assert len(generators) != 0

    def _impl(state: a.State) -> Sample[T]:
        state, index = a.nat(state, 0, len(generators) - 1)
        return generators[index].sample(state)

    combined_cardinality = c.ZERO
    for generator in generators:
        combined_cardinality = combined_cardinality + generator.cardinality
    return Generator(_impl, combined_cardinality)


def weighted_choice[T](
    *weighted_generators: _tuple[_int, Generator[T]],
) -> Generator[T]:
    """A generator of a type `T` composed of other weighted generators of type `T`.

    :param weighted_generators: Number of chances to sample from, with their corresponding generators of type `T`.
    :type weighted_generators: `Tuple[Tuple[int, Generator[T]], ...]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    assert len(weighted_generators) != 0
    weights = [weight for weight, _ in weighted_generators]
    samplers = [generator.sample for _, generator in weighted_generators]

    def _impl(state: a.State) -> Sample[T]:
        state, sampler = a.weighted_choice(state, weights, samplers)
        return sampler(state)

    combined_cardinality = c.ZERO
    for _, generator in weighted_generators:
        combined_cardinality = combined_cardinality + generator.cardinality
    return Generator(_impl, combined_cardinality)


def one_of[T](values: _list[T]) -> Generator[T]:
    """A generator of a type `T` defined over a list of `T`, which will select one of the values of given list when sampled.

    :param values: A list of values of type `T`.
    :type values: `List[T]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    assert len(values) != 0

    def _select(index: _int) -> T:
        return values[index]

    return map(_select, int_range(0, len(values) - 1))


def subset_of[T](values: _set[T]) -> Generator[_set[T]]:
    """A generator of a type `T` defined over a list of `T`, which will select a subset of the values of given set when sampled.

    :param values: A set of values of type `T`.
    :type values: `Set[T]`

    :return: A set generator of type `T`.
    :rtype: `Generator[Set[T]]`
    """
    assert len(values) != 0
    _values = _list(values)

    def _select(indices: _set[_int]) -> _set[T]:
        return _set([_values[index] for index in indices])

    count = len(_values)
    return map(_select, bounded_set(0, count, int_range(0, count - 1)))


###############################################################################
# Infer a generator
###############################################################################
def infer(T: type) -> Generator[Any] | None:
    """Infer a generator for a given type `T`.

    :param T: A type to infer a generator of.
    :type T: `type`

    :return: A generator of type T, or None when no generator is known.
    :rtype: `Generator[Any] | None`
    """

    def _case_tuple(T: type) -> Generator[Any] | None:
        item_generators: _list[Generator[Any]] = []
        for item_T in get_args(T):
            item_generator = infer(item_T)
            if item_generator is None:
                return None
            item_generators.append(item_generator)
        return tuple(*item_generators)

    def _case_list(T: type) -> Generator[Any] | None:
        item_generator = infer(get_args(T)[0])
        if item_generator is None:
            return None
        return list(item_generator)

    def _case_dict(T: type) -> Generator[Any] | None:
        K, V = get_args(T)[:2]
        key_generator = infer(K)
        value_generator = infer(V)
        if key_generator is None or value_generator is None:
            return None
        return dict(key_generator, value_generator)

    def _case_set(T: type) -> Generator[Any] | None:
        item_generator = infer(get_args(T)[0])
        if item_generator is None:
            return None
        return set(item_generator)

    if T == _bool:
        return bool()
    if T == _int:
        return int()
    if T == _float:
        return float()
    if T == _str:
        return str()

    inner = u.optional_inner(T)
    if inner is not None:
        inner_generator = infer(inner)
        if inner_generator is None:
            return None
        return optional(inner_generator)

    match get_origin(T):
        case x if x is _tuple:
            return _case_tuple(T)
        case x if x is _list:
            return _case_list(T)
        case x if x is _dict:
            return _case_dict(T)
        case x if x is _set:
            return _case_set(T)
        case _:
            return None
