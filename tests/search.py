"""Properties of the counterexample search and shrinking."""

import contextvars
import itertools
import math
import random
import time

import minigun.arbitrary as a
import minigun.generate as g
import minigun.search as s
from minigun import check
from minigun.specify import conj, context, prop


# With upper at least twice the threshold, half the draws fail the law,
# so 200 attempts find a counterexample but for a 2^-200 chance.
@context(g.int_range(1, 500), g.int_range(1000, 10000))
@prop("integer counterexamples shrink to the exact boundary")
def _integer_boundary(threshold: int, upper: int, rng: random.Random) -> bool:
    search = s.find_counter_example(
        rng, lambda x: x < threshold, {"x": g.int_range(0, upper)}, 200
    )
    if search.counter_example is None:
        return False
    return search.counter_example.args == {"x": threshold}


@context(g.int_range(1, 500), g.int_range(1000, 10000))
@prop("shrinking evaluates the law a logarithmic number of times")
def _evaluation_count(threshold: int, upper: int, rng: random.Random) -> bool:
    calls = 0

    def _law(x: int) -> bool:
        nonlocal calls
        calls += 1
        return x < threshold

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, upper)}, 200
    )
    if search.counter_example is None:
        return False
    # A bisection halves the interval per evaluation; the final node's
    # alternatives are walked once more to confirm the minimum.
    depth = math.log2(upper) + 2
    return calls <= search.evaluations + 2 * depth


@context(g.float_range(1.0, 1000.0), g.float_range(2.0, 10.0))
@prop("float counterexamples shrink to the boundary")
def _float_boundary(
    threshold: float, spread: float, rng: random.Random
) -> bool:
    # At least half of the range fails, as for integers; halving stops one
    # part in a billion from the boundary, well inside the tolerance.
    search = s.find_counter_example(
        rng,
        lambda x: x < threshold,
        {"x": g.float_range(0.0, threshold * spread)},
        200,
    )
    if search.counter_example is None:
        return False
    x = search.counter_example.args["x"]
    return threshold <= x <= threshold * (1 + 1e-6)


@context(g.int_range(1, 50))
@prop("a search stops at the attempt that finds a counterexample")
def _stops(failing: int, rng: random.Random) -> bool:
    calls = 0

    def _law(x: int) -> bool:
        nonlocal calls
        calls += 1
        return calls < failing

    search = s.find_counter_example(rng, _law, {"x": g.ints()}, 100)
    return (
        search.counter_example is not None
        and search.counter_example.attempt == failing - 1
        and search.attempts == failing
        and search.discards == 0
    )


@context(g.int_range(1, 4))
@prop("list counterexamples shrink to the shortest list of zeros")
def _list_minimal(length: int, rng: random.Random) -> bool:
    search = s.find_counter_example(
        rng, lambda xs: len(xs) < length, {"xs": g.lists(g.ints())}, 300
    )
    if search.counter_example is None:
        return False
    return search.counter_example.args == {"xs": [0] * length}


@prop("a law that always holds has no counterexample")
def _always_holds(rng: random.Random, attempts: int) -> bool:
    bound = abs(attempts) % 50
    search = s.find_counter_example(rng, lambda x: True, {"x": g.ints()}, bound)
    return (
        search.counter_example is None
        and search.attempts == bound
        and search.discards == 0
    )


@context(g.int_range(1, 50))
@prop("rejected draws are counted as discards")
def _discards(attempts: int, rng: random.Random) -> bool:
    generator = g.filter(lambda x: False, g.ints())
    search = s.find_counter_example(
        rng, lambda x: True, {"x": generator}, attempts
    )
    return (
        search.counter_example is None
        and search.attempts == attempts
        and search.discards == attempts
        and search.evaluations == 0
    )


@context(g.int_range(1, 50))
@prop("arguments a law rejects with assume are counted as discards")
def _assume_discards(attempts: int, rng: random.Random) -> bool:
    def _law(x: int) -> bool:
        s.assume(False)
        return False

    search = s.find_counter_example(rng, _law, {"x": g.ints()}, attempts)
    return (
        search.counter_example is None
        and search.discards == attempts
        and search.evaluations == 0
    )


@context(g.int_range(1, 500))
@prop("counterexamples shrink only through arguments the law accepts")
def _assume_shrinks(threshold: int, rng: random.Random) -> bool:
    def _law(x: int) -> bool:
        if x % 2 == 1:
            s.discard()
        return x < threshold

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, 10000)}, 200
    )
    if search.counter_example is None:
        return False
    x = search.counter_example.args["x"]
    return (
        x % 2 == 0
        and x >= threshold
        and search.counter_example.exception is None
    )


@prop("an expired deadline stops the search after one attempt")
def _deadline(rng: random.Random) -> bool:
    search = s.find_counter_example(
        rng, lambda x: True, {"x": g.ints()}, 100, deadline=time.perf_counter()
    )
    return search.attempts == 1 and search.counter_example is None


# The discard count comes from a generator other than the search's own, so
# a mutated search cannot also choose it.
@context(g.int_range(1, 50), g.rngs())
@prop("an expired deadline lets the search run until the law is evaluated")
def _deadline_discards(discarded: int, rng: random.Random) -> bool:
    calls = 0

    def _law(x: int) -> bool:
        nonlocal calls
        calls += 1
        if calls <= discarded:
            s.discard()
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.ints()}, 100, deadline=time.perf_counter()
    )
    return (
        search.attempts == discarded + 1
        and search.discards == discarded
        and search.counter_example is None
    )


@prop("past a deadline the attempt limit bounds a law that always discards")
def _deadline_limit(rng: random.Random) -> bool:
    search = s.find_counter_example(
        rng, lambda x: s.discard(), {"x": g.ints()}, 20, deadline=0.0
    )
    return search.attempts == 20 and search.discards == 20


# Every draw fails, and every draw but the lower bound has smaller
# alternatives, so only the deadline stops shrinking at the arguments
# first found.
@context(g.int_range(1, 500), g.rngs())
@prop("an expired shrink deadline reports the counterexample as found")
def _shrink_deadline(threshold: int, rng: random.Random) -> bool:
    found: list[s.CounterExample] = []
    search = s.find_counter_example(
        rng,
        lambda x: x < threshold,
        {"x": g.int_range(1000, 10000)},
        10,
        shrink_deadline=time.perf_counter(),
        on_found=found.append,
    )
    example = search.counter_example
    return (
        example is not None
        and found == [s.CounterExample(example.args, 0)]
        and example.shrinks == 0
        and example.path == (example.args,)
        and example.minimal == (example.args["x"] == 1000)
        and search.evaluations == 1
    )


@context(g.int_range(1, 500), g.rngs())
@prop("a counterexample is announced before it is shrunk, steps counted")
def _announce(threshold: int, rng: random.Random) -> bool:
    calls = 0
    failing = 0
    announced_at: list[int] = []
    found: list[s.CounterExample] = []

    def _law(x: int) -> bool:
        nonlocal calls, failing
        calls += 1
        failing += x >= threshold
        return x < threshold

    def _found(example: s.CounterExample) -> None:
        announced_at.append(calls)
        found.append(example)

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, 10000)}, 200, on_found=_found
    )
    example = search.counter_example
    if example is None or len(found) != 1:
        return False
    first = found[0]
    return (
        announced_at == [search.evaluations]
        and first.attempt == example.attempt
        and first.args["x"] >= example.args["x"] == threshold
        and first.shrinks == 0
        and example.shrinks == failing - 1
        and example.minimal
    )


@prop("exceptions are counterexamples and are reported with the arguments")
def _exception(rng: random.Random) -> bool:
    def _law(x: int) -> bool:
        if x > 10:
            raise ValueError("too big")
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, 10000)}, 200
    )
    if search.counter_example is None:
        return False
    return search.counter_example.args == {"x": 11} and isinstance(
        search.counter_example.exception, ValueError
    )


@prop("shrinking keeps the kind of failure that was found")
def _failure_kind(by_exception: bool, rng: random.Random) -> bool:
    # Above the boundary the law fails one way; between zero and the
    # boundary it fails the other way. Only the boundary is a valid
    # minimum of the failure that was found.
    def _law(x: int) -> bool:
        if x >= 1000:
            if by_exception:
                raise ValueError("found failure")
            return False
        if x > 0:
            if by_exception:
                return False
            raise TypeError("other failure")
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(1000, 10000)}, 200
    )
    if search.counter_example is None:
        return False
    found = search.counter_example
    if found.args != {"x": 1000}:
        return False
    if by_exception:
        return isinstance(found.exception, ValueError)
    return found.exception is None


@prop("a search is a function of its seed")
def _reproducible(seed: int) -> bool:
    def _run() -> s.Search:
        return s.find_counter_example(
            a.seed(seed), lambda x: x < 300, {"x": g.ints()}, 100
        )

    return _run() == _run()


###############################################################################
# Labels and coverage
###############################################################################


@context(g.int_range(1, 9), g.int_range(1, 200))
@prop("labels count the tested attempts that carry them, once per attempt")
def _labels(modulus: int, attempts: int, rng: random.Random) -> bool:
    seen: list[int] = []

    def _law(x: int) -> bool:
        seen.append(x % modulus)
        s.label(f"r{x % modulus}")
        s.label("every")
        s.label("every")
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, 1000)}, attempts
    )
    expected = {f"r{r}": seen.count(r) for r in set(seen)}
    expected["every"] = attempts
    return search.labels == expected and search.coverage == {}


@context(g.int_range(2, 5), g.int_range(1, 200))
@prop("a discarded attempt's labels are dropped")
def _labels_discarded(modulus: int, attempts: int, rng: random.Random) -> bool:
    def _law(x: int) -> bool:
        s.label("drawn")
        s.assume(x % modulus != 0)
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, 1000)}, attempts
    )
    return search.labels.get("drawn", 0) == search.evaluations


@context(g.int_range(1, 500), g.int_range(1000, 10000))
@prop("shrunk candidates are not counted in the labels")
def _labels_shrinking(threshold: int, upper: int, rng: random.Random) -> bool:
    calls = 0

    def _law(x: int) -> bool:
        nonlocal calls
        calls += 1
        s.label("evaluated")
        return x < threshold

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, upper)}, 200
    )
    return (
        search.counter_example is not None
        and calls > search.evaluations
        and search.labels == {"evaluated": search.evaluations}
    )


@context(g.int_range(1, 20))
@prop("a search run by a law keeps its labels apart from the outer search")
def _labels_nested(attempts: int, rng: random.Random) -> bool:
    inner: list[dict[str, int]] = []

    def _inner(y: int) -> bool:
        s.label("inner")
        return True

    def _outer(x: int) -> bool:
        s.label("before")
        search = s.find_counter_example(
            a.fork(rng), _inner, {"y": g.ints()}, attempts
        )
        inner.append(search.labels)
        s.label("after")
        return True

    outer = s.find_counter_example(rng, _outer, {"x": g.ints()}, attempts)
    return outer.labels == {"before": attempts, "after": attempts} and all(
        labels == {"inner": attempts} for labels in inner
    )


@prop("labels outside a search do nothing and names must be strings")
def _labels_outside(name: str) -> bool:
    def _outside() -> bool:
        # No search is running, so neither call records anything or
        # raises.
        s.label(name)
        s.cover(0.5, True, name)
        s.cover(0.25, True, name)
        try:
            s.label(1)  # type: ignore[arg-type]
        except TypeError:
            return True
        return False

    # This law runs inside a search; a fresh context has none.
    return contextvars.Context().run(_outside)


_FRACTIONS = [-1.0, -0.0, 0.0, 1e-300, 0.5, 1.0, 1.0000001, 2.0, math.nan]


@context(g.floats())
@prop("cover accepts exactly the fractions in (0, 1]")
def _cover_range(drawn: float) -> bool:
    def _accepted(fraction: float) -> bool:
        try:
            s.cover(fraction, True, "c")
        except ValueError:
            return False
        return True

    # The boundary fractions are checked on every attempt; a drawn float
    # would rarely be one. Each is checked outside any search, where the
    # label has no requirement yet.
    return all(
        contextvars.Context().run(_accepted, fraction)
        == (0.0 < fraction <= 1.0)
        for fraction in [drawn, *_FRACTIONS]
    )


@context(g.float_range(0.01, 1.0), g.int_range(0, 9), g.int_range(1, 100))
@prop("cover records its requirement and labels the attempts in its class")
def _cover_records(
    fraction: float, below: int, attempts: int, rng: random.Random
) -> bool:
    seen: list[bool] = []

    def _law(x: int) -> bool:
        seen.append(x < below)
        s.cover(fraction, x < below, "low")
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.int_range(0, 9)}, attempts
    )
    hits = seen.count(True)
    return search.coverage == {"low": fraction} and search.labels == (
        {"low": hits} if hits else {}
    )


@context(g.float_range(0.01, 0.5), g.float_range(0.51, 1.0))
@prop("two requirements of one label fail the law with a ValueError")
def _cover_conflict(first: float, second: float, rng: random.Random) -> bool:
    def _law(x: int) -> bool:
        s.cover(first, True, "c")
        s.cover(second, True, "c")
        return True

    search = s.find_counter_example(rng, _law, {"x": g.ints()}, 10)
    example = search.counter_example
    return (
        example is not None
        and example.attempt == 0
        and isinstance(example.exception, ValueError)
    )


@context(g.int_range(0, 50), g.rngs())
@prop("a search cut short by its deadline keeps the labels of its attempts")
def _labels_deadline(discarded: int, rng: random.Random) -> bool:
    calls = 0

    def _law(x: int) -> bool:
        nonlocal calls
        calls += 1
        s.label("drawn")
        if calls <= discarded:
            s.discard()
        s.cover(0.5, True, "tested")
        return True

    search = s.find_counter_example(
        rng, _law, {"x": g.ints()}, 100, deadline=time.perf_counter()
    )
    return (
        search.attempts == discarded + 1
        and search.labels == {"drawn": 1, "tested": 1}
        and search.coverage == {"tested": 0.5}
    )


###############################################################################
# Shrink paths
###############################################################################


@context(g.int_range(1, 500), g.int_range(1000, 10000), g.rngs())
@prop("a shrink path runs from the arguments found down to the counterexample")
def _path(threshold: int, upper: int, rng: random.Random) -> bool:
    found: list[s.CounterExample] = []
    search = s.find_counter_example(
        rng,
        lambda x: x < threshold,
        {"x": g.int_range(0, upper)},
        200,
        on_found=found.append,
    )
    example = search.counter_example
    if example is None:
        return False
    xs = [args["x"] for args in example.path]
    return (
        found[0].path == ()
        and example.path[0] == found[0].args
        and example.path[-1] == example.args
        and len(example.path) == example.shrinks + 1
        and all(x >= threshold for x in xs)
        and all(before > after for before, after in itertools.pairwise(xs))
    )


@context(g.bools(), g.int_range(1, 200), g.rngs())
@prop("every step of a shrink path fails the way the arguments found did")
def _path_failures(by_exception: bool, total: int, rng: random.Random) -> bool:
    def _law(xs: list[int]) -> bool:
        if sum(xs) >= total:
            if by_exception:
                raise ValueError("too much")
            return False
        return True

    search = s.find_counter_example(
        rng, _law, {"xs": g.lists(g.int_range(0, 100))}, 500
    )
    example = search.counter_example
    if example is None:
        # Lists of enough small values to reach the total are common.
        return False
    for args in example.path:
        try:
            holds = _law(**args)
        except ValueError:
            holds = not by_exception
        else:
            holds = holds or by_exception
        if holds:
            return False
    return True


###############################################################################
# Replays
###############################################################################


@context(g.int_range(0, 10**6), g.int_range(1, 20), g.rngs())
@prop("replays are evaluated first; a failing one is shrunk before any draw")
def _replays(value: int, attempts: int, rng: random.Random) -> bool:
    generators = {"x": g.int_range(0, 1000)}
    dissection = g.argument_pack(generators).sample(a.seed(value))
    if dissection is None:
        return False
    fails = dissection.head["x"] >= 500
    state = rng.getstate()
    replays = [s.Replay(value, 3, None), s.Replay(value, 5, dissection)]
    found: list[s.CounterExample] = []
    search = s.find_counter_example(
        rng,
        lambda x: x < 500,
        generators,
        attempts,
        on_found=found.append,
        replays=replays,
    )
    example = search.counter_example
    if not fails:
        # The replay held, so the attempts ran as without it.
        return search.replayed == 1 and search.attempts > 0
    return (
        search.replayed == 1
        and search.attempts == 0
        and rng.getstate() == state
        and example is not None
        and example.seed == value
        and example.attempt == 5
        and example.args == {"x": 500}
        and example.path[0] == dissection.head
        and found[0].seed == value
    )


@context(g.int_range(1, 10), g.rngs())
@prop("labels given while replaying stay out of an enclosing search")
def _replay_labels(attempts: int, rng: random.Random) -> bool:
    inner_generators = {"y": g.int_range(0, 9)}
    replay = g.argument_pack(inner_generators).sample(a.fork(rng))

    def _inner(y: int) -> bool:
        s.label("replayed")
        return True

    def _outer(x: int) -> bool:
        s.label("outer")
        s.find_counter_example(
            a.fork(rng),
            _inner,
            inner_generators,
            0,
            replays=[s.Replay(0, 0, replay)],
        )
        return True

    outer = s.find_counter_example(rng, _outer, {"x": g.ints()}, attempts)
    return outer.labels == {"outer": attempts}


spec = conj(
    _integer_boundary,
    _evaluation_count,
    _float_boundary,
    _stops,
    _list_minimal,
    _always_holds,
    _discards,
    _assume_discards,
    _assume_shrinks,
    _deadline,
    _deadline_discards,
    _deadline_limit,
    _shrink_deadline,
    _announce,
    _exception,
    _failure_kind,
    _reproducible,
    _labels,
    _labels_discarded,
    _labels_shrinking,
    _labels_nested,
    _labels_outside,
    _cover_range,
    _cover_records,
    _cover_conflict,
    _labels_deadline,
    _path,
    _path_failures,
    _replays,
    _replay_labels,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
