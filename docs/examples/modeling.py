"""Modeling: programs over a stack interface, evaluated against a model."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial

import minigun.arbitrary as a
import minigun.cardinality as c
import minigun.generate as g
import minigun.shrink as s
import minigun.stream as fs
from minigun import check
from minigun.specify import context, prop


# -- start: model --
def model_init[T]() -> list[T]:
    return []


def model_push[T](stack: list[T], item: T) -> list[T]:
    return [*stack, item]


def model_pop[T](stack: list[T]) -> tuple[list[T], T]:
    return stack[:-1], stack[-1]


# -- end: model --


# -- start: programs --
# Every operation makes a new stack version, named so that later
# operations can refer to it.
@dataclass
class InitOp:
    after: str


@dataclass
class PushOp[T]:
    before: str
    after: str
    item: T


@dataclass
class PopOp:
    before: str
    after: str


type StackOp[T] = InitOp | PushOp[T] | PopOp
type StackProg[T] = list[StackOp[T]]
# -- end: programs --


# -- start: generator --
def stack_prog_generator[T](
    value_generator: g.Generator[T], size: int
) -> g.Generator[StackProg[T]]:
    def _trim(prog: StackProg[T]) -> fs.Stream[StackProg[T]]:
        """Drop one operation, later operations first."""

        def _iterate() -> Iterator[StackProg[T]]:
            for index in reversed(range(len(prog))):
                yield prog[:index] + prog[index + 1 :]

        return _iterate

    def _sample(rng: a.Rng) -> s.Dissection[StackProg[T]] | None:
        prog: StackProg[T] = []
        stacks: list[str] = []
        nonempty: list[str] = []
        for fuel in range(size, 0, -1):
            if not stacks and fuel < 2:
                break
            ops = ["init"]
            if stacks:
                ops.append("push")
            if nonempty:
                ops.append("pop")
            after = f"s{len(stacks)}"
            match a.choice(rng, ops):
                case "init":
                    prog.append(InitOp(after))
                case "push":
                    before = a.choice(rng, stacks)
                    dissection = value_generator.sample(rng)
                    if dissection is None:
                        return None
                    prog.append(PushOp(before, after, dissection.head))
                    nonempty.append(after)
                case _:
                    prog.append(PopOp(a.choice(rng, nonempty), after))
            stacks.append(after)
        prog.append(InitOp(f"s{len(stacks)}"))
        return s.unfold(prog, _trim)

    return g.Generator(_sample, c.INFINITE)


def stack_prog[T](value_generator: g.Generator[T]) -> g.Generator[StackProg[T]]:
    return g.bind(
        partial(stack_prog_generator, value_generator), g.small_nats()
    )


# -- end: generator --


# -- start: evaluator --
def evaluate_stack_prog[S, T](
    init: Callable[[], S],
    push: Callable[[S, T], S],
    pop: Callable[[S], tuple[S, T]],
    prog: StackProg[T],
) -> bool:
    """Run a program on the model and the implementation side by side;
    whether every popped item agrees."""
    models: dict[str, list[T]] = {}
    impls: dict[str, S] = {}
    for op in prog:
        match op:
            case InitOp(after):
                models[after] = model_init()
                impls[after] = init()
            case PushOp(before, after, item):
                models[after] = model_push(models[before], item)
                impls[after] = push(impls[before], item)
            case PopOp(before, after):
                models[after], model_item = model_pop(models[before])
                impls[after], impl_item = pop(impls[before])
                if model_item != impl_item:
                    return False
    return True


# -- end: evaluator --


# -- start: property --
def _push[A](xs: list[A], x: A) -> list[A]:
    return [*xs, x]


def _pop[A](xs: list[A]) -> tuple[list[A], A]:
    return xs[:-1], xs[-1]


@context(stack_prog(g.ints()))
@prop("Stack implementation matches model")
def _stack_model(prog: StackProg[int]) -> bool:
    return evaluate_stack_prog(list, _push, _pop, prog)


# -- end: property --

spec = _stack_model

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
