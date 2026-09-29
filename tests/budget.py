"""Properties of the time budget and attempt policy."""

import math
import random
import time

import minigun.budget as b
import minigun.cardinality as c
import minigun.generate as g
from minigun import check
from minigun.specify import conj, context, prop


def _cardinalities() -> g.Generator[c.Cardinality]:
    def _finite(exponent: int) -> c.Cardinality:
        return c.Cardinality(float(10**exponent))

    # Sizes where the attempt policy changes shape are drawn densely, as
    # well as powers of ten across the whole float range.
    return g.choice(
        g.map(c.finite, g.int_range(0, 3_000_000)),
        g.map(_finite, g.int_range(0, 250)),
        g.constant(c.INFINITE),
    )


#: Domain sizes around which the baseline changes formula.
_BREAKPOINTS = (1000, 1_000_000)


@context(_cardinalities())
@prop("attempt limits lie between one and the unbounded cap")
def _limit_bounds(cardinality: c.Cardinality) -> bool:
    return 1 <= b.attempt_limit(cardinality) <= b.UNBOUNDED_LIMIT


@context(g.choice(g.int_range(0, 3), g.int_range(0, b.UNBOUNDED_LIMIT**2)))
@prop("a finite domain is worth the square root of its size in attempts")
def _limit_sqrt(size: int) -> bool:
    limit = b.attempt_limit(c.finite(size))
    return limit == max(1, math.isqrt(size))


@context(_cardinalities(), _cardinalities())
@prop("attempt limits and baselines are monotone in domain size")
def _monotone(left: c.Cardinality, right: c.Cardinality) -> bool:
    small, large = sorted([left, right], key=lambda k: k.size)
    return b.attempt_limit(small) <= b.attempt_limit(
        large
    ) and b.baseline_attempts(small) <= b.baseline_attempts(large)


@context(
    g.choice(
        *[g.int_range(point - 20, point + 20) for point in _BREAKPOINTS],
        g.int_range(1, 10**9),
    )
)
@prop("baseline attempts do not jump between neighbouring domain sizes")
def _continuous(size: int) -> bool:
    step = b.baseline_attempts(c.finite(size + 1)) - b.baseline_attempts(
        c.finite(size)
    )
    return step in (0, 1)


@context(g.float_range(-10.0, 10.0), g.int_range(1, 10))
@prop("the only pending property receives all remaining time and no more")
def _alone(remaining: float, limit: int) -> bool:
    # float_range draws zero and its bounds often, so spent budgets and
    # limits of one are both exercised.
    share = b.share(remaining, limit, limit)
    if remaining <= 0:
        return share == 0.0
    return math.isclose(share, remaining, rel_tol=1e-12)


@context(g.int_range(1, 1000), g.int_range(1, 10000), g.int_range(0, 100000))
@prop("a share never exceeds the remaining time and is proportional")
def _share(remaining_ms: int, limit: int, others: int) -> bool:
    remaining = remaining_ms / 1000
    share = b.share(remaining, limit, limit + others)
    whole = b.share(remaining, limit, limit)
    return (
        0 <= share <= remaining + 1e-9
        and abs(whole - remaining) < 1e-9
        and abs(share * (limit + others) - remaining * limit) < 1e-6
    )


@prop("shares of an exhausted budget are zero")
def _exhausted(limit: int, others: int) -> bool:
    return b.share(0.0, abs(limit), abs(limit) + abs(others)) == 0.0


@context(g.bounded_lists(1, 12, g.int_range(1, 10000)), g.int_range(50, 2000))
@prop("allowances never reach past the end of the budget")
def _deadlines(limits: list[int], budget_ms: int, rng: random.Random) -> bool:
    plans = [
        b.PropertyPlan(f"p{i}", c.INFINITE, limit)
        for i, limit in enumerate(limits)
    ]
    budget = b.TimeBudget(budget_ms / 1000, plans)
    order = list(plans)
    rng.shuffle(order)
    for plan in order:
        allowance = budget.allowance(plan.desc)
        if allowance.max_attempts != plan.attempt_limit:
            return False
        if allowance.deadline is None or allowance.deadline > budget.end + 1e-9:
            return False
        if allowance.deadline < time.perf_counter() - 1e-3:
            return False
    return True


@prop("the last property to start receives all remaining time")
def _last_gets_rest(seed: int) -> bool:
    plans = [
        b.PropertyPlan("a", c.INFINITE, 10),
        b.PropertyPlan("b", c.INFINITE, 10),
    ]
    budget = b.TimeBudget(1.0, plans)
    budget.allowance("a")
    last = budget.allowance("b")
    return last.deadline is not None and abs(last.deadline - budget.end) < 1e-3


@prop("a property can start at most once and must be planned")
def _once(seed: int) -> bool:
    budget = b.TimeBudget(1.0, [b.PropertyPlan("a", c.INFINITE, 10)])
    budget.allowance("a")
    for desc in ("a", "unplanned"):
        try:
            budget.allowance(desc)
        except KeyError:
            continue
        return False
    return True


@prop("plans sharing a description are rejected")
def _duplicate_plans(seed: int) -> bool:
    plans = [
        b.PropertyPlan("a", c.INFINITE, 10),
        b.PropertyPlan("a", c.INFINITE, 20),
    ]
    try:
        b.TimeBudget(1.0, plans)
    except ValueError:
        return True
    return False


@context(g.float_range(-1.0, 1.0))
@prop("exactly the non-positive budgets are rejected")
def _rejects(total: float) -> bool:
    try:
        b.TimeBudget(total, [])
    except ValueError:
        return total <= 0
    return total > 0


spec = conj(
    _limit_bounds,
    _limit_sqrt,
    _monotone,
    _continuous,
    _alone,
    _share,
    _exhausted,
    _deadlines,
    _last_gets_rest,
    _once,
    _duplicate_plans,
    _rejects,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
