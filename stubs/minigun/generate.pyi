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

from . import (
    arbitrary as a,
    order as o,
    shrink as s
)

type Sample[T] = _tuple[a.State, Maybe[s.Dissection[T]]]

type Generator[T] = Callable[[a.State], Sample[T]]

def map[**P, R](
    func: Callable[P, R],
    *generators: Generator[Any]
    ) -> Generator[R]: ...

def bind[**P, R](
    func: Callable[P, Generator[R]],
    *generators: Generator[Any]
    ) -> Generator[R]: ...

def filter[T](
    predicate: Callable[[T], _bool],
    generator: Generator[T]
    ) -> Generator[T]: ...

def constant[T](value: T) -> Generator[T]: ...

def none() -> Generator[None]: ...

def bool() -> Generator[_bool]: ...

def small_nat() -> Generator[_int]: ...

def nat() -> Generator[_int]: ...

def big_nat() -> Generator[_int]: ...

def small_int() -> Generator[_int]: ...

def int() -> Generator[_int]: ...

def big_int() -> Generator[_int]: ...

def float() -> Generator[_float]: ...

def int_range(
    lower_bound: _int,
    upper_bound: _int
    ) -> Generator[_int]: ...

def prop(bias: _float) -> Generator[_bool]: ...

def bounded_str(
    lower_bound: _int,
    upper_bound: _int,
    alphabet: _str
    ) -> Generator[_str]: ...

def str() -> Generator[_str]: ...

def word() -> Generator[_str]: ...

def tuple(*generators: Generator[Any]) -> Generator[_tuple[Any, ...]]: ...

def bounded_list[T](
    lower_bound: _int,
    upper_bound: _int,
    generator: Generator[T],
    ordered: o.Order[T] | None = None
    ) -> Generator[_list[T]]: ...

def list[T](
    generator: Generator[T],
    ordered: o.Order[T] | None = None
    ) -> Generator[_list[T]]: ...

def map_list[T](
    generators: _list[Generator[T]],
    ordered: o.Order[T] | None = None
    ) -> Generator[_list[T]]: ...

def list_append[T](
    items_gen: Generator[_list[T]],
    item_gen: Generator[T]
    ) -> Generator[_list[T]]: ...

def bounded_dict[K, V](
    lower_bound: _int,
    upper_bound: _int,
    key_generator: Generator[K],
    value_generator: Generator[V]
    ) -> Generator[_dict[K, V]]: ...

def dict[K, V](
    key_generator: Generator[K],
    value_generator: Generator[V]
    ) -> Generator[_dict[K, V]]: ...

def map_dict[K, V](
    generators: _dict[K, Generator[V]]
    ) -> Generator[_dict[K, V]]: ...

def dict_insert[K, V](
    kvs_gen: Generator[_dict[K, V]],
    key_gen: Generator[K],
    value_gen: Generator[V]
    ) -> Generator[_dict[K, V]]: ...

def bounded_set[T](
    lower_bound: _int,
    upper_bound: _int,
    generator: Generator[T]
    ) -> Generator[_set[T]]: ...

def set[T](generator: Generator[T]) -> Generator[_set[T]]: ...

def map_set[T](generators: _set[Generator[T]]) -> Generator[_set[T]]: ...

def set_add[T](
    items_gen: Generator[_set[T]],
    item_gen: Generator[T]
    ) -> Generator[_set[T]]: ...

def maybe[T](generator: Generator[T]) -> Generator[Maybe[T]]: ...

def argument_pack(
    generators: _dict[_str, Generator[Any]]
    ) -> Generator[_dict[_str, Any]]: ...

def choice[T](*generators: Generator[T]) -> Generator[T]: ...

def weighted_choice[T](
    *weighted_generators: _tuple[_int, Generator[T]]
    ) -> Generator[T]: ...

def one_of[T](values: _list[T]) -> Generator[T]: ...

def subset_of[T](values: _set[T]) -> Generator[_set[T]]: ...

def infer(T: type) -> Maybe[Generator[Any]]: ...
