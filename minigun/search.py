"""
Counterexample search

Draw arguments, evaluate the law, and on failure shrink the arguments to a
locally minimal counterexample: one none of whose immediate alternatives
fails. Every candidate is evaluated exactly once. An exception raised by
the law counts as a failure and is reported with the counterexample.

Each attempt draws from a fresh child of the property's random source, so
an attempt is reproducible from the property's seed and its index alone.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from minigun import arbitrary as a
from minigun import generate as g
from minigun import shrink as s

#: A law under test: a callable over keyword arguments returning truth.
type Law = Callable[..., bool]


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
    """

    args: dict[str, Any]
    attempt: int
    exception: Exception | None = None


@dataclass(frozen=True, slots=True)
class Search:
    """The outcome of a counterexample search.

    :param attempts: Attempts performed, including discarded ones.
    :param discards: Attempts whose argument generation was rejected.
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
def _evaluate(law: Law, args: dict[str, Any]) -> tuple[bool, Exception | None]:
    """Evaluate a law once; an exception is a failed evaluation."""
    try:
        return law(**args), None
    except Exception as exception:
        return False, exception


def _trim(
    law: Law,
    dissection: s.Dissection[dict[str, Any]],
    exception: Exception | None,
) -> tuple[dict[str, Any], Exception | None]:
    """Walk to a locally minimal failing dissection.

    Each candidate is evaluated once; the exception of the last accepted
    candidate is kept so the report matches the arguments shown.
    """
    while True:
        for child in dissection.shrinks():
            holds, child_exception = _evaluate(law, child.head)
            if holds:
                continue
            dissection, exception = child, child_exception
            break
        else:
            return dissection.head, exception


def find_counter_example(
    rng: a.Rng,
    law: Law,
    generators: dict[str, g.Generator[Any]],
    max_attempts: int,
    deadline: float | None = None,
) -> Search:
    """Search for a counterexample to a law.

    :param rng: The property's random source; one child is forked per
        attempt.
    :param law: The law under test.
    :param generators: Generators for the law's parameters by name.
    :param max_attempts: The maximum number of attempts.
    :param deadline: A ``time.perf_counter`` instant after which no further
        attempt starts, or None for no deadline. The first attempt always
        runs.

    :return: The search outcome.
    """
    arguments = g.argument_pack(generators)
    discards = 0
    for attempt in range(max_attempts):
        if (
            attempt > 0
            and deadline is not None
            and time.perf_counter() >= deadline
        ):
            return Search(attempt, discards, None)
        dissection = arguments.sample(a.fork(rng))
        if dissection is None:
            discards += 1
            continue
        holds, exception = _evaluate(law, dissection.head)
        if holds:
            continue
        args, exception = _trim(law, dissection, exception)
        return Search(
            attempt + 1, discards, CounterExample(args, attempt, exception)
        )
    return Search(max_attempts, discards, None)
