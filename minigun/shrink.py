# External module dependencies
from typing import (
    cast,
    Callable,
    Any
)
from returns.maybe import (
    Maybe,
    Nothing,
    Some
)
import math

# Internal module dependencies
from . import stream as fs

###############################################################################
# Localizing builtins
###############################################################################
from builtins import (
    bool as _bool,
    int as _int,
    float as _float,
    str as _str,
    tuple as _tuple
)

###############################################################################
# Shrink state
###############################################################################

#: Dissection datatype defined over a type parameter `T`.
type Dissection[T] = _tuple[T, fs.Stream['Dissection[T]']]

#: Shrinker datatype defined over a type parameter `T.
type Shrinker[T] = Callable[[T], Dissection[T]]

def head[T](dissection: Dissection[T]) -> T:
    """Get dissection head.

    :param dissection: A dissection to get the head from.
    :type dissection: `Dissection[T]`

    :return: The head of given dissection.
    :rtype: `T`
    """
    return dissection[0]

def tail[T](dissection: Dissection[T]) -> fs.Stream[Dissection[T]]:
    """Get dissection tail.

    :param dissection: A dissection to get the tail from.
    :type dissection: `Dissection[T]`

    :return: The tail of given dissection.
    :rtype: `minigun.stream.Stream[Dissection[T]]`
    """
    return dissection[1]

def map[**P, R](
    func: Callable[P, R],
    *dissections: Dissection[Any]
    ) -> Dissection[R]:
    """A variadic map function of given input dissections over types `A`, `B`, etc. to an output dissection over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param dissections: Input dissections over types `A`, `B`, etc. to map from.
    :type dissections: `tuple[Dissection[A], Dissection[B], ...]`

    :return: A mapped output dissection.
    :rtype: `Dissection[R]`
    """
    def _apply(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    def _combine(
        input_dissections: list[Dissection[Any]]
        ) -> Dissection[R]:
        output_heads = [ head(dissection) for dissection in input_dissections ]
        return _apply(*output_heads), _cartesian(input_dissections)
    def _cartesian(
        input_dissections: list[Dissection[Any]]
        ) -> fs.Stream[Dissection[R]]:
        past = len(input_dissections)
        tails = [ tail(dissection) for dissection in input_dissections ]
        def _shift_horizontal(
            index: _int
            ) -> fs.Stream[Dissection[R]]:
            if past <= index: return fs.empty()
            def _shift_vertical(
                next_dissection: Dissection[Any]
                ) -> Dissection[R]:
                next_dissections = input_dissections.copy()
                next_dissections[index] = next_dissection
                return _combine(next_dissections)
            return fs.braid(
                cast(
                    fs.Stream[Dissection[R]],
                    fs.map(_shift_vertical, tails[index])
                ),
                _shift_horizontal(index + 1)
            )
        return _shift_horizontal(0)
    return _combine(list(dissections))

def bind[**P, R](
    func: Callable[P, Dissection[R]],
    *dissections: Dissection[Any]
    ) -> Dissection[R]:
    """A variadic bind function of given input dissections over types `A`, `B`, etc. to an output dissection over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output dissection of type `R`.
    :type func: `A x B x ... -> Dissection[R]`
    :param dissections: Input dissections over types `A`, `B`, etc. to map from.
    :type dissections: `tuple[Dissection[A], Dissection[B], ...]`

    :return: A bound output dissection.
    :rtype: `Dissection[R]`
    """
    def _apply(*args: P.args, **kwargs: P.kwargs) -> Dissection[R]:
        return func(*args, **kwargs)
    def _combine(
        input_dissections: list[Dissection[Any]]
        ) -> Dissection[R]:
        output_heads = [ head(dissection) for dissection in input_dissections ]
        output_head, output_tail = _apply(*output_heads)
        return output_head, fs.concat(
            output_tail, _cartesian(input_dissections)
        )
    def _cartesian(
        input_dissections: list[Dissection[Any]]
        ) -> fs.Stream[Dissection[R]]:
        past = len(input_dissections)
        tails = [ tail(dissection) for dissection in input_dissections ]
        def _shift_horizontal(
            index: _int
            ) -> fs.Stream[Dissection[R]]:
            if past <= index: return fs.empty()
            def _shift_vertical(
                next_dissection: Dissection[Any]
                ) -> Dissection[R]:
                next_dissections = input_dissections.copy()
                next_dissections[index] = next_dissection
                return _combine(next_dissections)
            return fs.braid(
                cast(
                    fs.Stream[Dissection[R]],
                    fs.map(_shift_vertical, tails[index])
                ),
                _shift_horizontal(index + 1)
            )
        return _shift_horizontal(0)
    return _combine(list(dissections))

def filter[T](
    predicate: Callable[[T], _bool],
    dissection: Dissection[T]
    ) -> Maybe[Dissection[T]]:
    """Filter a dissection of type `T`.

    :param predicate: A predicate on type `T`.
    :type predicate: `A -> bool`
    :param dissection: A dissection of type `T` to be filtered.
    :type dissection: `Dissection[T]`

    :return: A dissection of type `T`.
    :rtype: `Dissection[T]`
    """
    def _predicate(dissection: Dissection[T]) -> _bool:
        return predicate(head(dissection))

    return fs.peek(cast(
        fs.Stream[Dissection[T]],
        fs.filter(_predicate, fs.singleton(dissection))
    ))

def concat[T](
    left: Dissection[T],
    right: Dissection[T]
    ) -> Dissection[T]:
    """Concatenation of two dissects over type `T`.

    :param left: The first dissection to take the concatenation of.
    :type left: `Dissection[T]`
    :param right: The second dissection to take the concatenation of.
    :type right: `Dissection[T]`

    :return: A dissection that is the concatenation of the two give dissects.
    :rtype: `Dissection[T]`
    """
    return left[0], fs.append(left[1], right)

def prepend[T](value: T, dissection: Dissection[T]) -> Dissection[T]:
    """Prepend a value to a dissection.

    :param value: The value to be prepended.
    :type value: `T`
    :param dissection: The dissection to be prepended to.
    :type dissection: `Dissection[T]`

    :return: The updated dissection containing the given value.
    :rtype: `Dissection[T]`
    """
    return value, fs.singleton(dissection)

def append[T](dissection: Dissection[T], value: T) -> Dissection[T]:
    """Append a value to a dissection.

    :param dissection: The dissection to be appended to.
    :type dissection: `Dissection[T]`
    :param value: The value to be appended.
    :type value: `T`

    :return: The updated dissection containing the given value.
    :rtype: `Dissection[T]`
    """
    return dissection[0], fs.append(dissection[1], singleton(value))

def singleton[T](value: T) -> Dissection[T]:
    """A singleton dissection containing a single unshrinkable value.

    :param value: An unshrinkable value.
    :type value: `T`

    :return: A dissection over the type `T`.
    :rtype: `Dissection[T]`
    """
    return value, cast(fs.Stream[Dissection[T]], fs.empty())

###############################################################################
# Trimmer
###############################################################################

#: A timmer over a type `T`
type Trimmer[T] = Callable[[T], fs.Stream[T]]

###############################################################################
# Unfold trimmers
###############################################################################
def unfold[T](
    value: T,
    *trimmers: Trimmer[T]
    ) -> Dissection[T]:
    """Define a dissection of an n-ary dimensional trimmed iteration of a given value.

    :param value: The initial value to do a trimmed iteration of.
    :type value: `T`
    :param trimmers: The given trimmers for values of type `T`.
    :type trimmers: `Trimmer[T]`

    :return: A dissection of trimmed interations over the given value.
    :rtype: `Dissection[T]`
    """
    _trimmers: list[Trimmer[T]] = list(trimmers)
    dissections: list[Dissection[T]] = list()
    for index, trimmer in enumerate(trimmers):
        other_timmers = _trimmers[:index] + _trimmers[index+1:]
        maybe_shrunk, shrunk_stream = fs.next(trimmer(value))
        match maybe_shrunk:
            case Maybe.empty: continue
            case Some(shrunk):
                dissections.append((shrunk, fs.map(
                    lambda shrunk_more: unfold(
                        shrunk_more,
                        *other_timmers
                    ),
                    shrunk_stream
                )))
            case _: assert False, 'Invariant'
    return value, fs.from_list(dissections)

###############################################################################
# Booleans
###############################################################################
def bool() -> Shrinker[_bool]:
    def _trim(initial: _bool) -> fs.Stream[_bool]:
        return fs.singleton(not initial)
    def _impl(value: _bool) -> Dissection[_bool]:
        return unfold(value, _trim)
    return _impl

###############################################################################
# Numbers
###############################################################################
def int(target: _int) -> Shrinker[_int]:
    """A shrinker for integers which shrinks towards a given target.

    :param target: A target value to shrink towards.
    :type target: `int`

    :return: A shrinker of int.
    :rtype: `Shrinker[T]`
    """
    def _trim(initial: _int) -> fs.Stream[_int]:
        def _towards(
            state: tuple[_int, _int]
            ) -> Maybe[tuple[_int, tuple[_int, _int]]]:
            value, current = state
            if current == value: return Nothing
            _value = current + _int((value - current) / 2)
            return Some((_value, (_value, current)))
        return fs.unfold(_towards, (initial, target))
    def _impl(value: _int) -> Dissection[_int]:
        return unfold(value, _trim)
    return _impl

def float(target: _float) -> Shrinker[_float]:
    """A shrinker for floats which takes a target to shrink towards.

    :param target: A target value to shrink towards.
    :type target: `float`

    :return: A shrinker of float.
    :rtype: `Shrinker[float]`
    """
    def _trim_integer_part(initial: _float) -> fs.Stream[_float]:
        def _towards(
            state: tuple[_float, _int]
            ) -> Maybe[tuple[_float, tuple[_float, _int]]]:
            value, current = state
            value_f, value_i = math.modf(value)
            if current == _int(value_i): return Nothing
            _value = current + value_f + _int((value_i - current) / 2)
            return Some((_value, (_value, current)))
        return fs.unfold(_towards, (initial, _int(target)))
    def _trim_fractional_part(initial: _float) -> fs.Stream[_float]:
        def _towards(
            state: tuple[_int, _float, _float]
            ) -> Maybe[tuple[_float, tuple[_int, _float, _float]]]:
            count, value, current = state
            value_f, value_i = math.modf(value)
            if count == 0: return Nothing
            if current == value_f: return Nothing
            _value = value_i + current + ((value_f - current) / 2)
            return Some((_value, (count - 1, _value, current)))
        return fs.unfold(_towards, (10, initial, math.modf(target)[0]))
    def _impl(value: _float) -> Dissection[_float]:
        return unfold(
            value,
            _trim_integer_part,
            _trim_fractional_part
        )
    return _impl

###############################################################################
# String
###############################################################################
def str() -> Shrinker[_str]:
    """A shrinker for strings.

    :return: A shrinker of str.
    :rtype: `Shrinker[str]`
    """
    def _trim(initial: _str) -> fs.Stream[_str]:
        past = len(initial)
        def _towards(index: _int) -> Maybe[tuple[_str, _int]]:
            if index == past: return Nothing
            _value = initial[:index] + initial[index + 1:]
            return Some((_value, index + 1))
        return fs.unfold(_towards, 0)
    def _impl(value: _str) -> Dissection[_str]:
        return unfold(value, _trim)
    return _impl