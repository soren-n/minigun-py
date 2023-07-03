# External module dependencies
from functools import partial
from typing import (
    cast,
    Any,
    TypeVar,
    ParamSpec,
    Optional,
    Callable,
    Tuple
)

# Internal module dependencies
from . import maybe as m

###############################################################################
# Persistent streams
###############################################################################
T = TypeVar('T')
P = ParamSpec('P')
R = TypeVar('R')

Thunk = Callable[[], R]

#: StreamResult datatype defined over a type parameter `T`.
StreamResult = Tuple[T, 'Stream[T]']

#: Stream datatype defined over a type parameter `T`.
Stream = Thunk[StreamResult[T]]

def next(stream: Stream[T]) -> Tuple[m.Maybe[T], Stream[T]]:
    """Get the next head and tail of the stream, if a next head exists.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: A tuple of maybe the head of stream and the tail of stream.
    :rtype: `Tuple[minigun.maybe.Maybe[T], Stream[T]]`
    """
    try:
        next_value, next_stream = stream()
        return m.Something(next_value), next_stream
    except StopIteration:
        return m.Nothing(), stream

def peek(stream: Stream[T]) -> m.Maybe[T]:
    """Peek the next head of the stream, if a next head exists.

    :param stream: A stream of type `T`.
    :type stream: `Stream[T]`

    :return: Maybe of the head of the stream.
    :rtype: `minigun.maybe.Maybe[T]`
    """
    try:
        next_value, _ = stream()
        return m.Something(next_value)
    except StopIteration:
        return m.Nothing()

def is_empty(stream: Stream[T]) -> bool:
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

def map(
    func: Callable[P, R],
    *streams: Stream[Any]
    ) -> Stream[R]:
    """A variadic map function of given input streams over types `A`, `B`, etc. to an output stream over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param streams: Input streams over types `A`, `B`, etc. to map from.
    :type streams: `Tuple[Stream[A], Stream[B], ...]`

    :return: A mapped output stream.
    :rtype: `Stream[R]`
    """
    def _apply(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    def _thunk() -> StreamResult[R]:
        next_values, next_streams = zip(*[stream() for stream in streams])
        return _apply(*next_values), map(func, *next_streams)
    return _thunk

def filter(
    predicate: Callable[[T], bool],
    stream: Stream[T]
    ) -> Stream[T]:
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
            if not predicate(next_value): continue
            return next_value, filter(predicate, next_stream)
    return _thunk

def filter_map(
    func: Callable[[T], m.Maybe[R]],
    stream: Stream[T]
    ) -> Stream[R]:
    """Filter and map a stream of type `T` to a type `R`.

    :param func: A function on type `T` to a maybe value of type `R`.
    :type func: `A -> minigun.maybe.Maybe[R]`
    :param stream: A stream of type `T` to be filtered.
    :type stream: `Stream[T]`

    :return: A stream of type `R`.
    :rtype: `Stream[R]`
    """
    def _thunk() -> StreamResult[R]:
        next_stream = stream
        while True:
            next_value, next_stream = next_stream()
            _next_value = func(next_value)
            if isinstance(_next_value, m.Nothing): continue
            return _next_value.value, filter_map(func, next_stream)
    return _thunk

S = TypeVar('S')
def unfold(
    func: Callable[[S], m.Maybe[Tuple[T, S]]],
    init: S
    ) -> Stream[T]:
    """Create a stream of a type `T` unfolded from a function over a state of type `S`.

    :param func: A function that maybe produces a value of type `T` over given a state of type `S`.
    :type func: `S -> minigun.maybe.Maybe[Tuple[T, S]]`
    :param init: An initial value of type `S`.
    :type init: `S`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """
    def _thunk() -> StreamResult[T]:
        result = func(init)
        if isinstance(result, m.Nothing): raise StopIteration
        value, state = result.value
        return value, unfold(func, state)
    return _thunk

def empty(_dummy: Optional[T] = None) -> Stream[T]:
    """Create an empty stream of type `T`.

    :return: An empty stream of type `T`.
    :rtype: `Stream[T]`
    """
    def _thunk() -> StreamResult[T]:
        raise StopIteration
    return _thunk

def singleton(value: T) -> Stream[T]:
    """Create a stream containing only one value, is empty after that value.

    :param value: A value of type `T`.
    :type value: `T`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """
    def _thunk() -> StreamResult[T]:
        return value, cast(Stream[T], empty())
    return _thunk

def prepend(value: T, stream: Stream[T]) -> Stream[T]:
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

def append(stream: Stream[T], value: T) -> Stream[T]:
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

def concat(left: Stream[T], right: Stream[T]) -> Stream[T]:
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

def braid(*streams: Stream[T]) -> Stream[T]:
    """Braid multiple streams of type `T` together into a single stream of type `T`.

    :param streams: Multiple streams of type `T`.
    :type streams: `Tuple[Stream[T], ...]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """
    def _impl(
        streams: list[Stream[T]]
        ) -> StreamResult[T]:
        while len(streams) != 0:
            try:
                stream = streams.pop(0)
                next_value, next_stream = stream()
                streams.append(next_stream)
                return next_value, partial(_impl, streams)
            except: pass
        raise StopIteration
    return partial(_impl, list(streams))

def from_list(items: list[T]) -> Stream[T]:
    """Create a stream of type `T` from a list of type `T`.

    :param items: A list of type `T`.
    :type items: `List[T]`

    :return: A stream of type `T`.
    :rtype: `Stream[T]`
    """
    result: Stream[T] = empty()
    for item in reversed(items):
        result = prepend(item, result)
    return result
