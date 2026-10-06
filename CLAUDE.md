# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
```bash
# Run all tests with time budget (required parameter)
uv run minigun --time-budget 30

# Run specific test modules with time budget
uv run minigun --time-budget 45 --modules generate shrink

# Run tests in quiet mode (CI/CD)
uv run minigun --time-budget 60 --output quiet

# Run tests with JSON output (tool integration)
uv run minigun --time-budget 30 --output json

# Reproduce a failing run (the seed is printed on failure)
uv run minigun --time-budget 30 --seed 42

# Replay only the properties whose descriptions contain a substring
uv run minigun --time-budget 30 --seed 42 --select "shrinks to"

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

### Benchmarks
```bash
# Microbenchmarks (draw, shrink, attempts, fork, memory, probe); results
# are JSON files under --out, kept outside the repository
uv run python scripts/bench/micro.py --out /tmp/bench/head all

# The same against a baseline checkout, run from that checkout so its
# own minigun is imported (the scripts run by path, never as a package)
git worktree add ../minigun-py-v3.0.1 v3.0.1
(cd ../minigun-py-v3.0.1 && uv sync && uv run python \
    ../minigun-py/scripts/bench/micro.py --out /tmp/bench/v3.0.1 all)

# End to end CLI runs on both checkouts, HEAD profiles, and the tables
uv run python scripts/bench/e2e.py --out /tmp/bench --baseline ../minigun-py-v3.0.1
uv run python scripts/bench/hotspots.py --out /tmp/bench/profiles all
uv run python scripts/bench/report.py --results /tmp/bench

# Type-check the benchmark scripts (they import each other by bare name)
uv run mypy --no-namespace-packages scripts/bench scripts/mutate.py
```

### Mutation Testing
```bash
# Mutate core functions one operator or constant at a time and run each
# mutant's test modules in copies under --out (outside the repository);
# about 8 minutes with 6 workers. Survivors are printed with their lines.
uv run python scripts/mutate.py --out /tmp/mutants
uv run python scripts/mutate.py --out /tmp/mutants --files search shrink
```
Survivors are either equivalent mutants or behavior no test pins down.
Because minigun tests itself, a mutated generator also draws the tests'
arguments: a test of a generator should draw its inputs from another one.
Small finite domains get few attempts under a budget, and a property's
time share follows its attempt limit, so a test that must see a boundary
value or every one of a list of cases should check them on every attempt
rather than draw one.

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
  primitives. Alternatives are ordered most aggressive first, and the
  numeric shrinkers offer each alternative knowing the one before it held,
  so a first-failing-child walk is a bisection to the exact boundary.
- `cardinality.py` - Domain sizes as a saturating non-negative float
  (math.inf for unbounded), with `+`, `*`, `**`.

### Generation System
- `generate.py` - `Generator[T]` (a sampler `Rng -> Dissection | None` plus
  the cardinality of its domain), generators for built-in types, and
  combinators (map, bind, lazy, filter, choice). None from a sampler is a
  discard. Names avoid shadowing builtins: `ints()`, `lists()`,
  `strings()`. `rngs()` gives laws a reproducible random source (inferred
  from a `random.Random` annotation). `bind` and `lazy` report unbounded
  cardinality; `with_cardinality` overrides it. `float_range` draws its
  bounds and, when it holds zero, zero and tiny magnitudes down to 5e-324
  (`edges=False` for uniform only); `nonzero_int_range` excludes zero
  without discarding; `dates`/`datetimes` map `int_range`;
  string domains take an `alphabet`. `Generator` and `Dissection` are
  frozen, so both are covariant in `T`.

### Testing Framework
- `specify.py` - The DSL (`@prop`, `@context`, `conj()`, `neg()`) over a
  closed `Spec` union of `Prop | Neg | Conj` (matches end in
  `assert_never`). `resolve_all` raises `SpecificationError` for missing
  generators or duplicate descriptions before anything runs. `evaluate`
  runs every property (no short-circuit), each from a source derived from
  the run seed and its description, and emits structured `Outcome` values.
  `@prop(desc, attempts=n)` declares a property's attempts, overriding the
  domain-derived count in both `check` and budgeted runs. `select` prunes
  a spec to the properties a predicate keeps.
  Knows nothing about reporters or printing.
- `search.py` - Counterexample search: one law evaluation per candidate,
  attempts drawn in sequence from the property's source, discards
  counted, optional deadline. Shrinking keeps the kind of failure found:
  a False result only shrinks to False results, an exception only to the
  same exception type. A law raising `Discard` (via `assume`/`discard`)
  rejects its arguments: the attempt counts as a discard and the shrunk
  alternative is skipped.
- `budget.py` - Attempt policy (`attempt_limit`, `baseline_attempts`) and
  the time-sliced `TimeBudget`: no calibration; each property gets a share
  of the remaining time weighted by its attempt limit, unspent time flows
  on, and the budget is held strictly, except that a property declaring
  `attempts=n` always makes all n (no deadline; the run may overrun).
- `reporter.py` - Passive sinks over `Outcome`: `PlainReporter` (for
  `check`), `QuietReporter`, `RichReporter`, `JSONReporter`. Also the
  stdout encoding guard and counterexample formatting.
- `fixture.py` - Filesystem fixtures under `.minigun`; temporary paths are
  removed by the enclosing `scope()`, so nested runs clean only their own.

### Orchestration
- `orchestrator.py` - `run(RunConfig, modules)` for budgeted runs and
  `check(spec, seed)` for standalone checks; `OutputMode` selects the
  reporter.
- `cli.py` - Command-line interface and test discovery. Modules are
  registered in `sys.modules` before execution, as submodules of a package
  per test directory (`minigun_discovered.d<digest>`, `__path__` the
  directory) so relative helper imports work; `--modules` imports only the
  selected modules (repeatable); `--select`/`-k` runs only properties
  whose descriptions contain a pattern, with unchanged draws.

## Key Patterns

### Test Module Contract
Test modules in `tests/` export a module-level `spec: Spec` (typically
`spec = conj(...)`). The CLI discovers these; a module that fails to
import, or defines the retired `test()` contract, is reported as broken
and fails the run. With `--modules` only the selected modules are
imported, and a selected module without a `spec` is an error. Files
starting with an underscore are helpers, imported relatively
(`from ._support import x`); property descriptions must be unique across
all modules of a run. Modules can still be run standalone via
`if __name__ == "__main__": check(spec)`.

### Property DSL
Properties are defined with `@prop` (generators inferred from type
annotations via `get_type_hints`) plus optional `@context` (explicit
generators) and composed with `conj()` and `neg()`. `neg` distributes over
`conj` by De Morgan. Every property in a spec is evaluated and reported.
A law rejects arguments outside a multi-parameter precondition with
`assume(cond)` (counted as a discard), and `@prop(desc, attempts=n)`
declares what an expensive or statistical property is worth.

### Seeded Reproducibility
Every run has a concrete integer seed, printed in the run header and on
failure. Each property draws from `property_rng(seed, desc)`, and its
attempts draw in sequence from that source, so a property's samples depend
only on the seed and its description; `--seed` replays a run exactly and
the reported attempt index identifies the failing draw. Attempts are not
forked individually: a fresh `random.Random` costs about 6 microseconds,
more than a cheap attempt.

### Time Budget
There is no calibration. `TimeBudget` hands each starting property an
`Allowance` (attempt limit plus a deadline) from the time remaining; the
first attempt always runs. A property that declares its attempts gets
no deadline and makes all of them; its count still weighs in the others'
shares. `check()` uses a property's declared attempts, else
`baseline_attempts`, and no deadline.

### No Silent Fallbacks
Broken test modules, unknown module names, `--select` patterns matching
no property, missing test directories, duplicate property descriptions (within a spec and across the modules of
a run), missing generators and invalid arguments are hard errors
(`SpecificationError`, `ValueError`, `TypeError`). A property most of
whose attempts are discarded fails loudly. Unreachable match arms use
`typing.assert_never`.

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
messages at commit-msg and runs mypy on `minigun`, `scripts/bench` and
`scripts/mutate.py` at pre-push.

## Project Configuration

- Uses uv for dependency management
- Python >=3.12 required; single runtime dependency (rich)
- Configured with ruff for linting/formatting (80 char line limit)
- mypy strict settings; `uv run mypy minigun/` must pass with no errors
- Versions are managed by hand. The version is recorded once, in
  `pyproject.toml`; `minigun.__version__` reads it from the installed
  package metadata

## Releasing

Commit types do not decide versions; the maintainer chooses the bump.
Record changes under `## Unreleased` in `CHANGELOG.md` as they land.
To release:
```bash
uv version --bump patch     # or minor / major; updates pyproject.toml and uv.lock
# rename "## Unreleased" in CHANGELOG.md to "## vX.Y.Z (YYYY-MM-DD)"
# merge, then tag the merged commit on main
git tag -a vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z
```
The tag push runs `.github/workflows/release.yml`, which refuses a tag
that does not match the version or has no changelog entry, then builds,
publishes to PyPI and creates the GitHub release with that entry as notes.
