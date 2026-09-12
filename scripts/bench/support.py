"""
Version adapter and measurement helpers for the benchmark scripts.

The benchmark scripts run unchanged against the checked-out tree and
against a 3.0.1 worktree. The two APIs differ in shape (state threading
against forking, thunk streams against re-iterable streams), so every
version-specific access goes through this module and is typed loosely.
Which API is present is detected from the installed package, never from
the version string, since the working tree still carries the 3.0.1 number
until the release workflow bumps it.

Scripts are run by path so that ``minigun`` resolves from the active
virtual environment rather than from the working directory::

        uv run python scripts/bench/micro.py --out RESULTS/head all
        (cd ../minigun-py-v3.0.1 && uv run python \\
            ../minigun-py/scripts/bench/micro.py --out RESULTS/v3.0.1 all)
"""

import gc
import json
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import minigun
import minigun.arbitrary
import minigun.cardinality as c
import minigun.generate as g
import minigun.search
import minigun.shrink
import minigun.stream

_arbitrary: Any = minigun.arbitrary
_search: Any = minigun.search
_shrink: Any = minigun.shrink
_stream: Any = minigun.stream

#: Whether the installed minigun is the forking (4.0) API.
IS_FORKING: bool = hasattr(minigun.arbitrary, "fork")

#: A short label for the installed version, used in result file names.
LABEL: str = "head" if IS_FORKING else "v3.0.1"


###############################################################################
# Random sources
###############################################################################
def seed(value: int) -> Any:
    """A random source seeded from an integer."""
    return _arbitrary.seed(value)


def choice(rng: Any, items: list[Any]) -> tuple[Any, Any]:
    """Draw one of ``items``: the advanced source and the item."""
    if IS_FORKING:
        return rng, _arbitrary.choice(rng, items)
    result: tuple[Any, Any] = _arbitrary.choice(rng, items)
    return result


###############################################################################
# Generators and dissections
###############################################################################
def sample(generator: g.Generator[Any], rng: Any) -> tuple[Any, Any]:
    """Draw from a generator: the advanced source and the dissection or
    None on a discard."""
    sampler: Any = generator.sample
    if IS_FORKING:
        return rng, sampler(rng)
    result: tuple[Any, Any] = sampler(rng)
    return result


def make_generator(
    sampler: Callable[[Any], Any], cardinality: c.Cardinality
) -> g.Generator[Any]:
    """A generator from a version-neutral sampler.

    The sampler takes a source and returns the dissection or None; under
    3.0.1 the source is threaded back out unchanged.
    """
    if IS_FORKING:
        return g.Generator(sampler, cardinality)

    def _threaded(state: Any) -> tuple[Any, Any]:
        return state, sampler(state)

    return g.Generator(_threaded, cardinality)  # type: ignore[arg-type]


def shrinks(dissection: Any) -> Iterator[Any]:
    """Iterate the immediate shrunk alternatives of a dissection."""
    if IS_FORKING:
        return iter(dissection.shrinks())

    def _iterate() -> Iterator[Any]:
        stream = dissection.shrinks
        while True:
            try:
                value, stream = stream()
            except StopIteration:
                return
            yield value

    return _iterate()


def unfold(value: Any, alternatives: Callable[[Any], list[Any]]) -> Any:
    """A dissection unfolded from a function listing the immediate
    alternatives of a value."""

    def _trim(current: Any) -> Any:
        return _stream.from_list(alternatives(current))

    return _shrink.unfold(value, _trim)


###############################################################################
# Search
###############################################################################
type Law = Callable[..., bool]


class Counted:
    """A law wrapper counting evaluations."""

    def __init__(self, law: Law):
        self.law = law
        self.calls = 0

    def __call__(self, **args: Any) -> bool:
        self.calls += 1
        return self.law(**args)


def trim(law: Law, dissection: Any) -> dict[str, Any]:
    """Walk a failing argument dissection to a minimal counterexample
    with the installed version's own trimmer."""
    if IS_FORKING:
        args, _ = _search._trim(law, dissection, None)
        result: dict[str, Any] = args
        return result
    trimmed = _search._trim_counter_example(law, dissection)
    head: dict[str, Any] = trimmed.head
    return head


def find_counter_example(
    seed_value: int,
    law: Law,
    generators: dict[str, g.Generator[Any]],
    attempts: int,
) -> dict[str, Any] | None:
    """Search for a counterexample with the installed version's search."""
    rng = seed(seed_value)
    if IS_FORKING:
        search = _search.find_counter_example(rng, law, generators, attempts)
        if search.counter_example is None:
            return None
        found: dict[str, Any] = search.counter_example.args
        return found
    _, counter_example = _search.find_counter_example(
        rng, attempts, law, generators
    )
    if counter_example is None:
        return None
    args: dict[str, Any] = counter_example.args
    return args


###############################################################################
# Measurement
###############################################################################
def timed(func: Callable[[], object], repeat: int) -> list[float]:
    """Wall-clock seconds of ``repeat`` calls, garbage collected between."""
    times: list[float] = []
    for _ in range(repeat):
        gc.collect()
        started = time.perf_counter()
        func()
        times.append(time.perf_counter() - started)
    return times


@dataclass(frozen=True)
class Result:
    """One benchmark measurement.

    :param group: The benchmark family, for example ``draw``.
    :param name: The case within the family.
    :param metric: What ``value`` measures, for example ``per_second``.
    :param value: The measurement.
    :param better: ``higher`` or ``lower``: which direction is better.
    :param details: Anything else worth reporting alongside the value.
    """

    group: str
    name: str
    metric: str
    value: float
    better: str
    details: dict[str, Any] = field(default_factory=dict)


def time_result(
    group: str, name: str, times: list[float], **details: Any
) -> Result:
    """A result of the best of several timings, with the median noted."""
    return Result(
        group,
        name,
        "seconds",
        min(times),
        "lower",
        {"median_seconds": statistics.median(times), **details},
    )


def rate_result(
    group: str, name: str, count: int, times: list[float], **details: Any
) -> Result:
    """A throughput result from the best of several timings."""
    return Result(
        group,
        name,
        "per_second",
        count / min(times),
        "higher",
        {
            "count": count,
            "best_seconds": min(times),
            "median_seconds": statistics.median(times),
            **details,
        },
    )


def _git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(minigun.__file__).resolve().parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_results(out_dir: Path, group: str, results: list[Result]) -> Path:
    """Write a result file for one benchmark family and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{group}.json"
    payload = {
        "label": LABEL,
        "forking_api": IS_FORKING,
        "revision": _git_revision(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def announce(result: Result) -> None:
    """Print a result on one line."""
    print(
        f"{result.group:8} {result.name:36} "
        f"{result.value:14.3f} {result.metric}",
        file=sys.stderr,
    )
