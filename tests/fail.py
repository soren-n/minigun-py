from typing import List
from minigun.specify import prop, neg, conj, check

@prop('bool value not equal to negated value')
def _fail_bool_neg_eq(a: bool):
    return a == (not a)

@prop('int add and mul are not associative')
def _fail_int_add_mul_assoc(a: int, b: int, c: int):
    return c * (a + b) == (c * a) + b

@prop('list reverse does not distribute with concatenate')
def _fail_list_reverse_conc_dist(xs : List[int], ys : List[int]):
    return (
        list(reversed(xs + ys)) ==
        list(reversed(xs)) + list(reversed(ys))
    )

if __name__ == '__main__':
    import sys
    success = check(conj(
        neg(_fail_bool_neg_eq),
        neg(_fail_int_add_mul_assoc),
        neg(_fail_list_reverse_conc_dist)
    ))
    sys.exit(0 if success else -1)