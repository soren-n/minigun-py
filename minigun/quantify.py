# External module dependencies
from typing import (
    cast,
    overload,
    get_args,
    Any,
    TypeVar,
    Callable,
    Hashable,
    Tuple,
    List,
    Dict
)
import math

# Internal module dependencies
from . import arbitrary as a
from . import domain as d
from . import maybe as m
from . import trim as t

###############################################################################
# Sampler
###############################################################################
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
D = TypeVar('D')

Sample = Tuple[a.State, d.Domain[A]]
Sampler = Callable[[a.State], Sample[A]]

def map(func : Callable[[A], B], sampler : Sampler[A]) -> Sampler[B]:
    def _impl(state : a.State) -> Sample[B]:
        state, case = sampler(state)
        return state, d.map(func, case)
    return _impl

def bind(func : Callable[[A], Sampler[B]], sampler : Sampler[A]) -> Sampler[B]:
    def _impl(state : a.State) -> Sample[B]:
        def _step(value : A) -> d.Domain[B]:
            nonlocal state
            state, result = func(value)(state)
            return result
        state, case = sampler(state)
        return state, d.bind(_step, case)
    return _impl

def sample(state : a.State, sampler : Sampler[A]) -> Tuple[a.State, A]:
    state, case = sampler(state)
    return state, case[0]

###############################################################################
# None
###############################################################################
def none() -> Sampler[None]:
    def _impl(state : a.State) -> Sample[None]:
        return state, d.singleton(None)
    return _impl

###############################################################################
# Boolean
###############################################################################
def boolean() -> Sampler[bool]:
    def _impl(state : a.State) -> Sample[bool]:
        case_false = d.singleton(False)
        state, outcome = a.boolean(state)
        if not outcome: return state, case_false
        return state, d.union(True, case_false)
    return _impl

###############################################################################
# Numbers
###############################################################################
def _small_natural(state : a.State) -> Sample[int]:
    state, prop = a.probability(state)
    state, result = a.natural(state, (
        10 if prop < 0.75 else
        100
    ))
    return state, d.unary(t.integer(0), result)
def small_natural() -> Sampler[int]: return _small_natural

def _natural(state : a.State) -> Sample[int]:
    state, prop = a.probability(state)
    state, result = a.natural(state, (
        10 if prop < 0.5 else
        100 if prop < 0.75 else
        1000 if prop < 0.95 else
        10000
    ))
    return state, d.unary(t.integer(0), result)
def natural() -> Sampler[int]: return _natural

def _big_natural(state : a.State) -> Sample[int]:
    state, prop = a.probability(state)
    if prop < 0.75: return _natural(state)
    state, result = a.natural(state, 1000000)
    return state, d.unary(t.integer(0), result)
def big_natural() -> Sampler[int]: return _big_natural

def _small_integer(state : a.State) -> Sample[int]:
    state, prop = a.probability(state)
    bound = (
        10 if prop < 0.75 else
        100
    )
    state, result = a.integer(state, -bound, bound)
    return state, d.unary(t.integer(0), result)
def small_integer() -> Sampler[int]: return _small_integer

def _integer(state : a.State) -> Sample[int]:
    state, prop = a.probability(state)
    bound = (
        10 if prop < 0.5 else
        100 if prop < 0.75 else
        1000 if prop < 0.95 else
        10000
    )
    state, result = a.integer(state, -bound, bound)
    return state, d.unary(t.integer(0), result)
def integer() -> Sampler[int]: return _integer

def _big_integer(state : a.State) -> Sample[int]:
    state, prop = a.probability(state)
    if prop < 0.75: return _integer(state)
    state, result = a.integer(state, -1000000, 1000000)
    return state, d.unary(t.integer(0), result)
def big_integer() -> Sampler[int]: return _big_integer

def _real(state : a.State) -> Sample[float]:
    state, exponent = a.real(state, -15.0, 15.0)
    state, sign = a.boolean(state)
    result = (1.0 if sign else -1.0) * math.exp(exponent)
    return state, d.binary(
        t.real_integer_part(0.0),
        t.real_fractional_part(0.0),
        result
    )
def real() -> Sampler[float]: return _real

def positive_real() -> Sampler[float]:
    def _impl(value : float) -> float:
        if value > 0.0: return value
        return -1.0 * value
    return map(_impl, real())

def negative_real() -> Sampler[float]:
    def _impl(value : float) -> float:
        if value < 0.0: return value
        return -1.0 * value
    return map(_impl, real())

###############################################################################
# Ranges
###############################################################################
def integer_range(
    lower_bound : int,
    upper_bound : int
    ) -> Sampler[int]:
    def _impl(state : a.State) -> Sample[int]:
        assert lower_bound <= upper_bound
        state, result = a.integer(state, lower_bound, upper_bound)
        goal = max(lower_bound, min(0, upper_bound))
        return state, d.unary(t.integer(goal), result)
    return _impl

###############################################################################
# Strings
###############################################################################
def string() -> Sampler[str]:
    def _impl(state : a.State) -> Sample[str]:
        ...
    return _impl

def word() -> Sampler[str]:
    def _impl(state : a.State) -> Sample[str]:
        ...
    return _impl

###############################################################################
# Maybe
###############################################################################
def maybe_of(
    value_sampler : Sampler[A]
    ) -> Sampler[m.Maybe[A]]:
    def _impl(state : a.State) -> Sample[m.Maybe[A]]:
        state, outcome = a.boolean(state)
        if outcome: return state, d.singleton(m.Nothing())
        state, value = value_sampler(state)
        return state, d.maybe(value)
    return _impl

###############################################################################
# Tuples
###############################################################################
@overload
def tuple_of() -> Sampler[Tuple[()]]: ...
@overload
def tuple_of(
    a_sampler: Sampler[A]
    ) -> Sampler[Tuple[A]]: ...
@overload
def tuple_of(
    a_sampler: Sampler[A],
    b_sampler: Sampler[B]
    ) -> Sampler[Tuple[A, B]]: ...
@overload
def tuple_of(
    a_sampler: Sampler[A],
    b_sampler: Sampler[B],
    c_sampler: Sampler[C]
    ) -> Sampler[Tuple[A, B, C]]: ...
@overload
def tuple_of(
    a_sampler: Sampler[A],
    b_sampler: Sampler[B],
    c_sampler: Sampler[C],
    d_sampler: Sampler[D]
    ) -> Sampler[Tuple[A, B, C, D]]: ...
def tuple_of(*samplers: Sampler[Any]) -> Sampler[Tuple[Any, ...]]:
    def _tuple(*values : Any) -> Tuple[Any, ...]: return tuple(values)
    def _impl(state : a.State) -> Sample[Tuple[Any, ...]]:
        values : List[Any] = []
        for sampler in samplers:
            state, value = sampler(state)
            values.append(value)
        return state, d.map(_tuple, *values)
    return _impl

###############################################################################
# List
###############################################################################
def bounded_list_of(
    size_sampler : Sampler[int],
    item_sampler : Sampler[A]
    ) -> Sampler[List[A]]:
    def _impl(state : a.State) -> Sample[List[A]]:
        def _append(x : A, xs : List[A]) -> List[A]:
            xs1 = xs.copy()
            xs1.append(x)
            return xs1
        def _loop(size : int) -> d.Domain[List[A]]:
            nonlocal state
            result = d.singleton(cast(List[A], []))
            for _ in range(size):
                state, item = item_sampler(state)
                result = d.map(_append, item, result)
            return result
        state, size = size_sampler(state)
        return state, d.bind(_loop, size)
    return _impl

def list_of(item_sampler : Sampler[A]) -> Sampler[List[A]]:
    return bounded_list_of(small_natural(), item_sampler)

def unique_list_of(
    item_sampler : Sampler[Hashable]
    ) -> Sampler[List[Hashable]]:
    def _impl(items : List[Hashable]) -> List[Hashable]:
        return list(set(items))
    return map(_impl, list_of(item_sampler))

###############################################################################
# Dictionary
###############################################################################
K = TypeVar('K')
V = TypeVar('V')
def bounded_dict_of(
    size_sampler : Sampler[int],
    key_sampler : Sampler[K],
    value_sampler : Sampler[V]
    ) -> Sampler[Dict[K, V]]:
    def _impl(state : a.State) -> Sample[Dict[K, V]]:
        def _insert(kv : Tuple[K, V], kvs : Dict[K, V]) -> Dict[K, V]:
            kvs1 = kvs.copy()
            kvs1[kv[0]] = kv[1]
            return kvs1
        def _loop(size : int) -> d.Domain[Dict[K, V]]:
            nonlocal state
            result = d.singleton(cast(Dict[K, V], {}))
            for _ in range(size):
                state, key_value = tuple_of(key_sampler, value_sampler)(state)
                result = d.map(_insert, key_value, result)
            return result
        state, size = size_sampler(state)
        return state, d.bind(_loop, size)
    return _impl

def dict_of(
    key_sampler : Sampler[K],
    value_sampler : Sampler[V]
    ) -> Sampler[Dict[K, V]]:
    return bounded_dict_of(small_natural(), key_sampler, value_sampler)

###############################################################################
# Combinators
###############################################################################
def one_of(cases : List[Sampler[A]]) -> Sampler[A]:
    def _impl(index : int) -> Sampler[A]: return cases[index]
    return bind(_impl, integer_range(0, len(cases) - 1))

def weighted_one_of(cases : List[Tuple[int, Sampler[A]]]) -> Sampler[A]:
    weights, choices = cast(Tuple[List[int], List[Sampler[A]]], zip(*cases))
    def _impl(state : a.State) -> Sample[A]:
        state, sampler = a.choose(state, choices, weights)
        return sampler(state)
    return _impl

###############################################################################
# Infer a sampler
###############################################################################
def infer(T : type) -> m.Maybe[Sampler[Any]]:
    def _tuple(T : type) -> m.Maybe[Sampler[Any]]:
        item_samplers : List[Sampler[Any]] = []
        for item_T in get_args(T):
            item_sampler = infer(item_T)
            if isinstance(item_sampler, m.Nothing): return m.Nothing()
            item_samplers.append(item_sampler.value)
        return m.Something(tuple_of(*item_samplers))
    def _list(T : type) -> m.Maybe[Sampler[Any]]:
        item_sampler = infer(get_args(T)[0])
        if isinstance(item_sampler, m.Nothing): return m.Nothing()
        return m.Something(list_of(item_sampler.value))
    def _dict(T : type) -> m.Maybe[Sampler[Any]]:
        key_sampler = infer(get_args(T)[0])
        if isinstance(key_sampler, m.Nothing): return m.Nothing()
        value_sampler = infer(get_args(T)[1])
        if isinstance(value_sampler, m.Nothing): return m.Nothing()
        return m.Something(dict_of(key_sampler.value, value_sampler.value))
    if T is int: return m.Something(integer())
    if T is float: return m.Something(real())
    if T is str: return m.Something(string())
    if '__origin__' in T.__dict__:
        if T.__dict__['__origin__'] is tuple: return _tuple(T)
        if T.__dict__['__origin__'] is list: return _list(T)
        if T.__dict__['__origin__'] is dict: return _dict(T)
    return m.Nothing()