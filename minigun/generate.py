# External module dependencies
from typing import (
    get_origin,
    get_args,
    TypeVar,
    ParamSpec,
    Callable,
    Optional,
    Tuple,
    Any,
    List,
    Dict,
    Set
)
from functools import partial
import string
import math

# Internal module dependencies
from . import arbitrary as a
from . import stream as fs
from . import shrink as s
from . import order as o
from . import maybe as m

###############################################################################
# Localizing intrinsics
###############################################################################
_Bool = bool
_Int = int
_Float = float
_Str = str
_Tuple = tuple
_List = list
_Dict = dict
_Set = set
_Map = map

###############################################################################
# Generator
###############################################################################
T = TypeVar('T')
P = ParamSpec('P')
R = TypeVar('R')
S = TypeVar('S')

#: A sample taken from a generator over a type `T`
Sample = Tuple[a.State, s.Dissection[T]]

#: A generator over a type `T`
Generator = Callable[[a.State], Sample[T]]

def map(
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
    def _impl(state: a.State) -> Sample[R]:
        dissections: List[s.Dissection[Any]] = []
        for generator in generators:
            state, dissection = generator(state)
            dissections.append(dissection)
        return state, s.map(func, *dissections)
    return _impl

def bind(
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
    def _apply(*args: P.args, **kwargs: P.kwargs) -> Generator[R]:
        return func(*args, **kwargs)
    def _impl(state: a.State) -> Sample[R]:
        values: List[Any] = []
        for generator in generators:
            state, dissection = generator(state)
            values.append(s.head(dissection))
        return _apply(*values)(state)
    return _impl

###############################################################################
# Constant
###############################################################################
def constant(value: T) -> Generator[T]:
    """A generator that samples a constant value.

    :param value: The constant value to be samples.
    :type value: `T`

    :return: A constant generator.
    :rtype: `Generator[T]`
    """
    def _impl(state: a.State) -> Sample[T]:
        return state, s.singleton(value)
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
def bool() -> Generator[_Bool]:
    """A generator for booleans.

    :return: A generator of bool.
    :rtype: `Generator[bool]`
    """
    def _impl(state: a.State) -> Sample[_Bool]:
        state, result = a.bool(state)
        return state, s.prepend(result, s.singleton(not result))
    return _impl

###############################################################################
# Numbers
###############################################################################
def small_nat() -> Generator[_Int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        state, prop = a.probability(state)
        state, result = a.nat(state, 0, (
            10 if prop < 0.75 else
            100
        ))
        return state, s.int(0)(result)
    return _impl

def nat() -> Generator[_Int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        state, prop = a.probability(state)
        state, result = a.nat(state, 0, (
            10 if prop < 0.5 else
            100 if prop < 0.75 else
            1000 if prop < 0.95 else
            10000
        ))
        return state, s.int(0)(result)
    return _impl

def big_nat() -> Generator[_Int]:
    """A generator for integers :code:`n` in the range :code:`0 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        state, prop = a.probability(state)
        state, result = a.nat(state, 0, (
            10 if prop < 0.25 else
            100 if prop < 0.5 else
            1000 if prop < 0.75 else
            10000 if prop < 0.95 else
            1000000
        ))
        return state, s.int(0)(result)
    return _impl

def small_int() -> Generator[_Int]:
    """A generator for integers :code:`n` in the range :code:`-100 <= n <= 100`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        state, prop = a.probability(state)
        bound = (
            10 if prop < 0.75 else
            100
        )
        state, result = a.int(state, -bound, bound)
        return state, s.int(0)(result)
    return _impl

def int() -> Generator[_Int]:
    """A generator for integers :code:`n` in the range :code:`-10000 <= n <= 10000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        state, prop = a.probability(state)
        bound = (
            10 if prop < 0.5 else
            100 if prop < 0.75 else
            1000 if prop < 0.95 else
            10000
        )
        state, result = a.int(state, -bound, bound)
        return state, s.int(0)(result)
    return _impl

def big_int() -> Generator[_Int]:
    """A generator for integers :code:`n` in the range :code:`-1000000 <= n <= 1000000`.

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        state, prop = a.probability(state)
        bound = (
            10 if prop < 0.25 else
            100 if prop < 0.5 else
            1000 if prop < 0.75 else
            10000 if prop < 0.95 else
            1000000
        )
        state, result = a.int(state, -bound, bound)
        return state, s.int(0)(result)
    return _impl

def float() -> Generator[_Float]:
    """A generator for floats :code:`n` in the range :code:`-e^15 <= n <= e^15`.

    :return: A generator of float.
    :rtype: `Generator[float]`
    """
    def _impl(state: a.State) -> Sample[_Float]:
        state, exponent = a.float(state, -15.0, 15.0)
        state, sign = a.bool(state)
        result = (1.0 if sign else -1.0) * math.exp(exponent)
        return state, s.float(0.0)(result)
    return _impl

###############################################################################
# Ranges
###############################################################################
def int_range(
    lower_bound: _Int,
    upper_bound: _Int
    ) -> Generator[_Int]:
    """A generator for indices :code:`i` in the range :code:`lower_bound <= i <= upper_bound`.

    :param lower_bound: A min bound for the sampled value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the sampled value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A generator of int.
    :rtype: `Generator[int]`
    """
    def _impl(state: a.State) -> Sample[_Int]:
        assert lower_bound <= upper_bound
        state, result = a.int(state, lower_bound, upper_bound)
        target = max(lower_bound, min(0, upper_bound))
        return state, s.int(target)(result)
    return _impl

###############################################################################
# Propability
###############################################################################
def prop(bias: _Float) -> Generator[_Bool]:
    assert 0.0 <= bias and bias <= 1.0, 'Invariant'
    def _impl(state: a.State) -> Sample[_Bool]:
        state, roll = a.float(state, 0.0, 1.0)
        return state, s.bool()(roll <= bias)
    return _impl

###############################################################################
# Strings
###############################################################################
def bounded_str(
    lower_bound: _Int,
    upper_bound: _Int,
    alphabet: _Str
    ) -> Generator[_Str]:
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
    def _impl(state: a.State) -> Sample[_Str]:
        result = ''
        for _ in range(upper_bound - lower_bound):
            state, index = a.int(state, 0, len(alphabet) - 1)
            result += alphabet[index]
        return state, s.str()(result)
    return _impl

def str() -> Generator[_Str]:
    """A generator for strings over all printable ascii characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """
    def _impl(upper_bound: _Int) -> Generator[_Str]:
        return bounded_str(0, upper_bound, string.printable)
    return bind(_impl, nat())

def word() -> Generator[_Str]:
    """A generator for strings over ascii alphabet characters.

    :return: A generator of str.
    :rtype: `Generator[str]`
    """
    def _impl(upper_bound : _Int) -> Generator[_Str]:
        return bounded_str(0, upper_bound, string.ascii_letters)
    return bind(_impl, small_nat())

###############################################################################
# Tuples
###############################################################################
def tuple(
    *generators: Generator[Any]
    ) -> Generator[Tuple[Any, ...]]:
    """A generator of tuples over given value generators of type `A`, `B`, etc.

    :param generators: Value generators over types `A`, `B`, etc. to generate tuple values from.
    :type generators: `Tuple[Generator[A], Generator[B], ...]`

    :return: A generator of tuples over types `A`, `B`, etc.
    :rtype: `Generator[Tuple[A, B, ...]]`
    """
    def _shrink_value(
        index: _Int,
        dissections: List[s.Dissection[Any]],
        streams: List[fs.Stream[s.Dissection[Any]]]
        ) -> fs.StreamResult[s.Dissection[Tuple[Any, ...]]]:
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
        dissections: List[s.Dissection[Any]]
        ) -> s.Dissection[Tuple[Any, ...]]:
        heads = [ s.head(dissection) for dissection in dissections ]
        tails = [ s.tail(dissection) for dissection in dissections ]
        return _Tuple(heads), partial(_shrink_value, 0, heads, tails)
    def _impl(state: a.State) -> Sample[Tuple[Any, ...]]:
        values: List[s.Dissection[Any]] = []
        for generator in generators:
            state, value = generator(state)
            values.append(value)
        return state, _dist(values)
    return _impl

###############################################################################
# List
###############################################################################
def bounded_list(
    lower_bound: _Int,
    upper_bound: _Int,
    generator: Generator[T],
    ordered: Optional[o.Order[T]] = None
    ) -> Generator[List[T]]:
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
        index: _Int,
        dissections: List[s.Dissection[T]]
        ) -> fs.StreamResult[s.Dissection[List[T]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_length, _index, dissections)
    def _shrink_value(
        index: _Int,
        dissections: List[s.Dissection[T]],
        streams: List[fs.Stream[s.Dissection[T]]]
        ) -> fs.StreamResult[s.Dissection[List[T]]]:
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
    def _dist(dissections: List[s.Dissection[T]]) -> s.Dissection[List[T]]:
        heads = [ s.head(dissection) for dissection in dissections ]
        tails = [ s.tail(dissection) for dissection in dissections ]
        if ordered: heads = o.sort(ordered, heads)
        return heads, fs.concat(
            partial(_shrink_length, 0, dissections),
            partial(_shrink_value, 0, dissections, tails)
        )
    def _impl(state: a.State) -> Sample[List[T]]:
        state, length = a.nat(state, lower_bound, upper_bound)
        result: List[s.Dissection[T]] = []
        for _ in range(length):
            state, item = generator(state)
            result.append(item)
        return state, _dist(result)
    return _impl

def list(
    generator: Generator[T],
    ordered: Optional[o.Order[T]] = None
    ) -> Generator[List[T]]:
    """A generator for lists over a given type `T`.

    :param generator: A value generator from which list items are sampled.
    :type generator: `Generator[T]`
    :param ordering: Flag for whether items of sampled lists should be ordered`.
    :type ordering: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """
    def _impl(upper_bound: _Int) -> Generator[List[T]]:
        return bounded_list(0, upper_bound, generator, ordered)
    return bind(_impl, small_nat())

def map_list(
    generators: _List[Generator[T]],
    ordered: Optional[o.Order[T]] = None
    ) -> Generator[_List[T]]:
    """Composes lists of generators over a given type `T`, resulting in a generator of lists over the given type `T`.

    :param generators: A list of value generators from which value lists are sampled.
    :type generators: `List[Generator[T]]`
    :param ordering: Flag for whether items of sampled lists should be ordered`.
    :type ordering: `bool` (default: `False`)

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """
    def _compose(*values: T) -> _List[T]:
        result = _List(values)
        if ordered: result = o.sort(ordered, result)
        return result
    return map(_compose, *generators)

def list_append(
    items_gen: Generator[_List[T]],
    item_gen: Generator[T]
    ) -> Generator[_List[T]]:
    """Compose a lists generator over type `T` with a value generator of
    type `T`, resulting in a list generator over the given type `T`, where a value has been sampled from the later generator and guaranteed to have been appended to output sampled lists.

    :param items_gen: A generator from which lists are sampled.
    :type items_gen: `Generator[List[T]]`
    :param item_gen: A generator from which values are sampled.
    :type item_gen: `Generator[T]`

    :return: A generator of lists over type `T`.
    :rtype: `Generator[List[T]]`
    """
    def _append(items: _List[T], item: T) -> _List[T]:
        result = items.copy()
        result.append(item)
        return result
    return map(_append, items_gen, item_gen)

###############################################################################
# Dictionary
###############################################################################
K = TypeVar('K')
V = TypeVar('V')
def bounded_dict(
    lower_bound: _Int,
    upper_bound: _Int,
    key_generator: Generator[K],
    value_generator: Generator[V]
    ) -> Generator[Dict[K, V]]:
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
        index: _Int,
        dissections: List[Tuple[s.Dissection[K], s.Dissection[V]]]
        ) -> fs.StreamResult[s.Dissection[Dict[K, V]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_size, _index, dissections)
    def _shrink_keys(
        index: _Int,
        dissections: List[Tuple[s.Dissection[K], s.Dissection[V]]],
        streams: List[Tuple[
            fs.Stream[s.Dissection[K]],
            fs.Stream[s.Dissection[V]]]
        ]
        ) -> fs.StreamResult[s.Dissection[Dict[K, V]]]:
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
        index: _Int,
        dissections: List[Tuple[s.Dissection[K], s.Dissection[V]]],
        streams: List[Tuple[
            fs.Stream[s.Dissection[K]],
            fs.Stream[s.Dissection[V]]]
        ]
        ) -> fs.StreamResult[s.Dissection[Dict[K, V]]]:
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
        dissections: List[Tuple[s.Dissection[K], s.Dissection[V]]]
        ) -> s.Dissection[Dict[K, V]]:
        heads = [
            ( s.head(dissection[0]), s.head(dissection[1]) )
            for dissection in dissections
        ]
        tails = [
            ( s.tail(dissection[0]), s.tail(dissection[1]) )
            for dissection in dissections
        ]
        return _Dict(heads), fs.concat(
            partial(_shrink_size, 0, dissections),
            fs.concat(
                partial(_shrink_keys, 0, dissections, tails),
                partial(_shrink_values, 0, dissections, tails)
            )
        )
    def _impl(state: a.State) -> Sample[Dict[K, V]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        result: List[Tuple[s.Dissection[K], s.Dissection[V]]] = []
        for _ in range(size):
            state, key = key_generator(state)
            state, value = value_generator(state)
            result.append((key, value))
        return state, _dist(result)
    return _impl

def dict(
    key_generator: Generator[K],
    value_generator: Generator[V]
    ) -> Generator[Dict[K, V]]:
    """A generator for dicts over a given key type `K` and value type `V`.

    :param key_generator: A key generator from which dict keys are sampled.
    :type key_generator: `Generator[K]`
    :param value_generator: A value generator from which dict values are sampled.
    :type value_generator: `Generator[V]`

    :return: A generator of dicts over key type `K` and value type `V`.
    :rtype: `Generator[Dict[K, V]]`
    """
    def _impl(upper_bound: _Int) -> Generator[Dict[K, V]]:
        return bounded_dict(0, upper_bound, key_generator, value_generator)
    return bind(_impl, small_nat())

def map_dict(
    generators: _Dict[K, Generator[V]]
    ) -> Generator[_Dict[K, V]]:
    """Composes dicts of generators over given types `K` and `V`, resulting in a generator of dicts over the given types `K` and `V`.

    :param generators: A dict of value generators from which value dicts are sampled.
    :type generators: `Dict[K, Generator[V]]`

    :return: A generator of dicts over types `K` and `V`.
    :rtype: `Generator[Dict[K, V]]`
    """
    keys = _List(generators.keys())
    def _compose(*values: V) -> _Dict[K, V]:
        return {
            keys[index]: value
            for index, value in enumerate(values)
        }
    return map(_compose, *[ generators[key] for key in keys ])

def dict_insert(
    kvs_gen: Generator[_Dict[K, V]],
    key_gen: Generator[K],
    value_gen: Generator[V]
    ) -> Generator[_Dict[K, V]]:
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
    def _insert(kvs: _Dict[K, V], key: K, value: V) -> _Dict[K, V]:
        result = kvs.copy()
        result[key] = value
        return result
    return map(_insert, kvs_gen, key_gen, value_gen)

###############################################################################
# Sets
###############################################################################
def bounded_set(
    lower_bound: _Int,
    upper_bound: _Int,
    generator: Generator[T]
    ) -> Generator[Set[T]]:
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
        index: _Int,
        dissections: List[s.Dissection[T]]
        ) -> fs.StreamResult[s.Dissection[Set[T]]]:
        if index == len(dissections): raise StopIteration
        _index = index + 1
        _dissections = dissections.copy()
        del _dissections[index]
        return _dist(_dissections), partial(_shrink_size, _index, dissections)
    def _shrink_value(
        index: _Int,
        dissections: List[s.Dissection[T]],
        streams: List[fs.Stream[s.Dissection[T]]]
        ) -> fs.StreamResult[s.Dissection[Set[T]]]:
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
    def _dist(dissections: List[s.Dissection[T]]) -> s.Dissection[Set[T]]:
        heads = [ s.head(dissection) for dissection in dissections ]
        tails = [ s.tail(dissection) for dissection in dissections ]
        return _Set(heads), fs.concat(
            partial(_shrink_size, 0, dissections),
            partial(_shrink_value, 0, dissections, tails)
        )
    def _impl(state: a.State) -> Sample[Set[T]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        result: List[s.Dissection[T]] = []
        for _ in range(size):
            state, item = generator(state)
            result.append(item)
        return state, _dist(result)
    return _impl

def set(generator: Generator[T]) -> Generator[Set[T]]:
    """A generator for sets over a given type `T`.

    :param generator: A value generator from which set items are sampled.
    :type generator: `Generator[T]`

    :return: A generator of sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """
    def _impl(upper_bound: _Int) -> Generator[Set[T]]:
        return bounded_set(0, upper_bound, generator)
    return bind(_impl, small_nat())

def map_set(
    generators: _Set[Generator[T]]
    ) -> Generator[_Set[T]]:
    """Composes sets of generators over a given type `T`, resulting in a generator of sets over the given type `T`.

    :param generators: A set of value generators from which value sets are sampled.
    :type generators: `Set[Generator[T]]`

    :return: A generator of sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """
    return map(lambda values: _Set(_List(values)), *generators)

def set_add(
    items_gen: Generator[_Set[T]],
    item_gen: Generator[T]
    ) -> Generator[_Set[T]]:
    """Compose a set generator over a type `T` with a value generator of type `T`, resulting in a generator of sets over the given type `T`, where a value has been sampled from the later generator and guaranteed to have been added to the output sampled sets.

    :param items_gen: A generator from which sets are sampled.
    :type items_gen: `Generator[Set[T]]`
    :param item_gen: A generator from which values are sampled.
    :type item_gen: `Generator[T]`

    :return: A generator of output sets over type `T`.
    :rtype: `Generator[Set[T]]`
    """
    def _add(items: _Set[T], item: T) -> _Set[T]:
        result = items.copy()
        result.add(item)
        return result
    return map(_add, items_gen, item_gen)

###############################################################################
# Maybe
###############################################################################
def maybe(
    generator: Generator[T]
    ) -> Generator[m.Maybe[T]]:
    """A generator of maybe over a given type `T`.

    :param generator: A value generator to map maybe over.
    :type generator: `Generator[T]`

    :return: A generator of maybe over type `T`.
    :rtype: `Generator[minigun.maybe.Maybe[T]]`
    """
    def _something(value: T) -> m.Maybe[T]: return m.Something(value)
    def _impl(state: a.State) -> Sample[m.Maybe[T]]:
        state, p = a.probability(state)
        if p < 0.05: return state, s.singleton(m.Nothing())
        state, value = generator(state)
        _value = s.map(_something, value)
        return state, (s.head(_value), fs.map(
            lambda dissection: s.append(dissection, m.Nothing()),
            s.tail(_value)
        ))
    return _impl

###############################################################################
# Choice combinators
###############################################################################
def choice(*generators: Generator[T]) -> Generator[T]:
    """A generator of a type `T` composed of other generators of type `T`.

    :param generators: generators of type `T`.
    :type generators: `Tuple[Generator[T], ...]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    def _impl(index: _Int) -> Generator[T]: return generators[index]
    return bind(_impl, int_range(0, len(generators) - 1))

def weighted_choice(
    *weighted_generators : Tuple[_Int, Generator[T]]
    ) -> Generator[T]:
    """A generator of a type `T` composed of other weighted generators of type `T`.

    :param weighted_generators: Number of chances to sample from, with their corresponding generators of type `T`.
    :type weighted_generators: `Tuple[Tuple[int, Generator[T]], ...]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    weights, choices = _Map(_List, zip(*weighted_generators))
    def _impl(state: a.State) -> Sample[T]:
        state, generator = a.weighted_choice(state, weights, choices)
        return generator(state)
    return _impl

def one_of(
    values: List[T]
    ) -> Generator[T]:
    """A generator of a type `T` defined over a list of `T`, which will select one of the values of given list when sampled.

    :param values: A list of values of type `T`.
    :type values: `List[T]`

    :return: A generator of type `T`.
    :rtype: `Generator[T]`
    """
    def _select(index: _Int) -> T: return values[index]
    return map(_select, int_range(0, len(values) - 1))

def subset_of(
    values: Set[T]
    ) -> Generator[Set[T]]:
    """A generator of a type `T` defined over a list of `T`, which will select a subset of the values of given set when sampled.

    :param values: A set of values of type `T`.
    :type values: `Set[T]`

    :return: A set generator of type `T`.
    :rtype: `Generator[Set[T]]`
    """
    _values = _List(values)
    def _select(indices: Set[_Int]) -> Set[T]:
        return _Set([ _values[index] for index in indices ])
    count = len(_values)
    return map(_select, bounded_set(0, count, int_range(0, count - 1)))

###############################################################################
# Infer a generator
###############################################################################
def infer(T: type) -> m.Maybe[Generator[Any]]:
    """Infer a generator of type `T` for a given type `T`.

    :param T: A type to infer a generator of.
    :type T: `type`

    :return: A maybe of generator of type T.
    :rtype: `minigun.maybe.Maybe[Generator[T]]`
    """
    def _maybe(T: type) -> m.Maybe[Generator[Any]]:
        item_sampler = infer(m.get_domain(T))
        if isinstance(item_sampler, m.Nothing): return m.Nothing()
        return m.Something(maybe(item_sampler.value))
    def _tuple(T: type) -> m.Maybe[Generator[Any]]:
        item_samplers: List[Generator[Any]] = []
        for item_T in get_args(T):
            item_sampler = infer(item_T)
            if isinstance(item_sampler, m.Nothing): return m.Nothing()
            item_samplers.append(item_sampler.value)
        return m.Something(tuple(*item_samplers))
    def _list(T: type) -> m.Maybe[Generator[Any]]:
        item_sampler = infer(get_args(T)[0])
        if isinstance(item_sampler, m.Nothing): return m.Nothing()
        return m.Something(list(item_sampler.value))
    def _dict(T: type) -> m.Maybe[Generator[Any]]:
        key_sampler = infer(get_args(T)[0])
        if isinstance(key_sampler, m.Nothing): return m.Nothing()
        value_sampler = infer(get_args(T)[1])
        if isinstance(value_sampler, m.Nothing): return m.Nothing()
        return m.Something(dict(key_sampler.value, value_sampler.value))
    def _set(T: type) -> m.Maybe[Generator[Any]]:
        item_sampler = infer(get_args(T)[0])
        if isinstance(item_sampler, m.Nothing): return m.Nothing()
        return m.Something(set(item_sampler.value))
    if T == _Bool: return m.Something(bool())
    if T == _Int: return m.Something(int())
    if T == _Float: return m.Something(float())
    if T == _Str: return m.Something(str())
    if m.is_maybe(T): return _maybe(T)
    origin = get_origin(T)
    if origin != None:
        if origin == _Tuple: return _tuple(T)
        if origin == _List: return _list(T)
        if origin == _Dict: return _dict(T)
        if origin == _Set: return _set(T)
    return m.Nothing()