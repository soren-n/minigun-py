# CORE_CONCEPTS.md

## Property-Based Testing Fundamentals

Property-based testing is a methodology where you specify **properties** that your code should satisfy, and the testing framework generates hundreds of test cases to verify these properties hold.

## Core Concepts in Minigun

### 1. Properties
**Definition:** Mathematical statements about your code that should be true for all valid inputs.

**Examples:**
```python
# Identity property: reversing twice gives original
@prop("reverse is its own inverse")
def test_reverse_inverse(lst: list[int]) -> bool:
    return reverse(reverse(lst)) == lst

# Associativity: (a + b) + c == a + (b + c)
@prop("addition is associative")
def test_add_associative(a: int, b: int, c: int) -> bool:
    return (a + b) + c == a + (b + c)

# Postcondition: sorted list is actually sorted
@prop("sort produces sorted output")
def test_sort_postcondition(lst: list[int]) -> bool:
    result = sorted(lst)
    return all(result[i] <= result[i+1] for i in range(len(result)-1))
```

**Key Insight:** Properties describe **what** your code should do, not specific input/output examples.

### 2. Generators
**Definition:** Functions that produce random test data of specific types.

**Basic Generators:**
```python
g.int_range(0, 100)          # Integers between 0 and 100
g.str()                      # Random strings
g.bounded_list(0, 5, g.int_range(0, 10))  # Lists of 0-5 integers
g.maybe(g.str())             # Optional strings (None or Some(string))
```

**Generator Combinators:**
```python
# Compose generators to create complex data
person_gen = g.tuple(
    g.str(),                 # name
    g.int_range(0, 120),     # age
    g.one_of(["M", "F", "X"]) # gender
)

# Use bind for dependent generation
def person_with_valid_email(name: str) -> Generator[tuple[str, str]]:
    email_gen = g.map(lambda domain: f"{name.lower()}@{domain}",
                      g.one_of(["gmail.com", "yahoo.com"]))
    return g.tuple(g.constant(name), email_gen)

dependent_gen = g.bind(person_with_valid_email, g.str())
```

### 3. Domains
**Definition:** High-level specifications for test data that can be reused across properties.

**Built-in Domains:**
```python
d.small_nat()                # Small natural numbers (0-100)
d.int_range(-1000, 1000)     # Bounded integers
d.str()                      # Random strings
d.bool()                     # Boolean values
```

**Usage with Context:**
```python
@context(d.small_nat(), d.str())
@prop("string concatenation length")
def test_concat_length(n: int, s: str) -> bool:
    repeated = s * n
    return len(repeated) == len(s) * n
```

### 4. Shrinking
**Definition:** When a property fails, automatically find the minimal input that still causes failure.

**How it Works:**
1. Property fails with complex input: `[42, -17, 999, 3, -8]`
2. Shrinking tries smaller variants: `[42, -17, 999]`, `[42, -17]`, `[42]`, `[-17]`
3. Finds minimal failure: `[-17]` (if negative numbers cause the bug)

**Implementation Detail:**
```python
# Each generated value comes with shrinking information
Dissection[T] = tuple[T, Stream[Dissection[T]]]
#                    ^value  ^shrinking_options

# Example: integer 42 might shrink to [21, 10, 5, 1, 0]
# Lists shrink by: removing elements, shrinking elements, changing order
```

**Benefits:**
- Makes debugging easier with minimal failing cases
- Reduces noise in error reports
- Helps identify root causes of failures

### 5. Test Specifications
**Definition:** Declarative way to define and compose tests using decorators and combinators.

**Basic Property:**
```python
@prop("property description")
def test_something(x: int) -> bool:
    return some_condition(x)
```

**Property with Context:**
```python
@context(d.int_range(1, 100))
@prop("positive numbers stay positive when squared")
def test_positive_square(x: int) -> bool:
    return x * x > 0
```

**Conjunction (AND logic):**
```python
# Both properties must pass
combined_test = conj(
    property1,
    property2,
    property3
)
```

**Negation (Expected Failures):**
```python
@neg("this should fail")
@prop("deliberately broken property")
def test_expected_failure(x: int) -> bool:
    return x != x  # Always false - should fail and be caught by neg()
```

### 6. Counterexample Search
**Definition:** Systematically explore the input space to find cases where properties fail.

**Search Strategy:**
```python
# In search.py
def find_counter_example(
    state: State,
    max_attempts: int,
    property_function: Callable,
    generators: dict[str, Generator]
) -> tuple[State, Maybe[dict[str, Any]]]:
    # Try up to max_attempts to find input that makes property return False
    # If found, shrink it to minimal counterexample
    # Return the counterexample or Nothing if property always passes
```

**Usage:**
- Exhaustive testing within computational limits
- Statistical confidence based on sample size
- Targeted exploration of boundary conditions

## Advanced Concepts

### 7. Statistical Testing
**Principle:** Properties should hold for a large, diverse sample of inputs.

**Sample Size Considerations:**
- More samples = higher confidence
- Diminishing returns after certain point
- Balance between test time and confidence

**Randomness Quality:**
- Deterministic PRNG with explicit seed management
- Reproducible test runs for debugging
- Good distribution across input space

### 8. Invariant-Based Testing
**Approach:** Define invariants that must always be maintained.

**Examples:**
```python
# Data structure invariants
@prop("heap property maintained after insertion")
def test_heap_insert(heap: Heap[int], value: int) -> bool:
    new_heap = heap.insert(value)
    return is_valid_heap(new_heap)

# Round-trip invariants
@prop("serialize/deserialize round-trip")
def test_serialization(obj: MyObject) -> bool:
    serialized = serialize(obj)
    deserialized = deserialize(serialized)
    return obj == deserialized
```

### 9. Metamorphic Testing
**Approach:** Test relationships between different inputs rather than exact outputs.

**Examples:**
```python
# Scaling property
@prop("scaling preserves ratios")
def test_scale_preserves_ratios(image: Image, factor: float) -> bool:
    scaled = scale_image(image, factor)
    return (scaled.width / image.width) == factor

# Commutativity
@prop("addition is commutative")
def test_add_commutative(a: int, b: int) -> bool:
    return add(a, b) == add(b, a)
```

### 10. Error Handling Testing
**Approach:** Use generators to test edge cases and error conditions.

**Examples:**
```python
# Test that invalid inputs are properly rejected
@prop("invalid inputs raise appropriate exceptions")
def test_input_validation(invalid_input: InvalidData) -> bool:
    try:
        process(invalid_input)
        return False  # Should have raised exception
    except ValidationError:
        return True   # Expected behavior
    except Exception:
        return False  # Wrong exception type
```

## Property-Based Testing Patterns

### 1. **The Oracle Pattern**
Compare your implementation with a reference implementation or mathematical formula.

### 2. **The Inverse Pattern**
Apply operation and its inverse, verify you get back to original.

### 3. **The Invariant Pattern**
Define properties that should never be violated by any operation.

### 4. **The Idempotent Pattern**
Applying operation multiple times gives same result as applying once.

### 5. **The Postcondition Pattern**
Verify that operation results satisfy expected conditions.

These concepts form the foundation for understanding and extending Minigun's property-based testing capabilities.
