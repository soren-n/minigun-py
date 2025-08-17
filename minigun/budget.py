"""
Refactored Budget Allocation System

Clean, maintainable budget allocation with clear separation of concerns
and simplified state management.
"""

import math
from dataclasses import dataclass
from typing import Any


# Simplified attempt calculation strategies
class AttemptStrategy:
    """Encapsulates different attempt calculation strategies."""

    @staticmethod
    def theoretical_limit(cardinality: Any) -> int:
        """Secretary Problem optimal limit (√cardinality)."""
        domain_size = cardinality.evaluate()

        if domain_size >= float("inf"):
            return 10000
        return max(1, int(math.sqrt(domain_size)))

    @staticmethod
    def practical_baseline(cardinality: Any) -> int:
        """Practical attempts based on asymptotic complexity."""
        asymptotic = cardinality.asymptotic_class()

        if "∞" in asymptotic:
            return 1000
        elif "n^" in asymptotic:  # Exponential
            return 50
        elif "n²" in asymptotic:  # Quadratic
            return 100
        elif "n" in asymptotic:  # Linear
            domain_size = cardinality.evaluate()
            return max(10, int(math.sqrt(domain_size)))
        elif "log" in asymptotic:  # Logarithmic
            return 200
        else:  # O(1) - Constant
            domain_size = cardinality.evaluate()
            if domain_size <= 1000:
                return max(10, int(math.sqrt(domain_size)))
            elif domain_size <= 1_000_000:
                return int(
                    math.sqrt(1000) + math.log10(domain_size / 1000) * 10
                )
            else:
                return int(
                    math.sqrt(1000)
                    + math.log10(1000) * 10
                    + math.log10(domain_size / 1_000_000) * 5
                )


@dataclass
class PropertyBudget:
    """Immutable budget calculation for a single property."""

    name: str
    cardinality: Any
    theoretical_limit: int
    practical_baseline: int
    time_per_attempt: float
    final_attempts: int
    estimated_time: float

    @classmethod
    def create(
        cls, name: str, cardinality: Any, time_per_attempt: float = 0.0
    ) -> "PropertyBudget":
        """Create a property budget with calculated attempt limits."""
        theoretical = AttemptStrategy.theoretical_limit(cardinality)
        practical = AttemptStrategy.practical_baseline(cardinality)

        return cls(
            name=name,
            cardinality=cardinality,
            theoretical_limit=theoretical,
            practical_baseline=practical,
            time_per_attempt=time_per_attempt,
            final_attempts=practical,  # Start with practical as default
            estimated_time=practical * time_per_attempt,
        )

    def with_calibration(self, time_per_attempt: float) -> "PropertyBudget":
        """Return new PropertyBudget with calibration timing."""
        return PropertyBudget(
            name=self.name,
            cardinality=self.cardinality,
            theoretical_limit=self.theoretical_limit,
            practical_baseline=self.practical_baseline,
            time_per_attempt=time_per_attempt,
            final_attempts=self.practical_baseline,
            estimated_time=self.practical_baseline * time_per_attempt,
        )

    def with_final_attempts(self, attempts: int) -> "PropertyBudget":
        """Return new PropertyBudget with final allocated attempts."""
        return PropertyBudget(
            name=self.name,
            cardinality=self.cardinality,
            theoretical_limit=self.theoretical_limit,
            practical_baseline=self.practical_baseline,
            time_per_attempt=self.time_per_attempt,
            final_attempts=attempts,
            estimated_time=attempts * self.time_per_attempt,
        )

    def is_infinite_cardinality(self) -> bool:
        """Check if this property has infinite cardinality."""
        return "∞" in self.cardinality.asymptotic_class()

    def can_be_boosted(self) -> bool:
        """Check if this property can benefit from more attempts."""
        return (
            self.is_infinite_cardinality()
            and self.final_attempts < self.theoretical_limit
        )


class BudgetAllocationStrategy:
    """Encapsulates budget allocation logic."""

    @staticmethod
    def scale_down(
        properties: list[PropertyBudget], time_budget: float
    ) -> list[PropertyBudget]:
        """Scale down all properties proportionally to fit budget."""
        total_time = sum(p.estimated_time for p in properties)
        if total_time <= 0:
            return properties

        scaling_factor = time_budget / total_time

        return [
            p.with_final_attempts(
                max(1, int(p.practical_baseline * scaling_factor))
            )
            for p in properties
        ]

    @staticmethod
    def boost_infinite_properties(
        properties: list[PropertyBudget], time_budget: float
    ) -> list[PropertyBudget]:
        """Boost infinite cardinality properties with remaining budget."""
        # Calculate remaining budget
        current_time = sum(p.estimated_time for p in properties)
        remaining_budget = time_budget - current_time

        if remaining_budget <= 0:
            return properties

        # Find boostable properties
        boostable = [p for p in properties if p.can_be_boosted()]
        if not boostable:
            return properties

        # Distribute remaining budget
        result_properties = list(properties)  # Copy

        for i, prop in enumerate(result_properties):
            if not prop.can_be_boosted() or remaining_budget <= 0:
                continue

            if prop.time_per_attempt <= 0:
                continue

            # Calculate boost
            max_additional = prop.theoretical_limit - prop.final_attempts
            affordable_additional = int(
                remaining_budget / prop.time_per_attempt
            )
            additional_attempts = min(max_additional, affordable_additional)

            if additional_attempts > 0:
                new_attempts = prop.final_attempts + additional_attempts
                result_properties[i] = prop.with_final_attempts(new_attempts)
                remaining_budget -= additional_attempts * prop.time_per_attempt

        return result_properties


class BudgetAllocator:
    """Clean budget allocator."""

    def __init__(self, time_budget: float):
        self.time_budget = time_budget
        self._property_budgets: list[PropertyBudget] = []
        self._calibration_complete = False

    def add_property(self, name: str, cardinality: Any) -> None:
        """Add a property for budget allocation."""
        prop_budget = PropertyBudget.create(name, cardinality)
        self._property_budgets.append(prop_budget)

    def record_calibration(
        self, property_name: str, total_time: float, attempts: int
    ) -> None:
        """Record calibration timing for a property."""
        time_per_attempt = total_time / max(attempts, 1)

        # Update the property with calibration data
        for i, prop in enumerate(self._property_budgets):
            if prop.name == property_name:
                self._property_budgets[i] = prop.with_calibration(
                    time_per_attempt
                )
                break

    def finalize_allocation(self) -> None:
        """Finalize the budget allocation."""
        self._calibration_complete = True

        # Calculate total estimated time
        total_estimated = sum(p.estimated_time for p in self._property_budgets)

        if total_estimated <= self.time_budget:
            # Within budget - try to boost infinite properties
            self._property_budgets = (
                BudgetAllocationStrategy.boost_infinite_properties(
                    self._property_budgets, self.time_budget
                )
            )
        else:
            # Over budget - scale down proportionally
            self._property_budgets = BudgetAllocationStrategy.scale_down(
                self._property_budgets, self.time_budget
            )

    def get_allocated_attempts(self, property_name: str) -> int:
        """Get allocated attempts for a property."""
        if not self._calibration_complete:
            return 10  # Calibration phase

        for prop in self._property_budgets:
            if prop.name == property_name:
                return prop.final_attempts

        return 1  # Fallback

    def get_property_budget(self, property_name: str) -> PropertyBudget | None:
        """Get full budget info for a property."""
        for prop in self._property_budgets:
            if prop.name == property_name:
                return prop
        return None

    @property
    def total_estimated_time(self) -> float:
        """Total estimated execution time."""
        return sum(p.estimated_time for p in self._property_budgets)

    @property
    def scaling_factor(self) -> float:
        """Budget scaling factor applied."""
        if not self._property_budgets:
            return 1.0

        baseline_time = sum(
            p.practical_baseline * p.time_per_attempt
            for p in self._property_budgets
        )
        if baseline_time <= 0:
            return 1.0

        return min(1.0, self.time_budget / baseline_time)

    @property
    def properties(self) -> list[PropertyBudget]:
        """Get all property budgets."""
        return list(self._property_budgets)  # Return copy

    def is_calibration_complete(self) -> bool:
        """Check if calibration is complete."""
        return self._calibration_complete
