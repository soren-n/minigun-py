"""Properties of the runner entry points."""

import contextlib
import io
import time

import minigun.generate as g
import minigun.orchestrator as o
from minigun import check
from minigun.specify import Spec, SpecificationError, conj, context, prop


def _threshold(desc: str, threshold: int) -> Spec:
    @prop(desc)
    def _below(x: int) -> bool:
        return x < threshold

    return _below


def _quiet_run(
    config: o.RunConfig,
    modules: list[o.TestModule],
    errors: io.StringIO | None = None,
) -> tuple[bool, str]:
    buffer = io.StringIO()
    with (
        contextlib.redirect_stdout(buffer),
        contextlib.redirect_stderr(errors or io.StringIO()),
    ):
        success = o.run(config, modules)
    return success, buffer.getvalue()


@context(g.int_range(200, 800))
@prop("a run holds its time budget and reports every property")
def _holds_budget(budget_ms: int, seed: int) -> bool:
    budget = budget_ms / 1000
    modules = [
        o.TestModule(
            "passing", conj(_threshold("a", 10**9), _threshold("b", 10**9))
        ),
        o.TestModule("failing", conj(_threshold("c", 0))),
    ]
    started = time.perf_counter()
    success, text = _quiet_run(
        o.RunConfig(budget, seed=seed, output=o.OutputMode.QUIET), modules
    )
    elapsed = time.perf_counter() - started
    return (
        not success
        and elapsed < budget + 0.5
        and "FAIL [failing] c" in text
        and "FAIL [passing]" not in text
    )


# Every failing evaluation sleeps, so shrinking from a draw near a million
# down to the boundary takes far longer than the budget. Both a declared
# and an undeclared property are checked on every attempt.
@context(g.int_range(200, 400))
@prop(
    "shrinking stops at the end of the budget, the failure announced",
    attempts=2,
)
def _shrink_budget(budget_ms: int, seed: int) -> bool:
    budget = budget_ms / 1000

    def _run(declared: bool) -> bool:
        @context(g.int_range(0, 10**6))
        @prop("slow to fail", attempts=1 if declared else None)
        def _slow(x: int) -> bool:
            if x >= 1000:
                time.sleep(0.05)
                return False
            return True

        errors = io.StringIO()
        started = time.perf_counter()
        success, text = _quiet_run(
            o.RunConfig(budget, seed=seed, output=o.OutputMode.QUIET),
            [o.TestModule("slow", _slow)],
            errors,
        )
        elapsed = time.perf_counter() - started
        return (
            not success
            and elapsed < budget + 0.1
            and "may not be minimal" in text
            and "FOUND [slow] slow to fail" in errors.getvalue()
        )

    return _run(False) and _run(True)


@prop("a run of holding properties succeeds under every output mode")
def _succeeds(seed: int, mode: bool) -> bool:
    output = o.OutputMode.JSON if mode else o.OutputMode.RICH
    success, text = _quiet_run(
        o.RunConfig(0.3, seed=seed, output=output),
        [o.TestModule("m", _threshold("a", 10**9))],
    )
    return success and str(seed) in text


@prop("unresolvable specifications are rejected before anything runs")
def _rejects(seed: int) -> bool:
    modules = [
        o.TestModule("m", conj(_threshold("same", 1), _threshold("same", 2)))
    ]
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            o.run(
                o.RunConfig(0.3, seed=seed, output=o.OutputMode.QUIET), modules
            )
    except SpecificationError:
        return buffer.getvalue() == ""
    return False


@prop("descriptions shared across modules are rejected before anything runs")
def _cross_module(seed: int) -> bool:
    modules = [
        o.TestModule("first", _threshold("shared", 1)),
        o.TestModule("second", _threshold("shared", 2)),
    ]
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            o.run(
                o.RunConfig(0.3, seed=seed, output=o.OutputMode.QUIET), modules
            )
    except SpecificationError as error:
        message = str(error)
        return (
            buffer.getvalue() == ""
            and '"shared"' in message
            and '"first"' in message
            and '"second"' in message
        )
    return False


@context(g.int_range(2, 5))
@prop("a run makes every declared attempt, past the end of its budget")
def _declared_floor(attempts: int, seed: int) -> bool:
    calls = 0

    @prop("slow", attempts=attempts)
    def _slow(x: int) -> bool:
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return True

    success, _ = _quiet_run(
        o.RunConfig(0.005, seed=seed, output=o.OutputMode.QUIET),
        [o.TestModule("m", conj(_threshold("fast", 10**9), _slow))],
    )
    return success and calls == attempts


@prop("check prints failures with the seed and is silent on success")
def _check(seed: int) -> bool:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        failed = check(_threshold("t", -1), seed=seed)
        passed = check(_threshold("t", 10**9), seed=seed)
    text = buffer.getvalue()
    return (
        not failed
        and passed
        and "FAIL: t" in text
        and f"seed={seed}" in text
        and text.count("FAIL") == 1
    )


@context(g.float_range(-1.0, 1.0))
@prop("the configuration rejects exactly the non-positive budgets")
def _config(budget: float) -> bool:
    try:
        o.RunConfig(budget)
    except ValueError:
        return budget <= 0
    return budget > 0


spec = conj(
    _holds_budget,
    _shrink_budget,
    _succeeds,
    _rejects,
    _cross_module,
    _declared_floor,
    _check,
    _config,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
