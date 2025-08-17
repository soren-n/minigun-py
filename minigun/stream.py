"""
Functional Stream Operations

This module provides lazy functional streams for efficient handling of
potentially infinite sequences. Streams are used extensively throughout
Minigun for shrinking trees, generator composition, and lazy evaluation.

Architecture:
    - Stream[T]: Lazy thunked computation yielding (value, next_stream)
    - Combinators: map, filter, filter_map for stream processing
    - Construction: unfold, singleton, constant, from_list
    - Composition: concat, braid for combining streams

Streams enable memory-efficient processing of large or infinite data sets
while maintaining functional purity and composability. They're particularly
important in the shrinking system where they represent trees of shrunk values.

Example:
    ```python
    import minigun.stream as fs

    # Create infinite stream of natural numbers
    nats = fs.unfold(lambda n: Some((n, n + 1)), 0)

    # Transform and take first 10 even numbers
    evens = fs.map(lambda x: x * 2, nats)
    first_10_evens = fs.to_list(evens, 10)
    # [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
    ```
"""

# External module dependencies
from collections.abc import Callable
from functools import partial
from inspect import Parameter, signature
from typing import Any, cast

from returns.maybe import Maybe, Nothing, Some

###############################################################################
# Persistent streams
###############################################################################

type Thunk[R] = Callable[[], R]

#: StreamResult datatype defined over a type parameter `T`.
type StreamResult[T] = tuple[T, "Stream[T]"]

#: Stream datatype defined over a type parameter `T`.
type Stream[T] = Thunk[StreamResult[T]]


def next[T](stream: Stream[T]) -> tuple[Maybe[T], Stream[T]]:
    """Get the next head and tail of the stream, if a next head exists.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: A tuple of maybe the head of stream and the tail of stream.
    :rtype: `tuple[returns.maybe.Maybe[T], Stream[T]]`
    """
    try:
        next_value, next_stream = stream()
        return Some(next_value), next_stream
    except StopIteration:
        return Nothing, stream


def peek[T](stream: Stream[T]) -> Maybe[T]:
    """Peek the next head of the stream, if a next head exists.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: Maybe of the head of the stream.
    :rtype: `returns.maybe.Maybe[T]`
    """
    try:
        next_value, _ = stream()
        return Some(next_value)
    except StopIteration:
        return Nothing


def is_empty[T](stream: Stream[T]) -> bool:
    """Check if the stream is empty.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: A boolean value.
    :rtype: `bool`
    """
    try:
        _ = stream()
        return False
    except StopIteration:
        return True


def map[*P, R](func: Callable[[*P], R], *streams: Stream[Any]) -> Stream[R]:
    """A variadic map function of given input streams over types `A`, `B`, etc. to an output stream over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param streams: Input streams over types `A`, `B`, etc. to map from.
    :type streams: `tuple[Stream[A], Stream[B], ...]`

    :return: A mapped output stream.
    :rtype: `Stream[R]`
    """

    func_parameters = signature(func).parameters
    argument_count = len(func_parameters)
    func_is_variadic = any(
        parameter.kind == Parameter.VAR_POSITIONAL
        for parameter in func_parameters.values()
    )
    assert len(streams) == argument_count or func_is_variadic, (
        f"Function {func} expected {argument_count} "
        f"arguments, but got {len(streams)} streams."
    )

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


def filter_map[T, R](
    func: Callable[[T], Maybe[R]], stream: Stream[T]
) -> Stream[R]:
    """Filter and map a stream of type `T` to a type `R`.

    :param func: A function on type `T` to a maybe value of type `R`.
    :type func: `A -> returns.maybe.Maybe[R]`
    :param stream: A stream of type `T` to be filtered.
    :type stream: `Stream[T]`

    :return: A stream of type `R`.
    :rtype: `Stream[R]`
    """

    def _thunk() -> StreamResult[R]:
        next_stream = stream
        while True:
            next_value, next_stream = next_stream()
            match func(next_value):
                case Maybe.empty:
                    continue
                case Some(_next_value):
                    return _next_value, filter_map(func, next_stream)
                case _:
                    raise AssertionError("Invariant")

    return _thunk


def unfold[T, S](func: Callable[[S], Maybe[tuple[T, S]]], init: S) -> Stream[T]:
    """Create a stream of a type `T` unfolded from a function over a state of type `S`.

    :param func: A function that maybe produces a value of type `T` over given a state of type `S`.
    :type func: `S -> returns.maybe.Maybe[tuple[T, S]]`
    :param init: An initial value of type `S`.
    :type init: `S`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """

    def _thunk() -> StreamResult[T]:
        match func(init):
            case Maybe.empty:
                raise StopIteration
            case Some((value, state)):
                return value, unfold(func, state)
            case _:
                raise AssertionError("Invariant")

    return _thunk


def empty[T](_dummy: T | None = None) -> Stream[T]:
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
        return value, cast(Stream[T], empty())

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
            return next_value, append(next_stream, value)
        except StopIteration:
            return value, cast(Stream[T], empty())

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
            return next_value, concat(next_left, right)
        except StopIteration:
            return right()

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
            try:
                stream = streams.pop(0)
                next_value, next_stream = stream()
                streams.append(next_stream)
                return next_value, partial(_impl, streams)
            except:
                pass
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

    :return: A list of type `T`.
    :rtype: `list[T]`
    """
    items: list[T] = []
    for _ in range(max_items):
        maybe_item, stream = next(stream)
        match maybe_item:
            case Maybe.empty:
                break
            case Some(item):
                items.append(item)
            case _:
                raise AssertionError("Invariant")
    return items
