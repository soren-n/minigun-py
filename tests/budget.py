"""Properties of the time budget and attempt policy."""

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

    return g.choice(g.map(_finite, g.int_range(0, 250)), g.constant(c.INFINITE))


@context(_cardinalities())
@prop("attempt limits lie between one and the unbounded cap")
def _limit_bounds(cardinality: c.Cardinality) -> bool:
    return 1 <= b.attempt_limit(cardinality) <= b.UNBOUNDED_LIMIT


@context(_cardinalities(), _cardinalities())
@prop("attempt limits and baselines are monotone in domain size")
def _monotone(left: c.Cardinality, right: c.Cardinality) -> bool:
    small, large = sorted([left, right], key=lambda k: k.size)
    return b.attempt_limit(small) <= b.attempt_limit(
        large
    ) and b.baseline_attempts(small) <= b.baseline_attempts(large)


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


@context(g.int_range(-100, 0))
@prop("a non-positive budget is rejected")
def _rejects(total: int) -> bool:
    try:
        b.TimeBudget(float(total), [])
    except ValueError:
        return True
    return False


spec = conj(
    _limit_bounds,
    _monotone,
    _share,
    _exhausted,
    _deadlines,
    _last_gets_rest,
    _once,
    _rejects,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
