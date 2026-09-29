"""Properties of specifications and their evaluation, modeled as trees."""

import random
import time
from dataclasses import dataclass
from typing import Any, assert_never

import minigun.generate as g
import minigun.specify as sp
from minigun import assume, check
from minigun.specify import Spec, conj, context, neg, prop

###############################################################################
# Trees of constant properties
###############################################################################


@dataclass(frozen=True)
class Leaf:
    holds: bool


@dataclass(frozen=True)
class Not:
    inner: "Tree"


@dataclass(frozen=True)
class And:
    items: tuple["Tree", ...]


type Tree = Leaf | Not | And


def _sized(depth: int) -> g.Generator[Tree]:
    leaf: g.Generator[Tree] = g.map(Leaf, g.bools())
    if depth == 0:
        return leaf
    sub = _sized(depth - 1)

    def _and(items: list[Tree]) -> Tree:
        return And(tuple(items))

    return g.weighted_choice(
        (2, leaf),
        (1, g.map(Not, sub)),
        (2, g.map(_and, g.bounded_lists(0, 3, sub))),
    )


def trees() -> g.Generator[Tree]:
    return _sized(3)


def truth(tree: Tree) -> bool:
    match tree:
        case Leaf(holds):
            return holds
        case Not(inner):
            return not truth(inner)
        case And(items):
            return all(truth(item) for item in items)
        case _:
            assert_never(tree)


def expected_outcomes(tree: Tree, negated: bool = False) -> list[bool]:
    """Whether each leaf, in order, holds under its negation parity."""
    match tree:
        case Leaf(holds):
            return [holds != negated]
        case Not(inner):
            return expected_outcomes(inner, not negated)
        case And(items):
            return [
                outcome
                for item in items
                for outcome in expected_outcomes(item, negated)
            ]
        case _:
            assert_never(tree)


def build(tree: Tree) -> Spec:
    counter = 0

    def _build(node: Tree) -> Spec:
        nonlocal counter
        match node:
            case Leaf(holds):
                counter += 1

                @prop(f"leaf {counter}")
                def _leaf(x: int) -> bool:
                    return holds

                return _leaf
            case Not(inner):
                return neg(_build(inner))
            case And(items):
                return conj(*[_build(item) for item in items])
            case _:
                assert_never(node)

    return _build(tree)


def stable(outcome: sp.Outcome) -> tuple[Any, ...]:
    """An outcome without its wall-clock duration."""
    return (
        outcome.desc,
        outcome.negated,
        outcome.holds,
        outcome.attempts,
        outcome.discards,
        outcome.counter_example,
        outcome.error,
    )


def run(
    spec: Spec, seed: int, attempts: int = 5
) -> tuple[bool, list[sp.Outcome]]:
    outcomes: list[sp.Outcome] = []
    holds = sp.evaluate(
        seed,
        spec,
        lambda resolved: sp.Allowance(attempts),
        lambda p: None,
        outcomes.append,
    )
    return holds, outcomes


###############################################################################
# Evaluation of trees
###############################################################################


@context(trees())
@prop("evaluation agrees with the tree's truth value")
def _truth(tree: Tree, seed: int) -> bool:
    holds, _ = run(build(tree), seed)
    return holds == truth(tree)


@context(trees())
@prop("every property is reported exactly once, in order")
def _exhaustive(tree: Tree, seed: int) -> bool:
    _, outcomes = run(build(tree), seed)
    expected = expected_outcomes(tree)
    return [outcome.holds for outcome in outcomes] == expected and [
        outcome.desc for outcome in outcomes
    ] == [f"leaf {index}" for index in range(1, len(expected) + 1)]


@prop("an expected counterexample that is not found is reported as such")
def _neg_unmet(seed: int) -> bool:
    @prop("always holds")
    def _holds(x: int) -> bool:
        return True

    _, outcomes = run(neg(_holds), seed)
    outcome = outcomes[0]
    return (
        outcome.negated
        and not outcome.holds
        and outcome.error is not None
        and "expected" in outcome.error
    )


###############################################################################
# Reproducibility and independence
###############################################################################


def _threshold_prop(desc: str, threshold: int) -> Spec:
    @prop(desc)
    def _below(x: int) -> bool:
        return x < threshold

    return _below


@context(g.int_range(0, 1000))
@prop("evaluation is a function of the seed")
def _reproducible(threshold: int, seed: int) -> bool:
    spec = _threshold_prop("threshold", threshold)
    first_holds, first = run(spec, seed, 50)
    second_holds, second = run(spec, seed, 50)
    return first_holds == second_holds and [stable(o) for o in first] == [
        stable(o) for o in second
    ]


@context(g.int_range(1, 20), g.int_range(1, 20))
@prop("a property's outcome does not depend on its neighbours' allowances")
def _independent(first_attempts: int, second_attempts: int, seed: int) -> bool:
    def _run(neighbour_attempts: int) -> sp.Outcome:
        outcomes: list[sp.Outcome] = []
        sp.evaluate(
            seed,
            conj(
                _threshold_prop("neighbour", 0), _threshold_prop("subject", 100)
            ),
            lambda resolved: sp.Allowance(
                neighbour_attempts if resolved.prop.desc == "neighbour" else 50
            ),
            lambda p: None,
            outcomes.append,
        )
        return outcomes[1]

    return stable(_run(first_attempts)) == stable(_run(second_attempts))


@prop("the reported attempt index reproduces the counterexample")
def _attempt_index(seed: int) -> bool:
    spec = _threshold_prop("threshold", 100)
    _, outcomes = run(spec, seed, 50)
    example = outcomes[0].counter_example
    if example is None:
        return True
    rng = sp.property_rng(seed, "threshold")
    for _ in range(example.attempt):
        rng.getrandbits(64)
    _, replay = run(spec, seed, example.attempt + 1)
    return replay[0].counter_example == example


###############################################################################
# Discards
###############################################################################


@prop("a property whose generator rejects everything fails loudly")
def _discards(seed: int) -> bool:
    @context(g.filter(lambda x: False, g.ints()))
    @prop("never tested")
    def _never(x: int) -> bool:
        return True

    holds, outcomes = run(_never, seed)
    outcome = outcomes[0]
    return (
        not holds
        and outcome.error is not None
        and "discarded" in outcome.error
        and outcome.discards == outcome.attempts
    )


@prop("a property whose law rejects everything fails loudly")
def _assumptions(seed: int) -> bool:
    @prop("never accepted")
    def _never(x: int) -> bool:
        sp.assume(False)
        return True

    holds, outcomes = run(_never, seed)
    outcome = outcomes[0]
    return (
        not holds
        and outcome.error is not None
        and "discarded" in outcome.error
        and outcome.discards == outcome.attempts
    )


@context(g.int_range(1, 50), g.int_range(0, 50))
@prop("a property fails for discards exactly above the discard ratio")
def _discard_ratio(attempts: int, discarded: int, seed: int) -> bool:
    assume(discarded <= attempts)
    calls = 0

    @prop("partly discarded")
    def _partly(x: int) -> bool:
        nonlocal calls
        calls += 1
        sp.assume(calls > discarded)
        return True

    holds, outcomes = run(_partly, seed, attempts)
    tested = discarded < attempts
    within = discarded <= sp.MAX_DISCARD_RATIO * attempts
    return holds == (tested and within) and outcomes[0].discards == discarded


@context(trees())
@prop("reported durations lie within the wall time of the evaluation")
def _durations(tree: Tree, seed: int) -> bool:
    started = time.perf_counter()
    _, outcomes = run(build(tree), seed)
    elapsed = time.perf_counter() - started
    return all(0.0 <= o.duration <= elapsed for o in outcomes)


###############################################################################
# Declared attempts
###############################################################################


@context(g.int_range(1, 200))
@prop("check makes exactly the attempts a property declares")
def _declared_attempts(attempts: int, seed: int) -> bool:
    import contextlib
    import io

    calls = 0

    @prop("counted", attempts=attempts)
    def _counted(x: int) -> bool:
        nonlocal calls
        calls += 1
        return True

    with contextlib.redirect_stdout(io.StringIO()):
        holds = check(_counted, seed=seed)
    return holds and calls == attempts


@context(g.int_range(1, 200))
@prop("declared attempts survive context and set the budgeted limit")
def _declared_limit(attempts: int) -> bool:
    import minigun.budget as b

    @context(g.bools())
    @prop("declared", attempts=attempts)
    def _declared(x: int) -> bool:
        return True

    plans = b.plan(sp.resolve_all(_declared))
    return _declared.attempts == attempts and plans[0].attempt_limit == attempts


@context(g.choice(g.int_range(0, 1), g.int_range(-10, 10)))
@prop("prop accepts exactly the positive attempt counts")
def _declared_positive(attempts: int) -> bool:
    if attempts < 1:
        return _raises(lambda: prop("bad", attempts=attempts), ValueError)

    @prop("good", attempts=attempts)
    def _law(x: int) -> bool:
        return True

    return _law.attempts == attempts


###############################################################################
# Construction errors
###############################################################################


def _raises(action: Any, error: type[BaseException]) -> bool:
    try:
        action()
    except error:
        return True
    return False


@prop("duplicate descriptions are rejected before evaluation")
def _duplicates(seed: int) -> bool:
    spec = conj(_threshold_prop("same", 1), _threshold_prop("same", 2))
    return _raises(lambda: run(spec, seed), sp.SpecificationError)


@prop("a parameter without a generator is rejected before evaluation")
def _missing_generator(seed: int) -> bool:
    @prop("unannotated")
    def _law(x) -> bool:  # type: ignore[no-untyped-def]
        return True

    return _raises(lambda: run(_law, seed), sp.SpecificationError)


@prop("a law whose annotations cannot be resolved is rejected by prop")
def _unresolvable(seed: int) -> bool:
    def _law(x: "NoSuchType") -> bool:  # type: ignore[name-defined]  # noqa: F821
        return True

    return _raises(lambda: prop("unresolvable")(_law), sp.SpecificationError)


@prop("context validates its arguments")
def _context_validation(seed: int) -> bool:
    @prop("two parameters")
    def _law(x: int, y: int) -> bool:
        return True

    return (
        _raises(lambda: context(g.ints(), g.ints(), g.ints())(_law), TypeError)
        and _raises(lambda: context(z=g.ints())(_law), TypeError)
        and _raises(lambda: context(g.ints())(conj(_law)), TypeError)  # type: ignore[arg-type]
        and context(g.ints(), y=g.bools())(_law).generators["y"] is not None
    )


@prop("string annotations are resolved for inference")
def _string_annotations(rng: random.Random) -> bool:
    @prop("postponed annotation")
    def _law(x: "int") -> bool:
        return isinstance(x, int)

    generator = _law.generators["x"]
    if generator is None:
        return False
    dissection = generator.sample(rng)
    return dissection is not None and isinstance(dissection.head, int)


@prop("the standalone check prints failures and the seed")
def _check_prints(seed: int) -> bool:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        holds = check(_threshold_prop("threshold", -1), seed=seed)
    text = buffer.getvalue()
    return not holds and "FAIL: threshold" in text and str(seed) in text


spec = conj(
    _truth,
    _exhaustive,
    _neg_unmet,
    _reproducible,
    _independent,
    _attempt_index,
    _discards,
    _assumptions,
    _discard_ratio,
    _durations,
    _declared_attempts,
    _declared_limit,
    _declared_positive,
    _duplicates,
    _missing_generator,
    _unresolvable,
    _context_validation,
    _string_annotations,
    _check_prints,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
