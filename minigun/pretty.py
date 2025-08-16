# External module dependencies
###############################################################################
# Localizing builtins
###############################################################################
from builtins import bool as _bool
from builtins import dict as _dict
from builtins import float as _float
from builtins import int as _int
from builtins import list as _list
from builtins import set as _set
from builtins import str as _str
from builtins import tuple as _tuple
from collections.abc import Callable
from functools import reduce
from typing import Any, get_args, get_origin

import typeset as ts
from returns.maybe import Maybe, Nothing, Some

# Internal module dependencies
from minigun import util as u

###############################################################################
# Printer
###############################################################################

#: Printer datatype defined over a type parameter `A`.
type Printer[T] = Callable[[T], ts.Layout]


def render(layout: ts.Layout) -> _str:
    return ts.render(ts.compile(layout), 2, 80)


###############################################################################
# Helper functions
###############################################################################


def _delim(*layouts: ts.Layout) -> ts.Layout:
    if len(layouts) == 0:
        return ts.null()
    if len(layouts) == 1:
        return layouts[0]
    return reduce(
        lambda result, layout: ts.parse('{0} !& "," + {1}', result, layout),
        layouts[1:],
        layouts[0],
    )


def _group(layout: ts.Layout) -> ts.Layout:
    return ts.parse('seq ("(" & nest {0} & ")")', layout)


def _scope(layout: ts.Layout) -> ts.Layout:
    return ts.parse('seq ("{" & nest {0} & "}")', layout)


def _box(layout: ts.Layout) -> ts.Layout:
    return ts.parse('seq ("[" & nest {0} & "]")', layout)


###############################################################################
# Boolean
###############################################################################
def bool() -> Printer[_bool]:
    """Create a printer for values of type bool.

    :return: A printer for values of type bool.
    :rtype: `Printer[bool]`
    """

    def _printer(value: _bool) -> ts.Layout:
        return ts.text("True" if value else "False")

    return _printer


###############################################################################
# Numbers
###############################################################################
def int() -> Printer[_int]:
    """Create a printer for values of type int.

    :return: A printer for values of type int.
    :rtype: `Printer[int]`
    """

    def _printer(value: _int) -> ts.Layout:
        return ts.text("%d" % value)

    return _printer


def float(digits: _int = 2) -> Printer[_float]:
    """Create a printer for values of type float.

    :param digits: The number of digits to print by the float printer.
    :type digits: `int`

    :return: A printer for values of type float.
    :rtype: `Printer[float]`
    """

    assert digits >= 0, "Parameter digits must be a positive integer"
    _format = "%%.%df" % digits

    def _printer(value: _float) -> ts.Layout:
        return ts.text(_format % value)

    return _printer


###############################################################################
# Strings
###############################################################################
def str() -> Printer[_str]:
    """Create a printer for values of type str.

    :return: A printer for values of type str.
    :rtype: `Printer[str]`
    """
    return ts.text


###############################################################################
# Tuples
###############################################################################
def tuple(*printers: Printer[Any]) -> Printer[_tuple[Any, ...]]:
    """Create a printer of tuples over given value printers of type `A`, `B`, etc.

    :param printers: Value printers over types `A`, `B`, etc. to print tuple values with.
    :type printers: `tuple[Printer[A], Printer[B], ...]`

    :return: A printer of tuples over types `A`, `B`, etc.
    :rtype: `Printer[Tuple[A, B, ...]]`
    """

    def _printer(values: _tuple[Any, ...]) -> ts.Layout:
        def _apply(printer_value: _tuple[Printer[Any], Any]) -> ts.Layout:
            printer, value = printer_value
            return printer(value)

        if len(values) == 0:
            return ts.text("()")
        return _group(_delim(*map(_apply, zip(printers, values, strict=False))))

    return _printer


###############################################################################
# Lists
###############################################################################
def list[T](printer: Printer[T]) -> Printer[_list[T]]:
    """Create a printer for lists over a given type `A`.

    :param printer: A value printer with which list items are printed.
    :type printer: `Printer[T]`

    :return: A printer of lists over type `A`.
    :rtype: `Printer[List[T]]`
    """

    def _printer(values: _list[T]) -> ts.Layout:
        if len(values) == 0:
            return ts.text("[]")
        return _box(_delim(*map(printer, values)))

    return _printer


###############################################################################
# Dicts
###############################################################################
def dict[K, V](
    key_printer: Printer[K], value_printer: Printer[V]
) -> Printer[_dict[K, V]]:
    """Create a printer for dicts over a given key type `K` and value type `V`.

    :param key_printer: A key printer with which dict keys are printed.
    :type key_printer: `Printer[K]`
    :param value_printer: A value printer with which dict values are printed.
    :type value_printer: `Printer[V]`

    :return: A printer of dicts over key type `K` and value type `V`.
    :rtype: `Printer[Dict[K, V]]`
    """

    def _printer(values: _dict[K, V]) -> ts.Layout:
        def _item(key_value: _tuple[K, V]) -> ts.Layout:
            key, value = key_value
            return ts.parse(
                'grp ({0} !& ":" !+ {1})',
                key_printer(key),
                value_printer(value),
            )

        if len(values) == 0:
            return ts.text("{}")
        return _scope(_delim(*map(_item, values.items())))

    return _printer


###############################################################################
# Sets
###############################################################################
def set[T](printer: Printer[T]) -> Printer[_set[T]]:
    """Create a printer for sets over a given type `A`.

    :param printer: A value printer with which set items are printed.
    :type generator: `Printer[T]`

    :return: A printer of sets over type `A`.
    :rtype: `Printer[Set[T]]`
    """

    def _printer(values: _set[T]) -> ts.Layout:
        if len(values) == 0:
            return ts.text("{}")
        return _scope(_delim(*map(printer, values)))

    return _printer


###############################################################################
# Maybe
###############################################################################
def maybe[T](printer: Printer[T]) -> Printer[Maybe[T]]:
    """Create a printer of maybe over a given type `A`.

    :param printer: A value printer with which maybe values are printed.
    :type printer: `Printer[T]`

    :return: A printer of maybe over type `A`.
    :rtype: `Printer[returns.maybe.Maybe[T]]`
    """

    def _printer(maybe: Maybe[T]) -> ts.Layout:
        match maybe:
            case Maybe.empty:
                return ts.text("Nothing")
            case Some(value):
                return ts.parse(
                    'grp ("Some(" & nest {0} & ")")', printer(value)
                )
            case _:
                raise AssertionError("Invariant")

    return _printer


###############################################################################
# Argument pack
###############################################################################
def argument_pack(
    ordering: _list[_str], printers: _dict[_str, Printer[Any]]
) -> Printer[_dict[_str, Any]]:
    """Create a printer for argument packs`.

    :param ordering: The order of parameters in the argument pack.
    :type ordering: `List[str]`
    :param printers: Value printers with which arguments are printed.
    :type printers: `Dict[str, Printer[Any]]`

    :return: A printer of parameter packs.
    :rtype: `Printer[Dict[str, Any]]`
    """

    def _printer(args: _dict[_str, Any]) -> ts.Layout:
        param_printer = str()

        def _item(param: _str) -> ts.Layout:
            arg = args[param]
            arg_printer = printers[param]
            return ts.parse(
                'grp ("\\"" !& {0} !& "\\":" + {1})',
                param_printer(param),
                arg_printer(arg),
            )

        return _scope(_delim(*map(_item, ordering)))

    return _printer


###############################################################################
# Infer a printer
###############################################################################
def infer(T: type) -> Maybe[Printer[Any]]:
    """Infer a printer of type `T` for a given type `T`.

    :param T: A type to infer a printer of.
    :type T: `type`

    :return: A maybe of printer of type T.
    :rtype: `returns.maybe.Maybe[Printer[T]]`
    """

    def _case_maybe(T: type) -> Maybe[Printer[Any]]:
        return infer(get_args(T)[0]).map(maybe)

    def _case_tuple(T: type) -> Maybe[Printer[Any]]:
        item_printers: _list[Printer[Any]] = []
        for item_T in get_args(T):
            match infer(item_T):
                case Maybe.empty:
                    return Nothing
                case Some(item_printer):
                    item_printers.append(item_printer)
                case _:
                    raise AssertionError("Invariant")
        return Some(tuple(*item_printers))

    def _case_list(T: type) -> Maybe[Printer[Any]]:
        return infer(get_args(T)[0]).map(list)

    def _case_dict(T: type) -> Maybe[Printer[Any]]:
        K, V = get_args(T)[:2]
        match (infer(K), infer(V)):
            case (Some(key_printer), Some(value_printer)):
                return Some(dict(key_printer, value_printer))
            case (Maybe.empty, _) | (_, Maybe.empty):
                return Nothing
            case _:
                raise AssertionError("Invariant")

    def _case_set(T: type) -> Maybe[Printer[Any]]:
        return infer(get_args(T)[0]).map(set)

    # Check for basic types
    match T:
        case x if x is _bool:
            return Some(bool())
        case x if x is _int:
            return Some(int())
        case x if x is _float:
            return Some(float())
        case x if x is _str:
            return Some(str())
        case x if u.is_maybe(x):
            return _case_maybe(x)

    # Check origin-based types
    origin = get_origin(T)
    if origin is None:
        return Nothing

    match origin:
        case x if x is _tuple:
            return _case_tuple(T)
        case x if x is _list:
            return _case_list(T)
        case x if x is _dict:
            return _case_dict(T)
        case x if x is _set:
            return _case_set(T)
        case _:
            return Nothing
