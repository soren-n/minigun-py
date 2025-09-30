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

```python
from minigun.specify import prop, check

# Define a property that should hold for all valid inputs
@prop("reversing a list twice gives the original")
def reverse_twice_is_identity(lst: list[int]):
    return list(reversed(list(reversed(lst)))) == lst

# Check the property (returns True if all generated tests pass)
if __name__ == "__main__":
    success = check(reverse_twice_is_identity)
    print("✅ Property holds!" if success else "❌ Property failed!")
```

Minigun will automatically:
- Generate hundreds of diverse test cases
- Find minimal counterexamples when properties fail
- Provide detailed shrinking to the simplest failing case

# Documentation
A tutorial as well as reference documentation for the API can be found at [Read The Docs](https://minigun.readthedocs.io/en/latest/).

# Usage

Minigun is designed to be used **as a library** in your own test code. You write properties using the `@prop` decorator and check them with `check()`.

## Basic Usage Pattern

```python
# my_tests.py
from minigun.specify import prop, check, conj
import minigun.domain as d

@prop("reversing twice gives identity")
def test_reverse_identity(lst: list[int]):
    return list(reversed(list(reversed(lst)))) == lst

@prop("list length distributes over concatenation")
def test_list_length(xs: list[int], ys: list[int]):
    return len(xs + ys) == len(xs) + len(ys)

if __name__ == "__main__":
    # Check individual properties
    success = check(test_reverse_identity)

    # Or check multiple properties together
    success = check(conj(test_reverse_identity, test_list_length))

    exit(0 if success else 1)
```

Then run your tests:
```bash
python my_tests.py
```

## CLI Test Runner

Minigun includes a CLI test runner that discovers and executes test modules with time budget management and rich output:

### Setting Up Test Modules

Organize your tests in a directory (default: `./tests`) with modules containing a `test()` function:

```python
# tests/my_tests.py
from minigun.specify import prop, check, conj

@prop("addition is commutative")
def test_add_commute(x: int, y: int):
    return x + y == y + x

@prop("list length distributes")
def test_list_length(xs: list[int], ys: list[int]):
    return len(xs + ys) == len(xs) + len(ys)

def test():
    """Entry point for minigun-test CLI"""
    return check(conj(test_add_commute, test_list_length))
```

### Running Tests

```bash
# Run all tests in ./tests with 30 second time budget
minigun-test --time-budget 30

# Run tests from a different directory
minigun-test --time-budget 60 --test-dir my_tests

# Run specific modules
minigun-test --time-budget 45 --modules positive comprehensive

# List discovered test modules
minigun-test --list-modules

# Quiet mode for CI/CD
minigun-test --time-budget 60 --quiet

# JSON output for automation
minigun-test --time-budget 30 --json
```

### Test Discovery

The CLI automatically discovers test modules by:
1. Scanning the test directory for `.py` files
2. Finding modules with a `test()` function (no parameters)
3. Dynamically importing and running them with the orchestrator

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

## Key Features

- **Automatic Test Generation**: Generates test cases from type hints
- **Shrinking**: Finds minimal counterexamples on failure
- **Cardinality Analysis**: Calculates test attempts based on domain size
- **Time Budget Management** (with orchestrator): Distributes attempts across properties based on execution time
- **Rich Console Output** (with orchestrator): Progress indicators and detailed reports
- **Multiple Output Modes** (with orchestrator):
  - Verbose mode with rich formatting
  - Quiet mode for CI/CD
  - JSON mode for tool integration

## How Time Budget Works (Advanced)

When using the `TestOrchestrator`, the system runs in two phases to allocate time budget across properties:

### Phase 1: Calibration
- Runs 10 silent test attempts per property to measure execution speed
- Calculates time-per-attempt for each property
- Determines theoretical optimal attempts based on domain cardinality

### Phase 2: Execution
- Allocates attempts based on:
  - Available time budget
  - Measured execution speed
  - Domain cardinality
  - Secretary Problem optimization (√n attempts for infinite domains)
- Infinite cardinality properties use remaining budget when available
- All properties scaled proportionally when over budget

### Example Behavior

**With 5-second budget:**
```
Infinite cardinality property: 211 attempts
Total execution: ~3.6s (72% of budget)
```

**With 60-second budget:**
```
Infinite cardinality property: 10,000 attempts
Total execution: ~51.7s (86% of budget)
```

**Key Points:**
- Larger time budgets result in more test attempts
- Fast and slow properties are balanced automatically
- Infinite domains get more attempts with larger budgets
- Small finite domains may complete quickly regardless of budget

### Execution Plan Output

The orchestrator displays a table showing budget allocation:

```
📋 Property Testing Plan (Budget: 60.0s, Est: 60.0s)
┌────────────────────────────────┬───────────┬──────────┬───────────┬──────────┐
│ Property                       │ Domain    │ Ideal    │ Actual    │ Est.     │
│                                │ Size      │ Attempts │ Attempts  │ Time     │
├────────────────────────────────┼───────────┼──────────┼───────────┼──────────┤
│ string concatenation is ass... │ ∞         │ 10000    │ 2894      │ 51.96s   │
│ integer addition is associa... │ ∞         │ 10000    │ 10000     │ 0.93s    │
└────────────────────────────────┴───────────┴──────────┴───────────┴──────────┘
```

- **Domain Size**: Size of test input space (∞ = infinite)
- **Ideal Attempts**: Secretary Problem limit (√cardinality)
- **Actual Attempts**: Budget-allocated attempts (scaled down if over budget)
- **Est. Time**: Estimated execution time from calibration

### Common Questions

**Q: How do I run my own tests with time budgets and rich output?**

A: Use the `minigun-test` CLI with test discovery. Create test modules in a `tests/` directory with a `test()` function, then run:
```bash
minigun-test --time-budget 30
```

See "CLI Test Runner" section above for details.

**Q: My tests complete quickly even with a large time budget. Why?**

A: Common causes:
- Your properties have small finite domains that reach their optimal attempt limit quickly
- You're using `TestReporter` directly without the `TestOrchestrator` (which won't work)
- Most test time is spent in calibration overhead rather than actual testing

Solution: Use `TestOrchestrator` with `OrchestrationConfig` for proper time budget management.

**Q: How do I make tests run longer to find rare edge cases?**

A: When using the orchestrator, increase the time budget:
```python
config = OrchestrationConfig(
    time_budget=300.0,  # 5 minutes
    verbose=True
)
```

For basic usage without the orchestrator, use the `@context` decorator with larger domains:
```python
@context(d.int(0, 1000000))  # Larger domain
@prop("my property")
def test_property(x: int):
    return x >= 0
```

**Q: What's a good time budget for CI/CD?**

A: Recommended budgets (when using TestOrchestrator):
- **Quick feedback**: 30-60 seconds
- **Standard testing**: 2-5 minutes (120-300 seconds)
- **Thorough validation**: 10-30 minutes (600-1800 seconds)
- **Exhaustive testing**: 1+ hours (3600+ seconds) for critical releases

For basic usage, Minigun will automatically determine optimal attempts based on domain cardinality.

# Examples

## Basic Property Testing

```python
from minigun.specify import prop, check

# Test mathematical properties
@prop("addition is commutative")
def test_addition_commutative(x: int, y: int):
    return x + y == y + x

@prop("list concatenation length")
def test_list_concat_length(xs: list[str], ys: list[str]):
    return len(xs + ys) == len(xs) + len(ys)

# Run individual tests
success = check(test_addition_commutative)
```

## Advanced Testing with Contexts

```python
from minigun.specify import prop, context, conj, check
import minigun.domain as d

# Custom domain for small positive integers
@context(d.int(1, 100), d.int(1, 100))
@prop("multiplication by division identity")
def test_mult_div_identity(x: int, y: int):
    return (x * y) // y == x

# Test data structures
@context(d.list(d.int(), 0, 10))  # Lists of 0-10 integers
@prop("sorted list property")
def test_sorted_invariant(lst: list[int]):
    sorted_lst = sorted(lst)
    return all(sorted_lst[i] <= sorted_lst[i+1]
              for i in range(len(sorted_lst) - 1))

# Combine multiple properties
suite = conj(test_mult_div_identity, test_sorted_invariant)
success = check(suite)
```

## JSON Output for Tool Integration

Minigun supports structured JSON output for easy integration with CI/CD pipelines and external tools:

```bash
# Generate JSON output for automation
uv run minigun-test --time-budget 30 --json
```

The JSON output includes comprehensive test results, timing information, and cardinality analysis:

```json
{
  "version": "1.0",
  "timestamp": "2025-01-20T10:30:45.123456",
  "config": {
    "time_budget": 30.0,
    "modules": ["positive", "comprehensive"],
    "quiet": false
  },
  "summary": {
    "total_tests": 58,
    "total_passed": 56,
    "total_failed": 2,
    "total_duration": 28.5,
    "execution_duration": 25.2,
    "budget_usage": 84.0,
    "overall_success": false
  },
  "modules": [
    {
      "name": "positive",
      "tests": [...],
      "passed": 34,
      "failed": 0,
      "total": 34,
      "duration": 12.4,
      "success": true
    }
  ]
}
```

This format enables:
- **CI/CD Integration**: Parse results in build pipelines
- **Metric Collection**: Extract timing and coverage data
- **Dashboard Integration**: Build monitoring dashboards
- **Automated Reporting**: Generate test reports and notifications

## Real-World Usage

The following projects use Minigun for testing:
- [Minigun](https://github.com/soren-n/minigun/tree/main/tests) (self-testing)
- [Tickle](https://github.com/soren-n/tickle/tree/main/tests) (parsing library)

If you have used Minigun for testing a public project, please file an issue with a link to add it to this list.
