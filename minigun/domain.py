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
from functools import partial

# Internal module dependencies
from . import stream as s
from . import maybe as m
from . import trim as t

###############################################################################
# Domain state
###############################################################################
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
D = TypeVar('D')

P = ParamSpec('P')
R = TypeVar('R')

Domain = Tuple[A, s.Stream['Domain[A]']]

def head(domain : Domain[A]) -> A:
    return domain[0]

def tail(domain : Domain[A]) -> s.Stream[Domain[A]]:
    return domain[1]

@overload
def map(
    func : Callable[[], R]
    ) -> Domain[R]: ...
@overload
def map(
    func : Callable[[A], R],
    a_domain : Domain[A]
    ) -> Domain[R]: ...
@overload
def map(
    func : Callable[[A, B], R],
    a_domain : Domain[A],
    b_domain : Domain[B]
    ) -> Domain[R]: ...
@overload
def map(
    func : Callable[[A, B, C], R],
    a_domain : Domain[A],
    b_domain : Domain[B],
    c_domain : Domain[C]
    ) -> Domain[R]: ...
@overload
def map(
    func : Callable[[A, B, C, D], R],
    a_domain : Domain[A],
    b_domain : Domain[B],
    c_domain : Domain[C],
    d_domain : Domain[D]
    ) -> Domain[R]: ...
def map(
    func : Callable[P, R],
    *domains : Domain[Any]
    ) -> Domain[R]:
    heads, tails = zip(*domains)
    return func(*heads), s.map(partial(map, func), *tails)

@overload
def bind(
    func : Callable[[], Domain[R]]
    ) -> Domain[R]: ...
@overload
def bind(
    func : Callable[[A], Domain[R]],
    a_domain : Domain[A]
    ) -> Domain[R]: ...
@overload
def bind(
    func : Callable[[A, B], Domain[R]],
    a_domain : Domain[A],
    b_domain : Domain[B]
    ) -> Domain[R]: ...
@overload
def bind(
    func : Callable[[A, B, C], Domain[R]],
    a_domain : Domain[A],
    b_domain : Domain[B],
    c_domain : Domain[C]
    ) -> Domain[R]: ...
@overload
def bind(
    func : Callable[[A, B, C, D], Domain[R]],
    a_domain : Domain[A],
    b_domain : Domain[B],
    c_domain : Domain[C],
    d_domain : Domain[D]
    ) -> Domain[R]: ...
def bind(
    func : Callable[P, Domain[R]],
    *domains : Domain[Any]
    ) -> Domain[R]:
    heads, tails = zip(*domains)
    result_head, result_tail = func(*heads)
    return result_head, s.concat(
        s.map(partial(bind, func), *tails),
        result_tail
    )

def singleton(value : A) -> Domain[A]:
    return value, cast(s.Stream[Domain[A]], s.empty())

def union(value : A, case : Domain[A]) -> Domain[A]:
    return value, s.singleton(case)

def maybe(case : Domain[A]) -> Domain[m.Maybe[A]]:
    return (
        m.Something(case[0]),
        s.prepend(
            singleton(m.Nothing()),
            s.map(maybe, case[1])
        )
    )

def concat(
    domain : Domain[A],
    stream : s.Stream[Domain[A]]
    ) -> Domain[A]:
    domain_value, domain_stream = domain
    return domain_value, s.concat(domain_stream, stream)

def unary(
    x_trim : t.Trimmer[A],
    value : A
    ) -> Domain[A]:
    return value, s.map(partial(unary, x_trim), x_trim(value))

def binary(
    x_trim : t.Trimmer[A],
    y_trim : t.Trimmer[A],
    value : A
    ) -> Domain[A]:
    return value, s.map(partial(binary, y_trim, x_trim), x_trim(value))