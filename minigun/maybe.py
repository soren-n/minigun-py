# External module dependencies
from dataclasses import dataclass
from typing import TypeVar, Generic, Union, Callable

###############################################################################
# Maybe
###############################################################################
A = TypeVar('A')

@dataclass
class Nothing: pass

@dataclass
class Something(Generic[A]):
    value : A

Maybe = Union[Nothing, Something[A]]

B = TypeVar('B')
def map(func : Callable[[A], B], maybe : Maybe[A]) -> Maybe[B]:
    if isinstance(maybe, Something):
        return Something(func(maybe.value))
    return Nothing()