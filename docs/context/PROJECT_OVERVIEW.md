# PROJECT_OVERVIEW.md

## What is Minigun?

Minigun is a property-based testing library for Python 3.12+, inspired by Haskell's QuickCheck and OCaml's QCheck. It enables developers to write tests that verify properties of their code rather than testing specific input/output examples.

## Core Purpose

Instead of writing individual test cases like:
```python
assert reverse([1, 2, 3]) == [3, 2, 1]
assert reverse([]) == []
```

You write properties that should hold for all valid inputs:
```python
@prop("reversing twice gives original list")
def test_reverse_inverse(lst):
    return reverse(reverse(lst)) == lst
```

Minigun automatically generates hundreds of test cases and finds minimal counterexamples when properties fail.

## Key Features

### 1. **Random Data Generation**
- Comprehensive generators for built-in Python types (int, str, list, dict, set, etc.)
- Combinators for creating complex data structures
- Custom domain specifications for test contexts

### 2. **Property-Based Testing**
- Define mathematical properties your code should satisfy
- Automatic generation of test cases
- Statistical confidence through large sample sizes

### 3. **Intelligent Shrinking**
- When tests fail, automatically finds minimal counterexamples
- Makes debugging easier by presenting the simplest failing case
- Preserves failure conditions while minimizing input complexity

### 4. **Rich Testing Interface**
- Declarative test specification with `@prop` and `@context` decorators
- Composable test suites with `conj()` (conjunction)
- Negation testing with `neg()` for expected failures

### 5. **Enhanced CLI and Reporting**
- Rich terminal output with progress indicators
- Detailed test reports and timing information
- Modular test execution (run specific test modules)

## Project Structure

```
minigun/                 # Core library package
├── arbitrary.py         # PRNG state management and random generation
├── generate.py          # Data generators and combinators
├── domain.py           # Domain specifications for test contexts
├── shrink.py           # Shrinking strategies for minimal counterexamples
├── specify.py          # Property specification and test execution
├── search.py           # Counterexample search algorithms
├── sample.py           # Sampling and dissection functionality
├── stream.py           # Functional stream operations
├── pretty.py           # Output formatting and display
├── reporter.py         # Test reporting and progress tracking
├── cli.py              # Command-line interface
├── order.py            # Ordering utilities
└── util.py             # General utilities

tests/                   # Self-testing using Minigun
├── positive.py          # Tests expected to pass
├── negative.py          # Tests expected to fail
├── comprehensive.py     # Broad coverage tests
└── additional.py        # Edge cases and specific scenarios

docs/                    # Documentation
├── readthedocs/         # Sphinx documentation source
└── context/             # Coding agent context documents
```

## Target Use Cases

### 1. **Library Development**
Test fundamental properties of data structures and algorithms:
- Serialization/deserialization round-trips
- Invariants of data structures (e.g., sorted lists remain sorted)
- Mathematical properties (commutativity, associativity, etc.)

### 2. **API Testing**
Verify API contracts and edge cases:
- Input validation behaves correctly for all inputs
- State transitions maintain invariants
- Error handling is consistent

### 3. **Regression Testing**
Catch subtle bugs that example-based tests might miss:
- Boundary conditions
- Unexpected input combinations
- Performance degradation

## Development Philosophy

### **Functional Programming Principles**
- Immutable data structures where possible
- Pure functions with explicit state threading
- Pattern matching over complex conditionals
- Monadic error handling with `Maybe` types

### **Type Safety**
- Comprehensive type annotations
- Generic type parameters for reusable components
- Runtime type checking where beneficial

### **Performance Awareness**
- Lazy evaluation with streams
- Efficient shrinking algorithms
- Memory-conscious data generation

## Dependencies

**Core Runtime:**
- `returns` - Monadic types (Maybe, etc.)
- `tqdm` - Progress bars
- `typeset-soren-n` - Type utilities
- `rich` - Terminal formatting

**Development:**
- `mypy` - Static type checking
- `ruff` - Code formatting and linting
- `sphinx` - Documentation generation
- `pre-commit` - Git hooks

## Version and Compatibility

- **Current Version:** 2.0.0
- **Python Requirement:** >=3.12
- **License:** GPLv3
- **Package Name:** `minigun-soren-n` (on PyPI)

## Getting Started for Contributors

1. **Understanding Property-Based Testing:**
   - Watch John Hughes' presentations on QuickCheck
   - Read Jan Midtgaard's lecture materials
   - Study the existing test suite in `tests/`

2. **Key Concepts to Master:**
   - Generator composition and combinators
   - Shrinking strategies and dissections
   - Property specification patterns
   - Domain modeling for test data

3. **Codebase Entry Points:**
   - Start with `specify.py` to understand the testing DSL
   - Explore `generate.py` for data generation patterns
   - Study `tests/comprehensive.py` for usage examples

This project represents a sophisticated implementation of property-based testing concepts, requiring understanding of both functional programming patterns and testing methodologies.
