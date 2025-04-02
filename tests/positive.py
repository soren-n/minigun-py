from typing import TypeVar, Callable, Tuple, List, Dict

from minigun.specify import Spec, prop, context, check, conj
import minigun.domain as d
import minigun.order as o
import minigun.maybe as m

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
    name: str,
    value_domain: d.Domain[T],
    operator: Operator[T]
    ) -> Spec:
    @context(value_domain, value_domain)
    @prop('%s is commutative' % name)
    def _operator_commute_impl(a: T, b: T):
        return operator(a, b) == operator(b, a)
    return _operator_commute_impl

def _operator_assoc(
    name: str,
    value_domain: d.Domain[T],
    operator: Operator[T]
    ) -> Spec:
    @context(value_domain, value_domain, value_domain)
    @prop('%s is associative' % name)
    def _operator_assoc_impl(a: T, b: T, c: T):
        return operator(a, operator(b, c)) == operator(operator(a, b), c)
    return _operator_assoc_impl

def _operator_identity(
    name: str,
    identity: T,
    value_domain: d.Domain[T],
    operator: Operator[T]
    ) -> Spec:
    @context(value_domain)
    @prop('\"%s\" is identity under %s' % (identity, name))
    def _operator_neutral_impl(a: T):
        return operator(a, identity) == a
    return _operator_neutral_impl

def _operator_inverse(
    name: str,
    identity: T,
    value_domain: d.Domain[T],
    operator: Operator[T],
    inverse: Inverse[T]
    ) -> Spec:
    @context(value_domain)
    @prop('Domain has inverse under %s' % name)
    def _operator_inverse_impl(a: T):
        return operator(a, inverse(a)) == identity
    return _operator_inverse_impl

def _operators_dist(
    plus_name: str,
    times_name: str,
    value_domain: d.Domain[T],
    plus: Operator[T],
    times: Operator[T]
    ) -> Spec:
    @context(value_domain, value_domain, value_domain)
    @prop('%s and %s are distributive' % (plus_name, times_name))
    def _operators_dist_impl(a: T, b: T, c: T):
        return (
            (times(a, plus(b, c)) == plus(times(a, b), times(a, c))) and
            (times(plus(b, c), a) == plus(times(b, a), times(c, a)))
        )
    return _operators_dist_impl

def _operator_moniod(
    name: str,
    identity: T,
    value_domain: d.Domain[T],
    operator: Operator[T]
    ) -> Spec:
    return conj(
        _operator_identity(name, identity, value_domain, operator),
        _operator_assoc(name, value_domain, operator)
    )

def _operator_abelian(
    name: str,
    identity: T,
    value_domain: d.Domain[T],
    operator: Operator[T],
    inverse: Inverse[T]
    ) -> Spec:
    return conj(
        _operator_identity(name, identity, value_domain, operator),
        _operator_inverse(name, identity, value_domain, operator, inverse),
        _operator_assoc(name, value_domain, operator),
        _operator_commute(name, value_domain, operator)
    )

def _operators_ring(
    plus_name: str,
    times_name: str,
    plus_identity: T,
    times_identity: T,
    value_domain: d.Domain[T],
    plus: Operator[T],
    times: Operator[T],
    inverse: Inverse[T]
    ) -> Spec:
    return conj(
        _operator_abelian(
            plus_name,
            plus_identity,
            value_domain,
            plus,
            inverse
        ),
        _operator_moniod(times_name, times_identity, value_domain, times),
        _operators_dist(plus_name, times_name, value_domain, plus, times)
    )

###############################################################################
# Positive black-box testing of integer
###############################################################################
_int_ring = _operators_ring(
    'integer addition',
    'integer multiplication',
    0, 1, d.int(),
    lambda a, b: a + b,
    lambda a, b: a * b,
    lambda a: -a
)

###############################################################################
# Positive black-box testing of float
###############################################################################
def float_equal(a: float, b: float, epsilon: float = 1e-8) -> bool:
    return abs(a - b) <= epsilon

@context(d.float())
@prop('Zero is neutral element of float addition')
def _pos_black_float_add_zero(a: float) -> bool:
    return float_equal(a + 0, a)

@context(d.float())
@prop('One is neutral element of float multiplication')
def _pos_black_float_mul_one(a: float) -> bool:
    return float_equal(a * 1, a)

@context(d.float(), d.float())
@prop('Float addition is commutative')
def _pos_black_float_add_commute(a: float, b: float) -> bool:
    return float_equal(a + b, b + a)

@context(d.float(), d.float(), d.float())
@prop('Float addition is associative')
def _pos_black_float_add_assoc(
    a: float,
    b: float,
    c: float
    ) -> bool:
    return float_equal(a + (b + c), (a + b) + c)

@context(d.float())
@prop('Float addition has inverse')
def _pos_black_float_add_inverse(a: float) -> bool:
    return float_equal(a + (-a), 0.0)

@context(d.float(), d.float())
@prop('Float multiplication is commutative')
def _pos_black_float_mul_commute(a: float, b: float) -> bool:
    return float_equal(a * b, b * a)

###############################################################################
# Positive black-box testing of str
###############################################################################
_string_concat_moniod = _operator_moniod(
    'string concatenation',
    '', d.str(),
    lambda a, b: a + b
)

@context(d.str())
@prop('String append length identity')
def _pos_black_str_append_length_identity(s: str) -> bool:
    s1 = s + 'a'
    return len(s1) == len(s) + 1

@context(d.str(), d.str())
@prop('String concat length distribute')
def _pos_black_str_concat_length_dist(
    xs: str,
    ys: str
    ) -> bool:
    return len(xs + ys) == len(xs) + len(ys)

###############################################################################
# Positive black-box testing of lists
###############################################################################
_list_concat_moniod = _operator_moniod(
    'list concatenation',
    [], d.list(d.int()),
    lambda a, b: a + b
)

@context(d.list(d.int()), d.int())
@prop('List append identity')
def _pos_black_list_append_identity(
    xs: List[int],
    x: int
    ) -> bool:
    xs.append(x)
    return xs[-1] == x

@context(d.list(d.int()), d.int())
@prop('List append length identity')
def _pos_black_list_append_length_identity(
    xs: List[int],
    x: int
    ) -> bool:
    xs1 = xs.copy()
    xs1.append(x)
    return len(xs1) == len(xs) + 1

@context(d.list(d.int()), d.int())
@prop('List remove identity')
def _pos_black_list_remove_identity(
    xs: List[int],
    x: int
    ) -> bool:
    xs1 = xs.copy()
    xs1.append(x)
    del xs1[-1]
    return xs == xs1

@context(d.list(d.int()), d.int())
@prop('List remove length identity')
def _pos_black_list_remove_length_identity(
    xs: List[int],
    x: int
    ) -> bool:
    xs.append(x)
    xs1 = xs.copy()
    del xs1[-1]
    return len(xs1) == len(xs) - 1

@context(d.list(d.int()), d.list(d.int()))
@prop('List length concat distributes with add')
def _pos_black_list_concat_length_add_dist(
    xs: List[int],
    ys: List[int]
    ) -> bool:
    return len(xs + ys) == len(xs) + len(ys)

@context(d.list(d.int(), ordered = o.int))
@prop('Ordered list items are sorted')
def _pos_black_list_sorted(xs: List[int]) -> bool:
    if len(xs) == 0: return True
    return all([ xs[i] <= xs[i+1] for i in range(len(xs)-1) ])

###############################################################################
# Positive black-box testing of dictionaries
###############################################################################
@context(d.dict(d.int(), d.int()), d.int(), d.int())
@prop('Dictionary insert identity')
def _pos_black_dict_insert_identity(
    kvs: Dict[int, int],
    k: int,
    v: int
    ) -> bool:
    kvs[k] = v
    return kvs[k] == v

@context(d.dict(d.int(), d.int()), d.int(), d.int())
@prop('Dictionary remove identity')
def _pos_black_dict_remove_identity(
    kvs: Dict[int, int],
    k: int,
    v: int
    ) -> bool:
    kvs[k] = v
    del kvs[k]
    return k not in kvs

###############################################################################
# Positive white-box testing of infer
###############################################################################
@prop('Domain infer int')
def _pos_white_domain_infer_int(v: int) -> bool:
    return type(v) == int

@prop('Domain infer float')
def _pos_white_domain_infer_float(v: float) -> bool:
    return type(v) == float

@prop('Domain infer string')
def _pos_white_domain_infer_str(v: str) -> bool:
    return type(v) == str

@prop('Domain infer tuple')
def _pos_white_domain_infer_tuple(v: Tuple[int]) -> bool:
    return type(v) == tuple

@prop('Domain infer list')
def _pos_white_domain_infer_list(bs: List[int]) -> bool:
    return type(bs) == list

@prop('Domain infer dict')
def _pos_white_domain_infer_dict(kvs: Dict[int, int]) -> bool:
    return type(kvs) == dict

@prop('Domain inter maybe')
def _pos_white_domain_infer_maybe(mi: m.Maybe[int]) -> bool:
    return m.is_maybe(type(mi))

###############################################################################
# Running test suite
###############################################################################
def test():
    return check(conj(
        _int_ring,
        _pos_black_float_add_zero,
        _pos_black_float_mul_one,
        _pos_black_float_add_commute,
        _pos_black_float_add_assoc,
        _pos_black_float_add_inverse,
        _pos_black_float_mul_commute,
        _string_concat_moniod,
        _pos_black_str_append_length_identity,
        _pos_black_str_concat_length_dist,
        _list_concat_moniod,
        _pos_black_list_append_identity,
        _pos_black_list_append_length_identity,
        _pos_black_list_remove_identity,
        _pos_black_list_remove_length_identity,
        _pos_black_list_concat_length_add_dist,
        _pos_black_list_sorted,
        _pos_black_dict_insert_identity,
        _pos_black_dict_remove_identity,
        _pos_white_domain_infer_int,
        _pos_white_domain_infer_float,
        _pos_white_domain_infer_str,
        _pos_white_domain_infer_tuple,
        _pos_white_domain_infer_list,
        _pos_white_domain_infer_dict,
        _pos_white_domain_infer_maybe
    ))

if __name__ == '__main__':
    import sys
    success = test()
    sys.exit(0 if success else -1)