# External imports
import io
import sys
import types
import typing
from typing import Any, get_args, get_origin


###############################################################################
# Output encoding helpers
###############################################################################
def relax_stdout_errors() -> None:
    """Make stdout escape unencodable characters instead of raising.

    On Windows, redirected output (pipes, CI logs, files) is encoded
    with the legacy ANSI code page, which cannot represent every
    character a generated value - and therefore a counterexample - may
    contain. Reporting a failure must not crash the run that found it,
    so strict streams are switched to backslash-escaping, which keeps
    the exact codepoints visible.
    """
    stream = sys.stdout
    if isinstance(stream, io.TextIOWrapper) and stream.errors == "strict":
        stream.reconfigure(errors="backslashreplace")


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
