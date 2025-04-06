from typing import Any, Callable

from returns.maybe import Maybe

from . import (
    arbitrary as a,
    generate as g
)

def find_counter_example[**P](
    state: a.State,
    attempts: int,
    law: Callable[P, bool],
    generators: dict[str, g.Generator[Any]]
    ) -> tuple[a.State, Maybe[dict[str, Any]]]: ...
