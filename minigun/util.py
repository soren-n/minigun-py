# External imports
from typing import Any, get_origin

from returns.maybe import (
    Maybe,
    Nothing,
    Some,
)


###############################################################################
# Helpers for maybe
###############################################################################
def is_maybe(T: type[Any]) -> bool:
    origin = get_origin(T)
    if origin is not None:
        return origin is Maybe
    if T is type(Nothing):
        return True
    if T is Some:
        return True
    return False
