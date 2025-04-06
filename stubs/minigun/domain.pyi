from dataclasses import dataclass
from typing import Any
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

from . import (
    generate as g,
    order as o,
    pretty as p
)

@dataclass
class Domain[T]:
    generate: g.Generator[T]
    print: p.Printer[T]

def bool() -> Domain[_bool]: ...

def small_nat() -> Domain[_int]: ...

def nat() -> Domain[_int]: ...

def big_nat() -> Domain[_int]: ...

def small_int() -> Domain[_int]: ...

def int() -> Domain[_int]: ...

def big_int() -> Domain[_int]: ...

def float() -> Domain[_float]: ...

def int_range(
    lower_bound: _int,
    upper_bound: _int
    ) -> Domain[_int]: ...

def bounded_str(
    lower_bound: _int,
    upper_bound: _int,
    alphabet: _str
    ) -> Domain[_str]: ...

def str() -> Domain[_str]: ...

def word() -> Domain[_str]: ...

def tuple(*domains: Domain[Any]) -> Domain[_tuple[Any, ...]]: ...

def bounded_list[T](
    lower_bound: _int,
    upper_bound: _int,
    domain: Domain[T],
    ordered: o.Order[T] | None = None
    ) -> Domain[_list[T]]: ...

def list[T](
    domain: Domain[T],
    ordered: o.Order[T] | None = None
    ) -> Domain[_list[T]]: ...

def bounded_dict[K, V](
    lower_bound: _int,
    upper_bound: _int,
    key_domain: Domain[K],
    value_domain: Domain[V]
    ) -> Domain[_dict[K, V]]: ...

def dict[K, V](
    key_domain: Domain[K],
    value_domain: Domain[V]
    ) -> Domain[_dict[K, V]]: ...

def bounded_set[T](
    lower_bound: _int,
    upper_bound: _int,
    domain: Domain[T]
    ) -> Domain[_set[T]]: ...

def set[T](domain: Domain[T]) -> Domain[_set[T]]: ...

def maybe[T](domain: Domain[T]) -> Domain[Maybe[T]]: ...

def argument_pack(
    ordering: _list[_str],
    domains: _dict[_str, Domain[Any]]
    ) -> Domain[_dict[_str, Any]]: ...
