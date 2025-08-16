# TESTING_STRATEGY.md

## Testing Strategy for Minigun

Minigun uses itself for testing - a powerful demonstration of property-based testing in action. This document explains the testing philosophy, organization, and best practices used in the project.

## Self-Testing Philosophy

### Why Self-Testing?
1. **Dogfooding** - We use our own product, discovering issues early
2. **Demonstration** - Shows property-based testing in realistic use
3. **Confidence** - If Minigun can test itself, it can test anything
4. **Validation** - Proves the core concepts work in practice

### Challenges of Self-Testing
1. **Bootstrap problem** - Need working system to test itself
2. **Infinite recursion** - Must avoid circular dependencies
3. **Coverage gaps** - Some edge cases hard to reach via properties
4. **Error interpretation** - Failures might be in test or implementation

## Test Module Organization

### Test Module Structure
```
tests/
├── __init__.py
├── main.py              # Test runner and orchestration
├── positive.py          # Tests expected to pass
├── negative.py          # Tests expected to fail
├── comprehensive.py     # Broad functionality coverage
└── additional.py        # Edge cases and specific scenarios
```

### Module Responsibilities

#### `positive.py` - Expected Successes
**Purpose:** Properties that should always hold for correct implementations.

```python
@prop("reverse is its own inverse")
def test_reverse_inverse(lst: list[int]) -> bool:
    return reverse(reverse(lst)) == lst

@prop("map preserves list length")
def test_map_preserves_length(lst: list[int]) -> bool:
    doubled = [x * 2 for x in lst]
    return len(doubled) == len(lst)
```

**Categories:**
- Mathematical properties (commutativity, associativity, etc.)
- Data structure invariants
- Algorithm correctness properties
- API contract verification

#### `negative.py` - Expected Failures
**Purpose:** Properties that should fail, testing the failure detection system.

```python
@neg("this property should fail")
@prop("deliberately broken property")
def test_expected_failure(x: int) -> bool:
    return x != x  # Always false - should be caught by neg()

@neg("division by zero should be caught")
@prop("unsafe division")
def test_division_failure(x: int) -> bool:
    return x / 0 == 0  # Should raise exception
```

**Categories:**
- Logic errors that should be detected
- Boundary condition failures
- Exception handling verification
- Shrinking effectiveness tests

#### `comprehensive.py` - Broad Coverage
**Purpose:** Extensive testing of core functionality across all modules.

```python
###############################################################################
# Tests for arbitrary.py - PRNG state and basic generation
###############################################################################

@context(d.int_range(-1000, 1000), d.int_range(-1000, 1000))
@prop("nat generates values within bounds")
def test_nat_bounds(lower: int, upper: int) -> bool: ...

###############################################################################
# Tests for generate.py - Generator combinators
###############################################################################

@context(d.small_nat())
@prop("map preserves structure with identity function")
def test_map_identity(seed_val: int) -> bool: ...
```

**Organization by Module:**
- Each major module gets dedicated test section
- Tests cover all public APIs
- Focus on integration between modules
- Stress test complex interactions

#### `additional.py` - Edge Cases and Specific Scenarios
**Purpose:** Target specific edge cases and low-coverage areas.

```python
@context(d.small_nat())
@prop("constant generator always produces the same value")
def test_constant_generator(seed_val: int) -> bool: ...

@context(d.small_nat())
@prop("zero-length bounded collections work")
def test_zero_length_bounded_collections(seed_val: int) -> bool: ...
```

**Focus Areas:**
- Boundary conditions (empty collections, zero values, etc.)
- Error conditions and recovery
- Performance edge cases
- Unusual but valid inputs

## Property-Based Testing Patterns

### 1. Identity Properties
**Pattern:** Operations that should be reversible.

```python
@prop("encode/decode round-trip")
def test_encoding_roundtrip(data: bytes) -> bool:
    encoded = encode(data)
    decoded = decode(encoded)
    return decoded == data
```

### 2. Invariant Properties
**Pattern:** Properties that should never be violated.

```python
@prop("sorted list remains sorted after insertion")
def test_sorted_insertion(lst: list[int], value: int) -> bool:
    sorted_lst = sorted(lst)
    inserted = insert_sorted(sorted_lst, value)
    return is_sorted(inserted)
```

### 3. Equivalence Properties
**Pattern:** Different implementations should produce same results.

```python
@prop("custom sort equals built-in sort")
def test_sort_equivalence(lst: list[int]) -> bool:
    custom_result = custom_sort(lst.copy())
    builtin_result = sorted(lst)
    return custom_result == builtin_result
```

### 4. Metamorphic Properties
**Pattern:** Relationships between inputs and outputs.

```python
@prop("scaling preserves aspect ratio")
def test_scaling_aspect_ratio(width: int, height: int, factor: float) -> bool:
    original_ratio = width / height if height != 0 else 0
    scaled_width, scaled_height = scale(width, height, factor)
    scaled_ratio = scaled_width / scaled_height if scaled_height != 0 else 0
    return abs(original_ratio - scaled_ratio) < 0.001
```

### 5. Statistical Properties
**Pattern:** Properties about distributions and randomness.

```python
@prop("random generation produces diverse values")
def test_generation_diversity(seed: int) -> bool:
    state = a.seed(seed)
    values = []
    for _ in range(100):
        state, maybe_val = g.int_range(0, 1000)(state)
        match maybe_val:
            case Some(dissection):
                values.append(s.head(dissection))

    # Should see reasonable diversity
    unique_values = len(set(values))
    return unique_values > 50  # At least 50% unique
```

## Test Data Strategies

### 1. Domain Selection
**Choose appropriate domains for each property:**

```python
# Small domains for complex properties
@context(d.small_nat(), d.small_nat())
@prop("complex mathematical relationship")

# Large domains for simple properties
@context(d.int_range(-10000, 10000))
@prop("basic arithmetic property")

# Specific domains for edge cases
@context(d.one_of([0, 1, -1]))
@prop("behavior at special values")
```

### 2. Dependent Data Generation
**Use bind for related test data:**

```python
def test_list_operations():
    def list_with_valid_index(lst: list[int]) -> Generator[tuple[list[int], int]]:
        if not lst:
            return g.constant((lst, 0))
        index_gen = g.int_range(0, len(lst) - 1)
        return g.tuple(g.constant(lst), index_gen)

    @context(d.from_generator(g.bind(list_with_valid_index, g.bounded_list(1, 10, g.small_int()))))
    @prop("list indexing never fails")
    def test_valid_indexing(lst_and_index: tuple[list[int], int]) -> bool:
        lst, index = lst_and_index
        return 0 <= index < len(lst)
```

### 3. Shrinking Validation
**Test that shrinking finds minimal counterexamples:**

```python
@prop("shrinking finds minimal counterexample")
def test_shrinking_effectiveness(seed: int) -> bool:
    # Create a property that fails for values > 50
    def failing_prop(x: int) -> bool:
        return x <= 50

    state = a.seed(seed)
    generators = {"x": g.int_range(51, 100)}  # Ensure failure

    state, maybe_counter = search.find_counter_example(state, 10, failing_prop, generators)

    match maybe_counter:
        case Some(counter):
            # Should shrink to 51 (minimal failing value)
            return counter["x"] == 51
        case Maybe.empty:
            return False  # Should have found a counterexample
```

## Test Execution Strategy

### 1. Modular Execution
**Run specific test modules as needed:**

```bash
# Run all tests
uv run minigun-test

# Run specific modules
uv run minigun-test --modules positive comprehensive

# Quiet mode for CI/CD
uv run minigun-test --quiet
```

### 2. Progress Reporting
**Rich output with progress indicators:**

```python
# In cli.py
reporter = TestReporter(verbose=True)
set_reporter(reporter)

reporter.start_testing(len(test_modules))
for module_name, test_func in test_modules.items():
    reporter.start_module(module_name)
    success = test_func()
    reporter.end_module()

reporter.print_summary()
```

### 3. Error Handling and Debugging
**Comprehensive error information:**

```python
try:
    success = test_func()
except Exception as e:
    print(f"Error in module {module_name}: {e}")
    # Include full traceback in verbose mode
    if verbose:
        import traceback
        traceback.print_exc()
```

## Best Practices for Test Development

### 1. Property Design
- **Start simple** - Basic properties first, complex ones later
- **Think mathematically** - Look for algebraic properties
- **Consider edge cases** - Empty inputs, boundary values, error conditions
- **Test the test** - Use `neg()` to verify failure detection

### 2. Generator Selection
- **Match complexity** - Simple generators for complex properties
- **Consider distribution** - Ensure good coverage of input space
- **Balance efficiency** - Don't make generators too restrictive
- **Test generators** - Verify they produce expected distributions

### 3. Debugging Failed Properties
- **Use shrinking** - Minigun will find minimal counterexample
- **Add logging** - Print intermediate values during property evaluation
- **Isolate the issue** - Create focused tests for suspected problems
- **Check assumptions** - Verify your understanding of the property

### 4. Performance Considerations
- **Limit generation** - Use reasonable bounds to prevent infinite generation
- **Monitor test time** - Properties should complete in reasonable time
- **Profile bottlenecks** - Identify slow generators or properties
- **Balance thoroughness** - More test cases vs. execution time

### 5. Maintenance Guidelines
- **Update with changes** - Properties should reflect current behavior
- **Document edge cases** - Explain non-obvious property requirements
- **Refactor common patterns** - Extract reusable test utilities
- **Review coverage** - Ensure new features have corresponding tests

This testing strategy ensures Minigun is thoroughly validated while serving as a comprehensive example of property-based testing in practice.
