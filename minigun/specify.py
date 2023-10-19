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
from pathlib import Path
from tqdm import tqdm
import typeset as ts
import secrets
import logging
import shutil
import os

# Internal module dependencies
from . import arbitrary as a
from . import generate as g
from . import domain as d
from . import search as s
from . import pretty as p
from . import maybe as m

###############################################################################
# Type variables
###############################################################################
P = ParamSpec('P')
Q = ParamSpec('Q')

###############################################################################
# Spec constructors
###############################################################################
@dataclass
class Spec:
    """Representation of a specification."""

@dataclass
class _Prop(Spec, Generic[P]):
    desc: str
    attempts: int
    law: Callable[P, bool]
    ordering: List[str]
    generators: Dict[str, m.Maybe[g.Generator[Any]]]
    printers: Dict[str, m.Maybe[p.Printer[Any]]]

def prop(desc: str):
    """Decorator for property specfications.

    :param desc: A description of the decorated law.
    :type desc: `str`

    :return: A property specification.
    :rtype: `Spec`
    """
    def _decorate(law: Callable[P, bool]):

        # Law type signature
        sig = signature(law)
        params = list(sig.parameters.keys())
        param_types = {
            p.name : cast(type, p.annotation)
            for p in sig.parameters.values()
        }

        # Try to infer generators
        generators: Dict[str, m.Maybe[g.Generator[Any]]] = {}
        printers: Dict[str, m.Maybe[p.Printer[Any]]] = {}
        for param in params:
            param_type = param_types[param]
            generators[param] = g.infer(param_type)
            printers[param] = p.infer(param_type)

        # Done
        return _Prop(desc, 100, law, params, generators, printers)
    return _decorate

@dataclass
class _Neg(Spec):
    spec: Spec

def neg(spec: Spec) -> Spec:
    """A constructor for the negation of a specfication.

    :param spec: Term to be negated.
    :type spec: `Spec`

    :return: A negation of a specification.
    :rtype: `Spec`
    """
    return _Neg(spec)

@dataclass
class _Conj(Spec):
    specs: Tuple[Spec, ...]

def conj(*specs: Spec) -> Spec:
    """A constructor for the conjunction of specfications.

    :param specs: Terms of the conjunction.
    :type specs: `Spec`

    :return: A conjunction of specifications.
    :rtype: `Spec`
    """
    return _Conj(specs)

@dataclass
class _Disj(Spec):
    specs: Tuple[Spec, ...]

def disj(*specs: Spec) -> Spec:
    """A constructor for the disjunction of specfications.

    :param specs: Terms of the disjunction.
    :type specs: `Spec`

    :return: A disjunction of specifications.
    :rtype: `Spec`
    """
    return _Disj(specs)

@dataclass
class _Impl(Spec):
    premise: Spec
    conclusion: Spec

def impl(premise: Spec, conclusion: Spec) -> Spec:
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
def context(*lparams: d.Domain[Any], **kparams: d.Domain[Any]):
    """A decorator for defining domains of a property's parameters.

    :param lparam: Domains of positional parameters.
    :type lparam: Tuple[`minigun.domain.Domain[Any]`, ...]
    :param kparam: Domains of keyword parameters.
    :type kparam: `Dict[str, 'minigun.domain.Domain[Any]]`

    :return: A property specification.
    :rtype: `Spec`
    """
    def _decorate(spec: Spec) -> Spec:
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
def temporary_path(dir_path: Optional[Path] = None) -> Path:
    result = Path('.minigun', 'temporary', secrets.token_hex(15))
    if not result.parent.exists(): os.makedirs(result.parent)
    if dir_path and dir_path.exists(): shutil.copytree(dir_path, result)
    else: os.makedirs(result)
    return result

def permanent_path(dir_path: Optional[Path] = None) -> Path:
    result = Path('.minigun', 'permanent', secrets.token_hex(15))
    if not result.parent.exists(): os.makedirs(result.parent)
    if dir_path and dir_path.exists(): shutil.copytree(dir_path, result)
    else: os.makedirs(result)
    return result

###############################################################################
# Specification evaluation
###############################################################################
def _argument_pack_printer(
    ordering: list[str],
    printers: dict[str, p.Printer[Any]]
    ) -> p.Printer[dict[str, Any]]:
    def _printer(args: dict[str, Any]) -> ts.Layout:
        param_printer = p.str()
        def _wrap(body): return ts.parse('seq ("{" & nest {0} & "}")', body)
        def _item(param):
            arg = args[param]
            arg_printer = printers[param]
            return ts.parse(
                'fix ({0} & ":" + {1})',
                param_printer(param),
                arg_printer(arg)
            )
        params = iter(ordering)
        body = _item(next(params))
        for param in params:
            body = ts.parse(
                '{0} !& "," + {1}',
                body, _item(param)
            )
        return _wrap(body)
    return _printer

def check(spec: Spec) -> bool:
    """Check an interface against its specification.

    :param spec: The specification to test against.
    :type spec: `Spec`

    :return: A boolean value representing whether the interfaces passed testing against their specification.
    :rtype: `bool`
    """
    def _visit(
        state: a.State,
        spec: Spec,
        neg: bool = False
        ) -> Tuple[a.State, bool]:
        match spec:
            case _Prop(desc, attempts, law, ordering, generators, printers):
                _generators: Dict[str, g.Generator[Any]] = {}
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
                _printers: Dict[str, p.Printer[Any]] = {}
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
                printer = _argument_pack_printer(ordering, _printers)
                progress = tqdm(
                    range(attempts),
                    desc = desc,
                    ascii = " *•",
                    bar_format = "{desc}: {bar} [{elapsed} < {remaining}]"
                )
                prev_attempt = 0
                def _monitor(attempt: int) -> None:
                    nonlocal prev_attempt
                    progress.update(attempt - prev_attempt)
                    prev_attempt = attempt
                state, counter_example = s.find_counter_example(
                    state, attempts, law, _generators, _monitor
                )
                progress.close()
                match counter_example:
                    case m.Nothing():
                        if not neg: return state, True
                        logging.error(
                            'Found no counter example for \"%s\" '
                            'however one was expected!' % desc
                        )
                        return state, False
                    case m.Something(args):
                        if neg: return state, True
                        logging.error(
                            'A test case of \"%s\" failed with the '
                            'following counter example:\n%s' % (
                                desc, p.render(printer(args))
                            )
                        )
                        return state, False
            case _Neg(term):
                return _visit(state, term, not neg)
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
    temp_path = Path('.minigun', 'temporary')
    if temp_path.exists(): shutil.rmtree(temp_path)
    logging.info(
        'All checks passed!'
        if success else
        'Some checks failed!'
    )
    return success