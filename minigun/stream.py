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
from . import util as u
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

StreamResult = Tuple[A, 'Stream[A]']
Stream = u.Thunk[StreamResult[A]]

def next(stream : Stream[A]) -> Tuple[m.Maybe[A], Stream[A]]:
    try:
        next_value, next_stream = stream()
        return m.Something(next_value), next_stream
    except StopIteration:
        return m.Nothing(), stream

def peek(stream : Stream[A]) -> m.Maybe[A]:
    try:
        next_value, _ = stream()
        return m.Something(next_value)
    except StopIteration:
        return m.Nothing()

def is_empty(stream : Stream[A]) -> bool:
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
    def _thunk() -> StreamResult[R]:
        next_values, next_streams = zip(*[stream() for stream in streams])
        return func(*next_values), map(func, *next_streams)
    return _thunk

def filter(func : Callable[[A], bool], stream : Stream[A]) -> Stream[A]:
    def _thunk() -> StreamResult[A]:
        next_stream = stream
        while True:
            next_value, next_stream = next_stream()
            if not func(next_value): continue
            return next_value, filter(func, next_stream)
    return _thunk

def filter_map(
    func : Callable[[A], m.Maybe[B]],
    stream : Stream[A]
    ) -> Stream[B]:
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
    def _thunk() -> StreamResult[A]:
        result = func(init)
        if isinstance(result, m.Nothing): raise StopIteration
        value, state = result.value
        return value, unfold(func, state)
    return _thunk

def empty() -> Stream[A]:
    def _thunk() -> StreamResult[A]:
        raise StopIteration
    return _thunk

def singleton(value : A) -> Stream[A]:
    def _thunk() -> StreamResult[A]:
        return value, cast(Stream[A], empty())
    return _thunk

def prepend(value : A, stream : Stream[A]) -> Stream[A]:
    def _thunk() -> StreamResult[A]:
        return value, stream
    return _thunk

def append(stream : Stream[A], value : A) -> Stream[A]:
    def _thunk() -> StreamResult[A]:
        try:
            next_value, next_stream = stream()
            return next_value, append(next_stream, value)
        except StopIteration:
            return value, cast(Stream[A], empty())
    return _thunk

def concat(left : Stream[A], right : Stream[A]) -> Stream[A]:
    def _thunk() -> StreamResult[A]:
        try:
            next_value, next_left = left()
            return next_value, concat(next_left, right)
        except StopIteration:
            return right()
    return _thunk