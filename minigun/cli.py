#!/usr/bin/env python3
"""
Minigun CLI - Property-based testing with rich output.
"""

import argparse
import importlib.util
import inspect
import sys
from pathlib import Path


def discover_test_modules(test_dir: Path) -> dict[str, callable]:
    """
    Discover test modules in a directory.

    Looks for Python files containing a function: def test() -> bool

    :param test_dir: Directory to search for test modules
    :return: Dictionary mapping module names to test functions
    """
    test_modules = {}

    if not test_dir.exists() or not test_dir.is_dir():
        return test_modules

    # Find all Python files
    for py_file in test_dir.glob("*.py"):
        # Skip __init__.py and private files
        if py_file.name.startswith("_"):
            continue

        module_name = py_file.stem

        try:
            # Dynamically import the module
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if not spec or not spec.loader:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for test() function
            if not hasattr(module, "test"):
                continue

            test_func = module.test
            if not callable(test_func):
                continue

            # Verify it has no parameters
            sig = inspect.signature(test_func)
            if len(sig.parameters) != 0:
                continue

            test_modules[module_name] = test_func
        except Exception:
            # Silently skip modules that fail to import
            continue

    return test_modules


def run_tests(
    time_budget: float,
    test_dir: Path = Path("tests"),
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

    # Discover test modules
    test_modules = discover_test_modules(test_dir)

    if not test_modules:
        print(f"No test modules found in {test_dir}")
        print("Tip: Test modules should contain 'def test() -> bool' function")
        return False

    # Filter modules if specified
    if modules:
        filtered_modules = {}
        for module in modules:
            if module in test_modules:
                filtered_modules[module] = test_modules[module]
            else:
                available = ", ".join(test_modules.keys())
                print(
                    f"Warning: Module '{module}' not found. Available: {available}"
                )
        test_modules = filtered_modules

    if not test_modules:
        print("No test modules to run after filtering.")
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
        description="Minigun Property-Based Testing CLI - Discovers and runs test modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Discovery:
  Scans for Python files containing 'def test() -> bool' function.
  By default, searches in ./tests directory.

Examples:
  minigun -t 30                          # Run all tests in ./tests with 30s budget
  minigun -t 60 --test-dir my_tests      # Run tests in ./my_tests directory
  minigun -t 30 --modules positive comprehensive  # Run specific modules
  minigun -t 60 --quiet                  # Minimal output for CI/CD
  minigun -t 30 --json                   # JSON output for tools
  minigun --list-modules                 # List discovered test modules
        """,
    )

    parser.add_argument(
        "--test-dir",
        "-d",
        type=Path,
        default=Path("tests"),
        help="Directory containing test modules (default: ./tests)",
    )

    parser.add_argument(
        "--modules",
        "-m",
        nargs="+",
        help="Specific test modules to run (by name, without .py)",
    )

    parser.add_argument(
        "--time-budget",
        "-t",
        type=float,
        help="Time budget in seconds for test execution (required for running tests)",
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
        help="List discovered test modules and exit",
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
        test_modules = discover_test_modules(args.test_dir)
        if test_modules:
            print(f"Discovered test modules in {args.test_dir}:")
            for module in sorted(test_modules.keys()):
                print(f"  - {module}")
        else:
            print(f"No test modules found in {args.test_dir}")
            print("Tip: Test modules should contain 'def test() -> bool'")
        return

    # Validate time budget when needed
    if not args.time_budget:
        print("Error: --time-budget is required for running tests")
        print("Use --list-modules to see available test modules")
        sys.exit(1)

    if args.time_budget <= 0:
        print("Error: Time budget must be positive")
        sys.exit(1)

    # Run tests with time budget
    success = run_tests(
        args.time_budget,
        test_dir=args.test_dir,
        modules=args.modules,
        quiet=args.quiet,
        json_output=args.json,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
