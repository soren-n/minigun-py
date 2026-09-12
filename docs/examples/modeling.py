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
@dataclass
class Constant[T]:
    value: T


@dataclass
class Variable:
    name: str


type Value[T] = Constant[T] | Variable


@dataclass
class InitOp:
    after: str


@dataclass
class PushOp[T]:
    before: str
    after: str
    item: Value[T]


@dataclass
class PopOp:
    before: str
    after: str
    item: str


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
            for index in range(len(prog) - 1, -1, -1):
                yield prog[:index] + prog[index + 1 :]

        return _iterate

    def _visit(
        fuel: int,
        rng: a.Rng,
        stack_ctr: int,
        item_ctr: int,
        stacks: list[str],
        nonempty: list[str],
    ) -> StackProg[T] | None:
        if fuel <= 0 or (len(stacks) == 0 and fuel < 2):
            return [InitOp(f"s{stack_ctr}")]
        ops = ["init"]
        if stacks:
            ops.append("push")
        if nonempty:
            ops.append("pop")
        match a.choice(rng, ops):
            case "init":
                name = f"s{stack_ctr}"
                rest = _visit(
                    fuel - 1,
                    rng,
                    stack_ctr + 1,
                    item_ctr,
                    [*stacks, name],
                    nonempty,
                )
                return None if rest is None else [InitOp(name), *rest]
            case "push":
                before = a.choice(rng, stacks)
                after = f"s{stack_ctr}"
                dissection = value_generator.sample(rng)
                if dissection is None:
                    return None
                rest = _visit(
                    fuel - 1,
                    rng,
                    stack_ctr + 1,
                    item_ctr,
                    [*stacks, after],
                    [*nonempty, after],
                )
                if rest is None:
                    return None
                return [PushOp(before, after, Constant(dissection.head)), *rest]
            case _:
                before = a.choice(rng, nonempty)
                after = f"s{stack_ctr}"
                item_name = f"v{item_ctr}"
                rest = _visit(
                    fuel - 1,
                    rng,
                    stack_ctr + 1,
                    item_ctr + 1,
                    [*stacks, after],
                    nonempty,
                )
                if rest is None:
                    return None
                return [PopOp(before, after, item_name), *rest]

    def _sample(rng: a.Rng) -> s.Dissection[StackProg[T]] | None:
        prog = _visit(size, rng, 0, 0, [], [])
        return None if prog is None else s.unfold(prog, _trim)

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
    model_env: dict[str, list[T]] = {}
    impl_env: dict[str, S] = {}
    item_env: dict[str, T] = {}
    for op in prog:
        match op:
            case InitOp(after):
                model_env[after] = model_init()
                impl_env[after] = init()
            case PushOp(before, after, item):
                match item:
                    case Constant(value):
                        val = value
                    case Variable(name):
                        val = item_env[name]
                model_env[after] = model_push(model_env[before], val)
                impl_env[after] = push(impl_env[before], val)
            case PopOp(before, after, item_name):
                m_rest, m_item = model_pop(model_env[before])
                i_rest, i_item = pop(impl_env[before])
                if m_item != i_item:
                    return False
                model_env[after] = m_rest
                impl_env[after] = i_rest
                item_env[item_name] = m_item
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
