"""
Time budget

A run has a fixed time budget and no calibration phase. Every property
receives an equal share of the time remaining when it starts, divided
among the properties not yet started, and runs until it has spent that
share or reached its attempt limit. Time a property leaves unspent flows
to the properties after it.

Shares are equal per property, not per attempt. The cost of an attempt
varies by orders of magnitude between properties, and a share weighted by
attempt limit gives every attempt the same time, so a property whose
attempts cost more than that makes only a few of them however small its
limit, while cheap properties over unbounded domains take most of the
run. With equal shares a small finite domain is covered whenever its
attempts fit in one share, and properties that need more than a share
divide what the others leave. The time saved flows only forward: a
property that needs more than its share gets none of the time the
properties after it will leave unspent.

A property that declares its attempts always makes all of them: the count
is a statement of what the property needs, such as the sample size of a
statistical test, and a truncated run of it would pass without having
tested what it claims. It still counts as one of the properties sharing
the time, so the others leave it one share of room, but it has no deadline, and a run whose declared
properties take longer than their share overruns its budget. The budget
is held strictly for every other property.

Shrinking a counterexample may use what is left of the whole budget, not
only the failing property's share: a counterexample is what a failing run
is for, and the properties after it still make at least one evaluation
each. No shrunk candidate is evaluated once the budget is spent, so a run
that finds a failure ends within its budget plus one evaluation, or after
its declared attempts when those overran.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from minigun.cardinality import Cardinality
from minigun.specify import Allowance, Resolved

__all__ = [
    "UNBOUNDED_LIMIT",
    "UNBOUNDED_BASELINE",
    "MINIMUM_BASELINE",
    "COVERAGE_MISS",
    "coverage_attempts",
    "attempt_limit",
    "baseline_attempts",
    "share",
    "PropertyPlan",
    "plan",
    "TimeBudget",
]


###############################################################################
# Attempt policy
###############################################################################

#: Attempts an unbounded domain is worth in one run.
UNBOUNDED_LIMIT = 10000

#: Baseline attempts for an unbounded domain when no time budget applies.
UNBOUNDED_BASELINE = 1000

#: Baseline attempts for a domain of at most one value.
MINIMUM_BASELINE = 10

#: Chance, at most, that the coverage count of a finite domain leaves some
#: value undrawn.
COVERAGE_MISS = 1e-3


def coverage_attempts(size: float, cap: int) -> int:
    """Uniform draws needed to see every value of a finite domain.

    The least ``k`` with ``size * (1 - 1 / size) ** k <= COVERAGE_MISS``:
    by the union bound, ``k`` uniform draws then leave some value undrawn
    with chance at most ``COVERAGE_MISS``. That is about
    ``size * ln(size / COVERAGE_MISS)``, more than the square root of the
    size for every size above one.

    :param size: The number of values in the domain.
    :param cap: The most attempts to return.

    :return: The count, at most ``cap``; one for a domain of at most one
        value.
    """
    if size <= 1:
        return 1
    attempts = math.log(size / COVERAGE_MISS) / -math.log1p(-1 / size)
    if attempts >= cap:
        return cap
    return math.ceil(attempts)


def attempt_limit(cardinality: Cardinality) -> int:
    """Cap on useful attempts for a domain.

    A finite domain is worth enough attempts to draw each of its values
    with high probability (``coverage_attempts``), so a property over a
    small domain sees all of it. No domain, finite or not, is worth more
    than ``UNBOUNDED_LIMIT``, which domains of more than about 740 values
    reach.
    """
    if not cardinality.is_finite:
        return UNBOUNDED_LIMIT
    return coverage_attempts(cardinality.size, UNBOUNDED_LIMIT)


def baseline_attempts(cardinality: Cardinality) -> int:
    """Attempts for a domain when no time budget applies.

    The coverage count of a finite domain, as for ``attempt_limit``, but
    at least ``MINIMUM_BASELINE`` and at most ``UNBOUNDED_BASELINE``, which
    is what unbounded domains get and domains of more than about 90 values
    reach.
    """
    if not cardinality.is_finite:
        return UNBOUNDED_BASELINE
    return max(
        MINIMUM_BASELINE,
        coverage_attempts(cardinality.size, UNBOUNDED_BASELINE),
    )


###############################################################################
# Time shares
###############################################################################
def share(remaining_time: float, properties: int) -> float:
    """The time share of a property about to start.

    :param remaining_time: Seconds left in the budget.
    :param properties: The number of properties not yet started, this one
        included.

    :return: Seconds, an equal part of the remaining time; never negative.
    """
    if remaining_time <= 0 or properties <= 0:
        return 0.0
    return remaining_time / properties


@dataclass(frozen=True)
class PropertyPlan:
    """What is known about a property before the run.

    :param desc: The property's description.
    :param cardinality: The cardinality of its argument domain.
    :param attempt_limit: Its attempt limit.
    :param declared: Whether the property declares its attempts, making
        the limit a number of attempts it always makes.
    """

    desc: str
    cardinality: Cardinality
    attempt_limit: int
    declared: bool = False


def _limit(resolved: Resolved) -> int:
    attempts = resolved.prop.attempts
    return attempt_limit(resolved.cardinality) if attempts is None else attempts


def plan(resolved: list[Resolved]) -> list[PropertyPlan]:
    """The plan for a list of resolved properties.

    A property's attempt limit is the number of attempts it declares, or
    else the limit of its domain.
    """
    return [
        PropertyPlan(
            r.prop.desc, r.cardinality, _limit(r), r.prop.attempts is not None
        )
        for r in resolved
    ]


class TimeBudget:
    """Hands out allowances from a fixed budget as properties start.

    With several workers the budget is worker time: each worker has the
    time until the end of the run, less what the properties running on
    the others still hold. A property reports that it ended with
    ``finished``, which returns what it held to the others.

    :param total: The budget in seconds; the run ends ``total`` seconds
        after construction.
    :param plans: The properties that will run, in any order.
    :param workers: The number of properties that may run at once.

    :raises ValueError: When the budget is not positive, there are no
        workers, or two plans share a description.
    """

    def __init__(
        self, total: float, plans: list[PropertyPlan], workers: int = 1
    ):
        if total <= 0:
            raise ValueError(f"The time budget must be positive, got {total}")
        if workers < 1:
            raise ValueError(f"A budget needs a worker, got {workers}")
        self._limits = {p.desc: p.attempt_limit for p in plans}
        if len(self._limits) != len(plans):
            raise ValueError("Property plans must have unique descriptions")
        self._declared = {p.desc for p in plans if p.declared}
        self.total = total
        self.workers = workers
        self.end = time.perf_counter() + total
        self._pending = set(self._limits)
        # Deadlines of the properties that started and have not finished.
        self._running: dict[str, float] = {}

    def allowance(self, desc: str) -> Allowance:
        """The allowance of a property that is starting now.

        A property that declares its attempts gets them all, with no
        deadline; any other gets a deadline at the end of its share of the
        worker time, never past the end of the run. Either may shrink a
        counterexample until the budget ends.

        :raises KeyError: When the property is not in the plan or has
            already started.
        """
        if desc not in self._pending:
            raise KeyError(f'Property "{desc}" is not pending in the budget')
        self._pending.remove(desc)
        now = time.perf_counter()
        limit = self._limits[desc]
        if desc in self._declared:
            return Allowance(limit, shrink_deadline=self.end)
        if self.workers == 1:
            # One worker runs one property at a time: whatever started
            # before this one has ended.
            self._running.clear()
        remaining = max(0.0, self.end - now)
        held = sum(
            max(0.0, deadline - now) for deadline in self._running.values()
        )
        available = max(0.0, self.workers * remaining - held)
        seconds = min(remaining, share(available, 1 + len(self._pending)))
        self._running[desc] = now + seconds
        return Allowance(limit, now + seconds, self.end)

    def finished(self, desc: str) -> None:
        """A property that started has ended; the time it held is free.
        Needed with several workers; with one, the next start implies it.

        :raises KeyError: When the property has not started.
        """
        if desc in self._pending or desc not in self._limits:
            raise KeyError(f'Property "{desc}" has not started')
        self._running.pop(desc, None)
