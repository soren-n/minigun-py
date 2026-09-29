"""Properties of test discovery and the command line."""

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

import minigun.cli as cli
import minigun.fixture as f
import minigun.generate as g
from minigun import assume, check
from minigun.orchestrator import OutputMode
from minigun.specify import conj, context, prop

_SOURCES: dict[str, str] = {
    "valid": (
        "from minigun.specify import prop, conj\n"
        "@prop('holds')\n"
        "def _p(x: int) -> bool:\n"
        "    return True\n"
        "spec = conj(_p)\n"
    ),
    "syntax_error": "def (\n",
    "import_error": "import no_such_module_anywhere\n",
    "retired": "def test():\n    return True\n",
    "no_spec": "value = 1\n",
    "wrong_spec": "spec = 42\n",
    "forward_ref": (
        "from dataclasses import dataclass\n"
        "from minigun.specify import prop, conj\n"
        "@dataclass(frozen=True)\n"
        "class Node:\n"
        "    child: 'Node | None'\n"
        "@prop('holds')\n"
        "def _p(x: int) -> bool:\n"
        "    return True\n"
        "spec = conj(_p)\n"
    ),
}

_VALID = {"valid", "forward_ref"}
_BROKEN = {"syntax_error", "import_error", "retired", "wrong_spec"}


def _write(kinds: list[str]) -> Path:
    directory = f.temporary_path()
    for index, kind in enumerate(kinds):
        (directory / f"m{index}_{kind}.py").write_text(_SOURCES[kind])
    (directory / "_private.py").write_text("def (\n")
    return directory


@context(g.bounded_lists(0, 6, g.one_of(list(_SOURCES))))
@prop("discovery classifies every module correctly")
def _discovery(kinds: list[str]) -> bool:
    specs, broken = cli.discover_test_modules(_write(kinds))
    expected_specs = {f"m{i}_{k}" for i, k in enumerate(kinds) if k in _VALID}
    expected_broken = {f"m{i}_{k}" for i, k in enumerate(kinds) if k in _BROKEN}
    return set(specs) == expected_specs and set(broken) == expected_broken


@prop("a missing test directory is an error")
def _missing_dir(seed: int) -> bool:
    missing = f.ROOT / "no-such-tests"
    try:
        cli.discover_test_modules(missing)
    except NotADirectoryError:
        pass
    else:
        return False
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(0.2, test_dir=missing, output=OutputMode.QUIET)
    return not success and "does not exist" in buffer.getvalue()


@context(g.bounded_lists(1, 3, g.constant("valid")))
@prop("run_tests runs selected modules and rejects unknown names")
def _run_tests(kinds: list[str], seed: int) -> bool:
    directory = _write(kinds)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(
            0.2,
            test_dir=directory,
            modules=["m0_valid"],
            output=OutputMode.QUIET,
            seed=seed,
        )
        unknown = cli.run_tests(
            0.2,
            test_dir=directory,
            modules=["nope"],
            output=OutputMode.QUIET,
            seed=seed,
        )
    text = buffer.getvalue()
    return (
        success
        and not unknown
        and "Tests: PASS" in text
        and "'nope' not found" in text
    )


def _run_quietly(directory: Path) -> tuple[bool, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(
            0.2, test_dir=directory, output=OutputMode.QUIET
        )
    return success, buffer.getvalue()


# Each case is forced on every attempt rather than left to the draw: the
# domains are small, and so is their share of a budgeted run.
@context(g.bounded_lists(0, 3, g.one_of(list(_SOURCES))))
@prop("broken modules fail the run before any test executes")
def _broken(kinds: list[str]) -> bool:
    success, text = _run_quietly(_write([*kinds, "syntax_error"]))
    return not success and "failed to load" in text and "Tests:" not in text


@context(g.bounded_lists(0, 3, g.constant("no_spec")))
@prop("a directory without specifications is reported as empty")
def _no_specs(kinds: list[str]) -> bool:
    success, text = _run_quietly(_write(kinds))
    return not success and "No test modules found" in text


@prop("a directory runs again in the same process")
def _rediscovered(seed: int) -> bool:
    directory = _write(["valid"])
    return _run_quietly(directory)[0] and _run_quietly(directory)[0]


@context(g.bounded_lists(0, 3, g.constant("valid")), g.words())
@prop("loading a module the directory does not hold is an error")
def _unknown_name(kinds: list[str], name: str) -> bool:
    directory = _write(kinds)
    assume(not (directory / f"{name}.py").exists())
    try:
        cli.discover_test_modules(directory, [name])
    except ValueError:
        return True
    return False


@context(g.int_range(2, 4))
@prop("a description shared by two modules is an error before anything runs")
def _duplicates(count: int, seed: int) -> bool:
    # Every "valid" module defines a property described "holds".
    directory = _write(["valid"] * count)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(
            0.2, test_dir=directory, output=OutputMode.QUIET, seed=seed
        )
    text = buffer.getvalue()
    return (
        not success
        and 'Duplicate property description "holds"' in text
        and "Tests:" not in text
    )


def _main(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    saved = sys.argv
    sys.argv = ["minigun", *argv]
    try:
        with contextlib.redirect_stdout(buffer):
            cli.main()
    except SystemExit as exit_:
        code = exit_.code if isinstance(exit_.code, int) else 1
    else:
        code = 0
    finally:
        sys.argv = saved
    return code, buffer.getvalue()


@prop("main reports its version and requires a positive budget")
def _main_flags(budget: int) -> bool:
    code, text = _main(["--version"])
    if code != 0 or "Minigun" not in text:
        return False
    code, text = _main([])
    if code != 1 or "--time-budget is required" not in text:
        return False
    if budget <= 0:
        code, text = _main(["-t", str(budget)])
        return code == 1 and "must be positive" in text
    return True


@context(g.bounded_lists(0, 3, g.one_of(list(_SOURCES))))
@prop("listing modules exits non-zero exactly when a module is broken")
def _list(kinds: list[str]) -> bool:
    directory = _write(kinds)
    code, text = _main(["--list-modules", "--test-dir", str(directory)])
    has_broken = any(kind in _BROKEN for kind in kinds)
    has_valid = any(kind in _VALID for kind in kinds)
    return (
        code == (1 if has_broken else 0)
        and ("Broken test modules" in text) == has_broken
        and ("Discovered test modules" in text) == has_valid
    )


@context(g.bounded_lists(1, 5, g.one_of(list(_SOURCES))))
@prop("selected modules load alone, whatever else the directory holds")
def _selected_alone(kinds: list[str], seed: int) -> bool:
    assume(any(kind in _VALID for kind in kinds))
    directory = _write(kinds)
    # One module: every valid source describes its property "holds", and
    # descriptions must be unique across a run.
    selected = [f"m{i}_{k}" for i, k in enumerate(kinds) if k in _VALID][:1]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(
            0.2,
            test_dir=directory,
            modules=selected,
            output=OutputMode.QUIET,
            seed=seed,
        )
    return success and "failed to load" not in buffer.getvalue()


@prop("selecting a module without a specification is an error")
def _selected_no_spec(seed: int) -> bool:
    directory = _write(["valid", "no_spec"])
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(
            0.2,
            test_dir=directory,
            modules=["m0_valid", "m1_no_spec"],
            output=OutputMode.QUIET,
            seed=seed,
        )
    text = buffer.getvalue()
    return not success and "'m1_no_spec' exports no" in text


def _named_module(desc: str, threshold: int) -> str:
    return (
        "import minigun.generate as g\n"
        "from minigun.specify import context, prop\n"
        "@context(g.int_range(0, 100))\n"
        f"@prop({desc!r})\n"
        "def _p(x: int) -> bool:\n"
        f"    return x < {threshold}\n"
        "spec = _p\n"
    )


def _json_main(argv: list[str]) -> tuple[int, dict[str, Any] | None]:
    code, text = _main(["-o", "json", *argv])
    try:
        return code, json.loads(text)
    except json.JSONDecodeError:
        return code, None


def _tests(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if data is None:
        return {}
    return {t["name"]: t for m in data["modules"] for t in m["tests"]}


@prop("a repeated --modules flag runs every module it names, once")
def _repeated_modules(seed: int) -> bool:
    directory = f.temporary_path()
    (directory / "first.py").write_text(_named_module("first holds", 101))
    (directory / "second.py").write_text(_named_module("second holds", 101))
    (directory / "third.py").write_text(_named_module("third holds", 101))
    code, data = _json_main(
        ["-t", "0.2", "-d", str(directory), "-s", str(seed)]
        + ["-m", "first", "-m", "second", "first"]
    )
    return (
        code == 0
        and data is not None
        and data["config"]["modules"] == ["first", "second"]
    )


@prop("--select runs matching properties with their full-run counterexample")
def _select(seed: int) -> bool:
    directory = f.temporary_path()
    (directory / "a.py").write_text(_named_module("alpha holds", 101))
    (directory / "b.py").write_text(_named_module("beta fails", 50))
    common = ["-t", "0.2", "-d", str(directory), "-s", str(seed)]
    full_code, full = _json_main(common)
    alpha_code, alpha = _json_main([*common, "-k", "alpha"])
    beta_code, beta = _json_main([*common, "-k", "fails", "-k", "beta"])
    none_code, none = _main([*common, "-k", "alpha", "gamma"])
    return (
        full_code == 1
        and alpha_code == 0
        and list(_tests(alpha)) == ["alpha holds"]
        and beta_code == 1
        and list(_tests(beta)) == ["beta fails"]
        and _tests(beta)["beta fails"]["counter_example"]
        == _tests(full)["beta fails"]["counter_example"]
        and none_code == 1
        and "contains 'gamma'" in none
        and "'alpha'" not in none
    )


def _relative_module(expected: int) -> str:
    return (
        "from minigun.specify import prop\n"
        "from ._helpers import VALUE\n"
        "from .support.values import OTHER\n"
        "@prop('relative imports resolve beside the module')\n"
        "def _p(x: int) -> bool:\n"
        f"    return VALUE == {expected} and OTHER == {expected + 1}\n"
        "spec = _p\n"
    )


@context(g.ints(), g.ints())
@prop(
    "test modules import helpers beside them relatively, per directory",
    attempts=30,
)
def _relative(first: int, second: int, seed: int) -> bool:
    # Two directories with helpers of the same names but different values,
    # discovered in one process: each module must see its own.
    directories = []
    for value in (first, second):
        directory = f.temporary_path()
        (directory / "_helpers.py").write_text(f"VALUE = {value}\n")
        (directory / "support").mkdir()
        (directory / "support" / "values.py").write_text(
            f"OTHER = {value + 1}\n"
        )
        (directory / "relative.py").write_text(_relative_module(value))
        directories.append(directory)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        results = [
            cli.run_tests(
                0.2, test_dir=directory, output=OutputMode.QUIET, seed=seed
            )
            for directory in directories
        ]
    return all(results)


@prop("listing modules reports a missing or empty test directory")
def _list_edges(seed: int) -> bool:
    missing = f.ROOT / "no-such-tests"
    missing_code, missing_text = _main(
        ["--list-modules", "--test-dir", str(missing)]
    )
    empty = f.temporary_path()
    empty_code, empty_text = _main(["--list-modules", "--test-dir", str(empty)])
    return (
        missing_code == 1
        and "does not exist" in missing_text
        and empty_code == 0
        and "No test modules found" in empty_text
    )


@prop("python -m minigun runs the command line")
def _module_entry(seed: int) -> bool:
    import runpy

    buffer = io.StringIO()
    saved = sys.argv
    sys.argv = ["minigun", "--version"]
    try:
        with contextlib.redirect_stdout(buffer):
            runpy.run_module("minigun", run_name="__main__")
    except SystemExit as exit_:
        code = exit_.code
    else:
        code = 0
    finally:
        sys.argv = saved
    return code in (0, None) and "Minigun" in buffer.getvalue()


spec = conj(
    _discovery,
    _missing_dir,
    _run_tests,
    _duplicates,
    _selected_alone,
    _selected_no_spec,
    _repeated_modules,
    _select,
    _relative,
    _broken,
    _no_specs,
    _rediscovered,
    _unknown_name,
    _main_flags,
    _list,
    _list_edges,
    _module_entry,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
