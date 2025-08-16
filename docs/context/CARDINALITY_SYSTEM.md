# CARDINALITY_SYSTEM.md

## Advanced Cardinality and Budget Allocation System

Minigun 2.2.0 introduces a sophisticated cardinality analysis and budget allocation system that optimizes test coverage while respecting time constraints. This system represents a significant advancement in property-based testing efficiency.

## Core Cardinality System

### 1. Unified Symbolic Expressions

The cardinality system uses symbolic mathematics to represent and analyze test space complexity:

```python
# Basic cardinality types
Finite(100)              # Exactly 100 values
Variable("n")            # Parameter-dependent size
Infinite()               # Unbounded domain (∞)

# Composite expressions
Sum(Finite(10), Variable("n"))      # 10 + n
Product(Finite(256), Variable("n")) # 256 × n
Exponential(Finite(2), Variable("n")) # 2^n
```

### 2. Symbolic Expression Engine

Internal symbolic representation with automatic simplification:

```python
# Symbolic operations with overflow protection
_Const(42)                    # Constants
_Var("n")                     # Variables
_Add(left, right)             # Addition
_Mul(left, right)             # Multiplication with overflow protection
_Pow(base, exponent)          # Exponentiation with safety limits
_Log(expr, base=None)         # Logarithms
```

**Key Features:**
- **Automatic simplification** - Reduces expressions to minimal forms
- **Overflow protection** - Prevents infinite computation
- **Type-aware inference** - Infers cardinality from Python type hints

### 3. Big O Notation Support

Asymptotic complexity analysis with standard notation:

```python
BigO(_Const(1))               # O(1) - Constant time
BigO(_Var("n"))               # O(n) - Linear time
BigO(_Var("n") ** _Const(2))  # O(n²) - Quadratic time
BigO(_Var("n") * _Log(_Var("n"))) # O(n log n) - Linearithmic
```

**Complexity Classes:**
- `O(1)` - Constant
- `O(log n)` - Logarithmic
- `O(n)` - Linear
- `O(n²)` - Quadratic
- `O(n^k)` - Polynomial
- `O(∞)` - Infinite

## Budget Allocation System

### 1. Two-Phase Testing Process

**Phase 1: Calibration**
- Run 10 attempts per property to measure execution time
- Calculate time-per-attempt for each property
- Build performance profile for budget allocation

**Phase 2: Execution**
- Apply calculated attempt allocations
- Run full test suite with optimized attempt distribution
- Maximize coverage within time budget

### 2. Secretary Problem Optimization

For infinite cardinality domains, uses Secretary Problem mathematics:

```python
def calculate_secretary_problem_limit(cardinality: Cardinality) -> int:
    """Optimal stopping limit: √cardinality"""
    domain_size = cardinality.evaluate()
    return max(1, int(math.sqrt(domain_size)))
```

**Theory:** The Secretary Problem provides the optimal strategy for exploring infinite spaces - examine √n candidates, then select the best remaining option.

### 3. Multi-Tier Allocation Strategy

Sophisticated attempt allocation based on complexity analysis:

```python
def calculate_optimal_attempts(cardinality: Cardinality) -> int:
    asymptotic = cardinality.asymptotic_class()

    match asymptotic:
        case "O(∞)":     return 1000    # Infinite domains
        case "O(n^k)":   return 50      # Exponential/polynomial
        case "O(n²)":    return 100     # Quadratic
        case "O(n)":     return sqrt(domain_size)  # Linear
        case "O(log n)": return 200     # Logarithmic
        case "O(1)":     return adaptive_scaling(domain_size)
```

### 4. Budget Allocation Algorithm

```python
class BudgetAllocator:
    def finalize_allocation(self):
        total_estimated = sum(p.estimated_time for p in properties)

        if total_estimated <= time_budget:
            # Within budget - boost infinite properties
            self.boost_infinite_properties()
        else:
            # Over budget - scale down proportionally
            self.scale_down_proportionally()
```

**Strategies:**
- **Proportional scaling** - When over budget, scale all properties equally
- **Infinite boosting** - When under budget, give extra attempts to infinite cardinality properties
- **Minimum guarantees** - Ensure every property gets at least 1 attempt

## Type Inference System

### 1. Automatic Cardinality Detection

Infers cardinality from Python type hints:

```python
def infer_cardinality_from_type(type_hint: Any) -> Cardinality:
    match type_hint:
        case bool:           return Finite(2)
        case int:            return Infinite()
        case str:            return BigO(_Const(256) ** _Var('n'))
        case list[T]:        return BigO(element_cardinality ** _Var('n'))
        case dict[K, V]:     return BigO((key_card * val_card) ** _Var('n'))
        case tuple[*args]:   return Product(*[infer(arg) for arg in args])
```

### 2. Generator Integration

Generators automatically provide cardinality information:

```python
# Generators return (function, cardinality) tuples
g.int_range(0, 100)        # → (generator_func, Finite(101))
g.bounded_list(0, 10, gen) # → (generator_func, gen_cardinality^Variable("n"))
g.str()                    # → (generator_func, BigO(256^Variable("n")))
```

## Performance Characteristics

### 1. Symbolic Computation Efficiency

- **Lazy evaluation** - Expressions computed only when needed
- **Memoization** - Results cached for repeated calculations
- **Bounded computation** - Safety limits prevent infinite computation
- **Early termination** - Stop when overflow detected

### 2. Memory Management

- **Immutable expressions** - No mutation, safe for concurrent use
- **Minimal allocation** - Reuse common subexpressions
- **Garbage collection friendly** - No circular references

### 3. Scaling Behavior

**Small domains (< 1000 values):** O(√n) attempts for complete coverage
**Medium domains (1000-1M values):** Logarithmic scaling with base coverage
**Large domains (> 1M values):** Conservative scaling to prevent timeout
**Infinite domains:** Secretary Problem optimization

## Usage Patterns

### 1. Basic Cardinality Analysis

```python
from minigun.cardinality import *

# Analyze test space complexity
card = Product(Finite(256), Variable("n"))  # 256 × n
print(f"Complexity: {card.asymptotic_class()}")  # O(n)
print(f"At n=100: {card.evaluate({'n': 100})}")  # 25600
```

### 2. Budget Planning

```python
from minigun.budget import BudgetAllocator, PropertyBudget

allocator = BudgetAllocator(time_budget=60.0)
allocator.add_property("test_sorting", Linear(Variable("n")))
allocator.add_property("test_search", Logarithmic(Variable("n")))

# After calibration...
allocator.finalize_allocation()
attempts = allocator.get_allocated_attempts("test_sorting")
```

### 3. Custom Cardinality

```python
# Define custom cardinality for domain-specific types
GraphCardinality = Exponential(
    Variable("nodes"),
    Variable("edges")
)  # nodes^edges

TreeCardinality = Product(
    Exponential(Finite(2), Variable("depth")),
    Variable("branching_factor")
)  # 2^depth × branching_factor
```

## Integration with Testing Framework

### 1. Automatic Integration

The cardinality system integrates seamlessly with existing property definitions:

```python
@context(d.int_range(0, 1000))  # Automatically infers Finite(1001)
@prop("sorting preserves elements")
def test_sort_preserves(lst: list[int]) -> bool:
    # Cardinality system optimizes attempt allocation automatically
    return sorted(lst) contains same elements
```

### 2. Reporter Integration

Budget information displayed in test output:

```
📊 Global Calibration Phase
Running 10 silent tests per property to measure execution time...

🚀 Global Execution Phase
test_sorting         [O(n)] ■■■■■■■■■■ 89 attempts  (1.2s)
test_binary_search   [O(log n)] ■■■■■■■■■■ 200 attempts (0.8s)
test_graph_coloring  [O(∞)] ■■■■■■■■■■ 1000 attempts (15.2s)

Budget: 60.0s used, 17.8s total (scaling factor: 1.0)
```

## Advanced Features

### 1. Constraint Satisfaction

Handle complex cardinality constraints:

```python
# Password cardinality with constraints
PasswordCardinality = Product(
    Finite(95),  # Printable ASCII
    Variable("length")
).constrain(
    min_uppercase=1,
    min_lowercase=1,
    min_digits=1
)  # Reduces effective cardinality
```

### 2. Cardinality Algebra

Perform algebraic operations on cardinalities:

```python
# Combine independent test spaces
total_card = card1 * card2 + card3
simplified = total_card.simplify()

# Calculate theoretical limits
secretary_limit = calculate_secretary_problem_limit(total_card)
practical_limit = calculate_optimal_attempts(total_card)
```

### 3. Export and Analysis

```python
# Export cardinality analysis
analysis = {
    "expression": str(cardinality),
    "asymptotic_class": cardinality.asymptotic_class(),
    "variables": list(cardinality.variables()),
    "secretary_limit": calculate_secretary_problem_limit(cardinality),
    "practical_attempts": calculate_optimal_attempts(cardinality)
}
```

This cardinality system represents the state-of-the-art in property-based testing optimization, providing mathematical rigor with practical efficiency for real-world testing scenarios.
