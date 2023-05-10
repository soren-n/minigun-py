# External module dependencies
from dataclasses import dataclass
from typing import (
    get_origin,
    get_args,
    TypeVar,
    ParamSpec,
    TypeAlias,
    Generic,
    Callable,
    Union,
    Any,
    List
)

###############################################################################
# Maybe
###############################################################################
T = TypeVar('T')
P = ParamSpec('P')
R = TypeVar('R')

@dataclass
class Nothing(Generic[T]):
    """Maybe instance that has no value."""

@dataclass
class Something(Generic[T]):
    """Maybe instance that has a value.

    :param value: A value to wrap with Something.
    :type value: `A`
    """
    value: T

#: Abstract datatype for optional values
Maybe: TypeAlias = (
    Nothing[T] |
    Something[T]
)

def is_maybe(T: type):
    origin = get_origin(T)
    if origin is None:
        if T == Nothing: return True
        return T == Something
    if not (origin is Union): return False
    args = get_args(T)
    if len(args) != 2: return False
    if not (get_origin(args[0]) is Nothing): return False
    if not (get_origin(args[1]) is Something): return False
    return True

def map(
    func : Callable[P, R],
    *maybes : Maybe[Any]
    ) -> Maybe[R]:
    """A variadic map function of given input maybes over types `A`, `B`, etc. to an output maybe over type `R`.

    :param func: A function mapping the input values of type `A`, `B`, etc. to an output value of type `R`.
    :type func: `A x B x ... -> R`
    :param maybes: Input maybes over types `A`, `B`, etc. to map from.
    :type maybes: `Tuple[Maybe[T], Maybe[B], ...]`

    :return: A mapped output domain.
    :rtype: `Maybe[R]`
    """
    def _apply(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    values : List[Any] = []
    for maybe in maybes:
        match maybe:
            case Nothing(): return Nothing()
            case Something(value): values.append(value)
    return Something(_apply(*values))