"""Properties of the reporters, fed synthetic outcomes."""

import ast
import contextlib
import io
import json
import textwrap
from typing import Any

import minigun.budget as b
import minigun.cardinality as c
import minigun.generate as g
import minigun.reporter as r
import minigun.search as s
from minigun import check
from minigun.specify import Outcome, conj, context, prop

###############################################################################
# Synthetic outcomes
###############################################################################


#: How a synthetic outcome ends: it holds, it has a counterexample found
#: by a False result or by an exception, or it failed without one (too
#: many discards, or a negation that found nothing).
_KINDS = ["holds", "false", "exception", "error"]


def _outcome(index: int, kind: str, attempts: int, value: int) -> Outcome:
    # A list long enough to be rendered over several lines when it is.
    args = {"x": value, "name": f"v{index}", "xs": list(range(abs(value) % 40))}
    example = None
    if kind == "false":
        example = s.CounterExample(args, attempts - 1)
    elif kind == "exception":
        example = s.CounterExample(args, attempts - 1, ValueError(f"e{index}"))
    return Outcome(
        desc=f"property {index}",
        negated=False,
        holds=kind == "holds",
        duration=0.001 * attempts,
        attempts=attempts,
        discards=attempts if kind == "error" else 0,
        counter_example=example,
        error=f"not tested {index}" if kind == "error" else None,
    )


def _module(
    index: int, verdicts: list[tuple[str, int, int]]
) -> tuple[str, list[Outcome]]:
    outcomes = [
        _outcome(index * 100 + i, kind, max(1, attempts), value)
        for i, (kind, attempts, value) in enumerate(verdicts)
    ]
    return f"module{index}", outcomes


def _modules() -> g.Generator[list[tuple[str, list[Outcome]]]]:
    verdict = g.tuples(g.one_of(_KINDS), g.int_range(1, 50), g.ints())
    module = g.map(_module, g.small_nats(), g.bounded_lists(0, 5, verdict))
    return g.bounded_lists(0, 4, module)


def _feed(
    reporter: r.Reporter,
    modules: list[tuple[str, list[Outcome]]],
    errors: io.StringIO | None = None,
) -> str:
    """Drive a reporter through the modules and return what it printed.

    With ``errors``, each counterexample is also announced as found and
    stderr is captured there.
    """
    plans = [
        b.PropertyPlan(o.desc, c.finite(100), 10)
        for _, outcomes in modules
        for o in outcomes
    ]
    buffer = io.StringIO()
    with (
        contextlib.redirect_stdout(buffer),
        contextlib.redirect_stderr(errors or io.StringIO()),
    ):
        reporter.start_run([name for name, _ in modules], plans)
        for name, outcomes in modules:
            reporter.start_module(name)
            for outcome in outcomes:
                reporter.start_property(outcome.desc)
                example = outcome.counter_example
                if errors is not None and example is not None:
                    reporter.found_counter_example(outcome.desc, example)
                reporter.end_property(outcome)
            reporter.end_module()
        reporter.finish()
    return buffer.getvalue()


def _failures(modules: list[tuple[str, list[Outcome]]]) -> list[Outcome]:
    return [o for _, outcomes in modules for o in outcomes if not o.holds]


###############################################################################
# Properties
###############################################################################


@context(_modules())
@prop("the quiet reporter prints a verdict line and explains each failure")
def _quiet(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.QuietReporter(seed, 10.0), modules)
    failures = _failures(modules)
    lines = text.splitlines()
    verdict = "Tests: PASS" if not failures else "Tests: FAIL"
    fail_lines = [line for line in lines if line.startswith("FAIL [")]
    return (
        lines[0] == verdict
        and len(fail_lines) == len(failures)
        and all(
            textwrap.indent(r.describe_failure(o), "  ") in text
            for o in failures
        )
        and ((f"--seed {seed}" in text) == bool(failures))
    )


def _json_failure(test: dict[str, Any]) -> bool:
    """Whether a JSON test entry reports its synthetic failure verbatim."""
    index = test["name"].split()[-1]
    example = test["counter_example"]
    return test["error"] in (None, f"not tested {index}") and (
        example is None
        or example["exception"] in (None, f"ValueError: e{index}")
    )


@context(_modules())
@prop("the JSON reporter emits parseable output whose counts match")
def _json(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.JSONReporter(seed, 10.0), modules)
    data = json.loads(text)
    total = sum(len(outcomes) for _, outcomes in modules)
    failures = _failures(modules)
    tests = [test for module in data["modules"] for test in module["tests"]]
    return (
        data["config"]["seed"] == seed
        and data["summary"]["total_tests"] == total
        and data["summary"]["total_failed"] == len(failures)
        and data["summary"]["overall_success"] == (not failures)
        and [module["name"] for module in data["modules"]]
        == [name for name, _ in modules]
        and all(
            (test["counter_example"] is None)
            == (test["success"] or test["error"] is not None)
            for test in tests
        )
        and all(_json_failure(test) for test in tests)
        and all(
            test["counter_example"]["arguments"]["x"]
            == repr(int(test["counter_example"]["arguments"]["x"]))
            for test in tests
            if test["counter_example"] is not None
        )
    )


@context(_modules())
@prop("the plain reporter prints only failures and the seed")
def _plain(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.PlainReporter(seed, None), modules)
    failures = _failures(modules)
    if not failures:
        return text == ""
    return (
        text.count("FAIL: ") == len(failures)
        and all(r.describe_failure(o) in text for o in failures)
        and text.rstrip().endswith(f"seed={seed})")
    )


@context(_modules())
@prop("the rich reporter renders every module and the overall verdict")
def _rich(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.RichReporter(seed, 10.0), modules)
    failures = _failures(modules)
    verdict = "tests failed" if failures else "tests passed"
    return all(name in text for name, _ in modules) and verdict in text


@context(g.int_range(1, 80))
@prop("the rich reporter shortens long descriptions in its plan table")
def _rich_truncates(length: int, seed: int) -> bool:
    desc = "d" * length
    outcome = Outcome(desc, False, True, 0.0, 1, 0, None, None)
    text = _feed(r.RichReporter(seed, 10.0), [("m", [outcome])])
    # The plan table is the only boxed line naming the property; the
    # progress line below it always shows the whole description.
    rows = [line for line in text.splitlines() if line.startswith("│ d")]
    shown = desc if length <= 40 else desc[:37] + "..."
    return len(rows) == 1 and rows[0].startswith(f"│ {shown} ")


@prop("the rich summary reports time usage only under a budget")
def _rich_budget(budgeted: bool, seed: int) -> bool:
    budget = 10.0 if budgeted else None
    text = _feed(r.RichReporter(seed, budget), [])
    return ("Test time" in text) == budgeted


@context(_modules())
@prop("quiet and JSON reporters announce counterexamples on stderr only")
def _announced(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    examples = [
        (o.desc, o.counter_example)
        for _, outcomes in modules
        for o in outcomes
        if o.counter_example is not None
    ]
    for make in (r.QuietReporter, r.JSONReporter):
        errors = io.StringIO()
        announced = _feed(make(seed, 10.0), modules, errors)
        # The final report does not depend on what was announced, except
        # for the JSON timestamp and durations.
        silent = _feed(make(seed, 10.0), modules)
        if make is r.QuietReporter and announced != silent:
            return False
        if make is r.JSONReporter:
            json.loads(announced)
        text = errors.getvalue()
        if text.count("FOUND [") != len(examples):
            return False
        if not all(
            textwrap.indent(r.describe_found(desc, example), "  ") in text
            for desc, example in examples
        ):
            return False
    return True


@context(_modules())
@prop("plain and rich reporters announce counterexamples on stdout")
def _announced_stdout(
    modules: list[tuple[str, list[Outcome]]], seed: int
) -> bool:
    count = sum(
        o.counter_example is not None
        for _, outcomes in modules
        for o in outcomes
    )
    plain_errors, rich_errors = io.StringIO(), io.StringIO()
    plain = _feed(r.PlainReporter(seed, None), modules, plain_errors)
    rich = _feed(r.RichReporter(seed, 10.0), modules, rich_errors)
    return (
        plain.count("FOUND: ") == count
        and rich.count("counter example found on attempt") == count
        and plain_errors.getvalue() == rich_errors.getvalue() == ""
    )


@context(g.int_range(0, 100), g.bools())
@prop("a failure says when shrinking stopped short of a minimum")
def _not_minimal(shrinks: int, minimal: bool) -> bool:
    for exception in (None, ValueError("e")):
        example = s.CounterExample({"x": 1}, 0, exception, shrinks, minimal)
        outcome = Outcome("p", False, False, 0.0, 1, 0, example, None)
        text = r.describe_failure(outcome)
        stopped = f"stopped at the time budget after {shrinks} steps"
        if (stopped in text) == minimal:
            return False
    return True


@prop("reporting a property outside a module is an error")
def _outside_module(seed: int) -> bool:
    reporter = r.QuietReporter(seed, 1.0)
    outcome = Outcome("p", False, True, 0.0, 1, 0, None, None)
    with contextlib.redirect_stdout(io.StringIO()):
        reporter.start_run([], [])
        try:
            reporter.end_property(outcome)
        except RuntimeError:
            return True
    return False


@prop("formatted arguments have one entry per argument")
def _format(args: dict[str, int]) -> bool:
    text = r.format_arguments(args)
    if not args:
        return text == ""
    return all(f"{name} = {value}" in text for name, value in args.items())


@context(g.one_of(_KINDS), g.ints())
@prop("failure descriptions say how the property failed")
def _describe(kind: str, value: int) -> bool:
    outcome = _outcome(7, kind, 3, value)
    text = r.describe_failure(outcome)
    match kind:
        case "holds":
            return 'Property "property 7" did not hold' in text
        case "false":
            return "failed with the following counter example" in text
        case "exception":
            return "raised ValueError: e7" in text
        case _:
            return text == "not tested 7"


@context(g.lists(g.ints()))
@prop("formatted values that span lines are indented and read back")
def _format_multiline(xs: list[int]) -> bool:
    text = r.format_arguments({"xs": xs})
    if "\n" not in text:
        return text == f"xs = {xs!r}"
    head, rest = text.split("\n", 1)
    return (
        head == "xs ="
        and all(line.startswith("  ") for line in rest.splitlines())
        and ast.literal_eval(textwrap.dedent(rest)) == xs
    )


spec = conj(
    _quiet,
    _json,
    _plain,
    _rich,
    _rich_truncates,
    _rich_budget,
    _announced,
    _announced_stdout,
    _not_minimal,
    _outside_module,
    _format,
    _describe,
    _format_multiline,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
