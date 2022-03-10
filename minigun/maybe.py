# External module dependencies
from dataclasses import dataclass
from typing import (
    overload,
    Any,
    TypeVar,
    ParamSpec,
    Generic,
    Union,
    Callable,
    List
)

###############################################################################
# Maybe
###############################################################################
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
D = TypeVar('D')

P = ParamSpec('P')
R = TypeVar('R')

@dataclass
class Nothing:
    """Maybe instance that has no value."""

@dataclass
class Something(Generic[A]):
    """Maybe instance that has a value.

    :param value: A value to wrap with Something.
    :type value: `A`
    """
    value : A

#: Abstract datatype for optional values
Maybe = Union[Nothing, Something[A]]

@overload
def map(
    func : Callable[[], R]
    ) -> Maybe[R]: ...
@overload
def map(
    func : Callable[[A], R],
    a_maybe : Maybe[A]
    ) -> Maybe[R]: ...
@overload
def map(
    func : Callable[[A, B], R],
    a_maybe : Maybe[A],
    b_maybe : Maybe[B]
    ) -> Maybe[R]: ...
@overload
def map(
    func : Callable[[A, B, C], R],
    a_maybe : Maybe[A],
    b_maybe : Maybe[B],
    c_maybe : Maybe[C]
    ) -> Maybe[R]: ...
@overload
def map(
    func : Callable[[A, B, C, D], R],
    a_maybe : Maybe[A],
    b_maybe : Maybe[B],
    c_maybe : Maybe[C],
    d_maybe : Maybe[D]
    ) -> Maybe[R]: ...
def map(
    func : Callable[P, R],
    *maybes : Maybe[Any]
    ) -> Maybe[R]:
    """A variadic map function of given input maybes over types `A`, `B`, etc. to an output maybe over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param maybes: Input maybes over types `A`, `B`, etc. to map from.
    :type maybes: `Tuple[Maybe[A], Maybe[B], ...]`

    :return: A mapped output domain.
    :rtype: `Maybe[R]`
    """
    values : List[Any] = []
    for maybe in maybes:
        match maybe:
            case Nothing(): return Nothing()
            case Something(value): values.append(value)
    return Something(func(*values))