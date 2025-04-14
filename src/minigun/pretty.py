# External module dependencies
import typeset as ts
from returns.maybe import (
    Maybe,
    Nothing,
    Some
)
from typing import (
    get_origin,
    get_args,
    Callable,
    Any
)

# Internal module dependencies
from . import util as u

###############################################################################
# Localizing builtins
###############################################################################
from builtins import (
    bool as _bool,
    int as _int,
    float as _float,
    str as _str,
    dict as _dict,
    list as _list,
    set as _set,
    tuple as _tuple
)

###############################################################################
# Printer
###############################################################################

#: Printer datatype defined over a type parameter `A`.
type Printer[T] = Callable[[T], ts.Layout]

def render(layout: ts.Layout) -> _str:
    return ts.render(ts.compile(layout), 2, 80)

###############################################################################
# Boolean
###############################################################################
def bool() -> Printer[_bool]:
    """Create a printer for values of type bool.

    :return: A printer for values of type bool.
    :rtype: `Printer[bool]`
    """
    def _printer(value: _bool) -> ts.Layout:
        return ts.text('True' if value else 'False')
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
        return ts.text('%d' % value)
    return _printer

def float(digits: _int = 2) -> Printer[_float]:
    """Create a printer for values of type float.

    :param digits: The number of digits to print by the float printer.
    :type digits: `int`

    :return: A printer for values of type float.
    :rtype: `Printer[float]`
    """

    assert digits >= 0, 'Parameter digits must be a positive integer'
    _format = '%%.%df' % digits

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
def tuple(
    *printers: Printer[Any]
    ) -> Printer[_tuple[Any, ...]]:
    """Create a printer of tuples over given value printers of type `A`, `B`, etc.

    :param printers: Value printers over types `A`, `B`, etc. to print tuple values with.
    :type printers: `tuple[Printer[A], Printer[B], ...]`

    :return: A printer of tuples over types `A`, `B`, etc.
    :rtype: `Printer[Tuple[A, B, ...]]`
    """
    def _printer(value: _tuple[Any, ...]) -> ts.Layout:
        def _wrap(body: ts.Layout) -> ts.Layout:
            return ts.parse('"(" & {0} & ")"', body)
        def _print(printer: Printer[Any], value: Any) -> ts.Layout:
            return printer(value)
        if len(value) == 0: return ts.text('()')
        items = zip(printers, value)
        body = _print(*next(items))
        for item in items:
            body = ts.parse('{0} !& "," + {1}', body, _print(*item))
        return _wrap(body)
    return _printer

###############################################################################
# Lists
###############################################################################
def list[T](
    printer: Printer[T]
    ) -> Printer[_list[T]]:
    """Create a printer for lists over a given type `A`.

    :param printer: A value printer with which list items are printed.
    :type printer: `Printer[T]`

    :return: A printer of lists over type `A`.
    :rtype: `Printer[List[T]]`
    """
    def _printer(values: _list[T]) -> ts.Layout:
        def _wrap(body: ts.Layout) -> ts.Layout:
            return ts.parse('"[" & {0} & "]"', body)
        if len(values) == 0: return ts.text('[]')
        body = printer(values[0])
        for value in values[1:]:
            body = ts.parse('{0} !& "," + {1}', body, printer(value))
        return _wrap(body)
    return _printer

###############################################################################
# Dicts
###############################################################################
def dict[K, V](
    key_printer: Printer[K],
    value_printer: Printer[V]
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
        def _wrap(body: ts.Layout) -> ts.Layout:
            return ts.parse('"{" & {0} & "}"', body)
        def _item(key: K, value: V) -> ts.Layout:
            return ts.parse(
                '{0} !+ ":" !+ {1}',
                key_printer(key),
                value_printer(value)
            )
        if len(values) == 0: return ts.text('{}')
        items = iter(_list(values.items()))
        body = _item(*next(items))
        for item in items:
            body = ts.parse(
                '{0} !& "," + {1}',
                body, _item(*item)
            )
        return _wrap(body)
    return _printer

###############################################################################
# Sets
###############################################################################
def set[T](
    printer: Printer[T]
    ) -> Printer[_set[T]]:
    """Create a printer for sets over a given type `A`.

    :param printer: A value printer with which set items are printed.
    :type generator: `Printer[T]`

    :return: A printer of sets over type `A`.
    :rtype: `Printer[Set[T]]`
    """
    def _printer(values: _set[T]) -> ts.Layout:
        def _wrap(body: ts.Layout) -> ts.Layout:
            return ts.parse('"{" & {0} & "}"', body)
        if len(values) == 0: return ts.text('{}')
        items = _list(values)
        body = printer(items[0])
        for item in items[1:]:
            body = ts.parse('{0} !& "," + {1}', body, printer(item))
        return _wrap(body)
    return _printer

###############################################################################
# Maybe
###############################################################################
def maybe[T](
    printer: Printer[T]
    ) -> Printer[Maybe[T]]:
    """Create a printer of maybe over a given type `A`.

    :param printer: A value printer with which maybe values are printed.
    :type printer: `Printer[T]`

    :return: A printer of maybe over type `A`.
    :rtype: `Printer[returns.maybe.Maybe[T]]`
    """
    def _printer(maybe: Maybe[T]) -> ts.Layout:
        match maybe:
            case Maybe.empty:
                return ts.text('Nothing')
            case Some(value):
                return ts.parse(
                    '"Something(" & {0} & ")"',
                    printer(value)
                )
            case _: assert False, 'Invariant'
    return _printer

###############################################################################
# Argument pack
###############################################################################
def argument_pack(
    ordering: _list[_str],
    printers: _dict[_str, Printer[Any]]
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
        def _wrap(body: ts.Layout) -> ts.Layout:
            return ts.parse('seq ("{" & nest {0} & "}")', body)
        def _item(param: _str) -> ts.Layout:
            arg = args[param]
            arg_printer = printers[param]
            return ts.parse(
                'fix ("\\"" & {0} & "\\":") + {1}',
                param_printer(param),
                arg_printer(arg)
            )
        params = iter(ordering)
        body = _item(next(params))
        for param in params:
            body = ts.parse(
                '{0} !& "," + {1}',
                body, _item(param)
            )
        return _wrap(body)
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
                case Maybe.empty: return Nothing
                case Some(item_printer):
                    item_printers.append(item_printer)
                case _: assert False, 'Invariant'
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
            case _: assert False, 'Invariant'
    def _case_set(T: type) -> Maybe[Printer[Any]]:
        return infer(get_args(T)[0]).map(set)
    if T == _bool: return Some(bool())
    if T == _int: return Some(int())
    if T == _float: return Some(float())
    if T == _str: return Some(str())
    if u.is_maybe(T): return _case_maybe(T)
    origin = get_origin(T)
    if origin != None:
        if origin == _tuple: return _case_tuple(T)
        if origin == _list: return _case_list(T)
        if origin == _dict: return _case_dict(T)
        if origin == _set: return _case_set(T)
    return Nothing