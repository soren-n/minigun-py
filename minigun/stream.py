"""
Functional Stream Operations

This module provides lazy functional streams for efficient handling of
potentially infinite sequences. Streams are used extensively throughout
Minigun for shrinking trees, generator composition, and lazy evaluation.

Architecture:
    - Stream[T]: Lazy thunked computation yielding (value, next_stream)
    - Exhaustion is signalled by raising StopIteration from the thunk
    - Combinators: map, filter for stream processing
    - Construction: unfold, empty, singleton, constant, from_list
    - Composition: concat, braid for combining streams

Streams enable memory-efficient processing of large or infinite data sets
while maintaining functional purity and composability. They're particularly
important in the shrinking system where they represent trees of shrunk
values.

Example::

        import minigun.stream as fs

        # Create infinite stream of natural numbers
        nats = fs.unfold(lambda n: (n, n + 1), 0)

        # Transform and take first 10 even numbers
        evens = fs.map(lambda x: x * 2, nats)
        first_10_evens = fs.to_list(evens, 10)
        # [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
"""

# External module dependencies
from collections.abc import Callable
from functools import partial
from typing import Any

###############################################################################
# Persistent streams
###############################################################################

type Thunk[R] = Callable[[], R]

#: StreamResult datatype defined over a type parameter `T`.
type StreamResult[T] = tuple[T, "Stream[T]"]

#: Stream datatype defined over a type parameter `T`. Calling the thunk
#: yields the head and tail, or raises StopIteration when exhausted.
type Stream[T] = Thunk[StreamResult[T]]


def next[T](stream: Stream[T]) -> tuple[T | None, Stream[T]]:
    """Get the next head and tail of the stream, if a next head exists.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: A tuple of the head of the stream (None when exhausted) and
        the tail of the stream.
    :rtype: `tuple[T | None, Stream[T]]`
    """
    try:
        next_value, next_stream = stream()
        return next_value, next_stream
    except StopIteration:
        return None, stream


def peek[T](stream: Stream[T]) -> T | None:
    """Peek the next head of the stream, if a next head exists.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: The head of the stream, or None when exhausted.
    :rtype: `T | None`
    """
    try:
        next_value, _ = stream()
        return next_value
    except StopIteration:
        return None


def map[*P, R](func: Callable[[*P], R], *streams: Stream[Any]) -> Stream[R]:
    """A variadic map function of given input streams over types `A`, `B`, etc. to an output stream over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param streams: Input streams over types `A`, `B`, etc. to map from.
    :type streams: `tuple[Stream[A], Stream[B], ...]`

    :return: A mapped output stream.
    :rtype: `Stream[R]`
    """

    def _thunk() -> StreamResult[R]:
        next_values, next_streams = zip(
            *[stream() for stream in streams], strict=False
        )
        return func(*next_values), map(func, *next_streams)

    return _thunk


def filter[T](predicate: Callable[[T], bool], stream: Stream[T]) -> Stream[T]:
    """Filter a stream of type `T`.

    :param predicate: A predicate on type `T`.
    :type predicate: `A -> bool`
    :param stream: A stream of type `T` to be filtered.
    :type stream: `Stream[T]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        next_stream: Stream[T] = stream
        while True:
            next_value, next_stream = next_stream()
            if not predicate(next_value):
                continue
            return next_value, filter(predicate, next_stream)

    return _thunk


def unfold[T, S](func: Callable[[S], tuple[T, S] | None], init: S) -> Stream[T]:
    """Create a stream of a type `T` unfolded from a function over a state of type `S`.

    :param func: A function that produces a value of type `T` and a next state given a state of type `S`, or None to end the stream.
    :type func: `S -> tuple[T, S] | None`
    :param init: An initial value of type `S`.
    :type init: `S`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        match func(init):
            case None:
                raise StopIteration
            case (value, state):
                return value, unfold(func, state)

    return _thunk


def empty[T]() -> Stream[T]:
    """Create an empty stream of type `T`.

    :return: An empty stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        raise StopIteration

    return _thunk


def singleton[T](value: T) -> Stream[T]:
    """Create a stream containing only one value, is empty after that value.

    :param value: A value of type `T`.
    :type value: `T`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        return value, empty()

    return _thunk


def constant[T](value: T) -> Stream[T]:
    """Create a infinite stream containing a constant value.

    :param value: A value of type `T`.
    :type value: `T`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        return value, constant(value)

    return _thunk


def prepend[T](value: T, stream: Stream[T]) -> Stream[T]:
    """Prepend a value of type `T` to a stream of type `T`.

    :param value: A value of type `T`.
    :type value: `T`
    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        return value, stream

    return _thunk


def append[T](stream: Stream[T], value: T) -> Stream[T]:
    """Append a value of type `T` to a stream of type `T`.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`
    :param value: A value of type `T`.
    :type value: `T`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        try:
            next_value, next_stream = stream()
        except StopIteration:
            return value, empty()
        return next_value, append(next_stream, value)

    return _thunk


def concat[T](left: Stream[T], right: Stream[T]) -> Stream[T]:
    """Concatenate two streams of type `T`.

    :param left: A stream of type `T`.
    :type left: `Stream[T]`
    :param right: A stream of type `T`.
    :type right: `Stream[T]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        try:
            next_value, next_left = left()
        except StopIteration:
            return right()
        return next_value, concat(next_left, right)

    return _thunk


def braid[T](*streams: Stream[T]) -> Stream[T]:
    """Braid multiple streams of type `T` together into a single stream of type `T`.

    :param streams: Multiple streams of type `T`.
    :type streams: `tuple[Stream[T], ...]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _impl(streams: list[Stream[T]]) -> StreamResult[T]:
        while len(streams) != 0:
            stream = streams.pop(0)
            try:
                next_value, next_stream = stream()
            except StopIteration:
                continue
            streams.append(next_stream)
            return next_value, partial(_impl, streams)
        raise StopIteration

    return partial(_impl, list(streams))


def from_list[T](items: list[T]) -> Stream[T]:
    """Create a stream of type `T` from a list of type `T`.

    :param items: A list of type `T`.
    :type items: `list[T]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """
    result: Stream[T] = empty()
    for item in reversed(items):
        result = prepend(item, result)
    return result


def to_list[T](stream: Stream[T], max_items: int) -> list[T]:
    """Create a list of type `T` from a stream of type `T`.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`
    :param max_items: The maximum number of items to take from the stream.
    :type max_items: `int`

    :return: A list of type `T`.
    :rtype: `list[T]`
    """
    items: list[T] = []
    for _ in range(max_items):
        try:
            item, stream = stream()
        except StopIteration:
            break
        items.append(item)
    return items
