# External module dependencies
from typing import TypeVar, Optional, Tuple, List
import random

###############################################################################
# PRNG state
###############################################################################
State = object

def seed(value : Optional[int] = None) -> State:
    random.seed(value)
    return random.getstate()

###############################################################################
# Boolean
###############################################################################
def boolean(state : State) -> Tuple[State, bool]:
    random.setstate(state)
    result = random.randint(0, 1) == 1
    return random.getstate(), result

###############################################################################
# Numbers
###############################################################################
def natural(state : State, bound : int) -> Tuple[State, int]:
    assert bound >= 0
    random.setstate(state)
    result = random.randint(0, bound)
    return random.getstate(), result

def integer(
    state : State,
    lower_bound : int,
    upper_bound : int
    ) -> Tuple[State, int]:
    assert lower_bound <= upper_bound
    random.setstate(state)
    result = random.randint(lower_bound, upper_bound)
    return random.getstate(), result

def probability(state : State) -> Tuple[State, float]:
    random.setstate(state)
    result = random.uniform(0.0, 1.0)
    return random.getstate(), result

def real(
    state : State,
    lower_bound : float,
    upper_bound : float
    ) -> Tuple[State, float]:
    assert lower_bound <= upper_bound
    random.setstate(state)
    result = random.uniform(lower_bound, upper_bound)
    return random.getstate(), result

###############################################################################
# Sequences
###############################################################################
A = TypeVar('A')
def choose(
    state : State,
    choices : List[A],
    weights : List[int]
    ) -> Tuple[State, A]:
    assert len(choices) == len(weights)
    random.setstate(state)
    result = random.choices(choices, weights, k = 1)[0]
    return random.getstate(), result