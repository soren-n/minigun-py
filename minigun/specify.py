"""
Property Specification and Evaluation

This module provides the DSL for defining property specifications and the
evaluator for running them.

Key Components:
    - @prop decorator: Define properties with automatic type inference
    - @context decorator: Explicit generators for parameters
    - Spec composition: conj() and neg() for logical operations
    - check(): Standalone test execution with seed control
    - evaluate(): Callback-driven evaluation used by the orchestrator

Example::

        from minigun.specify import prop, context, check, conj
        import minigun.generate as g

        @prop("list length distributes over concatenation")
        def test_list_length(xs: list[int], ys: list[int]):
            return len(xs + ys) == len(xs) + len(ys)

        @context(g.bounded_list(0, 10, g.int()))
        @prop("bounded lists respect their bounds")
        def test_bounded_lists(xs: list[int]):
            return len(xs) <= 10

        # Run conjunction of tests
        success = check(conj(test_list_length, test_bounded_lists))
"""

# External module dependencies
import os
import pprint
import secrets
import shutil
import textwrap
import time
from collections.abc import Callable
from dataclasses import dataclass
from inspect import signature
from pathlib import Path
from typing import Any, cast

# Internal module dependencies
from minigun import arbitrary as a
from minigun import cardinality as c
from minigun import generate as g
from minigun import search as s
from minigun.budget import baseline_attempts


###############################################################################
# Spec constructors
###############################################################################
@dataclass
class Spec:
    """Representation of a specification."""


@dataclass
class _Prop[**P](Spec):
    desc: str
    law: Callable[P, bool]
    ordering: list[str]
    generators: dict[str, g.Generator[Any] | None]


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
        generators: dict[str, g.Generator[Any] | None] = {}
        for param in params:
            param_type = param_types[param]
            generators[param] = g.infer(param_type)

        # Done
        return _Prop(desc, law, params, generators)

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


###############################################################################
# Overwrite default generators for law parameters
###############################################################################
def context(
    *lparams: g.Generator[Any], **kparams: g.Generator[Any]
) -> Callable[[Spec], Spec]:
    """A decorator for defining generators of a property's parameters.

    :param lparam: Generators of positional parameters.
    :type lparam: tuple[`minigun.generate.Generator[Any]`, ...]
    :param kparam: Generators of keyword parameters.
    :type kparam: `dict[str, minigun.generate.Generator[Any]]`

    :return: A property specification.
    :rtype: `Spec`
    """

    def _decorate(spec: Spec) -> Spec:
        match spec:
            case _Prop(desc, law, params, generators):
                if len(lparams) > len(params):
                    raise TypeError(
                        f'Property "{desc}" takes {len(params)} parameters '
                        f"but context() received {len(lparams)} positional "
                        "generators"
                    )
                unknown = [param for param in kparams if param not in params]
                if unknown:
                    raise TypeError(
                        f'Property "{desc}" has no parameters named '
                        f"{', '.join(sorted(unknown))}"
                    )
                _generators = dict(generators)
                for param, generator in zip(params, lparams, strict=False):
                    _generators[param] = generator
                for param, generator in kparams.items():
                    _generators[param] = generator
                return _Prop(desc, law, params, _generators)
            case _:
                raise AssertionError("Invariant")

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


def cleanup_temporary() -> None:
    """Remove temporary directory fixtures created by temporary_path."""
    temp_path = Path(".minigun", "temporary")
    if temp_path.exists():
        shutil.rmtree(temp_path)


###############################################################################
# Specification evaluation
###############################################################################

#: Callback deciding the number of attempts for a property, given the
#: property and the total cardinality of its resolved generators.
type AttemptsFor = Callable[["_Prop[Any]", c.Cardinality], int]

#: Callback invoked when evaluation of a property starts.
type OnStart = Callable[[str], None]

#: Callback invoked with the outcome of a property:
#: (desc, success, duration, counter_example, error_message).
type OnResult = Callable[[str, bool, float, str | None, str | None], None]


def collect_properties(spec: Spec) -> list["_Prop[Any]"]:
    """Collect all properties contained in a specification.

    :param spec: The specification to collect properties from.

    :return: The properties in evaluation order.
    """
    match spec:
        case _Prop():
            return [spec]
        case _Neg(term):
            return collect_properties(term)
        case _Conj(terms):
            props: list[_Prop[Any]] = []
            for term in terms:
                props.extend(collect_properties(term))
            return props
        case _:
            raise AssertionError("Invariant")


def resolved_generators(
    prop: "_Prop[Any]",
) -> tuple[dict[str, g.Generator[Any]], c.Cardinality] | str:
    """Resolve a property's generators and total cardinality.

    :param prop: The property whose generators to resolve.

    :return: The generators and their combined cardinality, or an error
        message when a parameter has no inferred or defined generator.
    """
    generators: dict[str, g.Generator[Any]] = {}
    total_cardinality = c.ONE
    for param, generator in prop.generators.items():
        if generator is None:
            return (
                "No generator was inferred or defined "
                f'for parameter "{param}" of property "{prop.desc}"'
            )
        generators[param] = generator
        total_cardinality = total_cardinality * generator.cardinality
    return generators, total_cardinality


def _format_counter_example(ordering: list[str], args: dict[str, Any]) -> str:
    """Format counter-example arguments as 'param = value' lines."""
    lines: list[str] = []
    for param in ordering:
        rendered = pprint.pformat(args[param], width=72, sort_dicts=False)
        if "\n" in rendered:
            indented = textwrap.indent(rendered, "  ")
            lines.append(f"{param} =\n{indented}")
        else:
            lines.append(f"{param} = {rendered}")
    return "\n".join(lines)


def evaluate(
    state: a.State,
    spec: Spec,
    attempts_for: AttemptsFor,
    on_start: OnStart,
    on_result: OnResult,
) -> tuple[a.State, bool]:
    """Evaluate a specification, reporting each property's outcome.

    :param state: The RNG state to evaluate with.
    :param spec: The specification to evaluate.
    :param attempts_for: Decides the number of attempts per property.
    :param on_start: Invoked with the description when a property starts.
    :param on_result: Invoked with each property's outcome.

    :return: The resulting RNG state and whether the specification holds.
    """

    def _visit_prop(
        state: a.State, prop: "_Prop[Any]", negated: bool
    ) -> tuple[a.State, bool]:
        on_start(prop.desc)
        start_time = time.time()

        resolution = resolved_generators(prop)
        if isinstance(resolution, str):
            duration = time.time() - start_time
            on_result(prop.desc, False, duration, None, resolution)
            return state, False
        generators, total_cardinality = resolution

        attempts = attempts_for(prop, total_cardinality)
        state, counter_ex = s.find_counter_example(
            state, attempts, prop.law, generators
        )
        duration = time.time() - start_time

        if counter_ex is None:
            if not negated:
                on_result(prop.desc, True, duration, None, None)
                return state, True
            error_msg = (
                f'Found no counter example for "{prop.desc}" however one '
                "was expected!"
            )
            on_result(prop.desc, False, duration, None, error_msg)
            return state, False

        if negated:
            on_result(prop.desc, True, duration, None, None)
            return state, True

        counter_example = _format_counter_example(
            prop.ordering, counter_ex.args
        )
        if counter_ex.exception:
            error_msg = (
                f'A test case of "{prop.desc}" raised an exception:\n'
                f"{type(counter_ex.exception).__name__}: "
                f"{counter_ex.exception}"
            )
        else:
            error_msg = (
                f'A test case of "{prop.desc}" failed with the following '
                "counter example:"
            )
        on_result(prop.desc, False, duration, counter_example, error_msg)
        return state, False

    def _visit(
        state: a.State, spec: Spec, negated: bool
    ) -> tuple[a.State, bool]:
        match spec:
            case _Prop():
                return _visit_prop(state, spec, negated)
            case _Neg(term):
                return _visit(state, term, not negated)
            case _Conj(terms):
                if negated:
                    # De Morgan: neg(conj(...)) holds when at least one
                    # negated term holds.
                    for term in terms:
                        state, success = _visit(state, term, True)
                        if success:
                            return state, True
                    return state, False
                for term in terms:
                    state, success = _visit(state, term, False)
                    if not success:
                        return state, False
                return state, True
            case _:
                raise AssertionError("Invariant")

    return _visit(state, spec, False)


def check(spec: Spec, seed: int | None = None) -> bool:
    """Check a specification, printing failures to stdout.

    This is the standalone entry point for running a specification without
    the time-budgeted orchestrator: every property gets a baseline number
    of attempts derived from its input domain size.

    :param spec: The specification to test against.
    :type spec: `Spec`
    :param seed: The seed for random generation; when None a fresh seed is
        drawn and printed on failure so the run can be reproduced.
    :type seed: `int | None`

    :return: Whether the specification holds.
    :rtype: `bool`
    """
    seed_value = seed if seed is not None else secrets.randbits(64)
    state = a.seed(seed_value)

    def _attempts_for(
        prop: "_Prop[Any]", total_cardinality: c.Cardinality
    ) -> int:
        return baseline_attempts(total_cardinality)

    def _on_start(desc: str) -> None:
        pass

    def _on_result(
        desc: str,
        success: bool,
        duration: float,
        counter_example: str | None,
        error_message: str | None,
    ) -> None:
        if success:
            return
        print(f"FAIL: {desc}")
        if error_message:
            print(error_message)
        if counter_example:
            print(counter_example)

    _, success = evaluate(state, spec, _attempts_for, _on_start, _on_result)
    if not success:
        print(f"Reproduce with: check(spec, seed={seed_value})")
    cleanup_temporary()
    return success
