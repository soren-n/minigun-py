"""Properties of cardinality arithmetic."""

import math

import minigun.cardinality as c
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


def _cardinalities() -> g.Generator[c.Cardinality]:
    def _finite(exponent: int) -> c.Cardinality:
        return c.Cardinality(float(10**exponent))

    return g.weighted_choice(
        (6, g.map(c.finite, g.int_range(0, 1000))),
        (2, g.map(_finite, g.int_range(0, 200))),
        (1, g.constant(c.INFINITE)),
    )


@context(_cardinalities(), _cardinalities())
@prop("addition and multiplication are commutative")
def _commutative(a: c.Cardinality, b: c.Cardinality) -> bool:
    return a + b == b + a and a * b == b * a


def _close(x: c.Cardinality, y: c.Cardinality) -> bool:
    """Equal up to the rounding of the float-backed size."""
    return x.size == y.size or math.isclose(x.size, y.size, rel_tol=1e-9)


@context(_cardinalities(), _cardinalities(), _cardinalities())
@prop("addition and multiplication are associative up to rounding")
def _associative(a: c.Cardinality, b: c.Cardinality, k: c.Cardinality) -> bool:
    return _close((a + b) + k, a + (b + k)) and _close((a * b) * k, a * (b * k))


@context(_cardinalities())
@prop("zero and one are the identities, and zero annihilates")
def _identities(a: c.Cardinality) -> bool:
    return a + c.ZERO == a and a * c.ONE == a and a * c.ZERO == c.ZERO


@context(_cardinalities(), _cardinalities())
@prop("arithmetic saturates at infinity and never leaves the domain")
def _saturates(a: c.Cardinality, b: c.Cardinality) -> bool:
    results = [a + b, a * b, a**b]
    if not a.is_finite and b != c.ZERO:
        if (a + b).is_finite or (a * b).is_finite:
            return False
    return all(r.size >= 0 and not math.isnan(r.size) for r in results)


@context(g.int_range(0, 60), g.int_range(0, 60))
@prop("exponentiation of finite sizes agrees with integer arithmetic")
def _power(base: int, exponent: int) -> bool:
    result = c.finite(base) ** c.finite(exponent)
    return result.is_finite and _close(
        result, c.Cardinality(float(base**exponent))
    )


@context(_cardinalities())
@prop("rendering is ASCII and marks unbounded domains")
def _render(a: c.Cardinality) -> bool:
    text = str(a)
    return text.isascii() and (text == "inf") == (not a.is_finite)


@context(g.ints())
@prop("a negative size is rejected")
def _negative(size: int) -> bool:
    if size >= 0:
        return True
    try:
        c.Cardinality(float(size))
    except ValueError:
        return True
    return False


spec = conj(
    _commutative,
    _associative,
    _identities,
    _saturates,
    _power,
    _render,
    _negative,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
