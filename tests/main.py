#!/usr/bin/env python3
"""
Minigun test runner with enhanced output.
"""

import sys

from minigun.reporter import TestReporter, set_reporter

from .additional import test as additional_test
from .comprehensive import test as comprehensive_test
from .negative import test as negative_test
from .positive import test as positive_test


def test() -> bool:
    """Run all tests with enhanced output."""
    # Test modules to run
    test_modules = [
        ("negative", negative_test),
        ("positive", positive_test),
        ("comprehensive", comprehensive_test),
        ("additional", additional_test),
    ]

    # Create and set up reporter
    reporter = TestReporter(verbose=True)
    set_reporter(reporter)

    # Start testing
    reporter.start_testing(len(test_modules))

    overall_success = True

    # Run each test module
    for module_name, test_func in test_modules:
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


if __name__ == "__main__":
    success = test()
    sys.exit(0 if success else 1)
