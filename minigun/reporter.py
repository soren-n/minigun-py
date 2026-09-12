"""
Reporting

Reporters are passive sinks: the runner drives the run and calls the
reporter's hooks; reporters accumulate outcomes and render them. Four
renderings are provided:

    - PlainReporter: failures only, for the standalone ``check``
    - QuietReporter: a pass/fail line per run, for CI pipelines
    - RichReporter: console tables and progress lines
    - JSONReporter: structured output for tool integration
"""

import io
import json
import pprint
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
from minigun.specify import Outcome


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


def describe_failure(outcome: Outcome) -> str:
    """One paragraph explaining why an outcome did not hold."""
    if outcome.error is not None:
        return outcome.error
    example = outcome.counter_example
    if example is None:
        return f'Property "{outcome.desc}" did not hold'
    if example.exception is not None:
        return (
            f'A test case of "{outcome.desc}" raised '
            f"{type(example.exception).__name__}: {example.exception}\n"
            f"{format_arguments(example.args)}"
        )
    return (
        f'A test case of "{outcome.desc}" failed with the following counter '
        f"example:\n{format_arguments(example.args)}"
    )


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
    """

    def __init__(self, seed: int, time_budget: float | None):
        relax_stdout_errors()
        self.seed = seed
        self.time_budget = time_budget
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

    def end_property(self, outcome: Outcome) -> None:
        """Evaluation of a property ended."""
        self._current_module().outcomes.append(outcome)

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
    """Failures as they happen and the seed at the end; nothing on success."""

    def end_property(self, outcome: Outcome) -> None:
        super().end_property(outcome)
        if outcome.holds:
            return
        print(f"FAIL: {outcome.desc}")
        print(describe_failure(outcome))

    def finish(self) -> None:
        if not self.overall_success:
            print(f"Reproduce with: check(spec, seed={self.seed})")


###############################################################################
# Quiet reporter
###############################################################################
class QuietReporter(Reporter):
    """A pass/fail line, and on failure the failing properties and seed."""

    def finish(self) -> None:
        print(f"Tests: {'PASS' if self.overall_success else 'FAIL'}")
        if self.overall_success:
            return
        for module in self.modules:
            for outcome in module.outcomes:
                if not outcome.holds:
                    print(f"FAIL [{module.name}] {outcome.desc}")
        print(f"Reproduce with: --seed {self.seed}")


###############################################################################
# Rich console reporter
###############################################################################
class RichReporter(Reporter):
    """Console output with tables and progress lines."""

    def __init__(self, seed: int, time_budget: float | None):
        super().__init__(seed, time_budget)
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

    def end_property(self, outcome: Outcome) -> None:
        super().end_property(outcome)
        detail = (
            f"{outcome.attempts} attempts"
            + (f", {outcome.discards} discarded" if outcome.discards else "")
            + f", {outcome.duration:.3f}s"
        )
        if outcome.holds:
            self.console.print(f" [green]PASS[/green] [dim]({detail})[/dim]")
            return
        self.console.print(f" [red]FAIL[/red] [dim]({detail})[/dim]")
        self.console.print(
            Panel(
                describe_failure(outcome),
                title="[red]Failure[/red]",
                title_align="left",
                border_style="red",
                padding=(0, 1),
            )
        )

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
                f"\n[dim]Test time: {self.execution_time:.3f}s / "
                f"{self.time_budget:.1f}s "
                f"({100 * self.execution_time / self.time_budget:.1f}%)[/dim]"
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
    """Structured output for tool integration, printed at the end."""

    def __init__(self, seed: int, time_budget: float | None):
        super().__init__(seed, time_budget)
        self._module_names: list[str] = []

    def start_run(
        self, module_names: list[str], plans: list[PropertyPlan]
    ) -> None:
        super().start_run(module_names, plans)
        self._module_names = list(module_names)

    def _outcome(self, outcome: Outcome) -> dict[str, Any]:
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
                "exception": None
                if example.exception is None
                else f"{type(example.exception).__name__}: {example.exception}",
            },
            "error": outcome.error,
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
                    "tests": [self._outcome(o) for o in module.outcomes],
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
