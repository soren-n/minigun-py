"""
Random source

The random source for all generation in Minigun is a dedicated
``random.Random`` instance. Draws never touch the global ``random`` module,
so a test run cannot disturb the host program and independent runs cannot
disturb each other.

Reproducibility comes from seeding, parallel safety from forking: a child
source is seeded from a draw on its parent, so children are deterministic
given the parent's seed and independent of one another. Draw functions take
the source and return the drawn value; the source advances in place.

Example::

        import minigun.arbitrary as a

        rng = a.seed(42)
        value = a.draw_int(rng, 1, 100)
        child = a.fork(rng)
"""

from __future__ import annotations

import random
from collections.abc import Sequence

#: The random source from which values are drawn.
type Rng = random.Random


__all__ = [
    "Rng",
    "seed",
    "fork",
    "draw_bool",
    "draw_int",
    "draw_float",
    "probability",
    "choice",
    "weighted_choice",
]


###############################################################################
# Sources
###############################################################################
def seed(value: int | str | None = None) -> Rng:
    """Create a random source.

    :param value: The seed; when None the source is seeded from operating
        system entropy.

    :return: A fresh random source.
    """
    return random.Random(value)


def fork(rng: Rng) -> Rng:
    """Create a child source seeded from a draw on the parent.

    The child is deterministic given the parent's history and independent
    of the parent's subsequent draws and of other children.

    :param rng: The parent source; advanced by one draw.

    :return: A fresh child source.
    """
    return random.Random(rng.getrandbits(64))


###############################################################################
# Draws
###############################################################################
def draw_bool(rng: Rng) -> bool:
    """Draw a boolean, each value equally likely."""
    return rng.getrandbits(1) == 1


def draw_int(rng: Rng, lower_bound: int, upper_bound: int) -> int:
    """Draw an integer ``n`` with ``lower_bound <= n <= upper_bound``.

    :raises ValueError: When ``lower_bound > upper_bound``.
    """
    if lower_bound > upper_bound:
        raise ValueError(
            f"draw_int requires lower_bound <= upper_bound, got "
            f"{lower_bound} > {upper_bound}"
        )
    return rng.randint(lower_bound, upper_bound)


def draw_float(rng: Rng, lower_bound: float, upper_bound: float) -> float:
    """Draw a float ``x`` with ``lower_bound <= x <= upper_bound``.

    :raises ValueError: When ``lower_bound > upper_bound``.
    """
    if lower_bound > upper_bound:
        raise ValueError(
            f"draw_float requires lower_bound <= upper_bound, got "
            f"{lower_bound} > {upper_bound}"
        )
    return rng.uniform(lower_bound, upper_bound)


def probability(rng: Rng) -> float:
    """Draw a float ``p`` with ``0.0 <= p < 1.0``."""
    return rng.random()


def choice[T](rng: Rng, items: Sequence[T]) -> T:
    """Draw one item, each equally likely.

    :raises ValueError: When ``items`` is empty.
    """
    if len(items) == 0:
        raise ValueError("choice requires at least one item")
    return rng.choice(items)


def weighted_choice[T](
    rng: Rng, weights: Sequence[int], items: Sequence[T]
) -> T:
    """Draw one item with probability proportional to its weight.

    :raises ValueError: When ``items`` is empty, the lengths differ, a
        weight is negative, or all weights are zero.
    """
    if len(items) == 0:
        raise ValueError("weighted_choice requires at least one item")
    if len(items) != len(weights):
        raise ValueError(
            f"weighted_choice received {len(weights)} weights for "
            f"{len(items)} items"
        )
    if any(weight < 0 for weight in weights):
        raise ValueError("weighted_choice weights must be non-negative")
    if sum(weights) == 0:
        raise ValueError("weighted_choice requires a positive total weight")
    return rng.choices(items, weights, k=1)[0]
