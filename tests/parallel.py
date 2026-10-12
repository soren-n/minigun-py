"""Properties of parallel evaluation in worker processes.

Each property that evaluates in workers spawns a pool of processes, so
those declare their attempts and keep their specifications small.
"""

import functools
import pickle
import secrets
import time
from concurrent.futures.process import BrokenProcessPool
from typing import Any

import minigun.fixture as fixture
import minigun.generate as g
import minigun.orchestrator as o
import minigun.parallel as p
import minigun.reporter as r
from minigun import check
from minigun.search import CounterExample
from minigun.specify import (
    Allowance,
    AllowanceFor,
    Outcome,
    Resolved,
    Spec,
    conj,
    context,
    prop,
)
from tests._parallel import (
    EVERY_KIND,
    KINDS,
    Opaque,
    Shape,
    Twofold,
    build,
    fails_to_load,
)

###############################################################################
# Recording what a reporter sees
###############################################################################


class _Recorder(r.Reporter):
    """Records every call as text, durations left out; counterexamples
    and failures are recorded as the reporters render them, so an
    argument or exception sent back by its text compares equal to the
    original."""

    def __init__(self) -> None:
        super().__init__(0, None)
        self.calls: list[tuple[Any, ...]] = []
        self.times: list[float] = []

    def start_module(self, name: str) -> None:
        super().start_module(name)
        self.calls.append(("start_module", name))

    def start_property(self, desc: str) -> None:
        self.calls.append(("start_property", desc))

    def found_counter_example(self, desc: str, example: CounterExample) -> None:
        self.times.append(time.perf_counter())
        self.calls.append(("found", desc, r.describe_found(desc, example)))

    def end_property(self, outcome: Outcome) -> None:
        super().end_property(outcome)
        self.times.append(time.perf_counter())
        example = outcome.counter_example
        self.calls.append(
            (
                "end_property",
                outcome.desc,
                outcome.negated,
                outcome.holds,
                outcome.attempts,
                outcome.discards,
                outcome.error,
                r.describe_failure(outcome),
                None
                if example is None
                else (example.attempt, example.shrinks, example.minimal),
            )
        )

    def end_module(self) -> None:
        super().end_module()
        self.calls.append(("end_module",))


def _declared(resolved: Resolved) -> Allowance:
    attempts = resolved.prop.attempts
    if attempts is None:
        raise ValueError(f'"{resolved.prop.desc}" declares no attempts')
    return Allowance(attempts)


def _sequential(
    seed: int, shapes: list[Shape], allowance_for: AllowanceFor = _declared
) -> tuple[bool, list[tuple[Any, ...]]]:
    reporter = _Recorder()
    modules = [
        o.TestModule(f"module {index}", build(index, shape))
        for index, shape in enumerate(shapes)
    ]
    holds = o._evaluate_modules(seed, modules, reporter, allowance_for)
    return holds, reporter.calls


def _parallel(
    seed: int,
    shapes: list[Shape],
    jobs: int,
    events: list[tuple[str, str]],
    allowance_for: AllowanceFor = _declared,
) -> tuple[bool, list[tuple[Any, ...]]]:
    """Evaluate in workers, logging each property as its allowance is
    decided ("sent") and as its worker is done with it ("finished")."""
    reporter = _Recorder()
    modules: list[tuple[str, Spec, p.SpecLoader]] = [
        (
            f"module {index}",
            build(index, shape),
            functools.partial(build, index, shape),
        )
        for index, shape in enumerate(shapes)
    ]

    def _sent(resolved: Resolved) -> Allowance:
        events.append(("sent", resolved.prop.desc))
        return allowance_for(resolved)

    holds = p.evaluate(
        seed,
        modules,
        reporter,
        _sent,
        lambda desc: events.append(("finished", desc)),
        jobs,
    )
    return holds, reporter.calls


def _within_jobs(
    events: list[tuple[str, str]], descs: list[str], jobs: int
) -> bool:
    """Whether every property was sent once and finished once after it,
    with never more than ``jobs`` sent and not yet finished."""
    running: set[str] = set()
    seen: set[str] = set()
    for event, desc in events:
        if event == "sent":
            if desc in seen:
                return False
            seen.add(desc)
            running.add(desc)
            if len(running) > jobs:
                return False
        elif desc not in running:
            return False
        else:
            running.remove(desc)
    return not running and sorted(seen) == sorted(descs)


###############################################################################
# Generators
###############################################################################
def _shapes(max_modules: int) -> g.Generator[list[Shape]]:
    leaf = g.tuples(g.one_of(KINDS), g.int_range(1, 4))
    term = g.tuples(g.bools(), g.bools(), g.bounded_lists(1, 3, leaf))
    return g.bounded_lists(0, max_modules, g.bounded_lists(0, 3, term))


###############################################################################
# Parallel and sequential runs agree
###############################################################################
# Every kind of law, plain and negated, is evaluated on every attempt in a
# module of its own, at a drawn position among drawn modules.
@context(g.ints(), g.int_range(2, 3), _shapes(3), g.int_range(0, 3))
@prop(
    "a parallel evaluation reports what a sequential one does, in order",
    attempts=6,
)
def _agrees(seed: int, jobs: int, shapes: list[Shape], at: int) -> bool:
    shapes = shapes[:at] + [EVERY_KIND] + shapes[at:]
    events: list[tuple[str, str]] = []
    expected = _sequential(seed, shapes)
    observed = _parallel(seed, shapes, jobs, events)
    descs = [call[1] for call in expected[1] if call[0] == "start_property"]
    return observed == expected and _within_jobs(events, descs, jobs)


# A deadline that has passed stops the attempts after the first evaluated
# one, and a shrink deadline that has passed stops shrinking; deadlines
# well in the future change nothing. All four combinations are checked on
# every attempt, so a deadline misread in a worker shows up as a
# difference in attempts or in the counterexample's minimality.
@context(g.ints(), g.int_range(1, 3), g.float_range(1.0, 60.0))
@prop("a worker keeps the deadlines it is sent", attempts=2)
def _deadlines(seed: int, jobs: int, offset: float) -> bool:
    for deadline in (-offset, offset + 60.0):
        for shrink_deadline in (-offset, offset + 60.0):

            def _allowance(
                resolved: Resolved,
                deadline: float = deadline,
                shrink_deadline: float = shrink_deadline,
            ) -> Allowance:
                now = time.perf_counter()
                return Allowance(
                    10 * _declared(resolved).max_attempts,
                    now + deadline,
                    now + shrink_deadline,
                )

            expected = _sequential(seed, [EVERY_KIND], _allowance)
            observed = _parallel(seed, [EVERY_KIND], jobs, [], _allowance)
            if observed != expected:
                return False
    return True


@context(g.ints(), g.int_range(1, 3), g.int_range(0, 4), g.bools())
# Each attempt creates a pool, though no worker process is started.
@prop(
    "modules without properties are reported in order, without workers",
    attempts=300,
)
def _empty_modules(seed: int, jobs: int, count: int, negated: bool) -> bool:
    # A module of an empty conjunction, or of its negation, which fails.
    shapes: list[Shape] = [[(negated, False, [])]] * count
    events: list[tuple[str, str]] = []
    expected = _sequential(seed, shapes)
    observed = _parallel(seed, shapes, jobs, events)
    return observed == expected and events == []


# The property sleeps on each evaluation, so bisecting its counterexample
# down to the boundary takes some ten evaluations, about 0.3 seconds; the
# counterexample is announced as soon as it is found, not with the outcome.
@context(g.ints(), g.int_range(1, 2))
@prop("a counterexample found in a worker is announced live", attempts=1)
def _announced_live(seed: int, jobs: int) -> bool:
    shape: Shape = [(False, True, [("slow", 50)])]
    reporter = _Recorder()
    p.evaluate(
        seed,
        [("slow", build(0, shape), functools.partial(build, 0, shape))],
        reporter,
        _declared,
        lambda desc: None,
        jobs,
    )
    kinds = [call[0] for call in reporter.calls]
    if kinds != [
        "start_module",
        "start_property",
        "found",
        "end_property",
        "end_module",
    ]:
        return False
    found, ended = reporter.times
    return ended - found > 0.15


# Every attempt of a marking property creates a temporary fixture holding
# a file named by the drawn token, so the run's own fixtures can be told
# from those of properties evaluated beside it.
@context(g.ints(), g.int_range(1, 3), g.bounded_lists(1, 4, g.int_range(1, 3)))
@prop("temporary fixtures made in workers belong to the run", attempts=2)
def _fixtures_adopted(seed: int, jobs: int, attempts: list[int]) -> bool:
    token = secrets.token_hex(8)
    shape: Shape = [(False, False, [(f"marks {token}", n) for n in attempts])]
    pattern = f"*/{token}"
    temporary = fixture.ROOT / "temporary"
    with fixture.scope():
        p.evaluate(
            seed,
            [("marks", build(0, shape), functools.partial(build, 0, shape))],
            _Recorder(),
            _declared,
            lambda desc: None,
            jobs,
        )
        made = list(temporary.glob(pattern))
        if len(made) != sum(attempts):
            return False
    return not any(temporary.glob(pattern))


# A worker process joins its child processes as it ends, so a process
# pool a law leaves running would keep the evaluation from returning. Both
# a pool shut down by an exit handler and one never shut down are left on
# every attempt; every worker that evaluated the first runs its handler.
@context(g.ints(), g.int_range(1, 3))
@prop("workers end although laws leave process pools running", attempts=1)
def _pools_left(seed: int, jobs: int) -> bool:
    with fixture.scope():
        directory = fixture.temporary_path()
        shape: Shape = [
            (False, False, [(f"pools {directory}", 1), ("leaks", 1)])
        ]
        reporter = _Recorder()
        holds = p.evaluate(
            seed,
            [("pools", build(0, shape), functools.partial(build, 0, shape))],
            reporter,
            _declared,
            lambda desc: None,
            jobs,
        )
        return holds and any(directory.iterdir())


###############################################################################
# Failures of the evaluation itself
###############################################################################
@context(g.int_range(-3, 0), g.ints())
@prop("an evaluation without workers is rejected before anything is reported")
def _rejects_jobs(jobs: int, seed: int) -> bool:
    reporter = _Recorder()
    try:
        p.evaluate(
            seed,
            [
                (
                    "m",
                    build(0, EVERY_KIND),
                    functools.partial(build, 0, EVERY_KIND),
                )
            ],
            reporter,
            _declared,
            lambda desc: None,
            jobs,
        )
    except ValueError as error:
        return str(jobs) in str(error) and reporter.calls == []
    return False


# Both ways of failing are checked on every attempt.
@context(g.ints(), g.int_range(1, 2))
@prop("a failing worker process is an error, not a passing run", attempts=2)
def _worker_failure(seed: int, jobs: int) -> bool:
    holding: Shape = [(False, True, [("holds", 1)])]
    exiting: Shape = [(False, True, [("exits", 1)])]
    broken = [
        # The loader raises in the worker.
        ("broken", build(0, holding), functools.partial(fails_to_load, "no")),
        # The law ends its worker process.
        ("exiting", build(0, exiting), functools.partial(build, 0, exiting)),
    ]
    for module in broken:
        reporter = _Recorder()
        try:
            p.evaluate(
                seed, [module], reporter, _declared, lambda desc: None, jobs
            )
        except RuntimeError as error:
            if not isinstance(error.__cause__, BrokenProcessPool):
                return False
            if any(call[0] == "end_property" for call in reporter.calls):
                return False
        else:
            return False
    return True


###############################################################################
# Portable counterexamples
###############################################################################
def _contains_opaque(value: Any) -> bool:
    if isinstance(value, Opaque):
        return True
    if isinstance(value, list):
        return any(_contains_opaque(item) for item in value)
    return False


_VALUES = g.choice(
    g.ints(),
    g.strings(),
    g.map(Opaque, g.small_nats()),
    g.bounded_lists(
        0, 3, g.choice(g.small_ints(), g.map(Opaque, g.small_nats()))
    ),
)

#: The exceptions a law may raise: none, one that pickles, one that does
#: not unpickle, and one holding a value that does not pickle.
_EXCEPTIONS = ["none", "value", "twofold", "opaque"]


def _exception(kind: str, n: int) -> Exception | None:
    match kind:
        case "value":
            return ValueError(f"bad {n}")
        case "twofold":
            return Twofold(n, n + 1)
        case "opaque":
            return ValueError(Opaque(n))
        case _:
            return None


def _portable_with(
    values: list[Any],
    kind: str,
    attempt: int,
    shrinks: int,
    n: int,
    minimal: bool,
) -> bool:
    # A value that pickles and one that does not are always among them.
    args = {"plain": [n], "opaque": Opaque(n)}
    args.update((f"a{i}", value) for i, value in enumerate(values))
    exception = _exception(kind, n)
    example = CounterExample(args, attempt, exception, shrinks, minimal)
    sent = p.portable(example)
    received = pickle.loads(pickle.dumps(sent))
    if list(sent.args) != list(args) or (
        (sent.attempt, sent.shrinks, sent.minimal)
        != (attempt, shrinks, minimal)
    ):
        return False
    for name, value in args.items():
        kept = sent.args[name]
        if _contains_opaque(value):
            if not (isinstance(kept, p.Shown) and repr(kept) == repr(value)):
                return False
        elif kept is not value:
            return False
        if received.args[name] != kept:
            return False
    match kind:
        case "none":
            if sent.exception is not None:
                return False
        case "value":
            if sent.exception is not exception:
                return False
        case _:
            remote = received.exception
            if not (
                isinstance(remote, p.RemoteException)
                and remote.type_name == type(exception).__name__
                and str(remote) == str(exception)
            ):
                return False

    def _rendered(example: CounterExample) -> tuple[str, str]:
        outcome = Outcome("d", False, False, 0.0, 1, 0, example, None)
        return r.describe_failure(outcome), r.describe_found("d", example)

    return _rendered(example) == _rendered(sent) == _rendered(received)


# Every kind of exception is checked on every attempt.
@context(
    g.bounded_lists(0, 4, _VALUES),
    g.small_nats(),
    g.small_nats(),
    g.small_nats(),
    g.bools(),
)
@prop("portable keeps what pickles and shows the rest by its text")
def _portable(
    values: list[Any], attempt: int, shrinks: int, n: int, minimal: bool
) -> bool:
    return all(
        _portable_with(values, kind, attempt, shrinks, n, minimal)
        for kind in _EXCEPTIONS
    )


@context(g.strings(), g.strings())
@prop("a remote exception and a shown value survive pickling")
def _remote_pickles(type_name: str, text: str) -> bool:
    remote = p.RemoteException(type_name, text)
    back = pickle.loads(pickle.dumps(remote))
    shown = pickle.loads(pickle.dumps(p.Shown(text)))
    return (
        isinstance(back, p.RemoteException)
        and back.type_name == type_name
        and str(back) == text
        and shown == p.Shown(text)
        and hash(shown) == hash(p.Shown(text))
        and repr(shown) == text
        and shown != text
    )


spec = conj(
    _agrees,
    _deadlines,
    _announced_live,
    _fixtures_adopted,
    _pools_left,
    _empty_modules,
    _rejects_jobs,
    _worker_failure,
    _portable,
    _remote_pickles,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
