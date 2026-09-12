"""
Running specifications

``run`` evaluates a set of test modules under a time budget and reports
through a reporter; ``check`` evaluates one specification with baseline
attempts and no budget. Both resolve every specification before anything
runs, evaluate every property, and remove the temporary fixtures they
created at the end.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from minigun import fixture, specify
from minigun.budget import PropertyPlan, TimeBudget, baseline_attempts, plan
from minigun.reporter import (
    JSONReporter,
    PlainReporter,
    QuietReporter,
    Reporter,
    RichReporter,
)
from minigun.specify import Allowance, Resolved, Spec

__all__ = [
    "OutputMode",
    "TestModule",
    "RunConfig",
    "run",
    "check",
]


class OutputMode(StrEnum):
    """How a run reports."""

    RICH = "rich"
    QUIET = "quiet"
    JSON = "json"


_REPORTERS: dict[OutputMode, Callable[[int, float | None], Reporter]] = {
    OutputMode.RICH: RichReporter,
    OutputMode.QUIET: QuietReporter,
    OutputMode.JSON: JSONReporter,
}


@dataclass(frozen=True)
class TestModule:
    """A named test module specification."""

    name: str
    spec: Spec


@dataclass(frozen=True)
class RunConfig:
    """Configuration of a run.

    :param time_budget: The time budget in seconds; must be positive.
    :param seed: The run seed; when None a fresh seed is drawn and reported
        so the run can be reproduced.
    :param output: How the run reports.
    """

    time_budget: float
    seed: int | None = None
    output: OutputMode = OutputMode.RICH

    def __post_init__(self) -> None:
        if self.time_budget <= 0:
            raise ValueError(
                f"The time budget must be positive, got {self.time_budget}"
            )


def _seed(seed: int | None) -> int:
    return seed if seed is not None else secrets.randbits(64)


def _evaluate_modules(
    seed: int,
    modules: list[TestModule],
    reporter: Reporter,
    plans: list[PropertyPlan],
    allowance_for: specify.AllowanceFor,
) -> bool:
    reporter.start_run([module.name for module in modules], plans)
    success = True
    with fixture.scope():
        for module in modules:
            reporter.start_module(module.name)
            holds = specify.evaluate(
                seed,
                module.spec,
                allowance_for,
                lambda prop: reporter.start_property(prop.desc),
                reporter.end_property,
            )
            success = success and holds
            reporter.end_module()
    reporter.finish()
    return success


def run(config: RunConfig, modules: list[TestModule]) -> bool:
    """Run test modules under a time budget.

    :return: Whether every module's specification holds.

    :raises SpecificationError: When a specification cannot be resolved;
        raised before any property runs.
    """
    seed = _seed(config.seed)
    resolved = [
        r for module in modules for r in specify.resolve_all(module.spec)
    ]
    plans = plan(resolved)
    budget = TimeBudget(config.time_budget, plans)
    reporter = _REPORTERS[config.output](seed, config.time_budget)
    return _evaluate_modules(
        seed,
        modules,
        reporter,
        plans,
        lambda r: budget.allowance(r.prop.desc),
    )


def check(spec: Spec, seed: int | None = None) -> bool:
    """Check a specification without a time budget, printing failures.

    Every property gets a baseline number of attempts derived from the
    size of its argument domain.

    :return: Whether the specification holds.

    :raises SpecificationError: When the specification cannot be resolved.
    """
    seed_value = _seed(seed)
    resolved = specify.resolve_all(spec)

    def _allowance_for(r: Resolved) -> Allowance:
        return Allowance(baseline_attempts(r.cardinality))

    return _evaluate_modules(
        seed_value,
        [TestModule("spec", spec)],
        PlainReporter(seed_value, None),
        plan(resolved),
        _allowance_for,
    )
