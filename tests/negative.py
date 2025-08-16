# Internal imports
from minigun.specify import check, conj, neg, prop


###############################################################################
# Negative properties
###############################################################################
@prop("bool value not equal to negated value")
def _fail_bool_neg_eq(a: bool):
    return a == (not a)


@prop("int add and mul are not associative")
def _fail_int_add_mul_assoc(a: int, b: int, c: int):
    return c * (a + b) == (c * a) + b


@prop("list reverse does not distribute with concatenate")
def _fail_list_reverse_conc_dist(xs: list[int], ys: list[int]):
    return list(reversed(xs + ys)) == list(reversed(xs)) + list(reversed(ys))


###############################################################################
# Running test suite
###############################################################################
def test():
    return check(
        conj(
            neg(_fail_bool_neg_eq),
            neg(_fail_int_add_mul_assoc),
            neg(_fail_list_reverse_conc_dist),
        )
    )


if __name__ == "__main__":
    import sys

    success = test()
    sys.exit(0 if success else -1)
