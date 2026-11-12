"""Looking at what the generators produce: labels and coverage."""

import minigun.generate as g
from minigun import check, cover, label
from minigun.specify import conj, context, prop


# -- start: label --
@prop("A deleted key is no longer in the table")
def _delete(key: int, table: dict[int, int]) -> bool:
    label("present" if key in table else "absent")
    table.pop(key, None)
    return key not in table


# -- end: label --


# -- start: cover --
@context(
    g.int_range(0, 9),
    g.bounded_dicts(0, 10, g.int_range(0, 9), g.ints()),
)
@prop("A deleted key is no longer in the table, present or not")
def _delete_covered(key: int, table: dict[int, int]) -> bool:
    cover(0.2, key in table, "present")
    table.pop(key, None)
    return key not in table


# -- end: cover --

spec = conj(_delete, _delete_covered)

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
