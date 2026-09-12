"""
Shrinking

A ``Dissection[T]`` is a value together with a lazy stream of dissections of
shrunk alternatives: a rose tree whose children are built only when the
search walks into them. Shrinkers for the built-in types are provided, and
``unfold`` builds a shrinker from trimmers, functions that produce the
immediate shrunk alternatives of a value.

Alternatives are ordered from the most aggressive shrink to the least, so a
first-failing-child search behaves as a binary search toward the smallest
failing value.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from minigun import stream as fs

__all__ = [
    "Dissection",
    "Shrinker",
    "Trimmer",
    "singleton",
    "prepend",
    "append",
    "map",
    "filter",
    "unfold",
    "chunk_removals",
    "boolean",
    "integer",
    "floating",
    "string",
]


###############################################################################
# Dissection
###############################################################################


@dataclass(slots=True)
class Dissection[T]:
    """A value together with a lazy stream of shrunk alternatives.

    :param head: The value itself.
    :param shrinks: A lazy, re-iterable stream of dissections of shrunk
        values, ordered from most to least aggressive shrink. Never a live
        iterator: always the means of making one.
    """

    head: T
    shrinks: fs.Stream[Dissection[T]]


#: A shrinker over a type ``T``.
type Shrinker[T] = Callable[[T], Dissection[T]]

#: A trimmer over a type ``T``: the immediate shrunk alternatives of a value.
type Trimmer[T] = Callable[[T], fs.Stream[T]]


def singleton[T](value: T) -> Dissection[T]:
    """A dissection of an unshrinkable value."""
    return Dissection(value, fs.empty())


def prepend[T](value: T, dissection: Dissection[T]) -> Dissection[T]:
    """A dissection of ``value`` whose only alternative is ``dissection``."""
    return Dissection(value, fs.singleton(dissection))


def append[T](dissection: Dissection[T], value: T) -> Dissection[T]:
    """The dissection with an unshrinkable ``value`` as its last alternative."""
    return Dissection(
        dissection.head, fs.append(dissection.shrinks, singleton(value))
    )


def map[*Ts, R](
    func: Callable[[*Ts], R], *dissections: Dissection[Any]
) -> Dissection[R]:
    """Combine dissections with a function.

    The result shrinks one argument at a time, interleaving the arguments
    round-robin so no single argument starves the others.
    """
    inputs = list(dissections)

    def _combine(current: list[Dissection[Any]]) -> Dissection[R]:
        def _dimension(index: int) -> fs.Stream[Dissection[R]]:
            def _iterate() -> Iterator[Dissection[R]]:
                for child in current[index].shrinks():
                    replaced = list(current)
                    replaced[index] = child
                    yield _combine(replaced)

            return _iterate

        heads = [dissection.head for dissection in current]
        return Dissection(
            func(*heads),
            fs.braid(*[_dimension(index) for index in range(len(current))]),
        )

    return _combine(inputs)


def filter[T](
    predicate: Callable[[T], bool], dissection: Dissection[T]
) -> Dissection[T] | None:
    """Restrict a dissection to values satisfying a predicate.

    :return: The restricted dissection, or None when the head itself fails
        the predicate.
    """
    if not predicate(dissection.head):
        return None

    def _restrict(node: Dissection[T]) -> Dissection[T]:
        def _iterate() -> Iterator[Dissection[T]]:
            for child in node.shrinks():
                if predicate(child.head):
                    yield _restrict(child)

        return Dissection(node.head, _iterate)

    return _restrict(dissection)


###############################################################################
# Unfold trimmers
###############################################################################
def unfold[T](value: T, *trimmers: Trimmer[T]) -> Dissection[T]:
    """The dissection of a value under a set of trimmers.

    Children are the alternatives of each trimmer in turn, each child
    recursively unfolded under all trimmers. Nothing is computed until the
    children are iterated.
    """

    def _iterate() -> Iterator[Dissection[T]]:
        for trimmer in trimmers:
            for shrunk in trimmer(value)():
                yield unfold(shrunk, *trimmers)

    return Dissection(value, _iterate)


###############################################################################
# Removal of chunks from sequences
###############################################################################
def chunk_removals(length: int, max_removed: int) -> Iterator[tuple[int, int]]:
    """Index ranges to delete from a sequence, largest chunks first.

    Yields ``(start, end)`` half-open ranges for chunk sizes halving from
    ``min(length, max_removed)`` down to one, at positions aligned to the
    chunk size. This is the sequence shrinking order of QuickCheck.
    """
    size = min(length, max_removed)
    while size >= 1:
        for start in range(0, length - size + 1, size):
            yield start, start + size
        size //= 2


###############################################################################
# Booleans
###############################################################################
def boolean() -> Shrinker[bool]:
    """A shrinker for booleans, shrinking True to False."""

    def _impl(value: bool) -> Dissection[bool]:
        if value:
            return prepend(True, singleton(False))
        return singleton(False)

    return _impl


###############################################################################
# Numbers
###############################################################################
def _halve(distance: int) -> int:
    """Half of a signed distance, truncated toward zero."""
    return distance // 2 if distance >= 0 else -(-distance // 2)


def integer(target: int) -> Shrinker[int]:
    """A shrinker for integers, shrinking toward a target.

    The alternatives of a value are the target, then the midpoints between
    the target and the value, each closer to the value than the last. An
    alternative is offered knowing that the one before it did not fail,
    so its own alternatives lie between that one and itself. A
    first-failing-child search over the tree is therefore a bisection: it
    finds the exact boundary of a monotone failing region in a
    logarithmic number of evaluations.
    """

    def _node(bound: int, value: int, from_target: bool) -> Dissection[int]:
        # ``bound`` is the alternative offered before ``value``, or the
        # target at the root; the alternatives of ``value`` lie strictly
        # between the two.
        def _iterate() -> Iterator[Dissection[int]]:
            if from_target and value != target:
                yield singleton(target)
            previous = bound
            while True:
                candidate = previous + _halve(value - previous)
                if candidate == previous:
                    return
                yield _node(previous, candidate, False)
                previous = candidate

        return Dissection(value, _iterate)

    def _impl(value: int) -> Dissection[int]:
        return _node(target, value, True)

    return _impl


#: Relative difference below which float alternatives stop being offered.
_FLOAT_RESOLUTION = 1e-9


def floating(target: float) -> Shrinker[float]:
    """A shrinker for floats, shrinking toward a target.

    The alternatives of a finite value are the target, the value truncated
    to an integer when that is closer to the target, then the midpoints
    between the target and the value as for integers, each offered knowing
    the one before it did not fail. Halving stops once an alternative
    differs from the value by less than one part in a billion, so a
    search ends after a bounded number of evaluations instead of walking
    the full precision of floats. Non-finite values shrink directly to the
    target.
    """

    def _closer(candidate: float, value: float) -> bool:
        return abs(candidate - target) < abs(value - target)

    def _node(
        bound: float, value: float, from_target: bool
    ) -> Dissection[float]:
        def _iterate() -> Iterator[Dissection[float]]:
            if value == target:
                return
            if not math.isfinite(value):
                yield singleton(target)
                return
            if from_target:
                yield singleton(target)
            previous = bound
            truncated = float(math.trunc(value))
            if (
                truncated != value
                and _closer(truncated, value)
                and _closer(bound, truncated)
            ):
                yield _node(bound, truncated, False)
                previous = truncated
            while True:
                candidate = previous + (value - previous) / 2
                if (
                    candidate == previous
                    or not _closer(candidate, value)
                    or math.isclose(candidate, value, rel_tol=_FLOAT_RESOLUTION)
                ):
                    return
                yield _node(previous, candidate, False)
                previous = candidate

        return Dissection(value, _iterate)

    def _impl(value: float) -> Dissection[float]:
        return _node(target, value, True)

    return _impl


###############################################################################
# Strings
###############################################################################
def string() -> Shrinker[str]:
    """A shrinker for strings, removing chunks of characters."""

    def _trim(value: str) -> fs.Stream[str]:
        def _iterate() -> Iterator[str]:
            for start, end in chunk_removals(len(value), len(value)):
                yield value[:start] + value[end:]

        return _iterate

    def _impl(value: str) -> Dissection[str]:
        return unfold(value, _trim)

    return _impl
