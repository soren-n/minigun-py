# API_PATTERNS.md

## API Design Patterns and Conventions

This document outlines the consistent patterns and conventions used throughout the Minigun codebase. Following these patterns ensures code consistency and maintainability.

## Core API Design Principles

### 1. Functional Programming First
- **Immutable data structures** wherever possible
- **Pure functions** with explicit state management
- **No global state** - everything explicitly passed
- **Monadic error handling** with `Maybe` types

### 2. Type Safety and Generics
- **Comprehensive type annotations** on all public APIs
- **Generic type parameters** for reusable components
- **Type aliases** for complex types to improve readability
- **Runtime type validation** where beneficial

### 3. Composable Design
- **Small, focused functions** that do one thing well
- **Combinator patterns** for building complex behavior from simple parts
- **Consistent interfaces** across similar functionality
- **Minimal coupling** between modules

## Common Type Patterns

### 1. State Threading Pattern
**Used everywhere PRNG state is needed:**

```python
def operation_with_state(state: a.State, *args) -> tuple[a.State, ResultType]:
    # Perform operation that consumes randomness
    state, intermediate = some_random_operation(state)
    state, result = another_operation(state, intermediate)
    return state, result
```

**Rules:**
- **Always return** updated state as first element of tuple
- **Thread state** through all random operations in sequence
- **Never mutate** state - treat as immutable

### 2. Maybe Type Error Handling
**Used for operations that can fail gracefully:**

```python
from returns.maybe import Maybe, Some, Nothing

def safe_operation(input: T) -> Maybe[ResultType]:
    match condition:
        case valid:
            return Some(result)
        case invalid:
            return Nothing
```

**Pattern Matching with Maybe:**
```python
match maybe_value:
    case Maybe.empty:
        # Handle failure case - usually early return
        return handle_failure()
    case Some(value):
        # Continue with success case
        process(value)
    case _:
        raise AssertionError("Invariant")  # Always include this
```

### 3. Generator Function Pattern
**All generators follow this structure:**

```python
def generator_name[T](*params) -> Generator[T]:
    """Docstring explaining what the generator produces.

    :param param: Description
    :type param: Type
    :return: Description
    :rtype: Generator[T]
    """

    def _impl(state: a.State) -> Sample[T]:
        # Implementation logic here
        # Always return (state, Maybe[Dissection[T]])
        return state, Some(dissection)

    return _impl
```

**Rules:**
- **Private implementation** function named `_impl`
- **Return the implementation** function, don't call it
- **Handle failure** cases with `Maybe.empty`
- **Include comprehensive** docstrings

### 4. Dissection Creation Pattern
**For creating shrinkable values:**

```python
def create_dissection(value: T, shrink_strategy: Callable) -> s.Dissection[T]:
    # Create shrinking stream lazily
    shrink_stream = fs.lazy_stream(lambda: shrink_strategy(value))
    return value, shrink_stream
```

**Common Dissection Helpers:**
```python
s.singleton(value)           # Value with no shrinking options
s.prepend(value, other_dissection)  # Add value before existing dissection
s.map(func, dissection)      # Transform dissection with function
s.filter(predicate, dissection)  # Filter dissection by predicate
```

## Naming Conventions

### 1. Module Level
```python
# External imports first
import math
import string

# Standard library imports
from typing import Any, Callable
from collections.abc import Iterator

# Third-party imports
from returns.maybe import Maybe, Some, Nothing

# Internal imports (relative)
from minigun import arbitrary as a
from minigun import shrink as s
```

### 2. Function Naming
```python
# Generators: describe what they generate
def int_range(lower: int, upper: int) -> Generator[int]: ...
def bounded_list(lower: int, upper: int, gen: Generator[T]) -> Generator[list[T]]: ...

# Combinators: describe the operation
def map(func: Callable, *generators: Generator) -> Generator: ...
def filter(predicate: Callable, generator: Generator) -> Generator: ...
def choice(*generators: Generator) -> Generator: ...

# Utilities: verb_noun pattern
def find_counter_example(...) -> ...: ...
def create_dissection(...) -> ...: ...
```

### 3. Type Aliases
```python
# Clear, descriptive names for complex types
type Sample[T] = tuple[a.State, Maybe[s.Dissection[T]]]
type Generator[T] = Callable[[a.State], Sample[T]]
type Printer[T] = Callable[[T], str]
```

### 4. Variable Naming
```python
# Descriptive names for important concepts
state: a.State                    # PRNG state
maybe_dissection: Maybe[s.Dissection[T]]  # Optional dissection
generators: list[Generator[T]]     # List of generators
```

## Error Handling Patterns

### 1. Validation Pattern
**Used at API boundaries:**

```python
def bounded_operation(lower: int, upper: int, value: T) -> Result:
    # Validate preconditions
    assert lower <= upper, f"Invalid bounds: {lower} > {upper}"
    assert 0 <= lower, f"Lower bound must be non-negative: {lower}"

    # Proceed with operation
    return implementation(lower, upper, value)
```

### 2. Graceful Failure Pattern
**Used in generators and combinators:**

```python
def possibly_failing_generator(state: a.State) -> Sample[T]:
    # Attempt operation
    result = try_operation()

    match result:
        case Success(value):
            return state, Some(create_dissection(value))
        case Failure():
            return state, Nothing  # Graceful failure
```

### 3. Invariant Assertion Pattern
**Used for maintaining internal consistency:**

```python
match value:
    case ExpectedCase1():
        return handle_case1()
    case ExpectedCase2():
        return handle_case2()
    case _:
        raise AssertionError("Invariant")  # Should never happen
```

## Documentation Patterns

### 1. Function Docstrings
**Sphinx-compatible format:**

```python
def function_name(param1: Type1, param2: Type2) -> ReturnType:
    """Brief description of what the function does.

    Longer explanation if needed, including examples:

    .. code-block:: python

        result = function_name(arg1, arg2)

    :param param1: Description of parameter
    :type param1: Type1
    :param param2: Description of parameter
    :type param2: Type2
    :return: Description of return value
    :rtype: ReturnType
    :raises SomeError: When this error occurs
    """
```

### 2. Type Annotations
**Always comprehensive and precise:**

```python
# Use specific types, not Any when possible
def process_items(items: list[str]) -> dict[str, int]: ...

# Use generics for reusable functions
def map_values[T, R](func: Callable[[T], R], items: list[T]) -> list[R]: ...

# Use type aliases for complex signatures
ProcessorFunc = Callable[[list[str]], dict[str, int]]
def apply_processor(processor: ProcessorFunc) -> Result: ...
```

### 3. Module Docstrings
**Include purpose and key exports:**

```python
"""
Module for generating random test data.

This module provides the core generator system for property-based testing,
including primitive generators, combinators, and collection generators.

Key exports:
    - Generator[T]: Type alias for generator functions
    - map, filter, bind: Core combinators
    - int_range, str, list: Common generators
"""
```

## Testing Patterns

### 1. Property Definition Pattern
**Consistent structure for all properties:**

```python
@context(d.domain1(), d.domain2())
@prop("descriptive property name")
def test_property_name(param1: Type1, param2: Type2) -> bool:
    """Optional docstring explaining the property."""

    # Setup if needed
    setup_value = prepare(param1, param2)

    # Apply operation
    result = operation(setup_value)

    # Verify property
    return property_holds(result)
```

### 2. Test Organization Pattern
**Group related tests in modules:**

```python
###############################################################################
# Tests for specific functionality - descriptive comment
###############################################################################

@context(...)
@prop("first property in group")
def test_first_property(...) -> bool: ...

@context(...)
@prop("second property in group")
def test_second_property(...) -> bool: ...

###############################################################################
# Tests for different functionality
###############################################################################
```

### 3. Conjunction Pattern
**For combining multiple properties:**

```python
def test_combined_properties():
    """Test multiple related properties together."""
    return check(conj(
        property1,
        property2,
        property3
    ))
```

## Performance Patterns

### 1. Lazy Evaluation Pattern
**For potentially expensive operations:**

```python
def lazy_operation(params) -> Iterator[ResultType]:
    """Yield results on demand rather than computing all upfront."""
    for item in large_collection:
        if expensive_condition(item):
            yield expensive_computation(item)
```

### 2. Bounded Exploration Pattern
**For potentially infinite spaces:**

```python
def bounded_search(space: InfiniteSpace, max_attempts: int) -> Maybe[Result]:
    """Search infinite space with termination guarantee."""
    for _ in range(max_attempts):
        candidate = space.next()
        if satisfies_condition(candidate):
            return Some(candidate)
    return Nothing
```

### 3. Memoization Pattern
**For expensive pure computations:**

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_pure_function(immutable_input: tuple) -> Result:
    """Cache results of expensive computations."""
    return expensive_computation(immutable_input)
```

## Integration Patterns

### 1. CLI Integration Pattern
**For command-line tools:**

```python
def main():
    """Main entry point with proper error handling."""
    try:
        args = parse_arguments()
        result = run_operation(args)
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("Operation cancelled")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
```

### 2. Reporter Integration Pattern
**For progress reporting:**

```python
def operation_with_reporting(reporter: Optional[Reporter]) -> Result:
    """Include optional reporting in long operations."""
    if reporter:
        reporter.start_operation("operation_name")

    try:
        # Perform operation with progress updates
        for i, item in enumerate(items):
            result = process(item)
            if reporter:
                reporter.update_progress(i, len(items))

        if reporter:
            reporter.end_operation(success=True)
        return result

    except Exception as e:
        if reporter:
            reporter.end_operation(success=False, error=str(e))
        raise
```

Following these patterns ensures consistency across the codebase and makes the code easier to understand, maintain, and extend.
