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

A law whose precondition involves several parameters rejects arguments
outside it with ``assume``; a property that is expensive or statistical
says how many attempts it is worth with ``@prop(desc, attempts=n)``.

A law labels its attempts with ``label``, and each outcome reports how
many tested attempts carried each label, so a run shows what the
generators produced. ``cover(fraction, condition, name)`` also requires a
label on a fraction of the attempts; a property whose attempts show with
overwhelming confidence that the requirement is unmet fails.

A property can be given recorded draws to replay: the run seed and attempt
index of failing draws from earlier runs, with the canonical text of what
they drew. A property's draws depend only on the seed and its description,
so each is drawn again exactly, and is evaluated before the property's own
attempts; one that draws something else than it recorded is stale, because
a generator changed, and the property fails.
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeGuard, assert_never, get_type_hints

from minigun import arbitrary as a
from minigun import canonical
from minigun import cardinality as c
from minigun import generate as g
from minigun import search as s
from minigun import shrink as sh
from minigun.search import Discard, assume, cover, discard, label


class SpecificationError(Exception):
    """A specification cannot be evaluated as written."""


__all__ = [
    "SpecificationError",
    "Discard",
    "assume",
    "discard",
    "label",
    "cover",
    "Prop",
    "Neg",
    "Conj",
    "Spec",
    "is_spec",
    "prop",
    "context",
    "neg",
    "conj",
    "Resolved",
    "collect",
    "leaves",
    "combine",
    "select",
    "resolve",
    "resolve_all",
    "MAX_DISCARD_RATIO",
    "COVERAGE_Z",
    "coverage_upper_bound",
    "coverage_shortfalls",
    "Allowance",
    "Outcome",
    "AllowanceFor",
    "Recorded",
    "RecordedFor",
    "OnStart",
    "OnOutcome",
    "OnFound",
    "property_rng",
    "drawn_text",
    "redraw",
    "first_arguments",
    "evaluate_property",
    "evaluate",
]


###############################################################################
# Specifications
###############################################################################
@dataclass(frozen=True)
class Prop:
    """A property: a described law with generators for its parameters.

    :param desc: The description; unique within a specification, and
        within a run of several.
    :param law: The law under test, called with keyword arguments.
    :param generators: A generator per parameter in signature order, None
        where none was inferred or supplied.
    :param attempts: The number of attempts the property is worth, or None
        to derive it from the size of its argument domain.
    """

    desc: str
    law: Callable[..., bool]
    generators: dict[str, g.Generator[Any] | None]
    attempts: int | None = None

    @property
    def parameters(self) -> list[str]:
        """The law's parameter names in signature order."""
        return list(self.generators)


@dataclass(frozen=True)
class Neg:
    """The negation of a specification: holds when its term fails."""

    spec: Spec


@dataclass(frozen=True)
class Conj:
    """The conjunction of specifications: holds when every term holds."""

    specs: tuple[Spec, ...]


#: A specification: a tree of properties under negation and conjunction.
type Spec = Prop | Neg | Conj


def is_spec(value: object) -> TypeGuard[Spec]:
    """Whether a value is a specification."""
    return isinstance(value, Prop | Neg | Conj)


def prop(
    desc: str, attempts: int | None = None
) -> Callable[[Callable[..., bool]], Prop]:
    """Decorate a law as a property.

    Generators are inferred from the law's parameter annotations; a
    parameter whose annotation is missing or unsupported has no generator
    until ``@context`` supplies one.

    :param desc: A description of the law.
    :param attempts: The number of attempts the property is worth. By
        default it is derived from the size of the argument domain, which
        gives every property over an unbounded domain the same number; set
        it for properties whose attempts are expensive or statistical. It
        is the attempt count of ``check`` and of a budgeted run, where the
        property makes every attempt even past its share of the time; the
        other properties leave it one share of room.

    :raises ValueError: When ``attempts`` is not positive.
    :raises SpecificationError: When the law's annotations cannot be
        resolved.
    """
    if attempts is not None and attempts < 1:
        raise ValueError(f"prop requires attempts >= 1, got {attempts}")

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
        return Prop(desc, law, generators, attempts)

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
        return dataclasses.replace(spec, generators=generators)

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


def leaves(spec: Spec) -> list[tuple[Prop, bool]]:
    """The properties of a specification in evaluation order, each with
    whether it is evaluated under negation."""

    def _visit(spec: Spec, negated: bool) -> list[tuple[Prop, bool]]:
        match spec:
            case Prop():
                return [(spec, negated)]
            case Neg(term):
                return _visit(term, not negated)
            case Conj(terms):
                return [
                    leaf for term in terms for leaf in _visit(term, negated)
                ]
            case _:
                assert_never(spec)

    return _visit(spec, False)


def combine(spec: Spec, holds: Callable[[str], bool]) -> bool:
    """The truth of a specification from whether each property held,
    negation applied, as its outcome reports it.

    :param holds: Whether the property of a description held.
    """

    def _visit(spec: Spec, negated: bool) -> bool:
        match spec:
            case Prop():
                return holds(spec.desc)
            case Neg(term):
                return _visit(term, not negated)
            case Conj(terms):
                # Under negation the conjunction holds when any negated
                # term holds.
                results = [_visit(term, negated) for term in terms]
                return any(results) if negated else all(results)
            case _:
                assert_never(spec)

    return _visit(spec, False)


def select(spec: Spec, keep: Callable[[Prop], bool]) -> Spec | None:
    """The part of a specification made of the properties it keeps.

    Negations and conjunctions are kept around the kept properties, so
    each is evaluated under the same negation as in the whole
    specification; a conjunction holds or fails over the kept terms only.

    :return: The pruned specification, or None when no property is kept.
    """
    match spec:
        case Prop():
            return spec if keep(spec) else None
        case Neg(term):
            kept = select(term, keep)
            return None if kept is None else Neg(kept)
        case Conj(terms):
            selected = [select(term, keep) for term in terms]
            kept_terms = tuple(term for term in selected if term is not None)
            return Conj(kept_terms) if kept_terms else None
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
        attempt starts once the law has been evaluated, or None. Attempts
        continue past it until one is not discarded.
    :param shrink_deadline: A ``time.perf_counter`` instant after which no
        shrunk candidate of a counterexample is evaluated, or None.
    """

    max_attempts: int
    deadline: float | None = None
    shrink_deadline: float | None = None


@dataclass(frozen=True)
class Recorded:
    """A failing draw recorded by an earlier run.

    :param seed: The seed of the run that drew it.
    :param attempt: The zero-based index of the attempt that drew it.
    :param drawn: The canonical text of the arguments it drew by name
        (``drawn_text``), which its replay must draw again.
    """

    seed: int
    attempt: int
    drawn: dict[str, str]


@dataclass(frozen=True)
class Outcome:
    """The outcome of evaluating one property.

    :param desc: The property's description.
    :param negated: Whether the property was evaluated under negation.
    :param holds: Whether the property held, negation applied.
    :param duration: Wall-clock seconds spent.
    :param attempts: Attempts performed, including discards.
    :param discards: Attempts whose arguments were rejected, by a filtered
        generator or by the law through ``assume``.
    :param counter_example: The counterexample found, if any.
    :param error: Why the property did not hold when the reason is not a
        counterexample: no counterexample where one was expected, too
        many discards, or unmet coverage.
    :param labels: Per label, the attempts on which the law was evaluated
        and gave it.
    :param coverage: The required fraction of each covered label.
    :param replayed: Recorded draws replayed before the attempts on which
        the law was evaluated.
    :param stale: Recorded draws that no longer draw the arguments they
        drew when recorded, so a generator changed; they are not replayed
        and the property does not hold.
    """

    desc: str
    negated: bool
    holds: bool
    duration: float
    attempts: int
    discards: int
    counter_example: s.CounterExample | None
    error: str | None
    labels: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, float] = field(default_factory=dict)
    replayed: int = 0
    stale: tuple[Recorded, ...] = ()

    @property
    def evaluations(self) -> int:
        """Attempts on which the law was actually evaluated."""
        return self.attempts - self.discards


#: Decides the allowance of a resolved property.
type AllowanceFor = Callable[[Resolved], Allowance]

#: The recorded draws a property replays before its own attempts.
type RecordedFor = Callable[[Prop], Sequence[Recorded]]

#: Invoked when evaluation of a property starts.
type OnStart = Callable[[Prop], None]

#: Invoked with the outcome of a property.
type OnOutcome = Callable[[Outcome], None]

#: Invoked when a counterexample falsifying a property is found, before it
#: is shrunk.
type OnFound = Callable[[Prop, s.CounterExample], None]


def property_rng(seed: int, desc: str) -> a.Rng:
    """The random source of a property in a run.

    Derived from the run seed and the description alone, so a property
    draws the same values regardless of what else the run contains.
    """
    return a.seed(f"{seed}\x1f{desc}")


#: The z score of the coverage test: a requirement fails when the upper
#: bound of the Wilson score interval at this z lies below it. About six
#: standard deviations, so a property whose true fraction meets its
#: requirement fails on it in fewer than one run in a billion.
COVERAGE_Z = 6.0


def coverage_upper_bound(hits: int, evaluations: int) -> float:
    """The upper bound of the Wilson score interval, at ``COVERAGE_Z``, of
    the fraction of draws in a class seen ``hits`` times in
    ``evaluations`` draws.

    :raises ValueError: When ``evaluations`` is not positive or ``hits``
        is outside ``0..evaluations``.
    """
    if evaluations < 1 or not 0 <= hits <= evaluations:
        raise ValueError(
            "coverage_upper_bound requires 0 <= hits <= evaluations and "
            f"evaluations >= 1, got {hits} of {evaluations}"
        )
    n = evaluations
    p = hits / n
    z2 = COVERAGE_Z * COVERAGE_Z
    centre = p + z2 / (2 * n)
    spread = COVERAGE_Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    # The bound is never below the observed fraction; rounding can put
    # it there by an ulp when every draw was in the class.
    return max(p, min(1.0, (centre + spread) / (1 + z2 / n)))


def coverage_shortfalls(
    labels: dict[str, int], coverage: dict[str, float], evaluations: int
) -> list[str]:
    """The covered labels whose requirement the attempts show is unmet,
    in the order they were first required."""
    if evaluations < 1:
        return []
    return [
        name
        for name, required in coverage.items()
        if coverage_upper_bound(labels.get(name, 0), evaluations) < required
    ]


def _judge(
    resolved: Resolved, search: s.Search, negated: bool
) -> tuple[bool, str | None]:
    """Decide whether a property held from its search, negation applied."""
    desc = resolved.prop.desc
    example = search.counter_example
    # A replayed counterexample was found before any attempt was made.
    replayed = example is not None and example.seed is not None
    if not replayed and (
        search.evaluations == 0
        or search.discards > MAX_DISCARD_RATIO * search.attempts
    ):
        return False, (
            f'Property "{desc}" was not tested: {search.discards} of '
            f"{search.attempts} attempts were discarded by its generators "
            "or assumptions"
        )
    if search.counter_example is None:
        if negated:
            return False, (
                f'Found no counter example for "{desc}" however one was '
                "expected"
            )
        shortfalls = coverage_shortfalls(
            search.labels, search.coverage, search.evaluations
        )
        if shortfalls:
            details = "; ".join(
                f'"{name}" on {search.labels.get(name, 0)} '
                f"({100 * search.labels.get(name, 0) / search.evaluations:.1f}%)"
                f", required {100 * search.coverage[name]:g}%"
                for name in shortfalls
            )
            return False, (
                f'Property "{desc}" did not reach its coverage over '
                f"{search.evaluations} tested attempts: {details}"
            )
        return True, None
    return negated, None


def drawn_text(
    dissection: sh.Dissection[dict[str, Any]] | None,
) -> dict[str, str] | None:
    """The canonical text of drawn arguments by name, or None for a
    discarded draw."""
    if dissection is None:
        return None
    return {
        name: canonical.text(value) for name, value in dissection.head.items()
    }


def redraw(resolved: Resolved, seed: int, attempt: int) -> s.Replay:
    """Draw an attempt of a property in a run again.

    The attempts of a run draw in sequence from the property's source, and
    the law never draws from it, so the attempts before the recorded one
    are drawn and dropped without evaluating the law.

    :param resolved: The property.
    :param seed: The seed of the run.
    :param attempt: The zero-based index of the attempt.

    :raises ValueError: When the attempt index is negative.
    """
    if attempt < 0:
        raise ValueError(f"redraw requires attempt >= 0, got {attempt}")
    rng = property_rng(seed, resolved.prop.desc)
    arguments = g.argument_pack(resolved.generators)
    for _ in range(attempt):
        arguments.sample(rng)
    return s.Replay(seed, attempt, arguments.sample(rng))


def first_arguments(
    resolved: Resolved, seed: int, n: int
) -> list[dict[str, Any]]:
    """The arguments of the first ``n`` attempts of a property in a run
    with the given seed whose draws its generators keep, for looking at
    what the property is tested with.

    These are the arguments the run's attempts draw, in order, skipping
    draws a generator discards; an attempt whose arguments the law
    rejects with ``assume`` is included, since the law is not evaluated.

    :raises ValueError: When ``n`` is negative, or when the generators
        discard so many draws that ``n`` arguments take more than
        ``generate.EXAMPLE_DRAWS_PER_VALUE * n`` draws.
    """
    if n < 0:
        raise ValueError(f"first_arguments requires n >= 0, got {n}")
    rng = property_rng(seed, resolved.prop.desc)
    arguments = g.argument_pack(resolved.generators)
    kept: list[dict[str, Any]] = []
    draws = g.EXAMPLE_DRAWS_PER_VALUE * n
    for _ in range(draws):
        if len(kept) == n:
            break
        dissection = arguments.sample(rng)
        if dissection is not None:
            kept.append(dissection.head)
    if len(kept) < n:
        raise ValueError(
            f'The generators of "{resolved.prop.desc}" discarded all but '
            f"{len(kept)} of {draws} draws; {n} arguments were requested"
        )
    return kept


def evaluate_property(
    seed: int,
    resolved: Resolved,
    negated: bool,
    allowance: Allowance,
    on_found: Callable[[s.CounterExample], None] | None = None,
    recorded: Sequence[Recorded] = (),
) -> Outcome:
    """Evaluate one property of a run.

    :param seed: The run seed.
    :param resolved: The property.
    :param negated: Whether it is evaluated under negation.
    :param allowance: What it may spend.
    :param on_found: Invoked when a counterexample is found that makes the
        property fail, before it is shrunk; never invoked under negation.
    :param recorded: Failing draws recorded by earlier runs, drawn again
        and replayed in order before the property's own attempts. One that
        no longer draws its recorded arguments is stale: it is not
        replayed, and the property does not hold.
    """
    prop = resolved.prop
    started = time.perf_counter()
    replays: list[s.Replay] = []
    stale: list[Recorded] = []
    for entry in recorded:
        replay = redraw(resolved, entry.seed, entry.attempt)
        if drawn_text(replay.dissection) == entry.drawn:
            replays.append(replay)
        else:
            stale.append(entry)
    search = s.find_counter_example(
        property_rng(seed, prop.desc),
        prop.law,
        resolved.generators,
        allowance.max_attempts,
        allowance.deadline,
        allowance.shrink_deadline,
        None if negated else on_found,
        replays,
    )
    duration = time.perf_counter() - started
    holds, error = _judge(resolved, search, negated)
    if stale:
        holds = False
        error = _stale_error(prop.desc, stale) + (
            "" if error is None else f"\n{error}"
        )
    return Outcome(
        prop.desc,
        negated,
        holds,
        duration,
        search.attempts,
        search.discards,
        search.counter_example,
        error,
        search.labels,
        search.coverage,
        search.replayed,
        tuple(stale),
    )


def _stale_error(desc: str, stale: list[Recorded]) -> str:
    entries = ", ".join(
        f"attempt {entry.attempt + 1} of seed {entry.seed}" for entry in stale
    )
    return (
        f'Property "{desc}" has recorded counter examples that no longer '
        "draw the arguments they drew when recorded, so one of its "
        f"generators changed: {entries}. They no longer cover the failures "
        "they recorded; remove them from the regressions file"
    )


def evaluate(
    seed: int,
    spec: Spec,
    allowance_for: AllowanceFor,
    on_start: OnStart,
    on_outcome: OnOutcome,
    on_found: OnFound | None = None,
    recorded_for: RecordedFor | None = None,
) -> bool:
    """Evaluate a specification, reporting every property's outcome.

    Every property in the tree is evaluated, in the order of ``leaves``;
    nothing is skipped on failure. The truth of the tree is computed from
    the outcomes.

    :param seed: The run seed.
    :param spec: The specification to evaluate.
    :param allowance_for: Decides each property's allowance.
    :param on_start: Invoked when a property starts.
    :param on_outcome: Invoked with each property's outcome.
    :param on_found: Invoked when a counterexample is found that makes a
        property fail, before it is shrunk, so a run whose shrinking is
        slow can say what failed. Not invoked under negation, where a
        counterexample is what the property expects.
    :param recorded_for: The recorded draws each property replays before
        its own attempts; none when omitted.

    :return: Whether the specification holds.

    :raises SpecificationError: When the specification cannot be resolved;
        raised before any property runs.
    """
    resolved_by_desc = {
        resolved.prop.desc: resolved for resolved in resolve_all(spec)
    }
    held: dict[str, bool] = {}
    for prop, negated in leaves(spec):
        resolved = resolved_by_desc[prop.desc]
        on_start(prop)
        outcome = evaluate_property(
            seed,
            resolved,
            negated,
            allowance_for(resolved),
            None if on_found is None else functools.partial(on_found, prop),
            () if recorded_for is None else recorded_for(prop),
        )
        held[prop.desc] = outcome.holds
        on_outcome(outcome)
    return combine(spec, held.__getitem__)
