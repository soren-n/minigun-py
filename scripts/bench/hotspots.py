"""
Profiles of the current tree: the shrink benchmarks and a budgeted run.

Each workload is profiled twice, deterministically with ``cProfile`` and
by sampling with ``pyinstrument``; the outputs are written under
``--out``. A profiled run performs fewer attempts than an unprofiled one,
so the profiles say where time goes, not how much of it there is.
"""

import argparse
import cProfile
import io
import pstats
import sys
from collections.abc import Callable
from pathlib import Path

import micro
import pyinstrument

from minigun.cli import run_tests
from minigun.orchestrator import OutputMode

TOP = 35


def _cprofile(name: str, workload: Callable[[], object], out: Path) -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    workload()
    profiler.disable()
    profiler.dump_stats(out / f"{name}.pstats")
    text = io.StringIO()
    stats = pstats.Stats(profiler, stream=text)
    stats.strip_dirs()
    for order in ("cumulative", "tottime"):
        text.write(f"\n===== {name}: top {TOP} by {order}\n")
        stats.sort_stats(order).print_stats(TOP)
    (out / f"{name}_cprofile.txt").write_text(text.getvalue())


def _pyinstrument(
    name: str, workload: Callable[[], object], out: Path, interval: float
) -> None:
    profiler = pyinstrument.Profiler(interval=interval)
    profiler.start()
    workload()
    profiler.stop()
    (out / f"{name}_pyinstrument.txt").write_text(
        profiler.output_text(unicode=True, color=False, show_all=False)
    )
    (out / f"{name}_pyinstrument.html").write_text(profiler.output_html())


def _run(budget: float, tests: Path, seed: int) -> Callable[[], object]:
    def _workload() -> object:
        return run_tests(budget, tests, None, OutputMode.QUIET, seed)

    return _workload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tests", type=Path, default=Path("tests"))
    parser.add_argument("--budget", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "workloads",
        nargs="+",
        choices=["shrink", "draw", "run", "all"],
    )
    args = parser.parse_args()
    workloads = (
        ["shrink", "draw", "run"] if "all" in args.workloads else args.workloads
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for name in workloads:
        if name == "run":
            workload = _run(args.budget, args.tests, args.seed)
            interval = 0.001
        else:
            workload = micro.FAMILIES[name]
            interval = 0.0001
        print(f"profiling {name} with cProfile", file=sys.stderr)
        _cprofile(name, workload, args.out)
        print(f"profiling {name} with pyinstrument", file=sys.stderr)
        _pyinstrument(name, workload, args.out, interval)
    print(f"wrote profiles under {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
