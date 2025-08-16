#!/usr/bin/env python3
"""
Minigun CLI - Property-based testing with rich output.
"""

import argparse
import sys


def get_available_modules() -> list[str]:
    """Get list of available test modules."""
    return ["negative", "positive", "comprehensive", "additional"]


def run_tests(
    time_budget: float,
    modules: list[str] | None = None,
    quiet: bool = False,
    json_output: bool = False,
) -> bool:
    """Run tests with rich console output and mandatory time budget."""
    from minigun.orchestrator import (
        OrchestrationConfig,
        TestModule,
        TestOrchestrator,
    )

    # Import test modules dynamically
    test_modules = {}
    try:
        from tests.additional import test as additional_test
        from tests.comprehensive import test as comprehensive_test
        from tests.negative import test as negative_test
        from tests.positive import test as positive_test

        test_modules = {
            "negative": negative_test,
            "positive": positive_test,
            "comprehensive": comprehensive_test,
            "additional": additional_test,
        }
    except ImportError as e:
        print(f"Error importing test modules: {e}")
        return False

    # Filter modules if specified
    if modules:
        filtered_modules = {}
        for module in modules:
            if module in test_modules:
                filtered_modules[module] = test_modules[module]
            else:
                print(f"Warning: Unknown test module '{module}', skipping.")
        test_modules = filtered_modules

    if not test_modules:
        print("No test modules to run.")
        return False

    # Create test modules for orchestrator
    test_module_objects = [
        TestModule(name, test_func) for name, test_func in test_modules.items()
    ]

    # Configure and run orchestration
    config = OrchestrationConfig(
        time_budget=time_budget,
        verbose=not quiet,
        quiet=quiet,
        json_output=json_output,
    )

    orchestrator = TestOrchestrator(config)
    return orchestrator.execute_tests(test_module_objects)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Minigun Property-Based Testing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  minigun-test -t 30                     # Run all tests with 30s budget
  minigun-test -t 60 --quiet             # Run with 60s budget, minimal output
  minigun-test -t 30 --json              # Run with JSON output for tools
  minigun-test -t 45 --modules positive comprehensive  # Run specific modules with 45s budget
  minigun-test --list-modules            # List available test modules
        """,
    )

    parser.add_argument(
        "--modules",
        "-m",
        nargs="*",
        choices=get_available_modules(),
        help="Specific test modules to run",
    )

    parser.add_argument(
        "--time-budget",
        "-t",
        type=float,
        help="Time budget in seconds for test execution (required)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output (just pass/fail status)",
    )

    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output results in JSON format for tool integration",
    )

    parser.add_argument(
        "--list-modules",
        "-l",
        action="store_true",
        help="List available test modules and exit",
    )

    parser.add_argument(
        "--version", "-v", action="store_true", help="Show version information"
    )

    args = parser.parse_args()

    if args.version:
        try:
            from minigun import __version__

            print(f"Minigun {__version__}")
        except ImportError:
            print("Minigun (version unknown)")
        return

    if args.list_modules:
        print("Available test modules:")
        for module in get_available_modules():
            print(f"  - {module}")
        return

    # Validate time budget when needed
    if not args.time_budget:
        print("Error: Time budget is required for running tests.")
        sys.exit(1)

    if args.time_budget <= 0:
        print("Error: Time budget must be positive.")
        sys.exit(1)

    # Run tests with time budget
    success = run_tests(
        args.time_budget,
        modules=args.modules,
        quiet=args.quiet,
        json_output=args.json,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
