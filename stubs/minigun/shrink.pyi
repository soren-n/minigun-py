from typing import Any, Callable
from builtins import (
    bool as _bool,
    float as _float,
    int as _int,
    str as _str,
    tuple as _tuple
)

from returns.maybe import Maybe

from . import stream as fs

type Dissection[T] = _tuple[T, fs.Stream['Dissection[T]']]

type Shrinker[T] = Callable[[T], Dissection[T]]

def head[T](dissection: Dissection[T]) -> T: ...

def tail[T](dissection: Dissection[T]) -> fs.Stream[Dissection[T]]: ...

def map[**P, R](
    func: Callable[P, R],
    *dissections: Dissection[Any]
    ) -> Dissection[R]: ...

def bind[**P, R](
    func: Callable[P, Dissection[R]],
    *dissections: Dissection[Any]
    ) -> Dissection[R]: ...

def filter[T](
    predicate: Callable[[T], _bool],
    dissection: Dissection[T]
    ) -> Maybe[Dissection[T]]: ...

def concat[T](
    left: Dissection[T],
    right: Dissection[T]
    ) -> Dissection[T]: ...

def prepend[T](value: T, dissection: Dissection[T]) -> Dissection[T]: ...

def append[T](dissection: Dissection[T], value: T) -> Dissection[T]: ...

def singleton[T](value: T) -> Dissection[T]: ...

type Trimmer[T] = Callable[[T], fs.Stream[T]]

def unfold[T](value: T, *trimmers: Trimmer[T]) -> Dissection[T]: ...

def bool() -> Shrinker[_bool]: ...

def int(target: _int) -> Shrinker[_int]: ...

def float(target: _float) -> Shrinker[_float]: ...

def str() -> Shrinker[_str]: ...
