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

    # Sizes below and around where the attempt policy reaches its caps
    # are drawn densely, as well as powers of ten across the float range.
    return g.choice(
        g.map(c.finite, g.int_range(0, 3_000_000)),
        g.map(_finite, g.int_range(0, 250)),
        g.constant(c.INFINITE),
    )


@context(_cardinalities())
@prop("attempt limits lie between one and the unbounded cap")
def _limit_bounds(cardinality: c.Cardinality) -> bool:
    return 1 <= b.attempt_limit(cardinality) <= b.UNBOUNDED_LIMIT


def _log_miss(size: int, attempts: int) -> float:
    """The log of the union bound on leaving a value of the domain undrawn
    after a number of uniform draws."""
    return math.log(size) + attempts * math.log1p(-1 / size)


#: Domain sizes checked on every attempt: the trivial domains and the
#: smallest that need coverage.
_SMALL_SIZES = (0, 1, 2, 3)


@context(g.int_range(0, 1_000_000), g.int_range(1, 20000))
@prop("a coverage count is the least that draws every value, or the cap")
def _coverage(drawn: int, cap: int) -> bool:
    log_bound = math.log(b.COVERAGE_MISS)
    for size in (*_SMALL_SIZES, drawn):
        attempts = b.coverage_attempts(size, cap)
        if size <= 1:
            if attempts != 1:
                return False
            continue
        if not 1 <= attempts <= cap:
            return False
        if _log_miss(size, attempts - 1) <= log_bound - 1e-9:
            return False
        if attempts < cap and _log_miss(size, attempts) > log_bound + 1e-9:
            return False
    return True


@context(g.int_range(0, b.UNBOUNDED_LIMIT**2))
@prop("a finite domain is worth its coverage count, and no less than sqrt")
def _limit_coverage(drawn: int) -> bool:
    for size in (*_SMALL_SIZES, drawn):
        cardinality = c.finite(size)
        limit = b.attempt_limit(cardinality)
        baseline = b.baseline_attempts(cardinality)
        if limit != b.coverage_attempts(size, b.UNBOUNDED_LIMIT):
            return False
        if baseline != max(
            b.MINIMUM_BASELINE,
            b.coverage_attempts(size, b.UNBOUNDED_BASELINE),
        ):
            return False
        if limit < min(b.UNBOUNDED_LIMIT, math.isqrt(size)):
            return False
    return True


@prop("unbounded domains get the caps")
def _unbounded() -> bool:
    return (
        b.attempt_limit(c.INFINITE) == b.UNBOUNDED_LIMIT
        and b.baseline_attempts(c.INFINITE) == b.UNBOUNDED_BASELINE
    )


@context(_cardinalities(), _cardinalities())
@prop("attempt limits and baselines are monotone in domain size")
def _monotone(left: c.Cardinality, right: c.Cardinality) -> bool:
    small, large = sorted([left, right], key=lambda k: k.size)
    return b.attempt_limit(small) <= b.attempt_limit(
        large
    ) and b.baseline_attempts(small) <= b.baseline_attempts(large)


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


@context(
    g.bounded_lists(1, 12, g.tuples(g.int_range(1, 10000), g.bools())),
    g.int_range(50, 2000),
)
@prop("only declared attempts outlast the budget, and are made in full")
def _deadlines(
    limits: list[tuple[int, bool]], budget_ms: int, rng: random.Random
) -> bool:
    plans = [
        b.PropertyPlan(f"p{i}", c.INFINITE, limit, declared)
        for i, (limit, declared) in enumerate(limits)
    ]
    budget = b.TimeBudget(budget_ms / 1000, plans)
    order = list(plans)
    rng.shuffle(order)
    for plan in order:
        allowance = budget.allowance(plan.desc)
        if allowance.max_attempts != plan.attempt_limit:
            return False
        if plan.declared:
            if allowance.deadline is not None:
                return False
            continue
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


@context(g.int_range(1, 100), g.int_range(1, 100))
@prop("a declared property leaves room in the shares of the others")
def _declared_room(limit: int, declared: int) -> bool:
    plans = [
        b.PropertyPlan("a", c.INFINITE, limit),
        b.PropertyPlan("d", c.INFINITE, declared, True),
    ]
    budget = b.TimeBudget(1.0, plans)
    started = time.perf_counter()
    first = budget.allowance("a")
    if first.deadline is None:
        return False
    expected = (budget.end - started) * limit / (limit + declared)
    return abs(first.deadline - started - expected) < 1e-3


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
    _coverage,
    _limit_coverage,
    _unbounded,
    _monotone,
    _alone,
    _share,
    _exhausted,
    _deadlines,
    _last_gets_rest,
    _declared_room,
    _once,
    _duplicate_plans,
    _rejects,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
