# ARCHITECTURE_GUIDE.md

## Minigun Architecture Overview

Minigun follows a layered architecture that separates concerns while maintaining functional programming principles. Understanding these layers and their interactions is crucial for effective development.

## Architectural Layers

### Layer 1: Foundation (Bottom Layer)
**Files:** `arbitrary.py`, `util.py`, `order.py`

**Purpose:** Provides fundamental building blocks and utilities.

- **`arbitrary.py`** - PRNG state management, core random generation functions
- **`util.py`** - General-purpose utilities and helper functions
- **`order.py`** - Ordering and comparison utilities

### Layer 2: Core Data Structures (Middle Layer)
**Files:** `stream.py`, `sample.py`, `shrink.py`

**Purpose:** Implements the core abstractions for data generation and manipulation.

- **`stream.py`** - Lazy functional streams for infinite data sequences
- **`sample.py`** - Dissection data structure for value + shrinking information
- **`shrink.py`** - Shrinking strategies and algorithms

### Layer 3: Generation System (Core Layer)
**Files:** `generate.py`, `domain.py`

**Purpose:** The heart of the system - data generation and domain modeling.

- **`generate.py`** - All data generators, combinators, and composition functions
- **`domain.py`** - High-level domain specifications for test contexts

### Layer 4: Analysis and Optimization (Analysis Layer)
**Files:** `cardinality.py`, `budget.py`

**Purpose:** Cardinality analysis and budget optimization for efficient test allocation.

- **`cardinality.py`** - Unified symbolic cardinality system with Big O notation
- **`budget.py`** - Budget allocation system with Secretary Problem optimization

### Layer 5: Testing Framework (Testing Layer)
**Files:** `specify.py`, `search.py`, `pretty.py`, `reporter.py`

**Purpose:** Property specification, test execution, and result presentation.

- **`specify.py`** - Property definition DSL and test execution engine
- **`search.py`** - Counterexample search and test case exploration
- **`pretty.py`** - Value formatting and display utilities
- **`reporter.py`** - Test progress reporting and results aggregation

### Layer 6: Orchestration and Interface (Interface Layer)
**Files:** `orchestrator.py`, `cli.py`, `__main__.py`

**Purpose:** Test orchestration, command-line interface, and user interaction.

- **`orchestrator.py`** - Two-phase test execution coordination (calibration + execution)
- **`cli.py`** - CLI argument parsing and main entry logic
- **`__main__.py`** - Package entry point for `python -m minigun`

## Key Architectural Patterns

### 1. State Threading Pattern
**Used throughout the codebase for PRNG state management.**

```python
# State is explicitly threaded through all operations
def generate_value(state: a.State) -> tuple[a.State, T]:
    state, value1 = generate_first(state)
    state, value2 = generate_second(state)
    return state, combine(value1, value2)
```

**Why:** Ensures reproducible random generation and avoids global state.

### 2. Monadic Error Handling
**Used with `Maybe` types for safe computation.**

```python
from returns.maybe import Maybe, Some, Nothing

def safe_operation(state: a.State) -> tuple[a.State, Maybe[T]]:
    match condition:
        case valid:
            return state, Some(result)
        case invalid:
            return state, Nothing
```

**Why:** Explicit error handling without exceptions, composable failure modes.

### 3. Lazy Evaluation with Streams
**Used for infinite data sequences and shrinking.**

```python
def lazy_shrink(value: T) -> Stream[T]:
    # Returns infinite stream of progressively smaller values
    return stream_of_shrunk_values(value)
```

**Why:** Memory efficient, allows infinite exploration spaces.

### 4. Dissection Pattern
**Core abstraction linking values with their shrinking information.**

```python
Dissection[T] = tuple[T, Stream[Dissection[T]]]
# (current_value, stream_of_shrunk_dissections)
```

**Why:** Couples data with its reduction strategy, enables automatic shrinking.

## Module Interdependencies

### Critical Dependencies
```
arbitrary.py → (no dependencies - foundation)
util.py → arbitrary.py
order.py → (minimal dependencies)

stream.py → arbitrary.py
sample.py → arbitrary.py, stream.py
shrink.py → arbitrary.py, stream.py, sample.py

generate.py → arbitrary.py, stream.py, sample.py, shrink.py, order.py
domain.py → generate.py (and all its dependencies)

cardinality.py → (minimal dependencies - math, typing)
budget.py → cardinality.py

specify.py → ALL lower layers, budget.py
search.py → generate.py, specify.py
pretty.py → (minimal dependencies)
reporter.py → pretty.py, budget.py

orchestrator.py → reporter.py
cli.py → orchestrator.py, specify.py, reporter.py
__main__.py → cli.py
```

### Dependency Rules
1. **No circular dependencies** - Strict layered architecture
2. **Minimal imports** - Each module imports only what it needs
3. **Interface segregation** - Clean boundaries between layers

## Data Flow Architecture

### Test Execution Flow
```
1. CLI parses arguments → cli.py
2. Test specifications loaded → specify.py
3. Generators created for each property → generate.py
4. Test cases generated using PRNG state → arbitrary.py
5. Properties evaluated with generated data → specify.py
6. Failed cases shrunk to minimal examples → shrink.py
7. Results formatted and reported → pretty.py, reporter.py
```

### Generator Composition Flow
```
1. Basic generators created → generate.py (primitives)
2. Combinators applied → generate.py (bounded_list, tuple, etc.)
3. Domain specifications → domain.py (high-level abstractions)
4. Context applied to properties → specify.py (@context decorator)
```

## Memory Management Strategy

### Lazy Evaluation
- **Streams** are computed on-demand, not stored in memory
- **Shrinking** explores infinite spaces without materializing all values
- **Generation** produces values as needed, not in batches

### State Management
- **PRNG state** is immutable, threaded through computations
- **No global state** - everything is explicitly passed
- **Reproducible** - same seed always produces same sequence

### Resource Cleanup
- **Automatic** - Python's GC handles most cleanup
- **Bounded** - Stream operations respect limits to prevent infinite computation
- **Fail-fast** - Early termination on resource exhaustion

## Extension Points

### Adding New Generators
1. **Location:** Add to `generate.py`
2. **Pattern:** Return `Generator[T]` type
3. **Requirements:** Must support shrinking via dissections
4. **Testing:** Add comprehensive tests in `tests/` modules

### Custom Domains
1. **Location:** Add to `domain.py` or extend existing
2. **Pattern:** Create `Domain[T]` instances
3. **Integration:** Use with `@context` decorators

### New Shrinking Strategies
1. **Location:** Extend `shrink.py`
2. **Pattern:** Return `Stream[Dissection[T]]`
3. **Requirements:** Must preserve failure conditions

### Reporting Extensions
1. **Location:** Extend `reporter.py` or `pretty.py`
2. **Pattern:** Implement reporter interface
3. **Integration:** Set via `set_reporter()`

## Performance Considerations

### Bottlenecks
- **Generator composition** can create deep call stacks
- **Shrinking** may explore large search spaces
- **Stream operations** can cause memory pressure if not properly bounded

### Optimizations
- **Memoization** where appropriate (careful with memory usage)
- **Early termination** in search algorithms
- **Efficient shrinking** strategies that converge quickly

### Profiling Points
- Monitor generator performance with complex compositions
- Track memory usage during shrinking phases
- Measure overall test execution time

This architecture balances functional programming principles with practical performance needs, creating a robust foundation for property-based testing.
