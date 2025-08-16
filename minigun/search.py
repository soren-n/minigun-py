# External module dependencies
from collections.abc import Callable
from typing import Any

from returns.maybe import Maybe, Nothing, Some

# Internal module dependencies
from minigun import arbitrary as a
from minigun import generate as g
from minigun import shrink as s
from minigun import stream as fs


###############################################################################
# Find and trim counter examples
###############################################################################
def _trim_counter_example[T, *P](
    law: Callable[[T, *P], bool], example: s.Dissection[dict[str, Any]]
) -> dict[str, Any]:
    def _is_counter_example(args: s.Dissection[dict[str, Any]]) -> bool:
        _args: dict[str, Any] = s.head(args)
        _keys: list[str] = list(_args.keys())
        _values: tuple[Any, ...] = tuple(_args[key] for key in _keys)
        return not law(**dict(zip(_keys, _values, strict=False)))

    def _shrink(args: s.Dissection[dict[str, Any]]) -> Any:
        arg_values, arg_streams = args
        while True:
            match fs.peek(fs.filter(_is_counter_example, arg_streams)):
                case Some(next_args):
                    arg_values, arg_streams = next_args
                case Maybe.empty:
                    return arg_values
                case _:
                    raise AssertionError("Invariant")

    return _shrink(example)


def find_counter_example[*P](
    state: a.State,
    attempts: int,
    law: Callable[[*P], bool],
    generators: dict[str, g.Generator[Any]],
) -> tuple[a.State, Maybe[dict[str, Any]]]:
    """Attempt to find a counter example to a given law.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param attempts: The number of test attempts.
    :type attempts: `int`
    :param law: The law to be tested.
    :type law: `Callable[Parameters, bool]`
    :param generators: The generators for the arguments.
    :type generators: `dict[str, minigun.generate.Generator[Any]]`

    :return: The resulting RNG state an the potentially found counter example.
    :rtype: `tuple[minigun.arbitrary.State, returns.maybe.Maybe[dict[str, Any]]]`
    """

    def _is_counter_example(args: dict[str, Any]) -> bool:
        return not law(**args)

    counter_examples_sampler, _ = g.filter(
        _is_counter_example, g.argument_pack(generators)
    )
    for _attempt in range(attempts):
        state, maybe_counter_example = counter_examples_sampler(state)
        match maybe_counter_example:
            case Maybe.empty:
                continue
            case Some(counter_example):
                return state, Some(_trim_counter_example(law, counter_example))
            case _:
                raise AssertionError("Invariant")
    return state, Nothing
