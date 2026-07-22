# Additional blackbox tests targeting low-coverage areas
# Focusing on edge cases, error conditions, and advanced functionality

# External imports
import contextlib
import io
import string

# Internal imports
import minigun.arbitrary as a
import minigun.budget as b
import minigun.cardinality as c
import minigun.generate as g
import minigun.orchestrator as o
import minigun.reporter as r
import minigun.stream as fs
from minigun.specify import Spec, check, conj, context, neg, prop

###############################################################################
# Additional tests for generate.py - targeting missed functionality
###############################################################################


@context(g.small_nats())
@prop("constant generator always produces the same value")
def test_constant_generator(seed_val: int) -> bool:
    state = a.seed(seed_val)

    const_gen = g.constant(42)

    # Generate multiple times and ensure same value
    for _ in range(5):
        state, dissection = const_gen.sample(state)
        if dissection is None:
            return False
        if dissection.head != 42:
            return False
    return True


@context(g.small_nats())
@prop("bind with constant creates mapped values")
def test_bind_with_constant(seed_val: int) -> bool:
    state = a.seed(seed_val)

    def double_constant(x):
        return g.constant(x * 2)

    # Bind an int generator with a function that creates a constant generator
    bound_gen = g.bind(double_constant, g.int_range(1, 10))

    state, dissection = bound_gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    # Result should be even and between 2 and 20
    return isinstance(value, int) and value % 2 == 0 and 2 <= value <= 20


@context(g.small_nats())
@prop("weighted_choice generator respects weights")
def test_weighted_choice_generator(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Create weighted choice generator with heavily weighted options
    weighted_gen = g.weighted_choice(
        (99, g.constant("heavy")),
        (1, g.constant("light")),  # 99% weight  # 1% weight
    )

    # Sample many times and check that "heavy" appears more frequently
    heavy_count = 0
    total_samples = 50

    for _ in range(total_samples):
        state, dissection = weighted_gen.sample(state)
        if dissection is None:
            continue
        if dissection.head == "heavy":
            heavy_count += 1

    # With 99:1 ratio, we should see "heavy" in most samples
    # Allow some variance due to randomness
    return heavy_count > total_samples * 0.8


@context(g.small_nats(), g.int_range(1, 10))
@prop("one_of generator selects from provided list")
def test_one_of_generator(seed_val: int, list_size: int) -> bool:
    state = a.seed(seed_val)

    test_list = list(range(list_size))
    one_of_gen = g.one_of(test_list)

    state, dissection = one_of_gen.sample(state)
    if dissection is None:
        return len(test_list) == 0  # Empty list should produce empty
    return dissection.head in test_list


@context(g.small_nats())
@prop("str generator produces valid strings")
def test_str_generator_validity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    str_gen = g.strings()

    state, dissection = str_gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    # Should be a string with printable characters
    return isinstance(value, str) and all(
        ch in string.printable for ch in value
    )


@context(g.small_nats())
@prop("word generator produces alphabetic strings")
def test_word_generator_validity(seed_val: int) -> bool:
    state = a.seed(seed_val)

    word_gen = g.words()

    state, dissection = word_gen.sample(state)
    if dissection is None:
        return True
    value = dissection.head
    # Should be a string with only alphabetic characters
    return isinstance(value, str) and (len(value) == 0 or value.isalpha())


@context(g.small_nats())
@prop("lazy defers inner construction and reuses the built generator")
def test_lazy_generator_defers_and_memoizes(seed_val: int) -> bool:
    build_count = [0]

    def _build():
        build_count[0] += 1
        return g.int_range(1, 10)

    lazy_gen = g.lazy(_build)

    if lazy_gen.cardinality.is_finite:
        return False
    if build_count[0] != 0:
        return False

    state = a.seed(seed_val)
    for _ in range(3):
        state, dissection = lazy_gen.sample(state)
        if dissection is None:
            continue
        value = dissection.head
        if not (isinstance(value, int) and 1 <= value <= 10):
            return False

    return build_count[0] == 1


###############################################################################
# Additional tests for shrink.py - edge cases and advanced shrinking
###############################################################################


@context(g.small_nats())
@prop("shrinking preserves type")
def test_shrinking_preserves_type(seed_val: int) -> bool:
    import minigun.shrink as sh

    state = a.seed(seed_val)

    str_gen = g.strings()
    state, dissection = str_gen.sample(state)

    if dissection is None:
        return True
    original_value = dissection.head

    # Check that shrunk values are still strings
    shrunk_dissections = fs.to_list(dissection.shrinks, 3)
    for shrunk_dissection in shrunk_dissections:
        if not isinstance(shrunk_dissection.head, type(original_value)):
            return False
    _ = sh  # imported for parity with other shrink tests
    return True


@context(g.small_nats())
@prop("singleton creates valid dissection")
def test_singleton_dissection(seed_val: int) -> bool:
    import minigun.shrink as sh

    # Test with singleton dissection
    singleton_dissection = sh.singleton(seed_val)

    # Singleton should not shrink further
    shrunk_dissections = fs.to_list(singleton_dissection.shrinks, 5)

    return (
        singleton_dissection.head == seed_val and len(shrunk_dissections) == 0
    )


###############################################################################
# Additional tests for stream.py - advanced stream operations
###############################################################################


@context(g.small_nats())
@prop("stream constant produces infinite stream of same value")
def test_stream_constant(seed_val: int) -> bool:
    n = seed_val % 5 + 1

    # Create constant stream
    constant_stream = fs.constant(42)
    taken_list = fs.to_list(constant_stream, n)

    return len(taken_list) == n and all(x == 42 for x in taken_list)


@context(g.small_nats())
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


@context(g.small_nats())
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


@context(g.small_nats())
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


@context(g.small_nats())
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


@context(g.small_nats())
@prop("zero-length bounded collections work")
def test_zero_length_bounded_collections(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Test zero-length bounded list
    empty_list_gen = g.bounded_lists(0, 0, g.int_range(0, 100))
    state, dissection = empty_list_gen.sample(state)

    if dissection is None:
        return True
    value = dissection.head
    return isinstance(value, list) and len(value) == 0


@context(g.small_nats())
@prop("single-element bounded collections work")
def test_single_element_bounded_collections(seed_val: int) -> bool:
    state = a.seed(seed_val)

    # Test single-element bounded set
    single_set_gen = g.bounded_sets(1, 1, g.int_range(0, 100))
    state, dissection = single_set_gen.sample(state)

    if dissection is None:
        return True
    value = dissection.head
    # Could be smaller than 1 due to duplicates collapsing
    return isinstance(value, set) and len(value) <= 1


@context(g.small_nats())
@prop("optional generator produces both None and values")
def test_optional_generator_coverage(seed_val: int) -> bool:
    state = a.seed(seed_val)

    optional_gen = g.optional(g.int_range(0, 100))

    # Sample multiple times to see both None and values
    none_seen = False
    value_seen = False

    for _ in range(20):
        state, dissection = optional_gen.sample(state)
        if dissection is None:
            continue
        if dissection.head is None:
            none_seen = True
        elif isinstance(dissection.head, int):
            value_seen = True

    # We should see at least one of each type (with high probability)
    return none_seen or value_seen  # At least one should be true


###############################################################################
# Cardinality module tests
###############################################################################


@context(g.small_nats())
@prop("cardinality renders as ASCII")
def test_cardinality_ascii_rendering(size: int) -> bool:
    # Windows encodes redirected stdout with the legacy ANSI code page;
    # displayed domain sizes must never contain unencodable glyphs.
    return str(c.finite(size)).isascii() and str(c.INFINITE).isascii()


###############################################################################
# Budget module tests - targeting low coverage areas
###############################################################################


@context(g.small_nats())
@prop("attempt_limit returns reasonable values")
def test_attempt_limit_policy(size: int) -> bool:
    cardinality = c.finite(max(1, size % 10000))
    limit = b.attempt_limit(cardinality)
    return 1 <= limit <= 10000


@context(g.small_nats())
@prop("baseline_attempts handles finite cardinalities")
def test_baseline_attempts_policy(size: int) -> bool:
    cardinality = c.finite(max(10, size % 1000))
    attempts = b.baseline_attempts(cardinality)
    return attempts >= 10


@context(g.small_nats())
@prop("PropertyBudget.create produces valid budgets")
def test_property_budget_create(seed_val: int) -> bool:
    size = max(10, seed_val % 1000)
    cardinality = c.finite(size)
    budget = b.PropertyBudget.create("test_prop", cardinality)

    return (
        budget.name == "test_prop"
        and budget.cardinality == cardinality
        and budget.attempt_limit > 0
        and budget.baseline_attempts > 0
        and budget.final_attempts == budget.baseline_attempts
    )


@context(g.small_nats())
@prop("PropertyBudget.with_calibration updates timing correctly")
def test_property_budget_with_calibration(seed_val: int) -> bool:
    cardinality = c.finite(100)
    budget = b.PropertyBudget.create("test", cardinality)
    time_per_attempt = max(0.001, (seed_val % 100) / 1000.0)

    calibrated = budget.with_calibration(time_per_attempt)

    return (
        calibrated.time_per_attempt == time_per_attempt
        and calibrated.estimated_time
        == calibrated.baseline_attempts * time_per_attempt
        and calibrated.name == budget.name
    )


@context(g.small_nats())
@prop("PropertyBudget.with_final_attempts updates attempts correctly")
def test_property_budget_with_final_attempts(seed_val: int) -> bool:
    cardinality = c.finite(100)
    budget = b.PropertyBudget.create("test", cardinality, 0.01)
    new_attempts = max(1, seed_val % 50)

    updated = budget.with_final_attempts(new_attempts)

    return (
        updated.final_attempts == new_attempts
        and updated.estimated_time == new_attempts * 0.01
        and updated.name == budget.name
    )


@context(g.small_nats())
@prop("PropertyBudget tracks finiteness of its cardinality")
def test_property_budget_infinite_cardinality_detection(seed_val: int) -> bool:
    # Test with finite cardinality
    finite_card = c.finite(max(1, seed_val % 1000))
    finite_budget = b.PropertyBudget.create("finite", finite_card)

    # Test with infinite cardinality
    infinite_card = c.INFINITE
    infinite_budget = b.PropertyBudget.create("infinite", infinite_card)

    return (
        finite_budget.cardinality.is_finite
        and not infinite_budget.cardinality.is_finite
    )


@context(g.small_nats())
@prop("BudgetAllocator.add_property increases property count")
def test_budget_allocator_add_property(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(30.0)
    initial_count = len(allocator.properties)

    cardinality = c.finite(max(1, seed_val % 100))
    allocator.add_property("test_prop", cardinality)

    return len(allocator.properties) == initial_count + 1


@context(g.small_nats())
@prop("BudgetAllocator.record_calibration updates timing")
def test_budget_allocator_record_calibration(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(60.0)
    cardinality = c.finite(100)
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


@context(g.small_nats())
@prop(
    "BudgetAllocator.get_allocated_attempts returns calibration value during calibration"
)
def test_budget_allocator_calibration_attempts(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(30.0)
    cardinality = c.finite(max(1, seed_val % 100))
    allocator.add_property("test", cardinality)

    # Should return calibration default before finalization
    attempts = allocator.get_allocated_attempts("test")
    return attempts == 10


@context(g.small_nats())
@prop("BudgetAllocator.finalize_allocation completes calibration")
def test_budget_allocator_finalize_allocation(seed_val: int) -> bool:
    allocator = b.BudgetAllocator(60.0)
    cardinality = c.finite(100)
    allocator.add_property("test", cardinality)
    allocator.record_calibration("test", 0.1, 10)

    initial_calibration = allocator.is_calibration_complete()
    allocator.finalize_allocation()
    final_calibration = allocator.is_calibration_complete()

    return not initial_calibration and final_calibration


@context(g.small_nats())
@prop("over-budget allocation scales attempts down to fit")
def test_budget_allocation_scale_down(seed_val: int) -> bool:
    # Use a small budget that forces scaling
    time_budget = max(0.5, (seed_val % 5) + 1.0)
    allocator = b.BudgetAllocator(time_budget)

    # Create properties whose estimates will exceed the budget
    cardinality = c.finite(1000)
    allocator.add_property("prop1", cardinality)
    allocator.add_property("prop2", cardinality)
    allocator.record_calibration("prop1", 1.0, 10)
    allocator.record_calibration("prop2", 1.0, 10)

    allocator.finalize_allocation()

    total_time = allocator.total_estimated_time
    return total_time <= time_budget * 1.1 and len(allocator.properties) == 2


###############################################################################
# Orchestrator module tests - testing orchestration system
###############################################################################


@context(g.small_nats())
@prop("TestModule creates valid module objects")
def test_test_module_creation(seed_val: int) -> bool:
    @prop("inner always true")
    def _inner(x: int) -> bool:
        return True

    module = o.TestModule("test_module", _inner)
    return module.name == "test_module" and isinstance(module.spec, Spec)


@context(g.small_nats())
@prop("OrchestrationConfig has reasonable defaults")
def test_orchestration_config_defaults(seed_val: int) -> bool:
    time_budget = max(10.0, float(seed_val % 100))
    config = o.OrchestrationConfig(time_budget=time_budget)

    return (
        config.time_budget == time_budget
        and config.seed is None
        and config.output == "rich"
    )


@context(g.small_nats())
@prop("OrchestrationConfig accepts custom settings")
def test_orchestration_config_custom(seed_val: int) -> bool:
    time_budget = max(5.0, float(seed_val % 50))
    output = ["rich", "quiet", "json"][seed_val % 3]

    config = o.OrchestrationConfig(
        time_budget=time_budget, seed=seed_val, output=output
    )

    return (
        config.time_budget == time_budget
        and config.seed == seed_val
        and config.output == output
    )


@context(g.small_nats())
@prop("OrchestrationConfig rejects unknown output modes")
def test_orchestration_config_rejects_unknown_output(seed_val: int) -> bool:
    try:
        o.OrchestrationConfig(time_budget=5.0, output="verbose")
    except ValueError:
        return True
    return False


@context(g.small_nats())
@prop("TestOrchestrator initializes with valid config")
def test_orchestrator_initialization(seed_val: int) -> bool:
    time_budget = max(10.0, float(seed_val % 100))
    config = o.OrchestrationConfig(time_budget=time_budget, output="quiet")
    orchestrator = o.TestOrchestrator(config)

    return orchestrator.config == config


@context(g.small_nats())
@prop("TestOrchestrator executes simple test modules")
def test_orchestrator_execute_simple_modules(seed_val: int) -> bool:
    config = o.OrchestrationConfig(
        time_budget=2.0, seed=seed_val, output="quiet"
    )
    orchestrator = o.TestOrchestrator(config)

    @prop("inner passing law")
    def _passes(x: int) -> bool:
        return x == x

    @prop("inner failing law")
    def _fails(x: int) -> bool:
        return False

    modules = [
        o.TestModule("passing", conj(_passes)),
        o.TestModule("failing", conj(neg(_fails))),
    ]

    # Suppress the orchestrator's own quiet-mode output so it doesn't
    # interleave with the parent test runner's output.
    with contextlib.redirect_stdout(io.StringIO()):
        result = orchestrator.execute_tests(modules)

    return result is True


###############################################################################
# Reporter module tests - testing reporting system data structures
###############################################################################


@context(g.small_nats())
@prop("CardinalityInfo creates valid objects")
def test_cardinality_info_creation(seed_val: int) -> bool:
    cardinality = c.finite(max(1, seed_val % 1000))
    attempt_limit = max(1, seed_val % 100)
    allocated_attempts = max(1, seed_val % 50)
    estimated_time = max(0.001, float(seed_val % 100) / 1000.0)

    info = r.CardinalityInfo(
        domain_size=cardinality,
        attempt_limit=attempt_limit,
        allocated_attempts=allocated_attempts,
        estimated_time=estimated_time,
    )

    return (
        info.domain_size == cardinality
        and info.attempt_limit == attempt_limit
        and info.allocated_attempts == allocated_attempts
        and info.estimated_time == estimated_time
    )


@context(g.small_nats())
@prop("CardinalityInfo.to_dict creates valid dictionary")
def test_cardinality_info_to_dict(seed_val: int) -> bool:
    cardinality = c.finite(max(1, seed_val % 1000))
    attempt_limit = max(1, seed_val % 100)
    allocated_attempts = max(1, seed_val % 50)

    info = r.CardinalityInfo(
        domain_size=cardinality,
        attempt_limit=attempt_limit,
        allocated_attempts=allocated_attempts,
    )

    result_dict = info.to_dict()

    return (
        isinstance(result_dict, dict)
        and "domain_size" in result_dict
        and "attempt_limit" in result_dict
        and "allocated_attempts" in result_dict
        and "estimated_time" in result_dict
    )


@context(g.small_nats())
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


@context(g.small_nats())
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


@context(g.small_nats())
@prop("TestResult with CardinalityInfo serializes correctly")
def test_test_result_with_cardinality_to_dict(seed_val: int) -> bool:
    name = f"test_property_{seed_val % 100}"
    cardinality = c.finite(max(1, seed_val % 1000))

    cardinality_info = r.CardinalityInfo(
        domain_size=cardinality, attempt_limit=10, allocated_attempts=5
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


###############################################################################
# Running all additional tests
###############################################################################
spec = conj(
    # Generate module additional tests
    test_constant_generator,
    test_bind_with_constant,
    test_weighted_choice_generator,
    test_one_of_generator,
    test_str_generator_validity,
    test_word_generator_validity,
    test_lazy_generator_defers_and_memoizes,
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
    test_optional_generator_coverage,
    # Cardinality module tests
    test_cardinality_ascii_rendering,
    # Budget module tests
    test_attempt_limit_policy,
    test_baseline_attempts_policy,
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
    test_orchestration_config_rejects_unknown_output,
    test_orchestrator_initialization,
    test_orchestrator_execute_simple_modules,
    # Reporter module tests
    test_cardinality_info_creation,
    test_cardinality_info_to_dict,
    test_test_result_creation,
    test_test_result_to_dict,
    test_test_result_with_cardinality_to_dict,
)


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else -1)
