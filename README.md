[![GitHub](https://img.shields.io/github/license/soren-n/minigun-py)](https://github.com/soren-n/minigun-py/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![Discord](https://img.shields.io/discord/931473325543268373?label=discord)](https://discord.gg/bddF43Vk2q)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/soren-n)](https://github.com/sponsors/soren-n)
[![Documentation Status](https://readthedocs.org/projects/minigun/badge/?version=latest)](https://minigun.readthedocs.io/en/latest/?badge=latest)

# Minigun
A QuickCheck-like library for property-based unit-testing of Python programs.

Minigun is inspired by [QCheck](https://github.com/c-cube/qcheck), which in turn was inspired by [QuickCheck](https://github.com/nick8325/quickcheck). Both are libraries that provide implementations for performing property-based unit-testing; for OCaml and Haskell respectively.

If you would like a bit of motivation as to why you should use a QuickCheck-like system for testing your project, then I would recommend that you watch:
- [John Hughes - Testing the Hard Stuff and Staying Sane](https://www.youtube.com/watch?v=zi0rHwfiX1Q)
- [John Hughes - Certifying your car with Erlang](https://vimeo.com/68331689)

If you wish to learn more about the subject, I can recommend Jan Midtgaard's [lecture materials](https://janmidtgaard.dk/quickcheck/index.html); it is OCaml based but translates easily to other QuickCheck-like libraries for other languages.

# Install
Minigun requires Python >=3.12. It is distributed with pip and can be installed with the following command:
```
pip install minigun-soren-n
```

# Quick Start

## Using the CLI (Recommended)

Create a test module in the `tests/` directory:

```python
# tests/my_tests.py
from minigun import prop, conj


@prop("reversing a list twice gives the original")
def test_reverse(lst: list[int]) -> bool:
    return list(reversed(list(reversed(lst)))) == lst


@prop("list length distributes over concatenation")
def test_length(xs: list[int], ys: list[int]) -> bool:
    return len(xs + ys) == len(xs) + len(ys)


spec = conj(test_reverse, test_length)
```

Run your tests with a time budget:

```bash
minigun --time-budget 30
```

## Using as a Library

```python
from minigun import prop, check


@prop("reversing a list twice gives the original")
def test_reverse(lst: list[int]) -> bool:
    return list(reversed(list(reversed(lst)))) == lst


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(test_reverse) else 1)
```

Run directly:
```bash
python my_tests.py
```

# Documentation
Full documentation and tutorials at [Read The Docs](https://minigun.readthedocs.io/en/latest/).

# Usage Guide

## CLI Test Runner

```bash
# Run all tests in ./tests directory
minigun --time-budget 30

# Run tests from a different directory
minigun --time-budget 60 --test-dir my_tests

# Run specific test modules (only these are imported)
minigun --time-budget 45 --modules my_tests other_tests

# Run only the properties whose descriptions contain a substring
minigun --time-budget 30 --select "sensitivities"

# List available test modules
minigun --list-modules

# Quiet mode (for CI/CD)
minigun --time-budget 60 --output quiet

# JSON output (for automation)
minigun --time-budget 30 --output json

# Reproduce a failing run
minigun --time-budget 30 --seed 42

# Evaluate four properties at once in worker processes ('auto': one per CPU)
minigun --time-budget 30 --jobs 4

# Replay recorded counterexamples first, and record new ones
minigun --time-budget 30 --regressions tests/regressions

# Show how each counterexample was shrunk
minigun --time-budget 30 --verbose
```

The CLI discovers Python files in the test directory that export a module-level `spec: Spec`. Every property in every module is evaluated and reported. Property descriptions identify properties across the whole run, so they must be unique across modules; a description used twice is reported as an error naming both modules before anything runs. The time budget is shared equally between properties, whatever their attempts cost: each runs until it has spent its share or reached the attempts its input domain is worth, and time a property leaves unspent flows to the properties after it. A small finite domain is worth enough attempts to draw every value with 99.9% confidence (11 for a `bool`, 88 for ten values); larger and unbounded domains share one cap. The summary counts the properties that held without reaching that number, and each one's line shows its attempts against it (for example `3/2029 attempts`). A property that declares its attempts always makes all of them (see Declaring Effort). Failures are reported with their shrunk counterexample in every output mode. A counterexample is announced as soon as it is found, before shrinking starts (on stderr in quiet and JSON output), and shrinking stops when the run's budget is spent: no further shrunk candidate is evaluated, and the smallest counterexample found so far is reported with a note that it may not be minimal.

Every run is seeded. When a property fails, the seed is printed so the exact run can be replayed with `--seed`, and each property draws from its own source derived from that seed, so a property's samples never depend on what else ran. To replay one failing property cheaply, pass the seed together with `--select` and part of its description: the property draws the same values as in the full run.

With `--regressions DIR`, a failing property's counterexample is recorded in `DIR/<module>.json`, and every later run replays the recorded counterexamples of a property before its own attempts, so a bug stays covered after it is fixed (see Recorded Counterexamples). With `--verbose`, each failure also shows its shrink path: the arguments found, then the arguments each shrink step changed.

With `--jobs N`, N properties are evaluated at once, each in a worker process that imports the test modules itself. A property draws the same values whichever worker evaluates it, so a seed replays a parallel run too, and the report lists outcomes in the same order as a sequential run. The time budget is then worker time: N workers share out N times the remaining time, and no property runs past the end of the run. A law that scans or clears the fixture directories as a whole sees the fixtures of properties running beside it. Workers end with the run as an interpreter does: their `atexit` handlers run, so a process pool shared by a module's laws can be shut down there, and a child process still running after them is terminated.

## Running Programmatically

```python
from minigun.orchestrator import OutputMode, RunConfig, TestModule, run
from minigun.specify import prop


@prop("your property")
def my_property(x: int) -> bool:
    return x + 0 == x


if __name__ == "__main__":
    import sys

    config = RunConfig(time_budget=30.0, output=OutputMode.QUIET)
    sys.exit(0 if run(config, [TestModule("my_tests", my_property)]) else 1)
```

To run with several jobs, give each `TestModule` a `load`: a picklable callable, such as a module-level function, that returns the module's specification in a worker process, and set `RunConfig(jobs=...)`. Workers are started with `spawn`, so the entry point must be guarded by `if __name__ == "__main__":`.

The CLI's other options are `RunConfig` fields as well: `select` (patterns, as `--select`; pass whole specifications and `run` prunes them), `regressions` (a directory, as `--regressions`) and `verbose`.

For structured outcomes without a reporter, drive `minigun.specify.evaluate` directly; the tutorial's "Running specifications programmatically" section shows how.

## Writing Tests

### Basic Properties

```python
from minigun import prop


@prop("addition is commutative")
def test_add_commute(x: int, y: int) -> bool:
    return x + y == y + x
```

### Custom Generators

```python
from minigun import prop, context, generate as g


@context(g.int_range(1, 100), g.int_range(1, 100))
@prop("division reverses multiplication")
def test_div(x: int, y: int) -> bool:
    return (x * y) // y == x
```

### Bounded Domains

```python
import datetime
import math
import string

from minigun import prop, context, generate as g


@context(
    g.float_range(0.0, 0.25),
    g.dates(datetime.date(2000, 1, 1), datetime.date(2040, 12, 31)),
    g.bounded_strings(1, 5, string.ascii_uppercase),
)
@prop("discount factors lie in the unit interval")
def test_discount(rate: float, day: datetime.date, ticker: str) -> bool:
    years = (day - datetime.date(2000, 1, 1)).days / 365
    factor = math.exp(-rate * years)
    return 0.0 < factor <= 1.0 and ticker.isupper()
```

`nonzero_int_range(lower, upper)` draws integers other than zero, for divisors and step counts. `float_range` draws its bounds and, when the range holds zero, zero and tiny magnitudes down to the smallest subnormal float more often than a uniform draw would; pass `edges=False` for uniform draws only. `datetimes(first, last, resolution)` draws datetimes on a grid.

### Preconditions

When a precondition relates several parameters, reject the arguments inside the law with `assume` (or `discard()`) instead of generating the parameters together:

```python
from minigun import prop, context, assume, generate as g

side = g.int_range(1, 20)


@context(side, side, side)
@prop("proper triangles have a positive area")
def test_heron(a: int, b: int, c: int) -> bool:
    assume(a < b + c and b < a + c and c < a + b)
    return (a + b + c) * (-a + b + c) * (a - b + c) * (a + b - c) > 0
```

Rejected attempts count as discards, and shrunk counterexamples always satisfy the precondition.

### Declaring Effort

A property whose attempts are expensive, or statistical, can declare how many attempts it is worth. `check` makes exactly that many, and so does a budgeted run, even when the property's share of the time runs out first: a declared count is what the property needs, not a limit to cut. It still counts as one of the properties sharing the time, so the others leave it a share of room, but a run whose declared properties overrun their share takes longer than its budget, and the summary shows by how much:

```python
import random
from minigun import prop


@prop("the mean of uniform samples is close to one half", attempts=50)
def test_mean(rng: random.Random) -> bool:
    mean = sum(rng.random() for _ in range(1000)) / 1000
    return abs(mean - 0.5) < 0.1
```

### Looking at the Test Data

A passing property says nothing about cases it never drew. `g.examples` shows what a generator produces:

```python
from minigun import generate as g

g.examples(g.dicts(g.ints(), g.ints()), n=3, seed=1)
# [{4: 2}, {2: -10, -32: -42, -74: -938, 10: -3, 8: 35, 4: 132, -3: 94}, {}]
```

Inside a law, `label` tags each attempt and the run reports how often each label came up; `cover` also requires a share of the attempts:

```python
from minigun import prop, label, cover


@prop("a deleted key is no longer in the table")
def test_delete(key: int, table: dict[int, int]) -> bool:
    label("present" if key in table else "absent")
    cover(0.2, key in table, "present")
    table.pop(key, None)
    return key not in table
```

Here about nine keys in ten are absent, so the `cover` requirement fails the property: drawing keys independently of the table mostly tests deleting keys that are not there. The distribution is printed by `check` and the rich output, and included in JSON output as `labels`. Because attempt counts vary with the budget, a requirement fails only when the attempts show with overwhelming confidence that it is unmet; a short run does not fail on it. The fraction is a fraction, not a percentage.

### Recorded Counterexamples

A run given a regressions directory records the counterexample of every new failure in a JSON file per test module and replays the recorded ones before each property's own attempts:

```bash
minigun --time-budget 30 --regressions tests/regressions
```

`check(spec, regressions="tests/spec_regressions.json")` does the same with one file. An entry records the seed of the run that found the failure and the attempt that drew it. A property's draws depend only on the seed and its description, so the entry draws the same arguments again and shrinks to the same counterexample for as long as the property's generators are unchanged. The shrunk arguments are recorded as text beside it, for reading; nothing is replayed from them. Keep the directory in version control, so everyone who runs the tests replays the same failures. Entries are never removed automatically: delete one to stop replaying it. An entry naming a property that no longer exists is an error, so renaming a property cannot silently drop the failures recorded for it; rename the entry too. After a generator changes, an entry replays whatever the generator now draws at that attempt, and no longer reproduces the recorded case.

### Combining Properties

```python
from minigun import prop, check, conj, neg


@prop("property 1")
def test_1(x: int) -> bool:
    return x + 0 == x


@prop("this law is false and a counterexample must be found")
def test_2(x: int) -> bool:
    return x * 2 == x


# Check both together; neg holds when its term is refuted
success = check(conj(test_1, neg(test_2)))
```

### Randomness Inside a Law

Annotate a parameter with `random.Random` to receive a source that is reproducible from the run seed:

```python
import random
from minigun import prop


@prop("shuffling preserves the elements")
def test_shuffle(xs: list[int], rng: random.Random) -> bool:
    shuffled = list(xs)
    rng.shuffle(shuffled)
    return sorted(shuffled) == sorted(xs)
```

### Arrival Order

`g.interleave` merges one list of steps per client (or per node of a distributed system) in a random order that keeps each list's order. Running the result sequentially tests a system under every order in which requests or messages can arrive, as long as each step runs to completion; a counterexample shrinks to the fewest steps and the fewest switches between clients:

```python
from minigun import prop, context, generate as g


def writes(client: int) -> g.Generator[list[tuple[int, int]]]:
    return g.lists(g.map(lambda value: (client, value), g.small_nats()))


@context(g.interleave(writes(0), writes(1)))
@prop("the log keeps each client's writes in order")
def test_log(arrivals: list[tuple[int, int]]) -> bool:
    log = Log()  # the system under test
    for client, value in arrivals:
        log.append(client, value)
    return all(
        log.entries(c) == [v for k, v in arrivals if k == c] for c in (0, 1)
    )
```

See the tutorial's Nondeterminism section for a simulated network of replicas.

## FAQ

**Q: What's a good time budget?**

A: Start with 30-60 seconds for quick feedback. Use 2-5 minutes for thorough testing in CI/CD.

**Q: How do I test larger input spaces?**

A: Increase the time budget. Every property gets an equal part of it, and properties short of their attempt limit absorb the extra time, up to 10000 attempts each per run for unbounded domains.

**Q: Can I customize test generation?**

A: Yes, use the `@context` decorator with generators from `minigun.generate`, or write your own generator and shrinker. See the tutorial for details.

**Q: Some properties are much more expensive than others. How do I balance them?**

A: The time budget is shared equally between properties, not attempts, so a property whose attempts are expensive gets as much time as a cheap one, and time a property leaves unspent flows to the properties after it. When a property needs a number of attempts regardless of the budget, declare them with `@prop("...", attempts=n)`. A declared property always makes all its attempts, so the run takes as long as they need.

**Q: A run seems to hang after a failure. What is it doing?**

A: Shrinking: the counterexample found is being reduced by re-running the law on smaller arguments, and a smaller argument can be slower to evaluate than the original. The failure is announced, with its seed and original arguments, as soon as it is found (on stderr in quiet and JSON output), and shrinking stops when the time budget is spent. A single evaluation already running is not interrupted, so a law whose evaluations can take minutes can still overrun by one evaluation.

**Q: How do I measure coverage?**

A: Run the CLI under coverage: `coverage run --source=mylib -m minigun --time-budget 60`, then `coverage report`. To combine with a pytest suite, run both with `coverage run -p` and then `coverage combine`.

**Q: How do I share helpers between test modules?**

A: Put them in files whose names start with an underscore, or in a subdirectory, and import them relatively: `from ._models import levy_models`. Test modules are imported as a package of their directory.

**Q: One test module is broken. Can I still run the others?**

A: Yes: `minigun --modules name ...` imports only the selected modules.

**Q: How do I reproduce a failing run?**

A: Every failing run prints its seed. Pass it back with `minigun --seed <n>` (or `check(spec, seed=n)`) to replay the exact same generation. Add `--select "<part of the description>"` to replay only the failing property; it draws the same values as in the full run. To have every run replay a failure until it is fixed, and afterwards, record it with `--regressions DIR` (see Recorded Counterexamples).

**Q: How did minigun arrive at this counterexample?**

A: Run with `--verbose` (or `check(spec, verbose=True)`): each failure then shows its shrink path, the arguments first found followed by the arguments each accepted shrink step changed. Every step fails the law in the same way as the arguments found.

**Q: My property passed but was it tested?**

A: A property whose generators or assumptions discard most of its attempts (for example an over-restrictive `g.filter` or `assume`) fails with a message saying how many attempts were discarded, rather than passing silently. A property that held without reaching its attempt limit, because its share of the time ran out, shows its attempts against the limit (for example `3/2029 attempts`), and the summary counts such properties; give the run a larger budget or `--jobs` to cover more. To see whether the attempts exercised the cases that matter, label them with `label(...)` and require the important ones with `cover(fraction, condition, name)` (see Looking at the Test Data).

# Real-World Usage

The following projects use Minigun for testing:
- [Minigun](https://github.com/soren-n/minigun-py/tree/main/tests) (self-testing)
- [Tickle](https://github.com/soren-n/tickle/tree/main/tests) (parsing library)

If you have used Minigun for testing a public project, please file an issue with a link to add it to this list.
