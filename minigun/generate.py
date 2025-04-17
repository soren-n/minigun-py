# External module dependencies
from inspect import signature
from typing import (
    get_origin,
    get_args,
    Callable,
    Optional,
    Any
)
from returns.maybe import (
    Maybe,
    Nothing,
    Some
)
from functools import partial
import string
import math

# Internal module dependencies
from . import (
    arbitrary as a,
    stream as fs,
    shrink as s,
    order as o,
    util as u
)

###############################################################################
# Localizing builtins
###############################################################################
from builtins import (
    bool as _bool,
    int as _int,
    float as _float,
    str as _str,
    dict as _dict,
    list as _list,
    set as _set,
    tuple as _tuple,
    map as _map
)

###############################################################################
# Generator
###############################################################################

#: A sample taken from a generator over a type `T`
type Sample[T] = _tuple[a.State, Maybe[s.Dissection[T]]]

#: A generator over a type `T`
type Generator[T] = Callable[[a.State], Sample[T]]

def map[**P, R](
    func: Callable[P, R],
    *generators: Generator[Any]
    ) -> Generator[R]:
    """A variadic map function of given input generators over types `A`, `B`, etc. to an output generator over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param generators: Input generators over types `A`, `B`, etc. to map from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A mapped output generator.
    :rtype: `Generator[R]`
    """

    func_signature = signature(func)
    argument_count = len(func_signature.parameters)
    assert len(generators) == argument_count, (
        f'Function {func.__name__} expected {argument_count} '
        f'arguments, but got {len(generators)} generators.'
    )

    def _impl(state: a.State) -> Sample[R]:
        dissections: _list[s.Dissection[Any]] = []
        for generator in generators:
            state, maybe_dissection = generator(state)
            match maybe_dissection:
                case Maybe.empty: return state, Nothing
                case Some(dissection):
                    dissections.append(dissection)
                case _: assert False, 'Invariant'
        return state, Some(s.map(func, *dissections))

    return _impl

def bind[**P, R](
    func: Callable[P, Generator[R]],
    *generators: Generator[Any]
    ) -> Generator[R]:
    """A variadic bind function of given input generators over types `A`, `B`, etc. to an output generator over type `R`.

    :param func: A function creating a generator of type `R`, parameterized by generated instances of type `A`, `B`, etc.
    :type func: `A x B x ... -> Generator[R]`
    :param generators: Generators over types `A`, `B`, etc. to instance from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A bound output generator.
    :rtype: `Generator[R]`
    """

    func_signature = signature(func)
    argument_count = len(func_signature.parameters)
    assert len(generators) == argument_count, (
        f'Function {func.__name__} expected {argument_count} '
        f'arguments, but got {len(generators)} generators.'
    )

    def _impl(state: a.State) -> Sample[R]:
        values: _list[Any] = []
        for generator in generators:
            state, maybe_dissection = generator(state)
            match maybe_dissection:
                case Maybe.empty: return state, Nothing
                case Some(dissection):
                    values.append(s.head(dissection))
                case _: assert False, 'Invariant'
        return func(*values)(state)

    return _impl

def filter[T](
    predicate: Callable[[T], _bool],
    generator: Generator[T]
    ) -> Generator[T]:
    """Filter a generator of type `T`.

    :param predicate: A predicate on type `T`.
    :type predicate: `A -> bool`
    :param generator: A generator of type `T` to be filtered.
    :type generator: `Generator[T]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    def _impl(state: a.State) -> Sample[T]:
        state, maybe_dissection = generator(state)
        match maybe_dissection:
            case Maybe.empty: return state, Nothing
            case Some(dissection):
                match s.filter(predicate, dissection):
                    case Maybe.empty: return state, Nothing
                    case Some(dissection1):
                        return state, Some(dissection1)
                    case _: assert False, 'Invariant'
            case _: assert False, 'Invariant'

    return _impl

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
    return _impl

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
    return _impl

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
        state, result = a.nat(state, 0, (
            10 if prop < 0.75 else
            100
        ))
        return state, Some(s.int(0)(result))
    return _impl

def nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        state, result = a.nat(state, 0, (
            10 if prop < 0.5 else
            100 if prop < 0.75 else
            1000 if prop < 0.95 else
            10000
        ))
        return state, Some(s.int(0)(result))
    return _impl

def big_nat() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        state, result = a.nat(state, 0, (
            10 if prop < 0.25 else
            100 if prop < 0.5 else
            1000 if prop < 0.75 else
            10000 if prop < 0.95 else
            1000000
        ))
        return state, Some(s.int(0)(result))
    return _impl

def small_int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-100 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        bound = (
            10 if prop < 0.75 else
            100
        )
        state, result = a.int(state, -bound, bound)
        return state, Some(s.int(0)(result))
    return _impl

def int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-10000 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        bound = (
            10 if prop < 0.5 else
            100 if prop < 0.75 else
            1000 if prop < 0.95 else
            10000
        )
        state, result = a.int(state, -bound, bound)
        return state, Some(s.int(0)(result))
    return _impl

def big_int() -> Generator[_int]:
    """A generator for integers :code:`n` in the range :code:`-1000000 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_int]:
        state, prop = a.probability(state)
        bound = (
            10 if prop < 0.25 else
            100 if prop < 0.5 else
            1000 if prop < 0.75 else
            10000 if prop < 0.95 else
            1000000
        )
        state, result = a.int(state, -bound, bound)
        return state, Some(s.int(0)(result))
    return _impl

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
    return _impl

###############################################################################
# Ranges
###############################################################################
def int_range(
    lower_bound: _int,
    upper_bound: _int
    ) -> Generator[_int]:
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
    return _impl

###############################################################################
# Propability
###############################################################################
def prop(bias: _float) -> Generator[_bool]:
    assert 0.0 <= bias and bias <= 1.0, 'Invariant'
    def _impl(state: a.State) -> Sample[_bool]:
        state, roll = a.float(state, 0.0, 1.0)
        return state, Some(s.bool()(roll <= bias))
    return _impl

###############################################################################
# Strings
###############################################################################
def bounded_str(
    lower_bound: _int,
    upper_bound: _int,
    alphabet: _str
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
        result = ''
        for _ in range(upper_bound - lower_bound):
            state, index = a.int(state, 0, len(alphabet) - 1)
            result += alphabet[index]
        return state, Some(s.str()(result))
    return _impl

def str() -> Generator[_str]:
    """A generator for strings over all printable ascii characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """
    def _impl(upper_bound: _int) -> Generator[_str]:
        return bounded_str(0, upper_bound, string.printable)
    return bind(_impl, nat())

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
def tuple(
    *generators: Generator[Any]
    ) -> Generator[_tuple[Any, ...]]:
    """A generator of tuples over given value generators of type `A`, `B`, etc.

    :param generators: Value generators over types `A`, `B`, etc. to generate tuple values from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A generator of tuples over types `A`, `B`, etc.
    :rtype: `Generator[Tuple[A, B, ...]]`
    """
    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[Any]],
        streams: _list[fs.Stream[s.Dissection[Any]]]
        ) -> fs.StreamResult[s.Dissection[_tuple[Any, ...]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        try: next_dissect, next_stream = streams[index]()
        except StopIteration: return _shrink_value(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = next_dissect
        _streams[index] = next_stream
        return _dist(_dissections), fs.concat(
            partial(_shrink_value, index, dissections, _streams),
            partial(_shrink_value, _index, dissections, streams)
        )
    def _dist(
        dissections: _list[s.Dissection[Any]]
        ) -> s.Dissection[_tuple[Any, ...]]:
        heads: _list[Any] = [ s.head(dissection) for dissection in dissections ]
        tails: _list[Any] = [ s.tail(dissection) for dissection in dissections ]
        return _tuple(heads), partial(_shrink_value, 0, heads, tails)
    def _impl(state: a.State) -> Sample[_tuple[Any, ...]]:
        values: _list[s.Dissection[Any]] = []
        for generator in generators:
            state, maybe_value = generator(state)
            match maybe_value:
                case Maybe.empty: return state, Nothing
                case Some(value): values.append(value)
                case _: assert False, 'Invariant'
        return state, Some(_dist(values))
    return _impl

###############################################################################
# List
###############################################################################
def bounded_list[T](
    lower_bound: _int,
    upper_bound: _int,
    generator: Generator[T],
    ordered: Optional[o.Order[T]] = None
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
    def _shrink_length(
        index: _int,
        dissections: _list[s.Dissection[T]]
        ) -> fs.StreamResult[s.Dissection[_list[T]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_length, _index, dissections)
    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[T]],
        streams: _list[fs.Stream[s.Dissection[T]]]
        ) -> fs.StreamResult[s.Dissection[_list[T]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        try: next_dissect, next_stream = streams[index]()
        except StopIteration: return _shrink_value(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = next_dissect
        _streams[index] = next_stream
        return _dist(_dissections), fs.concat(
            partial(_shrink_value, index, dissections, _streams),
            partial(_shrink_value, _index, dissections, streams)
        )
    def _dist(dissections: _list[s.Dissection[T]]) -> s.Dissection[_list[T]]:
        heads: _list[Any] = [ s.head(dissection) for dissection in dissections ]
        tails: _list[Any] = [ s.tail(dissection) for dissection in dissections ]
        if ordered: heads = o.sort(ordered, heads)
        return heads, fs.concat(
            partial(_shrink_length, 0, dissections),
            partial(_shrink_value, 0, dissections, tails)
        )
    def _impl(state: a.State) -> Sample[_list[T]]:
        state, length = a.nat(state, lower_bound, upper_bound)
        result: _list[s.Dissection[T]] = []
        for _ in range(length):
            state, maybe_item = generator(state)
            match maybe_item:
                case Maybe.empty: return state, Nothing
                case Some(item): result.append(item)
                case _: assert False, 'Invariant'
        return state, Some(_dist(result))
    return _impl

def list[T](
    generator: Generator[T],
    ordered: Optional[o.Order[T]] = None
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
    return bind(_impl, small_nat())

def map_list[T](
    generators: _list[Generator[T]],
    ordered: Optional[o.Order[T]] = None
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
        if ordered: result = o.sort(ordered, result)
        return result
    return map(_compose, *generators)

def list_append[T](
    items_gen: Generator[_list[T]],
    item_gen: Generator[T]
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
    value_generator: Generator[V]
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
    def _shrink_size(
        index: _int,
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]]
        ) -> fs.StreamResult[s.Dissection[_dict[K, V]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_size, _index, dissections)
    def _shrink_keys(
        index: _int,
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]],
        streams: _list[_tuple[
            fs.Stream[s.Dissection[K]],
            fs.Stream[s.Dissection[V]]]
        ]
        ) -> fs.StreamResult[s.Dissection[_dict[K, V]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        try: next_dissect, next_stream = streams[index][0]()
        except StopIteration: return _shrink_keys(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = (next_dissect, _dissections[index][1])
        _streams[index] = (next_stream, _streams[index][1])
        return _dist(_dissections), fs.concat(
            partial(_shrink_keys, index, dissections, _streams),
            partial(_shrink_keys, _index, dissections, streams)
        )
    def _shrink_values(
        index: _int,
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]],
        streams: _list[_tuple[
            fs.Stream[s.Dissection[K]],
            fs.Stream[s.Dissection[V]]]
        ]
        ) -> fs.StreamResult[s.Dissection[_dict[K, V]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        try: next_dissect, next_stream = streams[index][1]()
        except StopIteration: return _shrink_values(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = (_dissections[index][0], next_dissect)
        _streams[index] = (_streams[index][0], next_stream)
        return _dist(_dissections), fs.concat(
            partial(_shrink_values, index, dissections, _streams),
            partial(_shrink_values, _index, dissections, streams)
        )
    def _dist(
        dissections: _list[_tuple[s.Dissection[K], s.Dissection[V]]]
        ) -> s.Dissection[_dict[K, V]]:
        heads: _list[_tuple[Any, Any]] = [
            ( s.head(dissection[0]), s.head(dissection[1]) )
            for dissection in dissections
        ]
        tails = [
            ( s.tail(dissection[0]), s.tail(dissection[1]) )
            for dissection in dissections
        ]
        return _dict(heads), fs.concat(
            partial(_shrink_size, 0, dissections),
            fs.concat(
                partial(_shrink_keys, 0, dissections, tails),
                partial(_shrink_values, 0, dissections, tails)
            )
        )
    def _impl(state: a.State) -> Sample[_dict[K, V]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        result: _list[_tuple[s.Dissection[K], s.Dissection[V]]] = []
        for _ in range(size):
            state, maybe_key = key_generator(state)
            match maybe_key:
                case Maybe.empty: return state, Nothing
                case Some(key):
                    state, maybe_value = value_generator(state)
                    match maybe_value:
                        case Maybe.empty: return state, Nothing
                        case Some(value):
                            result.append((key, value))
                        case _: assert False, 'Invariant'
                case _: assert False, 'Invariant'
        return state, Some(_dist(result))
    return _impl

def dict[K, V](
    key_generator: Generator[K],
    value_generator: Generator[V]
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
    generators: _dict[K, Generator[V]]
    ) -> Generator[_dict[K, V]]:
    """Composes dicts of generators over given types `K` and `V`, resulting in a generator of dicts over the given types `K` and `V`.

    :param generators: A dict of value generators from which value dicts are sampled.
    :type generators: `Dict[K, Generator[V]]`

    :return: A generator of dicts over types `K` and `V`.
    :rtype: `Generator[Dict[K, V]]`
    """
    keys = _list(generators.keys())
    def _compose(*values: V) -> _dict[K, V]:
        return {
            keys[index]: value
            for index, value in enumerate(values)
        }
    return map(_compose, *[ generators[key] for key in keys ])

def dict_insert[K, V](
    kvs_gen: Generator[_dict[K, V]],
    key_gen: Generator[K],
    value_gen: Generator[V]
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
    lower_bound: _int,
    upper_bound: _int,
    generator: Generator[T]
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
    def _shrink_size(
        index: _int,
        dissections: _list[s.Dissection[T]]
        ) -> fs.StreamResult[s.Dissection[_set[T]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_size, _index, dissections)
    def _shrink_value(
        index: _int,
        dissections: _list[s.Dissection[T]],
        streams: _list[fs.Stream[s.Dissection[T]]]
        ) -> fs.StreamResult[s.Dissection[_set[T]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        try: next_dissect, next_stream = streams[index]()
        except StopIteration: return _shrink_value(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = next_dissect
        _streams[index] = next_stream
        return _dist(_dissections), fs.concat(
            partial(_shrink_value, index, dissections, _streams),
            partial(_shrink_value, _index, dissections, streams)
        )
    def _dist(dissections: _list[s.Dissection[T]]) -> s.Dissection[_set[T]]:
        heads: _list[Any] = [ s.head(dissection) for dissection in dissections ]
        tails: _list[Any] = [ s.tail(dissection) for dissection in dissections ]
        return _set(heads), fs.concat(
            partial(_shrink_size, 0, dissections),
            partial(_shrink_value, 0, dissections, tails)
        )
    def _impl(state: a.State) -> Sample[_set[T]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        result: _list[s.Dissection[T]] = []
        for _ in range(size):
            state, maybe_item = generator(state)
            match maybe_item:
                case Maybe.empty: return state, Nothing
                case Some(item): result.append(item)
                case _: assert False, 'Invariant'
        return state, Some(_dist(result))
    return _impl

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

def map_set[T](
    generators: _set[Generator[T]]
    ) -> Generator[_set[T]]:
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
    items_gen: Generator[_set[T]],
    item_gen: Generator[T]
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
def maybe[T](
    generator: Generator[T]
    ) -> Generator[Maybe[T]]:
    """A generator of maybe over a given type `T`.

    :param generator: A value generator to map maybe over.
    :type generator: `Generator[T]`

    :return: A generator of maybe over type `T`.
    :rtype: `Generator[returns.maybe.Maybe[T]]`
    """
    def _something(value: T) -> Maybe[T]:
        return Some(value)
    def _append(dissection: s.Dissection[Maybe[T]]) -> s.Dissection[Maybe[T]]:
        return s.append(dissection, Nothing)
    def _impl(state: a.State) -> Sample[Maybe[T]]:
        state, p = a.probability(state)
        if p < 0.05: return state, Some(s.singleton(Nothing))
        state, maybe_value = generator(state)
        match maybe_value:
            case Maybe.empty: return state, Nothing
            case Some(value):
                _value = s.map(_something, value)
                return state, Some((
                    s.head(_value),
                    fs.map(_append, s.tail(_value))
                ))
            case _: assert False, 'Invariant'
    return _impl

###############################################################################
# Argument pack
###############################################################################
def argument_pack(
    generators: _dict[_str, Generator[Any]]
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
        streams: _list[_tuple[_str, fs.Stream[s.Dissection[Any]]]]
        ) -> fs.StreamResult[s.Dissection[_dict[_str, Any]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        try: next_dissect, next_stream = streams[index][1]()
        except StopIteration: return _shrink_args(_index, dissections, streams)
        _dissections = dissections.copy()
        _streams = streams.copy()
        _dissections[index] = (_dissections[index][0], next_dissect)
        _streams[index] = (_streams[index][0], next_stream)
        return _dist(_dissections), fs.concat(
            partial(_shrink_args, index, dissections, _streams),
            partial(_shrink_args, _index, dissections, streams)
        )
    def _dist(
        dissections: _list[_tuple[_str, s.Dissection[Any]]]
        ) -> s.Dissection[_dict[_str, Any]]:
        heads: _list[_tuple[_str, Any]] = [
            (dissection[0], s.head(dissection[1]))
            for dissection in dissections
        ]
        tails = [
            (dissection[0], s.tail(dissection[1]))
            for dissection in dissections
        ]
        return _dict(heads), partial(_shrink_args, 0, dissections, tails)
    def _impl(state: a.State) -> Sample[_dict[_str, Any]]:
        result: _list[_tuple[_str, s.Dissection[Any]]] = []
        for param, arg_generator in generators.items():
            state, maybe_arg = arg_generator(state)
            match maybe_arg:
                case Maybe.empty: return state, Nothing
                case Some(arg): result.append((param, arg))
                case _: assert False, 'Invariant'
        return state, Some(_dist(result))
    return _impl

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
    def _impl(index: _int) -> Generator[T]: return generators[index]
    return bind(_impl, int_range(0, len(generators) - 1))

def weighted_choice[T](
    *weighted_generators: _tuple[_int, Generator[T]]
    ) -> Generator[T]:
    """A generator of a type `T` composed of other weighted generators of type `T`.

    :param weighted_generators: Number of chances to sample from, with their corresponding generators of type `T`.
    :type weighted_generators: `Tuple[Tuple[int, Generator[T]], ...]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    assert len(weighted_generators) != 0
    weights: _list[_int] = []
    choices: _list[Generator[T]] = []
    weights, choices = _map(_list, zip(*weighted_generators))
    def _impl(state: a.State) -> Sample[T]:
        state, generator = a.weighted_choice(state, weights, choices)
        return generator(state)
    return _impl

def one_of[T](
    values: _list[T]
    ) -> Generator[T]:
    """A generator of a type `T` defined over a list of `T`, which will select one of the values of given list when sampled.

    :param values: A list of values of type `T`.
    :type values: `List[T]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    assert len(values) != 0
    def _select(index: _int) -> T: return values[index]
    return map(_select, int_range(0, len(values) - 1))

def subset_of[T](
    values: _set[T]
    ) -> Generator[_set[T]]:
    """A generator of a type `T` defined over a list of `T`, which will select a subset of the values of given set when sampled.

    :param values: A set of values of type `T`.
    :type values: `Set[T]`

    :return: A set generator of type `T`.
    :rtype: `Generator[Set[T]]`
    """
    assert len(values) != 0
    _values = _list(values)
    def _select(indices: _set[_int]) -> _set[T]:
        return _set([ _values[index] for index in indices ])
    count = len(_values)
    return map(_select, bounded_set(
        0, count, int_range(0, count - 1)
    ))

###############################################################################
# Infer a generator
###############################################################################
def infer(T: type) -> Maybe[Generator[Any]]:
    """Infer a generator of type `T` for a given type `T`.

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
                case Maybe.empty: return Nothing
                case Some(item_sampler):
                    item_samplers.append(item_sampler)
                case _: assert False, 'Invariant'
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
            case _: assert False, 'Invariant'
    def _case_set(T: type) -> Maybe[Generator[Any]]:
        return infer(get_args(T)[0]).map(set)
    if T == _bool: return Some(bool())
    if T == _int: return Some(int())
    if T == _float: return Some(float())
    if T == _str: return Some(str())
    if u.is_maybe(T): return _case_maybe(T)
    origin = get_origin(T)
    if origin != None:
        if origin == _tuple: return _case_tuple(T)
        if origin == _list: return _case_list(T)
        if origin == _dict: return _case_dict(T)
        if origin == _set: return _case_set(T)
    return Nothing