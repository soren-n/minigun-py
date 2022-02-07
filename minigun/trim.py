# External module dependencies
from typing import TypeVar, Callable, Tuple
import math

# Internal module dependencies
from . import stream as s
from . import maybe as m

###############################################################################
# Trimmer
###############################################################################
A = TypeVar('A')
Trimmer = Callable[[A], s.Stream[A]]

###############################################################################
# Numbers
###############################################################################
def integer(target : int) -> Trimmer[int]:
    def _impl(initial : int) -> s.Stream[int]:
        def _towards(
            state : Tuple[int, int]
            ) -> m.Maybe[Tuple[int, Tuple[int, int]]]:
            value, current = state
            if current == value: return m.Nothing()
            _value = current + int((value - current) / 2)
            return m.Something((_value, (_value, current)))
        return s.unfold(_towards, (initial, target))
    return _impl

def real(target : float) -> Trimmer[float]:
    def _impl(initial : float) -> s.Stream[float]:
        def _towards(
            state : Tuple[int, float, float]
            ) -> m.Maybe[Tuple[float, Tuple[int, float, float]]]:
            count, value, current = state
            if count == 0: return m.Nothing()
            if current == value: return m.Nothing()
            _count = count - 1
            _value = current + ((value - current) / 2)
            return m.Something((_value, (_count, _value, current)))
        return s.unfold(_towards, (15, initial, target))
    return _impl

def real_integer_part(target : float) -> Trimmer[float]:
    def _impl(initial : float) -> s.Stream[float]:
        def _towards(
            state : Tuple[float, int]
            ) -> m.Maybe[Tuple[float, Tuple[float, int]]]:
            value, current = state
            value_f, value_i = math.modf(value)
            if current == int(value_i): return m.Nothing()
            _value = current + value_f + int((value_i - current) / 2)
            return m.Something((_value, (_value, current)))
        return s.unfold(_towards, (initial, int(target)))
    return _impl

def real_fractional_part(target : float) -> Trimmer[float]:
    def _impl(initial : float) -> s.Stream[float]:
        def _towards(
            state : Tuple[int, float, float]
            ) -> m.Maybe[Tuple[float, Tuple[int, float, float]]]:
            count, value, current = state
            value_f, value_i = math.modf(value)
            if count == 0: return m.Nothing()
            if current == value_f: return m.Nothing()
            _value = value_i + current + ((value_f - current) / 2)
            return m.Something((_value, (count - 1, _value, current)))
        return s.unfold(_towards, (10, initial, math.modf(target)[0]))
    return _impl

###############################################################################
# String
###############################################################################
def string() -> Trimmer[str]:
    def _impl(initial : str) -> s.Stream[str]:
        past = len(initial)
        def _towards(index : int) -> m.Maybe[Tuple[str, int]]:
            if index == past: return m.Nothing()
            _value = initial[:index] + initial[index + 1:]
            return m.Something((_value, index + 1))
        return s.unfold(_towards, 0)
    return _impl