# GENERATOR_SYSTEM.md

## Generator System Deep Dive

The generator system is the heart of Minigun, responsible for creating random test data and enabling shrinking when tests fail. Understanding this system is essential for working with or extending Minigun.

## Core Generator Concepts

### Generator Type Definition
```python
type Sample[T] = tuple[a.State, Maybe[s.Dissection[T]]]
type Generator[T] = Callable[[a.State], Sample[T]]
```

**Key Points:**
- Generators are **functions** that take PRNG state and return (new_state, maybe_dissection)
- **State threading** ensures reproducible randomness
- **Maybe types** handle generation failures gracefully
- **Dissections** couple values with shrinking information

### Dissection Structure
```python
type Dissection[T] = tuple[T, Stream[Dissection[T]]]
#                         ^value  ^shrinking_options
```

**Example:**
```python
# Integer 42 with shrinking to smaller values
dissection = (42, stream([
    (21, stream([...])),  # Half the value
    (10, stream([...])),  # Smaller step
    (0,  stream([]))      # Minimal value
]))
```

## Core Generator Categories

### 1. Primitive Generators
**Location:** `generate.py` - Basic building blocks

```python
# Constants
g.constant(42)           # Always generates 42
g.none()                 # Always generates None

# Basic types
g.bool()                 # True or False
g.nat()                  # Natural numbers (0, 1, 2, ...)
g.int_range(0, 100)      # Integers within bounds
g.float_range(0.0, 1.0)  # Floats within bounds
g.char()                 # Single characters
```

**Implementation Pattern:**
```python
def bool() -> Generator[bool]:
    def _impl(state: a.State) -> Sample[bool]:
        state, result = a.bool(state)  # Get random bool from PRNG
        # Create dissection with original value and its negation as shrink option
        return state, Some(s.prepend(result, s.singleton(not result)))
    return _impl
```

### 2. Collection Generators
**Location:** `generate.py` - Data structures

```python
# Bounded collections
g.bounded_list(0, 10, g.int_range(0, 100))    # Lists of 0-10 integers
g.bounded_set(0, 5, g.str())                  # Sets of 0-5 strings
g.bounded_dict(0, 3, g.str(), g.int_range(0, 100))  # Dicts with 0-3 entries

# Unbounded (with reasonable defaults)
g.list(g.int_range(0, 100))                   # Lists with default size bounds
g.set(g.str())                                # Sets with default size bounds
```

**Shrinking Strategy for Collections:**
1. **Remove elements** (shorter collections)
2. **Shrink individual elements** (simpler element values)
3. **Reorder elements** (for unordered collections)

### 3. Combinator Generators
**Location:** `generate.py` - Composition and selection

```python
# Choice and selection
g.choice(gen1, gen2, gen3)                    # Pick one generator randomly
g.one_of([1, 2, 3, 4, 5])                    # Pick from list of values
g.weighted_choice([(gen1, 3), (gen2, 1)])    # Weighted selection

# Composition
g.tuple(g.int_range(0, 100), g.str())         # Generate tuples
g.maybe(g.str())                              # Optional values (None or Some)
```

### 4. Higher-Order Generators
**Location:** `generate.py` - Generator transformations

```python
# Transformation
g.map(lambda x: x * 2, g.int_range(0, 100))  # Transform generated values
g.filter(lambda x: x % 2 == 0, g.int_range(0, 100))  # Only even numbers
g.bind(lambda n: g.bounded_list(n, n, g.str()), g.int_range(1, 5))  # Dependent generation
```

## Advanced Generator Patterns

### 1. Map Combinator
**Purpose:** Transform generated values while preserving shrinking.

```python
def map[*P, R](func: Callable[[*P], R], *generators: Generator[Any]) -> Generator[R]:
    def _impl(state: a.State) -> Sample[R]:
        dissections: list[s.Dissection[Any]] = []
        for generator in generators:
            state, maybe_dissection = generator(state)
            match maybe_dissection:
                case Maybe.empty:
                    return state, Nothing  # Early failure propagation
                case Some(dissection):
                    dissections.append(dissection)
        return state, Some(s.map(func, *dissections))  # Transform dissections
    return _impl
```

**Key Features:**
- **Variadic** - can map over multiple generators
- **Failure propagation** - if any generator fails, whole mapping fails
- **Shrinking preservation** - shrinks inputs and maps function over them

### 2. Bind Combinator (Monadic Composition)
**Purpose:** Create dependent generators where later choices depend on earlier values.

```python
def bind[*P, R](func: Callable[[*P], Generator[R]], *generators: Generator[Any]) -> Generator[R]:
    def _impl(state: a.State) -> Sample[R]:
        values: list[Any] = []
        for generator in generators:
            state, maybe_dissection = generator(state)
            match maybe_dissection:
                case Maybe.empty:
                    return state, Nothing
                case Some(dissection):
                    values.append(s.head(dissection))  # Extract value, lose shrinking
        return func(*values)(state)  # Create new generator based on values
    return _impl
```

**Key Difference from Map:**
- **Value extraction** - uses actual values, not dissections
- **Generator creation** - function returns a new generator
- **Shrinking limitation** - cannot shrink the dependent part

**Example Use Case:**
```python
# Generate person with age-appropriate email domain
def person_generator(age: int) -> Generator[tuple[int, str]]:
    if age < 18:
        email_gen = g.map(lambda name: f"{name}@school.edu", g.word())
    else:
        email_gen = g.one_of(["@gmail.com", "@work.com", "@company.org"])
    return g.tuple(g.constant(age), email_gen)

# Bind age generator to person generator
person = g.bind(person_generator, g.int_range(10, 80))
```

### 3. Filter Combinator
**Purpose:** Generate only values that satisfy a predicate.

**Implementation:**
```python
def filter[T](predicate: Callable[[T], bool], generator: Generator[T]) -> Generator[T]:
    def _impl(state: a.State) -> Sample[T]:
        state, maybe_dissection = generator(state)
        match maybe_dissection:
            case Maybe.empty:
                return state, Nothing
            case Some(dissection):
                match s.filter(predicate, dissection):  # Filter dissection
                    case Maybe.empty:
                        return state, Nothing  # No valid value found
                    case Some(filtered_dissection):
                        return state, Some(filtered_dissection)
        return _impl
```

**Important:** May fail if no generated values satisfy predicate. Use sparingly and with predicates that have high success rates.

## Collection Generator Internals

### Bounded List Generator
**Key Implementation Details:**

```python
def bounded_list[T](lower_bound: int, upper_bound: int, generator: Generator[T]) -> Generator[list[T]]:
    def _impl(state: a.State) -> Sample[list[T]]:
        state, length = a.nat(state, lower_bound, upper_bound)  # Random length
        result: list[s.Dissection[T]] = []

        # Generate each element
        for _ in range(length):
            state, maybe_item = generator(state)
            match maybe_item:
                case Maybe.empty:
                    return state, Nothing  # Propagate failure
                case Some(item):
                    result.append(item)

        return state, Some(_dist(result))  # Create list dissection
```

**Shrinking Strategy (_dist function):**
```python
def _dist(dissections: list[s.Dissection[T]]) -> s.Dissection[list[T]]:
    heads = [s.head(d) for d in dissections]  # Current values
    tails = [s.tail(d) for d in dissections]  # Shrinking streams

    # Create shrinking stream that:
    # 1. Shrinks by removing elements (shorter lists)
    # 2. Shrinks individual elements (simpler values)
    shrink_stream = fs.concat([
        _shrink_length(0, dissections),    # Remove elements
        _shrink_value(0, heads, tails)     # Shrink elements
    ])

    return heads, shrink_stream
```

### Set Generator Differences
**Key Points:**
- Similar to list generator but handles **duplicates**
- **Set shrinking** focuses on removing elements rather than reordering
- **Hash-based** element management

```python
def bounded_set[T](lower_bound: int, upper_bound: int, generator: Generator[T]) -> Generator[set[T]]:
    # Generate list first, then convert to set
    # This naturally handles duplicates (set will be smaller than requested)
    def _impl(state: a.State) -> Sample[set[T]]:
        state, size = a.nat(state, lower_bound, upper_bound)
        # ... generate elements similar to list ...
        return state, Some(_dist_set(result))  # Set-specific dissection
```

## Domain Integration

### Domain Layer
**Location:** `domain.py` - High-level abstractions over generators

```python
class Domain[T]:
    def __init__(self, generator: Generator[T], printer: Printer[T]):
        self.generator = generator
        self.printer = printer

    def generate(self, state: a.State) -> Sample[T]:
        return self.generator(state)
```

**Built-in Domains:**
```python
d.small_nat()                    # Natural numbers 0-100
d.int_range(-1000, 1000)         # Bounded integers
d.str()                          # Random strings
d.bool()                         # Boolean values
d.small_int()                    # Small integers -100 to 100
```

**Usage Pattern:**
```python
@context(d.small_nat(), d.str())
@prop("string repetition length")
def test_string_repeat(n: int, s: str) -> bool:
    return len(s * n) == len(s) * n
```

## Performance Considerations

### Generator Composition Overhead
- **Deep composition** can create performance bottlenecks
- **Early failure** propagation minimizes wasted computation
- **Stream laziness** prevents memory issues with large collections

### Shrinking Performance
- **Bounded exploration** - streams respect limits
- **Efficient strategies** - prioritize likely successful shrinks
- **Caching** - avoid recomputing the same shrinks

### Memory Management
- **Lazy streams** don't materialize entire shrinking spaces
- **Bounded generation** prevents infinite memory usage
- **Immutable state** simplifies garbage collection

## Extension Guidelines

### Adding New Primitive Generators
1. **Follow naming** conventions (`snake_case`)
2. **Include bounds** checking and validation
3. **Implement efficient** shrinking strategies
4. **Add comprehensive** tests in `tests/` modules
5. **Document behavior** with docstrings

### Custom Combinator Patterns
1. **Use existing** combinators when possible
2. **Handle failure** cases with `Maybe.empty`
3. **Thread state** properly through all operations
4. **Preserve shrinking** information where feasible
5. **Test edge cases** thoroughly

### Domain Extensions
1. **Create logical** groupings of related generators
2. **Include appropriate** printers for output formatting
3. **Consider reusability** across different properties
4. **Document intended** use cases

The generator system's power comes from composability - simple generators combine to create complex data while maintaining shrinking capabilities throughout the composition chain.
