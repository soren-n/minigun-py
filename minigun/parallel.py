"""
Parallel evaluation

Evaluates the properties of a run in worker processes, several at a time.
A property's outcome depends only on the run seed, its description and its
allowance, so which worker evaluates it changes nothing it draws.

Workers are started with ``spawn`` on every platform and rebuild the run's
specifications from a loader per module: a picklable callable returning
the module's specification. Outcomes are reported in the order a
sequential run reports them; the property at the head of that order is
reported live, the others when their turn comes. A counterexample
argument or exception that does not survive pickling is sent back by its
``repr``.
"""

from __future__ import annotations

import atexit
import contextlib
import dataclasses
import multiprocessing
import multiprocessing.util
import pickle
import queue
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor
from concurrent.futures import wait as wait_futures
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from minigun import fixture, specify
from minigun.search import CounterExample
from minigun.specify import Allowance, Outcome, Prop, Resolved, Spec

if TYPE_CHECKING:
    from minigun.reporter import Reporter

__all__ = [
    "SpecLoader",
    "RemoteException",
    "Shown",
    "portable",
    "evaluate",
]


#: Rebuilds a module's specification in a worker process; must be
#: picklable, e.g. a module-level function or a ``functools.partial`` of one.
type SpecLoader = Callable[[], Spec]


###############################################################################
# Values sent back from workers
###############################################################################
class RemoteException(Exception):
    """An exception a law raised in a worker that could not be sent back
    as itself.

    :param type_name: The name of the exception's type.
    :param message: The exception's message.
    """

    def __init__(self, type_name: str, message: str):
        super().__init__(message)
        self.type_name = type_name

    def __reduce__(self) -> tuple[Any, ...]:
        return (RemoteException, (self.type_name, str(self)))


class Shown:
    """A counterexample argument that could not be sent back from a
    worker, standing in for it by its ``repr``."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self) -> str:
        return self.text

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Shown) and other.text == self.text

    def __hash__(self) -> int:
        return hash(self.text)


def _round_trips(value: Any) -> bool:
    try:
        pickle.loads(pickle.dumps(value))
    except Exception:
        return False
    return True


def portable(example: CounterExample) -> CounterExample:
    """A counterexample that can be sent from a worker: arguments and an
    exception that do not survive pickling are replaced by their text."""
    args = {
        name: value if _round_trips(value) else Shown(repr(value))
        for name, value in example.args.items()
    }
    exception = example.exception
    if exception is not None and not _round_trips(exception):
        exception = RemoteException(type(exception).__name__, str(exception))
    return dataclasses.replace(example, args=args, exception=exception)


###############################################################################
# Workers
###############################################################################
@dataclass(frozen=True)
class _Task:
    """A property to evaluate, with deadlines as ``time.time`` instants:
    ``perf_counter`` instants are not comparable between processes."""

    desc: str
    negated: bool
    max_attempts: int
    deadline: float | None
    shrink_deadline: float | None


@dataclass(frozen=True)
class _Done:
    """What a worker sends back for a task."""

    outcome: Outcome
    found: CounterExample | None
    paths: list[Path]


@dataclass
class _Worker:
    seed: int
    resolved: dict[str, Resolved]
    found: Any


_worker: _Worker | None = None

# Keeps a fixture scope open for the worker's lifetime; the paths created
# in it are detached after each task and removed by the run.
_scope = contextlib.ExitStack()


def _initialize(seed: int, loaders: list[SpecLoader], found: Any) -> None:
    global _worker
    resolved = {
        r.prop.desc: r for load in loaders for r in specify.resolve_all(load())
    }
    _scope.enter_context(fixture.scope())
    _worker = _Worker(seed, resolved, found)
    # Ahead of the finalizers closing the queues (priority 10), which a
    # process pool needs to shut down.
    multiprocessing.util.Finalize(None, _exit_worker, exitpriority=100)


def _exit_worker() -> None:
    # A worker process joins its child processes before the interpreter's
    # exit handlers would run, so a process pool a law left running, shut
    # down at exit as in a sequential run or not at all, would keep the
    # worker from ending. The handlers run first, as when an interpreter
    # exits, and any child process still running is then terminated.
    atexit._run_exitfuncs()
    for child in multiprocessing.active_children():
        child.terminate()


def _to_wall(instant: float | None) -> float | None:
    if instant is None:
        return None
    return time.time() + (instant - time.perf_counter())


def _to_perf(instant: float | None) -> float | None:
    if instant is None:
        return None
    return time.perf_counter() + (instant - time.time())


def _evaluate(task: _Task) -> _Done:
    worker = _worker
    if worker is None:
        raise RuntimeError("The worker process was not initialized")
    allowance = Allowance(
        task.max_attempts,
        _to_perf(task.deadline),
        _to_perf(task.shrink_deadline),
    )
    announced: list[CounterExample] = []

    def _found(example: CounterExample) -> None:
        sent = portable(example)
        announced.append(sent)
        worker.found.put((task.desc, sent))

    outcome = specify.evaluate_property(
        worker.seed,
        worker.resolved[task.desc],
        task.negated,
        allowance,
        _found,
    )
    if outcome.counter_example is not None:
        outcome = dataclasses.replace(
            outcome, counter_example=portable(outcome.counter_example)
        )
    return _Done(
        outcome, announced[0] if announced else None, fixture._detach()
    )


###############################################################################
# Evaluation
###############################################################################
#: Seconds between checks for counterexamples announced by workers.
_POLL_INTERVAL = 0.05


@dataclass(frozen=True)
class _Entry:
    module: int
    prop: Prop
    negated: bool


def evaluate(
    seed: int,
    modules: list[tuple[str, Spec, SpecLoader]],
    reporter: Reporter,
    allowance_for: Callable[[Resolved], Allowance],
    finished: Callable[[str], None],
    jobs: int,
) -> bool:
    """Evaluate the specifications of a run's modules in worker processes.

    The reporter sees the same calls as in a sequential run, except
    ``start_run`` and ``finish``, which are the caller's.

    :param seed: The run seed.
    :param modules: Each module's name, specification and loader; a
        loader rebuilds the specification in a worker.
    :param reporter: Receives the outcomes, in sequential order.
    :param allowance_for: Decides a property's allowance as it is sent to
        a worker.
    :param finished: Invoked with a property's description when its
        worker is done with it.
    :param jobs: The number of worker processes.

    :return: Whether every module's specification holds.

    :raises ValueError: When ``jobs`` is not positive.
    :raises RuntimeError: When a worker process fails, for example
        because a loader raised.
    """
    if jobs < 1:
        raise ValueError(f"Parallel evaluation needs a worker, got {jobs}")
    entries = [
        _Entry(index, prop, negated)
        for index, (_, spec, _) in enumerate(modules)
        for prop, negated in specify.leaves(spec)
    ]
    resolved = {
        r.prop.desc: r
        for _, spec, _ in modules
        for r in specify.resolve_all(spec)
    }
    context = multiprocessing.get_context("spawn")
    found_queue: Any = context.Queue()
    outcomes: dict[str, Outcome] = {}
    found: dict[str, CounterExample] = {}
    announced: set[str] = set()
    head = 0
    head_started = False
    current = -1

    def _announce(desc: str, example: CounterExample) -> None:
        if desc not in announced:
            announced.add(desc)
            found[desc] = example

    def _drain() -> None:
        while True:
            try:
                desc, example = found_queue.get_nowait()
            except queue.Empty:
                return
            _announce(desc, example)

    def _enter(module: int) -> None:
        # Move the report to a module, through any without properties.
        nonlocal current
        while current < module:
            if current >= 0:
                reporter.end_module()
            current += 1
            reporter.start_module(modules[current][0])

    def _report() -> None:
        # Report from the head of the sequential order as far as the
        # outcomes reach.
        nonlocal head, head_started
        while head < len(entries):
            entry = entries[head]
            desc = entry.prop.desc
            _enter(entry.module)
            if not head_started:
                reporter.start_property(desc)
                head_started = True
            example = found.pop(desc, None)
            if example is not None:
                reporter.found_counter_example(desc, example)
            outcome = outcomes.get(desc)
            if outcome is None:
                return
            reporter.end_property(outcome)
            head += 1
            head_started = False

    pending = deque(entries)
    running: dict[Future[_Done], str] = {}
    pool = ProcessPoolExecutor(
        max_workers=jobs,
        mp_context=context,
        initializer=_initialize,
        initargs=(seed, [load for _, _, load in modules], found_queue),
    )
    try:
        while pending or running:
            while pending and len(running) < jobs:
                entry = pending.popleft()
                allowance = allowance_for(resolved[entry.prop.desc])
                task = _Task(
                    entry.prop.desc,
                    entry.negated,
                    allowance.max_attempts,
                    _to_wall(allowance.deadline),
                    _to_wall(allowance.shrink_deadline),
                )
                running[pool.submit(_evaluate, task)] = entry.prop.desc
            _report()
            done, _ = wait_futures(
                running, timeout=_POLL_INTERVAL, return_when=FIRST_COMPLETED
            )
            _drain()
            for future in done:
                desc = running.pop(future)
                result = future.result()
                finished(desc)
                fixture._adopt(result.paths)
                if result.found is not None:
                    _announce(desc, result.found)
                outcomes[desc] = result.outcome
            _report()
    except BrokenProcessPool as error:
        pool.shutdown(wait=False, cancel_futures=True)
        raise RuntimeError(
            "A worker process failed; a module's loader may have raised "
            "or a law may have ended its process"
        ) from error
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    _enter(len(modules) - 1)
    if current >= 0:
        reporter.end_module()
    return all(
        specify.combine(spec, lambda desc: outcomes[desc].holds)
        for _, spec, _ in modules
    )
