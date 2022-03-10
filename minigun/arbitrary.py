# External module dependencies
from typing import Any, TypeVar, NewType, Optional, Tuple, List
import random

###############################################################################
# Localizing intrinsics
###############################################################################
_Bool = bool
_Int = int
_Float = float

###############################################################################
# PRNG state
###############################################################################

#: A state from which to generate a random value.
State = NewType('State', Tuple[Any, ...])

def seed(value : Optional[_Int] = None) -> State:
    """Constructor to seed an initial state for Minigun's PRNG module.

    :param value: An optional integer to be used as the seed.
    :type value: int, optional

    :return: An initial state for random generation.
    :rtype: `State`
    """
    random.seed(value)
    return State(random.getstate())

###############################################################################
# Boolean
###############################################################################
def bool(state : State) -> Tuple[State, _Bool]:
    """ Generate a random boolean value.

    :param state: A state from which to generate a random value.
    :type state: `State`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, bool]`
    """
    random.setstate(state)
    result = random.randint(0, 1) == 1
    return State(random.getstate()), result

###############################################################################
# Numbers
###############################################################################
def nat(
    state : State,
    lower_bound : _Int,
    upper_bound : _Int
    ) -> Tuple[State, _Int]:
    """Generate a random integer value :code:`n` in the range :code:`0 <= n <= bound`.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param lower_bound: A min bound for the generated value, must be greater than or equal to zero, and less than or equal to upper_bound.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the generated value, must be greater than or equal to the lower_bound.
    :type upper_bound: `int`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, int]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound
    if lower_bound == upper_bound: return state, upper_bound
    random.setstate(state)
    result = random.randint(lower_bound, upper_bound)
    return State(random.getstate()), result

def int(
    state : State,
    lower_bound : _Int,
    upper_bound : _Int
    ) -> Tuple[State, _Int]:
    """Generate a random integer value :code:`n` in the range :code:`lower_bound <= n <= upper_bound`.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param lower_bound: A min bound for the generated value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the generated value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, int]`
    """
    assert lower_bound <= upper_bound
    if lower_bound == upper_bound: return state, lower_bound
    random.setstate(state)
    result = random.randint(lower_bound, upper_bound)
    return State(random.getstate()), result

def probability(state : State) -> Tuple[State, _Float]:
    """Generate a random float value :code:`n` in the range :code:`0.0 <= n <= 1.0`.

    :param state: A state from which to generate a random value.
    :type state: `State`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, float]`
    """
    random.setstate(state)
    result = random.uniform(0.0, 1.0)
    return State(random.getstate()), result

def float(
    state : State,
    lower_bound : _Float,
    upper_bound : _Float
    ) -> Tuple[State, _Float]:
    """Generate a random float value :code:`n` in the range :code:`lower_bound <= n <= upper_bound`.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param lower_bound: A min bound for the generated value, must be less than or equal to `upper_bound`.
    :type lower_bound: `float`
    :param upper_bound: A max bound for the generated value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `float`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, float]`
    """
    assert lower_bound <= upper_bound
    if lower_bound == upper_bound: return state, upper_bound
    random.setstate(state)
    result = random.uniform(lower_bound, upper_bound)
    return State(random.getstate()), result

###############################################################################
# Sequences
###############################################################################
A = TypeVar('A')
def weighted_choice(
    state : State,
    weights : List[_Int],
    choices : List[A]
    ) -> Tuple[State, A]:
    """Select a random item from a list of weighted choices.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param choices: A list of items to choose from, must have same length as `weights`.
    :type choices: `List[A]`
    :param weights: A list of chances for each item in `choices`, must have same length as `choices`.
    :type weights: `List[int]`

    :return: A tuple of a modified state taken after random choice of a random item.
    :rtype: `Tuple[State, A]`
    """
    assert len(choices) > 0
    assert len(choices) == len(weights)
    if len(choices) == 1: return state, choices[0]
    random.setstate(state)
    result = random.choices(choices, weights, k = 1)[0]
    return State(random.getstate()), result

def choice(
    state : State,
    choices : List[A]
    ) -> Tuple[State, A]:
    """Select a random item from a list of choices.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param choices: A list of items to choose from.
    :type choices: `List[A]`

    :return: A tuple of a modified state taken after random choice of a random item.
    :rtype: `Tuple[State, A]`
    """
    return weighted_choice(state, [1] * len(choices), choices)