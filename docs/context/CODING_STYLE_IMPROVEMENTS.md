# file:CODING_STYLE_IMPROVEMENTS.md

# Coding Style Conventions for Minigun

**Instructions for Coding Agents**: This document defines the mandatory coding style conventions for the Minigun codebase. When modifying or creating code in this project, you MUST follow these patterns. These are not suggestions - they are requirements for maintaining code quality and consistency.

## Core Principles

### 1. Line Length Limit (MANDATORY)
All code must stay within 80 characters per line for optimal readability and consistency.

**Rule**: Keep all lines under 80 characters. Use line breaks, parentheses, and proper indentation to maintain readability.

### 2. Early Return / Golden Path Pattern (MANDATORY)
Always prioritize the successful execution path while handling edge cases and failures early.

**Rule**: Handle failure cases first with immediate returns, keep the "golden path" unindented and clear.

### 3. Pattern Matching over isinstance() and elif chains (MANDATORY)
Use Python 3.10+ `match/case` syntax instead of sequential `elif` blocks and `isinstance()` checks.

**Rule**: When you see `isinstance()` or sequential `elif` blocks checking types or values, refactor to pattern matching.

## Required Patterns

### Pattern 1: Maybe Type Handling
**ALWAYS use this pattern for Maybe types:**

```python
# ✅ CORRECT - Use pattern matching with early returns
match maybe_value:
    case Maybe.empty:
        return early_failure_case
    case Some(value):
        # Continue with golden path
        process(value)
    case _:
        raise AssertionError("Invariant")

# ❌ WRONG - Don't use isinstance checks
if maybe_value is Nothing:
    return early_failure_case
if not isinstance(maybe_value, Some):
    raise AssertionError("Invariant")
value = maybe_value.unwrap()
```

### Pattern 2: Probability-Based Value Selection
**ALWAYS use pattern matching for probability thresholds:**

```python
# ✅ CORRECT - Clear pattern matching with guard clauses
match probability:
    case _ if probability < 0.5:
        value = small_option
    case _ if probability < 0.75:
        value = medium_option
    case _ if probability < 0.95:
        value = large_option
    case _:
        value = max_option

# ❌ WRONG - Don't use nested ternary operators
value = (
    small_option if prob < 0.5 else
    medium_option if prob < 0.75 else
    large_option if prob < 0.95 else
    max_option
)
```

### Pattern 3: Type Origin Dispatch
**ALWAYS use this pattern for type origin checking:**

```python
# ✅ CORRECT - Pattern matching with early return for None
origin = get_origin(T)
if origin is None:
    return default_case

match origin:
    case x if x is target_type1:
        return handle_type1(T)
    case x if x is target_type2:
        return handle_type2(T)
    case _:
        return default_case

# ❌ WRONG - Don't use sequential if statements
if origin is not None:
    if origin == target_type1:
        return handle_type1(T)
    if origin == target_type2:
        return handle_type2(T)
return default_case
```

### Pattern 4: Type-Specific Dispatch
**ALWAYS use pattern matching for type checking:**

```python
# ✅ CORRECT - Pattern matching for type dispatch
match value:
    case str():
        return handle_string(value)
    case int():
        return handle_integer(value)
    case _:
        return handle_other(value)

# ❌ WRONG - Don't use isinstance chains
if isinstance(value, str):
    return handle_string(value)
elif isinstance(value, int):
    return handle_integer(value)
else:
    return handle_other(value)
```

## Enforcement Rules for Coding Agents

### When to Apply These Patterns

1. **Any function with Maybe types** → Use Pattern 1
2. **Any probability-based selection logic** → Use Pattern 2
3. **Any type origin checking with get_origin()** → Use Pattern 3
4. **Any isinstance() checks** → Use Pattern 4
5. **Any sequential elif blocks** → Convert to pattern matching

### Code Review Checklist

Before submitting any code changes, verify:

- [ ] No `isinstance()` calls remain (except in test assertions)
- [ ] No sequential `elif` blocks for type/value checking
- [ ] No nested ternary operators for multi-case selection
- [ ] All Maybe types use pattern matching
- [ ] Early returns are used for failure cases
- [ ] Golden path code is unindented and clear

### Refactoring Guidelines

When you encounter old patterns:

1. **Identify the pattern type** (Maybe handling, type checking, etc.)
2. **Apply the corresponding required pattern** from above
3. **Test that behavior is preserved**
4. **Ensure early returns are used** where applicable

## Implementation Examples from Codebase

### Example 1: Generator Combinator (minigun/generate.py)

```python
# In map() and bind() functions - ALWAYS use this pattern:
for generator in generators:
    state, maybe_dissection = generator(state)
    match maybe_dissection:
        case Maybe.empty:
            return state, Nothing  # Early return for failure
        case Some(dissection):
            # Golden path continues here
            process_success_case(dissection)
        case _:
            raise AssertionError("Invariant")
```

### Example 2: Number Generators (minigun/generate.py)

```python
# In nat(), int(), big_nat(), big_int() - ALWAYS use this pattern:
state, prop = a.probability(state)
match prop:
    case _ if prop < threshold1:
        bound = value1
    case _ if prop < threshold2:
        bound = value2
    case _ if prop < threshold3:
        bound = value3
    case _:
        bound = max_value
```

### Example 3: Type Inference (minigun/pretty.py, minigun/generate.py)

```python
# In infer() functions - ALWAYS use this pattern:
origin = get_origin(T)
if origin is None:
    return Nothing  # Early return for simple case

match origin:
    case x if x is _tuple:
        return _case_tuple(T)
    case x if x is _list:
        return _case_list(T)
    case x if x is _dict:
        return _case_dict(T)
    case x if x is _set:
        return _case_set(T)
    case _:
        return Nothing
```

## Benefits for Coding Agents

Following these patterns ensures:

1. **Consistency** - All similar code uses the same approach
2. **Readability** - Code intent is immediately clear
3. **Maintainability** - Easy to extend and modify
4. **Modern Python** - Leverages latest language features
5. **Performance** - More efficient than alternative approaches

## Error Prevention

**Common mistakes to avoid:**

- Don't mix old and new patterns in the same function
- Don't use `maybe_value.unwrap()` when pattern matching is available
- Don't create deeply nested conditionals when early returns are possible
- Don't use `isinstance()` when pattern matching can handle the dispatch

## Testing Requirements

All pattern changes must:
- Preserve existing test behavior
- Not introduce performance regressions
- Maintain type safety
- Pass all 82 existing tests

## Conclusion for Coding Agents

These patterns are **mandatory** for all code in the Minigun project. When you encounter code that doesn't follow these patterns, refactor it. When you write new code, use these patterns from the start. This ensures the codebase remains consistent, modern, and maintainable.

**Remember**: These are not optional style suggestions - they are required coding standards for this project.
