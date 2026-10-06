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
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
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
    """

    args: dict[str, Any]
    attempt: int
    exception: Exception | None = None
    shrinks: int = 0
    minimal: bool = True


@dataclass(frozen=True, slots=True)
class Search:
    """The outcome of a counterexample search.

    :param attempts: Attempts performed, including discarded ones.
    :param discards: Attempts whose arguments were rejected, by a filtered
        generator or by the law.
    :param counter_example: The counterexample found, if any.
    """

    attempts: int
    discards: int
    counter_example: CounterExample | None

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


def _trim(
    law: Law,
    dissection: s.Dissection[dict[str, Any]],
    exception: Exception | None,
    deadline: float | None = None,
) -> tuple[dict[str, Any], Exception | None, int, bool]:
    """Walk to a locally minimal dissection failing in the same way.

    Each candidate is evaluated once; the exception of the last accepted
    candidate is kept so the report matches the arguments shown. No
    candidate is evaluated past the deadline.

    :return: The arguments, their exception, the steps taken and whether
        the arguments are locally minimal.
    """
    steps = 0
    while True:
        for child in dissection.shrinks():
            if deadline is not None and time.perf_counter() >= deadline:
                return dissection.head, exception, steps, False
            result = _evaluate(law, child.head)
            if result is None:
                continue
            holds, child_exception = result
            if holds or not _same_failure(exception, child_exception):
                continue
            dissection, exception = child, child_exception
            steps += 1
            break
        else:
            return dissection.head, exception, steps, True


def find_counter_example(
    rng: a.Rng,
    law: Law,
    generators: dict[str, g.Generator[Any]],
    max_attempts: int,
    deadline: float | None = None,
    shrink_deadline: float | None = None,
    on_found: OnFound | None = None,
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

    :return: The search outcome.
    """
    arguments = g.argument_pack(generators)
    discards = 0
    for attempt in range(max_attempts):
        if (
            attempt > discards
            and deadline is not None
            and time.perf_counter() >= deadline
        ):
            return Search(attempt, discards, None)
        dissection = arguments.sample(rng)
        result = None if dissection is None else _evaluate(law, dissection.head)
        if dissection is None or result is None:
            discards += 1
            continue
        holds, exception = result
        if holds:
            continue
        if on_found is not None:
            on_found(CounterExample(dissection.head, attempt, exception))
        args, exception, shrinks, minimal = _trim(
            law, dissection, exception, shrink_deadline
        )
        return Search(
            attempt + 1,
            discards,
            CounterExample(args, attempt, exception, shrinks, minimal),
        )
    return Search(max_attempts, discards, None)
