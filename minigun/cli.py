#!/usr/bin/env python3
"""
Minigun CLI - Property-based testing with rich output.
"""
import argparse
import sys

from minigun.reporter import TestReporter, set_reporter


def get_available_modules() -> list[str]:
    """Get list of available test modules."""
    return ["negative", "positive", "comprehensive", "additional"]


def run_tests(modules: list[str] | None = None, quiet: bool = False) -> bool:
    """Run tests with enhanced output."""
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

    # Set up reporter
    if quiet:
        # Minimal output mode
        overall_success = True
        for module_name, test_func in test_modules.items():
            try:
                success = test_func()
                overall_success &= success
            except Exception as e:
                print(f"Error: {e}")
                overall_success = False

        status = "PASS" if overall_success else "FAIL"
        print(f"Tests: {status}")
        return overall_success
    else:
        # Enhanced output mode
        reporter = TestReporter(verbose=True)
        set_reporter(reporter)
        reporter.start_testing(len(test_modules))

        overall_success = True

        # Run each test module
        for module_name, test_func in test_modules.items():
            reporter.start_module(module_name)

            try:
                success = test_func()
                overall_success &= success
            except Exception as e:
                print(f"Error in module {module_name}: {e}")
                overall_success = False

            reporter.end_module()

        # Print final summary
        reporter.print_summary()
        return reporter.get_overall_success()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Minigun Property-Based Testing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  minigun-test                           # Run all tests with rich output
  minigun-test --quiet                   # Run all tests with minimal output
  minigun-test --modules positive comprehensive  # Run specific modules
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
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output (just pass/fail status)",
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

    # Run tests with enhanced output
    success = run_tests(modules=args.modules, quiet=args.quiet)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
