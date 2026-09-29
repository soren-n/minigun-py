"""Preconditions over several parameters, and declared attempts."""

import random

import minigun.generate as g
from minigun import assume, check
from minigun.specify import conj, context, prop


# -- start: assume --
@context(g.int_range(1, 20), g.int_range(1, 20), g.int_range(1, 20))
@prop("Sides of a proper triangle have a positive area by Heron's formula")
def _heron(a: int, b: int, c: int) -> bool:
    assume(a + b > c and a + c > b and b + c > a)
    # Sixteen times the squared area, in exact integers.
    return (a + b + c) * (-a + b + c) * (a - b + c) * (a + b - c) > 0


# -- end: assume --


# -- start: attempts --
@prop("The mean of uniform samples is close to one half", attempts=20)
def _mean(rng: random.Random) -> bool:
    # A statistical law: each attempt is a whole experiment, and the
    # tolerance is eleven standard errors, so a false alarm is negligible.
    mean = sum(rng.random() for _ in range(1000)) / 1000
    return abs(mean - 0.5) < 0.1


# -- end: attempts --

spec = conj(_heron, _mean)

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
