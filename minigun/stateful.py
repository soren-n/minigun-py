"""
Stateful testing

A system with mutable state is tested by running random programs of
commands against it and against a model, a simple value that says what
the system should do. A ``Machine`` describes the commands: how each
draws its arguments, when it may run (its precondition, over the model),
how it changes the model (its next state) and what it must return (its
postcondition, over the model before it ran). ``programs(machine)`` draws
programs whose every step meets its precondition, and a law runs a
program against a fresh system with ``Program.run``::

        import minigun.generate as g
        from minigun.specify import context, prop
        from minigun.stateful import command, machine, programs

        counter = machine(
            0,
            command(
                "add",
                lambda system, n: system.add(n),
                arguments=g.int_range(1, 9),
                next_state=lambda total, n: total + n,
            ),
            command(
                "total",
                lambda system, _: system.total(),
                postcondition=lambda total, _, result: result == total,
            ),
        )

        @context(programs(counter))
        @prop("the counter adds up")
        def _adds_up(program) -> bool:
            return program.run(Counter())

A failing program shrinks by removing steps, largest chunks first, and
by shrinking the arguments of a step, keeping only programs whose every
step still meets its precondition, so a counterexample is a short
program that could have run.

The model must be an immutable value, or at least never changed in
place: ``next_state`` returns the next model, and generation and
shrinking replay the model through a program many times. Preconditions
decide what a valid program is, so a step whose arguments depend on the
model (an existing key, say) needs a precondition saying so: shrinking
may remove the step that made them valid.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from minigun import arbitrary as a
from minigun import canonical
from minigun import cardinality as c
from minigun import generate as g
from minigun import shrink as s

__all__ = [
    "Command",
    "Machine",
    "Step",
    "Program",
    "ModelMismatch",
    "command",
    "machine",
    "programs",
    "DEFAULT_MAX_STEPS",
]

#: The longest program ``programs`` draws unless told otherwise.
DEFAULT_MAX_STEPS = 30

#: Commands tried per step, per command of the machine, before a program
#: ends early because no command can run.
_TRIES_PER_COMMAND = 10


def _always(*_: Any) -> bool:
    return True


def _unchanged[M](model: M, _: Any) -> M:
    return model


@dataclass(frozen=True, eq=False)
class Command[M, S]:
    """A command of a state machine; made with ``command``.

    :param name: The name it is shown with in programs.
    :param run: Runs it on the system with its arguments, returning a
        result for the postcondition.
    :param arguments: Its arguments' generator given the model before it
        runs, or None when it cannot run in that model.
    :param precondition: Whether it may run with these arguments in the
        model.
    :param next_state: The model after it ran with these arguments.
    :param postcondition: Whether its result is right, given the model
        before it ran and its arguments.
    """

    name: str
    run: Callable[[S, Any], Any]
    arguments: Callable[[M], g.Generator[Any] | None]
    precondition: Callable[[M, Any], bool]
    next_state: Callable[[M, Any], M]
    postcondition: Callable[[M, Any, Any], bool]


def command[M, S](
    name: str,
    run: Callable[[S, Any], Any],
    *,
    arguments: g.Generator[Any]
    | Callable[[M], g.Generator[Any] | None]
    | None = None,
    precondition: Callable[[M, Any], bool] | None = None,
    next_state: Callable[[M, Any], M] | None = None,
    postcondition: Callable[[M, Any, Any], bool] | None = None,
) -> Command[M, S]:
    """A command of a state machine.

    Every function gets the command's arguments, None for a command
    without ``arguments``.

    :param name: The name it is shown with in programs; unique within a
        machine.
    :param run: Runs it on the system: ``run(system, args)``, returning
        the result its postcondition checks.
    :param arguments: A generator of its arguments, or a function of the
        model giving one, or None when the command cannot run in that
        model (such as a removal from an empty collection); None for no
        arguments.
    :param precondition: ``precondition(model, args)``, whether it may
        run; always when None.
    :param next_state: ``next_state(model, args)``, the model after it
        ran; the model is unchanged when None.
    :param postcondition: ``postcondition(model, args, result)``, whether
        its result is right in the model before it ran; always when None.

    :raises ValueError: When the name is empty.
    """
    if not name:
        raise ValueError("A command needs a name")
    generator_of: Callable[[M], g.Generator[Any] | None]
    if arguments is None:
        none = g.none()
        generator_of = lambda _: none  # noqa: E731
    elif isinstance(arguments, g.Generator):
        fixed = arguments
        generator_of = lambda _: fixed  # noqa: E731
    else:
        generator_of = arguments
    return Command(
        name,
        run,
        generator_of,
        precondition or _always,
        next_state or _unchanged,
        postcondition or _always,
    )


@dataclass(frozen=True, eq=False)
class Machine[M, S]:
    """A state machine: an initial model and the commands that act on a
    system and its model; made with ``machine``."""

    initial: M
    commands: tuple[Command[M, S], ...]


def machine[M, S](initial: M, *commands: Command[M, S]) -> Machine[M, S]:
    """A state machine with an initial model and its commands.

    :param initial: The model of a fresh system; never changed in place.

    :raises ValueError: When there are no commands, or two share a name.
    """
    if not commands:
        raise ValueError("A machine needs at least one command")
    names = [cmd.name for cmd in commands]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(
            "Commands of a machine need distinct names; repeated: "
            + ", ".join(repeated)
        )
    return Machine(initial, tuple(commands))


@dataclass(frozen=True, eq=False)
class Step[M, S]:
    """A command with its arguments, shown as ``name(arguments)``."""

    command: Command[M, S]
    args: Any

    def __repr__(self) -> str:
        if self.args is None:
            return f"{self.command.name}()"
        if type(self.args) is tuple:
            inner = ", ".join(canonical.text(arg) for arg in self.args)
            return f"{self.command.name}({inner})"
        return f"{self.command.name}({canonical.text(self.args)})"

    def __eq__(self, other: object) -> bool:
        # By name, as shown: the same program drawn from two machines
        # built alike is equal.
        return (
            isinstance(other, Step)
            and other.command.name == self.command.name
            and other.args == self.args
        )

    def __hash__(self) -> int:
        return hash(self.command.name)


class ModelMismatch(Exception):
    """A program's run disagreed with the model: a postcondition rejected
    a step's result, or a step's precondition did not hold."""


@dataclass(frozen=True, eq=False)
class Program[M, S]:
    """A sequence of steps of a machine, every one meeting its
    precondition; shown as the list of its steps, and equal to a program
    whose steps have the same command names and equal arguments.

    :param machine: The machine the steps are commands of.
    :param steps: The steps in order.
    """

    machine: Machine[M, S]
    steps: tuple[Step[M, S], ...]

    def __repr__(self) -> str:
        return repr(list(self.steps))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Program) and other.steps == self.steps

    def __hash__(self) -> int:
        return hash(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    def models(self) -> list[M]:
        """The model before the first step and after each step."""
        model = self.machine.initial
        models = [model]
        for step in self.steps:
            model = step.command.next_state(model, step.args)
            models.append(model)
        return models

    def run(self, system: S) -> bool:
        """Run the program on a system, checking every step's result
        against the model.

        An exception the system raises propagates as it is.

        :return: True when every postcondition held.

        :raises ModelMismatch: When a postcondition rejects a step's
            result, saying which step and in which model, or a step's
            precondition does not hold.
        """
        model = self.machine.initial
        for index, step in enumerate(self.steps, start=1):
            cmd = step.command
            if not cmd.precondition(model, step.args):
                raise ModelMismatch(
                    f"Step {index}, {step!r}, does not meet its "
                    f"precondition in the model {canonical.text(model)}"
                )
            result = cmd.run(system, step.args)
            if not cmd.postcondition(model, step.args, result):
                raise ModelMismatch(
                    f"Step {index}, {step!r}, returned "
                    f"{canonical.text(result)}, which its postcondition "
                    f"rejects in the model {canonical.text(model)}"
                )
            model = cmd.next_state(model, step.args)
        return True


###############################################################################
# Generation and shrinking
###############################################################################

#: A step whose arguments are a dissection, so they can shrink.
type _Drawn = tuple[Command[Any, Any], s.Dissection[Any]]


def _valid(initial: Any, steps: Sequence[_Drawn]) -> bool:
    """Whether every step meets its precondition, replaying the model."""
    model = initial
    for cmd, args in steps:
        if not cmd.precondition(model, args.head):
            return False
        model = cmd.next_state(model, args.head)
    return True


def _dissection[M, S](
    chosen: Machine[M, S], drawn: list[_Drawn]
) -> s.Dissection[Program[M, S]]:
    def _node(steps: list[_Drawn]) -> s.Dissection[Program[M, S]]:
        def _candidates() -> Iterator[list[_Drawn]]:
            for start, end in s.chunk_removals(len(steps), len(steps)):
                yield steps[:start] + steps[end:]
            for index, (cmd, args) in enumerate(steps):
                for child in args.shrinks():
                    replaced = list(steps)
                    replaced[index] = (cmd, child)
                    yield replaced

        def _iterate() -> Iterator[s.Dissection[Program[M, S]]]:
            for candidate in _candidates():
                if _valid(chosen.initial, candidate):
                    yield _node(candidate)

        program = Program(
            chosen, tuple(Step(cmd, args.head) for cmd, args in steps)
        )
        return s.Dissection(program, _iterate)

    return _node(drawn)


def _draw_step(
    rng: a.Rng, chosen: Machine[Any, Any], model: Any
) -> _Drawn | None:
    """A command that may run in the model, with its arguments; None
    when no command was found to run within the tries."""
    for _ in range(_TRIES_PER_COMMAND * len(chosen.commands)):
        cmd = a.choice(rng, list(chosen.commands))
        generator = cmd.arguments(model)
        if generator is None:
            continue
        args = generator.sample(rng)
        if args is not None and cmd.precondition(model, args.head):
            return cmd, args
    return None


def programs[M, S](
    chosen: Machine[M, S], max_steps: int = DEFAULT_MAX_STEPS
) -> g.Generator[Program[M, S]]:
    """A generator of programs of a machine with up to ``max_steps``
    steps, every step meeting its precondition.

    The length is drawn uniformly. Each step draws a command and its
    arguments in the model so far until its precondition holds; when no
    command can run after a number of tries, the program ends there.

    :raises ValueError: When ``max_steps`` is negative.
    """
    if max_steps < 0:
        raise ValueError(f"programs requires max_steps >= 0, got {max_steps}")

    def _impl(rng: a.Rng) -> s.Dissection[Program[M, S]]:
        length = a.draw_int(rng, 0, max_steps)
        model = chosen.initial
        drawn: list[_Drawn] = []
        for _ in range(length):
            step = _draw_step(rng, chosen, model)
            if step is None:
                break
            drawn.append(step)
            cmd, args = step
            model = cmd.next_state(model, args.head)
        return _dissection(chosen, drawn)

    return g.Generator(_impl, c.ONE if max_steps == 0 else c.INFINITE)
