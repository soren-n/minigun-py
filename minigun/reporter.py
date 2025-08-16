# Enhanced test reporting with rich formatting
import time
from dataclasses import dataclass, field

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def format_counter_example(counter_example: str) -> str:
    """Format a counter-example string in a more readable way.

    Since we now use _call_context printer, the input should already be in the desired format.
    This function mainly serves as a pass-through with minimal cleanup if needed.
    """
    # The counter-example should already be in the correct format thanks to _call_context
    # Just return it as-is, maybe with some light cleanup
    return counter_example.strip()


@dataclass
class TestResult:
    """Result of a single test execution."""

    name: str
    success: bool
    duration: float
    counter_example: str | None = None
    error_message: str | None = None


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


class TestReporter:
    """Enhanced test reporter with rich formatting."""

    def __init__(self, verbose: bool = True):
        self.console = Console()
        self.verbose = verbose
        self.module_results: list[ModuleResult] = []
        self.current_module: ModuleResult | None = None
        self.overall_start_time = time.time()

    def start_testing(self, total_modules: int):
        """Start the overall testing process."""
        self.console.print(
            Panel.fit(
                "[bold blue]🚀 Minigun Property-Based Testing[/bold blue]",
                border_style="blue",
            )
        )
        self.overall_start_time = time.time()

    def start_module(self, module_name: str) -> None:
        """Start testing a module."""
        self.current_module = ModuleResult(name=module_name)
        if self.verbose:
            self.console.print(
                f"\n[bold cyan]📦 Testing module: {module_name}[/bold cyan]"
            )

    def start_test(self, test_name: str) -> None:
        """Start an individual test."""
        if self.verbose:
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
    ) -> None:
        """End an individual test."""
        result = TestResult(
            name=test_name,
            success=success,
            duration=duration,
            counter_example=counter_example,
            error_message=error_message,
        )

        if self.current_module:
            self.current_module.tests.append(result)

        if self.verbose:
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

    def end_module(self) -> None:
        """End testing a module."""
        if not self.current_module:
            return

        # Calculate module duration
        self.current_module.duration = sum(
            test.duration for test in self.current_module.tests
        )

        # Add to results
        self.module_results.append(self.current_module)

        # Print module summary
        if self.verbose:
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

        # Final result panel
        if all_passed:
            result_panel = Panel.fit(
                f"[bold green]🎉 All {total_tests} tests passed! 🎉[/bold green]\n[dim]Total time: {total_duration:.3f}s[/dim]",
                border_style="green",
            )
        else:
            result_panel = Panel.fit(
                f"[bold red]💥 {total_failed} of {total_tests} tests failed[/bold red]\n[dim]Total time: {total_duration:.3f}s[/dim]",
                border_style="red",
            )

        self.console.print("\n")
        self.console.print(result_panel)

    def get_overall_success(self) -> bool:
        """Return whether all tests passed."""
        return all(module.success for module in self.module_results)


# Global reporter instance
_global_reporter: TestReporter | None = None


def set_reporter(reporter: TestReporter) -> None:
    """Set the global reporter instance."""
    global _global_reporter
    _global_reporter = reporter


def get_reporter() -> TestReporter | None:
    """Get the global reporter instance."""
    return _global_reporter
