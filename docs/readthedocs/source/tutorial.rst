Tutorial
========
This tutorial covers property-based testing techniques and how to apply them with Minigun.

For motivation on why you should use a QuickCheck-like system for testing, we recommend watching the following videos:

- `Computerphile ft. John Hughes - Code Checking Automation <https://www.youtube.com/watch?v=AfaNEebCDos>`_
- `John Hughes - Testing the Hard Stuff and Staying Sane <https://www.youtube.com/watch?v=zi0rHwfiX1Q>`_
- `John Hughes - Certifying your car with Erlang <https://vimeo.com/68331689>`_

.. note::

    If you wish to learn more about the subject beyond this tutorial, we recommend Jan Midtgaard's `lecture materials <https://janmidtgaard.dk/quickcheck/index.html>`_. It is OCaml based but translates easily to other QuickCheck-like libraries for other languages, such as Minigun.

Installation
------------
Minigun is currently only supported for Python >=3.12, although it might work with older versions. It is distributed via PyPI and can be installed with the following command:

.. code-block:: shell

    $ python3 -m pip install minigun-soren-n

Introduction
------------
First an overview of the concept and history of property-based testing and QuickCheck.

Why do we want to test software?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
At first software testing might seem paradoxical: what is the implementation of a program, if not an expression of the intended functionality? Why should we write additional code to express the intended functionality? It seems like a duplicate effort.

From the perspective of a programmer, the discipline of testing and verification forces us to abstract away the functionality of software from its implementation details. That is, there might be many possible implementations of a piece of software, but there should only be one definition of its functionality.

When authoring production code we care about more than the bare minimum of providing the intended functionality; we also care about performance and other runtime characteristics. These additional properties add complexity to our codebases, which during development *will* be at odds with functionality. Testing pins down functionality regardless of how it is optimized or what implementation details are used, such that we can focus our efforts on the engineering of said implementation details without losing functionality.

Additionally, having a testing strategy improves the maintainability of our projects long term; making it possible to make large changes to the codebase without loss of functionality: confidently upgrading dependencies, large scale refactoring and rewrites, sometimes even migrating to another language or platform. It encodes the semantics of our projects; *what* they are supposed to do, in contrast to *how* they do it. It becomes part of the documentation of our projects, making it possible for programmers to come and go, without leaving knowledge gaps.

The problems with unit-testing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Traditionally we do software testing by writing unit-tests by hand. Since it is not tractable to test all input-output cases of a program (neither to write nor to evaluate them), we instead break these cases into classes based on some definition of similarity. We then find representatives within these classes to write tests for, in the hope that if a test passes for a representative, then the other cases in its class would pass as well. Notice that this assumption relies on implementations being well-behaved with regards to these classes; i.e. that the evaluation of any test case in a given class, would traverse similar or the same code paths.

This leads us to the first problem with hand written unit-tests; an arbitrary implementation of an interface would most likely not be well-behaved in this way. As such, a representative passing testing does not give us much confidence; i.e. hand written unit-tests give a very shallow level of testing.

The second problem with hand written unit-tests is that they become a ball and chain around the interfaces of the programs we are developing; it makes it difficult to refactor them (which we would often need to do during development) because we need to rewrite a lot of unit-tests whenever we do. This incentivizes us to either try to define good interfaces and tests prior to implementation, a.k.a. waterfall, or to wait with testing altogether until we are much further with the development, again not agile.

Property-based testing is the solution
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The solution to the first problem is to realize that the aforementioned test case classes simply *are* the properties that our specifications are composed of, and that the representatives should be automatically and randomly selected rather than hand picked as a fixed set. This is property-based testing in a nutshell.

Ideally we should formally verify our software against the specification rather than test it; e.g. in Coq or some other proof assistant, however this is still quite time consuming, and as such is still mostly reserved for critical or foundational systems. It also requires a different skillset from what most programmers have, and often further, programmers are not even aware this is a possibility.

Property-based testing serves as a practical approximation towards what we do in formal verification. The random selection of test cases means, that with each evaluation of our testing strategy, we grow more confident in our implementation as more cases are shown to be covered.

Regarding the second problem, property-based testing does not definitively solve it; in general it is not solvable, we can not avoid having to write *some* testing code. But property-based testing does alleviate the second problem, since we do end up writing *much less* testing code; as such refactoring it or entirely scrapping it is less painful.

QuickCheck
^^^^^^^^^^
QuickCheck is a library and REPL for property-based testing. The initial design and the first implementation was authored in `Haskell <https://github.com/nick8325/quickcheck>`_ by `Koen Claessen <https://www.cse.chalmers.se/~koen/>`_ and `John Hughes <https://www.cse.chalmers.se/~rjmh/>`_ at Chalmers University, with initial release in 1999.

Implementations of QuickCheck-like libraries are now available for all major and mainstream `programming languages <https://en.wikipedia.org/wiki/QuickCheck>`_.

.. note::

    Some implementations allow you to test interfaces in different languages than the language the QuickCheck library was implemented in; watch the presentations linked to earlier, where C interfaces were tested in Erlang.

QuickCheck implements utility for working with the following three concepts:

:Generation:
    The library provides implementations of random instance generators for the built-in types of the target language; such as integers, floats, strings and combinators for collection types such as list; as well as utility and combinators for users to define custom domains.

:Shrinking:
    Since a randomly generated input instance can be quite large, and it is only a small or specific part of the input that is causing the failure, we work with the concept of shrinking. The failing input instance is iteratively shrunk or trimmed, until a smallest possible failing instance is found. Again, the library provides implementations for shrinkers of the built-in types of the target language; as well as utility and combinators for user defined shrinkers.

:Printing:
    Once a smallest failing input instance is found, we wish to be able to print it out in a user friendly way. For this the library provides pretty printers for built-in types of the target languages; as well as utility and combinators for user defined pretty printers.

These three concepts put together is usually called a strategy; in Minigun it is called a :code:`Domain[A]`, and the generation and shrinking is joined under one type of :code:`Generator[A]`.

Basic usage
-----------
Lets start with a simple example where we define a law for an interface interaction between list concatenation, list length and integer addition. Then we will define a brief executable section, that when evaluated will check the implementation of the referenced interfaces, against the specification that we defined.

.. code-block:: python

    from minigun.specify import prop, context, check
    import minigun.domain as d

    @context(d.list(d.int()), d.list(d.int()))
    @prop('Length distributes over concatenation via addition')
    def _list_len_concat_add_dist(xs: list[int], ys: list[int]):
        return len(xs + ys) == len(xs) + len(ys)

    if __name__ == '__main__':
        import sys
        success = check(_list_len_concat_add_dist)
        sys.exit(0 if success else -1)

Declared at the top are the imports to the relevant dependencies of Minigun. When defining basic specifications, you should not need any other imports than those listed.

Next a law is defined with the name :code:`_list_len_concat_add_dist`. It is decorated with a specification header of :code:`@prop` and :code:`@context`; neither of which can be omitted when defining a specification (except for simple cases, see the following tip in this section).

The :code:`@context` decorator will quantify the domain of the law; here positionally giving the parameters :code:`xs` and :code:`ys` the type :code:`list[int]` via :code:`d.list(d.int())`.

The :code:`@prop` decorator defines a human readable description for the specification, and in turn converts the law into a property.

At last there is the executable section, where the implementation is checked against the specification.

.. tip::
    Parameter domains can also be quantified by name, e.g:

    .. code-block:: python

        @context(
            xs = d.list(d.int()),
            ys = d.list(d.int())
        )

    And in the usual mixed positional and named Pythonic way, e.g:

    .. code-block:: python

        @context(
            d.list(d.int()),
            ys = d.list(d.int())
        )

.. tip::

    For simple and general domains such as lists of integers, Minigun is actually able to infer the domain from the typehints annotated for the law's parameters. As such it is not necessary to fully write out the domain if you are quantifying over basic Python types. The following specification would have been valid as well:

    .. code-block:: python

        @prop('Length distributes over concatenation via addition')
        def _list_len_concat_add_dist(xs: list[int], ys: list[int]):
            return len(xs + ys) == len(xs) + len(ys)

Running tests
^^^^^^^^^^^^^
Save the example above as :code:`test_list.py` and run it directly:

.. code-block:: shell

    $ python3 test_list.py

Minigun also ships with a CLI test runner that discovers and runs test modules with a time budget. If you have a :code:`tests/` directory with test modules, you can run:

.. code-block:: shell

    $ minigun --time-budget 30

This will discover all test modules, run a calibration phase to measure execution time per property, then allocate attempts proportionally within the time budget. The output looks something like:

.. code-block:: text

    Test Summary
    ╭──────────┬───────┬────────┬────────┬──────────┬─────────╮
    │ Module   │ Tests │ Passed │ Failed │ Duration │ Status  │
    ├──────────┼───────┼────────┼────────┼──────────┼─────────┤
    │ positive │  34   │   34   │   0    │  7.698s  │ PASS    │
    ├──────────┼───────┼────────┼────────┼──────────┼─────────┤
    │ TOTAL    │  34   │   34   │   0    │ 12.816s  │ PASS    │
    ╰──────────┴───────┴────────┴────────┴──────────┴─────────╯

See :code:`minigun --help` for all available options, including :code:`--modules` to select specific test modules, :code:`--quiet` for CI output, and :code:`--json` for structured output.

Composing specifications
------------------------
A specification in Minigun's environment is represented as an instance of :code:`Spec`. You have seen one constructor for :code:`Spec`, namely the decorator :code:`minigun.specify.prop`, but there are other constructors.

``minigun.specify.conj``
    For a check of a conjunction to succeed, checks of all of its terms must succeed.

``minigun.specify.neg``
    For a check of a negation to succeed, the check of its term must fail.

A simple example of how to use :code:`conj`, is to extend our example from earlier with an additional specification:

.. code-block:: python

    from minigun.specify import prop, conj, check
    import minigun.domain as d

    @prop('Length distributes over concatenation via addition')
    def _list_len_concat_add_dist(xs: list[int], ys: list[int]):
        return len(xs + ys) == len(xs) + len(ys)

    @prop('Reverse distributes over concatenation')
    def _list_rev_concat_dist(xs: list[int], ys: list[int]):
        return (
            list(reversed(xs + ys)) ==
            list(reversed(ys)) + list(reversed(xs))
        )

    if __name__ == '__main__':
        import sys
        success = check(conj(
            _list_len_concat_add_dist,
            _list_rev_concat_dist
        ))
        sys.exit(0 if success else -1)

Notice that we are testing the conjunction of the two specifications.

Template specifications
-----------------------
We might wish to capture certain concepts as specifications, and repurpose them by instantiating them for different implementations. For example we could wish to define specifications for queues, stacks or some network protocol, or more abstractly for concepts such as monoids or abelian groups.

To do this with Minigun you can use the technique of template specifications (we could also call it parameterized or higher-kinded specifications). Python supports this naturally via functions, so we can template (or parameterize) our specifications as we otherwise would.

.. code-block:: python

    from typing import TypeVar, Callable
    from minigun.specify import prop, context, check
    import minigun.domain as d

    S = TypeVar('S')
    A = TypeVar('A')
    def _stack(
        item_domain: d.Domain[A],
        stack_domain: d.Domain[S],
        initial: S,
        length: Callable[[S], int],
        push: Callable[[S, A], S],
        pop: Callable[[S], tuple[A, S]]
        ):

        @context(d.constant(initial))
        @prop('Initial stack is empty')
        def _initial_empty(s: S):
            return length(s) == 0

        @context(stack_domain, item_domain)
        @prop('Stack push increments size')
        def _push_inc(s: S, a: A):
            return length(push(s, a)) == length(s) + 1

        @context(stack_domain)
        @prop('Stack pop decrements size')
        def _pop_dec(s: S):
            if length(s) == 0: return True
            _, s1 = pop(s)
            return length(s) - 1 == length(s1)

        @context(stack_domain, item_domain)
        @prop('Stack push and pop are inverse')
        def _push_pop_inv(s: S, a: A):
            b, t = pop(push(s, a))
            return a == b and s == t

        return conj(
            _initial_empty,
            _push_inc,
            _pop_dec,
            _push_pop_inv
        )

    # An implementation of an immutable stack of integers
    def _push(xs: list[A], x: A) -> list[A]:
        xs1 = xs.copy()
        xs1.append(x)
        return xs1

    def _pop(xs: list[A]) -> tuple[A, list[A]]:
        xs1 = xs.copy()
        x = xs1.pop(-1)
        return x, xs1

    # A specification for the above implementation
    _stack_int = _stack(
        d.int(), d.list(d.int()),
        [], len, _push, _pop
    )

    if __name__ == '__main__':
        import sys
        success = check(_stack_int)
        sys.exit(0 if success else -1)

What we are saying here is that :code:`[]`, :code:`len`, :code:`_push` and :code:`_pop` together implements the specification of :code:`_stack`, a relationship which is represented by :code:`_stack_int`. We can then run :code:`check` to test if the implementation adheres to the specification of :code:`_stack` (at least for the unit test cases generated during that given run).

The above example is a naive and shallow specification for immutable stacks; it does not capture more complex interactions with the stack interface; and therefore does not challenge the implementation very deeply. A more complete specification would be to model programs over the stack interface; i.e. arbitrary sequences of applications of :code:`push` and :code:`pop`.

.. note::
    For Python implementations you generally do not need to go any deeper that the above example does (in practice). It is mostly for lower level languages where you have to deal with concepts such as under- and over flows, and generally have more administrative implementation details to get right regarding resource management. But if you want to be more complete in your specifications, and want to go deeper, please checkout the section about Modeling.

Refining domains
----------------
Often the input domains to interfaces are not as general as their types suggests. Therefore to make useful and concise specifications we need to be able to define these more refined domains.

Map
^^^
As our first example, lets consider domains for even and odd natural numbers, both of which are subsets of the Python type :code:`int`.

.. code-block:: python

    import minigun.domain as d
    import minigun.generate as g
    import minigun.pretty as p

    def even_natural() -> d.Domain[int]:
        def _impl(i: int) -> int:
            return i * 2
        return d.Domain(
            g.map(_impl, g.nat()),
            p.int()
        )

    def odd_natural() -> d.Domain[int]:
        def _impl(i: int) -> int:
            return ((i + 1) * 2) - 1
        return d.Domain(
            g.map(_impl, g.nat()),
            p.int()
        )

Here we :code:`map` over the natural numbers, and use them as indices into the sets of even and odd natural numbers.

To use our new domains, we instantiate them the same as we would other domains defined in :code:`minigun.domain`:

.. code-block:: python

    @context(even_natural())
    @prop('Even natural numbers are even')
    def _even_is_even(n: int):
        return n % 2 == 0

    @context(odd_natural())
    @prop('Odd natural numbers are odd')
    def _odd_is_odd(n: int):
        return n % 2 == 1

Bind
^^^^
As another example, lets consider representing directed graphs using the type :code:`Dict[int, List[int]]`. Each node in the graph is represented with an index, and the edges are represented with a map from indices to lists of indices.

If we were to simply define the domain with the following direct translation of the type:

.. code-block:: python

    @context(d.dict(d.int(), d.list(d.int())))

We would end up generating and testing with instances of dictionaries that do not represent valid directed graphs.

To generate valid instances we need to define a refined domain:

.. code-block:: python

    from minigun.specify import permanent_path
    import minigun.generate as g
    import matplotlib.pyplot as plt
    import networkx as nx
    import typeset as ts

    def graph_printer(data: Dict[int, List[int]]) -> ts.Layout:
        graph = nx.Graph()
        graph.add_nodes_from(data.keys())
        for src, edges in data.items():
            graph.add_edges_from([ (src, dst) for dst in edges ])
        artifact_path = permanent_path().with_suffix('.png')
        nx.draw(graph, with_labels = True, font_weight = 'bold')
        plt.savefig(artifact_path)
        return ts.text(str(artifact_path))

    def sized_directed_graph(size: int) -> d.Domain[Dict[int, List[int]]]:
        def _impl(
            graph_data: List[List[bool]]
            ) -> Dict[int, List[int]]:
            result: Dict[int, List[int]] = {}
            for src_index, row_data in enumerate(graph_data):
                result[src_index] = []
                for dst_index, column_data in enumerate(row_data):
                    if not column_data: continue
                    result[src_index].append(dst_index)
            return result

        return d.Domain(
            g.map(_impl, g.bounded_list(
                size, size,
                g.bounded_list(
                    size, size,
                    g.bool()
                )
            )),
            graph_printer
        )

    def directed_graph() -> d.Domain[Dict[int, List[int]]]:
        return d.bind(sized_directed_graph, d.small_nat())

Here we define two domains over directed graphs. The first generates directed graphs of a given size, the second is defined using :code:`bind` which draws from the domain of small natural numbers (0 <= n <=100) and use it as the size argument for the sized sampler.

Also notice the use of :code:`permanent_path`, which is a helper function providing a path to a permanent filesystem directory within the :code:`.minigun` test directory. Here we use this path to store a rendered image of the diagram of generated graphs; and the pretty printed representation of the graph is the permanent filesystem path to the image.

Choice
^^^^^^
When defining domains for inductive datastructures such as various forms of trees, e.g. ASTs, it is useful to use :code:`choice` and :code:`weighted_choice`. Where :code:`choice` takes a variadic number of generators over the same type, and uniformly selects one during sampling. :code:`weighted_choice` is the weighted version of :code:`choice`, where you additionally define the relative weight for each generator to be chosen.

Lets consider an AST for arithmetic expressions:

.. code-block:: python

    @dataclass
    class Arith: pass

    @dataclass
    class Number(Arith):
        value: int

    @dataclass
    class Plus(Arith):
        left: Arith
        right: Arith

    @dataclass
    class Minus(Arith):
        left: Arith
        right: Arith

    @dataclass
    class Times(Arith):
        left: Arith
        right: Arith

    @dataclass
    class Divide(Arith):
        left: Arith
        right: Arith

Now lets define a sampler for this abstract datatype :code:`Arith`:

.. code-block:: python

    from functools import partial
    import minigun.generate as g
    import minigun.domain as d
    import typeset as ts

    def arith_printer() -> p.Printer[Arith]:
        def _pass(layout: ts.Layout) -> ts.Layout:
            return layout
        def _group(layout: ts.Layout) -> ts.Layout:
            return ts.grp(ts.parse('"(" !& {0} !& ")"', layout))
        def _visit(
            wrap: Callable[[ts.Layout], ts.Layout],
            arith: Arith
            ) -> ts.Layout:
            match arith:
                case Number(value): return ts.text(str(value))
                case Plus(left, right):
                    return wrap(ts.parse(
                        '{0} !+ "+" + {1}',
                        _visit(_pass, left),
                        _visit(_pass, right)
                    ))
                case Minus(left, right):
                    return wrap(ts.parse(
                        '{0} !+ "-" + {1}',
                        _visit(_pass, left),
                        _visit(_pass, right)
                    ))
                case Times(left, right):
                    return wrap(ts.parse(
                        '{0} !+ "*" + {1}',
                        _visit(_group, left),
                        _visit(_group, right)
                    ))
                case Divide(left, right):
                    return wrap(ts.parse(
                        '{0} !+ "/" + {1}',
                        _visit(_group, left),
                        _visit(_group, right)
                    ))
        return partial(_visit, _pass)

    def sized_arith(size: int) -> d.Domain[Arith]:
        assert 0 <= size

        def _arith_generator(size: int) -> g.Generator[Arith]:
            if size == 0: return g.map(Number, g.int())
            _size = size // 2
            _sub_arith = _arith_generator(_size)
            return g.weighted_choice(
                (1, g.map(Number, g.int())),
                (_size, g.map(Plus,
                    _sub_arith,
                    _sub_arith
                )),
                (_size, g.map(Minus,
                    _sub_arith,
                    _sub_arith
                )),
                (_size, g.map(Times,
                    _sub_arith,
                    _sub_arith
                )),
                (_size, g.map(Divide,
                    _sub_arith,
                    _sub_arith
                ))
            )

        return d.Domain(
            _arith_generator(size),
            arith_printer()
        )

    def arith() -> d.Domain[Arith]:
        return d.bind(sized_arith, d.small_nat())

The parameter :code:`size` is used here to control the height of the tree; you can think of :code:`size` as fuel for growing the tree. It is used in the application of :code:`weighted_choice` to skew the probability of a branch of the tree from terminating with a leaf, if :code:`size` is relatively large.

.. tip::

    Minigun uses `Typeset <https://github.com/soren-n/typeset-python>`_ as the backend of the pretty printing interface. Typeset is a declarative pretty printer DSL and compiler; i.e. you compose rules for how a data serialization should be layed out, and Typeset then handles the rendering for you. This example shows you how Typeset is used to define a pretty printer for the :code:`Arith` datatype via :code:`arith_printer`.

Beyond
^^^^^^
You will not be able to compose domains for all datatypes using the combinators that Minigun provide. If you do not see a way to compose one for your specific use case, you will need to implement your own shrinker and generator. Here is some pseudo code that frames the general workflow:

.. code-block:: python

    import minigun.stream as fs
    import minigun.shrink as s
    import minigun.generate as g
    import minigun.domain as d
    import typeset as ts

    def your_shrinker(instance: YourType) -> s.Dissection[YourType]:
        def your_trimmer_1(instance: YourType) -> fs.Stream[YourType]:
            ...
        def your_trimmer_2(instance: YourType) -> fs.Stream[YourType]:
            ...
        return s.unfold(
            instance,
            your_trimmer_1,
            your_trimmer_2,
            ...
            your_trimmer_N
        )

    def your_generator(state: a.State) -> g.Sample[YourType]:
        state, instance = ...
        return state, your_shrinker(instance)

    def your_printer(instance: YourType) -> ts.Layout:
        ...

    def your_domain() -> d.Domain[YourType]:
        return d.Domain(
            your_generator,
            your_printer
        )

A :code:`Trimmer[A]` will take an instance of :code:`A`, and produce a lazy stream of shrunk instances of :code:`A` from that given instance. Exactly how you are going to implement a trimmer depends on your datatype.

A :code:`Shrinker[A]` will take an instance of :code:`A`, and produce a lazy tree of shrunk instances of :code:`A`. Think of the shrinker as being the given trimmer lazy recursively applied to the shrunk values. The reason it is a tree, is because you can use multiple trimmers to build it; each step down the tree a trimmer is selected from the given trimmers in a rotating manner.

If you need examples for further clarification, then the following section on Modeling will define a custom generator and trimmer. Also please check out the implementation of Minigun, where there are implementations for all of Python's built-in types.

Modeling
--------
Modeling in the context of property-based testing is a general technique where we build a simplified, unoptimized and ideally correct reference implementation for an interface under test. We then use this implementation as the ground truth to test other implementations against; think of it as running both systems side-by-side and comparing their behavior. There are various strategies for doing this, depending on what we are testing.

Before we get into specifics, let us put emphasis on simplified and unoptimized; this is such that we have a better argument for correctness; the smaller the reference code is relative to the production code, all else being equal, it should have fewer bugs. Also, If we build the reference implementation in a language which handles various administrative aspects of the runtime, such as memory and other resources, then we again have a better argument for correctness. The same goes for type-safe languages such as Haskell, OCaml and others in that family. Ultimately, if we were to extract the reference implementation from a specification in a proof assistant then we would have the best grip on correctness.

Lets consider modeling strategies for software with different challenges:

:Immutable state:
    E.g. functions or programs without side-effects or mutable state between evaluations. Implement a simpler and correct version of the function, compare the outputs of this implementation against the outputs of the implementation under test.

:Mutable state:
    E.g. datastructures or programs with IO. Create a denotation of programs over the system under test; e.g. for the stack example we can push, pop and get the size; we then implement a generator, shrinker and pretty printer for sequences of these denoted commands. Define a correct reference implementation of the system. Define an interpreter which will evaluate terms of the defined language of programs, while also managing an instance of the state of the system under test, as well an instance of the state of the reference implementation. Compare observable values of the two systems that are important with regards to the specification, e.g. outputs. Report failure and shrink the test case when the two systems diverge under evaluation.

:Nondeterminism:
    E.g. because of concurrency, asynchrony or IO. Generate randomly ordered sequences of modelled operations, representing the possible interleavings that could arise from concurrent access. Run these sequences sequentially against the system under test and verify that it behaves correctly regardless of ordering.

Let us consider the modeling of the stack example from earlier:

.. code-block:: python

    # Stack interface
    T = TypeVar('T')
    S = TypeVar('S')
    StackInit = Callable[[], S]
    StackPush = Callable[[S, T], S]
    StackPop = Callable[[S], Tuple[S, T]]

    # Stack model
    StackModel = List[T]
    def model_init() -> StackModel[T]:
        return []

    def model_push(stack: StackModel[T], item: T) -> StackModel[T]:
        result = stack.copy()
        result.append(item)
        return result

    def model_pop(stack: StackModel[T]) -> Tuple[StackModel[T], T]:
        result = stack.copy()
        item = result.pop(-1)
        return result, item

    # Programs over stack operations
    @dataclass
    class Value(Generic[T]): ...

    @dataclass
    class Constant(Value[T]):
        value: T

    @dataclass
    class Variable(Value[T]):
        name: str

    @dataclass
    class StackOp(Generic[T]): pass

    @dataclass
    class InitOp(StackOp[T]):
        after: str

    @dataclass
    class PushOp(StackOp[T]):
        before: str
        after: str
        item: Value[T]

    @dataclass
    class PopOp(StackOp[T]):
        before: str
        after: str
        item: str

    StackProg = List[StackOp[T]]

    def stack_prog_printer(
        value_printer: p.Printer[T]
        ) -> p.Printer[StackProg[T]]:
        def _visit_value(value: Value[T]) -> ts.Layout:
            match value:
                case Constant(value): return value_printer(value)
                case Variable(name): return ts.text(name)
        def _visit_op(op: StackOp[T]) -> ts.Layout:
            match op:
                case InitOp(after):
                    return ts.parse(
                        'fix ({0} + "=" + "init()")',
                        ts.text(after)
                    )
                case PushOp(before, after, item):
                    return ts.parse(
                        'fix ({0} + "=" + "push(" & '
                        '{1} & "," + {2} & ")")',
                        ts.text(after),
                        ts.text(before),
                        _visit_value(item)
                    )
                case PopOp(before, after, item):
                    return ts.parse(
                        'fix ({0} & "," + {1} + "=" + '
                        '"pop(" & {2} & ")")',
                        ts.text(after),
                        ts.text(item),
                        ts.text(before)
                    )
        def _visit_prog(prog: StackProg[T]) -> ts.Layout:
            match prog:
                case []: return ts.null()
                case [op, *prog1]:
                    return ts.parse(
                        '{0} </> {1}',
                        _visit_op(op),
                        _visit_prog(prog1)
                    )
        return _visit_prog

    def stack_prog_generator(
        value_generator: g.Generator[T],
        size: int
        ) -> g.Generator[StackProg[T]]:

        def _trim(prog: StackProg[T]) -> fs.Stream[StackProg[T]]:
            def _step(index: int) -> Maybe[Tuple[StackProg[T], int]]:
                if index < 0: return Nothing
                trimmed = prog[:index] + prog[index + 1:]
                return Some((trimmed, index - 1))
            return fs.unfold(_step, len(prog) - 1)

        def _visit(
            fuel: int,
            state: a.State,
            stack_ctr: int,
            item_ctr: int,
            stacks: List[str],
            nonempty: List[str]
            ) -> Tuple[a.State, StackProg[T]]:
            if fuel <= 0 or len(stacks) == 0 and fuel < 2:
                name = f's{stack_ctr}'
                return state, [InitOp(name)]
            ops: List[str] = ['init']
            if len(stacks) > 0: ops.append('push')
            if len(nonempty) > 0: ops.append('pop')
            state, op = a.choice(state, ops)
            match op:
                case 'init':
                    name = f's{stack_ctr}'
                    state, rest = _visit(
                        fuel - 1, state,
                        stack_ctr + 1, item_ctr,
                        stacks + [name], nonempty
                    )
                    return state, [InitOp(name)] + rest
                case 'push':
                    state, before = a.choice(state, stacks)
                    after = f's{stack_ctr}'
                    sampler, _ = value_generator
                    state, maybe_val = sampler(state)
                    match maybe_val:
                        case Some(dissection):
                            val = s.head(dissection)
                        case _:
                            return state, []
                    state, rest = _visit(
                        fuel - 1, state,
                        stack_ctr + 1, item_ctr,
                        stacks + [after],
                        nonempty + [after]
                    )
                    return state, [
                        PushOp(before, after, Constant(val))
                    ] + rest
                case 'pop':
                    state, before = a.choice(state, nonempty)
                    after = f's{stack_ctr}'
                    item_name = f'v{item_ctr}'
                    state, rest = _visit(
                        fuel - 1, state,
                        stack_ctr + 1, item_ctr + 1,
                        stacks + [after], nonempty
                    )
                    return state, [
                        PopOp(before, after, item_name)
                    ] + rest

        def _impl(state: a.State) -> g.Sample[StackProg[T]]:
            state, result = _visit(size, state, 0, 0, [], [])
            return state, Some(s.unfold(result, _trim))

        return _impl

    def sized_stack_prog(
        value_domain: d.Domain[T],
        size: int
        ) -> d.Domain[StackProg[T]]:
        return d.Domain(
            stack_prog_generator(value_domain.generate, size),
            stack_prog_printer(value_domain.print)
        )

    def stack_prog(value_domain: d.Domain[T]) -> d.Domain[StackProg[T]]:
        return d.bind(
            partial(sized_stack_prog, value_domain),
            d.small_nat()
        )

    # The evaluator
    def evaluator_stack_prog(
        init: StackInit[S],
        push: StackPush[S, T],
        pop: StackPop[S, T],
        prog: StackProg[T]
        ) -> bool:
        model_env: Dict[str, StackModel[T]] = {}
        impl_env: Dict[str, S] = {}
        item_env: Dict[str, T] = {}
        for op in prog:
            match op:
                case InitOp(after):
                    model_env[after] = model_init()
                    impl_env[after] = init()
                case PushOp(before, after, item):
                    match item:
                        case Constant(value): val = value
                        case Variable(name): val = item_env[name]
                    model_env[after] = model_push(
                        model_env[before], val
                    )
                    impl_env[after] = push(
                        impl_env[before], val
                    )
                case PopOp(before, after, item_name):
                    m_stack = model_pop(model_env[before])
                    i_stack = pop(impl_env[before])
                    m_rest, m_item = m_stack
                    i_rest, i_item = i_stack
                    if m_item != i_item:
                        return False
                    model_env[after] = m_rest
                    impl_env[after] = i_rest
                    item_env[item_name] = m_item
        return True

With all the pieces in place, we can now define a property that generates random stack programs, evaluates them against both the model and our implementation, and reports failure if the two diverge:

.. code-block:: python

    @context(stack_prog(d.int()))
    @prop('Stack implementation matches model')
    def _stack_model(prog: StackProg[int]):
        return evaluator_stack_prog(
            list, _push, _pop, prog
        )

    if __name__ == '__main__':
        import sys
        success = check(_stack_model)
        sys.exit(0 if success else -1)

Notice how the property is expressed at a high level: we simply state that running any random stack program should yield the same observable behavior from both the model and the implementation. The generator takes care of producing valid programs, the evaluator compares the two systems, and the shrinker will find a minimal failing program if the implementation diverges.

.. tip::

    If you would like to see an example of modeling in the real world, we would like to plug Typeset again (one of our other projects); where modeling is used to test a more complex and performant implementation of a compiler of a DSL for pretty printers, via a much simpler and slower implementation of the compiler. Minigun is using the Rust+Python implementation of this project.

    `Typeset - An embedded DSL for defining source code pretty printers implemented in OCaml <https://github.com/soren-n/typeset-ocaml>`_

Nondeterminism
^^^^^^^^^^^^^^
When the system under test may be accessed by multiple clients or processes concurrently, the order in which operations arrive is not under our control. Different runs of the same set of operations may produce different results depending on scheduling decisions made by the runtime.

Rather than actually running things concurrently (which is difficult to reproduce and control), we can model this nondeterminism by generating random interleavings of operations. We then run each interleaving sequentially against the system under test and check that it behaves correctly. This makes our tests deterministic and reproducible (given the same PRNG seed), while still exploring the space of possible orderings.

The approach extends the mutable state modeling technique as follows:

1. Define the set of operations that concurrent clients could perform, using the same modeling AST approach as before.
2. Generate randomly ordered interleavings of operations from multiple clients.
3. Execute each generated sequence sequentially against both the reference model and the system under test.
4. Compare results; any valid ordering should produce consistent behavior.

Lets consider a simple example with a shared counter that supports :code:`increment`, :code:`decrement` and :code:`read` operations:

.. code-block:: python

    @dataclass
    class CounterOp: pass

    @dataclass
    class Increment(CounterOp):
        client: int

    @dataclass
    class Decrement(CounterOp):
        client: int

    @dataclass
    class Read(CounterOp):
        client: int

    CounterProg = List[CounterOp]

    # Reference model
    def model_counter(prog: CounterProg) -> List[int]:
        state = 0
        reads = []
        for op in prog:
            match op:
                case Increment(_): state += 1
                case Decrement(_): state -= 1
                case Read(_): reads.append(state)
        return reads

We then generate random interleavings of operations from multiple clients. The key is that each client has a fixed sequence of operations it wants to perform, but the order in which different clients' operations are interleaved is random:

.. code-block:: python

    def interleave_generator(
        num_clients: int,
        ops_per_client: int
        ) -> g.Generator[CounterProg]:

        def _trim(
            prog: CounterProg
            ) -> fs.Stream[CounterProg]:
            def _step(i: int) -> Maybe[Tuple[CounterProg, int]]:
                if i < 0: return Nothing
                return Some((prog[:i] + prog[i + 1:], i - 1))
            return fs.unfold(_step, len(prog) - 1)

        def _impl(state: a.State) -> g.Sample[CounterProg]:
            # Build per-client operation sequences
            queues: List[List[CounterOp]] = []
            for client in range(num_clients):
                ops = []
                for _ in range(ops_per_client):
                    state, op_kind = a.choice(
                        state, ['inc', 'dec', 'read']
                    )
                    match op_kind:
                        case 'inc': ops.append(Increment(client))
                        case 'dec': ops.append(Decrement(client))
                        case 'read': ops.append(Read(client))
                queues.append(ops)

            # Randomly interleave the queues
            prog: CounterProg = []
            indices = [0] * num_clients
            total = num_clients * ops_per_client
            for _ in range(total):
                active = [
                    c for c in range(num_clients)
                    if indices[c] < len(queues[c])
                ]
                state, client = a.choice(state, active)
                prog.append(queues[client][indices[client]])
                indices[client] += 1

            return state, Some(s.unfold(prog, _trim))

        return _impl

We wrap the generator in a domain, pairing it with a simple printer:

.. code-block:: python

    def interleave_domain(
        num_clients: int,
        ops_per_client: int
        ) -> d.Domain[CounterProg]:
        return d.Domain(
            interleave_generator(num_clients, ops_per_client),
            p.list(p.by(str))
        )

The property then checks that the system under test produces the same observable results as the model for any random interleaving:

.. code-block:: python

    def counter_spec(
        impl_counter: Callable[[CounterProg], List[int]]
        ):
        @context(d.bind(
            lambda n: d.bind(
                lambda m: interleave_domain(n, m),
                d.small_nat()
            ),
            d.small_nat()
        ))
        @prop('Counter is consistent under any interleaving')
        def _counter_consistent(prog: CounterProg):
            return model_counter(prog) == impl_counter(prog)

        return _counter_consistent

The key insight here is that the nondeterminism is entirely captured by the generator. We do not need threads, locks, or any concurrency primitives; the generator explores the space of possible interleavings, and the evaluator runs each one sequentially and deterministically. This means that when a counterexample is found, it is perfectly reproducible, and the shrinker can minimize it to a smallest failing interleaving.

Summary
-------

Let us end this tutorial with a brief summary of what we covered:

* Why we want to do testing, and what the problems are.
* What property-based testing is, and what problems it solves.
* QuickCheck is a conceptual framework for property-based testing, and Minigun is an instantiation of it.
* Learned how to define basic specifications.
* Learned how to compose specifications.
* Learned how to abstract over specifications.
* Learned how to make user defined domains.
* Learned about modeling.
* Learned about testing nondeterministic systems by generating random operation orderings.

Moving on from this tutorial, please:

* Consult the reference to see what else is available in Minigun's toolbox.
* File an issue if you find anything that is broken or missing!

**Happy testing!**
