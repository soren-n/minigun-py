"""
PRNG State Management and Random Generation

This module provides random number generation with explicit state threading.
It implements the foundation for all random generation in Minigun, ensuring
reproducible and deterministic test case generation: a run is fully
determined by its seed.

Key Components:
    - State: PRNG state for deterministic generation
    - seed(): Initialize state from an optional integer seed
    - Primitive draws: draw_bool, draw_nat, draw_int, draw_float, probability
    - Choice utilities: choice, weighted_choice for selection

State is a dedicated random.Random instance: draws never touch the global
random module, so a test run cannot disturb the host program's RNG and
concurrent runs cannot disturb each other. Functions thread the state
explicitly (state in, state out) to keep sampler code order-explicit.

Example::

        import minigun.arbitrary as a

        # Initialize state
        state = a.seed(42)

        # Generate values with explicit state threading
        state, value1 = a.draw_int(state, 1, 100)
        state, value2 = a.draw_bool(state)
        state, chosen = a.choice(state, ["a", "b", "c"])
"""

# External module dependencies
import random

###############################################################################
# PRNG state
###############################################################################

#: A state from which to generate random values.
type State = random.Random


def seed(value: int | None = None) -> State:
    """Create an initial state for Minigun's random generation.

    :param value: An optional integer to be used as the seed; when None
        the state is seeded from operating system entropy.
    :type value: int, optional

    :return: An initial state for random generation.
    :rtype: `State`
    """
    return random.Random(value)


###############################################################################
# Boolean
###############################################################################
def draw_bool(state: State) -> tuple[State, bool]:
    """Draw a random boolean value.

    :param state: A state from which to draw a random value.
    :type state: `State`

    :return: A tuple of the advanced state and the drawn value.
    :rtype: `tuple[State, bool]`
    """
    return state, state.getrandbits(1) == 1


###############################################################################
# Numbers
###############################################################################
def draw_nat(
    state: State, lower_bound: int, upper_bound: int
) -> tuple[State, int]:
    """Draw a random natural number :code:`n` in the range :code:`lower_bound <= n <= upper_bound`.

    :param state: A state from which to draw a random value.
    :type state: `State`
    :param lower_bound: A min bound for the drawn value, must be greater than or equal to zero, and less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the drawn value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A tuple of the advanced state and the drawn value.
    :rtype: `tuple[State, int]`
    """
    assert 0 <= lower_bound
    assert lower_bound <= upper_bound
    return state, state.randint(lower_bound, upper_bound)


def draw_int(
    state: State, lower_bound: int, upper_bound: int
) -> tuple[State, int]:
    """Draw a random integer value :code:`n` in the range :code:`lower_bound <= n <= upper_bound`.

    :param state: A state from which to draw a random value.
    :type state: `State`
    :param lower_bound: A min bound for the drawn value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the drawn value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A tuple of the advanced state and the drawn value.
    :rtype: `tuple[State, int]`
    """
    assert lower_bound <= upper_bound
    return state, state.randint(lower_bound, upper_bound)


def probability(state: State) -> tuple[State, float]:
    """Draw a random float value :code:`n` in the range :code:`0.0 <= n <= 1.0`.

    :param state: A state from which to draw a random value.
    :type state: `State`

    :return: A tuple of the advanced state and the drawn value.
    :rtype: `tuple[State, float]`
    """
    return state, state.random()


def draw_float(
    state: State, lower_bound: float, upper_bound: float
) -> tuple[State, float]:
    """Draw a random float value :code:`n` in the range :code:`lower_bound <= n <= upper_bound`.

    :param state: A state from which to draw a random value.
    :type state: `State`
    :param lower_bound: A min bound for the drawn value, must be less than or equal to `upper_bound`.
    :type lower_bound: `float`
    :param upper_bound: A max bound for the drawn value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `float`

    :return: A tuple of the advanced state and the drawn value.
    :rtype: `tuple[State, float]`
    """
    assert lower_bound <= upper_bound
    return state, state.uniform(lower_bound, upper_bound)


###############################################################################
# Sequences
###############################################################################
def weighted_choice[T](
    state: State, weights: list[int], choices: list[T]
) -> tuple[State, T]:
    """Select a random item from a list of weighted choices.

    :param state: A state from which to draw a random value.
    :type state: `State`
    :param weights: A list of chances for each item in `choices`, must have same length as `choices`.
    :type weights: `list[int]`
    :param choices: A list of items to choose from, must have same length as `weights`.
    :type choices: `list[T]`

    :return: A tuple of the advanced state and the chosen item.
    :rtype: `tuple[State, T]`
    """
    assert len(choices) > 0
    assert len(choices) == len(weights)
    return state, state.choices(choices, weights, k=1)[0]


def choice[T](state: State, choices: list[T]) -> tuple[State, T]:
    """Select a random item from a list of choices.

    :param state: A state from which to draw a random value.
    :type state: `State`
    :param choices: A list of items to choose from.
    :type choices: `list[T]`

    :return: A tuple of the advanced state and the chosen item.
    :rtype: `tuple[State, T]`
    """
    assert len(choices) > 0
    return state, state.choice(choices)
