"""Template specifications: a stack specification instantiated for lists."""

from collections.abc import Callable

import minigun.generate as g
from minigun import check
from minigun.specify import Spec, conj, context, prop


# -- start: template --
def stack[S, A](
    item_generator: g.Generator[A],
    stack_generator: g.Generator[S],
    initial: S,
    length: Callable[[S], int],
    push: Callable[[S, A], S],
    pop: Callable[[S], tuple[A, S]],
) -> Spec:
    @context(g.constant(initial))
    @prop("Initial stack is empty")
    def _initial_empty(s: S) -> bool:
        return length(s) == 0

    @context(stack_generator, item_generator)
    @prop("Stack push increments size")
    def _push_inc(s: S, a: A) -> bool:
        return length(push(s, a)) == length(s) + 1

    @context(stack_generator)
    @prop("Stack pop decrements size")
    def _pop_dec(s: S) -> bool:
        if length(s) == 0:
            return True
        _, s1 = pop(s)
        return length(s) - 1 == length(s1)

    @context(stack_generator, item_generator)
    @prop("Stack push and pop are inverse")
    def _push_pop_inv(s: S, a: A) -> bool:
        b, t = pop(push(s, a))
        return a == b and s == t

    return conj(_initial_empty, _push_inc, _pop_dec, _push_pop_inv)


# -- end: template --


# -- start: instance --
# An implementation of an immutable stack of integers
def _push[A](xs: list[A], x: A) -> list[A]:
    return [*xs, x]


def _pop[A](xs: list[A]) -> tuple[A, list[A]]:
    return xs[-1], xs[:-1]


# A specification for the above implementation
spec = stack(g.ints(), g.lists(g.ints()), [], len, _push, _pop)
# -- end: instance --

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
