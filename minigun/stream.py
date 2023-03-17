# External module dependencies
from typing import (
    cast,
    overload,
    Any,
    TypeVar,
    ParamSpec,
    Callable,
    Tuple
)

# Internal module dependencies
from . import maybe as m

###############################################################################
# Persistent streams
###############################################################################
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
D = TypeVar('D')

P = ParamSpec('P')
R = TypeVar('R')

Thunk = Callable[[], R]

#: StreamResult datatype defined over a type parameter `A`.
StreamResult = Tuple[A, 'Stream[A]']

#: Stream datatype defined over a type parameter `A`.
Stream = Thunk[StreamResult[A]]

def next(stream : Stream[A]) -> Tuple[m.Maybe[A], Stream[A]]:
    """Get the next head and tail of the stream, if a next head exists.

    :param stream: A stream of type `A`.
    :type stream: `Stream[A]`

    :return: A tuple of maybe the head of stream and the tail of stream.
    :rtype: `Tuple[minigun.maybe.Maybe[A], Stream[A]]`
    """
    try:
        next_value, next_stream = stream()
        return m.Something(next_value), next_stream
    except StopIteration:
        return m.Nothing(), stream

def peek(stream : Stream[A]) -> m.Maybe[A]:
    """Peek the next head of the stream, if a next head exists.

    :param stream: A stream of type `A`.
    :type stream: `Stream[A]`

    :return: Maybe of the head of the stream.
    :rtype: `minigun.maybe.Maybe[A]`
    """
    try:
        next_value, _ = stream()
        return m.Something(next_value)
    except StopIteration:
        return m.Nothing()

def is_empty(stream : Stream[A]) -> bool:
    """Check if the stream is empty.

    :param stream: A stream of type `A`.
    :type stream: `Stream[A]`

    :return: A boolean value.
    :rtype: `bool`
    """
    try:
        _ = stream()
        return False
    except StopIteration:
        return True

@overload
def map(
    func : Callable[[], R]
    ) -> Stream[R]:
    ...
@overload
def map(
    func : Callable[[A], R],
    a_stream : Stream[A]
    ) -> Stream[R]:
    ...
@overload
def map(
    func : Callable[[A, B], R],
    a_stream : Stream[A],
    b_stream : Stream[B]
    ) -> Stream[R]:
    ...
@overload
def map(
    func : Callable[[A, B, C], R],
    a_stream : Stream[A],
    b_stream : Stream[B],
    c_stream : Stream[C]
    ) -> Stream[R]:
    ...
@overload
def map(
    func : Callable[[A, B, C, D], R],
    a_stream : Stream[A],
    b_stream : Stream[B],
    c_stream : Stream[C],
    d_stream : Stream[D]
    ) -> Stream[R]:
    ...
def map(
    func : Callable[P, R],
    *streams : Stream[Any]
    ) -> Stream[R]:
    """A variadic map function of given input streams over types `A`, `B`, etc. to an output stream over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param streams: Input streams over types `A`, `B`, etc. to map from.
    :type streams: `Tuple[Stream[A], Stream[B], ...]`

    :return: A mapped output stream.
    :rtype: `Stream[R]`
    """
    def _thunk() -> StreamResult[R]:
        next_values, next_streams = zip(*[stream() for stream in streams])
        return func(*next_values), map(func, *next_streams)
    return _thunk

def filter(pred : Callable[[A], bool], stream : Stream[A]) -> Stream[A]:
    """Filter a stream of type `A`.

    :param pred: A predicate on type `A`.
    :type pred: `A -> bool`
    :param stream: A stream of type `A` to be filtered.
    :type stream: `Stream[A]`

    :return: A stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        next_stream : Stream[A] = stream
        while True:
            next_value, next_stream = next_stream()
            if not pred(next_value): continue
            return next_value, filter(pred, next_stream)
    return _thunk

def filter_map(
    func : Callable[[A], m.Maybe[B]],
    stream : Stream[A]
    ) -> Stream[B]:
    """Filter and map a stream of type `A` to a type `B`.

    :param func: A function on type `A` to a maybe value of type `B`.
    :type func: `A -> minigun.maybe.Maybe[B]`
    :param stream: A stream of type `A` to be filtered.
    :type stream: `Stream[A]`

    :return: A stream of type `B`.
    :rtype: `Stream[B]`
    """
    def _thunk() -> StreamResult[B]:
        next_stream = stream
        while True:
            next_value, next_stream = next_stream()
            _next_value = func(next_value)
            if isinstance(_next_value, m.Nothing): continue
            return _next_value.value, filter_map(func, next_stream)
    return _thunk

def unfold(
    func : Callable[[B], m.Maybe[Tuple[A, B]]],
    init : B
    ) -> Stream[A]:
    """Create a stream of a type `A` unfolded from a function over a state of type `B`.

    :param func: A function that maybe produces a value of type `A` over given a state of type `B`.
    :type func: `B -> minigun.maybe.Maybe[Tuple[A, B]]`
    :param init: An initial value of type `B`.
    :type init: `B`

    :return: A stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        result = func(init)
        if isinstance(result, m.Nothing): raise StopIteration
        value, state = result.value
        return value, unfold(func, state)
    return _thunk

def empty() -> Stream[A]:
    """Create an empty stream of type `A`.

    :return: An empty stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        raise StopIteration
    return _thunk

def singleton(value : A) -> Stream[A]:
    """Create a stream containing only one value, is empty after that value.

    :param value: A value of type `A`.
    :type value: `A`

    :return: A stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        return value, cast(Stream[A], empty())
    return _thunk

def prepend(value : A, stream : Stream[A]) -> Stream[A]:
    """Prepend a value of type `A` to a stream of type `A`.

    :param value: A value of type `A`.
    :type value: `A`
    :param stream: A stream of type `A`.
    :type stream: `Stream[A]`

    :return: A stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        return value, stream
    return _thunk

def append(stream : Stream[A], value : A) -> Stream[A]:
    """Append a value of type `A` to a stream of type `A`.

    :param stream: A stream of type `A`.
    :type stream: `Stream[A]`
    :param value: A value of type `A`.
    :type value: `A`

    :return: A stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        try:
            next_value, next_stream = stream()
            return next_value, append(next_stream, value)
        except StopIteration:
            return value, cast(Stream[A], empty())
    return _thunk

def concat(left : Stream[A], right : Stream[A]) -> Stream[A]:
    """Concatenate two streams of type `A`.

    :param left: A stream of type `A`.
    :type left: `Stream[A]`
    :param right: A stream of type `A`.
    :type right: `Stream[A]`

    :return: A stream of type `A`.
    :rtype: `Stream[A]`
    """
    def _thunk() -> StreamResult[A]:
        try:
            next_value, next_left = left()
            return next_value, concat(next_left, right)
        except StopIteration:
            return right()
    return _thunk