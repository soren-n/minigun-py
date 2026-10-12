"""
Running specifications

``run`` evaluates a set of test modules under a time budget and reports
through a reporter, in worker processes when asked for several jobs;
``check`` evaluates one specification with baseline attempts and no
budget. Both resolve every specification before anything runs, evaluate
every property, and remove the temporary fixtures they created at the
end.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from minigun import fixture, parallel, specify
from minigun.budget import TimeBudget, baseline_attempts, plan
from minigun.parallel import SpecLoader
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
    """A named test module specification.

    :param load: Rebuilds the specification in a worker process; needed
        to run with several jobs. It must be picklable, e.g. a
        module-level function or a ``functools.partial`` of one.
    """

    name: str
    spec: Spec
    load: SpecLoader | None = None


@dataclass(frozen=True)
class RunConfig:
    """Configuration of a run.

    :param time_budget: The time budget in seconds; must be positive.
    :param seed: The run seed; when None a fresh seed is drawn and reported
        so the run can be reproduced.
    :param output: How the run reports.
    :param jobs: The number of properties evaluated at once; with more
        than one they are evaluated in worker processes, and the time
        budget is shared out as worker time.
    """

    time_budget: float
    seed: int | None = None
    output: OutputMode = OutputMode.RICH
    jobs: int = 1

    def __post_init__(self) -> None:
        if self.time_budget <= 0:
            raise ValueError(
                f"The time budget must be positive, got {self.time_budget}"
            )
        if self.jobs < 1:
            raise ValueError(f"The jobs must be positive, got {self.jobs}")


def _seed(seed: int | None) -> int:
    return seed if seed is not None else secrets.randbits(64)


def _evaluate_modules(
    seed: int,
    modules: list[TestModule],
    reporter: Reporter,
    allowance_for: specify.AllowanceFor,
) -> bool:
    success = True
    for module in modules:
        reporter.start_module(module.name)
        holds = specify.evaluate(
            seed,
            module.spec,
            allowance_for,
            lambda prop: reporter.start_property(prop.desc),
            reporter.end_property,
            lambda prop, example: reporter.found_counter_example(
                prop.desc, example
            ),
        )
        success = success and holds
        reporter.end_module()
    return success


def _loaders(modules: list[TestModule]) -> list[SpecLoader]:
    """Every module's loader.

    :raises ValueError: When a module has no loader.
    """
    missing = [module.name for module in modules if module.load is None]
    if missing:
        raise ValueError(
            "Running with several jobs needs a loader for every module; "
            f"missing for {', '.join(missing)}"
        )
    return [module.load for module in modules if module.load is not None]


def _resolve_modules(modules: list[TestModule]) -> list[Resolved]:
    """Resolve every module's specification.

    Descriptions identify properties across the whole run: the time
    budget, the reports and each property's random source are keyed by
    them, so they must be unique across modules, not only within one.

    :raises SpecificationError: When a specification cannot be resolved or
        two properties of the run share a description.
    """
    owners: dict[str, str] = {}
    resolved: list[Resolved] = []
    for module in modules:
        for r in specify.resolve_all(module.spec):
            desc = r.prop.desc
            if desc in owners:
                raise specify.SpecificationError(
                    f'Duplicate property description "{desc}" in modules '
                    f'"{owners[desc]}" and "{module.name}"; descriptions '
                    "must be unique across a run"
                )
            owners[desc] = module.name
            resolved.append(r)
    return resolved


def run(config: RunConfig, modules: list[TestModule]) -> bool:
    """Run test modules under a time budget.

    Property descriptions must be unique across all modules of the run.

    With several jobs, properties are evaluated in worker processes, each
    rebuilding the specifications from the modules' loaders, and reported
    in the same order as with one. A program running with several jobs
    must guard its entry point with ``if __name__ == "__main__":``, as
    for any use of ``multiprocessing`` with ``spawn``.

    :return: Whether every module's specification holds.

    :raises SpecificationError: When a specification cannot be resolved or
        two properties share a description; raised before any property
        runs.
    :raises ValueError: When running with several jobs and a module has
        no loader.
    :raises RuntimeError: When a worker process fails.
    """
    seed = _seed(config.seed)
    plans = plan(_resolve_modules(modules))
    loaders = _loaders(modules) if config.jobs > 1 else []
    budget = TimeBudget(config.time_budget, plans, config.jobs)
    reporter = _REPORTERS[config.output](seed, config.time_budget)
    reporter.start_run([module.name for module in modules], plans)
    with fixture.scope():
        if config.jobs == 1:
            success = _evaluate_modules(
                seed, modules, reporter, lambda r: budget.allowance(r.prop.desc)
            )
        else:
            success = parallel.evaluate(
                seed,
                [
                    (module.name, module.spec, load)
                    for module, load in zip(modules, loaders, strict=True)
                ],
                reporter,
                lambda r: budget.allowance(r.prop.desc),
                budget.finished,
                config.jobs,
            )
    reporter.finish()
    return success


def check(spec: Spec, seed: int | None = None) -> bool:
    """Check a specification without a time budget, printing failures.

    Every property gets the number of attempts it declares, or else a
    baseline number derived from the size of its argument domain.

    :return: Whether the specification holds.

    :raises SpecificationError: When the specification cannot be resolved.
    """
    seed_value = _seed(seed)
    resolved = specify.resolve_all(spec)

    def _allowance_for(r: Resolved) -> Allowance:
        attempts = r.prop.attempts
        if attempts is None:
            return Allowance(baseline_attempts(r.cardinality))
        return Allowance(attempts)

    reporter = PlainReporter(seed_value, None)
    reporter.start_run(["spec"], plan(resolved))
    with fixture.scope():
        success = _evaluate_modules(
            seed_value, [TestModule("spec", spec)], reporter, _allowance_for
        )
    reporter.finish()
    return success
