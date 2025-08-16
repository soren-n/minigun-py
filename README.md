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

## CLI Testing Interface

Minigun provides a sophisticated CLI with time budget management and rich console output:

```bash
# Run all tests with 30 second time budget (required)
uv run minigun-test --time-budget 30

# Run specific test modules with time budget
uv run minigun-test --time-budget 45 --modules positive comprehensive

# Quiet mode for CI/CD (minimal output)
uv run minigun-test --time-budget 60 --quiet

# JSON output for tool integration and automation
uv run minigun-test --time-budget 30 --json

# List available test modules
uv run minigun-test --list-modules

# Show help and all options
uv run minigun-test --help
```

## Key CLI Features

- **Time Budget Management**: Automatically allocates test attempts based on complexity analysis
- **Rich Console Output**: Beautiful progress indicators, execution plans, and detailed reports
- **Cardinality Analysis**: Shows domain sizes, ideal vs actual attempts, and optimization insights
- **Modular Execution**: Run specific test modules or combinations
- **Multiple Output Modes**:
  - Verbose mode with rich console formatting
  - Quiet mode for CI/CD with simple pass/fail output
  - JSON mode for tool integration and automation

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
