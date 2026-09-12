"""Basic usage: one law, one property, one check."""

import minigun.generate as g
from minigun import check
from minigun.specify import context, prop


# -- start: property --
@context(g.lists(g.ints()), g.lists(g.ints()))
@prop("Length distributes over concatenation via addition")
def _list_len_concat_add_dist(xs: list[int], ys: list[int]) -> bool:
    return len(xs + ys) == len(xs) + len(ys)


# -- end: property --

spec = _list_len_concat_add_dist

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
