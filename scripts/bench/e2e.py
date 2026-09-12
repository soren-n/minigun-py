"""
End-to-end runs of the ``minigun`` CLI on two checkouts.

For each checkout the CLI runs twice with a fixed seed and budget: on the
checkout's own ``tests`` directory and on a synthetic directory of cheap
properties that both APIs accept. The JSON reports are reduced to
attempts per property and totals and written to ``--out/e2e.json``.

Under 3.0.1 the report carries allocated attempts rather than attempts
performed; for a passing property the two are equal.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SYNTHETIC_MODULES: dict[str, str] = {
    "syn_ints": """
from minigun.specify import conj, prop


@prop("addition commutes")
def _add_commutes(a: int, b: int) -> bool:
    return a + b == b + a


@prop("addition associates")
def _add_associates(a: int, b: int, c: int) -> bool:
    return (a + b) + c == a + (b + c)


@prop("zero is the additive identity")
def _zero_identity(a: int) -> bool:
    return a + 0 == a


@prop("negation is an involution")
def _neg_involution(a: int) -> bool:
    return -(-a) == a


@prop("absolute value is non-negative")
def _abs_nonneg(a: int) -> bool:
    return abs(a) >= 0


spec = conj(
    _add_commutes,
    _add_associates,
    _zero_identity,
    _neg_involution,
    _abs_nonneg,
)
""",
    "syn_lists": """
from minigun.specify import conj, prop


@prop("reverse is an involution")
def _reverse_involution(xs: list[int]) -> bool:
    return list(reversed(list(reversed(xs)))) == xs


@prop("length distributes over concatenation")
def _len_concat(xs: list[int], ys: list[int]) -> bool:
    return len(xs + ys) == len(xs) + len(ys)


@prop("sorting is idempotent")
def _sorted_idempotent(xs: list[int]) -> bool:
    return sorted(sorted(xs)) == sorted(xs)


@prop("appending grows the length by one")
def _append_length(xs: list[int], x: int) -> bool:
    return len([*xs, x]) == len(xs) + 1


@prop("counting an element bounds the length")
def _count_bound(xs: list[int], x: int) -> bool:
    return xs.count(x) <= len(xs)


spec = conj(
    _reverse_involution,
    _len_concat,
    _sorted_idempotent,
    _append_length,
    _count_bound,
)
""",
    "syn_strings": """
from minigun.specify import conj, prop


@prop("string length distributes over concatenation")
def _str_len_concat(s: str, t: str) -> bool:
    return len(s + t) == len(s) + len(t)


@prop("upper is idempotent")
def _upper_idempotent(s: str) -> bool:
    return s.upper().upper() == s.upper()


@prop("strip is idempotent")
def _strip_idempotent(s: str) -> bool:
    return s.strip().strip() == s.strip()


@prop("repetition doubles the length")
def _repeat_length(s: str) -> bool:
    return len(s * 2) == 2 * len(s)


@prop("a string starts with itself")
def _startswith_self(s: str) -> bool:
    return s.startswith(s)


spec = conj(
    _str_len_concat,
    _upper_idempotent,
    _strip_idempotent,
    _repeat_length,
    _startswith_self,
)
""",
    "syn_mixed": """
from minigun.specify import conj, prop


@prop("double negation is the identity on booleans")
def _bool_double_neg(a: bool) -> bool:
    return (not (not a)) == a


@prop("an inserted key is present")
def _dict_insert_present(d: dict[str, int], k: str, v: int) -> bool:
    return k in {**d, k: v}


@prop("insertion grows a dict by at most one")
def _dict_insert_size(d: dict[str, int], k: str, v: int) -> bool:
    return len({**d, k: v}) <= len(d) + 1


@prop("tuple swap is an involution")
def _swap_involution(a: int, b: str) -> bool:
    x, y = (b, a)
    return (y, x) == (a, b)


@prop("multiplying by one is the identity")
def _one_identity(a: int) -> bool:
    return a * 1 == a


spec = conj(
    _bool_double_neg,
    _dict_insert_present,
    _dict_insert_size,
    _swap_involution,
    _one_identity,
)
""",
}


def write_synthetic(directory: Path) -> Path:
    """Write the synthetic test modules and return the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, source in SYNTHETIC_MODULES.items():
        (directory / f"{name}.py").write_text(source.lstrip())
    return directory


@dataclass(frozen=True)
class PropertyRun:
    module: str
    name: str
    success: bool
    attempts: int
    attempt_limit: int | None
    duration: float


@dataclass(frozen=True)
class SuiteRun:
    label: str
    suite: str
    wall_seconds: float
    reported_total: float
    reported_execution: float
    properties: list[PropertyRun]

    @property
    def total_attempts(self) -> int:
        return sum(p.attempts for p in self.properties)


def _property_runs(report: dict[str, Any]) -> list[PropertyRun]:
    runs: list[PropertyRun] = []
    for module in report["modules"]:
        for test in module["tests"]:
            info = test.get("cardinality_info")
            if info is not None:
                attempts = int(info["allocated_attempts"])
                limit: int | None = int(info["attempt_limit"])
            else:
                attempts = int(test["attempts"])
                limit = test.get("attempt_limit")
            runs.append(
                PropertyRun(
                    module["name"],
                    test["name"],
                    bool(test["success"]),
                    attempts,
                    limit,
                    float(test["duration"]),
                )
            )
    return runs


def run_cli(
    root: Path,
    label: str,
    suite: str,
    test_dir: Path | None,
    budget: float,
    seed: int,
    json_flag: list[str],
) -> SuiteRun:
    """Run the CLI of the checkout at ``root`` and reduce its report."""
    command = [
        "uv",
        "run",
        "minigun",
        "--time-budget",
        str(budget),
        "--seed",
        str(seed),
        *json_flag,
    ]
    if test_dir is not None:
        command += ["--test-dir", str(test_dir)]
    print(f"{label}/{suite}: {' '.join(command)}", file=sys.stderr)
    started = time.perf_counter()
    completed = subprocess.run(
        command, cwd=root, capture_output=True, text=True, check=False
    )
    wall = time.perf_counter() - started
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr)
        raise RuntimeError(f"{label}/{suite} exited {completed.returncode}")
    report = json.loads(completed.stdout)
    summary = report["summary"]
    return SuiteRun(
        label,
        suite,
        wall,
        float(summary["total_duration"]),
        float(summary["execution_duration"]),
        _property_runs(report),
    )


def _describe(run: SuiteRun) -> None:
    attempts = [p.attempts for p in run.properties]
    at_limit = sum(
        1
        for p in run.properties
        if p.attempt_limit is not None and p.attempts >= p.attempt_limit
    )
    print(
        f"{run.label:8} {run.suite:10} props={len(attempts):4} "
        f"attempts={sum(attempts):8} min={min(attempts):6} "
        f"median={statistics.median(attempts):8.0f} max={max(attempts):6} "
        f"at_limit={at_limit:3} wall={run.wall_seconds:6.1f}s "
        f"reported={run.reported_total:6.1f}s",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--head", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    synthetic = write_synthetic(args.out / "synthetic_tests")
    checkouts: list[tuple[Path, str, list[str]]] = [
        (args.baseline.resolve(), "v3.0.1", ["--json"]),
        (args.head.resolve(), "head", ["--output", "json"]),
    ]
    runs: list[SuiteRun] = []
    for root, label, json_flag in checkouts:
        for suite, test_dir in (("own", None), ("synthetic", synthetic)):
            run = run_cli(
                root, label, suite, test_dir, args.budget, args.seed, json_flag
            )
            _describe(run)
            runs.append(run)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "e2e.json"
    path.write_text(
        json.dumps(
            {
                "budget": args.budget,
                "seed": args.seed,
                "runs": [asdict(run) for run in runs],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
