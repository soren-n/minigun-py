"""Properties of shrinkers and dissections."""

import math
import random

import minigun.generate as g
import minigun.shrink as s
import minigun.stream as fs
from minigun import check
from minigun.specify import conj, context, prop
from tests._support import breadth_first


def _between(target: int, value: int, candidate: int) -> bool:
    low, high = min(target, value), max(target, value)
    return low <= candidate <= high


@prop("integer alternatives start at the target and approach the value")
def _integer_order(target: int, value: int) -> bool:
    candidates = [node.head for node in s.integer(target)(value).shrinks()]
    if value == target:
        return candidates == []
    if candidates[0] != target:
        return False
    distances = [abs(value - candidate) for candidate in candidates]
    return (
        all(_between(target, value, candidate) for candidate in candidates)
        and value not in candidates
        and distances == sorted(distances, reverse=True)
        and len(set(candidates)) == len(candidates)
    )


@prop("every node of an integer shrink tree lies between target and root")
def _integer_tree(target: int, value: int) -> bool:
    return all(
        _between(target, value, node.head)
        for node in breadth_first(s.integer(target)(value), 40)
    )


@prop("booleans shrink only from True to False")
def _boolean(value: bool) -> bool:
    candidates = [node.head for node in s.boolean()(value).shrinks()]
    return candidates == ([False] if value else [])


@prop("float alternatives are strictly closer to the target")
def _floating(target: float, value: float) -> bool:
    candidates = [node.head for node in s.floating(target)(value).shrinks()]
    if value == target:
        return candidates == []
    return candidates[0] == target and all(
        abs(candidate - target) < abs(value - target)
        for candidate in candidates
    )


@prop("string alternatives are strictly shorter, emptiest first")
def _string(value: str) -> bool:
    candidates = [node.head for node in s.string()(value).shrinks()]
    if value == "":
        return candidates == []
    lengths = [len(candidate) for candidate in candidates]
    return candidates[0] == "" and all(
        length < len(value) for length in lengths
    )


@context(g.int_range(0, 50), g.int_range(1, 10))
@prop("chunk removals cover every position with descending chunk sizes")
def _chunks(length: int, max_removed: int) -> bool:
    ranges = list(s.chunk_removals(length, max_removed))
    if length == 0:
        return ranges == []
    sizes = [end - start for start, end in ranges]
    return (
        all(0 <= start < end <= length for start, end in ranges)
        and sizes == sorted(sizes, reverse=True)
        and sizes[0] == min(length, max_removed)
        and sizes[-1] == 1
        and {start for start, end in ranges if end - start == 1}
        == set(range(length))
    )


@prop("unfold computes nothing until its children are iterated")
def _unfold_lazy(value: int) -> bool:
    calls = 0

    def _trim(x: int) -> fs.Stream[int]:
        nonlocal calls
        calls += 1
        return fs.from_list([x // 2] if x != 0 else [])

    dissection = s.unfold(value, _trim, _trim)
    if calls != 0:
        return False
    list(dissection.shrinks())
    return calls == 2


@prop("map combines heads and shrinks one argument at a time")
def _map(x: int, y: int) -> bool:
    dissection = s.map(lambda a, b: (a, b), s.integer(0)(x), s.integer(0)(y))
    if dissection.head != (x, y):
        return False
    x_children = len(list(s.integer(0)(x).shrinks()))
    y_children = len(list(s.integer(0)(y).shrinks()))
    children = [node.head for node in dissection.shrinks()]
    return len(children) == x_children + y_children and all(
        (a == x) != (b == y) for a, b in children
    )


@prop("filter keeps only nodes satisfying the predicate")
def _filter(value: int) -> bool:
    filtered = s.filter(lambda v: v % 2 == 0, s.integer(0)(value))
    if value % 2 != 0:
        return filtered is None
    return filtered is not None and all(
        node.head % 2 == 0 for node in breadth_first(filtered, 40)
    )


@prop("prepend, append and singleton shape dissections as documented")
def _shape(value: int, other: int) -> bool:
    single = s.singleton(value)
    prepended = s.prepend(other, single)
    appended = s.append(s.integer(0)(value), other)
    return (
        list(single.shrinks()) == []
        and [node.head for node in prepended.shrinks()] == [value]
        and [node.head for node in appended.shrinks()][-1] == other
    )


@prop("non-finite floats shrink straight to the target")
def _non_finite(rng: random.Random) -> bool:
    value = rng.choice([math.inf, -math.inf, math.nan])
    candidates = [node.head for node in s.floating(0.0)(value).shrinks()]
    return candidates == [0.0]


spec = conj(
    _integer_order,
    _integer_tree,
    _boolean,
    _floating,
    _string,
    _chunks,
    _unfold_lazy,
    _map,
    _filter,
    _shape,
    _non_finite,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
