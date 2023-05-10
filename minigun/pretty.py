# External module dependencies
import typeset as ts
from typing import (
    get_origin,
    get_args,
    TypeVar,
    Callable,
    Tuple,
    Any,
    List,
    Dict,
    Set
)

# Internal module dependencies
from . import maybe as m

###############################################################################
# Localizing intrinsics
###############################################################################
_Bool = bool
_Int = int
_Float = float
_Str = str
_Tuple = tuple
_List = list
_Dict = dict
_Set = set

###############################################################################
# Printer
###############################################################################
A = TypeVar('A')

#: Printer datatype defined over a type parameter `A`.
Printer = Callable[[A], ts.Layout]

def render(layout : ts.Layout) -> _Str:
    return ts.render(ts.compile(layout), 2, 80)

###############################################################################
# Boolean
###############################################################################
def bool() -> Printer[_Bool]:
    """Create a printer for values of type bool.

    :return: A printer for values of type bool.
    :rtype: `Printer[bool]`
    """
    def _printer(value):
        return ts.text('True' if value else 'False')
    return _printer

###############################################################################
# Numbers
###############################################################################
def int() -> Printer[_Int]:
    """Create a printer for values of type int.

    :return: A printer for values of type int.
    :rtype: `Printer[int]`
    """
    def _printer(value):
        return ts.text('%d' % value)
    return _printer

def float(digits: _Int = 2) -> Printer[_Float]:
    """Create a printer for values of type float.

    :param digits: The number of digits to print by the float printer.
    :type digits: `int`

    :return: A printer for values of type float.
    :rtype: `Printer[float]`
    """

    assert digits >= 0, 'Parameter digits must be a positive integer'
    _format = '%%.%df' % digits

    def _printer(value):
        return ts.text(_format % value)
    return _printer

###############################################################################
# Strings
###############################################################################
def str() -> Printer[_Str]:
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
    ) -> Printer[Tuple[Any, ...]]:
    """Create a printer of tuples over given value printers of type `A`, `B`, etc.

    :param printers: Value printers over types `A`, `B`, etc. to print tuple values with.
    :type printers: `Tuple[Printer[A], Printer[B], ...]`

    :return: A printer of tuples over types `A`, `B`, etc.
    :rtype: `Printer[Tuple[A, B, ...]]`
    """
    def _printer(value):
        def _wrap(body): return ts.parse('"(" & {0} & ")"', body)
        def _print(item): return item[0](item[1])
        if len(value) == 0: return ts.text('()')
        items = zip(printers, value)
        body = _print(next(items))
        for item in items:
            body = ts.parse('{0} !& "," + {1}', body, _print(item))
        return _wrap(body)
    return _printer

###############################################################################
# Lists
###############################################################################
def list(
    printer: Printer[A]
    ) -> Printer[List[A]]:
    """Create a printer for lists over a given type `A`.

    :param printer: A value printer with which list items are printed.
    :type printer: `Printer[A]`

    :return: A printer of lists over type `A`.
    :rtype: `Printer[List[A]]`
    """
    def _printer(values):
        def _wrap(body): return ts.parse('"[" & {0} & "]"', body)
        if len(values) == 0: return ts.text('[]')
        body = printer(values[0])
        for value in values[1:]:
            body = ts.parse('{0} !& "," + {1}', body, printer(value))
        return _wrap(body)
    return _printer

###############################################################################
# Dicts
###############################################################################
K = TypeVar('K')
V = TypeVar('V')
def dict(
    key_printer: Printer[K],
    value_printer: Printer[V]
    ) -> Printer[Dict[K, V]]:
    """Create a printer for dicts over a given key type `K` and value type `V`.

    :param key_printer: A key printer with which dict keys are printed.
    :type key_printer: `Printer[K]`
    :param value_printer: A value printer with which dict values are printed.
    :type value_printer: `Printer[V]`

    :return: A printer of dicts over key type `K` and value type `V`.
    :rtype: `Printer[Dict[K, V]]`
    """
    def _printer(values):
        def _wrap(body): return ts.parse('"{" & {0} & "}"', body)
        def _item(item):
            return ts.parse(
                '{0} !+ ":" !+ {1}',
                key_printer(item[0]),
                value_printer(item[1])
            )
        if len(values) == 0: return ts.text('{}')
        items = values.items()
        body = _item(next(items))
        for item in items:
            body = ts.parse('{0} !& "," + {1}', body, _item(item))
        return _wrap(body)
    return _printer

###############################################################################
# Sets
###############################################################################
def set(
    printer: Printer[A]
    ) -> Printer[Set[A]]:
    """Create a printer for sets over a given type `A`.

    :param printer: A value printer with which set items are printed.
    :type generator: `Printer[A]`

    :return: A printer of sets over type `A`.
    :rtype: `Printer[Set[A]]`
    """
    def _printer(values):
        def _wrap(body): return ts.parse('"{" & {0} & "}"', body)
        if len(values) == 0: return ts.text('{}')
        items = list(values)
        body = printer(items[0])
        for item in items[1:]:
            body = ts.parse('{0} !& "," + {1}', body, printer(item))
        return _wrap(body)
    return _printer

###############################################################################
# Maybe
###############################################################################
def maybe(
    printer: Printer[A]
    ) -> Printer[m.Maybe[A]]:
    """Create a printer of maybe over a given type `A`.

    :param printer: A value printer with which maybe values are printed.
    :type printer: `Printer[A]`

    :return: A printer of maybe over type `A`.
    :rtype: `Printer[minigun.maybe.Maybe[A]]`
    """
    def _printer(maybe):
        match maybe:
            case m.Nothing(): return ts.text('Nothing()')
            case m.Something(value):
                return ts.parse(
                    '"Something(" & {0} & ")"',
                    printer(value)
                )
    return _printer

###############################################################################
# Infer a printer
###############################################################################
def infer(T: type) -> m.Maybe[Printer[Any]]:
    """Infer a printer of type `T` for a given type `T`.

    :param T: A type to infer a printer of.
    :type T: `type`

    :return: A maybe of printer of type T.
    :rtype: `minigun.maybe.Maybe[Printer[T]]`
    """
    def _maybe(T: type) -> m.Maybe[Printer[Any]]:
        item_printer = infer(get_args(T)[0])
        if isinstance(item_printer, m.Nothing): return m.Nothing()
        return m.Something(maybe(item_printer.value))
    def _tuple(T: type) -> m.Maybe[Printer[Any]]:
        item_printers : List[Printer[Any]] = []
        for item_T in get_args(T):
            item_printer = infer(item_T)
            if isinstance(item_printer, m.Nothing): return m.Nothing()
            item_printers.append(item_printer.value)
        return m.Something(tuple(*item_printers))
    def _list(T: type) -> m.Maybe[Printer[Any]]:
        item_printer = infer(get_args(T)[0])
        if isinstance(item_printer, m.Nothing): return m.Nothing()
        return m.Something(list(item_printer.value))
    def _dict(T: type) -> m.Maybe[Printer[Any]]:
        key_printer = infer(get_args(T)[0])
        if isinstance(key_printer, m.Nothing): return m.Nothing()
        value_printer = infer(get_args(T)[1])
        if isinstance(value_printer, m.Nothing): return m.Nothing()
        return m.Something(dict(key_printer.value, value_printer.value))
    def _set(T: type) -> m.Maybe[Printer[Any]]:
        item_printer = infer(get_args(T)[0])
        if isinstance(item_printer, m.Nothing): return m.Nothing()
        return m.Something(set(item_printer.value))
    if T == _Bool: return m.Something(bool())
    if T == _Int: return m.Something(int())
    if T == _Float: return m.Something(float())
    if T == _Str: return m.Something(str())
    if m.is_maybe(T): return _maybe(T)
    origin = get_origin(T)
    if origin != None:
        if origin == _Tuple: return _tuple(T)
        if origin == _List: return _list(T)
        if origin == _Dict: return _dict(T)
        if origin == _Set: return _set(T)
    return m.Nothing()