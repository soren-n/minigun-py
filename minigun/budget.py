"""
Time budget allocation for property testing.

Given a time budget and per-property calibration timings, the allocator
decides how many attempts each property gets:

1. Every property starts from a baseline that grows with the size of its
   input domain.
2. If the estimated total exceeds the budget, all properties are scaled
   down proportionally.
3. If time is left over, properties with unbounded domains are boosted up
   to their attempt limit.
"""

import math
from dataclasses import dataclass, replace

from minigun.cardinality import Cardinality


###############################################################################
# Attempt policy
###############################################################################
def attempt_limit(cardinality: Cardinality) -> int:
    """Cap on useful attempts for a domain.

    For finite domains this is the square root of the domain size; beyond
    that, repeat draws dominate and further attempts add little coverage.
    Unbounded domains are capped at 10000.
    """
    if not cardinality.is_finite:
        return 10000
    return max(1, int(math.sqrt(cardinality.size)))


def baseline_attempts(cardinality: Cardinality) -> int:
    """Baseline attempts for a domain before budget scaling.

    Grows with the square root of the domain size up to 1000 values, then
    logarithmically: large domains cannot be meaningfully covered by
    attempt count alone, so time is better spent elsewhere. Unbounded
    domains get a flat 1000.
    """
    if not cardinality.is_finite:
        return 1000
    size = cardinality.size
    if size <= 1000:
        return max(10, int(math.sqrt(size)))
    if size <= 1_000_000:
        return int(math.sqrt(1000) + math.log10(size / 1000) * 10)
    return int(
        math.sqrt(1000)
        + math.log10(1000) * 10
        + math.log10(size / 1_000_000) * 5
    )


###############################################################################
# Per-property budget
###############################################################################
@dataclass(frozen=True, slots=True)
class PropertyBudget:
    """Budget calculation for a single property."""

    name: str
    cardinality: Cardinality
    attempt_limit: int
    baseline_attempts: int
    time_per_attempt: float
    final_attempts: int
    estimated_time: float

    @classmethod
    def create(
        cls, name: str, cardinality: Cardinality, time_per_attempt: float = 0.0
    ) -> "PropertyBudget":
        """Create a property budget with calculated attempt limits."""
        baseline = baseline_attempts(cardinality)
        return cls(
            name=name,
            cardinality=cardinality,
            attempt_limit=attempt_limit(cardinality),
            baseline_attempts=baseline,
            time_per_attempt=time_per_attempt,
            final_attempts=baseline,
            estimated_time=baseline * time_per_attempt,
        )

    def with_calibration(self, time_per_attempt: float) -> "PropertyBudget":
        """Return a new PropertyBudget with calibration timing."""
        return replace(
            self,
            time_per_attempt=time_per_attempt,
            final_attempts=self.baseline_attempts,
            estimated_time=self.baseline_attempts * time_per_attempt,
        )

    def with_final_attempts(self, attempts: int) -> "PropertyBudget":
        """Return a new PropertyBudget with final allocated attempts."""
        return replace(
            self,
            final_attempts=attempts,
            estimated_time=attempts * self.time_per_attempt,
        )

    def can_be_boosted(self) -> bool:
        """Whether this property benefits from more attempts."""
        return (
            not self.cardinality.is_finite
            and self.final_attempts < self.attempt_limit
        )


###############################################################################
# Allocation strategies
###############################################################################
def _scale_down(
    properties: list[PropertyBudget], time_budget: float
) -> list[PropertyBudget]:
    """Scale down all properties proportionally to fit the budget."""
    total_time = sum(p.estimated_time for p in properties)
    if total_time <= 0:
        return properties

    scaling_factor = time_budget / total_time
    return [
        p.with_final_attempts(max(1, int(p.baseline_attempts * scaling_factor)))
        for p in properties
    ]


def _boost_unbounded(
    properties: list[PropertyBudget], time_budget: float
) -> list[PropertyBudget]:
    """Boost unbounded-domain properties with the remaining budget."""
    current_time = sum(p.estimated_time for p in properties)
    remaining_budget = time_budget - current_time
    if remaining_budget <= 0:
        return properties

    result = list(properties)
    for index, prop in enumerate(result):
        if not prop.can_be_boosted() or remaining_budget <= 0:
            continue
        if prop.time_per_attempt <= 0:
            continue

        max_additional = prop.attempt_limit - prop.final_attempts
        affordable_additional = int(remaining_budget / prop.time_per_attempt)
        additional_attempts = min(max_additional, affordable_additional)

        if additional_attempts > 0:
            result[index] = prop.with_final_attempts(
                prop.final_attempts + additional_attempts
            )
            remaining_budget -= additional_attempts * prop.time_per_attempt

    return result


###############################################################################
# Allocator
###############################################################################
class BudgetAllocator:
    """Distributes a time budget over calibrated properties."""

    def __init__(self, time_budget: float):
        self.time_budget = time_budget
        self._property_budgets: dict[str, PropertyBudget] = {}
        self._calibration_complete = False

    def add_property(self, name: str, cardinality: Cardinality) -> None:
        """Register a property for budget allocation.

        :raises ValueError: When a property with the same description was
            already registered; property descriptions must be unique.
        """
        if name in self._property_budgets:
            raise ValueError(
                f'Duplicate property description "{name}"; descriptions '
                "must be unique for budget allocation"
            )
        self._property_budgets[name] = PropertyBudget.create(name, cardinality)

    def record_calibration(
        self, property_name: str, total_time: float, attempts: int
    ) -> None:
        """Record calibration timing for a property."""
        prop = self._property_budgets[property_name]
        time_per_attempt = total_time / max(attempts, 1)
        self._property_budgets[property_name] = prop.with_calibration(
            time_per_attempt
        )

    def finalize_allocation(self) -> None:
        """Finalize the budget allocation."""
        self._calibration_complete = True

        properties = list(self._property_budgets.values())
        total_estimated = sum(p.estimated_time for p in properties)

        if total_estimated <= self.time_budget:
            properties = _boost_unbounded(properties, self.time_budget)
        else:
            properties = _scale_down(properties, self.time_budget)

        self._property_budgets = {p.name: p for p in properties}

    def get_allocated_attempts(self, property_name: str) -> int:
        """Get allocated attempts for a property.

        :raises KeyError: When the property was never registered.
        """
        if not self._calibration_complete:
            return 10  # Calibration phase
        return self._property_budgets[property_name].final_attempts

    def get_property_budget(self, property_name: str) -> PropertyBudget | None:
        """Get full budget info for a property."""
        return self._property_budgets.get(property_name)

    @property
    def total_estimated_time(self) -> float:
        """Total estimated execution time."""
        return sum(p.estimated_time for p in self._property_budgets.values())

    @property
    def scaling_factor(self) -> float:
        """Budget scaling factor applied."""
        if not self._property_budgets:
            return 1.0

        baseline_time = sum(
            p.baseline_attempts * p.time_per_attempt
            for p in self._property_budgets.values()
        )
        if baseline_time <= 0:
            return 1.0

        return min(1.0, self.time_budget / baseline_time)

    @property
    def properties(self) -> list[PropertyBudget]:
        """Get all property budgets."""
        return list(self._property_budgets.values())

    def is_calibration_complete(self) -> bool:
        """Check if calibration is complete."""
        return self._calibration_complete
