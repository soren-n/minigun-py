"""
Test orchestration

Coordinates the two-phase, time-budgeted test run over a set of test
modules:

1. Calibration phase: every property is timed with a short adaptive run
   and registered with the budget allocator.
2. Execution phase: every module's specification is evaluated once, with
   attempts allocated from the time budget.

The orchestrator owns the run: it drives the evaluator in minigun.specify
and pushes results into a reporter. Reporters never influence execution.
``check`` is the standalone entry point without a time budget.
"""

import secrets
import time
from dataclasses import dataclass

from minigun import fixture, specify
from minigun import search as s
from minigun.budget import BudgetAllocator, baseline_attempts
from minigun.reporter import (
    CardinalityInfo,
    JSONReporter,
    QuietReporter,
    Reporter,
    RichReporter,
    TestResult,
    format_arguments,
)
from minigun.specify import Allowance, Outcome, Resolved, Spec
from minigun.util import relax_stdout_errors

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
# Outcome rendering
###############################################################################
def _describe(outcome: Outcome) -> tuple[str | None, str | None]:
    """The counterexample text and error message of an outcome."""
    if outcome.holds:
        return None, None
    if outcome.error is not None:
        return None, outcome.error
    example = outcome.counter_example
    if example is None:
        return None, None
    if example.exception is not None:
        message = (
            f'A test case of "{outcome.desc}" raised an exception:\n'
            f"{type(example.exception).__name__}: {example.exception}"
        )
    else:
        message = (
            f'A test case of "{outcome.desc}" failed with the following '
            "counter example:"
        )
    return format_arguments(example.args), message


###############################################################################
# Calibration
###############################################################################

# Adaptive calibration: run until timing stabilizes.
_MIN_CALIBRATION_ATTEMPTS = 10
_MAX_CALIBRATION_ATTEMPTS = 100
_STABILITY_EPSILON = 0.15
_STABILITY_WINDOW = 5


def _calibrate_property(resolved: Resolved, seed: int) -> tuple[float, int]:
    """Measure a property's execution time per attempt.

    Runs single attempts until the timing coefficient of variation drops
    below the stability threshold, then returns total time and attempts.
    Failures found during calibration are ignored; calibration measures
    time, the execution phase judges the property.
    """
    attempt_times: list[float] = []
    rng = specify.property_rng(seed, resolved.prop.desc)
    start_time = time.perf_counter()
    total_attempts = 0

    for total_attempts in range(1, _MAX_CALIBRATION_ATTEMPTS + 1):
        attempt_start = time.perf_counter()
        s.find_counter_example(rng, resolved.prop.law, resolved.generators, 1)
        attempt_times.append(time.perf_counter() - attempt_start)

        if total_attempts < _MIN_CALIBRATION_ATTEMPTS:
            continue

        recent_times = attempt_times[-_STABILITY_WINDOW:]
        mean_time = sum(recent_times) / len(recent_times)
        if mean_time <= 0:
            continue

        variance = sum((t - mean_time) ** 2 for t in recent_times) / len(
            recent_times
        )
        coefficient_of_variation = (variance**0.5) / mean_time
        if coefficient_of_variation < _STABILITY_EPSILON:
            break

    return time.perf_counter() - start_time, total_attempts


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

        :raises SpecificationError: When a module's specification cannot
            be resolved; raised before any property runs.
        """
        seed = (
            self.config.seed
            if self.config.seed is not None
            else secrets.randbits(64)
        )
        reporter = _REPORTERS[self.config.output](self.config.time_budget, seed)
        allocator = BudgetAllocator(self.config.time_budget)

        resolved_modules = [
            (module, specify.resolve_all(module.spec)) for module in modules
        ]

        reporter.start_run([module.name for module in modules])

        for _, resolved_props in resolved_modules:
            for resolved in resolved_props:
                allocator.add_property(resolved.prop.desc, resolved.cardinality)
                total_time, attempts = _calibrate_property(resolved, seed)
                allocator.record_calibration(
                    resolved.prop.desc, total_time, attempts
                )

        allocator.finalize_allocation()
        reporter.show_plan(allocator)

        def _allowance_for(resolved: Resolved) -> Allowance:
            return Allowance(
                allocator.get_allocated_attempts(resolved.prop.desc)
            )

        def _on_outcome(outcome: Outcome) -> None:
            budget = allocator.get_property_budget(outcome.desc)
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
            counter_example, error_message = _describe(outcome)
            reporter.end_test(
                TestResult(
                    name=outcome.desc,
                    success=outcome.holds,
                    duration=outcome.duration,
                    counter_example=counter_example,
                    error_message=error_message,
                    cardinality_info=info,
                )
            )

        for module in modules:
            reporter.start_module(module.name)
            specify.evaluate(
                seed,
                module.spec,
                _allowance_for,
                lambda prop: reporter.start_test(prop.desc),
                _on_outcome,
            )
            reporter.end_module()

        fixture.cleanup_temporary()
        reporter.finish()
        return reporter.overall_success


###############################################################################
# Standalone check
###############################################################################
def check(spec: Spec, seed: int | None = None) -> bool:
    """Check a specification, printing failures to stdout.

    The standalone entry point without a time budget: every property gets
    a baseline number of attempts derived from its input domain size.

    :param spec: The specification to check.
    :param seed: The run seed; when None a fresh seed is drawn and printed
        on failure so the run can be reproduced.

    :return: Whether the specification holds.

    :raises SpecificationError: When the specification cannot be resolved.
    """
    relax_stdout_errors()
    seed_value = seed if seed is not None else secrets.randbits(64)

    def _allowance_for(resolved: Resolved) -> Allowance:
        return Allowance(baseline_attempts(resolved.cardinality))

    def _on_outcome(outcome: Outcome) -> None:
        if outcome.holds:
            return
        counter_example, error_message = _describe(outcome)
        print(f"FAIL: {outcome.desc}")
        if error_message:
            print(error_message)
        if counter_example:
            print(counter_example)

    success = specify.evaluate(
        seed_value, spec, _allowance_for, lambda prop: None, _on_outcome
    )
    if not success:
        print(f"Reproduce with: check(spec, seed={seed_value})")
    fixture.cleanup_temporary()
    return success
