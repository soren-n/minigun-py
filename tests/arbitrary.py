"""Properties of the random source: draws, bounds, forking."""

import random
import sys

import minigun.arbitrary as a
import minigun.generate as g
from minigun import assume, check
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


@context(
    g.float_range(-sys.float_info.max, sys.float_info.max),
    g.float_range(-sys.float_info.max, sys.float_info.max),
)
@prop("draw_float stays within bounds wider than the float span")
def _draw_float_wide(x: float, y: float, rng: random.Random) -> bool:
    lower, upper = min(x, y), max(x, y)
    return lower <= a.draw_float(rng, lower, upper) <= upper


@context(
    g.float_range(-sys.float_info.max, -sys.float_info.max / 2),
    g.float_range(sys.float_info.max / 2, sys.float_info.max),
)
@prop(
    "draws over ranges wider than the float span spread across them",
    attempts=20,
)
def _draw_float_spread(lower: float, upper: float, rng: random.Random) -> bool:
    # Uniform over the range: each sign has probability at least a third
    # and a bound is hit with probability 2^-53 per draw, so 200 draws see
    # both signs and stay off the bounds but for a 1e-13 chance.
    draws = [a.draw_float(rng, lower, upper) for _ in range(200)]
    return (
        any(x < 0 for x in draws)
        and any(x > 0 for x in draws)
        and not any(x in (lower, upper) for x in draws)
    )


@prop("draw_float rejects inverted bounds")
def _draw_float_rejects(lower: float, upper: float, rng: random.Random) -> bool:
    assume(lower > upper)
    try:
        a.draw_float(rng, lower, upper)
    except ValueError:
        return True
    return False


@context(
    g.bounded_lists(0, 4, g.int_range(-3, 3)), g.bounded_lists(0, 4, g.ints())
)
@prop("weighted_choice rejects empty, mismatched or invalid weights")
def _weighted_rejects(
    weights: list[int], items: list[int], rng: random.Random
) -> bool:
    assume(
        not items
        or len(weights) != len(items)
        or min(weights) < 0
        or sum(weights) == 0
    )
    try:
        a.weighted_choice(rng, weights, items)
    except ValueError:
        return True
    return False


@prop("choice rejects an empty sequence")
def _choice_rejects(rng: random.Random) -> bool:
    try:
        a.choice(rng, [])
    except ValueError:
        return True
    return False


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
    _draw_float_wide,
    _draw_float_spread,
    _draw_float_rejects,
    _weighted_rejects,
    _choice_rejects,
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
