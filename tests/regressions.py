"""Properties of recorded counterexamples and their replay."""

import contextlib
import io
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import minigun.fixture as f
import minigun.generate as g
import minigun.orchestrator as o
import minigun.regressions as rg
import minigun.reporter as r
import minigun.search as s
import minigun.specify as sp
from minigun import assume, check
from minigun.specify import Spec, conj, context, prop
from tests._support import (
    Program,
    greedy_descent,
    greedy_leaf,
    interpret,
    member,
    programs,
)

###############################################################################
# Files
###############################################################################


def _regressions() -> g.Generator[rg.Regression]:
    # Few seeds and attempts and mostly a few descriptions, so drawn lists
    # repeat draws; any string as a description exercises the escaping.
    return g.map(
        rg.Regression,
        g.weighted_choice(
            (3, g.one_of(["p", "q", "a property with spaces", "été"])),
            (1, g.strings()),
        ),
        g.int_range(-2, 2),
        g.int_range(0, 3),
        g.bounded_dicts(0, 2, g.words(), g.strings()),
        g.bounded_dicts(0, 2, g.words(), g.strings()),
        g.optional(g.strings()),
    )


@context(g.bounded_lists(0, 12, _regressions()))
@prop("a file keeps each recorded draw once, in the order first recorded")
def _round_trip(entries: list[rg.Regression]) -> bool:
    path = f.temporary_path() / "two" / "levels" / "m.json"
    added = [rg.record(path, entry) for entry in entries]
    first: dict[tuple[str, int, int], rg.Regression] = {}
    expected_added: list[bool] = []
    for entry in entries:
        expected_added.append(entry.key not in first)
        first.setdefault(entry.key, entry)
    return (
        rg.load(path) == list(first.values())
        and added == expected_added
        and (path.exists() == bool(entries))
        and not path.with_name("m.json.tmp").exists()
    )


@prop("a missing file records nothing")
def _missing(name: str) -> bool:
    return rg.load(f.temporary_path() / f"{name}.json") == []


_VALID_ENTRY: dict[str, Any] = {
    "property": "p",
    "seed": 3,
    "attempt": 0,
    "drawn": {"x": "5"},
    "arguments": {"x": "1"},
    "exception": None,
}


def _document(entries: Any) -> dict[str, Any]:
    return {"format": rg.FORMAT, "version": rg.VERSION, "regressions": entries}


def _entry(**changes: Any) -> dict[str, Any]:
    entry = dict(_VALID_ENTRY)
    entry.update(changes)
    return entry


#: Malformed files: every one is checked on every attempt.
_MALFORMED: list[str] = [
    "{",
    "[]",
    json.dumps({"format": "other", "version": 1, "regressions": []}),
    json.dumps({**_document([]), "extra": 1}),
    json.dumps({**_document([]), "version": 1}),
    json.dumps({**_document([]), "version": 3}),
    json.dumps(_document({})),
    json.dumps(_document([1])),
    json.dumps(
        _document([{k: v for k, v in _VALID_ENTRY.items() if k != "seed"}])
    ),
    json.dumps(_document([_entry(extra=1)])),
    json.dumps(_document([_entry(property=1)])),
    json.dumps(_document([_entry(seed=True)])),
    json.dumps(_document([_entry(seed=1.5)])),
    json.dumps(_document([_entry(attempt=-1)])),
    json.dumps(_document([_entry(attempt="0")])),
    json.dumps(
        _document([{k: v for k, v in _VALID_ENTRY.items() if k != "drawn"}])
    ),
    json.dumps(_document([_entry(drawn={"x": 1})])),
    json.dumps(_document([_entry(drawn=None)])),
    json.dumps(_document([_entry(arguments={"x": 1})])),
    json.dumps(_document([_entry(arguments=["x"])])),
    json.dumps(_document([_entry(exception=1)])),
]


@context(g.int_range(-(10**30), 10**30), g.int_range(0, 10**6))
@prop("a malformed file is an error naming it, a well formed one loads")
def _malformed(seed: int, attempt: int) -> bool:
    directory = f.temporary_path()
    valid = directory / "valid.json"
    valid.write_text(
        json.dumps(_document([_entry(seed=seed, attempt=attempt)]))
    )
    if rg.load(valid) != [
        rg.Regression("p", seed, attempt, {"x": "5"}, {"x": "1"})
    ]:
        return False
    if rg.load(valid)[0].recorded != sp.Recorded(seed, attempt, {"x": "5"}):
        return False
    for index, text in enumerate(_MALFORMED):
        path = directory / f"bad{index}.json"
        path.write_text(text)
        try:
            rg.load(path)
        except rg.RegressionsError as error:
            if str(path) not in str(error):
                return False
        else:
            return False
    old = directory / "old.json"
    old.write_text(json.dumps({**_document([]), "version": 1}))
    try:
        rg.load(old)
    except rg.RegressionsError as error:
        return "Version 1 entries" in str(error)
    return False


@context(
    g.bounded_lists(0, 5, g.one_of(["a", "b", "c", "d"])),
    g.bounded_lists(0, 5, g.one_of(["a", "b", "c", "d"])),
)
@prop("a file naming a property the specification lacks is an error")
def _unknown(recorded: list[str], defined: list[str]) -> bool:
    path = Path("m.json")
    entries = [rg.Regression(desc, 0, 0, {}, {}) for desc in recorded]
    unknown = sorted(set(recorded) - set(defined))
    try:
        rg.check_properties(path, entries, defined)
    except rg.RegressionsError as error:
        return bool(unknown) and all(f'"{d}"' in str(error) for d in unknown)
    return not unknown


_KINDS = ["holds", "negated", "error", "replayed", "false", "exception"]


@context(g.one_of(_KINDS), g.ints(), g.ints())
@prop("an outcome is recorded when the run drew the failing counterexample")
def _from_outcome(kind: str, value: int, seed: int) -> bool:
    exception = ValueError(f"e{value}") if kind == "exception" else None
    example = s.CounterExample(
        {"x": value, "name": "v"},
        7,
        exception,
        seed=value if kind == "replayed" else None,
    )
    outcome = sp.Outcome(
        desc="p",
        negated=kind == "negated",
        holds=kind in ("holds", "negated"),
        duration=0.0,
        attempts=8,
        discards=0,
        counter_example=None if kind == "error" else example,
        error="not tested" if kind == "error" else None,
    )
    drawn = {"x": str(seed), "name": "'w'"}
    regression = rg.from_outcome(seed, outcome, drawn)
    if kind not in ("false", "exception"):
        return regression is None
    return regression == rg.Regression(
        "p",
        seed,
        7,
        drawn,
        {"x": repr(value), "name": "'v'"},
        None if exception is None else f"ValueError: e{value}",
    )


###############################################################################
# Replay
###############################################################################


def _drawn(resolved: sp.Resolved, seed: int, attempt: int) -> dict[str, str]:
    drawn = sp.drawn_text(sp.redraw(resolved, seed, attempt).dissection)
    assert drawn is not None
    return drawn


def _recorded(resolved: sp.Resolved, seed: int, attempt: int) -> sp.Recorded:
    """An attempt of a property recorded with what it draws."""
    return sp.Recorded(seed, attempt, _drawn(resolved, seed, attempt))


def _rare(residue: int, holds: bool = False) -> sp.Resolved:
    # Fails on one value in a hundred, so a search of a few attempts
    # rarely finds it and 5000 attempts miss it once in 10^21 runs.
    @context(g.int_range(0, 10**6))
    @prop("rare failure")
    def _law(x: int) -> bool:
        return holds or x % 100 != residue

    return sp.resolve(_law)


def _found(seed: int, resolved: sp.Resolved) -> tuple[sp.Outcome, Any]:
    announced: list[s.CounterExample] = []
    outcome = sp.evaluate_property(
        seed, resolved, False, sp.Allowance(5000), announced.append
    )
    return outcome, announced[0].args if announced else None


@context(g.int_range(0, 99))
@prop("a recorded draw is drawn again and replayed before any attempt")
def _replays(residue: int, seed: int) -> bool:
    resolved = _rare(residue)
    first, found = _found(seed, resolved)
    example = first.counter_example
    if example is None:
        return False
    replay = sp.redraw(resolved, seed, example.attempt)
    # The attempt before the failing one held, so its replay holds too.
    held = (
        [_recorded(resolved, seed, example.attempt - 1)]
        if example.attempt > 0
        else []
    )
    again = sp.evaluate_property(
        seed + 1,
        resolved,
        False,
        sp.Allowance(1),
        recorded=[*held, _recorded(resolved, seed, example.attempt)],
    )
    replayed = again.counter_example
    return (
        replay.dissection is not None
        and replay.dissection.head == found
        and not again.holds
        and again.error is None
        and again.attempts == 0
        and replayed is not None
        and replayed.seed == seed
        and replayed.attempt == example.attempt
        and replayed.args == example.args
        and replayed.path == example.path
        and again.replayed == len(held) + 1
        and again.stale == ()
    )


@context(g.int_range(0, 99), g.int_range(1, 30))
@prop("a replay that holds leaves the attempts and their labels as they were")
def _replay_holds(residue: int, attempts: int, seed: int) -> bool:
    @context(g.int_range(0, 10**6))
    @prop("rare failure")
    def _law(x: int) -> bool:
        sp.label("tested")
        return True

    resolved = sp.resolve(_law)
    plain = sp.evaluate_property(seed, resolved, False, sp.Allowance(attempts))
    replaying = sp.evaluate_property(
        seed,
        resolved,
        False,
        sp.Allowance(attempts),
        recorded=[
            _recorded(resolved, seed + 1, residue),
            _recorded(resolved, seed + 2, 0),
        ],
    )
    return (
        replaying.holds
        and replaying.replayed == 2
        and replaying.labels == plain.labels == {"tested": attempts}
        and (replaying.attempts, replaying.discards)
        == (plain.attempts, plain.discards)
    )


@context(g.int_range(0, 50))
@prop("a recorded draw the law now rejects is skipped")
def _replay_rejected(attempt: int, seed: int) -> bool:
    generator = g.int_range(0, 10**6)

    @context(generator)
    @prop("rejects one value")
    def _probe(x: int) -> bool:
        return True

    replay = sp.redraw(sp.resolve(_probe), seed, attempt)
    if replay.dissection is None:
        return False
    rejected = replay.dissection.head["x"]

    @context(generator)
    @prop("rejects one value")
    def _law(x: int) -> bool:
        assume(x != rejected)
        return True

    outcome = sp.evaluate_property(
        seed + 1,
        sp.resolve(_law),
        False,
        sp.Allowance(10),
        recorded=[_recorded(sp.resolve(_probe), seed, attempt)],
    )
    return outcome.holds and outcome.replayed == 0


###############################################################################
# Runs and checks
###############################################################################


def _threshold(desc: str, threshold: int) -> Spec:
    @context(g.int_range(0, 1000))
    @prop(desc)
    def _below(x: int) -> bool:
        return x < threshold

    return _below


def _quiet_run(
    config: o.RunConfig, modules: list[o.TestModule]
) -> tuple[bool, str]:
    buffer = io.StringIO()
    with (
        contextlib.redirect_stdout(buffer),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        success = o.run(config, modules)
    return success, buffer.getvalue()


@prop("a run records a new failure once, replays it, and keeps it once fixed")
def _run_records(seed: int) -> bool:
    directory = f.temporary_path() / "regressions"
    file = directory / "m.json"

    def _run(threshold: int, run_seed: int) -> tuple[bool, str]:
        config = o.RunConfig(
            0.2, seed=run_seed, output=o.OutputMode.QUIET, regressions=directory
        )
        module = o.TestModule(
            "m", conj(_threshold("fails", threshold), _threshold("holds", 1001))
        )
        return _quiet_run(config, [module])

    first, first_text = _run(500, seed)
    recorded = rg.load(file)
    second, second_text = _run(500, seed + 1)
    fixed, _ = _run(1001, seed + 2)
    return (
        not first
        and "Recorded in" in first_text
        and len(recorded) == 1
        and recorded[0].desc == "fails"
        and recorded[0].seed == seed
        and not second
        and "Recorded in" not in second_text
        and "replays a recorded failure" in second_text
        and fixed
        and rg.load(file) == recorded
    )


@prop("a run rejects a file naming unknown properties before anything runs")
def _run_unknown(seed: int) -> bool:
    directory = f.temporary_path()
    rg.record(directory / "m.json", rg.Regression("gone", 0, 0, {}, {}))
    rg.record(directory / "m.json", rg.Regression("other", 0, 0, {}, {}))
    modules = [
        o.TestModule(
            "m", conj(_threshold("kept", 1001), _threshold("other", 1001))
        )
    ]
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            o.run(
                o.RunConfig(
                    0.2,
                    seed=seed,
                    output=o.OutputMode.QUIET,
                    regressions=directory,
                    select=("kept",),
                ),
                modules,
            )
    except rg.RegressionsError as error:
        message = str(error)
        return (
            buffer.getvalue() == ""
            and '"gone"' in message
            and '"other"' not in message
        )
    return False


@prop("a selected run replays its properties' entries and accepts the others")
def _run_selected(seed: int) -> bool:
    directory = f.temporary_path()
    # Attempt 0 of any seed draws a value at most 1000, failing below 0.
    for desc in ("first", "second"):
        drawn = _drawn(sp.resolve(_threshold(desc, 0)), seed, 0)
        rg.record(directory / "m.json", rg.Regression(desc, seed, 0, drawn, {}))
    modules = [
        o.TestModule("m", conj(_threshold("first", 0), _threshold("second", 0)))
    ]
    success, text = _quiet_run(
        o.RunConfig(
            0.2,
            seed=seed + 1,
            output=o.OutputMode.QUIET,
            regressions=directory,
            select=("first",),
        ),
        modules,
    )
    return (
        not success
        and "FAIL [m] first" in text
        and "second" not in text
        and "replays a recorded failure" in text
    )


def _changeable(offset: int, excluded: int | None = None) -> sp.Resolved:
    """A property over a generator a change of ``offset`` or ``excluded``
    alters, failing when ``offset`` is negative."""
    generator = g.map(lambda x: x + offset, g.int_range(0, 10**6))
    if excluded is not None:
        generator = g.filter(lambda x: x != excluded, generator)

    @context(generator)
    @prop("changeable")
    def _law(x: int) -> bool:
        return offset >= 0

    return sp.resolve(_law)


@context(g.int_range(0, 50), g.one_of(["shifted", "discarded", "failing"]))
@prop("a recorded draw a changed generator no longer draws is stale")
def _stale(attempt: int, change: str, seed: int) -> bool:
    entry = _recorded(_changeable(0), seed, attempt)
    replay = sp.redraw(_changeable(0), seed, attempt).dissection
    assert replay is not None
    changed = {
        "shifted": _changeable(1),
        "discarded": _changeable(0, replay.head["x"]),
        "failing": _changeable(-1),
    }[change]
    unchanged = sp.evaluate_property(
        seed + 1, _changeable(0), False, sp.Allowance(5), recorded=[entry]
    )
    outcome = sp.evaluate_property(
        seed + 1, changed, False, sp.Allowance(5), recorded=[entry]
    )
    where = f"attempt {attempt + 1} of seed {seed}"
    description = r.describe_failure(outcome)
    return (
        unchanged.holds
        and unchanged.stale == ()
        and unchanged.replayed == 1
        and not outcome.holds
        and outcome.stale == (entry,)
        and outcome.replayed == 0
        and outcome.error is not None
        and where in outcome.error
        # No other reason applies, so the error is the stale entries'.
        and outcome.error.endswith("remove them from the regressions file")
        and where in description
        and (outcome.counter_example is not None) == (change == "failing")
        and (change != "failing" or "following counter example" in description)
        and (change == "failing" or outcome.attempts == 5)
    )


@prop("a law that changes its arguments records what its attempt drew")
def _records_drawn(seed: int) -> bool:
    directory = f.temporary_path()

    @context(g.bounded_lists(1, 5, g.int_range(0, 9)))
    @prop("clears")
    def _law(xs: list[int]) -> bool:
        xs.clear()
        return False

    def _run(run_seed: int) -> tuple[bool, str]:
        config = o.RunConfig(
            0.2, seed=run_seed, output=o.OutputMode.QUIET, regressions=directory
        )
        return _quiet_run(config, [o.TestModule("m", _law)])

    first, _ = _run(seed)
    recorded = rg.load(directory / "m.json")
    second, text = _run(seed + 1)
    return (
        not first
        and len(recorded) == 1
        and recorded[0].drawn != {"xs": "[]"}
        and recorded[0].drawn
        == _drawn(sp.resolve(_law), seed, recorded[0].attempt)
        and not second
        and "replays a recorded failure" in text
        and "no longer draw" not in text
    )


_HASHED_MODULE = """
import minigun.generate as g
from minigun.specify import conj, context, prop
from minigun.stateful import command, machine, programs


@context(g.sets(g.words()), g.dicts(g.words(), g.sets(g.words())))
@prop("sets of words stay small")
def _sets(words: set[str], table: dict[str, set[str]]) -> bool:
    return len(words) + len(table) < 3


bag = machine(
    (),
    command(
        "add",
        lambda system, words: system.append(words),
        arguments=g.sets(g.words()),
        next_state=lambda model, words: (*model, words),
    ),
    command(
        "count",
        lambda system, _: len(system),
        postcondition=lambda model, _, result: result == len(model) < 3,
    ),
)


@context(programs(bag))
@prop("bags of word sets stay small")
def _bags(program) -> bool:
    return program.run([])


spec = conj(_sets, _bags)
"""


def _cli(
    directory: Path, hash_seed: int, run_seed: int, jobs: int
) -> tuple[int, str]:
    """A run of the CLI in a process of its own with a string hash seed
    of its own, recording in and replaying from ``directory``."""
    command = [sys.executable, "-m", "minigun", "-t", "1", "-o", "quiet"]
    command += ["-d", str(directory), "-r", str(directory / "regressions")]
    command += ["-s", str(run_seed), "-j", str(jobs)]
    child = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONHASHSEED": str(hash_seed)},
    )
    return child.returncode, child.stdout + child.stderr


# Processes take a second or two each, so few attempts.
@context(g.int_range(1, 2**32 - 1), g.int_range(1, 2**32 - 1))
@prop(
    "entries recorded in one process replay unstale in others and workers",
    attempts=2,
)
def _across_processes(first_hash: int, second_hash: int, seed: int) -> bool:
    # Sets of strings iterate in an order that depends on the hash seed,
    # so a fingerprint that is not canonical makes every entry stale.
    directory = f.temporary_path()
    (directory / "hashed.py").write_text(_HASHED_MODULE)
    file = directory / "regressions" / "hashed.json"
    recorded_code, _ = _cli(directory, first_hash, seed, 2)
    entries = rg.load(file)
    replays = [_cli(directory, second_hash, seed + 1, jobs) for jobs in (1, 2)]
    return (
        recorded_code == 1
        and sorted(entry.desc for entry in entries)
        == ["bags of word sets stay small", "sets of words stay small"]
        and all(
            code == 1
            and text.count("replays a recorded failure") == 2
            and "no longer draw" not in text
            for code, text in replays
        )
        and rg.load(file) == entries
    )


@prop("check records a new failure in its file and replays it")
def _check_records(seed: int) -> bool:
    file = f.temporary_path() / "spec.json"
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        first = check(_threshold("fails", 500), seed=seed, regressions=file)
    first_text = buffer.getvalue()
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        second = check(
            _threshold("fails", 500), seed=seed + 1, regressions=file
        )
    second_text = buffer.getvalue()
    return (
        not first
        and f"RECORDED: fails in {file}" in first_text
        and not second
        and "RECORDED" not in second_text
        and "replays a recorded failure" in second_text
        and len(rg.load(file)) == 1
    )


###############################################################################
# Every generator
###############################################################################


def _program_prop(program: Program) -> sp.Resolved:
    # A law that depends only on the value, failing on about a third of
    # them, so a replay must fail and shrink exactly as the original did.
    @context(interpret(program))
    @prop("program law")
    def _law(value: Any) -> bool:
        return len(repr(value)) % 3 != 0

    return sp.resolve(_law)


@context(programs())
@prop("a recorded draw of any generator replays to the same counterexample")
def _replays_any(program: Program, seed: int) -> bool:
    resolved = _program_prop(program)
    found: list[s.CounterExample] = []
    first = sp.evaluate_property(
        seed, resolved, False, sp.Allowance(200), found.append
    )
    example = first.counter_example
    assume(example is not None)
    assert example is not None
    replay = sp.redraw(resolved, seed, example.attempt)
    again = sp.evaluate_property(
        seed + 1,
        resolved,
        False,
        sp.Allowance(1),
        recorded=[_recorded(resolved, seed, example.attempt)],
    )
    replayed = again.counter_example
    return (
        replay.dissection is not None
        and repr(replay.dissection.head) == repr(found[0].args)
        and replayed is not None
        and replayed.seed == seed
        and repr(replayed.args) == repr(example.args)
        and repr(replayed.path) == repr(example.path)
        and again.stale == ()
    )


@context(programs())
@prop("a shrink path of any generator is its first-child descent, in domain")
def _path_any(program: Program, rng: random.Random) -> bool:
    # A law that always fails accepts the first child of every node, so
    # the path is the descent along first children.
    dissection = g.argument_pack({"value": interpret(program)}).sample(rng)
    assume(dissection is not None)
    assert dissection is not None
    steps = greedy_descent(dissection, 500)
    assume(steps < 500)
    search = s.find_counter_example(
        rng,
        lambda value: False,
        {"value": interpret(program)},
        1,
        replays=[s.Replay(0, 0, dissection)],
    )
    example = search.counter_example
    return (
        example is not None
        and len(example.path) == steps + 1
        and repr(example.path[0]) == repr(dissection.head)
        and repr(example.args["value"])
        == repr(greedy_leaf(dissection)["value"])
        and all(member(program, args["value"]) for args in example.path)
    )


spec = conj(
    _round_trip,
    _missing,
    _malformed,
    _unknown,
    _from_outcome,
    _replays,
    _replay_holds,
    _replay_rejected,
    _run_records,
    _run_unknown,
    _run_selected,
    _stale,
    _records_drawn,
    _across_processes,
    _check_records,
    _replays_any,
    _path_any,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
