# External module dependencies
from typing import (
    Callable,
    Any
)
from returns.maybe import (
    Maybe,
    Nothing,
    Some
)

# Internal module dependencies
from . import (
    arbitrary as a,
    generate as g,
    shrink as s,
    stream as fs
)

###############################################################################
# Find and trim counter examples
###############################################################################
def _trim_counter_example[**P](
    law: Callable[P, bool],
    example: s.Dissection[dict[str, Any]]
    ) -> dict[str, Any]:

    def _apply(*args: P.args, **kwargs: P.kwargs) -> bool:
        return law(*args, **kwargs)

    def _is_counter_example(args: s.Dissection[dict[str, Any]]) -> bool:
        return not _apply(**s.head(args))

    def _shrink(args: s.Dissection[dict[str, Any]]) -> Any:
        arg_values, arg_streams = args
        while True:
            match fs.peek(fs.filter(_is_counter_example, arg_streams)):
                case Some(next_args):
                    arg_values, arg_streams = next_args
                case Maybe.empty:
                    return arg_values

    return _shrink(example)

def find_counter_example[**P](
    state: a.State,
    attempts: int,
    law: Callable[P, bool],
    generators: dict[str, g.Generator[Any]]
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

    def _apply(*args: P.args, **kwargs: P.kwargs) -> bool:
        return law(*args, **kwargs)

    def _is_counter_example(args: dict[str, Any]) -> bool:
        return not _apply(**args)

    counter_examples = g.filter(
        _is_counter_example,
        g.argument_pack(generators)
    )
    for _attempt in range(attempts):
        state, maybe_counter_example = counter_examples(state)
        match maybe_counter_example:
            case Maybe.empty: continue
            case Some(counter_example):
                return state, Some(
                    _trim_counter_example(law, counter_example)
                )
            case _: assert False, 'Invariant'
    return state, Nothing