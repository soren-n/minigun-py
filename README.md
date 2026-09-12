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

# Run specific test modules
minigun --time-budget 45 --modules my_tests other_tests

# List available test modules
minigun --list-modules

# Quiet mode (for CI/CD)
minigun --time-budget 60 --output quiet

# JSON output (for automation)
minigun --time-budget 30 --output json

# Reproduce a failing run
minigun --time-budget 30 --seed 42
```

The CLI discovers Python files in the test directory that export a module-level `spec: Spec`. Every property in every module is evaluated and reported. The time budget is shared between properties in proportion to how many attempts their input domains are worth, and time a property leaves unspent flows to the properties after it.

Every run is seeded. When a property fails, the seed is printed so the exact run can be replayed with `--seed`, and each property draws from its own source derived from that seed, so a property's samples never depend on what else ran.

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

## FAQ

**Q: What's a good time budget?**

A: Start with 30-60 seconds for quick feedback. Use 2-5 minutes for thorough testing in CI/CD.

**Q: How do I test larger input spaces?**

A: Increase the time budget. Properties over unbounded domains absorb the extra time, up to 10000 attempts each per run.

**Q: Can I customize test generation?**

A: Yes, use the `@context` decorator with generators from `minigun.generate`, or write your own generator and shrinker. See the tutorial for details.

**Q: How do I reproduce a failing run?**

A: Every failing run prints its seed. Pass it back with `minigun --seed <n>` (or `check(spec, seed=n)`) to replay the exact same generation.

**Q: My property passed but was it tested?**

A: A property whose generators discard most of their draws (for example an over-restrictive `g.filter`) fails with a message saying how many attempts were discarded, rather than passing silently.

# Real-World Usage

The following projects use Minigun for testing:
- [Minigun](https://github.com/soren-n/minigun-py/tree/main/tests) (self-testing)
- [Tickle](https://github.com/soren-n/tickle/tree/main/tests) (parsing library)

If you have used Minigun for testing a public project, please file an issue with a link to add it to this list.
