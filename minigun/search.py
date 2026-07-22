# External module dependencies
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Internal module dependencies
from minigun import arbitrary as a
from minigun import generate as g
from minigun import shrink as s
from minigun import stream as fs


###############################################################################
# Exception handling for counter examples
###############################################################################
@dataclass
class CounterExample:
    """Represents a counter-example with optional exception information."""

    args: dict[str, Any]
    exception: Exception | None = None


###############################################################################
# Find and trim counter examples
###############################################################################
def _evaluate[*P](
    law: Callable[[*P], bool], args: dict[str, Any]
) -> tuple[bool, Exception | None]:
    """Evaluate a law; an exception counts as a failed evaluation."""
    try:
        return law(**args), None
    except Exception as exception:
        return False, exception


def _trim_counter_example[*P](
    law: Callable[[*P], bool], example: s.Dissection[dict[str, Any]]
) -> s.Dissection[dict[str, Any]]:
    def _is_counter_example(args: s.Dissection[dict[str, Any]]) -> bool:
        holds, _ = _evaluate(law, args.head)
        return not holds

    dissection = example
    while True:
        shrunk = fs.peek(fs.filter(_is_counter_example, dissection.shrinks))
        if shrunk is None:
            return dissection
        dissection = shrunk


def find_counter_example[*P](
    state: a.State,
    attempts: int,
    law: Callable[[*P], bool],
    generators: dict[str, g.Generator[Any]],
) -> tuple[a.State, CounterExample | None]:
    """Attempt to find a counter example to a given law.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param attempts: The number of test attempts.
    :type attempts: `int`
    :param law: The law to be tested.
    :type law: `Callable[Parameters, bool]`
    :param generators: The generators for the arguments.
    :type generators: `dict[str, minigun.generate.Generator[Any]]`

    :return: The resulting RNG state and the found counter example, if any.
    :rtype: `tuple[minigun.arbitrary.State, CounterExample | None]`
    """

    def _is_counter_example(args: dict[str, Any]) -> bool:
        holds, _ = _evaluate(law, args)
        return not holds

    arguments = g.filter(_is_counter_example, g.argument_pack(generators))
    for _attempt in range(attempts):
        state, counter_example = arguments.sample(state)
        if counter_example is None:
            continue
        trimmed = _trim_counter_example(law, counter_example)
        # Re-evaluate on the trimmed arguments so a reported exception
        # matches the counter example actually shown.
        _, exception = _evaluate(law, trimmed.head)
        return state, CounterExample(args=trimmed.head, exception=exception)
    return state, None
