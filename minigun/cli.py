#!/usr/bin/env python3
"""
Minigun CLI - Property-based testing with rich output.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from minigun.specify import Spec


def discover_test_modules(
    test_dir: Path,
) -> tuple[dict[str, Spec], dict[str, str]]:
    """
    Discover test modules in a directory.

    Looks for Python files exporting a module-level specification named
    ``spec``.

    :param test_dir: Directory to search for test modules
    :return: A tuple of (module name -> spec) for importable modules and
        (module name -> error description) for modules that failed to
        load. A broken module is an error, never skipped.
    """
    test_modules: dict[str, Spec] = {}
    broken_modules: dict[str, str] = {}

    if not test_dir.exists() or not test_dir.is_dir():
        return test_modules, broken_modules

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
                broken_modules[module_name] = "could not create import spec"
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as error:
            broken_modules[module_name] = f"{type(error).__name__}: {error}"
            continue

        # Look for a module-level spec; files without one are not test
        # modules, but a module using the retired test() contract is an
        # error rather than a silent skip.
        if not hasattr(module, "spec"):
            if hasattr(module, "test"):
                broken_modules[module_name] = (
                    "defines test(); test modules now export a "
                    "module-level 'spec: Spec' instead"
                )
            continue

        module_spec = module.spec
        if not isinstance(module_spec, Spec):
            broken_modules[module_name] = (
                "'spec' attribute is not a minigun Spec"
            )
            continue

        test_modules[module_name] = module_spec

    return test_modules, broken_modules


def run_tests(
    time_budget: float,
    test_dir: Path = Path("tests"),
    modules: list[str] | None = None,
    quiet: bool = False,
    json_output: bool = False,
    seed: int | None = None,
) -> bool:
    """Run tests with a mandatory time budget."""
    from minigun.orchestrator import (
        OrchestrationConfig,
        TestModule,
        TestOrchestrator,
    )

    # Discover test modules
    test_modules, broken_modules = discover_test_modules(test_dir)

    if broken_modules:
        for name, error in sorted(broken_modules.items()):
            print(f"Error: Test module '{name}' failed to load: {error}")
        return False

    if not test_modules:
        print(f"No test modules found in {test_dir}")
        print("Tip: Test modules should export a module-level 'spec: Spec'")
        return False

    # Filter modules if specified
    if modules:
        unknown = [module for module in modules if module not in test_modules]
        if unknown:
            available = ", ".join(sorted(test_modules.keys()))
            for module in unknown:
                print(f"Error: Module '{module}' not found.")
            print(f"Available modules: {available}")
            return False
        test_modules = {module: test_modules[module] for module in modules}

    # Create test modules for orchestrator
    test_module_objects = [
        TestModule(name, module_spec)
        for name, module_spec in test_modules.items()
    ]

    # Configure and run orchestration
    if quiet:
        output = "quiet"
    elif json_output:
        output = "json"
    else:
        output = "rich"
    config = OrchestrationConfig(
        time_budget=time_budget, seed=seed, output=output
    )

    orchestrator = TestOrchestrator(config)
    return orchestrator.execute_tests(test_module_objects)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Minigun Property-Based Testing CLI - Discovers and runs test modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Discovery:
  Scans for Python files exporting a module-level 'spec: Spec'.
  By default, searches in ./tests directory.

Examples:
  minigun -t 30                          # Run all tests in ./tests with 30s budget
  minigun -t 60 --test-dir my_tests      # Run tests in ./my_tests directory
  minigun -t 30 --modules positive comprehensive  # Run specific modules
  minigun -t 60 --quiet                  # Minimal output for CI/CD
  minigun -t 30 --json                   # JSON output for tools
  minigun -t 30 --seed 42                # Reproduce a run
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
        "--seed",
        "-s",
        type=int,
        help="Seed for random generation; reported on failure for replay",
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
        test_modules, broken_modules = discover_test_modules(args.test_dir)
        if test_modules:
            print(f"Discovered test modules in {args.test_dir}:")
            for module in sorted(test_modules.keys()):
                print(f"  - {module}")
        if broken_modules:
            print(f"Broken test modules in {args.test_dir}:")
            for module, error in sorted(broken_modules.items()):
                print(f"  - {module}: {error}")
        if not test_modules and not broken_modules:
            print(f"No test modules found in {args.test_dir}")
            print("Tip: Test modules should export a module-level 'spec: Spec'")
        sys.exit(1 if broken_modules else 0)

    # Validate time budget when needed
    if args.time_budget is None:
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
        seed=args.seed,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
