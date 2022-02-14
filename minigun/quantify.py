# External module dependencies
from typing import (
    cast,
    overload,
    get_origin,
    get_args,
    Any,
    TypeVar,
    ParamSpec,
    Callable,
    Optional,
    Tuple,
    List,
    Dict
)
import string
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

P = ParamSpec('P')
R = TypeVar('R')

Sample = Tuple[a.State, d.Domain[A]]
Sampler = Callable[[a.State], Sample[A]]

@overload
def map(
    func : Callable[[], R]
    ) -> Sampler[R]: ...
@overload
def map(
    func : Callable[[A], R],
    a_sampler : Sampler[A]
    ) -> Sampler[R]: ...
@overload
def map(
    func : Callable[[A, B], R],
    a_sampler : Sampler[A],
    b_sampler : Sampler[B]
    ) -> Sampler[R]: ...
@overload
def map(
    func : Callable[[A, B, C], R],
    a_sampler : Sampler[A],
    b_sampler : Sampler[B],
    c_sampler : Sampler[C]
    ) -> Sampler[R]: ...
@overload
def map(
    func : Callable[[A, B, C, D], R],
    a_sampler : Sampler[A],
    b_sampler : Sampler[B],
    c_sampler : Sampler[C],
    d_sampler : Sampler[D]
    ) -> Sampler[R]: ...
def map(
    func : Callable[P, R],
    *samplers : Sampler[Any]
    ) -> Sampler[R]:
    def _impl(state : a.State) -> Sample[R]:
        cases : List[Any] = []
        for sampler in samplers:
            state, case = sampler(state)
            cases.append(case)
        return state, d.map(func, *cases)
    return _impl

@overload
def bind(
    func : Callable[[], Sampler[R]]
    ) -> Sampler[R]: ...
@overload
def bind(
    func : Callable[[A], Sampler[R]],
    a_sampler : Sampler[A]
    ) -> Sampler[R]: ...
@overload
def bind(
    func : Callable[[A, B], Sampler[R]],
    a_sampler : Sampler[A],
    b_sampler : Sampler[B]
    ) -> Sampler[R]: ...
@overload
def bind(
    func : Callable[[A, B, C], Sampler[R]],
    a_sampler : Sampler[A],
    b_sampler : Sampler[B],
    c_sampler : Sampler[C]
    ) -> Sampler[R]: ...
@overload
def bind(
    func : Callable[[A, B, C, D], Sampler[R]],
    a_sampler : Sampler[A],
    b_sampler : Sampler[B],
    c_sampler : Sampler[C],
    d_sampler : Sampler[D]
    ) -> Sampler[R]: ...
def bind(
    func : Callable[P, Sampler[R]],
    *samplers : Sampler[Any]
    ) -> Sampler[R]:
    def _impl(state : a.State) -> Sample[R]:
        def _step(*values : Any) -> d.Domain[R]:
            nonlocal state
            state, result = func(*values)(state)
            return result
        cases : List[Any] = []
        for sampler in samplers:
            state, case = sampler(state)
            cases.append(case)
        return state, d.bind(_step, *cases)
    return _impl

def sample(state : a.State, sampler : Sampler[A]) -> Tuple[a.State, A]:
    state, case = sampler(state)
    return state, case[0]

###############################################################################
# Constant
###############################################################################
def constant(value : A) -> Sampler[A]:
    def _impl(state : a.State) -> Sample[A]:
        return state, d.singleton(value)
    return _impl

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
def alphabet(sigma : str) -> Sampler[str]:
    def _impl(state : a.State) -> Sample[str]:
        state, index = a.integer(state, 0, len(sigma) - 1)
        return state, d.singleton(sigma[index])
    return _impl

def bounded_string_of(
    lower_bound : int,
    upper_bound : int,
    alphabet : str
    ) -> Sampler[str]:
    assert lower_bound >= 0
    assert lower_bound <= upper_bound
    def _impl(state : a.State) -> Sample[str]:
        result = ''
        for _ in range(upper_bound - lower_bound):
            state, index = a.integer(state, 0, len(alphabet) - 1)
            result += alphabet[index]
        return state, d.unary(t.string(), result)
    return _impl

def text() -> Sampler[str]:
    def _impl(upper_bound : int) -> Sampler[str]:
        return bounded_string_of(0, upper_bound, string.printable)
    return bind(_impl, small_natural())

def word() -> Sampler[str]:
    def _impl(upper_bound : int) -> Sampler[str]:
        return bounded_string_of(0, upper_bound, string.ascii_letters)
    return bind(_impl, small_natural())

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
    lower_bound : int,
    upper_bound : int,
    item_sampler : Sampler[A],
    unique : bool = False,
    ordering : Optional[Callable[[A], int]] = None
    ) -> Sampler[List[A]]:
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound
    def _impl(state : a.State) -> Sample[List[A]]:
        def _append(x : A, xs : List[A]) -> List[A]:
            xs1 = xs.copy()
            xs1.append(x)
            return xs1
        def _unique(xs : List[A]) -> List[A]:
            return list(set(xs))
        def _sort(xs : List[A]) -> List[A]:
            if ordering == None: return xs
            xs1 = xs.copy()
            xs1.sort(key=ordering)
            return xs1
        result = d.singleton(cast(List[A], []))
        for _ in range(upper_bound - lower_bound):
            state, item = item_sampler(state)
            result = d.map(_append, item, result)
        if unique: result = d.map(_unique, result)
        return state, d.map(_sort, result)
    return _impl

def list_of(
    item_sampler : Sampler[A],
    unique : bool = False,
    ordering : Optional[Callable[[A], int]] = None
    ) -> Sampler[List[A]]:
    def _impl(upper_bound : int) -> Sampler[List[A]]:
        return bounded_list_of(0, upper_bound, item_sampler, unique, ordering)
    return bind(_impl, small_natural())

###############################################################################
# Dictionary
###############################################################################
K = TypeVar('K')
V = TypeVar('V')
def bounded_dict_of(
    lower_bound : int,
    upper_bound : int,
    key_sampler : Sampler[K],
    value_sampler : Sampler[V]
    ) -> Sampler[Dict[K, V]]:
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound
    def _impl(state : a.State) -> Sample[Dict[K, V]]:
        def _insert(kv : Tuple[K, V], kvs : Dict[K, V]) -> Dict[K, V]:
            kvs1 = kvs.copy()
            kvs1[kv[0]] = kv[1]
            return kvs1
        result = d.singleton(cast(Dict[K, V], {}))
        for _ in range(upper_bound - lower_bound):
            state, key_value = tuple_of(key_sampler, value_sampler)(state)
            result = d.map(_insert, key_value, result)
        return state, result
    return _impl

def dict_of(
    key_sampler : Sampler[K],
    value_sampler : Sampler[V]
    ) -> Sampler[Dict[K, V]]:
    def _impl(upper_bound : int) -> Sampler[Dict[K, V]]:
        return bounded_dict_of(0, upper_bound, key_sampler, value_sampler)
    return bind(_impl, small_natural())

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
    if T == int: return m.Something(integer())
    if T == float: return m.Something(real())
    if T == str: return m.Something(text())
    origin = get_origin(T)
    if origin != None:
        if origin == tuple: return _tuple(T)
        if origin == list: return _list(T)
        if origin == dict: return _dict(T)
    return m.Nothing()