# External module dependencies
from typing import (
    Any,
    ParamSpec,
    Dict,
    Tuple,
    Callable
)

# Internal module dependencies
from . import arbitrary as a
from . import generate as g
from . import shrink as s
from . import stream as fs
from . import maybe as m

###############################################################################
# Type variables
###############################################################################
P = ParamSpec('P')
Q = ParamSpec('Q')

###############################################################################
# Find and trim counter examples
###############################################################################
def _trim_counter_example(
    law: Callable[P, bool],
    example: s.Dissection[Dict[str, Any]]
    ) -> Dict[str, Any]:

    def _apply(*args: P.args, **kwargs: P.kwargs) -> bool:
        return law(*args, **kwargs)

    def _is_counter_example(args: s.Dissection[Dict[str, Any]]) -> bool:
        return not _apply(**s.head(args))

    def _shrink(args: s.Dissection[Dict[str, Any]]) -> Any:
        arg_values, arg_streams = args
        while True:
            match fs.peek(fs.filter(_is_counter_example, arg_streams)):
                case m.Something(next_args):
                    arg_values, arg_streams = next_args
                case m.Nothing():
                    return arg_values

    return _shrink(example)

def find_counter_example(
    state: a.State,
    attempts: int,
    law: Callable[P, bool],
    generators: Dict[str, g.Generator[Any]]
    ) -> Tuple[a.State, m.Maybe[Dict[str, Any]]]:
    """Attempt to find a counter example to a given law.

    :param state: A state from which to generate a random value.
    :type state: `State`
    :param attempts: The number of test attempts.
    :type attempts: `int`
    :param law: The law to be tested.
    :type law: `Callable[Parameters, bool]`
    :param generators: The generators for the arguments.
    :type generators: `Dict[str, minigun.generate.Generator[Any]]`

    :return: The resulting RNG state an the potentially found counter example.
    :rtype: `Tuple[minigun.arbitrary.State, minigun.maybe.Maybe[Dict[str, Any]]]`
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
            case m.Nothing(): continue
            case m.Something(counter_example):
                return state, m.Something(
                    _trim_counter_example(law, counter_example)
                )
    return state, m.Nothing()