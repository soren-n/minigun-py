"""Properties of the reporters, fed synthetic outcomes."""

import ast
import collections
import contextlib
import dataclasses
import io
import json
import shlex
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
        # Every third outcome labels its attempts, one label required.
        labels={f"tag{index}": attempts} if value % 3 == 0 else {},
        coverage={f"tag{index}": 0.5} if value % 3 == 0 else {},
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
        and "LABELS" not in text
        and "tag" not in text
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
        and [(test["labels"], test["coverage"]) for test in tests]
        == [(o.labels, o.coverage) for _, outcomes in modules for o in outcomes]
        and all(
            test["counter_example"]["arguments"]["x"]
            == repr(int(test["counter_example"]["arguments"]["x"]))
            for test in tests
            if test["counter_example"] is not None
        )
    )


@context(_modules())
@prop("the plain reporter prints only failures, labels and the seed")
def _plain(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.PlainReporter(seed, None), modules)
    failures = _failures(modules)
    labelled = [o for _, outcomes in modules for o in outcomes if o.labels]
    if not failures:
        return text == "".join(
            f"LABELS: {o.desc} ({o.evaluations} tested)\n"
            + textwrap.indent(r.format_distribution(o) or "", "  ")
            + "\n"
            for o in labelled
        )
    return (
        text.count("FAIL: ") == len(failures)
        and text.count("LABELS: ") == len(labelled)
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


@context(_modules())
@prop("the rich reporter flags passing properties short of their limit")
def _rich_short(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    # _feed plans every property with an attempt limit of ten.
    short = [
        o
        for _, outcomes in modules
        for o in outcomes
        if o.holds and o.attempts < 10
    ]
    text = _feed(r.RichReporter(seed, 10.0), modules)
    total = sum(len(outcomes) for _, outcomes in modules)
    summary = (
        f"{len(short)} of {total} properties stopped short of their "
        "attempt limit"
    )
    return (
        all(f"({o.attempts}/10 attempts" in text for o in short)
        and text.count("/10 attempts") == len(short)
        and (summary in text) == bool(short)
    )


@prop("the rich summary reports time usage only under a budget")
def _rich_budget(budgeted: bool, seed: int) -> bool:
    budget = 10.0 if budgeted else None
    text = _feed(r.RichReporter(seed, budget), [])
    return ("Run time" in text) == budgeted


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


###############################################################################
# Label distributions
###############################################################################


def _labelled() -> g.Generator[Outcome]:
    def _build(
        evaluations: int, labels: dict[str, int], covered: list[str]
    ) -> Outcome:
        counts = {
            name: count % (evaluations + 1) for name, count in labels.items()
        }
        return Outcome(
            desc="labelled",
            negated=False,
            holds=True,
            duration=0.01,
            attempts=evaluations,
            discards=0,
            counter_example=None,
            error=None,
            labels={n: c for n, c in counts.items() if c},
            coverage=dict.fromkeys(covered, 0.25),
        )

    return g.map(
        _build,
        g.int_range(1, 1000),
        g.bounded_dicts(0, 5, g.words(), g.int_range(1, 1000)),
        g.bounded_lists(0, 3, g.words()),
    )


@context(_labelled())
@prop("a distribution lists every label most frequent first, with requirements")
def _distribution(outcome: Outcome) -> bool:
    text = r.format_distribution(outcome)
    names = set(outcome.labels) | set(outcome.coverage)
    if not names:
        return text is None
    if text is None:
        return False
    lines = text.splitlines()
    counts = [int(line.rsplit("(", 1)[1].split(")")[0]) for line in lines]
    return (
        len(lines) == len(names)
        and counts == sorted(counts, reverse=True)
        and sum("required 25%" in line for line in lines)
        == len(outcome.coverage)
    )


@context(_labelled())
@prop("plain, rich and JSON reporters show a property's labels")
def _distribution_reported(outcome: Outcome, seed: int) -> bool:
    modules = [("labelled", [outcome])]
    distribution = r.format_distribution(outcome)
    plain = _feed(r.PlainReporter(seed, None), modules)
    rich = _feed(r.RichReporter(seed, None), modules)
    test = json.loads(_feed(r.JSONReporter(seed, None), modules))["modules"][0][
        "tests"
    ][0]
    if distribution is None:
        shown = plain == ""
    else:
        lines = distribution.splitlines()
        shown = (
            plain.startswith("LABELS: labelled")
            and all(line in plain for line in lines)
            and all(line.strip() in rich for line in lines)
        )
    return (
        shown
        and test["labels"] == outcome.labels
        and test["coverage"] == outcome.coverage
    )


###############################################################################
# Shrink paths, replays and recording
###############################################################################


def _paths() -> g.Generator[tuple[dict[str, int], ...]]:
    # Few values, so consecutive steps often leave an argument unchanged.
    args = g.map(
        lambda a, b: {"a": a, "b": b}, g.int_range(0, 3), g.int_range(0, 3)
    )
    return g.map(tuple, g.bounded_lists(0, 6, args))


@context(_paths())
@prop("a shrink path lists the arguments found, then each step's changes")
def _path(path: tuple[dict[str, int], ...]) -> bool:
    text = r.describe_path(
        s.CounterExample(path[-1] if path else {}, 0, path=path)
    )
    if len(path) < 2:
        return text is None
    if text is None:
        return False
    lines = text.splitlines()
    steps = len(path) - 1
    expected = [
        f"Shrink path, {steps} step{'s' if steps != 1 else ''}:",
        "found:",
        *(f"  {name} = {value}" for name, value in path[0].items()),
    ]
    for step, (before, after) in enumerate(
        zip(path, path[1:], strict=False), 1
    ):
        changed = [name for name in after if after[name] != before[name]]
        expected.append(f"step {step}:")
        expected.extend(
            [f"  {name} = {after[name]}" for name in changed]
            or ["  (the arguments print as before)"]
        )
    return lines == expected


def _failing(seed: int | None) -> Outcome:
    path = ({"x": 9}, {"x": 4}, {"x": 2})
    return Outcome(
        desc="falsified",
        negated=False,
        holds=False,
        duration=0.01,
        attempts=3,
        discards=0,
        counter_example=s.CounterExample(
            {"x": 2}, 2, shrinks=2, path=path, seed=seed
        ),
        error=None,
        replayed=0 if seed is None else 1,
    )


@context(g.bools(), g.optional(g.ints()))
@prop("every reporter shows a shrink path exactly when verbose")
def _verbose(verbose: bool, seed: int | None) -> bool:
    modules = [("m", [_failing(seed)])]
    texts = [
        _feed(reporter, modules)
        for reporter in (
            r.PlainReporter(0, None, verbose),
            r.QuietReporter(0, 1.0, verbose),
            r.RichReporter(0, 1.0, verbose),
        )
    ]
    data = json.loads(_feed(r.JSONReporter(0, 1.0, verbose), modules))
    example = data["modules"][0]["tests"][0]["counter_example"]
    return (
        all(("Shrink path, 2 steps" in text) == verbose for text in texts)
        and ("path" in example) == verbose
        and (
            not verbose
            or example["path"] == [{"x": "9"}, {"x": "4"}, {"x": "2"}]
        )
        and example["seed"] == seed
    )


@context(g.optional(g.int_range(-(10**6), 10**6)), g.int_range(0, 100))
@prop("a replayed counterexample says which recorded draw it replays")
def _replayed(seed: int | None, attempt: int) -> bool:
    example = s.CounterExample({"x": 1}, attempt, seed=seed)
    outcome = dataclasses.replace(_failing(seed), counter_example=example)
    failure = r.describe_failure(outcome)
    found = r.describe_found("falsified", example)
    note = f"replays a recorded failure: attempt {attempt + 1} of seed {seed}"
    replaying = f"replaying attempt {attempt + 1} of seed {seed}"
    if seed is None:
        return "replay" not in failure and f"on attempt {attempt + 1}" in found
    return note in failure and replaying in found


@context(_modules(), g.int_range(0, 999))
@prop("run reporters give the flags that reproduce each failure alone")
def _reproduce(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    quiet = _feed(r.QuietReporter(seed, 1.0), modules)
    rich = _feed(r.RichReporter(seed, 1.0), modules)
    data = json.loads(_feed(r.JSONReporter(seed, 1.0), modules))
    # Modules may share names and descriptions, so lines are counted.
    expected: collections.Counter[str] = collections.Counter()
    for (name, outcomes), shown in zip(modules, data["modules"], strict=True):
        for outcome, test in zip(outcomes, shown["tests"], strict=True):
            flags = f"--seed {seed} --modules={name} --select='{outcome.desc}'"
            if test["reproduce"] != (None if outcome.holds else flags):
                return False
            if not outcome.holds:
                expected[f"  Reproduce with: {flags}"] += 1
    shown_lines = collections.Counter(
        line
        for line in quiet.splitlines()
        if line.startswith("  Reproduce with: ")
    )
    if shown_lines != expected:
        return False
    failed = len(_failures(modules))
    return rich.count("Reproduce with: --seed") == failed + (failed > 0)


@context(g.strings(), g.words())
@prop("reproduce flags quote a description for a POSIX shell")
def _reproduce_quoting(desc: str, module: str, seed: int) -> bool:
    flags = r.reproduce_flags(seed, module, desc)
    expected = [
        "--seed",
        str(seed),
        f"--modules={module}",
        f"--select={desc}",
    ]
    return shlex.split(flags) == expected


@prop("every reporter says where a new counterexample was recorded")
def _recorded(seed: int) -> bool:
    modules = [("m", [_failing(None)])]
    path = f"regressions/m{seed}.json"

    def _text(reporter: r.Reporter) -> str:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            reporter.start_run(["m"], [])
            reporter.start_module("m")
            reporter.start_property("falsified")
            reporter.end_property(modules[0][1][0])
            reporter.recorded("falsified", path)
            reporter.end_module()
            reporter.finish()
        return buffer.getvalue()

    plain = _text(r.PlainReporter(seed, None))
    quiet = _text(r.QuietReporter(seed, 1.0))
    rich = _text(r.RichReporter(seed, 1.0))
    data = json.loads(_text(r.JSONReporter(seed, 1.0)))
    return (
        f"RECORDED: falsified in {path}" in plain
        and f"  Recorded in {path}" in quiet
        and f"Recorded in {path}" in rich
        and data["modules"][0]["tests"][0]["recorded"] == path
    )


spec = conj(
    _quiet,
    _json,
    _plain,
    _rich,
    _rich_truncates,
    _rich_short,
    _rich_budget,
    _announced,
    _announced_stdout,
    _not_minimal,
    _outside_module,
    _format,
    _describe,
    _format_multiline,
    _distribution,
    _distribution_reported,
    _path,
    _verbose,
    _replayed,
    _recorded,
    _reproduce,
    _reproduce_quoting,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
