"""Properties of the counterexample search and shrinking."""

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
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
