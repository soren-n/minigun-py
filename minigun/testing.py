# External module dependencies
from typing import (
    cast,
    ParamSpec,
    Concatenate,
    Any,
    Generic,
    List,
    Dict,
    Tuple,
    Callable
)
from contextlib import contextmanager
from dataclasses import dataclass
from inspect import signature
from functools import partial
from tqdm.auto import trange
from pathlib import Path
import secrets
import shutil
import os

# Internal module dependencies
from . import arbitrary as a
from . import quantify as q
from . import stream as s
from . import domain as d
from . import maybe as m

###############################################################################
# Type variables
###############################################################################
P = ParamSpec('P')
Q = ParamSpec('Q')

###############################################################################
# Testing context
###############################################################################
class Context:
    def __init__(self, root_path : Path):
        self._root_path = root_path

    @contextmanager
    def directory(self):
        test_path = Path(self._root_path, secrets.token_hex(15))
        os.makedirs(test_path)
        yield test_path

@contextmanager
def _context(name : str):
    root_path = Path('.minigun', name)
    try: yield Context(root_path)
    finally:
        if not root_path.exists(): return
        shutil.rmtree(root_path)

###############################################################################
# Test decorators
###############################################################################
Law = Callable[Concatenate[Context, P], bool]

@dataclass
class Unit(Generic[P]):
    law: Law[P]
    args: Dict[str, q.Sampler[Any]]

def domain(*lparams : q.Sampler[Any], **kparams : q.Sampler[Any]):
    def _decorate(law : Law[P]) -> Unit[P]:
        sig = signature(law)
        params = list(sig.parameters.keys())[1:]
        arg_types = {
            p.name : cast(type, p.annotation)
            for p in sig.parameters.values()
        }

        # Gather declared arguments
        args : Dict[str, q.Sampler[Any]] = {}
        for param, arg_sampler in zip(params[:len(lparams)], lparams):
            args[param] = arg_sampler
        for param, arg_sampler in kparams.items():
            args[param] = arg_sampler

        # Infer missing arguments
        for param in set(params).difference(set(args.keys())):
            arg_type = arg_types[param]
            arg_sampler = q.infer(arg_type)
            if isinstance(arg_sampler, m.Nothing):
                raise TypeError(
                    'Failed to infer domain for '
                    'parameter %s of function %s' % (
                        param, law.__name__
                    )
                )
            args[param] = arg_sampler.value

        # Wrap up the unit
        return Unit(law, args)
    return _decorate

def _merge_args(
    args : Dict[str, d.Domain[Any]]
    ) -> d.Domain[Dict[str, Any]]:
    def _shrink_args(
        args : Dict[str, d.Domain[Any]]
        ) -> s.Stream[d.Domain[Dict[str, Any]]]:
        def _step_left(
            param : str,
            args : Dict[str, d.Domain[Any]],
            next_arg_domain : d.Domain[Any]
            ) -> d.Domain[Dict[str, Any]]:
            _args = args.copy()
            _args[param] = next_arg_domain
            return _merge_args(_args)
        def _step_right(
            params : List[str]
            ) -> s.StreamResult[d.Domain[Dict[str, Any]]]:
            if len(params) == 0: raise StopIteration
            _params = params.copy()
            param = _params.pop(0)
            _args = args.copy()
            next_arg_domain, next_arg_stream = d.tail(args[param])()
            _args[param] = next_arg_domain
            return _merge_args(_args), s.concat(
                s.map(partial(_step_left, param, _args), next_arg_stream),
                partial(_step_right, _params)
            )
        return partial(_step_right, list(args.keys()))
    arg_values = { param : d.head(arg) for param, arg in args.items() }
    return arg_values, _shrink_args(args)

def _trim_counter_example(
    ctx : Context,
    law : Law[P],
    counter_example : Dict[str, d.Domain[Any]]
    ) -> Dict[str, Any]:

    def _is_counter_example(args : d.Domain[Dict[str, Any]]) -> bool:
        return not law(ctx, **d.head(args))

    def _search(args : d.Domain[Dict[str, Any]]) -> Dict[str, Any]:
        arg_values, arg_streams = args
        while True:
            next_args = s.peek(s.filter(_is_counter_example, arg_streams))
            if isinstance(next_args, m.Nothing): return arg_values
            arg_values, arg_streams = next_args.value

    return _search(_merge_args(counter_example))

def _find_counter_example(
    name : str,
    count : int,
    unit : Unit[P],
    ctx : Context,
    state : a.State
    ) -> Tuple[a.State, m.Maybe[Dict[str, Any]]]:
    for _ in trange(count, desc = name):
        example : Dict[str, d.Domain[Any]] = {}
        for param, arg_sampler in unit.args.items():
            state, arg = arg_sampler(state)
            example[param] = arg
        _example = { param : d.head(arg) for param, arg in example.items() }
        if unit.law(ctx, **_example): continue
        return state, m.Something(_trim_counter_example(ctx, unit.law, example))
    return state, m.Nothing()

@dataclass
class Test(Generic[P]):
    name: str
    count: int
    unit: Callable[[Context, a.State], Tuple[a.State, m.Maybe[Dict[str, Any]]]]
    unit_name: str

def test(name : str, count : int):
    def _decorate(unit : Unit[P]):
        _unit = partial(_find_counter_example, name, count, unit)
        return Test(name, count, _unit, unit.law.__name__)
    return _decorate

###############################################################################
# Test runner
###############################################################################
class Suite:
    def __init__(self, *tests : Test[P]):
        self._tests = tests

    def evaluate(self, args : List[str]) -> bool:
        state = a.seed()
        for test in self._tests:
            with _context(test.unit_name) as ctx:
                state, counter_example = test.unit(ctx, state)
            if isinstance(counter_example, m.Nothing): continue
            print(
                'Test \"%s\" failed with the '
                'following counter example:' % test.name
            )
            print(counter_example.value)
            return False
        print('All tests passed!')
        return True