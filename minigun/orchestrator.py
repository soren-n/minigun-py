"""
Running specifications

``run`` evaluates a set of test modules under a time budget and reports
through a reporter, in worker processes when asked for several jobs;
``check`` evaluates one specification with baseline attempts and no
budget. Both resolve every specification before anything runs, evaluate
every property, and remove the temporary fixtures they created at the
end.

Both can keep regressions: counterexamples recorded in files and replayed
before each property's own attempts (see ``minigun.regressions``). A run
keeps a file per test module in a directory, ``check`` one file. The files
are checked against the specifications before anything runs, and a new
counterexample is recorded as soon as its property has been reported.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from minigun import fixture, parallel, regressions, specify
from minigun.budget import TimeBudget, baseline_attempts, plan
from minigun.parallel import SpecLoader
from minigun.reporter import (
    JSONReporter,
    PlainReporter,
    QuietReporter,
    Reporter,
    RichReporter,
)
from minigun.specify import (
    Allowance,
    Outcome,
    Prop,
    Recorded,
    Resolved,
    Spec,
    SpecificationError,
    collect,
    select,
)

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


_REPORTERS: dict[OutputMode, Callable[[int, float | None, bool], Reporter]] = {
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
    :param select: Run only the properties whose descriptions contain one
        of these patterns, or every property when None. A selected
        property draws what it draws in a run of every property.
    :param regressions: A directory keeping a regressions file per test
        module, ``<module>.json``: its counterexamples are replayed before
        each property's own attempts, and the counterexample of a new
        failure is recorded in it. None keeps no regressions.
    :param verbose: Whether to show the shrink path of each counterexample.
    """

    time_budget: float
    seed: int | None = None
    output: OutputMode = OutputMode.RICH
    jobs: int = 1
    select: tuple[str, ...] | None = None
    regressions: Path | None = None
    verbose: bool = False

    def __post_init__(self) -> None:
        if self.time_budget <= 0:
            raise ValueError(
                f"The time budget must be positive, got {self.time_budget}"
            )
        if self.jobs < 1:
            raise ValueError(f"The jobs must be positive, got {self.jobs}")
        if self.select is not None and not self.select:
            raise ValueError("A selection needs at least one pattern")


def _seed(seed: int | None) -> int:
    return seed if seed is not None else secrets.randbits(64)


@dataclass(frozen=True)
class _Regressions:
    """The regressions of a run: what each property replays, and the
    file a new counterexample of each is recorded in.

    :param seed: The run seed, recorded with a new counterexample.
    :param files: The regressions file of each property by description;
        empty when the run keeps no regressions.
    :param recorded: The recorded draws of each property by description.
    :param resolved: Each property with a file by description, to draw
        the attempt of a new counterexample again when it is recorded.
    """

    seed: int
    files: dict[str, Path] = field(default_factory=dict)
    recorded: dict[str, list[Recorded]] = field(default_factory=dict)
    resolved: dict[str, Resolved] = field(default_factory=dict)

    def recorded_for(self, prop: Prop) -> list[Recorded]:
        return self.recorded.get(prop.desc, [])

    def record(self, outcome: Outcome, reporter: Reporter) -> None:
        """Record the counterexample of a reported outcome, when it is a
        new one drawn by the run, and tell the reporter where."""
        path = self.files.get(outcome.desc)
        example = outcome.counter_example
        if path is None or example is None:
            return
        # The law may have changed the arguments it was given, so what the
        # attempt drew is drawn again.
        drawn = specify.drawn_text(
            specify.redraw(
                self.resolved[outcome.desc], self.seed, example.attempt
            ).dissection
        )
        if drawn is None:
            raise RuntimeError(
                f'The failing attempt {example.attempt} of "{outcome.desc}" '
                "is discarded when drawn again; its generators are not "
                "deterministic"
            )
        regression = regressions.from_outcome(self.seed, outcome, drawn)
        if regression is None:
            return
        if regressions.record(path, regression):
            reporter.recorded(outcome.desc, str(path))


def _regressions(seed: int, files: list[tuple[Spec, Path]]) -> _Regressions:
    """Load each specification's regressions file; none kept for no files.

    :raises RegressionsError: When a file cannot be read or records a
        property its specification does not define.
    """
    by_desc: dict[str, Path] = {}
    recorded: dict[str, list[Recorded]] = {}
    resolved: dict[str, Resolved] = {}
    for spec, path in files:
        entries = regressions.load(path)
        descs = [prop.desc for prop in collect(spec)]
        regressions.check_properties(path, entries, descs)
        by_desc.update(dict.fromkeys(descs, path))
        resolved.update((r.prop.desc, r) for r in specify.resolve_all(spec))
        for entry in entries:
            recorded.setdefault(entry.desc, []).append(entry.recorded)
    return _Regressions(seed, by_desc, recorded, resolved)


def _evaluate_modules(
    seed: int,
    modules: list[TestModule],
    reporter: Reporter,
    allowance_for: specify.AllowanceFor,
    kept: _Regressions | None = None,
) -> bool:
    regressions_of_run = kept or _Regressions(seed)

    def _reported(outcome: Outcome) -> None:
        reporter.end_property(outcome)
        regressions_of_run.record(outcome, reporter)

    success = True
    for module in modules:
        reporter.start_module(module.name)
        holds = specify.evaluate(
            seed,
            module.spec,
            allowance_for,
            lambda prop: reporter.start_property(prop.desc),
            _reported,
            lambda prop, example: reporter.found_counter_example(
                prop.desc, example
            ),
            regressions_of_run.recorded_for,
        )
        success = success and holds
        reporter.end_module()
    return success


def _select(
    modules: list[TestModule], patterns: tuple[str, ...] | None
) -> list[TestModule]:
    """The modules pruned to the properties whose descriptions contain
    one of the patterns, without modules none of whose properties are
    selected.

    :raises SpecificationError: When a pattern matches no property.
    """
    if patterns is None:
        return modules
    descs = [prop.desc for module in modules for prop in collect(module.spec)]
    unmatched = [
        pattern
        for pattern in patterns
        if not any(pattern in desc for desc in descs)
    ]
    if unmatched:
        raise SpecificationError(
            "No property description contains "
            + ", ".join(f"'{pattern}'" for pattern in unmatched)
        )
    selected: list[TestModule] = []
    for module in modules:
        kept = select(
            module.spec,
            lambda prop: any(pattern in prop.desc for pattern in patterns),
        )
        if kept is not None:
            selected.append(TestModule(module.name, kept, module.load))
    return selected


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

    The modules' specifications are whole: ``config.select`` prunes them,
    and regressions files are checked against every property, selected
    or not.

    :return: Whether every module's specification holds.

    :raises SpecificationError: When a specification cannot be resolved,
        two properties share a description or a selection pattern matches
        no property; raised before any property runs.
    :raises RegressionsError: When a regressions file cannot be read or
        records a property its module does not define; raised before any
        property runs.
    :raises ValueError: When running with several jobs and a module has
        no loader.
    :raises RuntimeError: When a worker process fails.
    """
    seed = _seed(config.seed)
    directory = config.regressions
    kept = _regressions(
        seed,
        []
        if directory is None
        else [
            (module.spec, regressions.module_file(directory, module.name))
            for module in modules
        ],
    )
    modules = _select(modules, config.select)
    plans = plan(_resolve_modules(modules))
    loaders = _loaders(modules) if config.jobs > 1 else []
    budget = TimeBudget(config.time_budget, plans, config.jobs)
    reporter = _REPORTERS[config.output](
        seed, config.time_budget, config.verbose
    )
    reporter.start_run([module.name for module in modules], plans)
    with fixture.scope():
        if config.jobs == 1:
            success = _evaluate_modules(
                seed,
                modules,
                reporter,
                lambda r: budget.allowance(r.prop.desc),
                kept,
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
                kept.recorded_for,
                lambda outcome: kept.record(outcome, reporter),
            )
    reporter.finish()
    return success


def check(
    spec: Spec,
    seed: int | None = None,
    regressions: str | os.PathLike[str] | None = None,
    verbose: bool = False,
) -> bool:
    """Check a specification without a time budget, printing failures.

    Every property gets the number of attempts it declares, or else a
    baseline number derived from the size of its argument domain.

    :param spec: The specification.
    :param seed: The run seed; when None a fresh seed is drawn and printed
        on failure.
    :param regressions: A regressions file: its counterexamples are
        replayed before each property's own attempts, and the
        counterexample of a new failure is recorded in it. It is created
        when missing.
    :param verbose: Whether to print the shrink path of each
        counterexample.

    :return: Whether the specification holds.

    :raises SpecificationError: When the specification cannot be resolved.
    :raises RegressionsError: When the regressions file cannot be read or
        records a property the specification does not define.
    """
    seed_value = _seed(seed)
    resolved = specify.resolve_all(spec)
    kept = _regressions(
        seed_value, [] if regressions is None else [(spec, Path(regressions))]
    )

    def _allowance_for(r: Resolved) -> Allowance:
        attempts = r.prop.attempts
        if attempts is None:
            return Allowance(baseline_attempts(r.cardinality))
        return Allowance(attempts)

    reporter = PlainReporter(seed_value, None, verbose)
    reporter.start_run(["spec"], plan(resolved))
    with fixture.scope():
        success = _evaluate_modules(
            seed_value,
            [TestModule("spec", spec)],
            reporter,
            _allowance_for,
            kept,
        )
    reporter.finish()
    return success
