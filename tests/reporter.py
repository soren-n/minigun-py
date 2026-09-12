"""Properties of the reporters, fed synthetic outcomes."""

import contextlib
import io
import json

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


def _outcome(
    index: int, holds: bool, attempts: int, failing_value: int
) -> Outcome:
    example = (
        None
        if holds
        else s.CounterExample(
            {"x": failing_value, "name": f"v{index}"}, attempts - 1
        )
    )
    return Outcome(
        desc=f"property {index}",
        negated=False,
        holds=holds,
        duration=0.001 * attempts,
        attempts=attempts,
        discards=0,
        counter_example=example,
        error=None,
    )


def _module(
    index: int, verdicts: list[tuple[bool, int, int]]
) -> tuple[str, list[Outcome]]:
    outcomes = [
        _outcome(index * 100 + i, holds, max(1, attempts), value)
        for i, (holds, attempts, value) in enumerate(verdicts)
    ]
    return f"module{index}", outcomes


def _modules() -> g.Generator[list[tuple[str, list[Outcome]]]]:
    verdict = g.tuples(g.bools(), g.int_range(1, 50), g.ints())
    module = g.map(_module, g.small_nats(), g.bounded_lists(0, 5, verdict))
    return g.bounded_lists(0, 4, module)


def _feed(
    reporter: r.Reporter, modules: list[tuple[str, list[Outcome]]]
) -> str:
    plans = [
        b.PropertyPlan(o.desc, c.finite(100), 10)
        for _, outcomes in modules
        for o in outcomes
    ]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        reporter.start_run([name for name, _ in modules], plans)
        for name, outcomes in modules:
            reporter.start_module(name)
            for outcome in outcomes:
                reporter.start_property(outcome.desc)
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
@prop("the quiet reporter prints one verdict line and one line per failure")
def _quiet(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.QuietReporter(seed, 10.0), modules)
    failures = _failures(modules)
    lines = text.splitlines()
    verdict = "Tests: PASS" if not failures else "Tests: FAIL"
    fail_lines = [line for line in lines if line.startswith("FAIL [")]
    return (
        lines[0] == verdict
        and len(fail_lines) == len(failures)
        and ((f"--seed {seed}" in text) == bool(failures))
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
            (test["counter_example"] is None) == test["success"]
            for test in tests
        )
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
    return text.count("FAIL: ") == len(failures) and text.rstrip().endswith(
        f"seed={seed})"
    )


@context(_modules())
@prop("the rich reporter renders every module and the overall verdict")
def _rich(modules: list[tuple[str, list[Outcome]]], seed: int) -> bool:
    text = _feed(r.RichReporter(seed, 10.0), modules)
    failures = _failures(modules)
    verdict = "tests failed" if failures else "tests passed"
    return all(name in text for name, _ in modules) and verdict in text


@prop("formatted arguments have one entry per argument")
def _format(args: dict[str, int]) -> bool:
    text = r.format_arguments(args)
    if not args:
        return text == ""
    return all(f"{name} = {value}" in text for name, value in args.items())


spec = conj(_quiet, _json, _plain, _rich, _format)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
