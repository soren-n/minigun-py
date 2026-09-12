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
    config: o.RunConfig, modules: list[o.TestModule]
) -> tuple[bool, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
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


@context(g.int_range(-10, 0))
@prop("a non-positive budget is rejected by the configuration")
def _config(budget: int) -> bool:
    try:
        o.RunConfig(float(budget))
    except ValueError:
        return True
    return False


spec = conj(_holds_budget, _succeeds, _rejects, _check, _config)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
