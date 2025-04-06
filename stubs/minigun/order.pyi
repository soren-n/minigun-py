from typing import Callable
from enum import Enum
from builtins import (
    float as _float,
    int as _int,
    str as _str
)

class Total(Enum):
    Eq = 'Eq'
    Lt = 'Lt'
    Gt = 'Gt'

type Order[T] = Callable[[T, T], Total]

def int(left: _int, right: _int) -> Total: ...

def float(epsilon: _float) -> Order[_float]: ...

def str(left: _str, right: _str) -> Total: ...

def sort[T](order: Order[T], items: list[T]) -> list[T]: ...
