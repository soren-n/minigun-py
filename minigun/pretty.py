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
# Optional
###############################################################################
def optional[T](printer: Printer[T]) -> Printer[T | None]:
    """Create a printer of optional values over a given type `T`.

    :param printer: A value printer with which present values are printed.
    :type printer: `Printer[T]`

    :return: A printer of optional values over type `T`.
    :rtype: `Printer[T | None]`
    """

    def _printer(value: T | None) -> ts.Layout:
        if value is None:
            return ts.text("None")
        return printer(value)

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
def infer(T: type) -> Printer[Any] | None:
    """Infer a printer of type `T` for a given type `T`.

    :param T: A type to infer a printer of.
    :type T: `type`

    :return: A printer of type T, or None when no printer is known.
    :rtype: `Printer[Any] | None`
    """

    def _case_tuple(T: type) -> Printer[Any] | None:
        item_printers: _list[Printer[Any]] = []
        for item_T in get_args(T):
            item_printer = infer(item_T)
            if item_printer is None:
                return None
            item_printers.append(item_printer)
        return tuple(*item_printers)

    def _case_list(T: type) -> Printer[Any] | None:
        item_printer = infer(get_args(T)[0])
        if item_printer is None:
            return None
        return list(item_printer)

    def _case_dict(T: type) -> Printer[Any] | None:
        K, V = get_args(T)[:2]
        key_printer = infer(K)
        value_printer = infer(V)
        if key_printer is None or value_printer is None:
            return None
        return dict(key_printer, value_printer)

    def _case_set(T: type) -> Printer[Any] | None:
        item_printer = infer(get_args(T)[0])
        if item_printer is None:
            return None
        return set(item_printer)

    # Check for basic types
    if T is _bool:
        return bool()
    if T is _int:
        return int()
    if T is _float:
        return float()
    if T is _str:
        return str()

    inner = u.optional_inner(T)
    if inner is not None:
        inner_printer = infer(inner)
        if inner_printer is None:
            return None
        return optional(inner_printer)

    # Check origin-based types
    match get_origin(T):
        case x if x is _tuple:
            return _case_tuple(T)
        case x if x is _list:
            return _case_list(T)
        case x if x is _dict:
            return _case_dict(T)
        case x if x is _set:
            return _case_set(T)
        case _:
            return None
