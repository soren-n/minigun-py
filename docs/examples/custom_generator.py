"""A custom generator and shrinker for a user type."""

from collections.abc import Iterator
from dataclasses import dataclass

import minigun.arbitrary as a
import minigun.cardinality as c
import minigun.generate as g
import minigun.shrink as s
import minigun.stream as fs
from minigun import check
from minigun.specify import context, prop


# -- start: type --
@dataclass(frozen=True)
class Interval:
    """A closed interval of integers, ``lower <= upper``."""

    lower: int
    upper: int


# -- end: type --


# -- start: shrinker --
def _narrow(interval: Interval) -> fs.Stream[Interval]:
    """Shrink the width toward zero, most aggressive first."""

    def _iterate() -> Iterator[Interval]:
        width = interval.upper - interval.lower
        for candidate in s.integer(0)(width).shrinks():
            yield Interval(interval.lower, interval.lower + candidate.head)

    return _iterate


def _recenter(interval: Interval) -> fs.Stream[Interval]:
    """Move the interval toward zero, keeping its width."""

    def _iterate() -> Iterator[Interval]:
        width = interval.upper - interval.lower
        for candidate in s.integer(0)(interval.lower).shrinks():
            yield Interval(candidate.head, candidate.head + width)

    return _iterate


def interval_shrinker(interval: Interval) -> s.Dissection[Interval]:
    return s.unfold(interval, _narrow, _recenter)


# -- end: shrinker --


# -- start: generator --
def intervals(bound: int) -> g.Generator[Interval]:
    def _sample(rng: a.Rng) -> s.Dissection[Interval] | None:
        lower = a.draw_int(rng, -bound, bound)
        upper = a.draw_int(rng, lower, bound)
        return interval_shrinker(Interval(lower, upper))

    # (2 * bound + 1) endpoints; ordered pairs with lower <= upper.
    endpoints = 2 * bound + 1
    return g.Generator(_sample, c.finite(endpoints * (endpoints + 1) // 2))


# -- end: generator --


@context(intervals(1000))
@prop("Intervals are well formed")
def _well_formed(interval: Interval) -> bool:
    return interval.lower <= interval.upper


spec = _well_formed

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
