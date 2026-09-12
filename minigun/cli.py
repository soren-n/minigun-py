"""
Command-line interface

Discovers test modules in a directory and runs them under a time budget.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from minigun import __version__
from minigun.orchestrator import OutputMode, RunConfig, TestModule, run
from minigun.specify import Spec, SpecificationError, is_spec

#: Package name under which discovered test modules are registered.
_DISCOVERY_NAMESPACE = "minigun_discovered"


def discover_test_modules(
    test_dir: Path,
) -> tuple[dict[str, Spec], dict[str, str]]:
    """Discover test modules in a directory.

    A test module is a Python file, not starting with an underscore, that
    exports a module-level specification named ``spec``.

    :return: Specifications by module name, and load errors by module name
        for modules that failed to import or export something other than a
        specification. A broken module is an error, never skipped.

    :raises NotADirectoryError: When ``test_dir`` is not a directory.
    """
    if not test_dir.is_dir():
        raise NotADirectoryError(f"Test directory {test_dir} does not exist")

    specs: dict[str, Spec] = {}
    broken: dict[str, str] = {}
    for path in sorted(test_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = path.stem
        # Import under a private namespace so discovered modules never
        # shadow installed packages. Registering in sys.modules before
        # execution is required for dataclasses with string annotations,
        # which resolve them through sys.modules.
        qualified = f"{_DISCOVERY_NAMESPACE}.{name}"
        try:
            spec = importlib.util.spec_from_file_location(qualified, path)
            if spec is None or spec.loader is None:
                broken[name] = "could not create an import spec"
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                del sys.modules[qualified]
                raise
        except Exception as error:
            broken[name] = f"{type(error).__name__}: {error}"
            continue

        if not hasattr(module, "spec"):
            if hasattr(module, "test"):
                broken[name] = (
                    "defines test(); test modules export a module-level "
                    "'spec: Spec' instead"
                )
            continue
        if not is_spec(module.spec):
            broken[name] = "'spec' is not a minigun specification"
            continue
        specs[name] = module.spec
    return specs, broken


def run_tests(
    time_budget: float,
    test_dir: Path = Path("tests"),
    modules: list[str] | None = None,
    output: OutputMode = OutputMode.RICH,
    seed: int | None = None,
) -> bool:
    """Discover and run test modules under a time budget.

    :return: Whether every selected module's specification holds. Broken
        modules, unknown module names and unresolvable specifications are
        reported as errors and count as failure.
    """
    try:
        specs, broken = discover_test_modules(test_dir)
    except NotADirectoryError as error:
        print(f"Error: {error}")
        return False

    if broken:
        for name, reason in sorted(broken.items()):
            print(f"Error: Test module '{name}' failed to load: {reason}")
        return False
    if not specs:
        print(f"No test modules found in {test_dir}")
        print("Tip: Test modules export a module-level 'spec: Spec'")
        return False

    if modules:
        unknown = [name for name in modules if name not in specs]
        if unknown:
            for name in unknown:
                print(f"Error: Module '{name}' not found.")
            print(f"Available modules: {', '.join(sorted(specs))}")
            return False
        specs = {name: specs[name] for name in modules}

    config = RunConfig(time_budget=time_budget, seed=seed, output=output)
    try:
        return run(
            config, [TestModule(name, spec) for name, spec in specs.items()]
        )
    except SpecificationError as error:
        print(f"Error: {error}")
        return False


def main() -> None:
    """The CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Minigun property-based testing: discovers and runs test modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test discovery:
  Scans a directory for Python files exporting a module-level 'spec: Spec'.
  By default, searches ./tests.

Examples:
  minigun -t 30                            # Run all tests with a 30s budget
  minigun -t 60 --test-dir my_tests        # Run tests in ./my_tests
  minigun -t 30 --modules lists strings    # Run specific modules
  minigun -t 60 --output quiet             # Minimal output for CI
  minigun -t 30 --output json              # JSON output for tools
  minigun -t 30 --seed 42                  # Reproduce a run
  minigun --list-modules                   # List discovered test modules
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
        help="Test modules to run, by name without .py",
    )
    parser.add_argument(
        "--time-budget",
        "-t",
        type=float,
        help="Time budget in seconds; required to run tests",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        help="Seed for random generation; reported on failure for replay",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=OutputMode,
        choices=list(OutputMode),
        default=OutputMode.RICH,
        help="Output mode (default: rich)",
    )
    parser.add_argument(
        "--list-modules",
        "-l",
        action="store_true",
        help="List discovered test modules and exit",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"Minigun {__version__}",
    )
    args = parser.parse_args()

    if args.list_modules:
        try:
            specs, broken = discover_test_modules(args.test_dir)
        except NotADirectoryError as error:
            print(f"Error: {error}")
            sys.exit(1)
        if specs:
            print(f"Discovered test modules in {args.test_dir}:")
            for name in sorted(specs):
                print(f"  - {name}")
        if broken:
            print(f"Broken test modules in {args.test_dir}:")
            for name, reason in sorted(broken.items()):
                print(f"  - {name}: {reason}")
        if not specs and not broken:
            print(f"No test modules found in {args.test_dir}")
            print("Tip: Test modules export a module-level 'spec: Spec'")
        sys.exit(1 if broken else 0)

    if args.time_budget is None:
        print("Error: --time-budget is required to run tests")
        print("Use --list-modules to see available test modules")
        sys.exit(1)
    if args.time_budget <= 0:
        print("Error: the time budget must be positive")
        sys.exit(1)

    success = run_tests(
        args.time_budget,
        test_dir=args.test_dir,
        modules=args.modules,
        output=args.output,
        seed=args.seed,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
