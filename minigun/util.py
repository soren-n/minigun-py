# External imports
import types
import typing
from typing import Any, get_args, get_origin


###############################################################################
# Optional type helpers
###############################################################################
def optional_inner(T: type[Any]) -> type[Any] | None:
    """Return the inner type of an optional annotation, or None.

    Recognizes `X | None` and `typing.Optional[X]` annotations with a
    single non-None member.

    :param T: A type annotation.

    :return: The inner type `X` when `T` is `X | None`, otherwise None.
    """
    origin = get_origin(T)
    if origin is not types.UnionType and origin is not typing.Union:
        return None
    args = get_args(T)
    if type(None) not in args:
        return None
    inner = [arg for arg in args if arg is not type(None)]
    if len(inner) != 1:
        return None
    return inner[0]  # type: ignore[no-any-return]
