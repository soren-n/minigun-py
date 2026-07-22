"""
Test Reporting

Reporters are passive sinks: the orchestrator drives the run and calls the
reporter's hooks; reporters accumulate results and render them. Three
renderings are provided:

    - RichReporter: rich console output with tables and progress
    - QuietReporter: single pass/fail line for CI pipelines
    - JSONReporter: structured output for tool integration
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from minigun.budget import BudgetAllocator
from minigun.cardinality import Cardinality


###############################################################################
# Result model
###############################################################################
@dataclass
class CardinalityInfo:
    """Domain size and attempt allocation for a test."""

    domain_size: Cardinality
    attempt_limit: int
    allocated_attempts: int
    estimated_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "domain_size": str(self.domain_size),
            "attempt_limit": self.attempt_limit,
            "allocated_attempts": self.allocated_attempts,
            "estimated_time": self.estimated_time,
        }


@dataclass
class TestResult:
    """Result of a single test execution."""

    name: str
    success: bool
    duration: float
    counter_example: str | None = None
    error_message: str | None = None
    cardinality_info: CardinalityInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "success": self.success,
            "duration": self.duration,
            "counter_example": self.counter_example,
            "error_message": self.error_message,
            "cardinality_info": self.cardinality_info.to_dict()
            if self.cardinality_info
            else None,
        }


@dataclass
class ModuleResult:
    """Result of a test module execution."""

    name: str
    tests: list[TestResult] = field(default_factory=list)
    duration: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for test in self.tests if test.success)

    @property
    def failed(self) -> int:
        return sum(1 for test in self.tests if not test.success)

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def success(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "name": self.name,
            "tests": [test.to_dict() for test in self.tests],
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "duration": self.duration,
            "success": self.success,
        }


###############################################################################
# Reporter base: result accumulation with display hooks
###############################################################################
class Reporter:
    """Accumulates results; subclasses override the display hooks."""

    def __init__(self, time_budget: float, seed: int):
        self.time_budget = time_budget
        self.seed = seed
        self.module_results: list[ModuleResult] = []
        self._current_module: ModuleResult | None = None
        self.overall_start_time = time.time()
        self.pure_test_execution_time = 0.0

    # --- Result accumulation ------------------------------------------------
    @property
    def overall_success(self) -> bool:
        """Whether all recorded tests passed."""
        return all(module.success for module in self.module_results)

    @property
    def total_tests(self) -> int:
        return sum(module.total for module in self.module_results)

    @property
    def total_passed(self) -> int:
        return sum(module.passed for module in self.module_results)

    @property
    def total_failed(self) -> int:
        return sum(module.failed for module in self.module_results)

    # --- Run lifecycle hooks ------------------------------------------------
    def start_run(self, module_names: list[str]) -> None:
        """The run begins; calibration follows."""
        self.overall_start_time = time.time()

    def show_plan(self, allocator: BudgetAllocator) -> None:
        """Calibration is done and the budget has been allocated."""

    def start_module(self, module_name: str) -> None:
        """Execution of a module's spec begins."""
        self._current_module = ModuleResult(name=module_name)

    def start_test(self, test_name: str) -> None:
        """Execution of a property begins."""

    def end_test(self, result: TestResult) -> None:
        """Execution of a property ended."""
        assert self._current_module is not None, (
            "end_test called outside a module"
        )
        self._current_module.tests.append(result)
        self.pure_test_execution_time += result.duration

    def end_module(self) -> None:
        """Execution of a module's spec ended."""
        assert self._current_module is not None, (
            "end_module called outside a module"
        )
        self._current_module.duration = sum(
            test.duration for test in self._current_module.tests
        )
        self.module_results.append(self._current_module)
        self._current_module = None

    def finish(self) -> None:
        """The run ended; render the summary."""


###############################################################################
# Quiet reporter
###############################################################################
class QuietReporter(Reporter):
    """Minimal pass/fail output for CI pipelines."""

    def finish(self) -> None:
        status = "PASS" if self.overall_success else "FAIL"
        print(f"Tests: {status}")
        if not self.overall_success:
            for module in self.module_results:
                for test in module.tests:
                    if test.success:
                        continue
                    print(f"FAIL [{module.name}] {test.name}")
            print(f"Reproduce with: --seed {self.seed}")


###############################################################################
# Rich console reporter
###############################################################################
class RichReporter(Reporter):
    """Rich console output with tables and progress lines."""

    def __init__(self, time_budget: float, seed: int):
        super().__init__(time_budget, seed)
        self.console = Console()

    def start_run(self, module_names: list[str]) -> None:
        super().start_run(module_names)
        self.console.print(
            Panel.fit(
                "[bold blue]Minigun Property-Based Testing[/bold blue]\n"
                f"[dim]Time Budget: {self.time_budget:.1f}s | "
                f"Seed: {self.seed}[/dim]",
                border_style="blue",
            )
        )
        self.console.print("\n[bold blue]Calibration Phase[/bold blue]")
        self.console.print(
            "Measuring execution time per property (adaptive calibration)..."
        )

    def show_plan(self, allocator: BudgetAllocator) -> None:
        budget_status = (
            f"Budget: {allocator.time_budget:.1f}s, "
            f"Est: {allocator.total_estimated_time:.1f}s"
        )
        if allocator.scaling_factor < 1.0:
            budget_status += f", Scaled: {allocator.scaling_factor:.1f}x"

        plan_table = Table(
            title=f"Property Testing Plan ({budget_status})", box=box.ROUNDED
        )
        plan_table.add_column(
            "Property", style="yellow", no_wrap=True, width=30
        )
        plan_table.add_column(
            "Domain Size", justify="right", style="bright_blue"
        )
        plan_table.add_column(
            "Ideal Attempts", justify="right", style="bright_green"
        )
        plan_table.add_column("Actual Attempts", justify="right", style="cyan")
        plan_table.add_column("Est. Time", justify="right", style="magenta")

        for prop in allocator.properties:
            plan_table.add_row(
                _truncate(prop.name),
                str(prop.cardinality),
                str(prop.attempt_limit),
                str(prop.final_attempts),
                f"{prop.estimated_time:.2f}s",
            )

        self.console.print("\n")
        self.console.print(plan_table)
        self._print_budget_analysis(allocator)
        self.console.print(
            "\n[bold green]Starting Execution Phase[/bold green]"
        )

    def start_module(self, module_name: str) -> None:
        super().start_module(module_name)
        self.console.print(
            f"\n[bold cyan]Testing module: {module_name}[/bold cyan]"
        )

    def start_test(self, test_name: str) -> None:
        self.console.print(f"  [yellow]Running:[/yellow] {test_name}", end="")

    def end_test(self, result: TestResult) -> None:
        super().end_test(result)
        if result.success:
            self.console.print(
                f" [green]PASS[/green] [dim]({result.duration:.3f}s)[/dim]"
            )
            return
        self.console.print(
            f" [red]FAIL[/red] [dim]({result.duration:.3f}s)[/dim]"
        )
        if result.counter_example:
            self.console.print(
                Panel(
                    result.counter_example.strip(),
                    title="[red]Counter Example[/red]",
                    title_align="left",
                    border_style="red",
                    padding=(0, 1),
                )
            )
        if result.error_message:
            self.console.print(f"    [red]Error:[/red] {result.error_message}")

    def end_module(self) -> None:
        assert self._current_module is not None
        module = self._current_module
        super().end_module()

        if module.success:
            status_text = "[green]ALL PASSED[/green]"
        else:
            status_text = f"[red]{module.failed} FAILED[/red]"
        self.console.print(
            f"  [bold]{status_text}[/bold] "
            f"[dim]({module.passed}/{module.total} tests, "
            f"{module.duration:.3f}s)[/dim]"
        )

    def finish(self) -> None:
        total_duration = time.time() - self.overall_start_time

        table = Table(title="Test Summary", box=box.ROUNDED)
        table.add_column("Module", style="cyan", no_wrap=True)
        table.add_column("Tests", justify="center")
        table.add_column("Passed", justify="center", style="green")
        table.add_column("Failed", justify="center", style="red")
        table.add_column("Duration", justify="center")
        table.add_column("Status", justify="center")

        for module in self.module_results:
            status = "PASS" if module.success else "FAIL"
            status_style = "green" if module.success else "red"
            table.add_row(
                module.name,
                str(module.total),
                str(module.passed),
                str(module.failed),
                f"{module.duration:.3f}s",
                f"[{status_style}]{status}[/{status_style}]",
            )

        table.add_section()
        overall_status = "PASS" if self.overall_success else "FAIL"
        overall_style = "green" if self.overall_success else "red"
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{self.total_tests}[/bold]",
            f"[bold green]{self.total_passed}[/bold green]",
            f"[bold red]{self.total_failed}[/bold red]",
            f"[bold]{total_duration:.3f}s[/bold]",
            f"[bold {overall_style}]{overall_status}[/bold {overall_style}]",
        )

        self.console.print("\n")
        self.console.print(table)

        budget_usage = (self.pure_test_execution_time / self.time_budget) * 100
        budget_info = (
            f"Pure Test Time: {self.pure_test_execution_time:.3f}s / "
            f"{self.time_budget:.1f}s ({budget_usage:.1f}%)"
        )

        if self.overall_success:
            result_panel = Panel.fit(
                f"[bold green]All {self.total_tests} tests passed![/bold green]"
                f"\n[dim]{budget_info}[/dim]",
                border_style="green",
            )
        else:
            result_panel = Panel.fit(
                f"[bold red]{self.total_failed} of {self.total_tests} "
                f"tests failed[/bold red]\n"
                f"[dim]{budget_info}[/dim]\n"
                f"[dim]Reproduce with: --seed {self.seed}[/dim]",
                border_style="red",
            )

        self.console.print("\n")
        self.console.print(result_panel)

    def _print_budget_analysis(self, allocator: BudgetAllocator) -> None:
        """Print budget analysis and actionable suggestions."""
        if not allocator.properties:
            return

        slowest_props = sorted(
            [p for p in allocator.properties if p.estimated_time > 1.0],
            key=lambda p: p.estimated_time,
            reverse=True,
        )[:3]
        high_attempt_props = sorted(
            [p for p in allocator.properties if p.final_attempts > 100],
            key=lambda p: p.final_attempts,
            reverse=True,
        )[:3]

        analysis_parts = []

        if allocator.scaling_factor < 1.0:
            over_budget = allocator.total_estimated_time - allocator.time_budget
            over_percent = (
                allocator.total_estimated_time / allocator.time_budget
            ) * 100
            analysis_parts.append(
                f"[yellow]Over budget by {over_budget:.1f}s "
                f"({over_percent:.0f}%) - tests scaled down[/yellow]"
            )
            if over_budget > 5:
                suggested_budget = allocator.total_estimated_time * 1.1
                analysis_parts.append(
                    f"[dim]Suggestion: Try --time-budget "
                    f"{suggested_budget:.0f} for full coverage[/dim]"
                )
        elif allocator.total_estimated_time < allocator.time_budget * 0.5:
            analysis_parts.append(
                "[green]Well under budget - all properties get ideal "
                "attempts[/green]"
            )

        if slowest_props:
            slowest = ", ".join(
                f"{_truncate(p.name, 25)} ({p.estimated_time:.1f}s)"
                for p in slowest_props
            )
            analysis_parts.append(f"[dim]Slowest: {slowest}[/dim]")

        if high_attempt_props:
            most_attempts = ", ".join(
                f"{_truncate(p.name, 25)} ({p.final_attempts:,})"
                for p in high_attempt_props
            )
            analysis_parts.append(f"[dim]Most attempts: {most_attempts}[/dim]")

        if analysis_parts:
            self.console.print(
                "\n[bold bright_blue]Budget Analysis[/bold bright_blue]"
            )
            for part in analysis_parts:
                self.console.print(f"  {part}")


###############################################################################
# JSON reporter
###############################################################################
class JSONReporter(Reporter):
    """Structured JSON output for tool integration."""

    def __init__(self, time_budget: float, seed: int):
        super().__init__(time_budget, seed)
        self._module_names: list[str] = []

    def start_run(self, module_names: list[str]) -> None:
        super().start_run(module_names)
        self._module_names = module_names

    def finish(self) -> None:
        total_duration = time.time() - self.overall_start_time
        budget_usage = (self.pure_test_execution_time / self.time_budget) * 100

        output = {
            "version": "2.0",
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
                "total_duration": round(total_duration, 3),
                "execution_duration": round(self.pure_test_execution_time, 3),
                "budget_usage": round(budget_usage, 1),
                "overall_success": self.overall_success,
            },
            "modules": [module.to_dict() for module in self.module_results],
        }

        print(json.dumps(output, indent=2))


def _truncate(name: str, max_length: int = 30) -> str:
    """Truncate a property name if too long for table display."""
    if len(name) > max_length:
        return name[: max_length - 3] + "..."
    return name
