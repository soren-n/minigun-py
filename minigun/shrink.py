"""
Shrinking Strategies and Algorithms

This module implements the shrinking system that finds minimal counterexamples
when properties fail. It provides dissection trees that represent all possible
ways to shrink a value while preserving the failure condition.

Architecture:
    - Dissection[T]: Tree structure representing value and shrinking options
    - Trimmer[T]: Function producing stream of smaller values
    - unfold(): Create dissection from multiple trimming strategies

Built-in Shrinking:
    - Primitives: int, float, bool shrinking towards zero/false
    - Combinators: map for custom data structure shrinking

The shrinking system is integrated with generators to automatically provide
minimal counterexamples without additional user configuration.
"""

# External module dependencies
import math

###############################################################################
# Localizing builtins
###############################################################################
from builtins import bool as _bool
from builtins import float as _float
from builtins import int as _int
from builtins import str as _str
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Internal module dependencies
from minigun import stream as fs

###############################################################################
# Dissection
###############################################################################


@dataclass(slots=True)
class Dissection[T]:
    """A value together with a lazy stream of shrunk alternatives.

    :param head: The value itself.
    :param shrinks: A lazy stream of dissections of shrunk values.
    """

    head: T
    shrinks: fs.Stream["Dissection[T]"]


#: Shrinker datatype defined over a type parameter `T`.
type Shrinker[T] = Callable[[T], Dissection[T]]


def map[*Ts, R](
    func: Callable[[*Ts], R], *dissections: Dissection[Any]
) -> Dissection[R]:
    """A variadic map function of given input dissections over types `A`, `B`, etc. to an output dissection over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param dissections: Input dissections over types `A`, `B`, etc. to map from.
    :type dissections: `tuple[Dissection[A], Dissection[B], ...]`

    :return: A mapped output dissection.
    :rtype: `Dissection[R]`
    """

    def _combine(input_dissections: list[Dissection[Any]]) -> Dissection[R]:
        output_heads = [dissection.head for dissection in input_dissections]
        return Dissection(func(*output_heads), _cartesian(input_dissections))

    def _cartesian(
        input_dissections: list[Dissection[Any]],
    ) -> fs.Stream[Dissection[R]]:
        past = len(input_dissections)
        tails = [dissection.shrinks for dissection in input_dissections]

        def _shift_horizontal(index: _int) -> fs.Stream[Dissection[R]]:
            if past <= index:
                return fs.empty()

            def _shift_vertical(
                next_dissection: Dissection[Any],
            ) -> Dissection[R]:
                next_dissections = input_dissections.copy()
                next_dissections[index] = next_dissection
                return _combine(next_dissections)

            return fs.braid(
                fs.map(_shift_vertical, tails[index]),
                _shift_horizontal(index + 1),
            )

        return _shift_horizontal(0)

    return _combine(list(dissections))


def filter[T](
    predicate: Callable[[T], _bool], dissection: Dissection[T]
) -> Dissection[T] | None:
    """Filter a dissection of type `T`, both its head and shrunk values.

    :param predicate: A predicate on type `T`.
    :type predicate: `A -> bool`
    :param dissection: A dissection of type `T` to be filtered.
    :type dissection: `Dissection[T]`

    :return: The filtered dissection, or None if the head fails the predicate.
    :rtype: `Dissection[T] | None`
    """
    if not predicate(dissection.head):
        return None

    def _filter_shrinks(
        shrinks: fs.Stream[Dissection[T]],
    ) -> fs.Stream[Dissection[T]]:
        def _rebuild(dissection: Dissection[T]) -> Dissection[T]:
            return Dissection(
                dissection.head, _filter_shrinks(dissection.shrinks)
            )

        def _predicate(dissection: Dissection[T]) -> _bool:
            return predicate(dissection.head)

        return fs.map(_rebuild, fs.filter(_predicate, shrinks))

    return Dissection(dissection.head, _filter_shrinks(dissection.shrinks))


def prepend[T](value: T, dissection: Dissection[T]) -> Dissection[T]:
    """Prepend a value to a dissection.

    :param value: The value to be prepended.
    :type value: `T`
    :param dissection: The dissection to be prepended to.
    :type dissection: `Dissection[T]`

    :return: The updated dissection containing the given value.
    :rtype: `Dissection[T]`
    """
    return Dissection(value, fs.singleton(dissection))


def append[T](dissection: Dissection[T], value: T) -> Dissection[T]:
    """Append a value to a dissection.

    :param dissection: The dissection to be appended to.
    :type dissection: `Dissection[T]`
    :param value: The value to be appended.
    :type value: `T`

    :return: The updated dissection containing the given value.
    :rtype: `Dissection[T]`
    """
    return Dissection(
        dissection.head, fs.append(dissection.shrinks, singleton(value))
    )


def singleton[T](value: T) -> Dissection[T]:
    """A singleton dissection containing a single unshrinkable value.

    :param value: An unshrinkable value.
    :type value: `T`

    :return: A dissection over the type `T`.
    :rtype: `Dissection[T]`
    """
    return Dissection(value, fs.empty())


###############################################################################
# Trimmer
###############################################################################

#: A trimmer over a type `T`
type Trimmer[T] = Callable[[T], fs.Stream[T]]


###############################################################################
# Unfold trimmers
###############################################################################
def unfold[T](value: T, *trimmers: Trimmer[T]) -> Dissection[T]:
    """Define a dissection of an n-ary dimensional trimmed iteration of a given value.

    :param value: The initial value to do a trimmed iteration of.
    :type value: `T`
    :param trimmers: The given trimmers for values of type `T`.
    :type trimmers: `Trimmer[T]`

    :return: A dissection of trimmed interations over the given value.
    :rtype: `Dissection[T]`
    """

    # Bind the complementary trimmer set per iteration: the mapped stream
    # is forced lazily, after the loop variable has moved on.
    def _child(rest: list[Trimmer[T]]) -> Callable[[T], Dissection[T]]:
        def _mapping(shrunk_more: T) -> Dissection[T]:
            return unfold(shrunk_more, *rest)

        return _mapping

    _trimmers: list[Trimmer[T]] = list(trimmers)
    dissections: list[Dissection[T]] = []
    for index, trimmer in enumerate(trimmers):
        other_trimmers = _trimmers[:index] + _trimmers[index + 1 :]
        shrunk, shrunk_stream = fs.next(trimmer(value))
        if shrunk is None:
            continue
        dissections.append(
            Dissection(shrunk, fs.map(_child(other_trimmers), shrunk_stream))
        )
    return Dissection(value, fs.from_list(dissections))


###############################################################################
# Booleans
###############################################################################
def bool() -> Shrinker[_bool]:
    """A shrinker for booleans which shrinks towards False.

    :return: A shrinker of bool.
    :rtype: `Shrinker[bool]`
    """

    def _impl(value: _bool) -> Dissection[_bool]:
        if value:
            return Dissection(True, fs.singleton(singleton(False)))
        return singleton(False)

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
            state: tuple[_int, _int],
        ) -> tuple[_int, tuple[_int, _int]] | None:
            value, current = state
            if current == value:
                return None
            _value = current + _int((value - current) / 2)
            return _value, (_value, current)

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
            state: tuple[_float, _int],
        ) -> tuple[_float, tuple[_float, _int]] | None:
            value, current = state
            value_f, value_i = math.modf(value)
            if current == _int(value_i):
                return None
            _value = current + value_f + _int((value_i - current) / 2)
            return _value, (_value, current)

        return fs.unfold(_towards, (initial, _int(target)))

    def _trim_fractional_part(initial: _float) -> fs.Stream[_float]:
        def _towards(
            state: tuple[_int, _float, _float],
        ) -> tuple[_float, tuple[_int, _float, _float]] | None:
            count, value, current = state
            value_f, value_i = math.modf(value)
            if count == 0:
                return None
            if current == value_f:
                return None
            _value = value_i + current + ((value_f - current) / 2)
            return _value, (count - 1, _value, current)

        return fs.unfold(_towards, (10, initial, math.modf(target)[0]))

    def _impl(value: _float) -> Dissection[_float]:
        return unfold(value, _trim_integer_part, _trim_fractional_part)

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

        def _towards(index: _int) -> tuple[_str, _int] | None:
            if index == past:
                return None
            _value = initial[:index] + initial[index + 1 :]
            return _value, index + 1

        return fs.unfold(_towards, 0)

    def _impl(value: _str) -> Dissection[_str]:
        return unfold(value, _trim)

    return _impl
