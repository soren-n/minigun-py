"""Composing specifications with conj."""

from minigun import check
from minigun.specify import conj, prop


# -- start: properties --
@prop("Length distributes over concatenation via addition")
def _list_len_concat_add_dist(xs: list[int], ys: list[int]) -> bool:
    return len(xs + ys) == len(xs) + len(ys)


@prop("Reverse distributes over concatenation")
def _list_rev_concat_dist(xs: list[int], ys: list[int]) -> bool:
    return list(reversed(xs + ys)) == list(reversed(ys)) + list(reversed(xs))


spec = conj(_list_len_concat_add_dist, _list_rev_concat_dist)
# -- end: properties --

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
