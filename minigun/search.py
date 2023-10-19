# External module dependencies
from typing import (
    Any,
    ParamSpec,
    List,
    Dict,
    Tuple,
    Callable,
    Optional
)
from functools import partial

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
def _merge_args(
    args: Dict[str, s.Dissection[Any]]
    ) -> s.Dissection[Dict[str, Any]]:
    params = list(args.keys())
    param_count = len(params)
    def _shrink_values(
        index: int,
        args: Dict[str, s.Dissection[Any]],
        streams: Dict[str, fs.Stream[s.Dissection[Any]]]
        ) -> fs.StreamResult[s.Dissection[Dict[str, Any]]]:
        if index == param_count: raise StopIteration
        param = params[index]
        _index = index + 1
        try: next_arg, next_stream = streams[param]()
        except StopIteration: return _shrink_values(_index, args, streams)
        _args = args.copy()
        _streams = streams.copy()
        _args[param] = next_arg
        _streams[param] = next_stream
        return _merge_args(_args), fs.concat(
            partial(_shrink_values, index, args, _streams),
            partial(_shrink_values, _index, args, streams)
        )
    heads = { param: s.head(arg) for param, arg in args.items() }
    tails = { param: s.tail(arg) for param, arg in args.items() }
    return heads, partial(_shrink_values, 0, args, tails)

def _trim_counter_example(
    law: Callable[P, bool],
    example: Dict[str, s.Dissection[Any]]
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

    return _shrink(_merge_args(example))

def find_counter_example(
    state: a.State,
    attempts: int,
    law: Callable[P, bool],
    generators: Dict[str, g.Generator[Any]],
    monitor: Optional[Callable[[int], None]] = None
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
    :param monitor: An optional monitor of progress on attempts.
    :type monitor: `Optional[Callable[[int], None]]`

    :return: The output state with a possible found counter example.
    :rtype: `Tuple[minigun.arbitrary.State, minigun.maybe.Maybe[Dict[str, Any]]]`
    """

    def _apply(*args: P.args, **kwargs: P.kwargs) -> bool:
        return law(*args, **kwargs)

    for attempt in range(1, attempts + 1):
        if monitor is not None: monitor(attempt)
        example : Dict[str, s.Dissection[Any]] = {}
        for param, arg_generator in generators.items():
            state, arg = arg_generator(state)
            example[param] = arg
        _example = { param : s.head(arg) for param, arg in example.items() }
        if _apply(**_example): continue
        return state, m.Something(_trim_counter_example(law, example))
    return state, m.Nothing()