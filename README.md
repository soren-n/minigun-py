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
Minigun is currently only supported for Python >=3.12. It is distributed with pip and can be installed with the following example command:
```
pip install minigun-soren-n
```

# Quick Start

## Using the CLI (Recommended)

Create a test module in `tests/` directory:

```python
# tests/my_tests.py
from minigun.specify import prop, check, conj

@prop("reversing a list twice gives the original")
def test_reverse(lst: list[int]):
    return list(reversed(list(reversed(lst)))) == lst

@prop("list length distributes over concatenation")
def test_length(xs: list[int], ys: list[int]):
    return len(xs + ys) == len(xs) + len(ys)

def test():
    return check(conj(test_reverse, test_length))
```

Run your tests with time budget:

```bash
minigun --time-budget 30
```

## Using as a Library

```python
from minigun.specify import prop, check

@prop("reversing a list twice gives the original")
def test_reverse(lst: list[int]):
    return list(reversed(list(reversed(lst)))) == lst

if __name__ == "__main__":
    success = check(test_reverse)
    exit(0 if success else 1)
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
minigun --time-budget 60 --quiet

# JSON output (for automation)
minigun --time-budget 30 --json
```

The CLI discovers Python files in the test directory that contain a `test()` function.

## Advanced: Manual Orchestrator Usage

For programmatic control, use the orchestrator directly:

```python
# my_test_runner.py
from minigun.orchestrator import TestOrchestrator, OrchestrationConfig, TestModule
from minigun.specify import prop, check

@prop("your property")
def my_property(x: int):
    return x + 0 == x

def run_my_property():
    return check(my_property)

if __name__ == "__main__":
    config = OrchestrationConfig(
        time_budget=30.0,
        verbose=True
    )

    modules = [TestModule("my_tests", run_my_property)]
    orchestrator = TestOrchestrator(config)
    success = orchestrator.execute_tests(modules)

    exit(0 if success else 1)
```

## Writing Tests

### Basic Properties

```python
from minigun.specify import prop

@prop("addition is commutative")
def test_add_commute(x: int, y: int):
    return x + y == y + x
```

### Custom Domains

```python
import minigun.domain as d
from minigun.specify import prop, context

@context(d.int(1, 100), d.int(1, 100))
@prop("division reverses multiplication")
def test_div(x: int, y: int):
    return (x * y) // y == x
```

### Combining Properties

```python
from minigun.specify import prop, check, conj

@prop("property 1")
def test_1(x: int):
    return x + 0 == x

@prop("property 2")
def test_2(x: int):
    return x * 1 == x

# Check both together
success = check(conj(test_1, test_2))
```

## FAQ

**Q: What's a good time budget?**

A: Start with 30-60 seconds for quick feedback. Use 2-5 minutes for thorough testing in CI/CD.

**Q: How do I test larger input spaces?**

A: Increase the time budget. The system automatically runs more test attempts when given more time.

**Q: Can I customize test generation?**

A: Yes, use the `@context` decorator with domain specifications. See documentation for details.

# Real-World Usage

The following projects use Minigun for testing:
- [Minigun](https://github.com/soren-n/minigun/tree/main/tests) (self-testing)
- [Tickle](https://github.com/soren-n/tickle/tree/main/tests) (parsing library)

If you have used Minigun for testing a public project, please file an issue with a link to add it to this list.
