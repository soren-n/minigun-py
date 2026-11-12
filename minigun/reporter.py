"""
Reporting

Reporters are passive sinks: the runner drives the run and calls the
reporter's hooks; reporters accumulate outcomes and render them. A
counterexample is announced as soon as it is found, before it is shrunk,
so a run whose shrinking is slow still says what failed; quiet and JSON
output announce it on stderr, keeping stdout for the final report. The
distribution of a property's labels is shown by the plain and rich
reporters and included in the JSON output; quiet output shows unmet
coverage only, as a failure. A verbose reporter also shows each
counterexample's shrink path, and every reporter says where a run recorded
a new counterexample. Four renderings are provided:

    - PlainReporter: failures and label distributions, for the
      standalone ``check``
    - QuietReporter: a pass/fail line per run and the failures, for CI
      pipelines
    - RichReporter: console tables and progress lines
    - JSONReporter: structured output for tool integration
"""

from __future__ import annotations

import io
import itertools
import json
import pprint
import shlex
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from minigun.budget import PropertyPlan
from minigun.parallel import exception_name
from minigun.search import CounterExample
from minigun.specify import Outcome

__all__ = [
    "relax_stdout_errors",
    "format_arguments",
    "describe_failure",
    "describe_found",
    "reproduce_flags",
    "describe_path",
    "format_distribution",
    "ModuleResult",
    "Reporter",
    "PlainReporter",
    "QuietReporter",
    "RichReporter",
    "JSONReporter",
]


###############################################################################
# Output encoding
###############################################################################
def relax_stdout_errors() -> None:
    """Make stdout escape unencodable characters instead of raising.

    On Windows, redirected output is encoded with the legacy ANSI code
    page, which cannot represent every character a counterexample may
    contain. Reporting a failure must not crash the run that found it, so
    strict streams are switched to backslash-escaping, which keeps the
    exact codepoints visible.
    """
    stream = sys.stdout
    if isinstance(stream, io.TextIOWrapper) and stream.errors == "strict":
        stream.reconfigure(errors="backslashreplace")


###############################################################################
# Formatting
###############################################################################
def format_arguments(args: dict[str, Any]) -> str:
    """Render counterexample arguments as ``name = value`` lines."""
    lines: list[str] = []
    for name, value in args.items():
        rendered = pprint.pformat(value, width=72, sort_dicts=False)
        if "\n" in rendered:
            lines.append(f"{name} =\n{textwrap.indent(rendered, '  ')}")
        else:
            lines.append(f"{name} = {rendered}")
    return "\n".join(lines)


def _not_minimal(example: CounterExample) -> str:
    if example.minimal:
        return ""
    return (
        f"\nShrinking stopped at the time budget after {example.shrinks} "
        "steps; the counter example may not be minimal."
    )


def _replayed(example: CounterExample) -> str:
    if example.seed is None:
        return ""
    return (
        "\nIt replays a recorded failure: attempt "
        f"{example.attempt + 1} of seed {example.seed}."
    )


def _describe_example(desc: str, example: CounterExample) -> str:
    notes = f"{_not_minimal(example)}{_replayed(example)}"
    if example.exception is not None:
        return (
            f'A test case of "{desc}" raised '
            f"{exception_name(example.exception)}: {example.exception}\n"
            f"{format_arguments(example.args)}{notes}"
        )
    return (
        f'A test case of "{desc}" failed with the following counter '
        f"example:\n{format_arguments(example.args)}{notes}"
    )


def describe_failure(outcome: Outcome) -> str:
    """Why an outcome did not hold: its error, its counterexample, or
    both, a paragraph each."""
    example = outcome.counter_example
    paragraphs = [] if outcome.error is None else [outcome.error]
    if example is not None:
        paragraphs.append(_describe_example(outcome.desc, example))
    if not paragraphs:
        return f'Property "{outcome.desc}" did not hold'
    return "\n".join(paragraphs)


def reproduce_flags(seed: int, module: str, desc: str) -> str:
    """The command line flags that run one property of a run again: the
    seed, its module and its description as the selection, quoted for a
    POSIX shell. A selected property draws what it draws in the full run,
    so the run fails again on the same attempt."""
    # The values are attached with "=", so one starting with a dash is
    # not taken for a flag.
    return (
        f"--seed {seed} --modules={shlex.quote(module)} "
        f"--select={shlex.quote(desc)}"
    )


def describe_found(desc: str, example: CounterExample) -> str:
    """One paragraph announcing a counterexample found, before shrinking."""
    failure = (
        "failed"
        if example.exception is None
        else f"raised {exception_name(example.exception)}: {example.exception}"
    )
    where = (
        f"on attempt {example.attempt + 1}"
        if example.seed is None
        else (
            f"again, replaying attempt {example.attempt + 1} of seed "
            f"{example.seed}"
        )
    )
    return (
        f'A test case of "{desc}" {failure} {where}; shrinking the counter '
        f"example:\n{format_arguments(example.args)}"
    )


def describe_path(example: CounterExample) -> str | None:
    """The shrink path of a counterexample: the arguments found, then at
    each accepted shrink step the arguments it changed; None when it took
    no step or its path was not recorded."""
    path = example.path
    if len(path) < 2:
        return None
    steps = len(path) - 1
    blocks = [
        f"Shrink path, {steps} step{'s' if steps != 1 else ''}:",
        f"found:\n{textwrap.indent(format_arguments(path[0]), '  ')}",
    ]
    for step, (before, after) in enumerate(itertools.pairwise(path), 1):
        changed = {
            name: value
            for name, value in after.items()
            if name not in before or repr(value) != repr(before[name])
        }
        body = (
            format_arguments(changed)
            if changed
            else "(the arguments print as before)"
        )
        blocks.append(f"step {step}:\n{textwrap.indent(body, '  ')}")
    return "\n".join(blocks)


def format_distribution(outcome: Outcome) -> str | None:
    """The labels of a property's tested attempts as ``percent label``
    lines, most frequent first, each covered label with its requirement;
    None when the law gave no labels and required no coverage."""
    names = set(outcome.labels) | set(outcome.coverage)
    if not names:
        return None
    evaluations = outcome.evaluations
    lines: list[str] = []
    for name in sorted(names, key=lambda n: (-outcome.labels.get(n, 0), n)):
        count = outcome.labels.get(name, 0)
        share = 100 * count / evaluations if evaluations else 0.0
        line = f"{share:5.1f}% {name} ({count})"
        required = outcome.coverage.get(name)
        if required is not None:
            line += f", required {100 * required:g}%"
        lines.append(line)
    return "\n".join(lines)


def _truncate(name: str, max_length: int = 30) -> str:
    if len(name) > max_length:
        return name[: max_length - 3] + "..."
    return name


###############################################################################
# Result model
###############################################################################
@dataclass
class ModuleResult:
    """The outcomes of one test module."""

    name: str
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.holds)

    @property
    def failed(self) -> int:
        return sum(1 for outcome in self.outcomes if not outcome.holds)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def duration(self) -> float:
        return sum(outcome.duration for outcome in self.outcomes)

    @property
    def success(self) -> bool:
        return self.failed == 0


###############################################################################
# Reporter base
###############################################################################
class Reporter:
    """Accumulates outcomes; subclasses override the display hooks.

    :param seed: The run seed.
    :param time_budget: The run's time budget in seconds, or None when the
        run has no budget.
    :param verbose: Whether to show the shrink path of each counterexample.
    """

    def __init__(
        self, seed: int, time_budget: float | None, verbose: bool = False
    ):
        relax_stdout_errors()
        self.seed = seed
        self.time_budget = time_budget
        self.verbose = verbose
        self.recorded_in: dict[str, str] = {}
        self.modules: list[ModuleResult] = []
        self.plans: dict[str, PropertyPlan] = {}
        self._current: ModuleResult | None = None
        self._started = time.perf_counter()

    # --- Accumulated results ------------------------------------------------
    @property
    def overall_success(self) -> bool:
        return all(module.success for module in self.modules)

    @property
    def total_tests(self) -> int:
        return sum(module.total for module in self.modules)

    @property
    def total_passed(self) -> int:
        return sum(module.passed for module in self.modules)

    @property
    def total_failed(self) -> int:
        return sum(module.failed for module in self.modules)

    @property
    def execution_time(self) -> float:
        return sum(module.duration for module in self.modules)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self._started

    def short_of_limit(self, outcome: Outcome) -> int | None:
        """The attempt limit of a property that held without reaching it,
        such as one whose time share ran out; else None.

        Such a property passed without trying as much of its domain as it
        is worth, so a run whose properties all held may still have
        covered little.
        """
        plan = self.plans.get(outcome.desc)
        if (
            plan is None
            or not outcome.holds
            or outcome.counter_example is not None
            or outcome.attempts >= plan.attempt_limit
        ):
            return None
        return plan.attempt_limit

    @property
    def total_short(self) -> int:
        return sum(
            1
            for module in self.modules
            for outcome in module.outcomes
            if self.short_of_limit(outcome) is not None
        )

    def _current_module(self) -> ModuleResult:
        if self._current is None:
            raise RuntimeError("No module is being reported")
        return self._current

    # --- Hooks --------------------------------------------------------------
    def start_run(
        self, module_names: list[str], plans: list[PropertyPlan]
    ) -> None:
        """The run begins with the given modules and property plans."""
        self._started = time.perf_counter()
        self.plans = {plan.desc: plan for plan in plans}

    def start_module(self, name: str) -> None:
        """Evaluation of a module's specification begins."""
        self._current = ModuleResult(name)

    def start_property(self, desc: str) -> None:
        """Evaluation of a property begins."""

    def found_counter_example(self, desc: str, example: CounterExample) -> None:
        """A counterexample to a property was found and is about to be
        shrunk."""

    def end_property(self, outcome: Outcome) -> None:
        """Evaluation of a property ended."""
        self._current_module().outcomes.append(outcome)

    def recorded(self, desc: str, path: str) -> None:
        """The counterexample of a property that just ended was recorded
        in a regressions file."""
        self.recorded_in[desc] = path

    def shrink_path(self, outcome: Outcome) -> str | None:
        """The shrink path of an outcome's counterexample when verbose."""
        example = outcome.counter_example
        if not self.verbose or example is None:
            return None
        return describe_path(example)

    def end_module(self) -> None:
        """Evaluation of a module's specification ended."""
        self.modules.append(self._current_module())
        self._current = None

    def finish(self) -> None:
        """The run ended; render the summary."""


###############################################################################
# Plain reporter
###############################################################################
class PlainReporter(Reporter):
    """Failures as they happen and the seed at the end; on success only
    the label distributions of properties that label their attempts."""

    def found_counter_example(self, desc: str, example: CounterExample) -> None:
        print(f"FOUND: {desc}")
        print(describe_found(desc, example), flush=True)

    def end_property(self, outcome: Outcome) -> None:
        super().end_property(outcome)
        distribution = format_distribution(outcome)
        if distribution is not None:
            print(f"LABELS: {outcome.desc} ({outcome.evaluations} tested)")
            print(textwrap.indent(distribution, "  "))
        if outcome.holds:
            return
        print(f"FAIL: {outcome.desc}")
        print(describe_failure(outcome))
        path = self.shrink_path(outcome)
        if path is not None:
            print(path)

    def recorded(self, desc: str, path: str) -> None:
        super().recorded(desc, path)
        print(f"RECORDED: {desc} in {path}")

    def finish(self) -> None:
        if not self.overall_success:
            print(f"Reproduce with: check(spec, seed={self.seed})")


###############################################################################
# Quiet reporter
###############################################################################
def _announce(
    module: str, desc: str, example: CounterExample, seed: int
) -> None:
    """Announce a counterexample on stderr, keeping stdout for the report."""
    print(f"FOUND [{module}] {desc} (seed {seed})", file=sys.stderr)
    print(
        textwrap.indent(describe_found(desc, example), "  "),
        file=sys.stderr,
        flush=True,
    )


class QuietReporter(Reporter):
    """A pass/fail line, and on failure the failing properties, why each
    failed, with its counterexample, and the seed. Counterexamples are
    announced on stderr as they are found."""

    def found_counter_example(self, desc: str, example: CounterExample) -> None:
        _announce(self._current_module().name, desc, example, self.seed)

    def finish(self) -> None:
        print(f"Tests: {'PASS' if self.overall_success else 'FAIL'}")
        if self.overall_success:
            return
        for module in self.modules:
            for outcome in module.outcomes:
                if not outcome.holds:
                    print(f"FAIL [{module.name}] {outcome.desc}")
                    print(textwrap.indent(describe_failure(outcome), "  "))
                    path = self.shrink_path(outcome)
                    if path is not None:
                        print(textwrap.indent(path, "  "))
                    if outcome.desc in self.recorded_in:
                        print(f"  Recorded in {self.recorded_in[outcome.desc]}")
                    flags = reproduce_flags(
                        self.seed, module.name, outcome.desc
                    )
                    print(f"  Reproduce with: {flags}")
        print(f"Reproduce with: --seed {self.seed}")


###############################################################################
# Rich console reporter
###############################################################################
class RichReporter(Reporter):
    """Console output with tables and progress lines."""

    def __init__(
        self, seed: int, time_budget: float | None, verbose: bool = False
    ):
        super().__init__(seed, time_budget, verbose)
        self.console = Console()

    def start_run(
        self, module_names: list[str], plans: list[PropertyPlan]
    ) -> None:
        super().start_run(module_names, plans)
        budget = (
            f"Time Budget: {self.time_budget:.1f}s | "
            if self.time_budget is not None
            else ""
        )
        self.console.print(
            Panel.fit(
                "[bold blue]Minigun Property-Based Testing[/bold blue]\n"
                f"[dim]{budget}Seed: {self.seed}[/dim]",
                border_style="blue",
            )
        )
        table = Table(title="Properties", box=box.ROUNDED)
        table.add_column("Property", style="yellow", no_wrap=True, width=40)
        table.add_column("Domain Size", justify="right", style="bright_blue")
        table.add_column("Attempt Limit", justify="right", style="cyan")
        for plan in plans:
            table.add_row(
                _truncate(plan.desc, 40),
                str(plan.cardinality),
                str(plan.attempt_limit),
            )
        self.console.print()
        self.console.print(table)

    def start_module(self, name: str) -> None:
        super().start_module(name)
        self.console.print(f"\n[bold cyan]Testing module: {name}[/bold cyan]")

    def start_property(self, desc: str) -> None:
        self.console.print(f"  [yellow]Running:[/yellow] {desc}", end="")

    def found_counter_example(self, desc: str, example: CounterExample) -> None:
        where = (
            f"counter example found on attempt {example.attempt + 1}"
            if example.seed is None
            else "recorded counter example failed again"
        )
        self.console.print(f" [red]{where}, shrinking[/red]")
        self.console.print(
            Panel(
                format_arguments(example.args),
                title="[red]Found[/red]",
                title_align="left",
                border_style="red",
                padding=(0, 1),
            )
        )
        # The verdict follows on a progress line of its own.
        self.console.print(f"  [yellow]Shrinking:[/yellow] {desc}", end="")

    def end_property(self, outcome: Outcome) -> None:
        super().end_property(outcome)
        limit = self.short_of_limit(outcome)
        detail = (
            (f"{outcome.replayed} replayed, " if outcome.replayed else "")
            + f"{outcome.attempts}"
            + ("" if limit is None else f"/{limit}")
            + " attempts"
            + (f", {outcome.discards} discarded" if outcome.discards else "")
            + f", {outcome.duration:.3f}s"
        )
        status = "[green]PASS[/green]" if outcome.holds else "[red]FAIL[/red]"
        self.console.print(f" {status} [dim]({detail})[/dim]")
        distribution = format_distribution(outcome)
        if distribution is not None:
            self.console.print(
                textwrap.indent(distribution, "      "),
                style="dim",
                highlight=False,
                markup=False,
                soft_wrap=True,
            )
        if outcome.holds:
            return
        flags = reproduce_flags(
            self.seed, self._current_module().name, outcome.desc
        )
        self.console.print(
            Panel(
                f"{describe_failure(outcome)}\nReproduce with: {flags}",
                title="[red]Failure[/red]",
                title_align="left",
                border_style="red",
                padding=(0, 1),
            )
        )
        path = self.shrink_path(outcome)
        if path is not None:
            self.console.print(
                Panel(
                    path,
                    title="[red]Shrink path[/red]",
                    title_align="left",
                    border_style="red",
                    padding=(0, 1),
                ),
                highlight=False,
            )

    def recorded(self, desc: str, path: str) -> None:
        super().recorded(desc, path)
        self.console.print(f"  [dim]Recorded in {path}[/dim]", highlight=False)

    def end_module(self) -> None:
        module = self._current_module()
        super().end_module()
        status = (
            "[green]ALL PASSED[/green]"
            if module.success
            else f"[red]{module.failed} FAILED[/red]"
        )
        self.console.print(
            f"  [bold]{status}[/bold] [dim]({module.passed}/{module.total} "
            f"tests, {module.duration:.3f}s)[/dim]"
        )

    def finish(self) -> None:
        table = Table(title="Test Summary", box=box.ROUNDED)
        table.add_column("Module", style="cyan", no_wrap=True)
        table.add_column("Tests", justify="center")
        table.add_column("Passed", justify="center", style="green")
        table.add_column("Failed", justify="center", style="red")
        table.add_column("Duration", justify="center")
        table.add_column("Status", justify="center")
        for module in self.modules:
            style = "green" if module.success else "red"
            table.add_row(
                module.name,
                str(module.total),
                str(module.passed),
                str(module.failed),
                f"{module.duration:.3f}s",
                f"[{style}]{'PASS' if module.success else 'FAIL'}[/{style}]",
            )
        table.add_section()
        style = "green" if self.overall_success else "red"
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{self.total_tests}[/bold]",
            f"[bold green]{self.total_passed}[/bold green]",
            f"[bold red]{self.total_failed}[/bold red]",
            f"[bold]{self.elapsed:.3f}s[/bold]",
            f"[bold {style}]{'PASS' if self.overall_success else 'FAIL'}"
            f"[/bold {style}]",
        )
        self.console.print()
        self.console.print(table)

        usage = ""
        if self.time_budget is not None:
            usage = (
                # Wall time, like the budget: with several workers the
                # properties' own durations add up to more.
                f"\n[dim]Run time: {self.elapsed:.3f}s / "
                f"{self.time_budget:.1f}s "
                f"({100 * self.elapsed / self.time_budget:.1f}%)[/dim]"
            )
        short = self.total_short
        if short:
            usage += (
                f"\n[yellow]{short} of {self.total_tests} properties stopped "
                "short of their attempt limit[/yellow]"
            )
        if self.overall_success:
            panel = Panel.fit(
                f"[bold green]All {self.total_tests} tests passed[/bold green]"
                f"{usage}",
                border_style="green",
            )
        else:
            panel = Panel.fit(
                f"[bold red]{self.total_failed} of {self.total_tests} tests "
                f"failed[/bold red]{usage}\n"
                f"[dim]Reproduce with: --seed {self.seed}[/dim]",
                border_style="red",
            )
        self.console.print()
        self.console.print(panel)


###############################################################################
# JSON reporter
###############################################################################
class JSONReporter(Reporter):
    """Structured output for tool integration, printed at the end.
    Counterexamples are announced on stderr as they are found."""

    def __init__(
        self, seed: int, time_budget: float | None, verbose: bool = False
    ):
        super().__init__(seed, time_budget, verbose)
        self._module_names: list[str] = []

    def start_run(
        self, module_names: list[str], plans: list[PropertyPlan]
    ) -> None:
        super().start_run(module_names, plans)
        self._module_names = list(module_names)

    def found_counter_example(self, desc: str, example: CounterExample) -> None:
        _announce(self._current_module().name, desc, example, self.seed)

    def _outcome(self, module: str, outcome: Outcome) -> dict[str, Any]:
        example = outcome.counter_example
        plan = self.plans.get(outcome.desc)
        return {
            "name": outcome.desc,
            "negated": outcome.negated,
            "success": outcome.holds,
            "duration": round(outcome.duration, 6),
            "attempts": outcome.attempts,
            "discards": outcome.discards,
            "counter_example": None
            if example is None
            else {
                "arguments": {
                    name: repr(value) for name, value in example.args.items()
                },
                "attempt": example.attempt,
                "seed": example.seed,
                "shrinks": example.shrinks,
                "minimal": example.minimal,
                "exception": None
                if example.exception is None
                else f"{exception_name(example.exception)}: {example.exception}",
                **(
                    {
                        "path": [
                            {name: repr(value) for name, value in args.items()}
                            for args in example.path
                        ]
                    }
                    if self.verbose
                    else {}
                ),
            },
            "error": outcome.error,
            "labels": dict(outcome.labels),
            "coverage": dict(outcome.coverage),
            "replayed": outcome.replayed,
            "stale": [
                {"seed": entry.seed, "attempt": entry.attempt}
                for entry in outcome.stale
            ],
            "recorded": self.recorded_in.get(outcome.desc),
            "reproduce": None
            if outcome.holds
            else reproduce_flags(self.seed, module, outcome.desc),
            "domain_size": None if plan is None else str(plan.cardinality),
            "attempt_limit": None if plan is None else plan.attempt_limit,
        }

    def finish(self) -> None:
        output = {
            "version": "3.0",
            "timestamp": datetime.now().isoformat(),
            "config": {
                "time_budget": self.time_budget,
                "seed": self.seed,
                "modules": self._module_names,
            },
            "summary": {
                "total_tests": self.total_tests,
                "total_passed": self.total_passed,
                "total_failed": self.total_failed,
                "total_duration": round(self.elapsed, 3),
                "execution_duration": round(self.execution_time, 3),
                "overall_success": self.overall_success,
            },
            "modules": [
                {
                    "name": module.name,
                    "tests": [
                        self._outcome(module.name, o) for o in module.outcomes
                    ],
                    "passed": module.passed,
                    "failed": module.failed,
                    "total": module.total,
                    "duration": round(module.duration, 3),
                    "success": module.success,
                }
                for module in self.modules
            ],
        }
        print(json.dumps(output, indent=2))
