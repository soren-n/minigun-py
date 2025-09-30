# Test reporting with rich formatting
"""
Rich Console Reporting and Budget Allocation System.

This module provides comprehensive test reporting with rich console output,
cardinality-aware budget allocation, and detailed performance analysis.

Key Components:
    - TestReporter: Main reporting interface with rich console output
    - BudgetAllocator: Time budget distribution using Secretary Problem optimization
    - PropertyComplexity: Tracking for optimal vs allocated attempts
    - Execution plan tables, progress tracking, and cardinality analysis

Features:
    - Beautiful console output with tables, panels, and progress indicators
    - Two-phase testing: calibration followed by budget-aware execution
    - Cardinality analysis showing theoretical vs practical attempt allocation
    - Comprehensive timing analysis and resource utilization metrics
    - Module-based test organization and summary reporting

Integration:
    Works seamlessly with minigun.specify.check() to provide rich output
    for property-based testing with optimal resource allocation.

Example:
    ```python
    reporter = TestReporter(time_budget=30.0, verbose=True)
    set_reporter(reporter)
    # Reporter is automatically used by check() function
    ```
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


def format_counter_example(counter_example: str) -> str:
    """Format a counter-example string in a more readable way.

    Since we now use _call_context printer, the input should already be in the desired format.
    This function mainly serves as a pass-through with minimal cleanup if needed.
    """
    # The counter-example should already be in the correct format thanks to _call_context
    # Just return it as-is, maybe with some light cleanup
    return counter_example.strip()


@dataclass
class CardinalityInfo:
    """Cardinality analysis information for a test."""

    domain_size: Any  # Cardinality object from minigun.cardinality
    optimal_limit: int | str
    allocated_attempts: int
    estimated_time: float = 0.0  # Estimated execution time in seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "domain_size": str(self.domain_size),
            "optimal_limit": int(self.optimal_limit)
            if isinstance(self.optimal_limit, int | str)
            and str(self.optimal_limit).isdigit()
            else str(self.optimal_limit),
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


class TestReporter:
    """Test reporter with rich console formatting."""

    def __init__(self, time_budget: float, verbose: bool = True):
        self.console = Console()
        self.verbose = verbose
        self.time_budget = time_budget  # Time budget in seconds (required)
        self.module_results: list[ModuleResult] = []
        self.current_module: ModuleResult | None = None
        self.overall_start_time = time.time()
        self.execution_start_time = None  # Track when execution phase starts
        self.pure_test_execution_time = (
            0.0  # Track only actual property testing time, excluding overhead
        )
        self.budget_allocator = BudgetAllocator(time_budget)
        self.global_calibration_started = (
            False  # Track if we've started global calibration
        )
        self.global_execution_started = (
            False  # Track if we've shown the execution plan
        )
        self.is_last_module = False  # Track if we're processing the last module
        self.modules_processed = 0  # Track number of modules processed
        self.total_modules = 0  # Total number of modules to process

    def start_testing(self, total_modules: int):
        """Start the overall testing process."""
        self.total_modules = total_modules  # Store total number of modules
        title = f"[bold blue]🚀 Minigun Property-Based Testing[/bold blue]\n[dim]⏱️  Time Budget: {self.time_budget:.1f}s[/dim]"

        self.console.print(
            Panel.fit(
                title,
                border_style="blue",
            )
        )
        self.overall_start_time = time.time()

    def is_over_budget(self) -> bool:
        """Check if we're over the time budget."""
        elapsed = time.time() - self.overall_start_time
        return elapsed > self.time_budget

    def register_property_for_budget(
        self, name: str, cardinality: Any, optimal_attempts: int
    ) -> int:
        """Register a property for budget allocation and return allocated attempts."""
        # Add property to budget allocator
        self.budget_allocator.add_property(name, cardinality)
        return optimal_attempts  # Return initial attempts, will be adjusted after calibration

    def get_remaining_budget(self) -> float:
        """Get remaining time budget in seconds."""
        elapsed = time.time() - self.overall_start_time
        return max(0, self.time_budget - elapsed)

    def start_module(
        self,
        module_name: str,
        is_last_module: bool = False,
        calibration_only: bool = False,
        execution_only: bool = False,
    ) -> None:
        """Start testing a module."""
        self.current_module = ModuleResult(name=module_name)
        self.is_last_module = is_last_module  # Store for later use

        # Handle different phases
        self.calibration_only = calibration_only
        self.execution_only = execution_only

        if not calibration_only:
            self.modules_processed += 1  # Only count for execution phase

        if self.verbose and not calibration_only:
            # Don't print module headers during calibration phase
            self.console.print(
                f"\n[bold cyan]📦 Testing module: {module_name}[/bold cyan]"
            )

    def start_test(self, test_name: str) -> None:
        """Start an individual test."""
        # Only print during execution phase, not calibration
        if self.verbose and not getattr(self, "calibration_only", False):
            self.console.print(
                f"  [yellow]⏱️  Running:[/yellow] {test_name}", end=""
            )

    def end_test(
        self,
        test_name: str,
        success: bool,
        duration: float,
        counter_example: str | None = None,
        error_message: str | None = None,
        cardinality_info: CardinalityInfo | None = None,
    ) -> None:
        """End an individual test."""

        # Record calibration timing with budget allocator (during calibration phase)
        if (
            getattr(self, "calibration_only", False)
            and self.budget_allocator
            and cardinality_info
        ):
            self.budget_allocator.record_calibration(
                test_name, duration, cardinality_info.allocated_attempts
            )
            # Update estimated time from budget calculation
            prop_budget = self.budget_allocator.get_property_budget(test_name)
            if prop_budget:
                cardinality_info.estimated_time = prop_budget.estimated_time

        # Accumulate pure test execution time (only during execution phase, not calibration)
        if self.execution_start_time is not None and not getattr(
            self, "calibration_only", False
        ):
            self.pure_test_execution_time += duration

        result = TestResult(
            name=test_name,
            success=success,
            duration=duration,
            counter_example=counter_example,
            error_message=error_message,
            cardinality_info=cardinality_info,
        )

        if self.current_module:
            self.current_module.tests.append(result)

        # Only print during execution phase, not calibration
        if self.verbose and not getattr(self, "calibration_only", False):
            if success:
                self.console.print(
                    f" [green]✅ PASS[/green] [dim]({duration:.3f}s)[/dim]"
                )
            else:
                self.console.print(
                    f" [red]❌ FAIL[/red] [dim]({duration:.3f}s)[/dim]"
                )
                if counter_example:
                    formatted_example = format_counter_example(counter_example)
                    self.console.print(
                        Panel(
                            formatted_example,
                            title="[red]Counter Example[/red]",
                            title_align="left",
                            border_style="red",
                            padding=(0, 1),
                        )
                    )
                if error_message:
                    self.console.print(f"    [red]Error:[/red] {error_message}")

    def end_module(self, calibration_only: bool = False) -> None:
        """End testing a module."""
        if not self.current_module:
            return

        # Calculate module duration
        self.current_module.duration = sum(
            test.duration for test in self.current_module.tests
        )

        # Only add to results during execution phase, not calibration
        if not calibration_only:
            self.module_results.append(self.current_module)

        # Print module summary (only for execution phase)
        if self.verbose and not calibration_only:
            passed = self.current_module.passed
            failed = self.current_module.failed
            total = self.current_module.total
            duration = self.current_module.duration

            if self.current_module.success:
                status_text = "[green]✅ ALL PASSED[/green]"
            else:
                status_text = f"[red]❌ {failed} FAILED[/red]"

            self.console.print(
                f"  [bold]{status_text}[/bold] [dim]({passed}/{total} tests, {duration:.3f}s)[/dim]"
            )

        self.current_module = None

    def finalize_global_calibration_and_allocate(self) -> None:
        """Finalize global calibration phase and allocate budget for all modules."""
        if not self.budget_allocator:
            return

        # Finalize the calibration and allocation
        self.budget_allocator.finalize_allocation()

        # Start execution timing and reset pure test execution time
        self.execution_start_time = time.time()
        self.pure_test_execution_time = (
            0.0  # Reset to track only execution phase test time
        )

        # Print execution plan after global calibration
        if self.verbose:
            self.print_execution_plan()

    def print_execution_plan(self) -> None:
        """Print the execution plan table after calibration."""
        if not self.budget_allocator:
            return

        # Show the execution plan (budget info now in table title)
        self.console.print(
            "\n[bold green]🚀 Starting Execution Phase[/bold green]"
        )

        # Create and show the execution plan table with budget info in title
        budget_status = f"Budget: {self.budget_allocator.time_budget:.1f}s, Est: {self.budget_allocator.total_estimated_time:.1f}s"
        if self.budget_allocator.scaling_factor < 1.0:
            budget_status += (
                f", Scaled: {self.budget_allocator.scaling_factor:.1f}x"
            )

        plan_table = Table(
            title=f"📋 Property Testing Plan ({budget_status})", box=box.ROUNDED
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

        # Populate the table
        for prop in self.budget_allocator.properties:
            truncated_name = self._truncate_property_name(prop.name)
            # Display symbolic cardinality representation instead of numeric
            cardinality_display = self._format_cardinality_display(
                prop.cardinality
            )
            attempts_limit = (
                prop.theoretical_limit
            )  # The theoretical Secretary Problem limit
            est_attempts = prop.final_attempts  # The budget-allocated attempts
            est_time = f"{prop.estimated_time:.2f}s"

            plan_table.add_row(
                truncated_name,
                cardinality_display,
                str(attempts_limit),
                str(est_attempts),
                est_time,
            )

        self.console.print("\n")
        self.console.print(plan_table)

        # Add budget analysis and suggestions
        self._print_budget_analysis()

        self.global_execution_started = True

        # Start execution timing here
        self.execution_start_time = time.time()

    def print_cardinality_analysis(self) -> None:
        """Print cardinality analysis table for all tests."""
        # Collect all tests with cardinality info
        cardinality_tests = []
        for module in self.module_results:
            for test in module.tests:
                if test.cardinality_info:
                    cardinality_tests.append((module.name, test))

        if not cardinality_tests:
            return  # No cardinality info to display

        # Create cardinality analysis table
        card_table = Table(
            title="🧮 Cardinality-Based Complexity Analysis", box=box.ROUNDED
        )
        card_table.add_column(
            "Property", style="yellow", no_wrap=True, width=30
        )
        card_table.add_column(
            "Domain Size", justify="right", style="bright_blue"
        )
        card_table.add_column(
            "Ideal Attempts", justify="right", style="bright_green"
        )
        card_table.add_column(
            "Actual Attempts", justify="right", style="bright_magenta"
        )
        card_table.add_column("Est. Time", justify="right", style="bright_cyan")

        total_attempts = 0
        total_time = 0.0
        for _module_name, test in cardinality_tests:
            info = test.cardinality_info

            # Truncate property name if too long (max 30 chars with ellipsis)
            property_name = self._truncate_property_name(test.name)

            card_table.add_row(
                property_name,
                self._format_cardinality_display(info.domain_size),
                str(info.optimal_limit),
                str(info.allocated_attempts),
                f"{info.estimated_time:.3f}s",
            )
            total_attempts += info.allocated_attempts
            total_time += info.estimated_time

        # Add totals row
        card_table.add_section()
        card_table.add_row(
            "[bold]TOTAL[/bold]",
            "",
            "",
            f"[bold bright_magenta]{total_attempts}[/bold bright_magenta]",
            f"[bold bright_cyan]{total_time:.3f}s[/bold bright_cyan]",
        )

        self.console.print("\n")
        self.console.print(card_table)

    def print_summary(self) -> None:
        """Print final test summary."""
        total_duration = time.time() - self.overall_start_time

        # Calculate totals
        total_tests = sum(module.total for module in self.module_results)
        total_passed = sum(module.passed for module in self.module_results)
        total_failed = sum(module.failed for module in self.module_results)
        all_passed = total_failed == 0

        # Create summary table
        table = Table(title="Test Summary", box=box.ROUNDED)
        table.add_column("Module", style="cyan", no_wrap=True)
        table.add_column("Tests", justify="center")
        table.add_column("Passed", justify="center", style="green")
        table.add_column("Failed", justify="center", style="red")
        table.add_column("Duration", justify="center")
        table.add_column("Status", justify="center")

        for module in self.module_results:
            status = "✅ PASS" if module.success else "❌ FAIL"
            status_style = "green" if module.success else "red"

            table.add_row(
                module.name,
                str(module.total),
                str(module.passed),
                str(module.failed),
                f"{module.duration:.3f}s",
                f"[{status_style}]{status}[/{status_style}]",
            )

        # Add totals row
        table.add_section()
        overall_status = "✅ PASS" if all_passed else "❌ FAIL"
        overall_style = "green" if all_passed else "red"
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{total_tests}[/bold]",
            f"[bold green]{total_passed}[/bold green]",
            f"[bold red]{total_failed}[/bold red]",
            f"[bold]{total_duration:.3f}s[/bold]",
            f"[bold {overall_style}]{overall_status}[/bold {overall_style}]",
        )

        self.console.print("\n")
        self.console.print(table)

        # Print cardinality analysis table
        self.print_cardinality_analysis()

        # Final result panel - use pure test execution time for budget calculation
        if self.pure_test_execution_time > 0:
            # Use pure test execution time (excluding framework overhead)
            execution_duration = self.pure_test_execution_time
            budget_usage = (execution_duration / self.time_budget) * 100
            budget_info = f"Pure Test Time: {execution_duration:.3f}s / {self.time_budget:.1f}s ({budget_usage:.1f}%)"
        elif self.execution_start_time:
            # Fallback to total execution time if pure test time not available
            execution_duration = time.time() - self.execution_start_time
            budget_usage = (execution_duration / self.time_budget) * 100
            budget_info = f"Execution Time: {execution_duration:.3f}s / {self.time_budget:.1f}s ({budget_usage:.1f}%)"
        else:
            # Final fallback to total duration
            execution_duration = total_duration
            budget_usage = (execution_duration / self.time_budget) * 100
            budget_info = f"Total Time: {execution_duration:.3f}s / {self.time_budget:.1f}s ({budget_usage:.1f}%)"

        if all_passed:
            result_panel = Panel.fit(
                f"[bold green]🎉 All {total_tests} tests passed! 🎉[/bold green]\n[dim]{budget_info}[/dim]",
                border_style="green",
            )
        else:
            result_panel = Panel.fit(
                f"[bold red]💥 {total_failed} of {total_tests} tests failed[/bold red]\n[dim]{budget_info}[/dim]",
                border_style="red",
            )

        self.console.print("\n")
        self.console.print(result_panel)

    def get_overall_success(self) -> bool:
        """Return whether all tests passed."""
        return all(module.success for module in self.module_results)

    def start_calibration_phase(
        self, property_names_and_cardinalities: list[tuple[str, Any]]
    ) -> None:
        """Begin calibration phase for all properties."""
        if not self.budget_allocator:
            return

        # Only show the calibration message once globally
        if not self.global_calibration_started:
            self.console.print("\n[bold blue]📊 Calibration Phase[/bold blue]")
            self.console.print(
                "Running 10 silent tests per property to measure execution time..."
            )
            self.global_calibration_started = True

        # Add all properties for calibration
        for name, cardinality in property_names_and_cardinalities:
            self.budget_allocator.add_property(name, cardinality)

    def record_calibration_result(
        self, property_name: str, total_time: float, attempts: int
    ) -> None:
        """Record calibration timing result."""
        if self.budget_allocator:
            self.budget_allocator.record_calibration(
                property_name, total_time, attempts
            )

    def finalize_calibration_and_show_plan(self) -> None:
        """Finalize calibration and show the execution plan."""
        if not self.budget_allocator:
            return

        # Show execution plan once calibration is complete across all modules and we haven't shown it yet
        if (
            not self.global_execution_started
            and self.budget_allocator.is_calibration_complete()
            and self.modules_processed >= self.total_modules
        ):
            self.budget_allocator.finalize_allocation()

            # Show consolidated execution plan (budget info in table title)

            # Create and show the execution plan table with budget info in title
            budget_status = f"Budget: {self.budget_allocator.time_budget:.1f}s, Est: {self.budget_allocator.total_estimated_time:.1f}s"
            if self.budget_allocator.scaling_factor < 1.0:
                budget_status += (
                    f", Scaled: {self.budget_allocator.scaling_factor:.1f}x"
                )

            plan_table = Table(
                title=f"📋 Property Testing Plan ({budget_status})",
                box=box.ROUNDED,
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
            plan_table.add_column(
                "Actual Attempts", justify="right", style="cyan"
            )
            plan_table.add_column("Est. Time", justify="right", style="magenta")

            # Populate the table
            for prop in self.budget_allocator.properties:
                truncated_name = self._truncate_property_name(prop.name)
                # Display symbolic cardinality representation instead of numeric
                cardinality_display = self._format_cardinality_display(
                    prop.cardinality
                )
                attempts_limit = (
                    prop.theoretical_limit
                )  # The theoretical Secretary Problem limit
                est_attempts = (
                    prop.final_attempts
                )  # The budget-allocated attempts
                est_time = f"{prop.estimated_time:.2f}s"

                plan_table.add_row(
                    truncated_name,
                    cardinality_display,
                    str(attempts_limit),
                    str(est_attempts),
                    est_time,
                )

            self.console.print("\n")
            self.console.print(plan_table)

            # Add budget analysis and suggestions
            self._print_budget_analysis()

            self.console.print(
                "\n[bold green]🚀 Starting Execution Phase[/bold green]"
            )
            self.global_execution_started = True

    def get_allocated_attempts_for_property(self, property_name: str) -> int:
        """Get allocated attempts for a property during execution phase."""
        if self.budget_allocator:
            return self.budget_allocator.get_allocated_attempts(property_name)
        return 100  # Fallback

    def _print_budget_analysis(self) -> None:
        """Print budget analysis and actionable suggestions."""
        if not self.budget_allocator or not self.budget_allocator.properties:
            return

        # Find slowest properties
        slowest_props = sorted(
            [
                p
                for p in self.budget_allocator.properties
                if p.estimated_time > 1.0
            ],
            key=lambda p: p.estimated_time,
            reverse=True,
        )[:3]

        # Find most expensive properties (high attempts)
        high_attempt_props = sorted(
            [
                p
                for p in self.budget_allocator.properties
                if p.final_attempts > 100
            ],
            key=lambda p: p.final_attempts,
            reverse=True,
        )[:3]

        analysis_parts = []

        # Budget status
        if self.budget_allocator.scaling_factor < 1.0:
            over_budget = (
                self.budget_allocator.total_estimated_time
                - self.budget_allocator.time_budget
            )
            analysis_parts.append(
                f"[yellow]⚠️  Over budget by {over_budget:.1f}s ({((self.budget_allocator.total_estimated_time / self.budget_allocator.time_budget) * 100):.0f}%) - tests scaled down[/yellow]"
            )

            if over_budget > 5:
                suggested_budget = (
                    self.budget_allocator.total_estimated_time * 1.1
                )  # 10% buffer
                analysis_parts.append(
                    f"[dim]💡 Suggestion: Try --time-budget {suggested_budget:.0f} for full coverage[/dim]"
                )
        elif (
            self.budget_allocator.total_estimated_time
            < self.budget_allocator.time_budget * 0.5
        ):
            analysis_parts.append(
                "[green]✅ Well under budget - all properties get ideal attempts[/green]"
            )

        # Performance insights
        if slowest_props:
            prop_names = [
                self._truncate_property_name(p.name, 25) for p in slowest_props
            ]
            times = [f"{p.estimated_time:.1f}s" for p in slowest_props]
            analysis_parts.append(
                f"[dim]🐌 Slowest: {', '.join(f'{name} ({time})' for name, time in zip(prop_names, times, strict=False))}[/dim]"
            )

        if high_attempt_props:
            prop_names = [
                self._truncate_property_name(p.name, 25)
                for p in high_attempt_props
            ]
            attempts = [f"{p.final_attempts:,}" for p in high_attempt_props]
            analysis_parts.append(
                f"[dim]🔍 Most attempts: {', '.join(f'{name} ({att})' for name, att in zip(prop_names, attempts, strict=False))}[/dim]"
            )

        # Print analysis if we have insights
        if analysis_parts:
            self.console.print(
                "\n[bold bright_blue]💡 Budget Analysis[/bold bright_blue]"
            )
            for part in analysis_parts:
                self.console.print(f"  {part}")

    def _truncate_property_name(self, name: str, max_length: int = 30) -> str:
        """Truncate property name if too long."""
        if len(name) > max_length:
            return name[: max_length - 3] + "..."
        return name

    def _format_cardinality_display(self, cardinality: Any) -> str:
        """Format cardinality for display in tables, preferring symbolic representation."""
        # Convert numeric values to a more readable format
        cardinality_str = str(cardinality)

        # Handle special cases for better readability
        if cardinality_str == "∞":
            return "∞"

        # If it contains symbolic notation (BigO, mathematical symbols), return as-is
        if any(
            symbol in cardinality_str
            for symbol in ["O(", "Θ(", "Ω(", "×", "^", "log"]
        ):
            # Truncate if too long for table display
            if len(cardinality_str) > 15:
                return cardinality_str[:12] + "..."
            return cardinality_str

        # For very large numbers, show in scientific notation
        try:
            # Check if it's a pure number
            numeric_value = float(cardinality_str)
            if numeric_value >= 1e6:
                return f"{numeric_value:.1e}"
            elif numeric_value >= 1000:
                return f"{int(numeric_value):,}"
            else:
                return cardinality_str
        except (ValueError, OverflowError):
            # Fallback: return as-is but truncate if too long
            if len(cardinality_str) > 15:
                return cardinality_str[:12] + "..."
            return cardinality_str


class JSONReporter:
    """Test reporter with structured JSON output for tool integration."""

    def __init__(self, time_budget: float, modules: list[str] | None = None):
        self.time_budget = time_budget
        self.requested_modules = modules or []
        self.module_results: list[ModuleResult] = []
        self.current_module: ModuleResult | None = None
        self.overall_start_time = time.time()
        self.execution_start_time: float | None = None
        self.pure_test_execution_time = 0.0
        self.budget_allocator = BudgetAllocator(time_budget)

    def start_testing(self, total_modules: int) -> None:
        """Start the overall testing process."""
        self.overall_start_time = time.time()

    def register_property_for_budget(
        self, name: str, cardinality: Any, optimal_attempts: int
    ) -> int:
        """Register a property for budget allocation and return allocated attempts."""
        if self.budget_allocator:
            self.budget_allocator.add_property(name, cardinality)
        return optimal_attempts

    def get_remaining_budget(self) -> float:
        """Get remaining time budget in seconds."""
        elapsed = time.time() - self.overall_start_time
        return max(0, self.time_budget - elapsed)

    def is_over_budget(self) -> bool:
        """Check if we're over the time budget."""
        elapsed = time.time() - self.overall_start_time
        return elapsed > self.time_budget

    def start_module(
        self,
        module_name: str,
        is_last_module: bool = False,
        calibration_only: bool = False,
        execution_only: bool = False,
    ) -> None:
        """Start testing a module."""
        self.current_module = ModuleResult(name=module_name)

    def start_test(self, test_name: str) -> None:
        """Start an individual test."""
        pass

    def end_test(
        self,
        test_name: str,
        success: bool,
        duration: float,
        counter_example: str | None = None,
        error_message: str | None = None,
        cardinality_info: CardinalityInfo | None = None,
    ) -> None:
        """End an individual test."""
        # Record calibration timing with budget allocator (during calibration phase)
        calibration_only = getattr(self, "calibration_only", False)
        if calibration_only and self.budget_allocator and cardinality_info:
            self.budget_allocator.record_calibration(
                test_name, duration, cardinality_info.allocated_attempts
            )
            # Update estimated time from budget calculation
            prop_budget = self.budget_allocator.get_property_budget(test_name)
            if prop_budget:
                cardinality_info.estimated_time = prop_budget.estimated_time

        # Accumulate pure test execution time (only during execution phase)
        if self.execution_start_time is not None and not calibration_only:
            self.pure_test_execution_time += duration

        result = TestResult(
            name=test_name,
            success=success,
            duration=duration,
            counter_example=counter_example,
            error_message=error_message,
            cardinality_info=cardinality_info,
        )

        if self.current_module:
            self.current_module.tests.append(result)

    def end_module(self, calibration_only: bool = False) -> None:
        """End testing a module."""
        if not self.current_module:
            return

        # Calculate module duration
        self.current_module.duration = sum(
            test.duration for test in self.current_module.tests
        )

        # Only add to results during execution phase, not calibration
        if not calibration_only:
            self.module_results.append(self.current_module)

        self.current_module = None

    def finalize_global_calibration_and_allocate(self) -> None:
        """Finalize global calibration phase and allocate budget."""
        if self.budget_allocator:
            self.budget_allocator.finalize_allocation()
        self.execution_start_time = time.time()
        self.pure_test_execution_time = 0.0

    def print_execution_plan(self) -> None:
        """Print execution plan (no-op for JSON mode)."""
        pass

    def print_cardinality_analysis(self) -> None:
        """Print cardinality analysis (no-op for JSON mode)."""
        pass

    def print_summary(self) -> None:
        """Print final summary as JSON."""
        total_duration = time.time() - self.overall_start_time

        # Calculate totals
        total_tests = sum(module.total for module in self.module_results)
        total_passed = sum(module.passed for module in self.module_results)
        total_failed = sum(module.failed for module in self.module_results)
        overall_success = total_failed == 0

        # Calculate execution duration and budget usage
        if self.pure_test_execution_time > 0:
            execution_duration = self.pure_test_execution_time
        elif self.execution_start_time:
            execution_duration = time.time() - self.execution_start_time
        else:
            execution_duration = total_duration

        budget_usage = (execution_duration / self.time_budget) * 100

        # Build JSON output
        output = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "config": {
                "time_budget": self.time_budget,
                "modules": self.requested_modules,
                "quiet": False,
            },
            "summary": {
                "total_tests": total_tests,
                "total_passed": total_passed,
                "total_failed": total_failed,
                "total_duration": round(total_duration, 3),
                "execution_duration": round(execution_duration, 3),
                "budget_usage": round(budget_usage, 1),
                "overall_success": overall_success,
            },
            "modules": [module.to_dict() for module in self.module_results],
        }

        print(json.dumps(output, indent=2))

    def get_overall_success(self) -> bool:
        """Return whether all tests passed."""
        return all(module.success for module in self.module_results)

    def start_calibration_phase(
        self, property_names_and_cardinalities: list[tuple[str, Any]]
    ) -> None:
        """Begin calibration phase for all properties."""
        if self.budget_allocator:
            for name, cardinality in property_names_and_cardinalities:
                self.budget_allocator.add_property(name, cardinality)

    def record_calibration_result(
        self, property_name: str, total_time: float, attempts: int
    ) -> None:
        """Record calibration timing result."""
        if self.budget_allocator:
            self.budget_allocator.record_calibration(
                property_name, total_time, attempts
            )

    def finalize_calibration_and_show_plan(self) -> None:
        """Finalize calibration and show plan (no-op for JSON mode)."""
        pass

    def get_allocated_attempts_for_property(self, property_name: str) -> int:
        """Get allocated attempts for a property during execution phase."""
        if self.budget_allocator:
            return self.budget_allocator.get_allocated_attempts(property_name)
        return 100


# Global reporter instance
_global_reporter: TestReporter | JSONReporter | None = None


def set_reporter(reporter: TestReporter | JSONReporter) -> None:
    """Set the global reporter instance."""
    global _global_reporter
    _global_reporter = reporter


def get_reporter() -> TestReporter | JSONReporter | None:
    """Get the global reporter instance."""
    return _global_reporter
