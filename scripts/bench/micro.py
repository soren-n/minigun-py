"""
In-process microbenchmarks, runnable under 3.0.1 and the current tree.

Families (select one or ``all``):

- ``draw``: dissections drawn per second for the built-in generators and
  a recursive arithmetic AST.
- ``shrink``: wall time and law evaluations to reach the minimal
  counterexample from a fixed failing draw.
- ``attempts``: attempts per second through the search loop for a law
  that always holds, isolating the per-attempt overhead.
- ``fork``: the cost of the primitives behind per-attempt forking.
- ``memory``: peak allocation and frame depth while shrinking.

Results are written as JSON under ``--out``; see ``report.py``.
"""

import argparse
import random
import sys
import timeit
import tracemalloc
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from support import (
    IS_FORKING,
    LABEL,
    Counted,
    Result,
    announce,
    choice,
    find_counter_example,
    make_generator,
    rate_result,
    sample,
    seed,
    shrinks,
    time_result,
    timed,
    trim,
    unfold,
    write_results,
)

import minigun.cardinality as c
import minigun.generate as g

REPEAT = 5


###############################################################################
# Generators under test
###############################################################################
def arith() -> g.Generator[Any]:
    """The recursive expression AST of the ``refine_choice`` example."""

    def _number(value: int) -> tuple[str, int]:
        return ("num", value)

    def _node(kind: str) -> Callable[[Any, Any], tuple[str, Any, Any]]:
        def _make(left: Any, right: Any) -> tuple[str, Any, Any]:
            return (kind, left, right)

        return _make

    def _sized(size: int) -> g.Generator[Any]:
        if size == 0:
            return g.map(_number, g.ints())
        half = size // 2
        sub: g.Generator[Any] = g.lazy(lambda: _sized(half))
        return g.weighted_choice(
            (1, g.map(_number, g.ints())),
            (half, g.map(_node("plus"), sub, sub)),
            (half, g.map(_node("minus"), sub, sub)),
            (half, g.map(_node("times"), sub, sub)),
            (half, g.map(_node("divide"), sub, sub)),
        )

    return g.bind(_sized, g.small_nats())


type Op = tuple[Any, ...]


def stack_program(values: g.Generator[int]) -> g.Generator[list[Op]]:
    """The stack program generator of the ``modeling`` example, written
    against the adapter so it runs under both versions."""

    def _alternatives(prog: list[Op]) -> list[list[Op]]:
        return [
            prog[:index] + prog[index + 1 :]
            for index in range(len(prog) - 1, -1, -1)
        ]

    def _visit(
        fuel: int,
        rng: Any,
        stack_ctr: int,
        item_ctr: int,
        stacks: list[str],
        nonempty: list[str],
    ) -> tuple[Any, list[Op] | None]:
        if fuel <= 0 or (len(stacks) == 0 and fuel < 2):
            return rng, [("init", f"s{stack_ctr}")]
        ops = ["init"]
        if stacks:
            ops.append("push")
        if nonempty:
            ops.append("pop")
        rng, op = choice(rng, ops)
        after = f"s{stack_ctr}"
        if op == "init":
            rng, rest = _visit(
                fuel - 1,
                rng,
                stack_ctr + 1,
                item_ctr,
                [*stacks, after],
                nonempty,
            )
            head: Op = ("init", after)
        elif op == "push":
            rng, before = choice(rng, stacks)
            rng, dissection = sample(values, rng)
            if dissection is None:
                return rng, None
            rng, rest = _visit(
                fuel - 1,
                rng,
                stack_ctr + 1,
                item_ctr,
                [*stacks, after],
                [*nonempty, after],
            )
            head = ("push", before, after, dissection.head)
        else:
            rng, before = choice(rng, nonempty)
            rng, rest = _visit(
                fuel - 1,
                rng,
                stack_ctr + 1,
                item_ctr + 1,
                [*stacks, after],
                nonempty,
            )
            head = ("pop", before, after, f"v{item_ctr}")
        return rng, None if rest is None else [head, *rest]

    def _sized(size: int) -> g.Generator[list[Op]]:
        def _sample(rng: Any) -> Any:
            _, prog = _visit(size, rng, 0, 0, [], [])
            return None if prog is None else unfold(prog, _alternatives)

        return make_generator(_sample, c.INFINITE)

    programs: g.Generator[list[Op]] = g.bind(_sized, g.small_nats())
    return programs


def run_stack_program(
    pop: Callable[[list[int]], tuple[list[int], int]], prog: list[Op]
) -> bool:
    """Evaluate a stack program against the list model."""
    model: dict[str, list[int]] = {}
    impl: dict[str, list[int]] = {}
    items: dict[str, int] = {}
    for op in prog:
        match op:
            case ("init", after):
                model[after] = []
                impl[after] = []
            case ("push", before, after, value):
                model[after] = [*model[before], value]
                impl[after] = [*impl[before], value]
            case ("pop", before, after, name):
                model_rest, model_item = model[before][:-1], model[before][-1]
                impl_rest, impl_item = pop(impl[before])
                if model_item != impl_item:
                    return False
                model[after] = model_rest
                impl[after] = impl_rest
                items[name] = model_item
    return True


def broken_pop(xs: list[int]) -> tuple[list[int], int]:
    """A pop returning the bottom item instead of the top."""
    return xs[:-1], xs[0]


DRAW_CASES: dict[str, tuple[Callable[[], g.Generator[Any]], int]] = {
    "ints": (g.ints, 100_000),
    "floats": (g.floats, 100_000),
    "strings": (g.strings, 10_000),
    "lists_ints": (lambda: g.lists(g.ints()), 10_000),
    "dicts_str_int": (lambda: g.dicts(g.strings(), g.ints()), 2_000),
    "nested_lists": (lambda: g.lists(g.lists(g.ints())), 1_000),
    "arith_ast": (arith, 2_000),
}


###############################################################################
# Draw throughput
###############################################################################
def _draw_only(generator: g.Generator[Any], count: int) -> int:
    """Draw ``count`` dissections; the number discarded."""
    sampler: Any = generator.sample
    rng = seed(1234)
    discards = 0
    if IS_FORKING:
        for _ in range(count):
            if sampler(rng) is None:
                discards += 1
    else:
        for _ in range(count):
            rng, dissection = sampler(rng)
            if dissection is None:
                discards += 1
    return discards


def _draw_and_peek(generator: g.Generator[Any], count: int) -> int:
    """Draw ``count`` dissections and walk their first ten alternatives,
    which under 3.0.1 costs what draw alone pays eagerly."""
    rng = seed(1234)
    walked = 0
    for _ in range(count):
        rng, dissection = sample(generator, rng)
        if dissection is None:
            continue
        for index, _child in enumerate(shrinks(dissection)):
            walked += 1
            if index == 9:
                break
    return walked


def bench_draw() -> list[Result]:
    results: list[Result] = []
    for name, (make, count) in DRAW_CASES.items():
        generator = make()
        discards = _draw_only(generator, count)
        times = timed(partial(_draw_only, generator, count), REPEAT)
        results.append(
            rate_result("draw", name, count, times, discards=discards)
        )
        announce(results[-1])
        times = timed(partial(_draw_and_peek, generator, count), REPEAT)
        results.append(rate_result("draw", f"{name}+peek10", count, times))
        announce(results[-1])
    return results


###############################################################################
# Shrink cost
###############################################################################
def _first_failing_draw(
    generators: dict[str, g.Generator[Any]],
    law: Callable[..., bool],
    interesting: Callable[[dict[str, Any]], bool],
) -> tuple[int, Any]:
    """The lowest seed whose first draw fails the law and is interesting."""
    pack = g.argument_pack(generators)
    for seed_value in range(100_000):
        _, dissection = sample(pack, seed(seed_value))
        if dissection is None:
            continue
        if not law(**dissection.head) and interesting(dissection.head):
            return seed_value, dissection
    raise RuntimeError("no failing draw within 100000 seeds")


def _shrink_case(
    name: str,
    generators: dict[str, g.Generator[Any]],
    law: Callable[..., bool],
    interesting: Callable[[dict[str, Any]], bool],
    describe: Callable[[dict[str, Any]], str],
) -> Result:
    seed_value, dissection = _first_failing_draw(generators, law, interesting)
    counted = Counted(law)
    reached = trim(counted, dissection)
    evaluations = counted.calls
    times = timed(lambda: trim(law, dissection), REPEAT)
    result = time_result(
        "shrink",
        name,
        times,
        seed=seed_value,
        start=describe(dissection.head),
        reached=describe(reached),
        evaluations=evaluations,
        microseconds_per_evaluation=1e6 * min(times) / evaluations,
    )
    announce(result)
    return result


def bench_shrink() -> list[Result]:
    threshold = 1000

    def _int_law(x: int) -> bool:
        return x < threshold

    def _len_law(xs: list[int]) -> bool:
        return len(xs) < 8

    def _nested_law(entries: dict[str, list[int]]) -> bool:
        return sum(len(xs) for xs in entries.values()) < 5

    def _stack_law(prog: list[Op]) -> bool:
        return run_stack_program(broken_pop, prog)

    return [
        _shrink_case(
            "int_lt_threshold",
            {"x": g.int_range(0, 10_000)},
            _int_law,
            lambda args: args["x"] >= 5000,
            lambda args: str(args["x"]),
        ),
        _shrink_case(
            "list_len_lt_k",
            {"xs": g.lists(g.ints())},
            _len_law,
            lambda args: len(args["xs"]) >= 40,
            lambda args: f"len={len(args['xs'])} {args['xs'][:8]}...",
        ),
        _shrink_case(
            "nested_dict_lists",
            {"entries": g.dicts(g.strings(), g.lists(g.ints()))},
            _nested_law,
            lambda args: sum(len(xs) for xs in args["entries"].values()) >= 30,
            lambda args: (
                f"keys={len(args['entries'])} "
                f"ints={sum(len(xs) for xs in args['entries'].values())}"
            ),
        ),
        _shrink_case(
            "stack_program_broken_pop",
            {"prog": stack_program(g.ints())},
            _stack_law,
            lambda args: len(args["prog"]) >= 20,
            lambda args: f"ops={len(args['prog'])}",
        ),
    ]


###############################################################################
# Attempt throughput
###############################################################################
def bench_attempts() -> list[Result]:
    attempts = 20_000

    def _reflexive(x: int) -> bool:
        return x == x

    cases: dict[str, dict[str, g.Generator[Any]]] = {
        "x_eq_x_ints": {"x": g.ints()},
        "x_eq_x_constant": {"x": g.constant(0)},
        "x_eq_x_lists_ints": {"x": g.lists(g.ints())},
    }
    results: list[Result] = []
    for name, generators in cases.items():
        times = timed(
            partial(find_counter_example, 7, _reflexive, generators, attempts),
            REPEAT,
        )
        results.append(
            rate_result(
                "attempts",
                name,
                attempts,
                times,
                microseconds_per_attempt=1e6 * min(times) / attempts,
            )
        )
        announce(results[-1])
    return results


###############################################################################
# Fork primitives
###############################################################################
def bench_fork() -> list[Result]:
    number = 200_000
    parent = random.Random(1)
    cases: dict[str, Callable[[], object]] = {
        "Random(int)": lambda: random.Random(123456789),
        "Random(str)": lambda: random.Random("42\x1fsome property"),
        "Random(None)": lambda: random.Random(),
        "getrandbits(64)": lambda: parent.getrandbits(64),
        "fork=getrandbits+Random": lambda: random.Random(
            parent.getrandbits(64)
        ),
        "perf_counter": lambda: timeit.default_timer(),
        "randint(0,10000)": lambda: parent.randint(0, 10_000),
    }
    results: list[Result] = []
    for name, func in cases.items():
        seconds = min(timeit.repeat(func, number=number, repeat=REPEAT))
        results.append(
            Result(
                "fork",
                name,
                "nanoseconds",
                1e9 * seconds / number,
                "lower",
            )
        )
        announce(results[-1])
    return results


###############################################################################
# Memory and depth
###############################################################################
class _DepthProbe:
    """Tracks the maximum Python call depth reached while active."""

    def __init__(self) -> None:
        self.depth = 0
        self.max_depth = 0

    def __call__(self, frame: Any, event: str, arg: Any) -> None:
        if event == "call":
            self.depth += 1
            if self.depth > self.max_depth:
                self.max_depth = self.depth
        elif event == "return":
            self.depth -= 1


def _memory_case(
    name: str,
    generators: dict[str, g.Generator[Any]],
    law: Callable[..., bool],
    interesting: Callable[[dict[str, Any]], bool],
) -> list[Result]:
    seed_value, dissection = _first_failing_draw(generators, law, interesting)
    counted = Counted(law)
    tracemalloc.start()
    trim(counted, dissection)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    probe = _DepthProbe()
    sys.setprofile(probe)
    try:
        trim(law, dissection)
    finally:
        sys.setprofile(None)
    results = [
        Result(
            "memory",
            f"{name}:peak_kib",
            "kibibytes",
            peak / 1024,
            "lower",
            {"seed": seed_value, "evaluations": counted.calls},
        ),
        Result(
            "memory",
            f"{name}:max_frame_depth",
            "frames",
            probe.max_depth,
            "lower",
        ),
    ]
    for result in results:
        announce(result)
    return results


def bench_memory() -> list[Result]:
    def _outer_len(xs: list[list[int]]) -> bool:
        return len(xs) < 10

    def _total_len(xs: list[list[int]]) -> bool:
        return sum(len(x) for x in xs) < 10

    def _int_law(x: int) -> bool:
        return x < 1000

    return [
        *_memory_case(
            "list100_of_lists_len",
            {"xs": g.bounded_lists(100, 100, g.bounded_lists(0, 10, g.ints()))},
            _outer_len,
            lambda args: True,
        ),
        *_memory_case(
            "list100_of_lists_total",
            {"xs": g.bounded_lists(100, 100, g.bounded_lists(0, 10, g.ints()))},
            _total_len,
            lambda args: True,
        ),
        *_memory_case(
            "int_lt_threshold",
            {"x": g.int_range(0, 10_000)},
            _int_law,
            lambda args: args["x"] >= 5000,
        ),
    ]


###############################################################################
# Entry point
###############################################################################
FAMILIES: dict[str, Callable[[], list[Result]]] = {
    "draw": bench_draw,
    "shrink": bench_shrink,
    "attempts": bench_attempts,
    "fork": bench_fork,
    "memory": bench_memory,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("families", nargs="+", choices=[*FAMILIES, "all"])
    args = parser.parse_args()
    families = list(FAMILIES) if "all" in args.families else args.families
    print(f"minigun {LABEL} ({sys.version.split()[0]})", file=sys.stderr)
    for family in families:
        path = write_results(args.out, family, FAMILIES[family]())
        print(f"wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
