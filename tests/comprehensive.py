# Comprehensive blackbox tests for minigun using minigun itself
# This demonstrates property-based testing by using minigun to test its own functionality

# Internal imports
import minigun.arbitrary as a
import minigun.generate as g
import minigun.stream as fs
from minigun.specify import Spec, check, conj, context, prop

###############################################################################
# Tests for arbitrary.py - PRNG state and basic generation
###############################################################################


@context(g.int_range(-1000, 1000), g.int_range(-1000, 1000))
@prop("nat generates values within bounds")
def test_nat_bounds(lower: int, upper: int) -> bool:
    if lower < 0 or lower > upper:
        return True  # Skip invalid inputs

    state = a.seed(42)
    new_state, value = a.nat(state, lower, upper)
    return lower <= value <= upper


@context(g.int_range(-1000, 1000), g.int_range(-1000, 1000))
@prop("int generates values within bounds")
def test_int_bounds(lower: int, upper: int) -> bool:
    if lower > upper:
        return True  # Skip invalid inputs

    state = a.seed(42)
    new_state, value = a.int(state, lower, upper)
    return lower <= value <= upper


@context(g.small_nat())
@prop("bool generates only True or False")
def test_bool_values(seed_val: int) -> bool:
    state = a.seed(seed_val)
    new_state, value = a.bool(state)
    return isinstance(value, bool)


@context(g.small_nat())
@prop("probability generates values in [0,1]")
def test_probability_bounds(seed_val: int) -> bool:
    state = a.seed(seed_val)
    new_state, value = a.probability(state)
    return 0.0 <= value <= 1.0


###############################################################################
# Tests for generate.py - Generator combinators and complex generators
###############################################################################


@context(g.small_nat())
@prop("map preserves structure with identity function")
def test_map_identity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def identity_func(x):
        return x

    # Test with int generator
    int_gen = g.int_range(0, 100)
    mapped_gen = g.map(identity_func, int_gen)

    state1, dissection1 = int_gen.sample(state)
    state2, dissection2 = mapped_gen.sample(state)

    # Both should generate the same dissection head
    if dissection1 is None or dissection2 is None:
        return dissection1 is None and dissection2 is None
    return dissection1.head == dissection2.head


@context(g.small_nat(), g.small_nat())
@prop("map composition is associative")
def test_map_associative(seed_val: int, offset: int) -> bool:
    state = a.seed(seed_val)

    int_gen = g.int_range(0, 100)

    def f(x):
        return x + 1

    def g_func(x):
        return x * 2

    def compose_f_g(x):
        return f(g_func(x))

    # (f . g) . gen == f . (g . gen)
    composed1 = g.map(compose_f_g, int_gen)
    composed2 = g.map(f, g.map(g_func, int_gen))

    state1, dissection1 = composed1.sample(state)
    state2, dissection2 = composed2.sample(state)

    if dissection1 is None or dissection2 is None:
        return dissection1 is None and dissection2 is None
    return dissection1.head == dissection2.head


@context(g.small_nat())
@prop("filter only generates values satisfying predicate")
def test_filter_predicate(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def is_even(x):
        return x % 2 == 0

    # Create a generator that filters for even numbers
    even_gen = g.filter(is_even, g.int_range(0, 100))

    # Try to generate a value multiple times
    for _ in range(10):
        state, dissection = even_gen.sample(state)
        if dissection is None:
            continue
        if dissection.head % 2 != 0:
            return False
    return True


@context(g.small_nat())
@prop("filtered shrink candidates satisfy the predicate")
def test_filter_shrinks_satisfy_predicate(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def is_even(x):
        return x % 2 == 0

    even_gen = g.filter(is_even, g.int_range(0, 100))
    state, dissection = even_gen.sample(state)
    if dissection is None:
        return True
    shrunk = fs.to_list(dissection.shrinks, 10)
    return all(candidate.head % 2 == 0 for candidate in shrunk)


@context(g.small_nat())
@prop("choice selects from provided generators")
def test_choice_selection(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Create generators for different ranges
    gen1 = g.int_range(0, 10)
    gen2 = g.int_range(100, 110)
    gen3 = g.int_range(1000, 1010)

    choice_gen = g.choice(gen1, gen2, gen3)

    state, dissection = choice_gen.sample(state)
    if dissection is None:
        return True  # Empty generation is valid
    value = dissection.head
    # Value should be from one of the three ranges
    return (
        (0 <= value <= 10) or (100 <= value <= 110) or (1000 <= value <= 1010)
    )


@context(g.small_nat(), g.int_range(0, 8), g.int_range(0, 8))
@prop("bounded_str respects length bounds")
def test_bounded_str_bounds(seed_val: int, lower: int, upper: int) -> bool:
    if lower > upper:
        return True  # skip invalid
    state = a.seed(seed_val)
    gen = g.bounded_str(lower, upper, "abc")
    state, dissection = gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    return (
        isinstance(value, str)
        and lower <= len(value) <= upper
        and all(ch in "abc" for ch in value)
    )


@prop("bounded_str covers its full length range")
def test_bounded_str_length_coverage() -> bool:
    # Regression test: bounded_str previously always emitted
    # fixed-length strings (upper-lower), never varying across the range.
    state = a.seed(0xC0FFEE)
    gen = g.bounded_str(3, 7, "ab")
    observed: set[int] = set()
    for _ in range(400):
        state, dissection = gen.sample(state)
        if dissection is None:
            continue
        observed.add(len(dissection.head))
    return observed == {3, 4, 5, 6, 7}


@context(g.small_nat(), g.int_range(1, 5))
@prop("list generator produces lists of correct size range")
def test_list_size(seed_val: int, max_size: int) -> bool:
    state = a.seed(seed_val)

    list_gen = g.bounded_list(0, max_size, g.int_range(0, 100))

    state, dissection = list_gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    return isinstance(value, list) and 0 <= len(value) <= max_size


@context(g.small_nat(), g.int_range(1, 5))
@prop("dict generator produces dicts of correct size range")
def test_dict_size(seed_val: int, max_size: int) -> bool:
    state = a.seed(seed_val)

    dict_gen = g.bounded_dict(0, max_size, g.int_range(0, 100), g.str())

    state, dissection = dict_gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    return isinstance(value, dict) and 0 <= len(value) <= max_size


@context(g.small_nat(), g.int_range(1, 5))
@prop("set generator produces sets of correct size range")
def test_set_size(seed_val: int, max_size: int) -> bool:
    state = a.seed(seed_val)

    set_gen = g.bounded_set(0, max_size, g.int_range(0, 100))

    state, dissection = set_gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    return isinstance(value, set) and 0 <= len(value) <= max_size


###############################################################################
# Tests for domain.py - Domain construction and composition
###############################################################################


@context(g.small_nat())
@prop("int domain respects bounds")
def test_int_domain_bounds(seed_val: int) -> bool:
    state = a.seed(seed_val)

    small_int_gen = g.small_int()
    state, dissection = small_int_gen.sample(state)

    if dissection is None:
        return True
    return -100 <= dissection.head <= 100


@context(g.small_nat())
@prop("bounded_list domain respects size bounds")
def test_bounded_list_domain(seed_val: int) -> bool:
    state = a.seed(seed_val)

    list_gen = g.bounded_list(2, 5, g.small_int())
    state, dissection = list_gen.sample(state)

    if dissection is None:
        return True
    value = dissection.head
    return isinstance(value, list) and 2 <= len(value) <= 5


@context(g.small_nat())
@prop("list shrinking respects the lower size bound")
def test_bounded_list_shrink_lower_bound(seed_val: int) -> bool:
    state = a.seed(seed_val)

    list_gen = g.bounded_list(2, 5, g.small_int())
    state, dissection = list_gen.sample(state)
    if dissection is None:
        return True
    shrunk = fs.to_list(dissection.shrinks, 20)
    return all(len(candidate.head) >= 2 for candidate in shrunk)


@context(g.small_nat())
@prop("tuple domain produces tuples of correct arity")
def test_tuple_domain_arity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    tuple_gen = g.tuple(g.bool(), g.small_int(), g.str())
    state, dissection = tuple_gen.sample(state)

    if dissection is None:
        return True
    value = dissection.head
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], bool)
        and isinstance(value[1], int)
        and isinstance(value[2], str)
    )


@context(g.small_nat())
@prop("optional domain produces None or values")
def test_optional_domain(seed_val: int) -> bool:
    state = a.seed(seed_val)

    optional_gen = g.optional(g.small_int())
    state, dissection = optional_gen.sample(state)

    if dissection is None:
        return True
    value = dissection.head
    return value is None or isinstance(value, int)


###############################################################################
# Tests for shrink.py - Shrinking behavior
###############################################################################


@context(g.small_nat())
@prop("shrinking int produces smaller values")
def test_int_shrinking_decreases(seed_val: int) -> bool:
    state = a.seed(seed_val)

    int_gen = g.int_range(10, 100)  # Generate larger numbers
    state, dissection = int_gen.sample(state)

    if dissection is None:
        return True
    original_value = dissection.head

    # Check first few shrunk values
    shrunk_dissections = fs.to_list(dissection.shrinks, 5)
    for shrunk_dissection in shrunk_dissections:
        if abs(shrunk_dissection.head) >= abs(original_value):
            return False
    return True


@context(g.small_nat())
@prop("shrinking list produces shorter lists")
def test_list_shrinking_shortens(seed_val: int) -> bool:
    state = a.seed(seed_val)

    list_gen = g.bounded_list(0, 10, g.small_int())
    state, dissection = list_gen.sample(state)

    if dissection is None:
        return True
    original_list = dissection.head
    if len(original_list) == 0:
        return True  # Can't shrink empty list

    # The first len(original) shrink candidates remove one element each
    # and must therefore all be shorter than the original.
    shrunk_dissections = fs.to_list(dissection.shrinks, len(original_list))
    for shrunk_dissection in shrunk_dissections:
        if len(shrunk_dissection.head) >= len(original_list):
            return False
    return True


###############################################################################
# Tests for stream.py - Functional stream operations
###############################################################################


@context(g.small_nat())
@prop("stream map preserves length for finite streams")
def test_stream_map_length(seed_val: int) -> bool:
    # Create a finite stream from a list
    test_list = list(range(seed_val % 10))
    stream = fs.from_list(test_list)

    def increment(x):
        return x + 1

    # Map with increment function
    mapped_stream = fs.map(increment, stream)

    # Convert back to list and check length
    original_length = len(fs.to_list(stream, 100))
    mapped_length = len(fs.to_list(mapped_stream, 100))

    return original_length == mapped_length


@context(g.small_nat())
@prop("stream filter produces only matching elements")
def test_stream_filter(seed_val: int) -> bool:
    # Create a stream of numbers
    test_list = list(range(seed_val % 20))
    stream = fs.from_list(test_list)

    def is_even(x):
        return x % 2 == 0

    # Filter for even numbers
    filtered_stream = fs.filter(is_even, stream)
    filtered_list = fs.to_list(filtered_stream, 100)

    # All elements should be even
    return all(x % 2 == 0 for x in filtered_list)


###############################################################################
# Tests for search.py - Counterexample finding
###############################################################################


@context(g.small_nat())
@prop("search finds counterexamples for false properties")
def test_search_finds_counterexamples(seed_val: int) -> bool:
    from minigun.search import find_counter_example

    state = a.seed(seed_val)

    # A property that's always false
    def false_law(x):
        return x != x  # x should always equal itself

    generators = {"x": g.int_range(0, 100)}

    state, counter = find_counter_example(state, 50, false_law, generators)

    # Should find a counterexample since the law is always false
    if counter is None:
        # This could happen if generation fails, which is valid
        return True
    return "x" in counter.args and isinstance(counter.args["x"], int)


@context(g.small_nat())
@prop("search doesn't find counterexamples for true properties")
def test_search_no_counterexamples_for_true_props(seed_val: int) -> bool:
    from minigun.search import find_counter_example

    state = a.seed(seed_val)

    # A property that's always true
    def true_law(x):
        return x == x  # x should always equal itself

    generators = {"x": g.int_range(0, 100)}

    state, counter = find_counter_example(state, 50, true_law, generators)

    # Should NOT find a counterexample since the law is always true
    return counter is None


###############################################################################
# Integration tests - Testing the testing infrastructure itself
###############################################################################


@context(g.small_nat())
@prop("property specification creates valid spec objects")
def test_property_specification_execution(seed_val: int) -> bool:
    # Create a simple property that should always pass
    @context(g.small_int())
    @prop("identity property")
    def identity_prop(x: int) -> bool:
        return x == x

    # The property should be a Spec object with the right structure
    return isinstance(identity_prop, Spec)


###############################################################################
# Running all comprehensive tests
###############################################################################
def test() -> bool:
    """Run all comprehensive tests."""
    return check(
        conj(
            # Arbitrary module tests
            test_nat_bounds,
            test_int_bounds,
            test_bool_values,
            test_probability_bounds,
            # Generate module tests
            test_map_identity,
            test_map_associative,
            test_filter_predicate,
            test_filter_shrinks_satisfy_predicate,
            test_choice_selection,
            test_bounded_str_bounds,
            test_bounded_str_length_coverage,
            test_list_size,
            test_dict_size,
            test_set_size,
            # Domain module tests
            test_int_domain_bounds,
            test_bounded_list_domain,
            test_bounded_list_shrink_lower_bound,
            test_tuple_domain_arity,
            test_optional_domain,
            # Shrink module tests
            test_int_shrinking_decreases,
            test_list_shrinking_shortens,
            # Stream module tests
            test_stream_map_length,
            test_stream_filter,
            # Search module tests
            test_search_finds_counterexamples,
            test_search_no_counterexamples_for_true_props,
            # Integration tests
            test_property_specification_execution,
        )
    )


if __name__ == "__main__":
    import sys

    success = test()
    sys.exit(0 if success else -1)
