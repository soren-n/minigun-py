from returns.maybe import Maybe

from . import (
    arbitrary as a,
    generate as g
)

def slice[T](
    generator: g.Generator[T],
    max_width: int,
    max_depth: int,
    state: a.State
    ) -> tuple[a.State, Maybe[list[T]]]: ...
