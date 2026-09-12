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
uv run minigun --time-budget 60 --output quiet

# Run tests with JSON output (tool integration)
uv run minigun --time-budget 30 --output json

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
- `arbitrary.py` - The random source: a dedicated `random.Random` created
  by `seed()`. Draws take the source and return the value; `fork()` derives
  an independent child source. Reproducibility comes from seeding, parallel
  safety from forking; there is no state threading.
- `stream.py` - `Stream[T]` is a zero-argument callable returning a fresh
  iterator: lazy and re-traversable. Producers are generator functions;
  composition uses itertools (`concat`, `braid`, `map`, `filter`).

### Core Data Structures
- `shrink.py` - `Dissection[T]` (a value plus a lazy stream of shrunk
  alternatives, a rose tree), `unfold` from trimmers, and shrinkers for
  primitives. Alternatives are ordered most aggressive first (QuickCheck
  order), so a first-failing-child walk is a binary search.
- `cardinality.py` - Domain sizes as a saturating non-negative float
  (math.inf for unbounded), with `+`, `*`, `**`.

### Generation System
- `generate.py` - `Generator[T]` (a sampler `Rng -> Dissection | None` plus
  the cardinality of its domain), generators for built-in types, and
  combinators (map, bind, lazy, filter, choice). None from a sampler is a
  discard. Names avoid shadowing builtins: `ints()`, `lists()`,
  `strings()`. `rngs()` gives laws a reproducible random source (inferred
  from a `random.Random` annotation). `bind` and `lazy` report unbounded
  cardinality; `with_cardinality` overrides it.

### Testing Framework
- `specify.py` - The DSL (`@prop`, `@context`, `conj()`, `neg()`) over a
  closed `Spec` union of `Prop | Neg | Conj` (matches end in
  `assert_never`). `resolve_all` raises `SpecificationError` for missing
  generators or duplicate descriptions before anything runs. `evaluate`
  runs every property (no short-circuit), each from a source derived from
  the run seed and its description, and emits structured `Outcome` values.
  Knows nothing about reporters or printing.
- `search.py` - Counterexample search: one law evaluation per candidate,
  one forked source per attempt, discards counted, optional deadline.
- `budget.py` - Attempt policy (`attempt_limit`, `baseline_attempts`) and
  the time-sliced `TimeBudget`: no calibration; each property gets a share
  of the remaining time weighted by its attempt limit, unspent time flows
  on, and the budget is held strictly.
- `reporter.py` - Passive sinks over `Outcome`: `PlainReporter` (for
  `check`), `QuietReporter`, `RichReporter`, `JSONReporter`. Also the
  stdout encoding guard and counterexample formatting.
- `fixture.py` - Filesystem fixtures under `.minigun`; temporary paths are
  removed by the enclosing `scope()`, so nested runs clean only their own.

### Orchestration
- `orchestrator.py` - `run(RunConfig, modules)` for budgeted runs and
  `check(spec, seed)` for standalone checks; `OutputMode` selects the
  reporter.
- `cli.py` - Command-line interface and test discovery (modules are
  registered in `sys.modules` under a private namespace before execution).

## Key Patterns

### Test Module Contract
Test modules in `tests/` export a module-level `spec: Spec` (typically
`spec = conj(...)`). The CLI discovers these; a module that fails to
import, or defines the retired `test()` contract, is reported as broken
and fails the run. Modules can still be run standalone via
`if __name__ == "__main__": check(spec)`.

### Property DSL
Properties are defined with `@prop` (generators inferred from type
annotations via `get_type_hints`) plus optional `@context` (explicit
generators) and composed with `conj()` and `neg()`. `neg` distributes over
`conj` by De Morgan. Every property in a spec is evaluated and reported.

### Seeded Reproducibility
Every run has a concrete integer seed, printed in the run header and on
failure. Each property draws from `property_rng(seed, desc)`, and each
attempt from a fork of that, so a property's samples depend only on the
seed and its description; `--seed` replays a run exactly and the reported
attempt index identifies the failing draw.

### Time Budget
There is no calibration. `TimeBudget` hands each starting property an
`Allowance` (attempt limit plus a deadline) from the time remaining; the
first attempt always runs. `check()` uses `baseline_attempts` and no
deadline.

### No Silent Fallbacks
Broken test modules, unknown module names, missing test directories,
duplicate property descriptions, missing generators and invalid
arguments are hard errors (`SpecificationError`, `ValueError`,
`TypeError`). A property most of whose attempts are discarded fails
loudly. Unreachable match arms use `typing.assert_never`.

### Self-testing
`tests/` holds one module per library module plus `algebra` (end-to-end
laws) and `examples` (the tutorial examples under `docs/examples/`,
which the tutorial includes with `literalinclude`). `tests/_support.py`
models generators as programs and interprets them, so universal
properties quantify over all generators.

## CI

CI runs on Python 3.12, 3.13 and 3.14: `ruff format --check`,
`ruff check` (including import sorting), coverage with 60% minimum, and
distribution build/install check. Scope includes the `minigun`, `tests`,
`scripts` and `docs/examples` directories. Locally, pre-commit validates conventional commit
messages at commit-msg and runs mypy at pre-push.

## Project Configuration

- Uses uv for dependency management
- Python >=3.12 required; single runtime dependency (rich)
- Configured with ruff for linting/formatting (80 char line limit)
- mypy strict settings; `uv run mypy minigun/` must pass with no errors
- Semantic versioning via `python-semantic-release`; version tracked in
  both `pyproject.toml` and `minigun/__init__.py`
