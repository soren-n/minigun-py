"""
Test Orchestration System

This module provides clean separation between CLI, test execution, and reporting.
Implements the Orchestrator pattern to coordinate the two-phase testing process:
1. Calibration Phase: Measure execution time for budget allocation
2. Execution Phase: Run tests with allocated attempts

Key design principles:
- Single Responsibility: Each class has one clear purpose
- Dependency Injection: No global state or tight coupling
- Testability: Easy to unit test each component independently
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class TestModule:
    """Represents a test module to be executed."""

    name: str
    test_function: Callable[[], bool]


@dataclass
class OrchestrationConfig:
    """Configuration for test orchestration."""

    time_budget: float
    verbose: bool = True
    quiet: bool = False
    json_output: bool = False


@dataclass
class PhaseResult:
    """Result of a testing phase."""

    success: bool
    duration: float
    modules_executed: int


class TestOrchestrator:
    """
    Orchestrates the two-phase property-based testing process.

    This class separates the complex orchestration logic from the CLI,
    making the system more testable and maintainable.
    """

    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self._calibration_result: PhaseResult | None = None

    def execute_tests(self, modules: list[TestModule]) -> bool:
        """Execute all test modules using two-phase approach."""
        if self.config.quiet:
            return self._execute_quiet_mode(modules)

        if self.config.json_output:
            return self._execute_json_mode(modules)

        return self._execute_verbose_mode(modules)

    def _execute_quiet_mode(self, modules: list[TestModule]) -> bool:
        """Execute tests in quiet mode with minimal output."""
        overall_success = True

        for module in modules:
            try:
                success = module.test_function()
                overall_success &= success
            except Exception as e:
                print(f"Error: {e}")
                overall_success = False

        status = "PASS" if overall_success else "FAIL"
        print(f"Tests: {status}")
        return overall_success

    def _execute_verbose_mode(self, modules: list[TestModule]) -> bool:
        """Execute tests in verbose mode with rich output and two-phase process."""
        from minigun.reporter import TestReporter, set_reporter

        reporter = TestReporter(self.config.time_budget, verbose=True)
        set_reporter(reporter)
        reporter.start_testing(len(modules))

        self._calibration_result = self._execute_calibration_phase(
            modules, reporter
        )
        if not self._calibration_result.success:
            return False

        reporter.finalize_global_calibration_and_allocate()
        self._execute_execution_phase(modules, reporter)
        reporter.print_summary()
        return reporter.get_overall_success()

    def _execute_json_mode(self, modules: list[TestModule]) -> bool:
        """Execute tests in JSON mode with structured output."""
        from minigun.reporter import JSONReporter, set_reporter

        module_names = [module.name for module in modules]
        reporter = JSONReporter(self.config.time_budget, modules=module_names)
        set_reporter(reporter)
        reporter.start_testing(len(modules))

        self._calibration_result = self._execute_calibration_phase(
            modules, reporter
        )
        if not self._calibration_result.success:
            return False

        reporter.finalize_global_calibration_and_allocate()
        self._execute_execution_phase(modules, reporter)
        reporter.print_summary()
        return reporter.get_overall_success()

    def _execute_calibration_phase(
        self, modules: list[TestModule], reporter: Any
    ) -> PhaseResult:
        """Execute calibration phase for all modules."""
        if not self.config.json_output:
            print("📊 Global Calibration Phase")
            print(
                "Measuring execution time per property (adaptive calibration)..."
            )

        start_time = time.time()
        overall_success = True
        modules_executed = 0

        for module in modules:
            reporter.start_module(module.name, calibration_only=True)

            try:
                module.test_function()
                modules_executed += 1
            except Exception as e:
                if not self.config.json_output:
                    print(f"Error in calibration for module {module.name}: {e}")
                overall_success = False

            reporter.end_module(calibration_only=True)

        return PhaseResult(
            overall_success, time.time() - start_time, modules_executed
        )

    def _execute_execution_phase(
        self, modules: list[TestModule], reporter: Any
    ) -> PhaseResult:
        """Execute execution phase for all modules."""
        if not self.config.json_output:
            print("\n🚀 Global Execution Phase")

        start_time = time.time()
        overall_success = True
        modules_executed = 0

        for module in modules:
            reporter.start_module(module.name, execution_only=True)

            try:
                success = module.test_function()
                overall_success &= success
                modules_executed += 1
            except Exception as e:
                if not self.config.json_output:
                    print(f"Error in execution for module {module.name}: {e}")
                overall_success = False

            reporter.end_module()

        return PhaseResult(
            overall_success, time.time() - start_time, modules_executed
        )
