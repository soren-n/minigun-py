from typing import Tuple, List, Dict

from minigun.quantify import (
    integer_range,
    list_of,
    dict_of,
    one_of,
    small_natural,
    integer,
    real,
    text
)
from minigun.testing import Suite, test, domain

# The testing strategy for minigun is to exercise the bundled domains.
# This will cover the following four areas of testing for each domain:
#   - Positive black-box testing
#       (Expected outcome of specified interaction with interface)
#       (Historically referred to as property-based testing)
#   - Negative black-box testing
#       (Expected outcome of unspecified interaction with interface)
#       (Historically referred to as fuzzing)
#   - Positive white-box testing
#       (Expected outcome of specified interaction with interface using
#       implementation knowledge)
#   - Negative white-box testing
#       (Expected outcome of unspecified interaction with interface using
#       implementation knowledge)

###############################################################################
# Positive black-box testing of integer
###############################################################################
@test('Zero is neutral element of integer addition', 1000)
@domain(integer())
def _pos_black_int_add_zero(a : int):
    return (a + 0) == a

@test('One is neutral element of integer multiplication', 1000)
@domain(integer())
def _pos_black_int_mul_one(a : int):
    return (a * 1) == a

@test('Integer addition is commutative', 1000)
@domain(integer(), integer())
def _pos_black_int_add_commute(a : int, b : int):
    return (a + b) == (b + a)

@test('Integer addition is associative', 1000)
@domain(integer(), integer(), integer())
def _pos_black_int_add_assoc(a : int, b : int, c : int):
    return (a + (b + c)) == ((a + b) + c)

@test('Integer addition has inverse', 1000)
@domain(integer())
def _pos_black_int_add_inverse(a : int):
    return (a + (-a)) == 0

@test('Integer multiplication is commutative', 1000)
@domain(integer(), integer())
def _pos_black_int_mul_commute(a : int, b : int):
    return (a * b) == (b * a)

@test('Integer multiplication is associative', 1000)
@domain(integer(), integer(), integer())
def _pos_black_int_mul_assoc(a : int, b : int, c : int):
    return (a * (b * c)) == ((a * b) * c)

@test('Integer addition and multiplication is distributive', 1000)
@domain(integer(), integer(), integer())
def _pos_black_int_add_mul_dist(a : int, b : int, c : int):
    return (a * (b + c)) == ((a * b) + (a * c))

###############################################################################
# Positive black-box testing of real
###############################################################################
def float_equal(a : float, b : float, epsilon : float = 1e-8):
    return abs(a - b) <= epsilon

@test('Zero is neutral element of float addition', 1000)
@domain(real())
def _pos_black_float_add_zero(a : float):
    return float_equal(a + 0, a)

@test('One is neutral element of float multiplication', 1000)
@domain(real())
def _pos_black_float_mul_one(a : float):
    return float_equal(a * 1, a)

@test('Float addition is commutative', 1000)
@domain(real(), real())
def _pos_black_float_add_commute(a : float, b : float):
    return float_equal(a + b, b + a)

@test('Float addition is associative', 1000)
@domain(real(), real(), real())
def _pos_black_float_add_assoc(a : float, b : float, c : float):
    return float_equal(a + (b + c), (a + b) + c)

@test('Float addition has inverse', 1000)
@domain(real())
def _pos_black_float_add_inverse(a : float):
    return float_equal(a + (-a), 0.0)

@test('Float multiplication is commutative', 1000)
@domain(real(), real())
def _pos_black_float_mul_commute(a : float, b : float):
    return float_equal(a * b, b * a)

###############################################################################
# Positive black-box testing of text
###############################################################################
@test('String append identity', 1000)
@domain(text())
def _pos_black_text_append_identity(s : str):
    s1 = s + 'a'
    return s1[-1] == 'a'

@test('String append length identity', 1000)
@domain(text())
def _pos_black_text_append_length_identity(s : str):
    s1 = s + 'a'
    return len(s1) == len(s) + 1

@test('String prepend identity', 1000)
@domain(text())
def _pos_black_text_prepend_identity(s : str):
    s1 = 'a' + s
    return s1[0] == 'a'

@test('String prepend length identity', 1000)
@domain(text())
def _pos_black_text_prepend_length_identity(s : str):
    s1 = 'a' + s
    return len(s1) == len(s) + 1

@test('String concat length distribute', 1000)
@domain(text(), text())
def _pos_black_text_concat_length_dist(xs : str, ys : str):
    return len(xs + ys) == len(xs) + len(ys)

###############################################################################
# Positive black-box testing of lists
###############################################################################
@test('List append identity', 1000)
@domain(list_of(integer()), integer())
def _pos_black_list_append_identity(xs : List[int], x : int):
    xs.append(x)
    return xs[-1] == x

@test('List append length identity', 1000)
@domain(list_of(integer()), integer())
def _pos_black_list_append_length_identity(xs : List[int], x : int):
    xs1 = xs.copy()
    xs1.append(x)
    return len(xs1) == len(xs) + 1

@test('List remove identity', 1000)
@domain(list_of(integer()), integer())
def _pos_black_list_remove_identity(xs : List[int], x : int):
    xs1 = xs.copy()
    xs1.append(x)
    del xs1[-1]
    return xs == xs1

@test('List remove length identity', 1000)
@domain(list_of(integer()), integer())
def _pos_black_list_remove_length_identity(xs : List[int], x : int):
    xs.append(x)
    xs1 = xs.copy()
    del xs1[-1]
    return len(xs1) == len(xs) - 1

@test('List length concat distributes with add', 1000)
@domain(list_of(integer()), list_of(integer()))
def _pos_black_list_concat_length_add_dist(xs : List[int], ys : List[int]):
    return len(xs + ys) == len(xs) + len(ys)

###############################################################################
# Positive black-box testing of dictionaries
###############################################################################
@test('Dictionary insert identity', 1000)
@domain(dict_of(integer(), integer()), integer(), integer())
def _pos_black_dict_insert_identity(kvs : Dict[int, int], k : int, v : int):
    kvs[k] = v
    return kvs[k] == v

@test('Dictionary remove identity', 1000)
@domain(dict_of(integer(), integer()), integer(), integer())
def _pos_black_dict_remove_identity(kvs : Dict[int, int], k : int, v : int):
    kvs[k] = v
    del kvs[k]
    return k not in kvs

###############################################################################
# Positive white-box testing of domain combinators
###############################################################################
@test('One of combinator', 1000)
@domain(one_of([small_natural(), integer_range(0, 1000)]))
def _pos_white_one_of_bounds(v : int):
    return 0 <= v <= 1000

###############################################################################
# Positive white-box testing of infer
###############################################################################
@test('Domain infer int', 1)
@domain()
def _pos_white_domain_infer_int(v : int):
    return type(v) == int

@test('Domain infer float', 1)
@domain()
def _pos_white_domain_infer_float(v : float):
    return type(v) == float

@test('Domain infer string', 1)
@domain()
def _pos_white_domain_infer_str(v : str):
    return type(v) == str

@test('Domain infer tuple', 1)
@domain()
def _pos_white_domain_infer_tuple(v : Tuple[int]):
    return type(v) == tuple

@test('Domain infer list', 1)
@domain()
def _pos_white_domain_infer_list(bs : List[int]):
    return type(bs) == list

@test('Domain infer dict', 1)
@domain()
def _pos_white_domain_infer_dict(kvs : Dict[int, int]):
    return type(kvs) == dict

###############################################################################
# Running test suite
###############################################################################
if __name__ == '__main__':
    import sys
    tests = Suite(
        _pos_black_int_add_zero,
        _pos_black_int_mul_one,
        _pos_black_int_add_commute,
        _pos_black_int_add_assoc,
        _pos_black_int_add_inverse,
        _pos_black_int_mul_commute,
        _pos_black_int_mul_assoc,
        _pos_black_int_add_mul_dist,
        _pos_black_float_add_zero,
        _pos_black_float_mul_one,
        _pos_black_float_add_commute,
        _pos_black_float_add_assoc,
        _pos_black_float_add_inverse,
        _pos_black_float_mul_commute,
        _pos_black_text_append_identity,
        _pos_black_text_append_length_identity,
        _pos_black_text_prepend_identity,
        _pos_black_text_prepend_length_identity,
        _pos_black_text_concat_length_dist,
        _pos_black_list_append_identity,
        _pos_black_list_append_length_identity,
        _pos_black_list_remove_identity,
        _pos_black_list_remove_length_identity,
        _pos_black_list_concat_length_add_dist,
        _pos_black_dict_insert_identity,
        _pos_black_dict_remove_identity,
        _pos_white_one_of_bounds,
        _pos_white_domain_infer_int,
        _pos_white_domain_infer_float,
        _pos_white_domain_infer_str,
        _pos_white_domain_infer_tuple,
        _pos_white_domain_infer_list,
        _pos_white_domain_infer_dict,
    )
    success = tests.evaluate(sys.argv)
    sys.exit(0 if success else -1)