from typing import Any, Callable
from builtins import (
    bool as _bool,
    dict as _dict,
    float as _float,
    int as _int,
    list as _list,
    set as _set,
    str as _str,
    tuple as _tuple
)

from returns.maybe import Maybe
import typeset as ts

type Printer[T] = Callable[[T], ts.Layout]

def render(layout: ts.Layout) -> _str: ...

def bool() -> Printer[_bool]: ...

def int() -> Printer[_int]: ...

def float(digits: _int = 2) -> Printer[_float]: ...

def str() -> Printer[_str]: ...

def tuple(*printers: Printer[Any]) -> Printer[_tuple[Any, ...]]: ...

def list[T](printer: Printer[T]) -> Printer[_list[T]]: ...

def dict[K, V](
    key_printer: Printer[K],
    value_printer: Printer[V]
    ) -> Printer[_dict[K, V]]: ...

def set[T](printer: Printer[T]) -> Printer[_set[T]]: ...

def maybe[T](printer: Printer[T]) -> Printer[Maybe[T]]: ...

def argument_pack(
    ordering: _list[_str],
    printers: _dict[_str, Printer[Any]]
    ) -> Printer[_dict[_str, Any]]: ...

def infer(T: type) -> Maybe[Printer[Any]]: ...
