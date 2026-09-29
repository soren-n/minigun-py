"""
Command-line interface

Discovers test modules in a directory and runs them under a time budget.

Test modules are imported as submodules of a package registered for their
directory, so they can import helper modules beside them relatively, e.g.
``from ._helpers import model`` or ``from .support.models import Model``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import types
from pathlib import Path

from minigun import __version__
from minigun.orchestrator import OutputMode, RunConfig, TestModule, run
from minigun.specify import (
    Prop,
    Spec,
    SpecificationError,
    collect,
    is_spec,
    select,
)

__all__ = [
    "find_test_modules",
    "discover_test_modules",
    "select_properties",
    "run_tests",
    "main",
]


#: Package name under which discovered test modules are registered.
_DISCOVERY_NAMESPACE = "minigun_discovered"


def _directory_package(test_dir: Path) -> str:
    """Register the package that a directory's test modules belong to.

    Its path is the directory itself, so relative imports in test modules
    resolve against it. Each directory gets a package of its own, named
    by a digest of its resolved path, so helper modules of different
    directories never share an entry in ``sys.modules``.

    :return: The package name.
    """
    if _DISCOVERY_NAMESPACE not in sys.modules:
        namespace = types.ModuleType(_DISCOVERY_NAMESPACE)
        namespace.__path__ = []
        sys.modules[_DISCOVERY_NAMESPACE] = namespace
    directory = str(test_dir.resolve())
    digest = hashlib.sha256(directory.encode()).hexdigest()[:16]
    name = f"{_DISCOVERY_NAMESPACE}.d{digest}"
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [directory]
        package.__package__ = name
        sys.modules[name] = package
    return name


def find_test_modules(test_dir: Path) -> dict[str, Path]:
    """The candidate test modules of a directory, without importing them.

    A candidate is a Python file whose name does not start with an
    underscore; files starting with one are helpers.

    :return: Paths by module name.

    :raises NotADirectoryError: When ``test_dir`` is not a directory.
    """
    if not test_dir.is_dir():
        raise NotADirectoryError(f"Test directory {test_dir} does not exist")
    return {
        path.stem: path
        for path in sorted(test_dir.glob("*.py"))
        if not path.name.startswith("_")
    }


def discover_test_modules(
    test_dir: Path, names: list[str] | None = None
) -> tuple[dict[str, Spec], dict[str, str]]:
    """Load test modules from a directory.

    A test module is a candidate module that exports a module-level
    specification named ``spec``. Only the named modules are imported
    when names are given, so a broken module elsewhere in the directory
    does not stop them from running.

    :param names: The modules to load, or None for every candidate.

    :return: Specifications by module name, and load errors by module name
        for modules that failed to import or export something other than a
        specification. A broken module is an error, never skipped.

    :raises NotADirectoryError: When ``test_dir`` is not a directory.
    :raises ValueError: When a name is not a candidate module.
    """
    candidates = find_test_modules(test_dir)
    if names is not None:
        unknown = [name for name in names if name not in candidates]
        if unknown:
            raise ValueError(f"No test modules named {', '.join(unknown)}")
        candidates = {name: candidates[name] for name in names}
    package = _directory_package(test_dir)

    specs: dict[str, Spec] = {}
    broken: dict[str, str] = {}
    for name, path in candidates.items():
        # Import under a private namespace so discovered modules never
        # shadow installed packages. Registering in sys.modules before
        # execution is required for dataclasses with string annotations,
        # which resolve them through sys.modules.
        qualified = f"{package}.{name}"
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


def select_properties(
    specs: dict[str, Spec], patterns: list[str]
) -> tuple[dict[str, Spec], list[str]]:
    """The properties whose descriptions contain any of the patterns.

    A property draws from a source derived from the run seed and its
    description alone, so a selected property draws the same values as
    it does in a run of every module.

    :return: The pruned specifications by module name, without modules
        none of whose properties are selected, and the patterns that
        match no property.
    """

    def _keep(prop: Prop) -> bool:
        return any(pattern in prop.desc for pattern in patterns)

    selected: dict[str, Spec] = {}
    for name, spec in specs.items():
        kept = select(spec, _keep)
        if kept is not None:
            selected[name] = kept
    descs = [prop.desc for spec in specs.values() for prop in collect(spec)]
    unmatched = [
        pattern
        for pattern in patterns
        if not any(pattern in desc for desc in descs)
    ]
    return selected, unmatched


def run_tests(
    time_budget: float,
    test_dir: Path = Path("tests"),
    modules: list[str] | None = None,
    output: OutputMode = OutputMode.RICH,
    seed: int | None = None,
    patterns: list[str] | None = None,
) -> bool:
    """Discover and run test modules under a time budget.

    Only the selected modules are imported when ``modules`` is given, and
    only the properties whose descriptions contain one of ``patterns``
    run when it is given.

    :return: Whether every selected module's specification holds. Broken
        modules, unknown module names, selected modules without a
        specification, patterns matching no property and unresolvable
        specifications are reported as errors and count as failure.
    """
    try:
        candidates = find_test_modules(test_dir)
    except NotADirectoryError as error:
        print(f"Error: {error}")
        return False

    if modules:
        unknown = [name for name in modules if name not in candidates]
        if unknown:
            for name in unknown:
                print(f"Error: Module '{name}' not found.")
            print(f"Available modules: {', '.join(sorted(candidates))}")
            return False
    specs, broken = discover_test_modules(test_dir, modules or None)

    if broken:
        for name, reason in sorted(broken.items()):
            print(f"Error: Test module '{name}' failed to load: {reason}")
        return False
    if modules:
        missing = [name for name in modules if name not in specs]
        if missing:
            for name in missing:
                print(f"Error: Module '{name}' exports no 'spec: Spec'")
            return False
        specs = {name: specs[name] for name in modules}
    if not specs:
        print(f"No test modules found in {test_dir}")
        print("Tip: Test modules export a module-level 'spec: Spec'")
        return False
    if patterns:
        specs, unmatched = select_properties(specs, patterns)
        if unmatched:
            for pattern in unmatched:
                print(f"Error: No property description contains '{pattern}'")
            return False

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
  minigun -t 30 --modules lists strings    # Load and run only these modules
  minigun -t 30 -k "reverse"               # Run properties matching "reverse"
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
        action="extend",
        help="Test modules to load and run, by name without .py; may be "
        "repeated",
    )
    parser.add_argument(
        "--select",
        "-k",
        nargs="+",
        action="extend",
        metavar="PATTERN",
        help="Run only the properties whose descriptions contain one of "
        "these substrings; with --seed, a selected property draws the "
        "same values as in the full run; may be repeated",
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
        modules=None
        if args.modules is None
        else list(dict.fromkeys(args.modules)),
        output=args.output,
        seed=args.seed,
        patterns=args.select,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
