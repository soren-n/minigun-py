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

# Reproduce a failing run (the seed is printed on failure)
uv run minigun --time-budget 30 --seed 42

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

# Type checking (strict settings; must pass cleanly)
uv run mypy minigun/

# Run coverage analysis (uses minigun's own CLI, not pytest)
uv run coverage run -m minigun.cli --time-budget 60
uv run coverage report --show-missing --fail-under=60
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

Minigun is a property-based testing library organized in layers:

### Foundation
- `arbitrary.py` - PRNG state and primitive draws. State is a dedicated
  `random.Random` instance created by `seed()`; runs are fully determined
  by their seed. Draw functions thread state explicitly (state in,
  state out).
- `util.py` - Optional-type annotation helpers and the stdout encoding
  guard (`relax_stdout_errors`) that keeps reports from crashing on
  legacy Windows code pages.

### Core Data Structures
- `stream.py` - Lazy functional streams; exhaustion is signalled by
  StopIteration from the stream thunk.
- `shrink.py` - `Dissection[T]` (a value plus a lazy stream of shrunk
  alternatives) and shrinkers for primitives.

### Generation System
- `generate.py` - `Generator[T]` (a sampler plus the cardinality of its
  domain), generators for built-in types, and combinators (map, bind,
  filter, choice). Generator names avoid shadowing builtins: `ints()`,
  `lists()`, `strings()`, etc. Failed generation (e.g. filter rejection)
  is signalled by a None dissection.
- `cardinality.py` - Domain sizes as a saturating non-negative float
  (math.inf for unbounded), with `+`, `*`, `**`.

### Testing Framework
- `specify.py` - Property DSL (`@prop`, `@context`, `conj()`, `neg()`),
  the callback-driven evaluator `evaluate()`, and the standalone `check()`
  entry point with seed control. Knows nothing about reporters.
- `search.py` - Counterexample search and shrinking-based trimming.
- `budget.py` - Attempt policy (`attempt_limit`, `baseline_attempts`) and
  the `BudgetAllocator` that distributes the time budget over calibrated
  properties. Property descriptions must be unique.
- `reporter.py` - Passive result sinks: `RichReporter`, `QuietReporter`,
  `JSONReporter` share a result-accumulating base and differ only in
  rendering.

### Orchestration
- `orchestrator.py` - Owns a run: collects properties from module specs,
  calibrates each once, allocates the budget, evaluates each module spec
  once, and pushes results into the reporter.
- `cli.py` - Command-line interface and test discovery.

## Key Patterns

### Test Module Contract
Test modules in `tests/` export a module-level `spec: Spec` (typically
`spec = conj(...)`). The CLI discovers these; a module that fails to
import, or defines the retired `test()` contract, is reported as broken
and fails the run. Modules can still be run standalone via
`if __name__ == "__main__": check(spec)`.

### Property DSL
Properties are defined with `@prop` (generators inferred from type
annotations) plus optional `@context` (explicit generators) and composed
with `conj()` and `neg()`. `neg` distributes over `conj` by De Morgan.

### Seeded Reproducibility
Every run has a concrete integer seed, printed in the run header and on
failure. `--seed` (CLI), `OrchestrationConfig.seed`, and
`check(spec, seed=...)` replay a run exactly. States are advancing
`random.Random` instances: replaying a draw means re-seeding, not reusing
an old state value.

### Two-Phase Execution
The orchestrator first calibrates (times each property with a short
adaptive run), then executes each module spec exactly once with
budget-allocated attempts. Calibration is a runner concern; `check()` and
the evaluator never see it.

### No Silent Fallbacks
Broken test modules, unknown module names, duplicate property
descriptions, and unknown output modes are hard errors. Missing
generators for a property parameter fail that property loudly at
execution.

## CI

CI runs: `ruff format --check`, `ruff check` (including import sorting),
coverage with 60% minimum, and distribution build/install check. Scope
includes `minigun`, `tests` and `scripts` directories. mypy runs as a
pre-push hook locally.

## Project Configuration

- Uses uv for dependency management
- Python >=3.12 required; single runtime dependency (rich)
- Configured with ruff for linting/formatting (80 char line limit)
- mypy strict settings; `uv run mypy minigun/` must pass with no errors
- Semantic versioning via `python-semantic-release`; version tracked in
  both `pyproject.toml` and `minigun/__init__.py`
