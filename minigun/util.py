# External module dependencies
from typing import TypeVar, Callable

###############################################################################
# Functional helpers
###############################################################################
T = TypeVar('T')
Thunk = Callable[[], T]

A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
def compose(f : Callable[[B], C], g : Callable[[A], B]) -> Callable[[A], C]:
    def _impl(x : A) -> C: return f(g(x))
    return _impl