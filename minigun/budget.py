"""
Time budget

A run has a fixed time budget and no calibration phase. Every property
receives a share of the time remaining when it starts, weighted by its
attempt limit, and runs until it has spent that share or reached the
limit. Time a property leaves unspent flows to the properties after it, so
the budget is held strictly while cheap properties never starve expensive
ones.
"""

import math
import time
from dataclasses import dataclass

from minigun.cardinality import Cardinality
from minigun.specify import Allowance, Resolved

__all__ = [
    "UNBOUNDED_LIMIT",
    "UNBOUNDED_BASELINE",
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


def attempt_limit(cardinality: Cardinality) -> int:
    """Cap on useful attempts for a domain.

    For finite domains this is the square root of the domain size; beyond
    that repeat draws dominate and further attempts add little coverage.
    No domain, finite or not, is worth more than ``UNBOUNDED_LIMIT``.
    """
    if not cardinality.is_finite:
        return UNBOUNDED_LIMIT
    return min(UNBOUNDED_LIMIT, max(1, int(math.sqrt(cardinality.size))))


def baseline_attempts(cardinality: Cardinality) -> int:
    """Attempts for a domain when no time budget applies.

    Grows with the square root of the domain size up to 1000 values, then
    logarithmically: large domains cannot be meaningfully covered by
    attempt count alone. No domain gets more than ``UNBOUNDED_BASELINE``,
    which is what unbounded domains get.
    """
    if not cardinality.is_finite:
        return UNBOUNDED_BASELINE
    size = cardinality.size
    if size <= 1000:
        return max(10, int(math.sqrt(size)))
    if size <= 1_000_000:
        attempts = math.sqrt(1000) + math.log10(size / 1000) * 10
    else:
        attempts = (
            math.sqrt(1000)
            + math.log10(1000) * 10
            + math.log10(size / 1_000_000) * 5
        )
    return min(UNBOUNDED_BASELINE, int(attempts))


###############################################################################
# Time shares
###############################################################################
def share(remaining_time: float, limit: int, remaining_limits: int) -> float:
    """The time share of a property about to start.

    :param remaining_time: Seconds left in the budget.
    :param limit: The property's attempt limit.
    :param remaining_limits: The attempt limits of every property not yet
        started, this one included.

    :return: Seconds, proportional to the property's limit; never
        negative.
    """
    if remaining_time <= 0 or remaining_limits <= 0:
        return 0.0
    return remaining_time * limit / remaining_limits


@dataclass(frozen=True)
class PropertyPlan:
    """What is known about a property before the run.

    :param desc: The property's description.
    :param cardinality: The cardinality of its argument domain.
    :param attempt_limit: Its attempt limit.
    """

    desc: str
    cardinality: Cardinality
    attempt_limit: int


def plan(resolved: list[Resolved]) -> list[PropertyPlan]:
    """The plan for a list of resolved properties."""
    return [
        PropertyPlan(r.prop.desc, r.cardinality, attempt_limit(r.cardinality))
        for r in resolved
    ]


class TimeBudget:
    """Hands out allowances from a fixed budget as properties start.

    :param total: The budget in seconds; the run ends ``total`` seconds
        after construction.
    :param plans: The properties that will run, in any order.

    :raises ValueError: When the budget is not positive.
    """

    def __init__(self, total: float, plans: list[PropertyPlan]):
        if total <= 0:
            raise ValueError(f"The time budget must be positive, got {total}")
        self.total = total
        self.end = time.perf_counter() + total
        self._limits = {p.desc: p.attempt_limit for p in plans}
        self._pending = set(self._limits)

    def allowance(self, desc: str) -> Allowance:
        """The allowance of a property that is starting now.

        :raises KeyError: When the property is not in the plan or has
            already started.
        """
        if desc not in self._pending:
            raise KeyError(f'Property "{desc}" is not pending in the budget')
        self._pending.remove(desc)
        now = time.perf_counter()
        limit = self._limits[desc]
        remaining_limits = limit + sum(
            self._limits[pending] for pending in self._pending
        )
        seconds = share(self.end - now, limit, remaining_limits)
        return Allowance(limit, now + seconds)
