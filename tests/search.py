"""Properties of the counterexample search and shrinking."""

import math
import random
import time

import minigun.arbitrary as a
import minigun.generate as g
import minigun.search as s
from minigun import check
from minigun.specify import conj, context, prop


@context(g.int_range(1, 500), g.int_range(500, 10000))
@prop("integer counterexamples shrink to the exact boundary")
def _integer_boundary(threshold: int, upper: int, rng: random.Random) -> bool:
    search = s.find_counter_example(
        rng, lambda x: x < threshold, {"x": g.int_range(0, upper)}, 200
    )
    if search.counter_example is None:
        return False
    return search.counter_example.args == {"x": threshold}


@context(g.int_range(1, 500), g.int_range(500, 10000))
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


@prop("an expired deadline stops the search after one attempt")
def _deadline(rng: random.Random) -> bool:
    search = s.find_counter_example(
        rng, lambda x: True, {"x": g.ints()}, 100, deadline=time.perf_counter()
    )
    return search.attempts == 1 and search.counter_example is None


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
    _list_minimal,
    _always_holds,
    _discards,
    _deadline,
    _exception,
    _failure_kind,
    _reproducible,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
