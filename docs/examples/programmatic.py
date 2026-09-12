"""Running specifications programmatically."""

import minigun.specify as sp
from minigun.orchestrator import OutputMode, RunConfig, TestModule, run
from minigun.specify import conj, prop


@prop("Addition is commutative")
def _commutative(x: int, y: int) -> bool:
    return x + y == y + x


@prop("Multiplication distributes over addition")
def _distributes(x: int, y: int, z: int) -> bool:
    return x * (y + z) == x * y + x * z


spec = conj(_commutative, _distributes)


# -- start: run --
def run_with_budget() -> bool:
    """The CLI's behaviour as a library call: a time budget and a reporter."""
    config = RunConfig(time_budget=5.0, seed=42, output=OutputMode.JSON)
    return run(config, [TestModule("arithmetic", spec)])


# -- end: run --


# -- start: evaluate --
def collect_outcomes() -> list[sp.Outcome]:
    """Drive the evaluator directly and keep the structured outcomes."""
    outcomes: list[sp.Outcome] = []
    sp.evaluate(
        seed=42,
        spec=spec,
        allowance_for=lambda resolved: sp.Allowance(max_attempts=200),
        on_start=lambda prop: None,
        on_outcome=outcomes.append,
    )
    return outcomes


# -- end: evaluate --

if __name__ == "__main__":
    import sys

    for outcome in collect_outcomes():
        print(outcome.desc, "held" if outcome.holds else "failed")
    sys.exit(0 if run_with_budget() else 1)
