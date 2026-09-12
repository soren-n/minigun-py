"""Refining generators with map: even and odd natural numbers."""

import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


# -- start: generators --
def even_natural() -> g.Generator[int]:
    def _impl(i: int) -> int:
        return i * 2

    return g.map(_impl, g.nats())


def odd_natural() -> g.Generator[int]:
    def _impl(i: int) -> int:
        return ((i + 1) * 2) - 1

    return g.map(_impl, g.nats())


# -- end: generators --


# -- start: properties --
@context(even_natural())
@prop("Even natural numbers are even")
def _even_is_even(n: int) -> bool:
    return n % 2 == 0


@context(odd_natural())
@prop("Odd natural numbers are odd")
def _odd_is_odd(n: int) -> bool:
    return n % 2 == 1


# -- end: properties --

spec = conj(_even_is_even, _odd_is_odd)

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
