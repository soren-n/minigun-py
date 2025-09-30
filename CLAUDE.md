# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
```bash
# Run all tests with time budget (required parameter)
uv run minigun --time-budget 30

# Run specific test modules with time budget
uv run minigun --time-budget 45 --modules positive comprehensive

# Run tests in quiet mode (CI/CD)
uv run minigun --time-budget 60 --quiet

# Run tests with JSON output (tool integration)
uv run minigun --time-budget 30 --json

# List available test modules
uv run minigun --list-modules

# Alternative: use 'test' alias
uv run test --time-budget 30
```

### Quality Tools
```bash
# Run linting
uv run ruff check

# Auto-fix linting issues
uv run ruff check --fix

# Format code
uv run ruff format

# Type checking
uv run mypy minigun/

# Run coverage analysis
uv run coverage run -m pytest
uv run coverage report
```

### Build and Development
```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --group dev --group quality

# Build package
uv build

# Install local development version
uv pip install -e .
```

## Architecture Overview

Minigun is a property-based testing library organized in 5 architectural layers:

### Layer 1: Foundation
- `arbitrary.py` - PRNG state management and random generation
- `util.py` - General utilities and helpers
- `order.py` - Ordering and comparison utilities

### Layer 2: Core Data Structures
- `stream.py` - Lazy functional streams for infinite sequences
- `sample.py` - Dissection data structure (value + shrinking info)
- `shrink.py` - Shrinking strategies and algorithms

### Layer 3: Generation System
- `generate.py` - Data generators, combinators, and composition (core)
- `domain.py` - High-level domain specifications

### Layer 4: Testing Framework
- `specify.py` - Property definition DSL and test execution engine
- `search.py` - Counterexample search and exploration
- `pretty.py` - Value formatting and display
- `reporter.py` - Multiple output modes: rich console, quiet, and JSON reporting with budget allocation
- `budget.py` - Budget allocation and attempt calculation

### Layer 5: User Interface and Orchestration
- `cli.py` - Command-line interface and test runner
- `orchestrator.py` - Two-phase test execution coordination

## Key Patterns

### Generator Composition
Generators in `generate.py` follow functional composition patterns using combinators like `bind`, `map`, and `choose`.

### Cardinality System
The `cardinality.py` module calculates test attempts based on generator complexity, optimizing test coverage vs execution time.

### Reporter Integration
Use `set_reporter()` to configure test output. The system supports three output modes:
- **Verbose mode**: `TestReporter` with rich console output, tables, and progress indicators
- **Quiet mode**: Minimal pass/fail output for CI/CD pipelines
- **JSON mode**: `JSONReporter` with structured output for tool integration

### Budget Allocation System
The `BudgetAllocator` class manages time-based test allocation:
- Calibration phase measures execution time per test
- Secretary Problem optimization for infinite cardinality domains
- Proportional scaling when over budget

## Testing Structure

Test modules in `tests/`:
- `negative.py` - Edge cases and error conditions
- `positive.py` - Happy path scenarios
- `comprehensive.py` - Complex integration tests with cardinality optimization
- `additional.py` - Supplementary test cases

## Project Configuration

- Uses uv for dependency management
- Python >=3.12 required
- Configured with ruff for linting/formatting (80 char line limit)
- mypy for strict type checking
- Rich output formatting for enhanced UX
