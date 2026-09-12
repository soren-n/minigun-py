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

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from minigun import stream as fs

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
    shrinks: fs.Stream["Dissection[T]"]


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
def integer(target: int) -> Shrinker[int]:
    """A shrinker for integers, shrinking toward a target.

    Alternatives are the target, then values halving the distance toward
    the target from the far side: ``target, v - d/2, v - d/4, ...`` where
    ``d = v - target``. A first-failing-child search over this order finds
    the exact boundary of a monotone failing region.
    """

    def _trim(value: int) -> fs.Stream[int]:
        def _iterate() -> Iterator[int]:
            if value == target:
                return
            yield target
            step = int((value - target) / 2)
            while step != 0:
                yield value - step
                step = int(step / 2)

        return _iterate

    def _impl(value: int) -> Dissection[int]:
        return unfold(value, _trim)

    return _impl


def floating(target: float) -> Shrinker[float]:
    """A shrinker for floats, shrinking toward a target.

    Alternatives are the target, the value truncated to an integer, then
    values halving the distance toward the target. Non-finite values shrink
    directly to the target.
    """

    def _to_target(value: float) -> fs.Stream[float]:
        def _iterate() -> Iterator[float]:
            if value != target:
                yield target

        return _iterate

    def _truncate(value: float) -> fs.Stream[float]:
        def _iterate() -> Iterator[float]:
            if not math.isfinite(value):
                return
            truncated = float(math.trunc(value))
            if truncated != value and abs(truncated - target) < abs(
                value - target
            ):
                yield truncated

        return _iterate

    def _halve(value: float) -> fs.Stream[float]:
        def _iterate() -> Iterator[float]:
            if not math.isfinite(value):
                return
            distance = abs(value - target)
            step = (value - target) / 2
            while True:
                candidate = value - step
                # Stop once float arithmetic no longer makes progress: the
                # candidate must be strictly closer to the target.
                if candidate == target or abs(candidate - target) >= distance:
                    return
                yield candidate
                step /= 2

        return _iterate

    def _impl(value: float) -> Dissection[float]:
        return unfold(value, _to_target, _truncate, _halve)

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
