"""
Cardinality of generator domains.

A cardinality is the effective size of the set of values a generator can
produce. It is used by the budget allocator to decide how many attempts a
property deserves: small domains are exhausted quickly, while unbounded
domains benefit from as many attempts as the time budget allows.

Sizes are represented as non-negative floats so that unbounded domains can
be expressed as math.inf; arithmetic saturates to infinity on overflow.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Cardinality:
    """The effective size of a generator's domain.

    :param size: A non-negative count of distinct values; math.inf for
        unbounded domains.
    """

    size: float

    def __post_init__(self) -> None:
        assert self.size >= 0, "Cardinality must be non-negative"

    @property
    def is_finite(self) -> bool:
        """Whether the domain has finitely many values."""
        return self.size != math.inf

    def __add__(self, other: "Cardinality") -> "Cardinality":
        """Disjoint union: |A| + |B|."""
        return Cardinality(self.size + other.size)

    def __mul__(self, other: "Cardinality") -> "Cardinality":
        """Cartesian product: |A| * |B|."""
        if self.size == 0 or other.size == 0:
            return ZERO
        return Cardinality(self.size * other.size)

    def __pow__(self, other: "Cardinality") -> "Cardinality":
        """Exponentiation: |A| ** |B|."""
        try:
            return Cardinality(self.size**other.size)
        except OverflowError:
            return INFINITE

    def __str__(self) -> str:
        # Rendered as ASCII: the glyph U+221E crashes Windows runs whose
        # stdout is redirected and therefore ANSI-codepage encoded.
        if not self.is_finite:
            return "inf"
        if self.size >= 1e6:
            return f"{self.size:.1e}"
        if self.size >= 1000:
            return f"{int(self.size):,}"
        return str(int(self.size))


def finite(value: int) -> Cardinality:
    """A finite cardinality of the given size.

    :param value: The number of distinct values in the domain.

    :return: A finite cardinality.
    :rtype: `Cardinality`
    """
    return Cardinality(float(value))


ZERO = Cardinality(0.0)
ONE = Cardinality(1.0)
INFINITE = Cardinality(math.inf)
