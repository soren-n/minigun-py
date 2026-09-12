"""A test module: a file exporting a module-level ``spec``."""

from minigun.specify import conj, prop


@prop("Length distributes over concatenation via addition")
def _list_len_concat_add_dist(xs: list[int], ys: list[int]) -> bool:
    return len(xs + ys) == len(xs) + len(ys)


spec = conj(_list_len_concat_add_dist)
