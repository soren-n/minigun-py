"""
Test Orchestration

Coordinates the two-phase, time-budgeted test run over a set of test
modules:

1. Calibration phase: every property is timed with a short adaptive run
   and registered with the budget allocator.
2. Execution phase: every module's specification is evaluated once, with
   attempts allocated from the time budget.

The orchestrator owns the run: it drives the evaluator in minigun.specify
and pushes results into a reporter. Reporters never influence execution.
"""

import secrets
import time
from dataclasses import dataclass
from typing import Any

from minigun import arbitrary as a
from minigun import generate as g
from minigun import specify
from minigun.budget import BudgetAllocator
from minigun.cardinality import Cardinality
from minigun.reporter import (
    CardinalityInfo,
    JSONReporter,
    QuietReporter,
    Reporter,
    RichReporter,
    TestResult,
)
from minigun.specify import Spec

###############################################################################
# Configuration
###############################################################################

#: Output modes mapped to their reporter types.
_REPORTERS: dict[str, type[Reporter]] = {
    "rich": RichReporter,
    "quiet": QuietReporter,
    "json": JSONReporter,
}


@dataclass
class TestModule:
    """A named test module specification."""

    name: str
    spec: Spec


@dataclass
class OrchestrationConfig:
    """Configuration for test orchestration.

    :param time_budget: The time budget for the execution phase in seconds.
    :param seed: The seed for random generation; when None a fresh seed is
        drawn and reported so the run can be reproduced.
    :param output: The output mode: "rich", "quiet" or "json".
    """

    time_budget: float
    seed: int | None = None
    output: str = "rich"

    def __post_init__(self) -> None:
        if self.output not in _REPORTERS:
            raise ValueError(
                f'Unknown output mode "{self.output}"; '
                f"expected one of {', '.join(sorted(_REPORTERS))}"
            )


###############################################################################
# Calibration
###############################################################################

# Adaptive calibration: run until timing stabilizes.
_MIN_CALIBRATION_ATTEMPTS = 10
_MAX_CALIBRATION_ATTEMPTS = 100
_STABILITY_EPSILON = 0.15
_STABILITY_WINDOW = 5


def _calibrate_property(
    prop: "specify._Prop[Any]",
    generators: dict[str, g.Generator[Any]],
    seed: int,
) -> tuple[float, int]:
    """Measure a property's execution time per attempt.

    Runs single attempts until the timing coefficient of variation drops
    below the stability threshold, then returns total time and attempts.
    Failures found during calibration are ignored; calibration measures
    time, the execution phase judges the property.
    """
    from minigun import search as s

    attempt_times: list[float] = []
    state = a.seed(seed)
    start_time = time.time()
    total_attempts = 0

    for total_attempts in range(1, _MAX_CALIBRATION_ATTEMPTS + 1):
        attempt_start = time.time()
        state, _ = s.find_counter_example(state, 1, prop.law, generators)
        attempt_times.append(time.time() - attempt_start)

        if total_attempts < _MIN_CALIBRATION_ATTEMPTS:
            continue

        recent_times = attempt_times[-_STABILITY_WINDOW:]
        if len(recent_times) < _STABILITY_WINDOW:
            continue

        mean_time = sum(recent_times) / len(recent_times)
        if mean_time <= 0:
            continue

        variance = sum((t - mean_time) ** 2 for t in recent_times) / len(
            recent_times
        )
        coefficient_of_variation = (variance**0.5) / mean_time
        if coefficient_of_variation < _STABILITY_EPSILON:
            break

    return time.time() - start_time, total_attempts


###############################################################################
# Orchestrator
###############################################################################
class TestOrchestrator:
    """Runs test modules through the two-phase, time-budgeted process."""

    def __init__(self, config: OrchestrationConfig):
        self.config = config

    def execute_tests(self, modules: list[TestModule]) -> bool:
        """Execute all test modules and report results.

        :param modules: The test modules to run.

        :return: Whether all properties held.
        """
        seed = (
            self.config.seed
            if self.config.seed is not None
            else secrets.randbits(64)
        )
        reporter = _REPORTERS[self.config.output](self.config.time_budget, seed)
        allocator = BudgetAllocator(self.config.time_budget)

        reporter.start_run([module.name for module in modules])

        # Calibration phase: time every resolvable property. Properties
        # with missing generators are left unregistered; the execution
        # phase reports them as failures.
        for module in modules:
            for prop in specify.collect_properties(module.spec):
                resolution = specify.resolved_generators(prop)
                if isinstance(resolution, str):
                    continue
                generators, total_cardinality = resolution
                allocator.add_property(prop.desc, total_cardinality)
                total_time, attempts = _calibrate_property(
                    prop, generators, seed
                )
                allocator.record_calibration(prop.desc, total_time, attempts)

        allocator.finalize_allocation()
        reporter.show_plan(allocator)

        # Execution phase: evaluate every module's spec once.
        def _attempts_for(
            prop: "specify._Prop[Any]", total_cardinality: Cardinality
        ) -> int:
            return allocator.get_allocated_attempts(prop.desc)

        def _on_result(
            desc: str,
            success: bool,
            duration: float,
            counter_example: str | None,
            error_message: str | None,
        ) -> None:
            budget = allocator.get_property_budget(desc)
            info = (
                CardinalityInfo(
                    domain_size=budget.cardinality,
                    attempt_limit=budget.attempt_limit,
                    allocated_attempts=budget.final_attempts,
                    estimated_time=budget.estimated_time,
                )
                if budget
                else None
            )
            reporter.end_test(
                TestResult(
                    name=desc,
                    success=success,
                    duration=duration,
                    counter_example=counter_example,
                    error_message=error_message,
                    cardinality_info=info,
                )
            )

        state = a.seed(seed)
        for module in modules:
            reporter.start_module(module.name)
            state, _ = specify.evaluate(
                state,
                module.spec,
                _attempts_for,
                reporter.start_test,
                _on_result,
            )
            reporter.end_module()

        specify.cleanup_temporary()
        reporter.finish()
        return reporter.overall_success
