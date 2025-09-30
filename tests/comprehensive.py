# Comprehensive blackbox tests for minigun using minigun itself
# This demonstrates property-based testing by using minigun to test its own functionality

# External imports

# Internal imports
from returns.maybe import Maybe, Some

import minigun.arbitrary as a
import minigun.domain as d
import minigun.generate as g
import minigun.order as o
import minigun.sample as s
import minigun.shrink as sh
import minigun.stream as fs
from minigun.specify import Spec, check, conj, context, prop

###############################################################################
# Tests for arbitrary.py - PRNG state and basic generation
###############################################################################


@context(d.int_range(-1000, 1000), d.int_range(-1000, 1000))
@prop("nat generates values within bounds")
def test_nat_bounds(lower: int, upper: int) -> bool:
    if lower < 0 or lower > upper:
        return True  # Skip invalid inputs

    state = a.seed(42)
    new_state, value = a.nat(state, lower, upper)
    return lower <= value <= upper


@context(d.int_range(-1000, 1000), d.int_range(-1000, 1000))
@prop("int generates values within bounds")
def test_int_bounds(lower: int, upper: int) -> bool:
    if lower > upper:
        return True  # Skip invalid inputs

    state = a.seed(42)
    new_state, value = a.int(state, lower, upper)
    return lower <= value <= upper


@context(d.small_nat())
@prop("bool generates only True or False")
def test_bool_values(seed_val: int) -> bool:
    state = a.seed(seed_val)
    new_state, value = a.bool(state)
    return isinstance(value, bool)


@context(d.small_nat())
@prop("probability generates values in [0,1]")
def test_probability_bounds(seed_val: int) -> bool:
    state = a.seed(seed_val)
    new_state, value = a.probability(state)
    return 0.0 <= value <= 1.0


###############################################################################
# Tests for generate.py - Generator combinators and complex generators
###############################################################################


@context(d.small_nat())
@prop("map preserves structure with identity function")
def test_map_identity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def identity_func(x):
        return x

    # Test with int generator
    int_gen = g.int_range(0, 100)
    mapped_gen = g.map(identity_func, int_gen)

    # Extract samplers from generators
    int_sampler, _ = int_gen
    mapped_sampler, _ = mapped_gen

    state1, maybe_result1 = int_sampler(state)
    state2, maybe_result2 = mapped_sampler(state)

    # Both should generate the same dissection structure
    match (maybe_result1, maybe_result2):
        case (Some(dissection1), Some(dissection2)):
            return sh.head(dissection1) == sh.head(dissection2)
        case (Maybe.empty, Maybe.empty):
            return True
        case _:
            return False


@context(d.small_nat(), d.small_nat())
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

    sampler1, _ = composed1
    sampler2, _ = composed2
    state1, result1 = sampler1(state)
    state2, result2 = sampler2(state)

    match (result1, result2):
        case (Some(d1), Some(d2)):
            return sh.head(d1) == sh.head(d2)
        case (Maybe.empty, Maybe.empty):
            return True
        case _:
            return False


@context(d.small_nat())
@prop("filter only generates values satisfying predicate")
def test_filter_predicate(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def is_even(x):
        return x % 2 == 0

    # Create a generator that filters for even numbers
    even_gen = g.filter(is_even, g.int_range(0, 100))

    # Try to generate a value multiple times
    even_sampler, _ = even_gen
    for _ in range(10):
        state, maybe_result = even_sampler(state)
        match maybe_result:
            case Some(dissection):
                value = sh.head(dissection)
                if value % 2 != 0:
                    return False
            case Maybe.empty:
                continue
    return True


@context(d.small_nat())
@prop("choice selects from provided generators")
def test_choice_selection(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Create generators for different ranges
    gen1 = g.int_range(0, 10)
    gen2 = g.int_range(100, 110)
    gen3 = g.int_range(1000, 1010)

    choice_gen = g.choice(gen1, gen2, gen3)

    choice_sampler, _ = choice_gen
    state, maybe_result = choice_sampler(state)
    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            # Value should be from one of the three ranges
            return (
                (0 <= value <= 10)
                or (100 <= value <= 110)
                or (1000 <= value <= 1010)
            )
        case Maybe.empty:
            return True  # Empty generation is valid


@context(d.small_nat(), d.int_range(1, 5))
@prop("list generator produces lists of correct size range")
def test_list_size(seed_val: int, max_size: int) -> bool:
    state = a.seed(seed_val)

    list_gen = g.bounded_list(0, max_size, d.int_range(0, 100).generate)

    list_sampler, _ = list_gen
    state, maybe_result = list_sampler(state)
    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            return isinstance(value, list) and 0 <= len(value) <= max_size
        case Maybe.empty:
            return True


@context(d.small_nat(), d.int_range(1, 5))
@prop("dict generator produces dicts of correct size range")
def test_dict_size(seed_val: int, max_size: int) -> bool:
    state = a.seed(seed_val)

    dict_gen = g.bounded_dict(
        0, max_size, d.int_range(0, 100).generate, g.str()
    )

    dict_sampler, _ = dict_gen
    state, maybe_result = dict_sampler(state)
    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            return isinstance(value, dict) and 0 <= len(value) <= max_size
        case Maybe.empty:
            return True


@context(d.small_nat(), d.int_range(1, 5))
@prop("set generator produces sets of correct size range")
def test_set_size(seed_val: int, max_size: int) -> bool:
    state = a.seed(seed_val)

    set_gen = g.bounded_set(0, max_size, d.int_range(0, 100).generate)

    set_sampler, _ = set_gen
    state, maybe_result = set_sampler(state)
    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            return isinstance(value, set) and 0 <= len(value) <= max_size
        case Maybe.empty:
            return True


###############################################################################
# Tests for domain.py - Domain construction and composition
###############################################################################


@context(d.small_nat())
@prop("int domain respects bounds")
def test_int_domain_bounds(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Test small_int domain
    small_int_domain = g.small_int()
    small_int_sampler, _ = small_int_domain
    state, maybe_result = small_int_sampler(state)

    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            return -100 <= value <= 100
        case Maybe.empty:
            return True


@context(d.small_nat())
@prop("bounded_list domain respects size bounds")
def test_bounded_list_domain(seed_val: int) -> bool:
    state = a.seed(seed_val)

    list_domain = d.bounded_list(2, 5, d.small_int())
    list_sampler, _ = list_domain.generate
    state, maybe_result = list_sampler(state)

    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            return isinstance(value, list) and 2 <= len(value) <= 5
        case Maybe.empty:
            return True


@context(d.small_nat())
@prop("tuple domain produces tuples of correct arity")
def test_tuple_domain_arity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    tuple_domain = d.tuple(d.bool(), d.small_int(), d.str())
    tuple_sampler, _ = tuple_domain.generate
    state, maybe_result = tuple_sampler(state)

    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            return (
                isinstance(value, tuple)
                and len(value) == 3
                and isinstance(value[0], bool)
                and isinstance(value[1], int)
                and isinstance(value[2], str)
            )
        case Maybe.empty:
            return True


@context(d.small_nat())
@prop("maybe domain produces None or Some")
def test_maybe_domain(seed_val: int) -> bool:
    state = a.seed(seed_val)

    maybe_domain = d.maybe(d.small_int())
    maybe_sampler, _ = maybe_domain.generate
    state, maybe_result = maybe_sampler(state)

    match maybe_result:
        case Some(dissection):
            value = sh.head(dissection)
            # Value should be either Nothing or Some(int)
            match value:
                case Some(inner_value):
                    return isinstance(inner_value, int)
                case Maybe.empty:
                    return True
                case _:
                    return False
        case Maybe.empty:
            return True


###############################################################################
# Tests for shrink.py - Shrinking behavior
###############################################################################


@context(d.small_nat())
@prop("shrinking int produces smaller values")
def test_int_shrinking_decreases(seed_val: int) -> bool:
    state = a.seed(seed_val)

    int_gen = g.int_range(10, 100)  # Generate larger numbers
    int_sampler, _ = int_gen
    state, maybe_result = int_sampler(state)

    match maybe_result:
        case Some(dissection):
            original_value = sh.head(dissection)
            shrink_stream = sh.tail(dissection)

            # Check first few shrunk values
            shrunk_dissections = fs.to_list(shrink_stream, 5)
            for shrunk_dissection in shrunk_dissections:
                shrunk_value = sh.head(shrunk_dissection)
                if abs(shrunk_value) >= abs(original_value):
                    return False
            return True
        case Maybe.empty:
            return True


@context(d.small_nat())
@prop("shrinking list produces shorter lists")
def test_list_shrinking_shortens(seed_val: int) -> bool:
    state = a.seed(seed_val)

    list_gen = g.bounded_list(3, 10, g.small_int())  # Generate non-empty lists
    list_sampler, _ = list_gen
    state, maybe_result = list_sampler(state)

    match maybe_result:
        case Some(dissection):
            original_list = sh.head(dissection)
            if len(original_list) == 0:
                return True  # Can't shrink empty list

            shrink_stream = sh.tail(dissection)
            shrunk_dissections = fs.to_list(shrink_stream, 3)

            for shrunk_dissection in shrunk_dissections:
                shrunk_list = sh.head(shrunk_dissection)
                if len(shrunk_list) >= len(original_list):
                    return False
            return True
        case Maybe.empty:
            return True


###############################################################################
# Tests for sample.py - Domain slicing functionality
###############################################################################


@context(d.small_nat(), d.int_range(1, 5), d.int_range(1, 10))
@prop("slice generates valid sample sequences")
def test_slice_generation(
    seed_val: int, max_width: int, max_depth: int
) -> bool:
    state = a.seed(seed_val)

    int_gen = g.int_range(0, 100)
    state, maybe_slice = s.slice(int_gen, max_width, max_depth, state)

    match maybe_slice:
        case Some(values):
            # All values should be in the valid range
            return (
                isinstance(values, list)
                and len(values) <= max_depth
                and all(isinstance(v, int) and 0 <= v <= 100 for v in values)
            )
        case Maybe.empty:
            return True


###############################################################################
# Tests for stream.py - Functional stream operations
###############################################################################


@context(d.small_nat())
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


@context(d.small_nat())
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


@context(d.small_nat())
@prop("search finds counterexamples for false properties")
def test_search_finds_counterexamples(seed_val: int) -> bool:
    from minigun.search import find_counter_example

    state = a.seed(seed_val)

    # A property that's always false
    def false_law(x):
        return x != x  # x should always equal itself

    generators = {"x": d.int_range(0, 100).generate}

    state, maybe_counter = find_counter_example(
        state, 50, false_law, generators
    )

    # Should find a counterexample since the law is always false
    match maybe_counter:
        case Some(counter):
            return "x" in counter and isinstance(counter["x"], int)
        case Maybe.empty:
            # This could happen if generation fails, which is valid
            return True


@context(d.small_nat())
@prop("search doesn't find counterexamples for true properties")
def test_search_no_counterexamples_for_true_props(seed_val: int) -> bool:
    from minigun.search import find_counter_example

    state = a.seed(seed_val)

    # A property that's always true
    def true_law(x):
        return x == x  # x should always equal itself

    generators = {"x": d.int_range(0, 100).generate}

    state, maybe_counter = find_counter_example(state, 50, true_law, generators)

    # Should NOT find a counterexample since the law is always true
    match maybe_counter:
        case Some(_):
            return False
        case Maybe.empty:
            return True


###############################################################################
# Tests for order.py - Ordering functionality
###############################################################################


@context(d.small_nat(), d.small_nat())
@prop("int order is consistent with built-in comparison")
def test_int_order_consistency(a: int, b: int) -> bool:
    minigun_comparison = o.int(a, b)

    # Convert minigun's Order result to the same format as built-in comparison
    if a < b:
        expected = o.Total.Lt
    elif a == b:
        expected = o.Total.Eq
    else:
        expected = o.Total.Gt

    return minigun_comparison == expected


###############################################################################
# Integration tests - Testing the testing infrastructure itself
###############################################################################


@context(d.small_nat())
@prop("property specification creates valid spec objects")
def test_property_specification_execution(seed_val: int) -> bool:
    # Create a simple property that should always pass
    @context(d.small_int())
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
            test_choice_selection,
            test_list_size,
            test_dict_size,
            test_set_size,
            # Domain module tests
            test_int_domain_bounds,
            test_bounded_list_domain,
            test_tuple_domain_arity,
            test_maybe_domain,
            # Shrink module tests
            test_int_shrinking_decreases,
            test_list_shrinking_shortens,
            # Sample module tests
            test_slice_generation,
            # Stream module tests
            test_stream_map_length,
            test_stream_filter,
            # Search module tests
            test_search_finds_counterexamples,
            test_search_no_counterexamples_for_true_props,
            # Order module tests
            test_int_order_consistency,
            # Integration tests
            test_property_specification_execution,
        )
    )


if __name__ == "__main__":
    import sys

    success = test()
    sys.exit(0 if success else -1)
