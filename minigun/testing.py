# External module dependencies
from typing import (
    cast,
    ParamSpec,
    Any,
    Generic,
    List,
    Dict,
    Tuple,
    Callable
)
from dataclasses import dataclass
from inspect import signature
from functools import partial
from tqdm.auto import trange
from pathlib import Path
import logging
import shutil

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
# Test decorators
###############################################################################
Law = Callable[P, bool]

@dataclass
class Unit(Generic[P]):
    law: Law[P]
    args: Dict[str, q.Sampler[Any]]

def domain(*lparams : q.Sampler[Any], **kparams : q.Sampler[Any]):
    def _decorate(law : Law[P]) -> Unit[P]:
        sig = signature(law)
        params = list(sig.parameters.keys())
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
    law : Law[P],
    counter_example : Dict[str, d.Domain[Any]]
    ) -> Dict[str, Any]:

    def _is_counter_example(args : d.Domain[Dict[str, Any]]) -> bool:
        return not law(**d.head(args))

    def _search(args : d.Domain[Dict[str, Any]]) -> Dict[str, Any]:
        arg_values, arg_streams = args
        while True:
            next_args = s.peek(s.filter(_is_counter_example, arg_streams))
            if isinstance(next_args, m.Nothing): return arg_values
            arg_values, arg_streams = next_args.value

    return _search(_merge_args(counter_example))

def _find_counter_example(
    desc : str,
    count : int,
    unit : Unit[P],
    state : a.State
    ) -> Tuple[a.State, m.Maybe[Dict[str, Any]]]:
    for _ in trange(count, desc = desc):
        example : Dict[str, d.Domain[Any]] = {}
        for param, arg_sampler in unit.args.items():
            state, arg = arg_sampler(state)
            example[param] = arg
        _example = { param : d.head(arg) for param, arg in example.items() }
        if unit.law(**_example): continue
        return state, m.Something(_trim_counter_example(unit.law, example))
    return state, m.Nothing()

###############################################################################
# Spec constructors
###############################################################################
@dataclass
class Spec: pass

@dataclass
class Prop(Spec):
    desc: str
    unit: Callable[[a.State], Tuple[a.State, m.Maybe[Dict[str, Any]]]]

def prop(desc : str, count : int):
    def _decorate(unit : Unit[P]):
        return Prop(desc, partial(_find_counter_example, desc, count, unit))
    return _decorate

@dataclass
class Conj(Spec):
    specs : Tuple[Spec, ...]

def conj(*specs : Spec) -> Spec:
    return Conj(specs)

@dataclass
class Disj(Spec):
    specs : Tuple[Spec, ...]

def disj(*specs : Spec) -> Spec:
    return Disj(specs)

@dataclass
class Impl(Spec):
    premise : Spec
    conclusion : Spec

def impl(premise : Spec, conclusion : Spec) -> Spec:
    return Impl(premise, conclusion)

###############################################################################
# Spec evaluation
###############################################################################
def check(spec : Spec) -> bool:
    def _visit(state : a.State, spec : Spec) -> Tuple[a.State, bool]:
        match spec:
            case Prop(desc, unit):
                state, counter_example = unit(state)
                match counter_example:
                    case m.Nothing(): return state, True
                    case m.Something(value):
                        logging.error(
                            'A unit-test of \"%s\" failed with the '
                            'following counter example:\n%s' % (
                                desc, value
                            )
                        )
                        return state, False
                    case _: assert False, 'Invariant'
            case Conj(terms):
                for term in terms:
                    state, success = _visit(state, term)
                    if success: continue
                    return state, False
                return state, True
            case Disj(terms):
                for term in terms:
                    state, success = _visit(state, term)
                    if not success: continue
                    return state, True
                return state, False
            case Impl(premise, conclusion):
                state, success = _visit(state, premise)
                if not success: return state, False
                return _visit(state, conclusion)
            case _: assert False, 'Invariant'
    _, success = _visit(a.seed(), spec)
    temp_path = Path('.minigun')
    if temp_path.exists(): shutil.rmtree(temp_path)
    logging.info(
        'All checks passed!'
        if success else
        'Some checks failed!'
    )
    return success