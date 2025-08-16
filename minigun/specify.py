# External module dependencies
import os
import secrets
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from inspect import signature
from pathlib import Path
from typing import Any, cast

from returns.maybe import Maybe, Some

# Internal module dependencies
from minigun import arbitrary as a
from minigun import domain as d
from minigun import generate as g
from minigun import pretty as p
from minigun import reporter as r
from minigun import search as s


###############################################################################
# Spec constructors
###############################################################################
@dataclass
class Spec:
    """Representation of a specification."""


@dataclass
class _Prop[**P](Spec):
    desc: str
    attempts: int
    law: Callable[P, bool]
    ordering: list[str]
    generators: dict[str, Maybe[g.Generator[Any]]]
    printers: dict[str, Maybe[p.Printer[Any]]]


def prop[**P](desc: str) -> Callable[[Callable[P, bool]], Spec]:
    """Decorator for property specfications.

    :param desc: A description of the decorated law.
    :type desc: `str`

    :return: A property specification.
    :rtype: `Spec`
    """

    def _decorate(law: Callable[P, bool]) -> Spec:

        # Law type signature
        sig = signature(law)
        params = list(sig.parameters.keys())
        param_types = {
            param.name: cast(type, param.annotation)
            for param in sig.parameters.values()
        }

        # Try to infer generators
        generators: dict[str, Maybe[g.Generator[Any]]] = {}
        printers: dict[str, Maybe[p.Printer[Any]]] = {}
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
    specs: tuple[Spec, ...]


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
    specs: tuple[Spec, ...]


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
def context(
    *lparams: d.Domain[Any], **kparams: d.Domain[Any]
) -> Callable[[Spec], Spec]:
    """A decorator for defining domains of a property's parameters.

    :param lparam: Domains of positional parameters.
    :type lparam: tuple[`minigun.domain.Domain[Any]`, ...]
    :param kparam: Domains of keyword parameters.
    :type kparam: `dict[str, 'minigun.domain.Domain[Any]]`

    :return: A property specification.
    :rtype: `Spec`
    """

    def _decorate(spec: Spec) -> Spec:
        match spec:
            case _Prop(desc, count, law, params, generators, printers):
                _result = _Prop(desc, count, law, params, generators, printers)
                for param, domain in zip(params[: len(params)], lparams, strict=False):
                    _result.generators[param] = Some(domain.generate)
                    _result.printers[param] = Some(domain.print)
                for param, domain in kparams.items():
                    _result.generators[param] = Some(domain.generate)
                    _result.printers[param] = Some(domain.print)
                return _result
            case _:
                assert False, "Invariant"

    return _decorate


###############################################################################
# Directory fixtures
###############################################################################
def temporary_path(dir_path: Path | None = None) -> Path:
    result = Path(".minigun", "temporary", secrets.token_hex(15))
    if not result.parent.exists():
        os.makedirs(result.parent)
    if dir_path and dir_path.exists():
        shutil.copytree(dir_path, result)
    else:
        os.makedirs(result)
    return result


def permanent_path(dir_path: Path | None = None) -> Path:
    result = Path(".minigun", "permanent", secrets.token_hex(15))
    if not result.parent.exists():
        os.makedirs(result.parent)
    if dir_path and dir_path.exists():
        shutil.copytree(dir_path, result)
    else:
        os.makedirs(result)
    return result


###############################################################################
# Specification evaluation
###############################################################################
def _call_context(
    ordering: list[str], printers: dict[str, p.Printer[Any]]
) -> p.Printer[dict[str, Any]]:
    """Create a printer for call context that displays parameters in 'key = value' format.

    This is an alternative to argument_pack that produces more readable output for counter-examples.

    :param ordering: The order of parameters in the argument pack.
    :type ordering: `list[str]`
    :param printers: Value printers with which arguments are printed.
    :type printers: `dict[str, p.Printer[Any]]`

    :return: A printer that formats parameters as 'key = value' on separate lines.
    :rtype: `p.Printer[dict[str, Any]]`
    """
    from functools import reduce

    import typeset as ts

    def _printer(args: dict[str, Any]) -> ts.Layout:
        def _item(param: str) -> ts.Layout:
            arg = args[param]
            arg_printer = printers[param]
            # For strings, we want to use repr() to get proper Python string representation
            if isinstance(arg, str):
                return ts.parse('{0} + "=" + {1}', ts.text(param), ts.text(repr(arg)))
            else:
                return ts.parse('{0} + "=" + {1}', ts.text(param), arg_printer(arg))

        # Create items
        if not ordering:
            return ts.null()

        items = [_item(param) for param in ordering]

        # Join items with forced line breaks using @ operator
        if len(items) == 1:
            return items[0]

        return reduce(
            lambda result, layout: ts.parse("{0} @ {1}", result, layout),
            items[1:],
            items[0],
        )

    return _printer


def check(spec: Spec) -> bool:
    """Check an interface against its specification.

    :param spec: The specification to test against.
    :type spec: `Spec`

    :return: A boolean value representing whether the interfaces passed testing against their specification.
    :rtype: `bool`
    """

    def _visit(state: a.State, spec: Spec, neg: bool = False) -> tuple[a.State, bool]:
        match spec:
            case _Prop(desc, attempts, law, ordering, generators, printers):
                # Get reporter for enhanced output
                reporter = r.get_reporter()

                # Start timing this test
                start_time = time.time()
                if reporter:
                    reporter.start_test(desc)

                _generators: dict[str, g.Generator[Any]] = {}
                for param, maybe_generator in generators.items():
                    match maybe_generator:
                        case Maybe.empty:
                            error_msg = (
                                "No generator was inferred or defined "
                                f'for parameter "{param}" of property "{desc}"'
                            )
                            duration = time.time() - start_time
                            if reporter:
                                reporter.end_test(
                                    desc, False, duration, error_message=error_msg
                                )
                            return state, False
                        case Some(generator):
                            _generators[param] = generator
                        case _:
                            assert False, "Invariant"

                _printers: dict[str, p.Printer[Any]] = {}
                for param, maybe_printer in printers.items():
                    match maybe_printer:
                        case Maybe.empty:
                            error_msg = (
                                "No printer was inferred or defined "
                                f'for parameter "{param}" of property "{desc}"'
                            )
                            duration = time.time() - start_time
                            if reporter:
                                reporter.end_test(
                                    desc, False, duration, error_message=error_msg
                                )
                            return state, False
                        case Some(printer):
                            _printers[param] = printer
                        case _:
                            assert False, "Invariant"

                printer = _call_context(ordering, _printers)
                state, maybe_counter_example = s.find_counter_example(
                    state, attempts, law, _generators
                )

                duration = time.time() - start_time

                match maybe_counter_example:
                    case Maybe.empty:
                        if not neg:
                            if reporter:
                                reporter.end_test(desc, True, duration)
                            return state, True
                        error_msg = f'Found no counter example for "{desc}" however one was expected!'
                        if reporter:
                            reporter.end_test(
                                desc, False, duration, error_message=error_msg
                            )
                        return state, False
                    case Some(args):
                        if neg:
                            if reporter:
                                reporter.end_test(desc, True, duration)
                            return state, True
                        counter_example = p.render(printer(args))
                        error_msg = f'A test case of "{desc}" failed with the following counter example:'
                        if reporter:
                            reporter.end_test(
                                desc, False, duration, counter_example=counter_example
                            )
                        return state, False
                    case _:
                        assert False, "Invariant"
            case _Neg(term):
                return _visit(state, term, not neg)
            case _Conj(terms):
                for term in terms:
                    state, success = _visit(state, term)
                    if success:
                        continue
                    return state, False
                return state, True
            case _Disj(terms):
                for term in terms:
                    state, success = _visit(state, term)
                    if not success:
                        continue
                    return state, True
                return state, False
            case _Impl(premise, conclusion):
                state, success = _visit(state, premise)
                if not success:
                    return state, False
                return _visit(state, conclusion)
            case _:
                assert False, "Invariant"

    _, success = _visit(a.seed(), spec)
    temp_path = Path(".minigun", "temporary")
    if temp_path.exists():
        shutil.rmtree(temp_path)

    return success
