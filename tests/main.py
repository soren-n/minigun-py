from typing import TypeVar, Callable, Tuple, List, Dict

from minigun.testing import Spec, prop, domain, check, conj
import minigun.quantify as q

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
# Abstract specifications
###############################################################################
T = TypeVar('T')
Operator = Callable[[T, T], T]
Inverse = Callable[[T], T]

def _operator_commute(
    name : str,
    sampler : q.Sampler[T],
    operator : Operator[T]
    ) -> Spec:
    @prop('%s is commutative' % name, 100)
    @domain(sampler, sampler)
    def _operator_commute_impl(a : T, b : T):
        return operator(a, b) == operator(b, a)
    return _operator_commute_impl

def _operator_assoc(
    name : str,
    sampler : q.Sampler[T],
    operator : Operator[T]
    ) -> Spec:
    @prop('%s is associative' % name, 100)
    @domain(sampler, sampler, sampler)
    def _operator_assoc_impl(a : T, b : T, c : T):
        return operator(a, operator(b, c)) == operator(operator(a, b), c)
    return _operator_assoc_impl

def _operator_identity(
    name : str,
    identity : T,
    sampler : q.Sampler[T],
    operator : Operator[T]
    ) -> Spec:
    @prop('\"%s\" is identity under %s' % (identity, name), 100)
    @domain(sampler)
    def _operator_neutral_impl(a : T):
        return operator(a, identity) == a
    return _operator_neutral_impl

def _operator_inverse(
    name : str,
    identity : T,
    sampler : q.Sampler[T],
    operator : Operator[T],
    inverse : Inverse[T]
    ) -> Spec:
    @prop('Domain has inverse under %s' % name, 100)
    @domain(sampler)
    def _operator_inverse_impl(a : T):
        return operator(a, inverse(a)) == identity
    return _operator_inverse_impl

def _operators_dist(
    plus_name : str,
    times_name : str,
    sampler : q.Sampler[T],
    plus : Operator[T],
    times : Operator[T]
    ) -> Spec:
    @prop('%s and %s are distributive' % (plus_name, times_name), 100)
    @domain(sampler, sampler, sampler)
    def _operators_dist_impl(a : T, b : T, c : T):
        return (
            (times(a, plus(b, c)) == plus(times(a, b), times(a, c))) and
            (times(plus(b, c), a) == plus(times(b, a), times(c, a)))
        )
    return _operators_dist_impl

def _operator_moniod(
    name : str,
    identity : T,
    sampler : q.Sampler[T],
    operator : Operator[T]
    ) -> Spec:
    return conj(
        _operator_identity(name, identity, sampler, operator),
        _operator_assoc(name, sampler, operator)
    )

def _operator_abelian(
    name : str,
    identity : T,
    sampler : q.Sampler[T],
    operator : Operator[T],
    inverse : Inverse[T]
    ) -> Spec:
    return conj(
        _operator_identity(name, identity, sampler, operator),
        _operator_inverse(name, identity, sampler, operator, inverse),
        _operator_assoc(name, sampler, operator),
        _operator_commute(name, sampler, operator)
    )

def _operators_ring(
    plus_name : str,
    times_name : str,
    plus_identity : T,
    times_identity : T,
    sampler : q.Sampler[T],
    plus : Operator[T],
    times : Operator[T],
    inverse : Inverse[T]
    ) -> Spec:
    return conj(
        _operator_abelian(plus_name, plus_identity, sampler, plus, inverse),
        _operator_moniod(times_name, times_identity, sampler, times),
        _operators_dist(plus_name, times_name, sampler, plus, times)
    )

###############################################################################
# Positive black-box testing of integer
###############################################################################
_int_ring = _operators_ring(
    'integer addition',
    'integer multiplication',
    0, 1, q.integer(),
    lambda a, b: a + b,
    lambda a, b: a * b,
    lambda a: -a
)

###############################################################################
# Positive black-box testing of real
###############################################################################
def float_equal(a : float, b : float, epsilon : float = 1e-8) -> bool:
    return abs(a - b) <= epsilon

@prop('Zero is neutral element of float addition', 100)
@domain(q.real())
def _pos_black_float_add_zero(a : float) -> bool:
    return float_equal(a + 0, a)

@prop('One is neutral element of float multiplication', 100)
@domain(q.real())
def _pos_black_float_mul_one(a : float) -> bool:
    return float_equal(a * 1, a)

@prop('Float addition is commutative', 100)
@domain(q.real(), q.real())
def _pos_black_float_add_commute(a : float, b : float) -> bool:
    return float_equal(a + b, b + a)

@prop('Float addition is associative', 100)
@domain(q.real(), q.real(), q.real())
def _pos_black_float_add_assoc(
    a : float,
    b : float,
    c : float
    ) -> bool:
    return float_equal(a + (b + c), (a + b) + c)

@prop('Float addition has inverse', 100)
@domain(q.real())
def _pos_black_float_add_inverse(a : float) -> bool:
    return float_equal(a + (-a), 0.0)

@prop('Float multiplication is commutative', 100)
@domain(q.real(), q.real())
def _pos_black_float_mul_commute(a : float, b : float) -> bool:
    return float_equal(a * b, b * a)

###############################################################################
# Positive black-box testing of text
###############################################################################
_string_concat_moniod = _operator_moniod(
    'string concatenation',
    '', q.text(),
    lambda a, b: a + b
)

@prop('String append length identity', 100)
@domain(q.text())
def _pos_black_text_append_length_identity(s : str) -> bool:
    s1 = s + 'a'
    return len(s1) == len(s) + 1

@prop('String concat length distribute', 100)
@domain(q.text(), q.text())
def _pos_black_text_concat_length_dist(
    xs : str,
    ys : str
    ) -> bool:
    return len(xs + ys) == len(xs) + len(ys)

###############################################################################
# Positive black-box testing of lists
###############################################################################
_list_concat_moniod = _operator_moniod(
    'list concatenation',
    [], q.list_of(q.integer()),
    lambda a, b: a + b
)

@prop('List append identity', 100)
@domain(q.list_of(q.integer()), q.integer())
def _pos_black_list_append_identity(
    xs : List[int],
    x : int
    ) -> bool:
    xs.append(x)
    return xs[-1] == x

@prop('List append length identity', 100)
@domain(q.list_of(q.integer()), q.integer())
def _pos_black_list_append_length_identity(
    xs : List[int],
    x : int
    ) -> bool:
    xs1 = xs.copy()
    xs1.append(x)
    return len(xs1) == len(xs) + 1

@prop('List remove identity', 100)
@domain(q.list_of(q.integer()), q.integer())
def _pos_black_list_remove_identity(
    xs : List[int],
    x : int
    ) -> bool:
    xs1 = xs.copy()
    xs1.append(x)
    del xs1[-1]
    return xs == xs1

@prop('List remove length identity', 100)
@domain(q.list_of(q.integer()), q.integer())
def _pos_black_list_remove_length_identity(
    xs : List[int],
    x : int
    ) -> bool:
    xs.append(x)
    xs1 = xs.copy()
    del xs1[-1]
    return len(xs1) == len(xs) - 1

@prop('List length concat distributes with add', 100)
@domain(q.list_of(q.integer()), q.list_of(q.integer()))
def _pos_black_list_concat_length_add_dist(
    xs : List[int],
    ys : List[int]
    ) -> bool:
    return len(xs + ys) == len(xs) + len(ys)

@prop('Unique list have no duplicate items', 100)
@domain(q.list_of(q.integer(), unique = True))
def _pos_black_list_unique(xs : List[int]) -> bool:
    xs1 = set(xs)
    return len(xs1.difference(xs)) == 0

@prop('Ordered list items are sorted', 100)
@domain(q.list_of(q.integer(), ordering = (lambda x : x)))
def _pos_black_list_sorted(xs : List[int]) -> bool:
    if len(xs) == 0: return True
    return all([ xs[i] <= xs[i+1] for i in range(len(xs)-1) ])

###############################################################################
# Positive black-box testing of dictionaries
###############################################################################
@prop('Dictionary insert identity', 100)
@domain(q.dict_of(q.integer(), q.integer()), q.integer(), q.integer())
def _pos_black_dict_insert_identity(
    kvs : Dict[int, int],
    k : int,
    v : int
    ) -> bool:
    kvs[k] = v
    return kvs[k] == v

@prop('Dictionary remove identity', 100)
@domain(q.dict_of(q.integer(), q.integer()), q.integer(), q.integer())
def _pos_black_dict_remove_identity(
    kvs : Dict[int, int],
    k : int,
    v : int
    ) -> bool:
    kvs[k] = v
    del kvs[k]
    return k not in kvs

###############################################################################
# Positive white-box testing of domain combinators
###############################################################################
@prop('One of combinator', 100)
@domain(q.one_of([q.small_natural(), q.integer_range(0, 100)]))
def _pos_white_one_of_bounds(v : int) -> bool:
    return 0 <= v <= 100

###############################################################################
# Positive white-box testing of infer
###############################################################################
@prop('Domain infer int', 1)
@domain()
def _pos_white_domain_infer_int(v : int) -> bool:
    return type(v) == int

@prop('Domain infer float', 1)
@domain()
def _pos_white_domain_infer_float(v : float) -> bool:
    return type(v) == float

@prop('Domain infer string', 1)
@domain()
def _pos_white_domain_infer_str(v : str) -> bool:
    return type(v) == str

@prop('Domain infer tuple', 1)
@domain()
def _pos_white_domain_infer_tuple(v : Tuple[int]) -> bool:
    return type(v) == tuple

@prop('Domain infer list', 1)
@domain()
def _pos_white_domain_infer_list(bs : List[int]) -> bool:
    return type(bs) == list

@prop('Domain infer dict', 1)
@domain()
def _pos_white_domain_infer_dict(kvs : Dict[int, int]) -> bool:
    return type(kvs) == dict

###############################################################################
# Running test suite
###############################################################################
if __name__ == '__main__':
    import sys
    success = check(conj(
        _int_ring,
        _pos_black_float_add_zero,
        _pos_black_float_mul_one,
        _pos_black_float_add_commute,
        _pos_black_float_add_assoc,
        _pos_black_float_add_inverse,
        _pos_black_float_mul_commute,
        _string_concat_moniod,
        _pos_black_text_append_length_identity,
        _pos_black_text_concat_length_dist,
        _list_concat_moniod,
        _pos_black_list_append_identity,
        _pos_black_list_append_length_identity,
        _pos_black_list_remove_identity,
        _pos_black_list_remove_length_identity,
        _pos_black_list_concat_length_add_dist,
        _pos_black_list_unique,
        _pos_black_list_sorted,
        _pos_black_dict_insert_identity,
        _pos_black_dict_remove_identity,
        _pos_white_one_of_bounds,
        _pos_white_domain_infer_int,
        _pos_white_domain_infer_float,
        _pos_white_domain_infer_str,
        _pos_white_domain_infer_tuple,
        _pos_white_domain_infer_list,
        _pos_white_domain_infer_dict,
    ))
    sys.exit(0 if success else -1)