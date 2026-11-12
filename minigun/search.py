"""
Counterexample search

Draw arguments, evaluate the law, and on failure shrink the arguments to a
locally minimal counterexample: one none of whose immediate alternatives
fails in the same way. Every candidate is evaluated exactly once. An
exception raised by the law counts as a failure and is reported with the
counterexample.

Shrinking preserves the kind of failure. A shrunk alternative is accepted
only when it fails as the found counterexample did: by returning False, or
by raising an exception of the same type. Without this a counterexample
found by a False result could shrink into arguments that merely crash the
law, and the report would describe a different failure than the one found.

Shrinking can be given a deadline. A shrunk candidate can cost far more to
evaluate than the counterexample it came from, and a walk of many such
candidates would hold the run long past its budget; past the deadline no
further candidate is evaluated and the smallest counterexample accepted so
far is reported, marked as not minimal. A candidate already being
evaluated is not interrupted.

Attempts draw in sequence from the property's random source, so the whole
sequence of draws is a function of the property's seed and the reported
attempt index identifies the failing draw within it. Forking a child per
attempt would make each attempt independent of the ones before it, but a
fresh ``random.Random`` costs several microseconds to initialise, more than
a cheap attempt itself.

A law can label its attempts with ``label`` and require that a label
covers a fraction of them with ``cover``. The search counts, per label,
the attempts on which the law was evaluated and gave it; a discarded
attempt's labels are dropped, and shrunk candidates are not counted.

A search can be given replays: failing draws recorded by earlier runs,
drawn again. They are evaluated before the search's own attempts, and one
that still fails is shrunk and reported like a counterexample the search
drew, marked with the seed of the run that recorded it. Replays are not
attempts, and their labels are not counted.

Every counterexample keeps its shrink path: the arguments found and those
of every accepted shrink step, so a report can show how it was reached.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, NoReturn

from minigun import arbitrary as a
from minigun import generate as g
from minigun import shrink as s

#: A law under test: a callable over keyword arguments returning truth.
type Law = Callable[..., bool]

#: Invoked with a counterexample as it is found, before it is shrunk.
type OnFound = Callable[[CounterExample], None]


__all__ = [
    "Law",
    "OnFound",
    "Discard",
    "assume",
    "discard",
    "label",
    "cover",
    "Replay",
    "CounterExample",
    "Search",
    "find_counter_example",
]


###############################################################################
# Preconditions
###############################################################################
class Discard(Exception):
    """Raised by a law to reject its arguments as outside its precondition."""


def assume(condition: bool) -> None:
    """Reject the law's arguments unless ``condition`` holds.

    For preconditions that involve several parameters, where a filtered
    generator would have to generate the parameters together::

        @prop("the increment law can be tabulated at the step size")
        def _tabulated(model: Model, dt: float) -> bool:
            assume(model.tabulable(dt))
            return check_table(model, dt)

    Rejected attempts count as discards, and a property most of whose
    attempts are discarded fails.

    :raises Discard: When ``condition`` is false.
    """
    if not condition:
        raise Discard()


def discard() -> NoReturn:
    """Reject the law's arguments unconditionally.

    :raises Discard: Always.
    """
    raise Discard()


###############################################################################
# Labels
###############################################################################
@dataclass(slots=True)
class _Recorder:
    """What the laws of a search label.

    :param given: The labels given on the current attempt.
    :param counts: Per label, the tested attempts that gave it.
    :param coverage: The property's coverage requirements, shared by all
        of its attempts.
    """

    given: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, float] = field(default_factory=dict)


#: The recorder of the attempt being evaluated, None outside a search and
#: while shrinking. A context variable, so a search run by a law (a test of
#: minigun itself) records into its own recorder and restores the outer one.
_RECORDER: ContextVar[_Recorder | None] = ContextVar(
    "minigun_recorder", default=None
)


def label(name: str) -> None:
    """Label the current attempt.

    A property's outcome reports, per label, how many of its tested
    attempts were given it, so a run shows what the generators actually
    produced::

        @prop("lookup finds an inserted key")
        def _lookup(key: int, m: dict[int, str]) -> bool:
            label("present" if key in m else "absent")
            ...

    Labelling an attempt twice with the same name counts once. Outside a
    search, such as when a law is called directly or while a
    counterexample is being shrunk, the call does nothing.

    :raises TypeError: When ``name`` is not a string.
    """
    if not isinstance(name, str):
        raise TypeError(
            f"label requires a string name, got {type(name).__name__}"
        )
    recorder = _RECORDER.get()
    if recorder is not None:
        recorder.given.add(name)


def cover(fraction: float, condition: bool, name: str) -> None:
    """Require that at least ``fraction`` of the attempts satisfy
    ``condition``, labelling the current attempt ``name`` when it does.

    ::

        cover(0.2, key in m, "present")

    The property fails when its tested attempts show, with overwhelming
    confidence, that the condition holds on less than ``fraction`` of the
    draws; a run too short to tell does not fail on it. The requirement
    is checked only when no counterexample was found. Outside a search
    the call does nothing beyond checking its arguments.

    :param fraction: The required fraction, ``0 < fraction <= 1``.
    :param condition: Whether the current attempt is in the covered class.
    :param name: The label of the class.

    :raises ValueError: When ``fraction`` is out of range, or when a law
        requires two different fractions of the same label.
    :raises TypeError: When ``name`` is not a string.
    """
    if not 0.0 < fraction <= 1.0:
        raise ValueError(
            f"cover requires 0 < fraction <= 1, got {fraction}; a "
            "percentage must be given as a fraction"
        )
    if not isinstance(name, str):
        raise TypeError(
            f"cover requires a string name, got {type(name).__name__}"
        )
    recorder = _RECORDER.get()
    if recorder is None:
        return
    required = recorder.coverage.setdefault(name, fraction)
    if required != fraction:
        raise ValueError(
            f'cover requires {required} of label "{name}" and also '
            f"{fraction}; a label has one requirement"
        )
    if condition:
        recorder.given.add(name)


###############################################################################
# Results
###############################################################################
@dataclass(frozen=True, slots=True)
class CounterExample:
    """Arguments falsifying a law.

    :param args: The counterexample arguments by parameter name.
    :param attempt: The zero-based attempt index that found it.
    :param exception: The exception the law raised on these arguments, when
        the failure was an exception rather than a False result.
    :param shrinks: The shrink steps taken from the arguments first found.
    :param minimal: Whether shrinking reached a locally minimal
        counterexample; False when it stopped at its deadline.
    :param path: The arguments first found followed by those of every
        accepted shrink step, ending with ``args``; empty when the
        counterexample has not been shrunk yet, as when it is announced.
    :param seed: The seed of the earlier run whose recorded draw this
        counterexample replays, ``attempt`` being its index in that run;
        None when the search drew it.
    """

    args: dict[str, Any]
    attempt: int
    exception: Exception | None = None
    shrinks: int = 0
    minimal: bool = True
    path: tuple[dict[str, Any], ...] = ()
    seed: int | None = None


@dataclass(frozen=True, slots=True)
class Replay:
    """A failing draw recorded by an earlier run, drawn again to be
    evaluated before a search's own attempts.

    :param seed: The seed of the run that recorded it.
    :param attempt: The zero-based index of the attempt that drew it.
    :param dissection: The arguments drawn again, or None when the
        generators now discard them.
    """

    seed: int
    attempt: int
    dissection: s.Dissection[dict[str, Any]] | None


@dataclass(frozen=True, slots=True)
class Search:
    """The outcome of a counterexample search.

    :param attempts: Attempts performed, including discarded ones.
    :param discards: Attempts whose arguments were rejected, by a filtered
        generator or by the law.
    :param counter_example: The counterexample found, if any.
    :param labels: Per label, the attempts on which the law was evaluated
        and gave it.
    :param coverage: The required fraction of each covered label.
    :param replayed: Replays on which the law was evaluated; a replay
        whose arguments the generators or the law reject is skipped.
    """

    attempts: int
    discards: int
    counter_example: CounterExample | None
    labels: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, float] = field(default_factory=dict)
    replayed: int = 0

    @property
    def evaluations(self) -> int:
        """Attempts on which the law was actually evaluated."""
        return self.attempts - self.discards


###############################################################################
# Evaluation and trimming
###############################################################################
def _evaluate(
    law: Law, args: dict[str, Any]
) -> tuple[bool, Exception | None] | None:
    """Evaluate a law once; an exception is a failed evaluation.

    :return: Whether the law held and the exception it raised, or None
        when the law discarded the arguments.
    """
    try:
        return law(**args), None
    except Discard:
        return None
    except Exception as exception:
        return False, exception


def _same_failure(found: Exception | None, other: Exception | None) -> bool:
    """Whether two failed evaluations failed in the same way: both by
    returning False, or both by raising the same type of exception."""
    if found is None or other is None:
        return found is other
    return type(found) is type(other)


@dataclass(frozen=True, slots=True)
class _Failure:
    """A failing draw, before it is shrunk."""

    dissection: s.Dissection[dict[str, Any]]
    attempt: int
    exception: Exception | None
    seed: int | None


def _trim(
    law: Law, failure: _Failure, deadline: float | None = None
) -> CounterExample:
    """Walk to a locally minimal dissection failing in the same way.

    Each candidate is evaluated once; the exception of the last accepted
    candidate is kept so the report matches the arguments shown. No
    candidate is evaluated past the deadline. Labels given by the
    candidates are not recorded.
    """
    dissection, exception = failure.dissection, failure.exception
    path = [dissection.head]

    def _example(minimal: bool) -> CounterExample:
        return CounterExample(
            dissection.head,
            failure.attempt,
            exception,
            len(path) - 1,
            minimal,
            tuple(path),
            failure.seed,
        )

    token = _RECORDER.set(None)
    try:
        while True:
            for child in dissection.shrinks():
                if deadline is not None and time.perf_counter() >= deadline:
                    return _example(False)
                result = _evaluate(law, child.head)
                if result is None:
                    continue
                holds, child_exception = result
                if holds or not _same_failure(exception, child_exception):
                    continue
                dissection, exception = child, child_exception
                path.append(dissection.head)
                break
            else:
                return _example(True)
    finally:
        _RECORDER.reset(token)


def find_counter_example(
    rng: a.Rng,
    law: Law,
    generators: dict[str, g.Generator[Any]],
    max_attempts: int,
    deadline: float | None = None,
    shrink_deadline: float | None = None,
    on_found: OnFound | None = None,
    replays: Sequence[Replay] = (),
) -> Search:
    """Search for a counterexample to a law.

    :param rng: The property's random source, advanced by every attempt.
    :param law: The law under test.
    :param generators: Generators for the law's parameters by name.
    :param max_attempts: The maximum number of attempts.
    :param deadline: A ``time.perf_counter`` instant after which no further
        attempt starts once the law has been evaluated, or None for no
        deadline. Attempts continue past it until one is not discarded, so
        a search cut short by the budget has still tested the law; the
        attempt limit bounds them.
    :param shrink_deadline: A ``time.perf_counter`` instant after which no
        shrunk candidate is evaluated, or None for no deadline.
    :param on_found: Invoked with the counterexample as found, before it
        is shrunk.
    :param replays: Recorded failing draws, evaluated in order before the
        attempts; the first that still fails is the counterexample and no
        attempt is made.

    :return: The search outcome.
    """
    failure, replayed = _replay(law, replays)
    attempts = discards = 0
    recorder = _Recorder()
    if failure is None:
        # The recorder is set once for all attempts rather than per
        # attempt, which would cost a cheap law several percent of its
        # attempt rate.
        token = _RECORDER.set(recorder)
        try:
            attempts, discards, failure = _attempts(
                rng, law, generators, max_attempts, deadline, recorder
            )
        finally:
            _RECORDER.reset(token)
    labels, coverage = recorder.counts, recorder.coverage
    if failure is None:
        return Search(attempts, discards, None, labels, coverage, replayed)
    if on_found is not None:
        on_found(
            CounterExample(
                failure.dissection.head,
                failure.attempt,
                failure.exception,
                seed=failure.seed,
            )
        )
    return Search(
        attempts,
        discards,
        _trim(law, failure, shrink_deadline),
        labels,
        coverage,
        replayed,
    )


def _replay(law: Law, replays: Sequence[Replay]) -> tuple[_Failure | None, int]:
    """Evaluate the replays in order, labels unrecorded.

    :return: The first replay that fails, if any, and the replays on which
        the law was evaluated.
    """
    replayed = 0
    token = _RECORDER.set(None)
    try:
        for replay in replays:
            if replay.dissection is None:
                continue
            result = _evaluate(law, replay.dissection.head)
            if result is None:
                continue
            replayed += 1
            holds, exception = result
            if not holds:
                return _Failure(
                    replay.dissection, replay.attempt, exception, replay.seed
                ), replayed
    finally:
        _RECORDER.reset(token)
    return None, replayed


def _attempts(
    rng: a.Rng,
    law: Law,
    generators: dict[str, g.Generator[Any]],
    max_attempts: int,
    deadline: float | None,
    recorder: _Recorder,
) -> tuple[int, int, _Failure | None]:
    """The attempts of ``find_counter_example``, counting the labels of
    the tested ones in the recorder.

    :return: The attempts made, the discards among them, and the failing
        draw, if an attempt failed.
    """
    arguments = g.argument_pack(generators)
    discards = 0
    for attempt in range(max_attempts):
        if (
            attempt > discards
            and deadline is not None
            and time.perf_counter() >= deadline
        ):
            return attempt, discards, None
        dissection = arguments.sample(rng)
        recorder.given.clear()
        result = None if dissection is None else _evaluate(law, dissection.head)
        if dissection is None or result is None:
            discards += 1
            continue
        for name in recorder.given:
            recorder.counts[name] = recorder.counts.get(name, 0) + 1
        holds, exception = result
        if not holds:
            return (
                attempt + 1,
                discards,
                _Failure(dissection, attempt, exception, None),
            )
    return max_attempts, discards, None
