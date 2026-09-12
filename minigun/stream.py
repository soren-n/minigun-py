"""
Lazy re-iterable streams

A ``Stream[T]`` is a zero-argument callable that returns a fresh iterator
over values of type ``T``. Two properties follow from that shape and both
are relied on by the shrinking system:

- Laziness: nothing is computed until the iterator is advanced, so a stream
  can describe an unbounded space of values without materializing it.
- Re-traversability: calling the stream again yields a fresh iterator over
  the same values, so one stream can be walked from several places.

Producers are ordinarily generator functions closed over their inputs;
composition uses ``itertools`` and the builtin iteration protocol. A stream
must never hold a live iterator, only the means of making one.

Example::

        import minigun.stream as fs

        nats = fs.unfold(lambda n: (n, n + 1), 0)
        evens = fs.map(lambda x: x * 2, nats)
        fs.to_list(evens, 5)  # [0, 2, 4, 6, 8]
"""

import builtins
import itertools
from collections.abc import Callable, Iterator

#: A lazy, re-iterable sequence of values of type ``T``.
type Stream[T] = Callable[[], Iterator[T]]


__all__ = [
    "Stream",
    "empty",
    "singleton",
    "constant",
    "from_list",
    "unfold",
    "map",
    "filter",
    "prepend",
    "append",
    "concat",
    "braid",
    "to_list",
]


###############################################################################
# Construction
###############################################################################
def empty[T]() -> Stream[T]:
    """A stream with no values."""

    def _iterate() -> Iterator[T]:
        return iter(())

    return _iterate


def singleton[T](value: T) -> Stream[T]:
    """A stream of exactly one value."""

    def _iterate() -> Iterator[T]:
        yield value

    return _iterate


def constant[T](value: T) -> Stream[T]:
    """An infinite stream repeating one value."""

    def _iterate() -> Iterator[T]:
        return itertools.repeat(value)

    return _iterate


def from_list[T](items: list[T]) -> Stream[T]:
    """A stream over a snapshot of a list."""
    snapshot = list(items)

    def _iterate() -> Iterator[T]:
        return iter(snapshot)

    return _iterate


def unfold[T, S](func: Callable[[S], tuple[T, S] | None], init: S) -> Stream[T]:
    """A stream unfolded from a step function over a state.

    :param func: Produces the next value and state, or None to end.
    :param init: The initial state.
    """

    def _iterate() -> Iterator[T]:
        state = init
        while (step := func(state)) is not None:
            value, state = step
            yield value

    return _iterate


###############################################################################
# Transformation
###############################################################################
def map[T, R](func: Callable[[T], R], stream: Stream[T]) -> Stream[R]:
    """Apply a function to every value of a stream."""

    def _iterate() -> Iterator[R]:
        return builtins.map(func, stream())

    return _iterate


def filter[T](predicate: Callable[[T], bool], stream: Stream[T]) -> Stream[T]:
    """Keep the values of a stream that satisfy a predicate."""

    def _iterate() -> Iterator[T]:
        return builtins.filter(predicate, stream())

    return _iterate


###############################################################################
# Composition
###############################################################################
def prepend[T](value: T, stream: Stream[T]) -> Stream[T]:
    """A stream starting with a value followed by another stream."""

    def _iterate() -> Iterator[T]:
        yield value
        yield from stream()

    return _iterate


def append[T](stream: Stream[T], value: T) -> Stream[T]:
    """A stream ending with a value after another stream."""

    def _iterate() -> Iterator[T]:
        yield from stream()
        yield value

    return _iterate


def concat[T](*streams: Stream[T]) -> Stream[T]:
    """The values of each stream in turn."""

    def _iterate() -> Iterator[T]:
        for stream in streams:
            yield from stream()

    return _iterate


def braid[T](*streams: Stream[T]) -> Stream[T]:
    """The values of several streams interleaved round-robin.

    Exhausted streams drop out; the result ends when all have ended.
    """

    def _iterate() -> Iterator[T]:
        iterators = [stream() for stream in streams]
        while iterators:
            remaining: list[Iterator[T]] = []
            for iterator in iterators:
                try:
                    yield next(iterator)
                except StopIteration:
                    continue
                remaining.append(iterator)
            iterators = remaining

    return _iterate


###############################################################################
# Consumption
###############################################################################
def to_list[T](stream: Stream[T], max_items: int) -> list[T]:
    """Collect at most ``max_items`` values from the front of a stream."""
    return list(itertools.islice(stream(), max_items))
