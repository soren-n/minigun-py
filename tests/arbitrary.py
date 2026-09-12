"""Properties of the random source: draws, bounds, forking."""

import random

import minigun.arbitrary as a
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


def _ordered(a_: int, b_: int) -> tuple[int, int]:
    return min(a_, b_), max(a_, b_)


@context(g.map(_ordered, g.ints(), g.ints()))
@prop("draw_int stays within its bounds")
def _draw_int_bounds(bounds: tuple[int, int], rng: random.Random) -> bool:
    lower, upper = bounds
    return lower <= a.draw_int(rng, lower, upper) <= upper


@context(g.map(_ordered, g.ints(), g.ints()))
@prop("draw_int rejects inverted bounds")
def _draw_int_rejects(bounds: tuple[int, int], rng: random.Random) -> bool:
    lower, upper = bounds
    if lower == upper:
        return True
    try:
        a.draw_int(rng, upper, lower)
    except ValueError:
        return True
    return False


@context(g.map(_ordered, g.ints(), g.ints()))
@prop("draw_float stays within its bounds")
def _draw_float_bounds(bounds: tuple[int, int], rng: random.Random) -> bool:
    lower, upper = bounds
    return lower <= a.draw_float(rng, float(lower), float(upper)) <= upper


@prop("probability lies in the unit interval")
def _probability_unit(rng: random.Random) -> bool:
    return 0.0 <= a.probability(rng) < 1.0


@context(g.bounded_lists(1, 20, g.ints()))
@prop("choice returns one of its items")
def _choice_member(items: list[int], rng: random.Random) -> bool:
    return a.choice(rng, items) in items


@context(g.bounded_lists(1, 10, g.tuples(g.int_range(0, 5), g.ints())))
@prop("weighted_choice never returns a zero-weight item")
def _weighted_choice_zero(
    weighted: list[tuple[int, int]], rng: random.Random
) -> bool:
    weights = [weight for weight, _ in weighted]
    if sum(weights) == 0:
        return True
    items = [item for _, item in weighted]
    chosen = a.weighted_choice(rng, weights, items)
    return any(weight > 0 for weight, item in weighted if item == chosen)


@prop("seeding twice yields identical draw sequences")
def _seed_reproducible(seed: int) -> bool:
    first = [a.draw_int(a.seed(seed), 0, 10**9) for _ in range(1)]
    second = [a.draw_int(a.seed(seed), 0, 10**9) for _ in range(1)]
    return first == second


@prop("forked children are reproducible from the parent's seed")
def _fork_reproducible(seed: int) -> bool:
    def _children(parent: a.Rng) -> list[int]:
        return [a.fork(parent).getrandbits(64) for _ in range(3)]

    return _children(a.seed(seed)) == _children(a.seed(seed))


@prop("drawing from a child does not disturb the parent")
def _fork_independent(seed: int) -> bool:
    parent = a.seed(seed)
    child = a.fork(parent)
    for _ in range(5):
        child.getrandbits(64)
    after_child_draws = parent.getrandbits(64)

    control = a.seed(seed)
    a.fork(control)
    return after_child_draws == control.getrandbits(64)


spec = conj(
    _draw_int_bounds,
    _draw_int_rejects,
    _draw_float_bounds,
    _probability_unit,
    _choice_member,
    _weighted_choice_zero,
    _seed_reproducible,
    _fork_reproducible,
    _fork_independent,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
