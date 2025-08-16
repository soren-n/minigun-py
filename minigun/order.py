# External module dependencies
from collections.abc import Callable, Iterator
from enum import Enum

###############################################################################
# Total order
###############################################################################


class Total(Enum):
    Eq = "Eq"
    Lt = "Lt"
    Gt = "Gt"


#: A function defining a total order over a type `T`
type Order[T] = Callable[[T, T], Total]

###############################################################################
# Localizing builtins
###############################################################################
from builtins import float as _float
from builtins import int as _int
from builtins import str as _str


###############################################################################
# Orders
###############################################################################
def int(left: _int, right: _int) -> Total:
    """A total order over `int`.

    :param left: An instance of `int`.
    :type left: `int`
    :param right: An instance of `int`.
    :type right: `int`

    :return: The total ordering of left and right.
    :rtype: `Total`
    """

    if left == right:
        return Total.Eq
    if left < right:
        return Total.Lt
    return Total.Gt


def float(epsilon: _float) -> Order[_float]:
    """A total order over `float` given a epsilon.

    :param epsilon: An epsilon value to use in modulo comparison.
    :type left: `float`

    :return: A function defining a total order on `float`.
    :rtype: `Order[float]`
    """

    def _compare(left: _float, right: _float) -> Total:
        delta = left - right
        if delta < epsilon:
            return Total.Eq
        if left < right:
            return Total.Lt
        return Total.Gt

    return _compare


def str(left: _str, right: _str) -> Total:
    """A total order over `str`.

    :param left: An instance of `str`.
    :type left: `str`
    :param right: An instance of `str`.
    :type right: `str`

    :return: The total ordering of left and right.
    :rtype: `Total`
    """

    if left == right:
        return Total.Eq
    if left < right:
        return Total.Lt
    return Total.Gt


###############################################################################
# Selection sort using medians of medians
###############################################################################
def sort[T](order: Order[T], items: list[T]) -> list[T]:
    """A sorting function for lists over a given type `T`, using a given total order of the given type `T`.

    :param order: A function defining a total order over the given type `T`.
    :type order: `Order[T]`
    :param items: A list of elements over the given type `T`.
    :type items: `list[T]`

    :return: A sorted list over type `T`.
    :rtype: `list[T]`
    """

    def _median(items: list[T]) -> T:
        def _chunks(items: list[T], size: _int) -> Iterator[list[T]]:
            for offset in range(0, len(items), size):
                yield items[offset : offset + size]

        def _sort2(a: T, b: T) -> tuple[T, T]:
            match order(a, b):
                case Total.Gt:
                    return b, a
                case _:
                    return a, b

        def _sort3(a: T, b: T, c: T) -> tuple[T, T, T]:
            a, b = _sort2(a, b)
            b, c = _sort2(b, c)
            a, b = _sort2(a, b)
            return a, b, c

        def _sort4(a: T, b: T, c: T, d: T) -> tuple[T, T, T, T]:
            a, b, c = _sort3(a, b, c)
            c, d = _sort2(c, d)
            b, c = _sort2(b, c)
            a, b = _sort2(a, b)
            return a, b, c, d

        def _sort5(a: T, b: T, c: T, d: T, e: T) -> tuple[T, T, T, T, T]:
            a, b, c, d = _sort4(a, b, c, d)
            d, e = _sort2(d, e)
            c, d = _sort2(c, d)
            b, c = _sort2(b, c)
            a, b = _sort2(a, b)
            return a, b, c, d, e

        def _brute(chunk: list[T]) -> T:
            match len(chunk):
                case 1:
                    return chunk[0]
                case 2:
                    return _sort2(*chunk)[0]
                case 3:
                    return _sort3(*chunk)[1]
                case 4:
                    return _sort4(*chunk)[1]
                case 5:
                    return _sort5(*chunk)[2]
                case _:
                    raise AssertionError("Invariant")

        while len(items) > 5:
            items = [_brute(chunk) for chunk in _chunks(items, 5)]
        return _brute(items)

    def _partition(items: list[T], pivot: T) -> tuple[list[T], list[T]]:
        xs: list[T] = []
        ys: list[T] = []
        for item in items:
            match order(pivot, item):
                case Total.Eq:
                    continue
                case Total.Lt:
                    ys.append(item)
                case Total.Gt:
                    xs.append(item)
        return xs, ys

    if len(items) <= 1:
        return items
    result: list[T] = []
    stack: list[list[T]] = [items]
    while len(stack) != 0:
        items = stack.pop(-1)
        if len(items) <= 1:
            result += items
            continue
        pivot = _median(items)
        xs, ys = _partition(items, pivot)
        stack.append(ys)
        stack.append(xs)
    return result
