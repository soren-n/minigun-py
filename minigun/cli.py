"""
Command-line interface

Discovers test modules in a directory and runs them under a time budget.

Test modules are imported as submodules of a package registered for their
directory, so they can import helper modules beside them relatively, e.g.
``from ._helpers import model`` or ``from .support.models import Model``.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import os
import secrets
import sys
import textwrap
import types
from pathlib import Path
from typing import Any

from minigun import __version__, canonical
from minigun.orchestrator import OutputMode, RunConfig, TestModule, run
from minigun.regressions import RegressionsError
from minigun.reporter import format_arguments
from minigun.specify import (
    Prop,
    Spec,
    SpecificationError,
    collect,
    first_arguments,
    is_spec,
    resolve_all,
    select,
)

__all__ = [
    "find_test_modules",
    "discover_test_modules",
    "load_test_module",
    "select_properties",
    "show_examples",
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


def load_test_module(test_dir: Path, name: str) -> Spec:
    """Load one test module's specification, as a worker process of a
    parallel run does.

    :raises SpecificationError: When the module fails to load or exports
        no specification.
    """
    specs, broken = discover_test_modules(test_dir, [name])
    if name in broken:
        raise SpecificationError(
            f"Test module '{name}' failed to load: {broken[name]}"
        )
    if name not in specs:
        raise SpecificationError(f"Module '{name}' exports no 'spec: Spec'")
    return specs[name]


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


def _discover(
    test_dir: Path, modules: list[str] | None, patterns: list[str] | None
) -> dict[str, Spec] | None:
    """The whole specifications of the selected modules by name, checked
    for the errors a run reports before it starts.

    :return: The specifications, or None when an error was printed:
        a missing test directory, broken modules, unknown module names,
        selected modules without a specification, no modules, or
        patterns matching no property.
    """
    try:
        candidates = find_test_modules(test_dir)
    except NotADirectoryError as error:
        print(f"Error: {error}")
        return None

    if modules:
        unknown = [name for name in modules if name not in candidates]
        if unknown:
            for name in unknown:
                print(f"Error: Module '{name}' not found.")
            print(f"Available modules: {', '.join(sorted(candidates))}")
            return None
    specs, broken = discover_test_modules(test_dir, modules or None)

    if broken:
        for name, reason in sorted(broken.items()):
            print(f"Error: Test module '{name}' failed to load: {reason}")
        return None
    if modules:
        missing = [name for name in modules if name not in specs]
        if missing:
            for name in missing:
                print(f"Error: Module '{name}' exports no 'spec: Spec'")
            return None
        specs = {name: specs[name] for name in modules}
    if not specs:
        print(f"No test modules found in {test_dir}")
        print("Tip: Test modules export a module-level 'spec: Spec'")
        return None
    if patterns:
        _, unmatched = select_properties(specs, patterns)
        if unmatched:
            for pattern in unmatched:
                print(f"Error: No property description contains '{pattern}'")
            return None

    return specs


def show_examples(
    n: int,
    test_dir: Path = Path("tests"),
    modules: list[str] | None = None,
    output: OutputMode = OutputMode.RICH,
    seed: int | None = None,
    patterns: list[str] | None = None,
) -> bool:
    """Print the arguments of the first ``n`` attempts of each selected
    property in a run with the seed, without running any law.

    The arguments are those a run with the same seed tests the property
    with (``specify.first_arguments``), so ``--examples`` shows what
    ``--seed`` would test. Text is printed for the rich and quiet output
    modes, a JSON document for the JSON mode.

    :return: Whether every selected property's arguments were drawn.
        Errors a run would report before starting, and generators that
        discard nearly every draw, are reported and count as failure.
    """
    specs = _discover(test_dir, modules, patterns)
    if specs is None:
        return False
    seed_value = seed if seed is not None else secrets.randbits(64)
    shown: list[dict[str, Any]] = []
    try:
        if patterns:
            specs, _ = select_properties(specs, patterns)
        for name, spec in specs.items():
            for resolved in resolve_all(spec):
                shown.append(
                    {
                        "module": name,
                        "name": resolved.prop.desc,
                        "examples": first_arguments(resolved, seed_value, n),
                    }
                )
    except (SpecificationError, ValueError) as error:
        print(f"Error: {error}")
        return False
    if output is OutputMode.JSON:
        document = {
            "seed": seed_value,
            "properties": [
                {
                    **entry,
                    "examples": [
                        {
                            key: canonical.text(value)
                            for key, value in args.items()
                        }
                        for args in entry["examples"]
                    ],
                }
                for entry in shown
            ],
        }
        print(json.dumps(document, indent=2))
        return True
    print(f"Seed: {seed_value}")
    for entry in shown:
        print(f"\n[{entry['module']}] {entry['name']}")
        for index, args in enumerate(entry["examples"], start=1):
            print(f"  Example {index}:")
            print(
                textwrap.indent(
                    format_arguments(args) or "(no arguments)", "    "
                )
            )
    return True


def run_tests(
    time_budget: float,
    test_dir: Path = Path("tests"),
    modules: list[str] | None = None,
    output: OutputMode = OutputMode.RICH,
    seed: int | None = None,
    patterns: list[str] | None = None,
    jobs: int = 1,
    regressions: Path | None = None,
    verbose: bool = False,
) -> bool:
    """Discover and run test modules under a time budget.

    Only the selected modules are imported when ``modules`` is given, and
    only the properties whose descriptions contain one of ``patterns``
    run when it is given. With several ``jobs``, properties are evaluated
    in that many worker processes, each importing the test modules. With
    a ``regressions`` directory, each module's recorded counterexamples
    are replayed first and new ones recorded there; ``verbose`` shows
    each counterexample's shrink path.

    :return: Whether every selected module's specification holds. Broken
        modules, unknown module names, selected modules without a
        specification, patterns matching no property, unresolvable
        specifications, unreadable regressions files and entries naming
        properties a module does not define are reported as errors and
        count as failure.
    """
    specs = _discover(test_dir, modules, patterns)
    if specs is None:
        return False

    # The whole specifications are run, pruned by the selection, so that
    # regressions files are checked against every property.
    config = RunConfig(
        time_budget=time_budget,
        seed=seed,
        output=output,
        jobs=jobs,
        select=tuple(patterns) if patterns else None,
        regressions=regressions,
        verbose=verbose,
    )
    test_modules = [
        TestModule(
            name, spec, functools.partial(load_test_module, test_dir, name)
        )
        for name, spec in specs.items()
    ]
    try:
        return run(config, test_modules)
    except (SpecificationError, RegressionsError) as error:
        print(f"Error: {error}")
        return False


def _jobs(text: str) -> int:
    """Parse ``--jobs``: a positive count, or ``auto`` for one per CPU."""
    if text == "auto":
        return os.cpu_count() or 1
    try:
        jobs = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a positive integer or 'auto', got '{text}'"
        ) from None
    if jobs < 1:
        raise argparse.ArgumentTypeError(
            f"expected a positive integer or 'auto', got '{text}'"
        )
    return jobs


def _count(text: str) -> int:
    """Parse ``--examples``: a positive count."""
    try:
        count = int(text)
    except ValueError:
        count = 0
    if count < 1:
        raise argparse.ArgumentTypeError(
            f"expected a positive integer, got '{text}'"
        )
    return count


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
  minigun -t 30 --jobs auto                # One worker process per CPU
  minigun -t 30 --regressions tests/regressions  # Replay and record failures
  minigun -t 30 --verbose                  # Show each shrink path
  minigun --examples 5 -k "reverse"        # Show what properties are tested with
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
        "--jobs",
        "-j",
        type=_jobs,
        default=1,
        metavar="N",
        help="Evaluate N properties at once in worker processes, or 'auto' "
        "for one per CPU; the time budget is shared out as worker time "
        "(default: 1)",
    )
    parser.add_argument(
        "--regressions",
        "-r",
        type=Path,
        metavar="DIR",
        help="Replay the counterexamples recorded in DIR/<module>.json "
        "before each property's own attempts, and record the "
        "counterexample of every new failure there; keep DIR in version "
        "control",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the shrink path of each counterexample: the arguments "
        "found and those of every shrink step",
    )
    parser.add_argument(
        "--examples",
        "-e",
        type=_count,
        metavar="N",
        help="Print the arguments of the first N attempts of each selected "
        "property in a run with --seed, without running any law, and exit",
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

    if args.examples is not None:
        conflicting = [
            flag
            for flag, given in (
                ("--time-budget", args.time_budget is not None),
                ("--jobs", args.jobs != 1),
                ("--regressions", args.regressions is not None),
                ("--verbose", args.verbose),
            )
            if given
        ]
        if conflicting:
            print(
                "Error: --examples runs no tests and takes no "
                + ", ".join(conflicting)
            )
            sys.exit(1)
        shown = show_examples(
            args.examples,
            test_dir=args.test_dir,
            modules=None
            if args.modules is None
            else list(dict.fromkeys(args.modules)),
            output=args.output,
            seed=args.seed,
            patterns=args.select,
        )
        sys.exit(0 if shown else 1)

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
        jobs=args.jobs,
        regressions=args.regressions,
        verbose=args.verbose,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
