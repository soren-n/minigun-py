# External module dependencies
from typing import (
    cast,
    Any,
    ParamSpec,
    Generic,
    List,
    Dict,
    Tuple,
    Callable,
    Optional
)
from dataclasses import dataclass
from inspect import signature
from functools import partial
from tqdm.auto import trange
from pathlib import Path
import secrets
import logging
import shutil
import os

# Internal module dependencies
from . import arbitrary as a
from . import generate as g
from . import domain as d
from . import shrink as s
from . import stream as fs
from . import pretty as p
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
    args : Dict[str, s.Dissection[Any]]
    ) -> s.Dissection[Dict[str, Any]]:
    params = list(args.keys())
    param_count = len(params)
    def _shrink_values(
        index : int,
        args : Dict[str, s.Dissection[Any]],
        streams : Dict[str, fs.Stream[s.Dissection[Any]]]
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
    heads = { param : s.head(arg) for param, arg in args.items() }
    tails = { param : s.tail(arg) for param, arg in args.items() }
    return heads, partial(_shrink_values, 0, args, tails)

def _trim_counter_example(
    law : Callable[P, bool],
    params : List[str],
    printers : Dict[str, p.Printer[Any]],
    example : Dict[str, s.Dissection[Any]]
    ) -> p.Layout:

    printer = p.tuple(*[
        p.tuple(p.str(), printers[param])
        for param in params
    ])

    def _is_counter_example(args : s.Dissection[Dict[str, Any]]) -> bool:
        return not law(**s.head(args))

    def _search(args : s.Dissection[Dict[str, Any]]) -> p.Layout:
        arg_values, arg_streams = args
        while True:
            match fs.peek(fs.filter(_is_counter_example, arg_streams)):
                case m.Something(next_args):
                    arg_values, arg_streams = next_args
                case m.Nothing():
                    return printer(tuple([
                        (param, arg_values[param])
                        for param in params
                    ]))

    return _search(_merge_args(example))

def _find_counter_example(
    state : a.State,
    desc : str,
    count : int,
    law : Callable[P, bool],
    params : List[str],
    generators : Dict[str, g.Generator[Any]],
    printers : Dict[str, p.Printer[Any]]
    ) -> Tuple[a.State, m.Maybe[p.Layout]]:
    for _ in trange(count, desc = desc):
        example : Dict[str, s.Dissection[Any]] = {}
        for param, arg_generator in generators.items():
            state, arg = arg_generator(state)
            example[param] = arg
        _example = { param : s.head(arg) for param, arg in example.items() }
        if law(**_example): continue
        return state, m.Something(_trim_counter_example(
            law, params, printers, example
        ))
    return state, m.Nothing()

###############################################################################
# Spec constructors
###############################################################################
@dataclass
class Spec:
    """Representation of a specification."""

@dataclass
class _Prop(Spec, Generic[P]):
    desc: str
    count: int
    law: Callable[P, bool]
    params : List[str]
    generators: Dict[str, m.Maybe[g.Generator[Any]]]
    printers: Dict[str, m.Maybe[p.Printer[Any]]]

def prop(desc : str):
    """Decorator for property specfications.

    :param desc: A description of the decorated law.
    :type desc: `str`

    :return: A property specification.
    :rtype: `Spec`
    """
    def _decorate(law : Callable[P, bool]):

        # Law type signature
        sig = signature(law)
        params = list(sig.parameters.keys())
        param_types = {
            p.name : cast(type, p.annotation)
            for p in sig.parameters.values()
        }

        # Try to infer generators
        generators : Dict[str, m.Maybe[g.Generator[Any]]] = {}
        printers : Dict[str, m.Maybe[p.Printer[Any]]] = {}
        for param in params:
            param_type = param_types[param]
            generators[param] = g.infer(param_type)
            printers[param] = p.infer(param_type)

        # Done
        return _Prop(desc, 100, law, params, generators, printers)
    return _decorate

@dataclass
class _Conj(Spec):
    specs : Tuple[Spec, ...]

def conj(*specs : Spec) -> Spec:
    """A constructor for the conjunction of specfications.

    :param specs: Terms of the conjunction.
    :type specs: `Spec`

    :return: A conjunction of specifications.
    :rtype: `Spec`
    """
    return _Conj(specs)

@dataclass
class _Disj(Spec):
    specs : Tuple[Spec, ...]

def disj(*specs : Spec) -> Spec:
    """A constructor for the disjunction of specfications.

    :param specs: Terms of the disjunction.
    :type specs: `Spec`

    :return: A disjunction of specifications.
    :rtype: `Spec`
    """
    return _Disj(specs)

@dataclass
class _Impl(Spec):
    premise : Spec
    conclusion : Spec

def impl(premise : Spec, conclusion : Spec) -> Spec:
    """A constructor for the implication of two specfications.

    :param premise: The premise of the implication.
    :type premise: `Spec`
    :param conclusion: The conclusion of the implication.
    :type conclusion: `Spec`

    :return: A conjunction of specifications.
    :rtype: `Spec`
    """
    return _Impl(premise, conclusion)

###############################################################################
# Overwrite defaults or define generators and printers for law parameters
###############################################################################
def context(*lparams : d.Domain[Any], **kparams : d.Domain[Any]):
    """A decorator for defining domains of a property's parameters.

    :param lparam: Domains of positional parameters.
    :type lparam: Tuple[`minigun.domain.Domain[Any]`, ...]
    :param kparam: Domains of keyword parameters.
    :type kparam: `Dict[str, 'minigun.domain.Domain[Any]]`

    :return: A property specification.
    :rtype: `Spec`
    """
    def _decorate(spec : Spec) -> Spec:
        match spec:
            case _Prop(desc, count, law, params, generators, printers):
                _result = _Prop(desc, count, law, params, generators, printers)
                for param, domain in zip(params[:len(params)], lparams):
                    _result.generators[param] = m.Something(domain.generate)
                    _result.printers[param] = m.Something(domain.print)
                for param, domain in kparams.items():
                    _result.generators[param] = m.Something(domain.generate)
                    _result.printers[param] = m.Something(domain.print)
                return _result
            case _: assert False, 'Invariant'
    return _decorate

###############################################################################
# Directory fixtures
###############################################################################
def tempoary_path(dir_path : Optional[Path] = None) -> Path:
    result = Path('.minigun', 'tempoary', secrets.token_hex(15))
    if not result.parent.exists(): os.makedirs(result.parent)
    if dir_path and dir_path.exists(): shutil.copytree(dir_path, result)
    else: os.makedirs(result)
    return result

def permanent_path(dir_path : Optional[Path] = None) -> Path:
    result = Path('.minigun', 'permanent', secrets.token_hex(15))
    if not result.parent.exists(): os.makedirs(result.parent)
    if dir_path and dir_path.exists(): shutil.copytree(dir_path, result)
    else: os.makedirs(result)
    return result

###############################################################################
# Specification evaluation
###############################################################################
def check(spec : Spec) -> bool:
    """Check an interface against its specification.

    :param spec: The specification to test against.
    :type spec: `Spec`

    :return: A boolean value representing whether the interfaces passed testing against their specification.
    :rtype: `bool`
    """
    def _visit(state : a.State, spec : Spec) -> Tuple[a.State, bool]:
        match spec:
            case _Prop(desc, count, law, params, generators, printers):
                _generators : Dict[str, g.Generator[Any]] = {}
                for param, maybe_generator in generators.items():
                    match maybe_generator:
                        case m.Nothing():
                            logging.error(
                                'No generator was inferred or defined '
                                'for parameter \"%s\" of property \"%s\"' % (
                                    param, desc
                                )
                            )
                            return state, False
                        case m.Something(generator):
                            _generators[param] = generator
                _printers : Dict[str, p.Printer[Any]] = {}
                for param, maybe_printer in printers.items():
                    match maybe_printer:
                        case m.Nothing():
                            logging.error(
                                'No printer was inferred or defined '
                                'for parameter \"%s\" of property \"%s\"' % (
                                    param, desc
                                )
                            )
                            return state, False
                        case m.Something(printer):
                            _printers[param] = printer
                state, counter_example = _find_counter_example(
                    state, desc, count, law, params, _generators, _printers
                )
                match counter_example:
                    case m.Nothing(): return state, True
                    case m.Something(layout):
                        logging.error(
                            'A test case of \"%s\" failed with the '
                            'following counter example:\n%s' % (
                                desc, p.render(layout)
                            )
                        )
                        return state, False
            case _Conj(terms):
                for term in terms:
                    state, success = _visit(state, term)
                    if success: continue
                    return state, False
                return state, True
            case _Disj(terms):
                for term in terms:
                    state, success = _visit(state, term)
                    if not success: continue
                    return state, True
                return state, False
            case _Impl(premise, conclusion):
                state, success = _visit(state, premise)
                if not success: return state, False
                return _visit(state, conclusion)
            case _: assert False, 'Invariant'
    _, success = _visit(a.seed(), spec)
    temp_path = Path('.minigun', 'tempoary')
    if temp_path.exists(): shutil.rmtree(temp_path)
    logging.info(
        'All checks passed!'
        if success else
        'Some checks failed!'
    )
    return success