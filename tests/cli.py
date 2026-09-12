"""Properties of test discovery and the command line."""

import contextlib
import io
import sys
from pathlib import Path

import minigun.cli as cli
import minigun.fixture as f
import minigun.generate as g
from minigun import check
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


@context(g.bounded_lists(0, 3, g.one_of(["syntax_error", "no_spec"])))
@prop("broken modules fail the run before any test executes")
def _broken(kinds: list[str]) -> bool:
    directory = _write(kinds)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        success = cli.run_tests(
            0.2, test_dir=directory, output=OutputMode.QUIET
        )
    text = buffer.getvalue()
    if "syntax_error" in kinds:
        return not success and "failed to load" in text and "Tests:" not in text
    return not success and "No test modules found" in text


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


spec = conj(_discovery, _missing_dir, _run_tests, _broken, _main_flags, _list)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
