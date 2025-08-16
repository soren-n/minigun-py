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
    if origin is None:
        if T is type(Nothing):
            return True
        return T is Some
    return origin is Maybe
