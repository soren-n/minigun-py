# External module dependencies
# from typeset import Layout
from typing import (
    get_origin,
    get_args,
    Any,
    TypeVar,
    Callable,
    Tuple,
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

Layout = _Str # DELETE ME WHEN TYPESET IS READY

#: Printer datatype defined over a type parameter `A`.
Printer = Callable[[A], Layout]

def render(layout : Layout) -> _Str:
    return layout

###############################################################################
# Boolean
###############################################################################
def bool() -> Printer[_Bool]:
    """Create a printer for values of type bool.

    :return: A printer for values of type bool.
    :rtype: `Printer[bool]`
    """
    return _Str

###############################################################################
# Numbers
###############################################################################
def int() -> Printer[_Int]:
    """Create a printer for values of type int.

    :return: A printer for values of type int.
    :rtype: `Printer[int]`
    """
    return _Str

def float() -> Printer[_Float]:
    """Create a printer for values of type float.

    :return: A printer for values of type float.
    :rtype: `Printer[float]`
    """
    return _Str

###############################################################################
# Strings
###############################################################################
def str() -> Printer[_Str]:
    """Create a printer for values of type str.

    :return: A printer for values of type str.
    :rtype: `Printer[str]`
    """
    return _Str

###############################################################################
# Lists
###############################################################################
def tuple(
    *printers : Printer[Any]
    ) -> Printer[Tuple[Any, ...]]:
    """Create a printer of tuples over given value printers of type `A`, `B`, etc.

    :param printers: Value printers over types `A`, `B`, etc. to print tuple values with.
    :type printers: `Tuple[Printer[A], Printer[B], ...]`

    :return: A printer of tuples over types `A`, `B`, etc.
    :rtype: `Printer[Tuple[A, B, ...]]`
    """
    return _Str

###############################################################################
# Lists
###############################################################################
def list(
    printer : Printer[A]
    ) -> Printer[List[A]]:
    """Create a printer for lists over a given type `A`.

    :param printer: A value printer with which list items are printed.
    :type printer: `Printer[A]`

    :return: A printer of lists over type `A`.
    :rtype: `Printer[List[A]]`
    """
    return _Str

###############################################################################
# Dicts
###############################################################################
K = TypeVar('K')
V = TypeVar('V')
def dict(
    key_printer : Printer[K],
    value_printer : Printer[V]
    ) -> Printer[Dict[K, V]]:
    """Create a printer for dicts over a given key type `K` and value type `V`.

    :param key_printer: A key printer with which dict keys are printed.
    :type key_printer: `Printer[K]`
    :param value_printer: A value printer with which dict values are printed.
    :type value_printer: `Printer[V]`

    :return: A printer of dicts over key type `K` and value type `V`.
    :rtype: `Printer[Dict[K, V]]`
    """
    return _Str

###############################################################################
# Sets
###############################################################################
def set(
    printer : Printer[A]
    ) -> Printer[Set[A]]:
    """Create a printer for sets over a given type `A`.

    :param printer: A value printer with which set items are printed.
    :type generator: `Printer[A]`

    :return: A printer of sets over type `A`.
    :rtype: `Printer[Set[A]]`
    """
    return _Str

###############################################################################
# Maybe
###############################################################################
def maybe(
    printer : Printer[A]
    ) -> Printer[m.Maybe[A]]:
    """Create a printer of maybe over a given type `A`.

    :param printer: A value printer with which maybe values are printed.
    :type printer: `Printer[A]`

    :return: A printer of maybe over type `A`.
    :rtype: `Printer[minigun.maybe.Maybe[A]]`
    """
    return _Str

###############################################################################
# Infer a printer
###############################################################################
def infer(T : type) -> m.Maybe[Printer[Any]]:
    """Infer a printer of type `T` for a given type `T`.

    :param T: A type to infer a printer of.
    :type T: `type`

    :return: A maybe of printer of type T.
    :rtype: `minigun.maybe.Maybe[Printer[T]]`
    """
    def _tuple(T : type) -> m.Maybe[Printer[Any]]:
        item_printers : List[Printer[Any]] = []
        for item_T in get_args(T):
            item_printer = infer(item_T)
            if isinstance(item_printer, m.Nothing): return m.Nothing()
            item_printers.append(item_printer.value)
        return m.Something(tuple(*item_printers))
    def _list(T : type) -> m.Maybe[Printer[Any]]:
        item_printer = infer(get_args(T)[0])
        if isinstance(item_printer, m.Nothing): return m.Nothing()
        return m.Something(list(item_printer.value))
    def _dict(T : type) -> m.Maybe[Printer[Any]]:
        key_printer = infer(get_args(T)[0])
        if isinstance(key_printer, m.Nothing): return m.Nothing()
        value_printer = infer(get_args(T)[1])
        if isinstance(value_printer, m.Nothing): return m.Nothing()
        return m.Something(dict(key_printer.value, value_printer.value))
    def _set(T : type) -> m.Maybe[Printer[Any]]:
        item_printer = infer(get_args(T)[0])
        if isinstance(item_printer, m.Nothing): return m.Nothing()
        return m.Something(set(item_printer.value))
    if T == _Int: return m.Something(int())
    if T == _Float: return m.Something(float())
    if T == _Str: return m.Something(str())
    origin = get_origin(T)
    if origin != None:
        if origin == _Tuple: return _tuple(T)
        if origin == _List: return _list(T)
        if origin == _Dict: return _dict(T)
        if origin == _Set: return _set(T)
    return m.Nothing()