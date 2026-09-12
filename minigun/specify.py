"""
Property specification and evaluation

A specification is a tree: properties at the leaves, composed with
conjunction and negation. ``@prop`` turns a law into a property, inferring
generators from its parameter annotations; ``@context`` supplies generators
explicitly. ``evaluate`` runs every property in the tree, reports each
outcome, and computes the truth of the tree from them.

Each property draws from its own random source, derived from the run seed
and the property's description, so a property's outcome depends only on
the seed and itself, never on what ran before it.

Example::

        from minigun.specify import prop, context, conj
        import minigun.generate as g

        @prop("list length distributes over concatenation")
        def _length(xs: list[int], ys: list[int]) -> bool:
            return len(xs + ys) == len(xs) + len(ys)

        @context(g.bounded_lists(0, 10, g.ints()))
        @prop("bounded lists respect their bounds")
        def _bounded(xs: list[int]) -> bool:
            return len(xs) <= 10

        spec = conj(_length, _bounded)
"""

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeGuard, assert_never, get_type_hints

from minigun import arbitrary as a
from minigun import cardinality as c
from minigun import generate as g
from minigun import search as s


class SpecificationError(Exception):
    """A specification cannot be evaluated as written."""


###############################################################################
# Specifications
###############################################################################
@dataclass(frozen=True)
class Prop:
    """A property: a described law with generators for its parameters.

    :param desc: The description; unique within a specification.
    :param law: The law under test, called with keyword arguments.
    :param generators: A generator per parameter in signature order, None
        where none was inferred or supplied.
    """

    desc: str
    law: Callable[..., bool]
    generators: dict[str, g.Generator[Any] | None]

    @property
    def parameters(self) -> list[str]:
        """The law's parameter names in signature order."""
        return list(self.generators)


@dataclass(frozen=True)
class Neg:
    """The negation of a specification: holds when its term fails."""

    spec: "Spec"


@dataclass(frozen=True)
class Conj:
    """The conjunction of specifications: holds when every term holds."""

    specs: tuple["Spec", ...]


#: A specification: a tree of properties under negation and conjunction.
type Spec = Prop | Neg | Conj


def is_spec(value: object) -> TypeGuard[Spec]:
    """Whether a value is a specification."""
    return isinstance(value, Prop | Neg | Conj)


def prop(desc: str) -> Callable[[Callable[..., bool]], Prop]:
    """Decorate a law as a property.

    Generators are inferred from the law's parameter annotations; a
    parameter whose annotation is missing or unsupported has no generator
    until ``@context`` supplies one.

    :param desc: A description of the law.

    :raises SpecificationError: When the law's annotations cannot be
        resolved.
    """

    def _decorate(law: Callable[..., bool]) -> Prop:
        try:
            hints = get_type_hints(law)
        except Exception as error:
            raise SpecificationError(
                f'Cannot resolve the type annotations of property "{desc}": '
                f"{type(error).__name__}: {error}"
            ) from error
        generators: dict[str, g.Generator[Any] | None] = {}
        for name in inspect.signature(law).parameters:
            generators[name] = g.infer(hints[name]) if name in hints else None
        return Prop(desc, law, generators)

    return _decorate


def context(
    *positional: g.Generator[Any], **named: g.Generator[Any]
) -> Callable[[Prop], Prop]:
    """Decorate a property with generators for its parameters.

    Positional generators bind to parameters in signature order; named
    generators bind by name. Both override inferred generators.

    :raises TypeError: When applied to anything but a property, when more
        positional generators than parameters are given, or when a name
        matches no parameter.
    """

    def _decorate(spec: Prop) -> Prop:
        if not isinstance(spec, Prop):
            raise TypeError(
                "context() applies to a property; wrap the property before "
                "composing it"
            )
        parameters = spec.parameters
        if len(positional) > len(parameters):
            raise TypeError(
                f'Property "{spec.desc}" takes {len(parameters)} parameters '
                f"but context() received {len(positional)} positional "
                "generators"
            )
        unknown = sorted(name for name in named if name not in parameters)
        if unknown:
            raise TypeError(
                f'Property "{spec.desc}" has no parameters named '
                f"{', '.join(unknown)}"
            )
        generators = dict(spec.generators)
        for name, generator in zip(parameters, positional, strict=False):
            generators[name] = generator
        generators.update(named)
        return Prop(spec.desc, spec.law, generators)

    return _decorate


def neg(spec: Spec) -> Spec:
    """The negation of a specification."""
    return Neg(spec)


def conj(*specs: Spec) -> Spec:
    """The conjunction of specifications."""
    return Conj(specs)


###############################################################################
# Resolution
###############################################################################
@dataclass(frozen=True)
class Resolved:
    """A property whose generators are all present.

    :param prop: The property.
    :param generators: A generator per parameter.
    :param cardinality: The cardinality of the argument domain.
    """

    prop: Prop
    generators: dict[str, g.Generator[Any]]
    cardinality: c.Cardinality


def collect(spec: Spec) -> list[Prop]:
    """The properties of a specification in evaluation order."""
    match spec:
        case Prop():
            return [spec]
        case Neg(term):
            return collect(term)
        case Conj(terms):
            return [prop for term in terms for prop in collect(term)]
        case _:
            assert_never(spec)


def resolve(prop: Prop) -> Resolved:
    """Resolve a property's generators.

    :raises SpecificationError: When a parameter has no generator.
    """
    generators: dict[str, g.Generator[Any]] = {}
    cardinality = c.ONE
    for name, generator in prop.generators.items():
        if generator is None:
            raise SpecificationError(
                f'No generator was inferred or defined for parameter "{name}" '
                f'of property "{prop.desc}"'
            )
        generators[name] = generator
        cardinality = cardinality * generator.cardinality
    return Resolved(prop, generators, cardinality)


def resolve_all(spec: Spec) -> list[Resolved]:
    """Resolve every property of a specification.

    :raises SpecificationError: When a property cannot be resolved or two
        properties share a description.
    """
    seen: set[str] = set()
    resolved: list[Resolved] = []
    for prop in collect(spec):
        if prop.desc in seen:
            raise SpecificationError(
                f'Duplicate property description "{prop.desc}"; descriptions '
                "must be unique within a specification"
            )
        seen.add(prop.desc)
        resolved.append(resolve(prop))
    return resolved


###############################################################################
# Evaluation
###############################################################################

#: Fraction of attempts that may be discarded before a property fails for
#: not being tested.
MAX_DISCARD_RATIO = 0.9


@dataclass(frozen=True)
class Allowance:
    """What a property may spend.

    :param max_attempts: The maximum number of attempts.
    :param deadline: A ``time.perf_counter`` instant after which no further
        attempt starts, or None.
    """

    max_attempts: int
    deadline: float | None = None


@dataclass(frozen=True)
class Outcome:
    """The outcome of evaluating one property.

    :param desc: The property's description.
    :param negated: Whether the property was evaluated under negation.
    :param holds: Whether the property held, negation applied.
    :param duration: Wall-clock seconds spent.
    :param attempts: Attempts performed, including discards.
    :param discards: Attempts whose arguments were rejected by a filter.
    :param counter_example: The counterexample found, if any.
    :param error: Why the property did not hold when the reason is not a
        counterexample: no counterexample where one was expected, or too
        many discards.
    """

    desc: str
    negated: bool
    holds: bool
    duration: float
    attempts: int
    discards: int
    counter_example: s.CounterExample | None
    error: str | None


#: Decides the allowance of a resolved property.
type AllowanceFor = Callable[[Resolved], Allowance]

#: Invoked when evaluation of a property starts.
type OnStart = Callable[[Prop], None]

#: Invoked with the outcome of a property.
type OnOutcome = Callable[[Outcome], None]


def property_rng(seed: int, desc: str) -> a.Rng:
    """The random source of a property in a run.

    Derived from the run seed and the description alone, so a property
    draws the same values regardless of what else the run contains.
    """
    return a.seed(f"{seed}\x1f{desc}")


def _judge(
    resolved: Resolved, search: s.Search, negated: bool
) -> tuple[bool, str | None]:
    """Decide whether a property held from its search, negation applied."""
    desc = resolved.prop.desc
    if search.evaluations == 0 or (
        search.discards > MAX_DISCARD_RATIO * search.attempts
    ):
        return False, (
            f'Property "{desc}" was not tested: {search.discards} of '
            f"{search.attempts} attempts were discarded by its generators"
        )
    if search.counter_example is None:
        if negated:
            return False, (
                f'Found no counter example for "{desc}" however one was '
                "expected"
            )
        return True, None
    return negated, None


def evaluate(
    seed: int,
    spec: Spec,
    allowance_for: AllowanceFor,
    on_start: OnStart,
    on_outcome: OnOutcome,
) -> bool:
    """Evaluate a specification, reporting every property's outcome.

    Every property in the tree is evaluated; nothing is skipped on
    failure. The truth of the tree is computed from the outcomes.

    :param seed: The run seed.
    :param spec: The specification to evaluate.
    :param allowance_for: Decides each property's allowance.
    :param on_start: Invoked when a property starts.
    :param on_outcome: Invoked with each property's outcome.

    :return: Whether the specification holds.

    :raises SpecificationError: When the specification cannot be resolved;
        raised before any property runs.
    """
    resolved_by_desc = {
        resolved.prop.desc: resolved for resolved in resolve_all(spec)
    }

    def _visit_prop(prop: Prop, negated: bool) -> bool:
        resolved = resolved_by_desc[prop.desc]
        on_start(prop)
        allowance = allowance_for(resolved)
        started = time.perf_counter()
        search = s.find_counter_example(
            property_rng(seed, prop.desc),
            prop.law,
            resolved.generators,
            allowance.max_attempts,
            allowance.deadline,
        )
        duration = time.perf_counter() - started
        holds, error = _judge(resolved, search, negated)
        on_outcome(
            Outcome(
                prop.desc,
                negated,
                holds,
                duration,
                search.attempts,
                search.discards,
                search.counter_example,
                error,
            )
        )
        return holds

    def _visit(spec: Spec, negated: bool) -> bool:
        match spec:
            case Prop():
                return _visit_prop(spec, negated)
            case Neg(term):
                return _visit(term, not negated)
            case Conj(terms):
                # Evaluate every term; combine afterwards. Under negation
                # the conjunction holds when any negated term holds.
                results = [_visit(term, negated) for term in terms]
                return any(results) if negated else all(results)
            case _:
                assert_never(spec)

    return _visit(spec, False)
