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
    # (about 90 and 740 values) are drawn densely, as well as larger sizes
    # and powers of ten across the float range.
    return g.choice(
        g.map(c.finite, g.int_range(0, 1000)),
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


# Below about 1500 values the count stays under the drawn caps and its
# minimality is checked; larger sizes mostly check the cap.
@context(
    g.choice(g.int_range(2, 1500), g.int_range(0, 1_000_000)),
    g.int_range(1, 20000),
)
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
@prop("only declared attempts outlast the budget; shrinking lasts until it")
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
        if allowance.shrink_deadline != budget.end:
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


def _planned(limits: list[int]) -> list[b.PropertyPlan]:
    return [
        b.PropertyPlan(f"p{i}", c.INFINITE, limit)
        for i, limit in enumerate(limits)
    ]


@context(
    g.bounded_lists(1, 10, g.tuples(g.int_range(1, 10000), g.bools())),
    g.int_range(2, 6),
    g.int_range(50, 2000),
)
@prop("running properties never hold more than the workers' remaining time")
def _worker_time(
    limits: list[tuple[int, bool]],
    workers: int,
    budget_ms: int,
    rng: random.Random,
) -> bool:
    plans = [
        b.PropertyPlan(f"p{i}", c.INFINITE, limit, declared)
        for i, (limit, declared) in enumerate(limits)
    ]
    budget = b.TimeBudget(budget_ms / 1000, plans, workers)
    order = list(plans)
    rng.shuffle(order)
    # Deadlines of the undeclared properties started and not finished; a
    # declared property holds no deadline but occupies a worker.
    held: dict[str, float | None] = {}
    while order:
        # At most `workers` properties run at once, as in a parallel run;
        # one finishes at a drawn point, or when every worker is busy.
        if held and (len(held) == workers or rng.random() < 0.5):
            desc = rng.choice(sorted(held))
            budget.finished(desc)
            del held[desc]
            continue
        plan = order.pop()
        pending = plan.attempt_limit + sum(p.attempt_limit for p in order)
        before = time.perf_counter()
        allowance = budget.allowance(plan.desc)
        now = time.perf_counter()
        if allowance.shrink_deadline != budget.end:
            return False
        if plan.declared:
            if allowance.deadline is not None:
                return False
            held[plan.desc] = None
            continue
        deadline = allowance.deadline
        if deadline is None or deadline > budget.end:
            return False
        if budget.end > now:
            # The fraction of the remaining time received decreases with
            # the instant the budget read, and the expected fraction (a
            # share of what the running properties leave of the workers'
            # time) increases with it, so the two ranges over the
            # instants between the readings here must meet.
            def _expected(
                instant: float,
                limit: int = plan.attempt_limit,
                pending: int = pending,
            ) -> float:
                remaining = budget.end - instant
                others = sum(
                    max(0.0, d - instant)
                    for d in held.values()
                    if d is not None
                )
                available = max(0.0, workers - others / remaining)
                return min(1.0, b.share(available, limit, pending))

            low = (deadline - now) / (budget.end - now)
            high = (deadline - before) / (budget.end - before)
            if low > _expected(now) + 1e-9 or high < _expected(before) - 1e-9:
                return False
        held[plan.desc] = deadline
        holding = sum(max(0.0, d - now) for d in held.values() if d is not None)
        if holding > workers * max(0.0, budget.end - now) + 1e-6:
            return False
    return True


def _fraction(budget: b.TimeBudget, desc: str) -> tuple[float, float]:
    """Bounds on the fraction of the remaining time a starting property
    receives.

    The budget reads the clock between the two readings here, and the
    fraction ``(deadline - now) / (end - now)`` decreases with ``now``, so
    it lies between its values at the two readings, however long the
    process was descheduled in between.
    """
    before = time.perf_counter()
    deadline = budget.allowance(desc).deadline
    after = time.perf_counter()
    if deadline is None:
        return math.nan, math.nan
    low = (
        (deadline - after) / (budget.end - after)
        if budget.end > after
        else -math.inf
    )
    high = (
        (deadline - before) / (budget.end - before)
        if budget.end > before
        else math.inf
    )
    return low, high


def _within(bounds: tuple[float, float], value: float) -> bool:
    low, high = bounds
    return low - 1e-9 <= value <= high + 1e-9


@context(
    g.bounded_lists(1, 10, g.int_range(1, 10000)),
    g.int_range(50, 2000),
)
@prop("with one worker a share is the old share, finished or not")
def _one_worker(limits: list[int], budget_ms: int, rng: random.Random) -> bool:
    plans = _planned(limits)
    budget = b.TimeBudget(budget_ms / 1000, plans)
    order = list(plans)
    rng.shuffle(order)
    pending = sum(limits)
    for plan in order:
        # The old share, as a fraction of the remaining time.
        expected = b.share(1.0, plan.attempt_limit, pending)
        pending -= plan.attempt_limit
        if not _within(_fraction(budget, plan.desc), expected):
            return False
        # Whether the property reports its end changes nothing.
        if rng.random() < 0.5:
            budget.finished(plan.desc)
    return True


@context(
    g.int_range(1, 10000),
    g.int_range(1, 10000),
    g.bounded_lists(0, 4, g.int_range(1, 10000)),
    g.int_range(2, 6),
)
@prop("a finished property returns its time to the others")
def _returned(first: int, second: int, others: list[int], workers: int) -> bool:
    def _second(finish: bool) -> tuple[float, float]:
        budget = b.TimeBudget(1.0, _planned([first, second, *others]), workers)
        budget.allowance("p0")
        if finish:
            budget.finished("p0")
        return _fraction(budget, "p1")

    running_low, _ = _second(False)
    returned = _second(True)
    # With the first finished, the second gets its share of every
    # worker's remaining time, capped at that time; with the first still
    # running, no more.
    expected = min(1.0, b.share(workers, second, second + sum(others)))
    return _within(returned, expected) and running_low <= expected + 1e-9


@context(g.int_range(-5, 5))
@prop("finished needs a started property; a budget needs a worker")
def _finished_errors(drawn: int) -> bool:
    plans = _planned([10, 10])
    budget = b.TimeBudget(1.0, plans, 2)
    budget.allowance("p0")
    budget.finished("p0")
    for desc in ("p1", "unplanned"):
        try:
            budget.finished(desc)
        except KeyError:
            continue
        return False
    for workers in (-1, 0, 1, 2, drawn):
        try:
            b.TimeBudget(1.0, plans, workers)
        except ValueError:
            if workers >= 1:
                return False
            continue
        if workers < 1:
            return False
    return True


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
    _worker_time,
    _one_worker,
    _returned,
    _finished_errors,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
