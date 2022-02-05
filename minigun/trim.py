# External module dependencies
from typing import TypeVar, Callable, Tuple

# Internal module dependencies
from . import maybe as m
from . import stream as s

###############################################################################
# Trimmer
###############################################################################
A = TypeVar('A')
Trimmer = Callable[[A], s.Stream[A]]

###############################################################################
# Numbers
###############################################################################
def integer(target : int) -> Trimmer[int]:
    def _impl(value : int) -> s.Stream[int]:
        def _towards(current : int) -> m.Maybe[Tuple[int, int]]:
            if current == value: return m.Nothing()
            half_diff = int((value - current) / 2)
            if half_diff == 0: return m.Something((current, current))
            return m.Something((current + half_diff, current))
        return s.unfold(_towards, target)
    return _impl

def decimal(target : float) -> Trimmer[float]:
    def _impl(value : float) -> s.Stream[float]:
        def _towards(current : float) -> m.Maybe[Tuple[float, float]]:
            if current == value: return m.Nothing()
            half_diff = (value - current) / 2
            if half_diff == 0.0: return m.Something((current, current))
            return m.Something((current + half_diff, current))
        return s.unfold(_towards, target)
    return _impl
