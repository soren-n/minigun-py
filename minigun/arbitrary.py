"""
PRNG State Management and Random Generation

This module provides pure functional random number generation with explicit state
threading. It implements the foundation for all random generation in Minigun,
ensuring reproducible and deterministic test case generation.

Key Components:
    - State: PRNG state tuple for deterministic generation
    - seed(): Initialize state from optional integer seed
    - Primitive generators: bool, nat, int, float, probability
    - Choice utilities: choice, weighted_choice for selection

The module follows functional programming principles with immutable state and
pure functions that explicitly thread PRNG state through computations.

Example:
    ```python
    import minigun.arbitrary as a

    # Initialize state
    state = a.seed(42)

    # Generate values with explicit state threading
    state, value1 = a.int(state, 1, 100)
    state, value2 = a.bool(state)
    state, chosen = a.choice(state, ["a", "b", "c"])
    ```
"""

# External module dependencies
import random

###############################################################################
# Localizing intrinsics
###############################################################################
from builtins import bool as _bool
from builtins import float as _float
from builtins import int as _int
from builtins import list as _list
from builtins import tuple as _tuple
from typing import Any

###############################################################################
# PRNG state
###############################################################################

#: A state from which to generate a random value.
type State = _tuple[Any, ...]


def seed(value: _int | None = None) -> State:
    """Constructor to seed an initial state for Minigun's PRNG module.

    :param value: An optional integer to be used as the seed.
    :type value: int, optional

    :return: An initial state for random generation.
    :rtype: `State`
    """
    random.seed(value)
    return random.getstate()


###############################################################################
# Boolean
###############################################################################
def bool(state: State) -> _tuple[State, _bool]:
    """Generate a random boolean value.

    :param state: A state from which to generate a random value.
    :type state: `State`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, bool]`
    """
    random.setstate(state)
    result = random.randint(0, 1) == 1
    return random.getstate(), result


###############################################################################
# Numbers
###############################################################################
def nat(
    state: State, lower_bound: _int, upper_bound: _int
) -> _tuple[State, _int]:
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
    if lower_bound == upper_bound:
        return state, upper_bound
    random.setstate(state)
    result = random.randint(lower_bound, upper_bound)
    return random.getstate(), result


def int(
    state: State, lower_bound: _int, upper_bound: _int
) -> _tuple[State, _int]:
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
    if lower_bound == upper_bound:
        return state, lower_bound
    random.setstate(state)
    result = random.randint(lower_bound, upper_bound)
    return random.getstate(), result


def probability(state: State) -> _tuple[State, _float]:
    """Generate a random float value :code:`n` in the range :code:`0.0 <= n <= 1.0`.

    :param state: A state from which to generate a random value.
    :type state: `State`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `Tuple[State, float]`
    """
    random.setstate(state)
    result = random.uniform(0.0, 1.0)
    return random.getstate(), result


def float(
    state: State, lower_bound: _float, upper_bound: _float
) -> _tuple[State, _float]:
    """Generate a random float value :code:`n` in the range :code:`lower_bound <= n <= upper_bound`.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param lower_bound: A min bound for the generated value, must be less than or equal to `upper_bound`.
    :type lower_bound: `float`
    :param upper_bound: A max bound for the generated value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `float`

    :return: A tuple of a modified state taken after random generation and a generated random value.
    :rtype: `tuple[State, float]`
    """
    assert lower_bound <= upper_bound
    if lower_bound == upper_bound:
        return state, upper_bound
    random.setstate(state)
    result = random.uniform(lower_bound, upper_bound)
    return random.getstate(), result


###############################################################################
# Sequences
###############################################################################
def weighted_choice[T](
    state: State, weights: _list[_int], choices: _list[T]
) -> _tuple[State, T]:
    """Select a random item from a list of weighted choices.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param choices: A list of items to choose from, must have same length as `weights`.
    :type choices: `List[T]`
    :param weights: A list of chances for each item in `choices`, must have same length as `choices`.
    :type weights: `List[int]`

    :return: A tuple of a modified state taken after random choice of a random item.
    :rtype: `tuple[State, T]`
    """
    assert len(choices) > 0
    assert len(choices) == len(weights)
    if len(choices) == 1:
        return state, choices[0]
    random.setstate(state)
    result = random.choices(choices, weights, k=1)[0]
    return random.getstate(), result


def choice[T](state: State, choices: _list[T]) -> tuple[State, T]:
    """Select a random item from a list of choices.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param choices: A list of items to choose from.
    :type choices: `List[T]`

    :return: A tuple of a modified state taken after random choice of a random item.
    :rtype: `tuple[State, T]`
    """
    return weighted_choice(state, [1] * len(choices), choices)
