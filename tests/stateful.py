"""Properties of stateful testing.

The universal properties of generators (values and shrinks in domain,
determinism, termination, replay) cover ``programs`` through the
``Stateful`` node of the generator model in ``tests._support``; these are
the properties particular to machines and programs.
"""

import random
from typing import Any

import minigun.arbitrary as a
import minigun.cardinality as c
import minigun.generate as g
import minigun.specify as sp
import minigun.stateful as st
from minigun import canonical, check
from minigun.specify import conj, context, prop
from tests._support import (
    Program,
    Stateful,
    breadth_first,
    greedy_leaf,
    member,
    programs,
    stateful_machine,
)

###############################################################################
# A stack with a bug
###############################################################################


class _Stack:
    """A stack that drops every push beyond ``capacity`` items."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.items: list[int] = []

    def push(self, item: int) -> None:
        if len(self.items) < self.capacity:
            self.items.append(item)

    def pop(self) -> int:
        return self.items.pop()

    def size(self) -> int:
        return len(self.items)


def _push(model: tuple[int, ...], item: int) -> tuple[int, ...]:
    return (*model, item)


STACK: st.Machine[tuple[int, ...], _Stack] = st.machine(
    (),
    st.command(
        "push",
        lambda stack, item: stack.push(item),
        arguments=g.int_range(0, 9),
        next_state=_push,
    ),
    st.command(
        "pop",
        lambda stack, _: stack.pop(),
        precondition=lambda model, _: len(model) > 0,
        next_state=lambda model, _: model[:-1],
        postcondition=lambda model, _, result: result == model[-1],
    ),
    st.command(
        "size",
        lambda stack, _: stack.size(),
        postcondition=lambda model, _, result: result == len(model),
    ),
)


def _stack_law(capacity: int) -> sp.Resolved:
    @context(st.programs(STACK))
    @prop("the stack matches its model")
    def _law(program: st.Program[tuple[int, ...], _Stack]) -> bool:
        return program.run(_Stack(capacity))

    return sp.resolve(_law)


@context(g.int_range(1, 3))
@prop("a stack that drops pushes shrinks to a minimal failing program")
def _minimal(capacity: int, seed: int) -> bool:
    outcome = sp.evaluate_property(
        seed, _stack_law(capacity), False, sp.Allowance(2000)
    )
    example = outcome.counter_example
    if example is None:
        return False
    # Shrinking ends at a locally minimal program: it fails, and every
    # program with a step removed that could still run passes. Items
    # need not reach 0: shrinking keeps the kind of failure, and two
    # equal items may only change together for a pop of an empty stack
    # to stay an IndexError.
    program = example.args["program"]
    steps = program.steps

    def _fails(candidate: tuple[Any, ...]) -> bool:
        try:
            st.Program(STACK, candidate).run(_Stack(capacity))
        except (st.ModelMismatch, IndexError):
            return True
        return False

    removed = [steps[:i] + steps[i + 1 :] for i in range(len(steps))]
    runnable = [
        candidate
        for candidate in removed
        if all(
            step.command.name != "pop" or model
            for step, model in zip(
                candidate, st.Program(STACK, candidate).models(), strict=False
            )
        )
    ]
    pushes = [step.args for step in steps if step.command.name == "push"]
    return (
        isinstance(example.exception, (st.ModelMismatch, IndexError))
        and example.minimal
        and _fails(steps)
        and not any(_fails(candidate) for candidate in runnable)
        and len(pushes) > capacity
    )


@prop("a stack that keeps every push matches its model")
def _holds(seed: int) -> bool:
    outcome = sp.evaluate_property(
        seed, _stack_law(10**6), False, sp.Allowance(200)
    )
    return outcome.holds


###############################################################################
# Running programs
###############################################################################


@context(st.programs(STACK), g.int_range(0, 40))
@prop("a run raises at the first step whose result the model rejects")
def _mismatch(
    program: st.Program[tuple[int, ...], _Stack], capacity: int
) -> bool:
    models = program.models()
    stack = _Stack(capacity)
    failing: int | None = None
    raised = False
    for index, step in enumerate(program.steps):
        model = models[index]
        name = step.command.name
        if name == "push":
            stack.push(step.args)
        elif name == "pop":
            # A stack that dropped pushes runs out of items first.
            if not stack.items:
                failing, raised = index, True
                break
            if stack.pop() != model[-1]:
                failing = index
                break
        elif stack.size() != len(model):
            failing = index
            break
    try:
        result = program.run(_Stack(capacity))
    except IndexError:
        return raised
    except st.ModelMismatch as error:
        if failing is None or raised:
            return False
        step = program.steps[failing]
        return f"Step {failing + 1}, {step!r}, returned" in str(
            error
        ) and f"in the model {models[failing]!r}" in str(error)
    return failing is None and result is True


@context(st.programs(STACK))
@prop("models are the initial model followed by each step's next state")
def _models(program: st.Program[tuple[int, ...], _Stack]) -> bool:
    expected: list[tuple[int, ...]] = [()]
    for step in program.steps:
        model = expected[-1]
        name = step.command.name
        if name == "push":
            expected.append((*model, step.args))
        elif name == "pop":
            expected.append(model[:-1])
        else:
            expected.append(model)
    return program.models() == expected


@context(g.int_range(0, 9))
@prop("a run of a step whose precondition fails is a mismatch")
def _precondition(item: int) -> bool:
    push, pop = STACK.commands[0], STACK.commands[1]
    invalid = st.Program(
        STACK, (st.Step(push, item), st.Step(pop, None)) + (st.Step(pop, None),)
    )
    try:
        invalid.run(_Stack(10))
    except st.ModelMismatch as error:
        return "Step 3, pop(), does not meet its precondition" in str(error)
    return False


@context(g.int_range(0, 9))
@prop("an exception the system raises propagates as it is")
def _raises(item: int) -> bool:
    class _Broken(_Stack):
        def push(self, item: int) -> None:
            raise KeyError(item)

    program = st.Program(STACK, (st.Step(STACK.commands[0], item),))
    try:
        program.run(_Broken(10))
    except KeyError as error:
        return error.args == (item,)
    return False


###############################################################################
# Generating and shrinking programs
###############################################################################


def _counting(max_steps: int, rng: random.Random) -> list[int]:
    """The lengths of programs of a machine whose commands always run."""
    always = st.machine(0, st.command("tick", lambda system, _: None))
    generator = st.programs(always, max_steps)
    lengths = []
    for _ in range(200):
        dissection = generator.sample(rng)
        assert dissection is not None
        lengths.append(len(dissection.head))
    return lengths


@context(g.int_range(0, 5))
@prop("program lengths range from empty to the bound")
def _lengths(max_steps: int, rng: random.Random) -> bool:
    # 200 uniform draws of at most six lengths miss one about once in
    # 10^15 runs.
    lengths = _counting(max_steps, rng)
    return set(lengths) == set(range(max_steps + 1))


@context(st.programs(STACK, 0))
@prop("a bound of zero steps draws only the empty program")
def _empty(program: st.Program[tuple[int, ...], _Stack]) -> bool:
    return (
        len(program) == 0
        and repr(program) == "[]"
        and st.programs(STACK, 0).cardinality == c.ONE
        and st.programs(STACK).cardinality == c.INFINITE
    )


@context(g.int_range(1, 10))
@prop("a program ends where no command can run")
def _stuck(max_steps: int, rng: random.Random) -> bool:
    once = st.machine(
        False,
        st.command(
            "once",
            lambda system, _: None,
            precondition=lambda done, _: not done,
            next_state=lambda done, _: True,
        ),
    )
    dissection = st.programs(once, max_steps).sample(rng)
    return dissection is not None and repr(dissection.head) in (
        "[]",
        "[once()]",
    )


@context(programs(), g.int_range(2, 4), g.int_range(1, 8))
@prop("the first shrink of a program is the empty program")
def _first_shrink(
    put: Program, modulus: int, max_steps: int, seed: int
) -> bool:
    model = Stateful((put,), modulus, max_steps)
    dissection = st.programs(stateful_machine(model), max_steps).sample(
        a.seed(seed)
    )
    if dissection is None or len(dissection.head) == 0:
        return True
    first = next(dissection.shrinks(), None)
    return first is not None and len(first.head) == 0


@context(programs(), g.int_range(2, 4), g.int_range(1, 8))
@prop("every shrink of a program could have been drawn")
def _shrinks_valid(
    put: Program, modulus: int, max_steps: int, seed: int
) -> bool:
    model = Stateful((put, put), modulus, max_steps)
    dissection = st.programs(stateful_machine(model), max_steps).sample(
        a.seed(seed)
    )
    if dissection is None:
        return False
    nodes = list(breadth_first(dissection, 40))
    leaf = greedy_leaf(dissection)
    return all(member(model, node.head) for node in nodes) and len(leaf) == 0


@context(g.lists(g.int_range(0, 3)))
@prop("removing a step its successors depend on is never offered")
def _dependent(keys: list[int]) -> bool:
    # put adds a key, take removes one drawn from the model: a take
    # whose put was removed would fail its precondition.
    store: st.Machine[tuple[int, ...], None] = st.machine(
        (),
        st.command(
            "put",
            lambda system, key: None,
            arguments=g.int_range(0, 3),
            next_state=_push,
        ),
        st.command(
            "take",
            lambda system, key: None,
            arguments=lambda model: (
                g.one_of(sorted(set(model))) if model else None
            ),
            precondition=lambda model, key: key in model,
            next_state=lambda model, key: tuple(k for k in model if k != key),
        ),
    )
    rng = a.seed(sum(keys))
    dissection = st.programs(store, 12).sample(rng)
    assert dissection is not None
    for node in breadth_first(dissection, 60):
        model: tuple[int, ...] = ()
        for step in node.head.steps:
            if step.command.name == "take" and step.args not in model:
                return False
            model = step.command.next_state(model, step.args)
    return True


###############################################################################
# Construction and display
###############################################################################


@context(g.sets(g.strings()), g.int_range(0, 9), g.int_range(0, 9))
@prop("a step shows its command's name and its arguments' canonical text")
def _shown(words: set[str], x: int, y: int) -> bool:
    tick = st.command("tick", lambda system, args: None)
    return (
        repr(st.Step(tick, None)) == "tick()"
        and repr(st.Step(tick, x)) == f"tick({x})"
        and repr(st.Step(tick, (x, y))) == f"tick({x}, {y})"
        and repr(st.Step(tick, words)) == f"tick({canonical.text(words)})"
        and repr(st.Program(st.machine(0, tick), (st.Step(tick, x),)))
        == f"[tick({x})]"
    )


@context(g.int_range(0, 9))
@prop("programs are equal by their steps' names and arguments")
def _equality(x: int) -> bool:
    def _tick() -> st.Command[int, None]:
        return st.command("tick", lambda system, args: None)

    first, second = _tick(), _tick()
    other = st.command("tock", lambda system, args: None)
    left = st.Program(st.machine(0, first), (st.Step(first, x),))
    right = st.Program(st.machine(0, second), (st.Step(second, x),))
    different = st.Program(st.machine(0, other), (st.Step(other, x),))
    shifted = st.Program(st.machine(0, first), (st.Step(first, x + 1),))
    return (
        left == right
        and hash(left) == hash(right)
        and left != different
        and left != shifted
        and left != (st.Step(first, x),)
    )


@context(g.one_of(["empty name", "no commands", "repeated names", "negative"]))
@prop("machines reject what cannot be a machine")
def _rejects(case: str) -> bool:
    tick = st.command("tick", lambda system, args: None)
    attempts: dict[str, Any] = {
        "empty name": lambda: st.command("", lambda system, args: None),
        "no commands": lambda: st.machine(0),
        "repeated names": lambda: st.machine(0, tick, tick),
        "negative": lambda: st.programs(st.machine(0, tick), -1),
    }
    try:
        attempts[case]()
    except ValueError as error:
        return case != "repeated names" or "tick" in str(error)
    return False


spec = conj(
    _minimal,
    _holds,
    _mismatch,
    _models,
    _precondition,
    _raises,
    _lengths,
    _empty,
    _stuck,
    _first_shrink,
    _shrinks_valid,
    _dependent,
    _shown,
    _equality,
    _rejects,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
