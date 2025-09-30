"""
Data Generators and Combinators

This module provides the core data generation system for property-based testing.
It implements generators for all Python built-in types and combinators for
composing complex data structures with proper shrinking support.

Architecture:
    - Generator[T]: Tuple of (sampler, cardinality) for type T
    - Sample[T]: State-threaded generation with shrinking info
    - Combinators: map, bind, filter, choice for composition

Built-in Generators:
    - Primitives: bool, nat, int, float, char, str
    - Collections: list, dict, set, tuple
    - Utilities: constant, one_of, weighted_choice

The generator system integrates with the cardinality analysis system to provide
optimal test attempt allocation based on domain complexity.

Example:
    ```python
    import minigun.generate as g
    import minigun.arbitrary as a

    # Create generators for custom data
    person_gen = g.map(
        lambda name, age: {"name": name, "age": age},
        g.str(),
        g.nat(0, 120)
    )

    # Sample values
    state = a.seed(42)
    state, maybe_person = person_gen(state)
    ```
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
from functools import partial
from inspect import Parameter, signature
from typing import Any, cast, get_args, get_origin

from returns.maybe import Maybe, Nothing, Some

# Internal module dependencies
from minigun import arbitrary as a
from minigun import cardinality as c
from minigun import order as o
from minigun import shrink as s
from minigun import stream as fs
from minigun import util as u

###############################################################################
# Generator
###############################################################################

#: A sample taken from a generator over a type `T`
type Sample[T] = _tuple[a.State, Maybe[s.Dissection[T]]]

#: A sampler over a type `T`
type Sampler[T] = Callable[[a.State], Sample[T]]

#: A generator over a type `T`
type Generator[T] = _tuple[Sampler[T], c.Cardinality]


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

    func_parameters = signature(func).parameters
    argument_count = len(func_parameters)
    func_is_variadic = any(
        parameter.kind == Parameter.VAR_POSITIONAL
        for parameter in func_parameters.values()
    )
    assert len(generators) == argument_count or func_is_variadic, (
        f"Function {func} expected {argument_count} "
        f"arguments, but got {len(generators)} generators."
    )

    def _impl(state: a.State) -> Sample[R]:
        dissections: _list[s.Dissection[Any]] = []
        for sampler, _ in generators:
            state, maybe_dissection = sampler(state)
            match maybe_dissection:
                case Maybe.empty:
                    return state, Nothing
                case Some(dissection):
                    dissections.append(dissection)
                case _:
                    raise AssertionError("Invariant")
        return state, Some(s.map(func, *dissections))

    # Calculate combined cardinality: product of all input cardinalities
    combined_cardinality = c.ONE
    for _, cardinality in generators:
        combined_cardinality = combined_cardinality * cardinality
    return _impl, combined_cardinality


def bind[*P, R](
    func: Callable[[*P], Generator[R]],
    card: Callable[[_tuple[c.Cardinality, ...]], c.Cardinality],
    *generators: Generator[Any],
) -> Generator[R]:
    """A variadic bind function of given input generators over types `A`, `B`, etc. to an output generator over type `R`.

    :param func: A function creating a generator of type `R`, parameterized by generated instances of type `A`, `B`, etc.
    :type func: `A x B x ... -> Generator[R]`
    :param card: Cardinality function that computes combined cardinality from input cardinalities
    :type card: `Tuple[Cardinality, ...] -> Cardinality`
    :param generators: Additional generators over types `B`, `C`, etc. to instance from.
    :type generators: `Tuple[Generator[B], Generator[C], ...]`

    :return: A bound output generator.
    :rtype: `Generator[R]`
    """

    func_parameters = signature(func).parameters
    argument_count = len(func_parameters)
    func_is_variadic = any(
        parameter.kind == Parameter.VAR_POSITIONAL
        for parameter in func_parameters.values()
    )
    assert len(generators) == argument_count or func_is_variadic, (
        f"Function {func} expected {argument_count} "
        f"arguments, but got {len(generators)} generators."
    )

    def _impl(state: a.State) -> Sample[R]:
        values: _list[Any] = []
        for sampler, _ in generators:
            state, maybe_dissection = sampler(state)
            match maybe_dissection:
                case Maybe.empty:
                    return state, Nothing
                case Some(dissection):
                    values.append(s.head(dissection))
                case _:
                    raise AssertionError("Invariant")
        _values: _tuple[*P] = cast(_tuple[*P], _tuple(values))
        result_sampler, _ = func(*_values)
        return result_sampler(state)

    # Use product of input cardinalities as default approximation
    combined_cardinality = c.Finite(1)
    for _, cardinality in generators:
        combined_cardinality = combined_cardinality * cardinality
    return _impl, combined_cardinality


def filter[T](
    predicate: Callable[[T], _bool], generator: Generator[T]
) -> Generator[T]:
    """Filter a generator of type `T`.

    :param predicate: A predicate on type `T`.
    :type predicate: `A -> bool`
    :param generator: A generator of type `T` to be filtered.
    :type generator: `Generator[T]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """

    # Unpack the generator
    sampler, cardinality = generator

    def _impl(state: a.State) -> Sample[T]:
        state, maybe_dissection = sampler(state)
        match maybe_dissection:
            case Maybe.empty:
                return state, Nothing
            case Some(dissection):
                match s.filter(predicate, dissection):
                    case Maybe.empty:
                        return state, Nothing
                    case Some(dissection1):
                        return state, Some(dissection1)
                    case _:
                        raise AssertionError("Invariant")
            case _:
                raise AssertionError("Invariant")

    # Filtering reduces cardinality, but we don't know by how much
    # Use original cardinality as upper bound
    return _impl, cardinality


###############################################################################
# Constant
###############################################################################
def constant[T](value: T) -> Generator[T]:
    """A generator that samples a constant value.

    :param value: The constant value to be samples.
    :type value: `T`

    :return: A constant generator.
    :rtype: `Generator[T]`
    """

    def _impl(state: a.State) -> Sample[T]:
        return state, Some(s.singleton(value))

    # Constants have cardinality 1
    return _impl, c.Finite(1)


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

    def _impl(state: a.State) -> Sample[_bool]:
        state, result = a.bool(state)
        return state, Some(s.prepend(result, s.singleton(not result)))

    # Booleans have cardinality 2
    return _impl, c.Finite(2)


###############################################################################
# Numbers
###############################################################################
def small_nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        state, result = a.nat(state, 0, (10 if prop < 0.75 else 100))
        return state, Some(s.int(0)(result))

    # small_nat ranges from 0 to 100, so cardinality is 101
    return _impl, c.Finite(101)


def nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        match prop:
            case _ if prop < 0.5:
                bound = 10
            case _ if prop < 0.75:
                bound = 100
            case _ if prop < 0.95:
                bound = 1000
            case _:
                bound = 10000
        state, result = a.nat(state, 0, bound)
        return state, Some(s.int(0)(result))

    # Nat has cardinality approximately 10000 (weighted towards smaller numbers)
    return _impl, c.Finite(10001)  # 0 to 10000 inclusive


def big_nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        match prop:
            case _ if prop < 0.25:
                bound = 10
            case _ if prop < 0.5:
                bound = 100
            case _ if prop < 0.75:
                bound = 1000
            case _ if prop < 0.95:
                bound = 10000
            case _:
                bound = 1000000
        state, result = a.nat(state, 0, bound)
        return state, Some(s.int(0)(result))

    # Big nat has cardinality approximately 1000000
    return _impl, c.Finite(1000001)  # 0 to 1000000 inclusive


def small_int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-100 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        bound = 10 if prop < 0.75 else 100
        state, result = a.int(state, -bound, bound)
        return state, Some(s.int(0)(result))

    # Small int from -100 to 100 = 201 values
    return _impl, c.Finite(201)


def int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-10000 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        match prop:
            case _ if prop < 0.5:
                bound = 10
            case _ if prop < 0.75:
                bound = 100
            case _ if prop < 0.95:
                bound = 1000
            case _:
                bound = 10000
        state, result = a.int(state, -bound, bound)
        return state, Some(s.int(0)(result))

    # Int from -10000 to 10000 = 20001 values
    return _impl, c.Finite(20001)


def big_int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-1000000 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        match prop:
            case _ if prop < 0.25:
                bound = 10
            case _ if prop < 0.5:
                bound = 100
            case _ if prop < 0.75:
                bound = 1000
            case _ if prop < 0.95:
                bound = 10000
            case _:
                bound = 1000000
        state, result = a.int(state, -bound, bound)
        return state, Some(s.int(0)(result))

    # Big int from -1000000 to 1000000 = 2000001 values
    return _impl, c.Finite(2000001)


def float() -> Generator[_float]:
    """A generator for floats :code:`n` in the range :code:`-e^15 <= n <= e^15`.

    :return: A generator of float.
    :rtype: `Generator[float]`
    """

    def _impl(state: a.State) -> Sample[_float]:
        state, exponent = a.float(state, -15.0, 15.0)
        state, sign = a.bool(state)
        result = (1.0 if sign else -1.0) * math.exp(exponent)
        return state, Some(s.float(0.0)(result))

    # Float has IEEE 754 double precision: 2^64 possible values
    # Use BigO notation to represent this exponential complexity
    return _impl, c.BigO(c._Const(2) ** c._Const(64))


###############################################################################
# Ranges
###############################################################################
def int_range(lower_bound: _int, upper_bound: _int) -> Generator[_int]:
    """A generator for indices :code:`i` in the range :code:`lower_bound <= i <= upper_bound`.

    :param lower_bound: A min bound for the sampled value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the sampled value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A generator of int.
    :rtype: `Generator[int]`
    """

    def _impl(state: a.State) -> Sample[_int]:
        assert lower_bound <= upper_bound
        state, result = a.int(state, lower_bound, upper_bound)
        target = max(lower_bound, min(0, upper_bound))
        return state, Some(s.int(target)(result))

    # int_range cardinality is the number of integers in the range
    cardinality = upper_bound - lower_bound + 1
    return _impl, c.Finite(cardinality)


###############################################################################
# Propability
###############################################################################
def prop(bias: _float) -> Generator[_bool]:
    assert 0.0 <= bias and bias <= 1.0, "Invariant"

    def _impl(state: a.State) -> Sample[_bool]:
        state, roll = a.float(state, 0.0, 1.0)
        return state, Some(s.bool()(roll <= bias))

    return _impl, c.Finite(2)  # Still binary (True/False)


###############################################################################
# Strings
###############################################################################
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

    def _impl(state: a.State) -> Sample[_str]:
        result = ""
        for _ in range(upper_bound - lower_bound):
            state, index = a.int(state, 0, len(alphabet) - 1)
            result += alphabet[index]
        return state, Some(s.str()(result))

    # Cardinality for bounded strings: sum over all possible lengths
    # For each length l in [lower_bound, upper_bound], there are |alphabet|^l strings
    string_cardinality = c.Finite(0)
    for length in range(lower_bound, upper_bound + 1):
        string_cardinality = string_cardinality + (
            c.Finite(len(alphabet)) ** c.Finite(length)
        )

    return _impl, string_cardinality


def str() -> Generator[_str]:
    """A generator for strings over all printable ascii characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """

    def _impl(upper_bound: _int) -> Generator[_str]:
        return bounded_str(0, upper_bound, string.printable)

    def _card(cards: _tuple[c.Cardinality, ...]) -> c.Cardinality:
        # String cardinality grows exponentially with length: |alphabet|^length
        # Use BigO notation to express this exponential complexity
        max_length_card = cards[0] if cards else c.Finite(10)
        alphabet_size = c.Finite(
            len(string.printable)
        )  # ~95 printable ASCII chars
        return c.BigO(
            alphabet_size._to_symbolic() ** max_length_card._to_symbolic()
        )

    return bind(_impl, _card, nat())


def word() -> Generator[_str]:
    """A generator for strings over ascii alphabet characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """

    def _impl(upper_bound: _int) -> Generator[_str]:
        return bounded_str(0, upper_bound, string.ascii_letters)

    def _card(cards: _tuple[c.Cardinality, ...]) -> c.Cardinality:
        # Word cardinality: |alphabet|^length for alphabetic strings
        max_length_card = cards[0] if cards else c.Finite(10)
        alphabet_size = c.Finite(
            len(string.ascii_letters)
        )  # 52 letters (a-z, A-Z)
        return c.BigO(
            alphabet_size._to_symbolic() ** max_length_card._to_symbolic()
        )

    return bind(_impl, _card, small_nat())


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

    # Combined cardinality is the product of all cardinalities
    samplers = []
    combined_cardinality = c.Finite(1)  # Empty tuple has cardinality 1
    for sampler, cardinality in generators:
        samplers.append(sampler)
        combined_cardinality = combined_cardinality * cardinality

    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[Any]],
        streams: _list[fs.Stream[s.Dissection[Any]]],
    ) -> fs.StreamResult[s.Dissection[_tuple[Any, ...]]]:
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

    def _dist(
        dissections: _list[s.Dissection[Any]],
    ) -> s.Dissection[_tuple[Any, ...]]:
        heads: _list[Any] = [s.head(dissection) for dissection in dissections]
        tails: _list[fs.Stream[s.Dissection[Any]]] = [
            s.tail(dissection) for dissection in dissections
        ]
        return _tuple(heads), partial(_shrink_value, 0, dissections, tails)

    def _impl(state: a.State) -> Sample[_tuple[Any, ...]]:
        values: _list[s.Dissection[Any]] = []
        for sampler in samplers:
            state, maybe_value = sampler(state)
            match maybe_value:
                case Maybe.empty:
                    return state, Nothing
                case Some(value):
                    values.append(value)
                case _:
                    raise AssertionError("Invariant")
        return state, Some(_dist(values))

    return _impl, combined_cardinality


###############################################################################
# List
###############################################################################
def bounded_list[T](
    lower_bound: _int,
    upper_bound: _int,
    generator: Generator[T],
    ordered: o.Order[T] | None = None,
) -> Generator[_list[T]]:
    """A generator for lists over a given type `T` with bounded length :code:`l` in the range :code:`0 <= lower_bound <= l <= upper_bound`.

    :param lower_bound: A min bound for the length of the sampled list, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the length of the sampled list, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param generator: A value generator from which list items are sampled.
    :type generator: `Generator[T]`
    :param ordering: Flag for whether items of sampled lists should be ordered.
    :type ordering: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound

    # Unpack the generator
    sampler, item_cardinality = generator

    def _shrink_length(
        index: _int, dissections: _list[s.Dissection[T]]
    ) -> fs.StreamResult[s.Dissection[_list[T]]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_length, _index, dissections)

    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[T]],
        streams: _list[fs.Stream[s.Dissection[T]]],
    ) -> fs.StreamResult[s.Dissection[_list[T]]]:
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

    def _dist(dissections: _list[s.Dissection[T]]) -> s.Dissection[_list[T]]:
        heads: _list[Any] = [s.head(dissection) for dissection in dissections]
        tails: _list[Any] = [s.tail(dissection) for dissection in dissections]
        if ordered:
            heads = o.sort(ordered, heads)
        return heads, fs.concat(
            partial(_shrink_length, 0, dissections),
            partial(_shrink_value, 0, dissections, tails),
        )

    def _impl(state: a.State) -> Sample[_list[T]]:
        state, length = a.nat(state, lower_bound, upper_bound)
        result: _list[s.Dissection[T]] = []
        for _ in range(length):
            state, maybe_item = sampler(state)
            match maybe_item:
                case Maybe.empty:
                    return state, Nothing
                case Some(item):
                    result.append(item)
                case _:
                    raise AssertionError("Invariant")
        return state, Some(_dist(result))

    # Calculate cardinality for bounded list
    # For a list of length k with items from domain of size n:
    # - If order matters: n^k possibilities
    # - Total across all lengths from lower_bound to upper_bound

    # Sum over all possible lengths
    cardinalities = []
    for length in range(lower_bound, upper_bound + 1):
        length_cardinality = c.ONE
        for _ in range(length):
            length_cardinality = length_cardinality * item_cardinality
        cardinalities.append(length_cardinality)

    # Sum all length possibilities
    list_cardinality = c.ZERO
    for card in cardinalities:
        list_cardinality = c.Sum(list_cardinality, card)

    return _impl, list_cardinality


def list[T](
    generator: Generator[T], ordered: o.Order[T] | None = None
) -> Generator[_list[T]]:
    """A generator for lists over a given type `T`.

    :param generator: A value generator from which list items are sampled.
    :type generator: `Generator[T]`
    :param ordering: Flag for whether items of sampled lists should be ordered`.
    :type ordering: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """

    def _impl(upper_bound: _int) -> Generator[_list[T]]:
        return bounded_list(0, upper_bound, generator, ordered)

    def _card(cards: _tuple[c.Cardinality, ...]) -> c.Cardinality:
        # List cardinality grows exponentially with length: |item_type|^length
        max_length_card = cards[0] if cards else c.Finite(10)
        _, item_cardinality = generator
        return c.BigO(
            item_cardinality._to_symbolic() ** max_length_card._to_symbolic()
        )

    return bind(_impl, _card, small_nat())


def map_list[T](
    generators: _list[Generator[T]], ordered: o.Order[T] | None = None
) -> Generator[_list[T]]:
    """Composes lists of generators over a given type `T`, resulting in a generator of lists over the given type `T`.

    :param generators: A list of value generators from which value lists are sampled.
    :type generators: `List[Generator[T]]`
    :param ordering: Flag for whether items of sampled lists should be ordered`.
    :type ordering: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """

    def _compose(*values: T) -> _list[T]:
        result = _list(values)
        if ordered:
            result = o.sort(ordered, result)
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

    # Extract samplers and cardinalities
    key_sampler, key_cardinality = key_generator
    value_sampler, value_cardinality = value_generator

    def _shrink_size(
        index: _int,
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]],
    ) -> fs.StreamResult[s.Dissection[_dict[K, V]]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_size, _index, dissections)

    def _shrink_keys(
        index: _int,
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]],
        streams: _list[
            _tuple[fs.Stream[s.Dissection[K]], fs.Stream[s.Dissection[V]]]
        ],
    ) -> fs.StreamResult[s.Dissection[_dict[K, V]]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        try:
            next_dissect, next_stream = streams[index][0]()
        except StopIteration:
            return _shrink_keys(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = (next_dissect, _dissections[index][1])
        _streams[index] = (next_stream, _streams[index][1])
        return _dist(_dissections), fs.concat(
            partial(_shrink_keys, index, dissections, _streams),
            partial(_shrink_keys, _index, dissections, streams),
        )

    def _shrink_values(
        index: _int,
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]],
        streams: _list[
            _tuple[fs.Stream[s.Dissection[K]], fs.Stream[s.Dissection[V]]]
        ],
    ) -> fs.StreamResult[s.Dissection[_dict[K, V]]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        try:
            next_dissect, next_stream = streams[index][1]()
        except StopIteration:
            return _shrink_values(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = (_dissections[index][0], next_dissect)
        _streams[index] = (_streams[index][0], next_stream)
        return _dist(_dissections), fs.concat(
            partial(_shrink_values, index, dissections, _streams),
            partial(_shrink_values, _index, dissections, streams),
        )

    def _dist(
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]],
    ) -> s.Dissection[_dict[K, V]]:
        heads: _list[_tuple[Any, Any]] = [
            (s.head(dissection[0]), s.head(dissection[1]))
            for dissection in dissections
        ]
        tails = [
            (s.tail(dissection[0]), s.tail(dissection[1]))
            for dissection in dissections
        ]
        return _dict(heads), fs.concat(
            partial(_shrink_size, 0, dissections),
            fs.concat(
                partial(_shrink_keys, 0, dissections, tails),
                partial(_shrink_values, 0, dissections, tails),
            ),
        )

    def _impl(state: a.State) -> Sample[_dict[K, V]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        result: _list[_tuple[s.Dissection[K], s.Dissection[V]]] = []
        for _ in range(size):
            state, maybe_key = key_sampler(state)
            match maybe_key:
                case Maybe.empty:
                    return state, Nothing
                case Some(key):
                    state, maybe_value = value_sampler(state)
                    match maybe_value:
                        case Maybe.empty:
                            return state, Nothing
                        case Some(value):
                            result.append((key, value))
                        case _:
                            raise AssertionError("Invariant")
                case _:
                    raise AssertionError("Invariant")
        return state, Some(_dist(result))

    # Calculate cardinality for bounded dict
    # For a dict of size k with keys from domain of size n and values from domain of size m:
    # - Ideally: C(n,k) * m^k (choose k unique keys, each paired with any of m values)
    # - For large n: approximately n^k * m^k = (n*m)^k (keys rarely collide)
    # - We use the simpler approximation for computational efficiency

    pair_cardinality = key_cardinality * value_cardinality
    cardinalities = []
    for size in range(lower_bound, upper_bound + 1):
        size_cardinality = c.ONE
        for _ in range(size):
            size_cardinality = size_cardinality * pair_cardinality
        cardinalities.append(size_cardinality)

    # Sum all size possibilities
    dict_cardinality = c.ZERO
    for card in cardinalities:
        dict_cardinality = dict_cardinality + card

    return _impl, dict_cardinality


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

    def _card(cards: _tuple[c.Cardinality, ...]) -> c.Cardinality:
        # Dict cardinality: (|key_type| × |value_type|)^size
        max_size_card = cards[0] if cards else c.Finite(10)
        _, key_cardinality = key_generator
        _, value_cardinality = value_generator
        pair_cardinality = key_cardinality * value_cardinality
        return c.BigO(
            pair_cardinality._to_symbolic() ** max_size_card._to_symbolic()
        )

    return bind(_impl, _card, small_nat())


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

    # Unpack the generator
    sampler, item_cardinality = generator

    def _shrink_size(
        index: _int, dissections: _list[s.Dissection[T]]
    ) -> fs.StreamResult[s.Dissection[_set[T]]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_size, _index, dissections)

    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[T]],
        streams: _list[fs.Stream[s.Dissection[T]]],
    ) -> fs.StreamResult[s.Dissection[_set[T]]]:
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

    def _dist(dissections: _list[s.Dissection[T]]) -> s.Dissection[_set[T]]:
        heads: _list[Any] = [s.head(dissection) for dissection in dissections]
        tails: _list[Any] = [s.tail(dissection) for dissection in dissections]
        return _set(heads), fs.concat(
            partial(_shrink_size, 0, dissections),
            partial(_shrink_value, 0, dissections, tails),
        )

    def _impl(state: a.State) -> Sample[_set[T]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        result: _list[s.Dissection[T]] = []
        for _ in range(size):
            state, maybe_item = sampler(state)
            match maybe_item:
                case Maybe.empty:
                    return state, Nothing
                case Some(item):
                    result.append(item)
                case _:
                    raise AssertionError("Invariant")
        return state, Some(_dist(result))

    # Calculate cardinality for bounded set
    # For a set of size k with items from domain of size n:
    # - Exact: C(n,k) = n! / (k! * (n-k)!) possibilities (choose k unique items)
    # - For large n: approximately n^k (collision probability is low)
    # - We use the simpler n^k approximation since exact combinations are expensive to compute
    # - The unified cardinality system handles overflow protection automatically

    cardinalities = []
    for size in range(lower_bound, upper_bound + 1):
        size_cardinality = c.ONE
        for _ in range(size):
            size_cardinality = size_cardinality * item_cardinality
        cardinalities.append(size_cardinality)

    # Sum all size possibilities
    set_cardinality = c.ZERO
    for card in cardinalities:
        set_cardinality = set_cardinality + card

    return _impl, set_cardinality


def set[T](generator: Generator[T]) -> Generator[_set[T]]:
    """A generator for sets over a given type `T`.

    :param generator: A value generator from which set items are sampled.
    :type generator: `Generator[T]`

    :return: A generator of sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """

    def _impl(upper_bound: _int) -> Generator[_set[T]]:
        return bounded_set(0, upper_bound, generator)

    def _card(cards: _tuple[c.Cardinality, ...]) -> c.Cardinality:
        # Set cardinality: approximately |item_type|^size (unique elements)
        max_size_card = cards[0] if cards else c.Finite(10)
        _, item_cardinality = generator
        return c.BigO(
            item_cardinality._to_symbolic() ** max_size_card._to_symbolic()
        )

    return bind(_impl, _card, small_nat())


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
# Maybe
###############################################################################
def maybe[T](generator: Generator[T]) -> Generator[Maybe[T]]:
    """A generator of maybe over a given type `T`.

    :param generator: A value generator to map maybe over.
    :type generator: `Generator[T]`

    :return: A generator of maybe over type `T`.
    :rtype: `Generator[returns.maybe.Maybe[T]]`
    """
    sampler, cardinality = generator

    def _something(value: T) -> Maybe[T]:
        return Some(value)

    def _append(dissection: s.Dissection[Maybe[T]]) -> s.Dissection[Maybe[T]]:
        return s.append(dissection, Nothing)

    def _impl(state: a.State) -> Sample[Maybe[T]]:
        state, p = a.probability(state)
        if p < 0.05:
            return state, Some(s.singleton(Nothing))
        state, maybe_value = sampler(state)
        match maybe_value:
            case Maybe.empty:
                return state, Nothing
            case Some(value):
                _value = s.map(_something, value)
                return state, Some(
                    (s.head(_value), fs.map(_append, s.tail(_value)))
                )
            case _:
                raise AssertionError("Invariant")

    # Maybe[T] has cardinality |T| + 1 (for the Nothing case)
    maybe_cardinality = cardinality + c.Finite(1)
    return _impl, maybe_cardinality


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

    def _shrink_args(
        index: _int,
        dissections: _list[_tuple[_str, s.Dissection[Any]]],
        streams: _list[_tuple[_str, fs.Stream[s.Dissection[Any]]]],
    ) -> fs.StreamResult[s.Dissection[_dict[_str, Any]]]:
        if index == len(dissections):
            raise StopIteration
        _index = index + 1
        try:
            next_dissect, next_stream = streams[index][1]()
        except StopIteration:
            return _shrink_args(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = (_dissections[index][0], next_dissect)
        _streams[index] = (_streams[index][0], next_stream)
        return _dist(_dissections), fs.concat(
            partial(_shrink_args, index, dissections, _streams),
            partial(_shrink_args, _index, dissections, streams),
        )

    def _dist(
        dissections: _list[_tuple[_str, s.Dissection[Any]]],
    ) -> s.Dissection[_dict[_str, Any]]:
        heads: _list[_tuple[_str, Any]] = [
            (dissection[0], s.head(dissection[1])) for dissection in dissections
        ]
        tails = [
            (dissection[0], s.tail(dissection[1])) for dissection in dissections
        ]
        return _dict(heads), partial(_shrink_args, 0, dissections, tails)

    def _impl(state: a.State) -> Sample[_dict[_str, Any]]:
        result: _list[_tuple[_str, s.Dissection[Any]]] = []
        for param, generator in generators.items():
            sampler, _ = generator
            state, maybe_arg = sampler(state)
            match maybe_arg:
                case Maybe.empty:
                    return state, Nothing
                case Some(arg):
                    result.append((param, arg))
                case _:
                    raise AssertionError("Invariant")
        return state, Some(_dist(result))

    # Calculate combined cardinality
    total_cardinality = c.ONE
    for generator in generators.values():
        _, cardinality = generator
        total_cardinality = total_cardinality * cardinality

    return _impl, total_cardinality


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

    # Extract samplers and cardinalities
    samplers: _list[Sampler[T]] = []
    cardinalities: _list[c.Cardinality] = []

    for sampler, cardinality in generators:
        samplers.append(sampler)
        cardinalities.append(cardinality)

    def _impl(state: a.State) -> Sample[T]:
        state, index = a.nat(state, 0, len(samplers) - 1)
        return samplers[index](state)

    # Cardinality is the sum of all generator cardinalities
    combined_cardinality = c.ZERO
    for card in cardinalities:
        combined_cardinality = combined_cardinality + card

    return _impl, combined_cardinality


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
    weights: _list[_int] = []
    samplers: _list[Sampler[T]] = []
    cardinalities: _list[c.Cardinality] = []

    for weight, (sampler, cardinality) in weighted_generators:
        weights.append(weight)
        samplers.append(sampler)
        cardinalities.append(cardinality)

    def _impl(state: a.State) -> Sample[T]:
        state, sampler = a.weighted_choice(state, weights, samplers)
        return sampler(state)

    # For weighted choice, cardinality is the sum of all possible choices
    combined_cardinality = c.ZERO
    for card in cardinalities:
        combined_cardinality = combined_cardinality + card

    return _impl, combined_cardinality


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
def infer(T: type) -> Maybe[Generator[Any]]:
    """Infer a generator of type `T` for a given type `T` with cardinality-aware optimization.

    This function leverages the unified cardinality system to choose appropriate
    generators based on the complexity of the target type.

    :param T: A type to infer a generator of.
    :type T: `type`

    :return: A maybe of generator of type T.
    :rtype: `returns.maybe.Maybe[Generator[T]]`
    """

    def _case_maybe(T: type) -> Maybe[Generator[Any]]:
        return infer(get_args(T)[0]).map(maybe)

    def _case_tuple(T: type) -> Maybe[Generator[Any]]:
        item_samplers: _list[Generator[Any]] = []
        for item_T in get_args(T):
            match infer(item_T):
                case Maybe.empty:
                    return Nothing
                case Some(item_sampler):
                    item_samplers.append(item_sampler)
                case _:
                    raise AssertionError("Invariant")
        return Some(tuple(*item_samplers))

    def _case_list(T: type) -> Maybe[Generator[Any]]:
        return infer(get_args(T)[0]).map(list)

    def _case_dict(T: type) -> Maybe[Generator[Any]]:
        K, V = get_args(T)[:2]
        match (infer(K), infer(V)):
            case (Some(key_sampler), Some(value_sampler)):
                return Some(dict(key_sampler, value_sampler))
            case (Maybe.empty, _) | (_, Maybe.empty):
                return Nothing
            case _:
                raise AssertionError("Invariant")

    def _case_set(T: type) -> Maybe[Generator[Any]]:
        return infer(get_args(T)[0]).map(set)

    # Use cardinality inference to choose appropriate generators
    inferred_cardinality = c.infer_cardinality_from_type(T)
    complexity_class = inferred_cardinality.asymptotic_class()

    if T == _bool:
        return Some(bool())
    if T == _int:
        # For infinite integer types, use bounded generators for practicality
        if "∞" in complexity_class:
            return Some(int())  # Uses bounded range internally
        return Some(small_int())
    if T == _float:
        return Some(float())
    if T == _str:
        # For exponential string types, use smaller bounds
        if "^" in complexity_class:
            return Some(word())  # Smaller alphabet than str()
        return Some(str())
    if u.is_maybe(T):
        return _case_maybe(T)

    # Use pattern matching for origin-based type dispatch
    origin = get_origin(T)
    if origin is None:
        return Nothing

    match origin:
        case x if x is _tuple:
            return _case_tuple(T)
        case x if x is _list:
            return _case_list(T)
        case x if x is _dict:
            return _case_dict(T)
        case x if x is _set:
            return _case_set(T)
        case _:
            return Nothing
