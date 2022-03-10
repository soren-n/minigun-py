# External module dependencies
from dataclasses import dataclass
from typing import (
    overload,
    Any,
    TypeVar,
    Generic,
    Tuple,
    List,
    Dict,
    Set
)

# Internal module dependencies
from . import generate as g
from . import pretty as p
from . import maybe as m

###############################################################################
# Localizing intrinsics
###############################################################################
_Bool = bool
_Int = int
_Float = float
_Str = str

###############################################################################
# Domain
###############################################################################
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
D = TypeVar('D')

@dataclass
class Domain(Generic[A]):
    """A domain datatype over a type `A`.

    :param generate: A generator over a type `A`.
    :type generate: `minigun.generate.Generator[A]`
    :param print: A printer over a type `A`.
    :type print: `minigun.pretty.Printer[A]`
    """
    generate: g.Generator[A]
    print: p.Printer[A]

###############################################################################
# Boolean
###############################################################################
def bool():
    """A domain for booleans.

    :return: A domain of bool.
    :rtype: `Domain[bool]`
    """
    return Domain(
        g.bool(),
        p.bool()
    )

###############################################################################
# Numbers
###############################################################################
def small_nat() -> Domain[_Int]:
    """A domain for integers :code:`n` in the range :code:`0 <= n <= 100`.

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.small_nat(),
        p.int()
    )

def nat() -> Domain[_Int]:
    """A domain for integers :code:`n` in the range :code:`0 <= n <= 10000`.

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.nat(),
        p.int()
    )

def big_nat() -> Domain[_Int]:
    """A domain for integers :code:`n` in the range :code:`0 <= n <= 1000000`.

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.big_nat(),
        p.int()
    )

def small_int() -> Domain[_Int]:
    """A domain for integers :code:`n` in the range :code:`-100 <= n <= 100`.

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.small_int(),
        p.int()
    )

def int() -> Domain[_Int]:
    """A domain for integers :code:`n` in the range :code:`-10000 <= n <= 10000`.

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.int(),
        p.int()
    )

def big_int() -> Domain[_Int]:
    """A domain for integers :code:`n` in the range :code:`-1000000 <= n <= 1000000`.

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.big_int(),
        p.int()
    )

def float() -> Domain[_Float]:
    """A domain for floats :code:`n` in the range :code:`-e^15 <= n <= e^15`.

    :return: A domain of float.
    :rtype: `Domain[float]`
    """
    return Domain(
        g.float(),
        p.float()
    )

###############################################################################
# Ranges
###############################################################################
def int_range(
    lower_bound : _Int,
    upper_bound : _Int
    ) -> Domain[_Int]:
    """A domain for indices :code:`i` in the range :code:`lower_bound <= i <= upper_bound`.

    :param lower_bound: A min bound for the sampled value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the sampled value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`

    :return: A domain of int.
    :rtype: `Domain[int]`
    """
    return Domain(
        g.int_range(lower_bound, upper_bound),
        p.int()
    )

###############################################################################
# Strings
###############################################################################
def bounded_str(
    lower_bound : _Int,
    upper_bound : _Int,
    alphabet : _Str
    ) -> Domain[_Str]:
    """A domain for strings over a given alphabet with bounded length :code:`l` in the range :code:`lower_bound <= l <= upper_bound`.

    :param lower_bound: A min bound for the length of the sampled value, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the length of the sampled value, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param alphabet: A string representing the alphabet to be sampled from.
    :type alphabet: `str`

    :return: A domain of str.
    :rtype: `Domain[str]`
    """
    return Domain(
        g.bounded_str(lower_bound, upper_bound, alphabet),
        p.str()
    )

def str() -> Domain[_Str]:
    """A domain for strings over all printable ascii characters.

    :return: A domain of str.
    :rtype: `Domain[str]`
    """
    return Domain(
        g.str(),
        p.str()
    )

def word() -> Domain[_Str]:
    """A domain for strings over ascii alphabet characters.

    :return: A domain of str.
    :rtype: `Domain[str]`
    """
    return Domain(
        g.word(),
        p.str()
    )

###############################################################################
# Tuples
###############################################################################
@overload
def tuple() -> Domain[Tuple[()]]: ...
@overload
def tuple(
    a_domain: Domain[A]
    ) -> Domain[Tuple[A]]: ...
@overload
def tuple(
    a_domain: Domain[A],
    b_domain: Domain[B]
    ) -> Domain[Tuple[A, B]]: ...
@overload
def tuple(
    a_domain: Domain[A],
    b_domain: Domain[B],
    c_domain: Domain[C]
    ) -> Domain[Tuple[A, B, C]]: ...
@overload
def tuple(
    a_domain: Domain[A],
    b_domain: Domain[B],
    c_domain: Domain[C],
    d_domain: Domain[D]
    ) -> Domain[Tuple[A, B, C, D]]: ...
def tuple(*domains: Domain[Any]) -> Domain[Tuple[Any, ...]]:
    """A domain of tuples over given value generators of type `A`, `B`, etc.

    :param domains: Value domains over types `A`, `B`, etc. to generate tuple values from.
    :type domain: `Tuple[Domain[A], Domain[B], ...]`

    :return: A domain of tuples over types `A`, `B`, etc.
    :rtype: `Domain[Tuple[A, B, ...]]`
    """
    return Domain(
        g.tuple(*[domain.generate for domain in domains]),
        p.tuple(*[domain.print for domain in domains])
    )

###############################################################################
# List
###############################################################################
def bounded_list(
    lower_bound : _Int,
    upper_bound : _Int,
    domain : Domain[A],
    unique : _Bool = False,
    ordered : _Bool = False
    ) -> Domain[List[A]]:
    """A domain for lists over a given type `A` with bounded length :code:`l` in the range :code:`0 <= lower_bound <= l <= upper_bound`.

    :param lower_bound: A min bound for the length of the sampled list, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the length of the sampled list, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param domain: A value domain from which list items are samples.
    :type domain: `Domain[A]`
    :param unique: Flag for whether items of sampled lists should be unique.
    :type unique: `bool` (default: `False`)
    :param ordering: Flag for whether items of sampled lists should be ordered.
    :type ordering: `bool` (default: `False`)

    :return: A domain of lists over type `A`.
    :rtype: `Domain[List[A]]`
    """
    return Domain(
        g.bounded_list(
            lower_bound,
            upper_bound,
            domain.generate,
            unique,
            ordered
        ),
        p.list(domain.print)
    )

def list(
    domain : Domain[A],
    unique : _Bool = False,
    ordered : _Bool = False
    ) -> Domain[List[A]]:
    """A domain for lists over a given type `A`.

    :param domain: A value domain from which list items are samples.
    :type domain: `Domain[A]`
    :param unique: Flag for whether items of sampled lists should be unique.
    :type unique: `bool` (default: `False`)
    :param ordering: Flag for whether items of sampled lists should be ordered`.
    :type ordering: `bool` (default: `False`)

    :return: A domain of lists over type `A`.
    :rtype: `Domain[List[A]]`
    """
    return Domain(
        g.list(
            domain.generate,
            unique,
            ordered
        ),
        p.list(domain.print)
    )

###############################################################################
# Dictionary
###############################################################################
K = TypeVar('K')
V = TypeVar('V')
def bounded_dict(
    lower_bound : _Int,
    upper_bound : _Int,
    key_domain : Domain[K],
    value_domain : Domain[V]
    ) -> Domain[Dict[K, V]]:
    """A domain for dicts over a given key type `K` and value type `V` with bounded size :code:`s` in the range :code:`0 <= lower_bound <= s <= upper_bound`.

    :param lower_bound: A min bound for the size of the sampled dict, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the size of the sampled dict, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param key_domain: A key domain from which dict keys are samples.
    :type key_domain: `Domain[K]`
    :param value_domain: A value domain from which dict values are samples.
    :type value_domain: `Domain[V]`

    :return: A domain of dicts over key type `K` and value type `V`.
    :rtype: `Domain[Dict[K, V]]`
    """
    return Domain(
        g.bounded_dict(
            lower_bound,
            upper_bound,
            key_domain.generate,
            value_domain.generate
        ),
        p.dict(
            key_domain.print,
            value_domain.print
        )
    )

def dict(
    key_domain : Domain[K],
    value_domain : Domain[V]
    ) -> Domain[Dict[K, V]]:
    """A domain for dicts over a given key type `K` and value type `V`.

    :param key_domain: A key domain from which dict keys are samples.
    :type key_domain: `Domain[K]`
    :param value_domain: A value domain from which dict values are samples.
    :type value_domain: `Domain[V]`

    :return: A domain of dicts over key type `K` and value type `V`.
    :rtype: `Domain[Dict[K, V]]`
    """
    return Domain(
        g.dict(
            key_domain.generate,
            value_domain.generate
        ),
        p.dict(
            key_domain.print,
            value_domain.print
        )
    )

###############################################################################
# Sets
###############################################################################
def bounded_set(
    lower_bound : _Int,
    upper_bound : _Int,
    domain : Domain[A]
    ) -> Domain[Set[A]]:
    """A domain for sets over a given type `A` with bounded size :code:`s` in the range :code:`0 <= lower_bound <= s <= upper_bound`.

    :param lower_bound: A min bound for the size of the sampled set, must be less than or equal to `upper_bound`.
    :type lower_bound: `int`
    :param upper_bound: A max bound for the size of the sampled set, must be greater than or equal to `lower_bound`.
    :type upper_bound: `int`
    :param domain: A value domain from which set items are samples.
    :type domain: `Domain[A]`

    :return: A domain of sets over type `A`.
    :rtype: `Domain[Set[A]]`
    """
    return Domain(
        g.bounded_set(
            lower_bound,
            upper_bound,
            domain.generate
        ),
        p.set(domain.print)
    )

def set(domain : Domain[A]) -> Domain[Set[A]]:
    """A domain for sets over a given type `A`.

    :param domain: A value domain from which set items are samples.
    :type domain: `Domain[A]`

    :return: A domain of sets over type `A`.
    :rtype: `Domain[Set[A]]`
    """
    return Domain(
        g.set(domain.generate),
        p.set(domain.print)
    )

###############################################################################
# Maybe
###############################################################################
def maybe(
    domain : Domain[A]
    ) -> Domain[m.Maybe[A]]:
    """A domain of maybe over a given type `A`.

    :param domain: A value domain to map maybe over.
    :type domain: `Domain[A]`

    :return: A domain of maybe over type `A`.
    :rtype: `Domain[minigun.maybe.Maybe[A]]`
    """
    return Domain(
        g.maybe(domain.generate),
        p.maybe(domain.print)
    )