# External module dependencies
from functools import partial
from typing import (
    cast,
    overload,
    Any,
    TypeVar,
    ParamSpec,
    Callable,
    Tuple
)
import math

# Internal module dependencies
from . import maybe as m
from . import stream as fs

###############################################################################
# Localizing intrinsics
###############################################################################
_Int = int
_Float = float
_Str = str

###############################################################################
# Shrink state
###############################################################################
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
D = TypeVar('D')

P = ParamSpec('P')
R = TypeVar('R')

#: Dissection datatype defined over a type parameter `A`.
Dissection = Tuple[A, fs.Stream['Dissection[A]']]

#: Shrinker datatype defined over a type parameter `A.
Shrinker = Callable[[A], Dissection[A]]

def head(dissection : Dissection[A]) -> A:
    """Get dissection head.

    :param dissection: A dissection to get the head from.
    :type dissection: `Dissection[A]`

    :return: The head of given dissection.
    :rtype: `A`
    """
    return dissection[0]

def tail(dissection : Dissection[A]) -> fs.Stream[Dissection[A]]:
    """Get dissection tail.

    :param dissection: A dissection to get the tail from.
    :type dissection: `Dissection[A]`

    :return: The tail of given dissection.
    :rtype: `minigun.stream.Stream[Dissection[A]]`
    """
    return dissection[1]

@overload
def map(
    func : Callable[[], R]
    ) -> Dissection[R]: ...
@overload
def map(
    func : Callable[[A], R],
    a_dissection : Dissection[A]
    ) -> Dissection[R]: ...
@overload
def map(
    func : Callable[[A, B], R],
    a_dissection : Dissection[A],
    b_dissection : Dissection[B]
    ) -> Dissection[R]: ...
@overload
def map(
    func : Callable[[A, B, C], R],
    a_dissection : Dissection[A],
    b_dissection : Dissection[B],
    c_dissection : Dissection[C]
    ) -> Dissection[R]: ...
@overload
def map(
    func : Callable[[A, B, C, D], R],
    a_dissection : Dissection[A],
    b_dissection : Dissection[B],
    c_dissection : Dissection[C],
    d_dissection : Dissection[D]
    ) -> Dissection[R]: ...
def map(
    func : Callable[P, R],
    *dissections : Dissection[Any]
    ) -> Dissection[R]:
    """A variadic map function of given input dissections over types `A`, `B`, etc. to an output dissection over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param dissections: Input dissections over types `A`, `B`, etc. to map from.
    :type dissections: `Tuple[Dissection[A], Dissection[B], ...]`

    :return: A mapped output dissection.
    :rtype: `Dissection[R]`
    """
    def _map(*dissections : Dissection[Any]) -> Dissection[R]:
        return map(func, *dissections)
    heads = [ head(dissection) for dissection in dissections ]
    tails = [ tail(dissection) for dissection in dissections ]
    return func(*heads), fs.map(_map, *tails)

@overload
def bind(
    func : Callable[[], Dissection[R]]
    ) -> Dissection[R]: ...
@overload
def bind(
    func : Callable[[A], Dissection[R]],
    a_dissection : Dissection[A]
    ) -> Dissection[R]: ...
@overload
def bind(
    func : Callable[[A, B], Dissection[R]],
    a_dissection : Dissection[A],
    b_dissection : Dissection[B]
    ) -> Dissection[R]: ...
@overload
def bind(
    func : Callable[[A, B, C], Dissection[R]],
    a_dissection : Dissection[A],
    b_dissection : Dissection[B],
    c_dissection : Dissection[C]
    ) -> Dissection[R]: ...
@overload
def bind(
    func : Callable[[A, B, C, D], Dissection[R]],
    a_dissection : Dissection[A],
    b_dissection : Dissection[B],
    c_dissection : Dissection[C],
    d_dissection : Dissection[D]
    ) -> Dissection[R]: ...
def bind(
    func : Callable[P, Dissection[R]],
    *dissections : Dissection[Any]
    ) -> Dissection[R]:
    """A variadic bind function of given input dissections over types `A`, `B`, etc. to an output dissection over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output dissection of type `R`.
    :type func: `A x B x ... -> Dissection[R]`
    :param dissections: Input dissections over types `A`, `B`, etc. to map from.
    :type dissections: `Tuple[Dissection[A], Dissection[B], ...]`

    :return: A bound output dissection.
    :rtype: `Dissection[R]`
    """
    def _bind(*dissections : Dissection[Any]) -> Dissection[R]:
        return bind(func, *dissections)
    heads = [ head(dissection) for dissection in dissections ]
    tails = [ tail(dissection) for dissection in dissections ]
    result_head, result_tail = func(*heads)
    return result_head, fs.concat(
        fs.map(_bind, *tails),
        result_tail
    )

def concat(
    left : Dissection[A],
    right : Dissection[A]
    ) -> Dissection[A]:
    """Concatenation of two dissects over type `A`.

    :param left: The first dissection to take the concatenation of.
    :type left: `Dissection[A]`
    :param right: The second dissection to take the concatenation of.
    :type right: `Dissection[A]`

    :return: A dissection that is the concatenation of the two give dissects.
    :rtype: `Dissection[A]`
    """
    return left[0], fs.append(left[1], right)

def prepend(value : A, dissection : Dissection[A]) -> Dissection[A]:
    """Prepend a value to a dissection.

    :param value: The value to be prepended.
    :type value: `A`
    :param dissection: The dissection to be prepended to.
    :type dissection: `Dissection[A]`

    :return: The updated dissection containing the given value.
    :rtype: `Dissection[A]`
    """
    return value, fs.singleton(dissection)

def append(dissection : Dissection[A], value : A) -> Dissection[A]:
    """Append a value to a dissection.

    :param dissection: The dissection to be appended to.
    :type dissection: `Dissection[A]`
    :param value: The value to be appended.
    :type value: `A`

    :return: The updated dissection containing the given value.
    :rtype: `Dissection[A]`
    """
    return dissection[0], fs.append(dissection[1], singleton(value))

def singleton(value : A) -> Dissection[A]:
    """A singleton dissection containing a single unshrinkable value.

    :param value: An unshrinkable value.
    :type value: `A`

    :return: A dissection over the type `A`.
    :rtype: `Dissection[A]`
    """
    return value, cast(fs.Stream[Dissection[A]], fs.empty())

###############################################################################
# Trimmer
###############################################################################

#: A timmer over a type `A`
Trimmer = Callable[[A], fs.Stream[A]]

###############################################################################
# Unfold trimmers
###############################################################################
def unfold(
    value : A,
    *trimmers : Trimmer[A]
    ) -> Dissection[A]:
    """Define a dissection of an n-ary dimensional trimmed iteration of a given value.

    :param value: The initial value to do a trimmed iteration of.
    :type value: `A`
    :param trimmers: The given trimmers for values of type `A`.
    :type trimmers: `Trimmer[A]`

    :return: A dissection of trimmed interations over the given value.
    :rtype: `Dissection[A]`
    """
    if len(trimmers) == 0:
        return value, cast(fs.Stream[Dissection[A]], fs.empty())
    trim, remain = trimmers[-1], trimmers[:-1]
    return value, fs.map(lambda value: unfold(value, *remain), trim(value))

###############################################################################
# Numbers
###############################################################################
def int(target : _Int) -> Shrinker[_Int]:
    """A shrinker for integers which shrinks towards a given target.

    :param target: A target value to shrink towards.
    :type target: `int`

    :return: A shrinker of int.
    :rtype: `Shrinker[A]`
    """
    def _trim(initial : _Int) -> fs.Stream[_Int]:
        def _towards(
            state : Tuple[_Int, _Int]
            ) -> m.Maybe[Tuple[_Int, Tuple[_Int, _Int]]]:
            value, current = state
            if current == value: return m.Nothing()
            _value = current + _Int((value - current) / 2)
            return m.Something((_value, (_value, current)))
        return fs.unfold(_towards, (initial, target))
    def _impl(value : _Int) -> Dissection[_Int]:
        return unfold(value, _trim)
    return _impl

def float(target : _Float) -> Shrinker[_Float]:
    """A shrinker for floats which takes a target to shrink towards.

    :param target: A target value to shrink towards.
    :type target: `float`

    :return: A shrinker of float.
    :rtype: `Shrinker[float]`
    """
    def _trim_integer_part(initial : _Float) -> fs.Stream[_Float]:
        def _towards(
            state : Tuple[_Float, _Int]
            ) -> m.Maybe[Tuple[_Float, Tuple[_Float, _Int]]]:
            value, current = state
            value_f, value_i = math.modf(value)
            if current == _Int(value_i): return m.Nothing()
            _value = current + value_f + _Int((value_i - current) / 2)
            return m.Something((_value, (_value, current)))
        return fs.unfold(_towards, (initial, _Int(target)))
    def _trim_fractional_part(initial : _Float) -> fs.Stream[_Float]:
        def _towards(
            state : Tuple[_Int, _Float, _Float]
            ) -> m.Maybe[Tuple[_Float, Tuple[_Int, _Float, _Float]]]:
            count, value, current = state
            value_f, value_i = math.modf(value)
            if count == 0: return m.Nothing()
            if current == value_f: return m.Nothing()
            _value = value_i + current + ((value_f - current) / 2)
            return m.Something((_value, (count - 1, _value, current)))
        return fs.unfold(_towards, (10, initial, math.modf(target)[0]))
    def _impl(value : _Float) -> Dissection[_Float]:
        return unfold(
            value,
            _trim_integer_part,
            _trim_fractional_part
        )
    return _impl

###############################################################################
# String
###############################################################################
def str() -> Shrinker[_Str]:
    """A shrinker for strings.

    :return: A shrinker of str.
    :rtype: `Shrinker[str]`
    """
    def _trim(initial : _Str) -> fs.Stream[_Str]:
        past = len(initial)
        def _towards(index : _Int) -> m.Maybe[Tuple[_Str, _Int]]:
            if index == past: return m.Nothing()
            _value = initial[:index] + initial[index + 1:]
            return m.Something((_value, index + 1))
        return fs.unfold(_towards, 0)
    def _impl(value : _Str) -> Dissection[_Str]:
        return unfold(value, _trim)
    return _impl