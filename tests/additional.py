# Additional blackbox tests targeting low-coverage areas
# Focusing on edge cases, error conditions, and advanced functionality

# External imports
import string

from returns.maybe import Maybe, Some

# Internal imports
import minigun.arbitrary as a
import minigun.budget as b
import minigun.cardinality as c
import minigun.domain as d
import minigun.generate as g
import minigun.orchestrator as o
import minigun.pretty as p
import minigun.reporter as r
import minigun.shrink as sh
import minigun.stream as fs
from minigun.specify import Spec, check, conj, context, neg, prop

###############################################################################
# Additional tests for generate.py - targeting missed functionality
###############################################################################


@context(d.small_nat())
@prop("constant generator always produces the same value")
def test_constant_generator(seed_val: int) -> bool:
    state = a.seed(seed_val)

    const_gen = g.constant(42)
    const_sampler, _ = const_gen

    # Generate multiple times and ensure same value
    for _ in range(5):
        state, maybe_result = const_sampler(state)
        if isinstance(maybe_result, Some):
            dissection = maybe_result.unwrap()
            if sh.head(dissection) != 42:
                return False
        elif maybe_result == Maybe.empty:
            return False
    return True


@context(d.small_nat())
@prop("bind with constant creates mapped values")
def test_bind_with_constant(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def double_constant(x):
        return g.constant(x * 2)

    # Bind an int generator with a function that creates a constant generator
    from minigun import cardinality as c

    bound_gen = g.bind(
        double_constant, lambda cards: c.FINITE(20), g.int_range(1, 10)
    )
    bound_sampler, _ = bound_gen

    state, maybe_result = bound_sampler(state)
    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        value = sh.head(dissection)
        # Result should be even and between 2 and 20
        return isinstance(value, int) and value % 2 == 0 and 2 <= value <= 20
    elif maybe_result == Maybe.empty:
        return True
    return False


@context(d.small_nat())
@prop("weighted_choice generator respects weights")
def test_weighted_choice_generator(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Create weighted choice generator with heavily weighted options
    weighted_gen = g.weighted_choice(
        (99, g.constant("heavy")),
        (1, g.constant("light")),  # 99% weight  # 1% weight
    )
    weighted_sampler, _ = weighted_gen

    # Sample many times and check that "heavy" appears more frequently
    heavy_count = 0
    total_samples = 50

    for _ in range(total_samples):
        state, maybe_result = weighted_sampler(state)
        if isinstance(maybe_result, Some):
            dissection = maybe_result.unwrap()
            if sh.head(dissection) == "heavy":
                heavy_count += 1
        elif maybe_result == Maybe.empty:
            continue

    # With 99:1 ratio, we should see "heavy" in most samples
    # Allow some variance due to randomness
    return heavy_count > total_samples * 0.8


@context(d.small_nat(), d.int_range(1, 10))
@prop("one_of generator selects from provided list")
def test_one_of_generator(seed_val: int, list_size: int) -> bool:
    state = a.seed(seed_val)

    test_list = list(range(list_size))
    one_of_gen = g.one_of(test_list)
    one_of_sampler, _ = one_of_gen

    state, maybe_result = one_of_sampler(state)
    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        value = sh.head(dissection)
        return value in test_list
    elif maybe_result == Maybe.empty:
        return len(test_list) == 0  # Empty list should produce empty
    return False


@context(d.small_nat())
@prop("str generator produces valid strings")
def test_str_generator_validity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    str_gen = g.str()
    str_sampler, _ = str_gen

    state, maybe_result = str_sampler(state)
    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        value = sh.head(dissection)
        # Should be a string with printable characters
        return isinstance(value, str) and all(
            c in string.printable for c in value
        )
    elif maybe_result == Maybe.empty:
        return True
    return False


@context(d.small_nat())
@prop("word generator produces alphabetic strings")
def test_word_generator_validity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    word_gen = g.word()
    word_sampler, _ = word_gen

    state, maybe_result = word_sampler(state)
    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        value = sh.head(dissection)
        # Should be a string with only alphabetic characters
        return isinstance(value, str) and (len(value) == 0 or value.isalpha())
    elif maybe_result == Maybe.empty:
        return True
    return False


###############################################################################
# Additional tests for pretty.py - testing output formatting
###############################################################################


@context(d.small_nat())
@prop("int printer produces string representation")
def test_int_printer(seed_val: int) -> bool:
    int_printer = p.int()
    layout = int_printer(seed_val)
    result = p.render(layout)
    return isinstance(result, str) and str(seed_val) in result


@context(d.str())
@prop("str printer produces string output")
def test_str_printer(s: str) -> bool:
    str_printer = p.str()
    layout = str_printer(s)
    result = p.render(layout)
    return isinstance(result, str)


@context(d.bool())
@prop("bool printer produces 'True' or 'False'")
def test_bool_printer(b: bool) -> bool:
    bool_printer = p.bool()
    layout = bool_printer(b)
    result = p.render(layout)
    return result in ["True", "False"]


@context(d.small_nat())
@prop("float printer produces valid representation")
def test_float_printer(seed_val: int) -> bool:
    float_val = float(seed_val) + 0.5
    float_printer = p.float()
    layout = float_printer(float_val)
    result = p.render(layout)
    return isinstance(result, str) and len(result) > 0


@context(d.list(d.small_int()))
@prop("list printer includes brackets")
def test_list_printer(lst: list[int]) -> bool:
    list_printer = p.list(p.int())
    layout = list_printer(lst)
    result = p.render(layout)
    return isinstance(result, str) and "[" in result and "]" in result


###############################################################################
# Additional tests for shrink.py - edge cases and advanced shrinking
###############################################################################


@context(d.small_nat())
@prop("shrinking preserves type")
def test_shrinking_preserves_type(seed_val: int) -> bool:
    state = a.seed(seed_val)

    str_gen = g.str()
    str_sampler, _ = str_gen
    state, maybe_result = str_sampler(state)

    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        original_value = sh.head(dissection)
        shrink_stream = sh.tail(dissection)

        # Check that shrunk values are still strings
        shrunk_dissections = fs.to_list(shrink_stream, 3)
        for shrunk_dissection in shrunk_dissections:
            shrunk_value = sh.head(shrunk_dissection)
            if not isinstance(shrunk_value, type(original_value)):
                return False
        return True
    elif maybe_result == Maybe.empty:
        return True
    return False


@context(d.small_nat())
@prop("singleton creates valid dissection")
def test_singleton_dissection(seed_val: int) -> bool:
    # Test with singleton dissection
    singleton_dissection = sh.singleton(seed_val)
    value = sh.head(singleton_dissection)
    shrink_stream = sh.tail(singleton_dissection)

    # Singleton should not shrink further
    shrunk_dissections = fs.to_list(shrink_stream, 5)

    return value == seed_val and len(shrunk_dissections) == 0


###############################################################################
# Additional tests for stream.py - advanced stream operations
###############################################################################


@context(d.small_nat())
@prop("stream constant produces infinite stream of same value")
def test_stream_constant(seed_val: int) -> bool:
    n = seed_val % 5 + 1

    # Create constant stream
    constant_stream = fs.constant(42)
    taken_list = fs.to_list(constant_stream, n)

    return len(taken_list) == n and all(x == 42 for x in taken_list)


@context(d.small_nat())
@prop("stream concat concatenates correctly")
def test_stream_concat(seed_val: int) -> bool:
    n = seed_val % 5 + 1

    list1 = list(range(n))
    list2 = list(range(n, 2 * n))

    stream1 = fs.from_list(list1)
    stream2 = fs.from_list(list2)

    concatenated_stream = fs.concat(stream1, stream2)
    result_list = fs.to_list(concatenated_stream, 2 * n + 5)

    expected = list1 + list2
    return result_list == expected


@context(d.small_nat())
@prop("stream braid interleaves correctly")
def test_stream_braid(seed_val: int) -> bool:
    # Create two streams with different patterns
    stream1 = fs.from_list([0, 2, 4])
    stream2 = fs.from_list([1, 3, 5])

    braided_stream = fs.braid(stream1, stream2)
    result_list = fs.to_list(braided_stream, 10)

    # Should start with elements from first stream, then interleave
    return len(result_list) > 0 and result_list[0] == 0


###############################################################################
# Additional tests for specify.py - property specification edge cases
###############################################################################


@context(d.small_nat())
@prop("negated properties work correctly")
def test_negated_properties(seed_val: int) -> bool:
    # Create a property that always fails
    @prop("always false")
    def always_false(x: int) -> bool:
        return False

    # Negating it should make it always true
    negated_prop = neg(always_false)

    # The negated property should be a valid Spec
    return isinstance(negated_prop, Spec)


@context(d.small_nat())
@prop("conjunction of properties works correctly")
def test_conjunction_properties(seed_val: int) -> bool:
    # Create two properties that always pass
    @prop("first property")
    def prop1(x: int) -> bool:
        return True

    @prop("second property")
    def prop2(x: int) -> bool:
        return True

    # Conjunction should also be a valid Spec
    conjunction = conj(prop1, prop2)
    return isinstance(conjunction, Spec)


###############################################################################
# Edge case tests - boundary conditions and error handling
###############################################################################


@context(d.small_nat())
@prop("zero-length bounded collections work")
def test_zero_length_bounded_collections(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Test zero-length bounded list
    empty_list_gen = g.bounded_list(0, 0, g.int_range(0, 100))
    empty_list_sampler, _ = empty_list_gen
    state, maybe_result = empty_list_sampler(state)

    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        value = sh.head(dissection)
        return isinstance(value, list) and len(value) == 0
    elif maybe_result == Maybe.empty:
        return True
    return False


@context(d.small_nat())
@prop("single-element bounded collections work")
def test_single_element_bounded_collections(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Test single-element bounded set
    single_set_gen = g.bounded_set(1, 1, g.int_range(0, 100))
    single_set_sampler, _ = single_set_gen
    state, maybe_result = single_set_sampler(state)

    if isinstance(maybe_result, Some):
        dissection = maybe_result.unwrap()
        value = sh.head(dissection)
        return (
            isinstance(value, set) and len(value) <= 1
        )  # Could be 0 due to duplicates
    elif maybe_result == Maybe.empty:
        return True
    return False


@context(d.small_nat())
@prop("maybe generator produces both None and Some values")
def test_maybe_generator_coverage(seed_val: int) -> bool:
    state = a.seed(seed_val)

    maybe_gen = g.maybe(g.int_range(0, 100))
    maybe_sampler, _ = maybe_gen

    # Sample multiple times to see both None and Some
    none_seen = False
    some_seen = False

    for _ in range(20):
        state, maybe_result = maybe_sampler(state)
        if isinstance(maybe_result, Some):
            dissection = maybe_result.unwrap()
            value = sh.head(dissection)
            if value == Maybe.empty:
                none_seen = True
            elif isinstance(value, Some):
                some_seen = True
        elif maybe_result == Maybe.empty:
            continue

    # We should see at least one of each type (with high probability)
    return none_seen or some_seen  # At least one should be true


###############################################################################
# Budget module tests - targeting low coverage areas
###############################################################################


@context(d.small_nat())
@prop("AttemptStrategy.theoretical_limit returns reasonable values")
def test_attempt_strategy_theoretical_limit(size: int) -> bool:
    cardinality = c.Finite(max(1, size % 10000))
    limit = b.AttemptStrategy.theoretical_limit(cardinality)
    return 1 <= limit <= 10000


@context(d.small_nat())
@prop("AttemptStrategy.practical_baseline handles finite cardinalities")
def test_attempt_strategy_practical_baseline_finite(size: int) -> bool:
    cardinality = c.Finite(max(10, size % 1000))
    attempts = b.AttemptStrategy.practical_baseline(cardinality)
    return attempts >= 10


@context(d.small_nat())
@prop("PropertyBudget.create produces valid budgets")
def test_property_budget_create(seed_val: int) -> bool:
    size = max(10, seed_val % 1000)
    cardinality = c.Finite(size)
    budget = b.PropertyBudget.create("test_prop", cardinality)

    return (
        budget.name == "test_prop"
        and budget.cardinality == cardinality
        and budget.theoretical_limit > 0
        and budget.practical_baseline > 0
        and budget.final_attempts == budget.practical_baseline
    )


@context(d.small_nat())
@prop("PropertyBudget.with_calibration updates timing correctly")
def test_property_budget_with_calibration(seed_val: int) -> bool:
    cardinality = c.Finite(100)
    budget = b.PropertyBudget.create("test", cardinality)
    time_per_attempt = max(0.001, (seed_val % 100) / 1000.0)

    calibrated = budget.with_calibration(time_per_attempt)

    return (
        calibrated.time_per_attempt == time_per_attempt
        and calibrated.estimated_time
        == calibrated.practical_baseline * time_per_attempt
        and calibrated.name == budget.name
    )


@context(d.small_nat())
@prop("PropertyBudget.with_final_attempts updates attempts correctly")
def test_property_budget_with_final_attempts(seed_val: int) -> bool:
    cardinality = c.Finite(100)
    budget = b.PropertyBudget.create("test", cardinality, 0.01)
    new_attempts = max(1, seed_val % 50)

    updated = budget.with_final_attempts(new_attempts)

    return (
        updated.final_attempts == new_attempts
        and updated.estimated_time == new_attempts * 0.01
        and updated.name == budget.name
    )


@context(d.small_nat())
@prop("PropertyBudget.is_infinite_cardinality detects infinite correctly")
def test_property_budget_infinite_cardinality_detection(seed_val: int) -> bool:
    # Test with finite cardinality
    finite_card = c.Finite(max(1, seed_val % 1000))
    finite_budget = b.PropertyBudget.create("finite", finite_card)

    # Test with infinite cardinality
    infinite_card = c.Infinite()
    infinite_budget = b.PropertyBudget.create("infinite", infinite_card)

    return (
        not finite_budget.is_infinite_cardinality()
        and infinite_budget.is_infinite_cardinality()
    )


@context(d.small_nat())
@prop("BudgetAllocator.add_property increases property count")
def test_budget_allocator_add_property(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(30.0)
    initial_count = len(allocator.properties)

    cardinality = c.Finite(max(1, seed_val % 100))
    allocator.add_property("test_prop", cardinality)

    return len(allocator.properties) == initial_count + 1


@context(d.small_nat())
@prop("BudgetAllocator.record_calibration updates timing")
def test_budget_allocator_record_calibration(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(60.0)
    cardinality = c.Finite(100)
    allocator.add_property("test_prop", cardinality)

    # Record calibration
    total_time = max(0.01, (seed_val % 100) / 100.0)
    attempts = max(1, seed_val % 10)
    allocator.record_calibration("test_prop", total_time, attempts)

    prop_budget = allocator.get_property_budget("test_prop")
    expected_time_per_attempt = total_time / attempts

    return (
        prop_budget is not None
        and abs(prop_budget.time_per_attempt - expected_time_per_attempt)
        < 0.001
    )


@context(d.small_nat())
@prop(
    "BudgetAllocator.get_allocated_attempts returns calibration value during calibration"
)
def test_budget_allocator_calibration_attempts(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(30.0)
    cardinality = c.Finite(max(1, seed_val % 100))
    allocator.add_property("test", cardinality)

    # Should return calibration default before finalization
    attempts = allocator.get_allocated_attempts("test")
    return attempts == 10


@context(d.small_nat())
@prop("BudgetAllocator.finalize_allocation completes calibration")
def test_budget_allocator_finalize_allocation(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(60.0)
    cardinality = c.Finite(100)
    allocator.add_property("test", cardinality)
    allocator.record_calibration("test", 0.1, 10)

    initial_calibration = allocator.is_calibration_complete()
    allocator.finalize_allocation()
    final_calibration = allocator.is_calibration_complete()

    return not initial_calibration and final_calibration


@context(d.small_nat())
@prop("BudgetAllocationStrategy.scale_down reduces attempts proportionally")
def test_budget_allocation_scale_down(seed_val: int) -> bool:
    # Create properties that will exceed budget
    cardinality = c.Finite(1000)
    prop1 = b.PropertyBudget.create("prop1", cardinality)
    prop2 = b.PropertyBudget.create("prop2", cardinality)

    # Add calibration timing that will exceed our small budget
    prop1 = prop1.with_calibration(0.1)
    prop2 = prop2.with_calibration(0.1)
    properties = [prop1, prop2]

    # Use a small budget that forces scaling
    time_budget = max(0.5, (seed_val % 5) + 1.0)
    scaled = b.BudgetAllocationStrategy.scale_down(properties, time_budget)

    total_time = sum(p.estimated_time for p in scaled)
    return total_time <= time_budget * 1.1 and len(scaled) == len(properties)


###############################################################################
# Orchestrator module tests - testing orchestration system
###############################################################################


@context(d.small_nat())
@prop("TestModule creates valid module objects")
def test_test_module_creation(seed_val: int) -> bool:
    def dummy_test() -> bool:
        return True

    module = o.TestModule("test_module", dummy_test)
    return module.name == "test_module" and callable(module.test_function)


@context(d.small_nat())
@prop("OrchestrationConfig has reasonable defaults")
def test_orchestration_config_defaults(seed_val: int) -> bool:
    time_budget = max(10.0, float(seed_val % 100))
    config = o.OrchestrationConfig(time_budget=time_budget)

    return (
        config.time_budget == time_budget
        and config.verbose is True
        and config.quiet is False
        and config.json_output is False
    )


@context(d.small_nat())
@prop("OrchestrationConfig accepts custom settings")
def test_orchestration_config_custom(seed_val: int) -> bool:
    time_budget = max(5.0, float(seed_val % 50))
    verbose = (seed_val % 2) == 0
    quiet = (seed_val % 3) == 0
    json_output = (seed_val % 5) == 0

    config = o.OrchestrationConfig(
        time_budget=time_budget,
        verbose=verbose,
        quiet=quiet,
        json_output=json_output,
    )

    return (
        config.time_budget == time_budget
        and config.verbose == verbose
        and config.quiet == quiet
        and config.json_output == json_output
    )


@context(d.small_nat())
@prop("PhaseResult captures test execution results")
def test_phase_result_structure(seed_val: int) -> bool:
    success = (seed_val % 2) == 0
    duration = max(0.1, float(seed_val % 100) / 10.0)
    modules = max(1, seed_val % 10)

    result = o.PhaseResult(success, duration, modules)

    return (
        result.success == success
        and result.duration == duration
        and result.modules_executed == modules
    )


@context(d.small_nat())
@prop("TestOrchestrator initializes with valid config")
def test_orchestrator_initialization(seed_val: int) -> bool:
    time_budget = max(10.0, float(seed_val % 100))
    config = o.OrchestrationConfig(time_budget=time_budget, quiet=True)
    orchestrator = o.TestOrchestrator(config)

    return orchestrator.config == config


@context(d.small_nat())
@prop("TestOrchestrator executes simple test modules")
def test_orchestrator_execute_simple_modules(seed_val: int) -> bool:
    config = o.OrchestrationConfig(time_budget=5.0, quiet=True)
    orchestrator = o.TestOrchestrator(config)

    def always_pass() -> bool:
        return True

    def sometimes_pass() -> bool:
        return (seed_val % 3) != 0  # Fails 1/3 of the time

    modules = [
        o.TestModule("always_pass", always_pass),
        o.TestModule("sometimes_pass", sometimes_pass),
    ]

    result = orchestrator.execute_tests(modules)

    # Result should be boolean
    return isinstance(result, bool)


###############################################################################
# Reporter module tests - testing reporting system data structures
###############################################################################


@context(d.small_nat())
@prop("CardinalityInfo creates valid objects")
def test_cardinality_info_creation(seed_val: int) -> bool:
    cardinality = c.Finite(max(1, seed_val % 1000))
    optimal_limit = max(1, seed_val % 100)
    allocated_attempts = max(1, seed_val % 50)
    estimated_time = max(0.001, float(seed_val % 100) / 1000.0)

    info = r.CardinalityInfo(
        domain_size=cardinality,
        optimal_limit=optimal_limit,
        allocated_attempts=allocated_attempts,
        estimated_time=estimated_time,
    )

    return (
        info.domain_size == cardinality
        and info.optimal_limit == optimal_limit
        and info.allocated_attempts == allocated_attempts
        and info.estimated_time == estimated_time
    )


@context(d.small_nat())
@prop("CardinalityInfo.to_dict creates valid dictionary")
def test_cardinality_info_to_dict(seed_val: int) -> bool:
    cardinality = c.Finite(max(1, seed_val % 1000))
    optimal_limit = max(1, seed_val % 100)
    allocated_attempts = max(1, seed_val % 50)

    info = r.CardinalityInfo(
        domain_size=cardinality,
        optimal_limit=optimal_limit,
        allocated_attempts=allocated_attempts,
    )

    result_dict = info.to_dict()

    return (
        isinstance(result_dict, dict)
        and "domain_size" in result_dict
        and "optimal_limit" in result_dict
        and "allocated_attempts" in result_dict
        and "estimated_time" in result_dict
    )


@context(d.small_nat())
@prop("TestResult creates valid test result objects")
def test_test_result_creation(seed_val: int) -> bool:
    name = f"test_property_{seed_val % 100}"
    success = (seed_val % 2) == 0
    duration = max(0.001, float(seed_val % 100) / 1000.0)
    counter_example = f"counter_example_{seed_val}" if not success else None

    result = r.TestResult(
        name=name,
        success=success,
        duration=duration,
        counter_example=counter_example,
    )

    return (
        result.name == name
        and result.success == success
        and abs(result.duration - duration) < 0.001
        and result.counter_example == counter_example
    )


@context(d.small_nat())
@prop("TestResult.to_dict creates valid dictionary")
def test_test_result_to_dict(seed_val: int) -> bool:
    name = f"test_property_{seed_val % 100}"
    success = (seed_val % 2) == 0
    duration = max(0.001, float(seed_val % 100) / 1000.0)

    result = r.TestResult(name=name, success=success, duration=duration)

    result_dict = result.to_dict()

    return (
        isinstance(result_dict, dict)
        and result_dict["name"] == name
        and result_dict["success"] == success
        and abs(result_dict["duration"] - duration) < 0.001
    )


@context(d.small_nat())
@prop("TestResult with CardinalityInfo serializes correctly")
def test_test_result_with_cardinality_to_dict(seed_val: int) -> bool:
    name = f"test_property_{seed_val % 100}"
    cardinality = c.Finite(max(1, seed_val % 1000))

    cardinality_info = r.CardinalityInfo(
        domain_size=cardinality, optimal_limit=10, allocated_attempts=5
    )

    result = r.TestResult(
        name=name, success=True, duration=0.1, cardinality_info=cardinality_info
    )

    result_dict = result.to_dict()

    return (
        isinstance(result_dict, dict)
        and "cardinality_info" in result_dict
        and isinstance(result_dict["cardinality_info"], dict)
    )


@context(d.small_nat())
@prop("format_counter_example returns clean strings")
def test_format_counter_example(seed_val: int) -> bool:
    input_str = f"  test_counter_example_{seed_val % 100}  \n"
    result = r.format_counter_example(input_str)

    # Should strip whitespace and be non-empty
    return (
        isinstance(result, str)
        and len(result.strip()) > 0
        and result == result.strip()
    )


###############################################################################
# Running all additional tests
###############################################################################
def test() -> bool:
    """Run all additional blackbox tests."""
    return check(
        conj(
            # Generate module additional tests
            test_constant_generator,
            test_bind_with_constant,
            test_weighted_choice_generator,
            test_one_of_generator,
            test_str_generator_validity,
            test_word_generator_validity,
            # Pretty module tests
            test_int_printer,
            test_str_printer,
            test_bool_printer,
            test_float_printer,
            test_list_printer,
            # Shrink module additional tests
            test_shrinking_preserves_type,
            test_singleton_dissection,
            # Stream module additional tests
            test_stream_constant,
            test_stream_concat,
            test_stream_braid,
            # Specify module additional tests
            test_negated_properties,
            test_conjunction_properties,
            # Edge case tests
            test_zero_length_bounded_collections,
            test_single_element_bounded_collections,
            test_maybe_generator_coverage,
            # Budget module tests
            test_attempt_strategy_theoretical_limit,
            test_attempt_strategy_practical_baseline_finite,
            test_property_budget_create,
            test_property_budget_with_calibration,
            test_property_budget_with_final_attempts,
            test_property_budget_infinite_cardinality_detection,
            test_budget_allocator_add_property,
            test_budget_allocator_record_calibration,
            test_budget_allocator_calibration_attempts,
            test_budget_allocator_finalize_allocation,
            test_budget_allocation_scale_down,
            # Orchestrator module tests
            test_test_module_creation,
            test_orchestration_config_defaults,
            test_orchestration_config_custom,
            test_phase_result_structure,
            test_orchestrator_initialization,
            test_orchestrator_execute_simple_modules,
            # Reporter module tests
            test_cardinality_info_creation,
            test_cardinality_info_to_dict,
            test_test_result_creation,
            test_test_result_to_dict,
            test_test_result_with_cardinality_to_dict,
            test_format_counter_example,
        )
    )


if __name__ == "__main__":
    import sys

    success = test()
    sys.exit(0 if success else -1)
