"""Properties of lazy streams, modeled against lists."""

import minigun.generate as g
import minigun.stream as fs
from minigun import check
from minigun.specify import conj, context, prop


@prop("from_list round-trips through to_list")
def _from_to_list(items: list[int], limit: int) -> bool:
    bound = abs(limit)
    return fs.to_list(fs.from_list(items), bound) == items[:bound]


@prop("map agrees with the list model")
def _map_model(items: list[int]) -> bool:
    stream = fs.map(lambda x: x * 2, fs.from_list(items))
    return fs.to_list(stream, len(items)) == [x * 2 for x in items]


@prop("filter agrees with the list model")
def _filter_model(items: list[int]) -> bool:
    stream = fs.filter(lambda x: x % 2 == 0, fs.from_list(items))
    return fs.to_list(stream, len(items)) == [x for x in items if x % 2 == 0]


@prop("concat agrees with list concatenation")
def _concat_model(xs: list[int], ys: list[int]) -> bool:
    stream = fs.concat(fs.from_list(xs), fs.from_list(ys))
    return fs.to_list(stream, len(xs) + len(ys)) == xs + ys


@prop("braid interleaves round-robin")
def _braid_model(xs: list[int], ys: list[int]) -> bool:
    expected: list[int] = []
    for index in range(max(len(xs), len(ys))):
        if index < len(xs):
            expected.append(xs[index])
        if index < len(ys):
            expected.append(ys[index])
    stream = fs.braid(fs.from_list(xs), fs.from_list(ys))
    return fs.to_list(stream, len(expected)) == expected


@prop("prepend and append place values at the ends")
def _prepend_append(items: list[int], head: int, tail: int) -> bool:
    stream = fs.append(fs.prepend(head, fs.from_list(items)), tail)
    return fs.to_list(stream, len(items) + 2) == [head, *items, tail]


@context(g.int_range(0, 50))
@prop("unfold agrees with a countdown model")
def _unfold_model(count: int) -> bool:
    def _step(n: int) -> tuple[int, int] | None:
        return None if n == 0 else (n, n - 1)

    stream = fs.unfold(_step, count)
    return fs.to_list(stream, count + 5) == list(range(count, 0, -1))


@context(g.ints(), g.int_range(0, 50))
@prop("constant repeats its value indefinitely")
def _constant_model(value: int, count: int) -> bool:
    return fs.to_list(fs.constant(value), count) == [value] * count


@context(g.int_range(0, 30), g.int_range(0, 30))
@prop("streams compute exactly the values consumed")
def _lazy(count: int, taken: int) -> bool:
    calls = 0

    def _observe(x: int) -> int:
        nonlocal calls
        calls += 1
        return x

    stream = fs.map(_observe, fs.from_list(list(range(count))))
    if calls != 0:
        return False
    fs.to_list(stream, taken)
    return calls == min(count, taken)


@prop("streams are re-traversable")
def _reiterable(items: list[int]) -> bool:
    stream = fs.map(lambda x: x + 1, fs.from_list(items))
    return fs.to_list(stream, len(items)) == fs.to_list(stream, len(items))


spec = conj(
    _from_to_list,
    _map_model,
    _filter_model,
    _concat_model,
    _braid_model,
    _prepend_append,
    _unfold_model,
    _constant_model,
    _lazy,
    _reiterable,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
