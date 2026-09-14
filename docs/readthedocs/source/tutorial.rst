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
Minigun requires Python >=3.12; it relies on Python 3.12 generics syntax and will not import on older versions. It is distributed via PyPI and can be installed with the following command:

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

QuickCheck implements utility for working with the following two concepts:

:Generation:
    The library provides implementations of random instance generators for the built-in types of the target language; such as integers, floats, strings and combinators for collection types such as list; as well as utility and combinators for users to define custom generators.

:Shrinking:
    Since a randomly generated input instance can be quite large, and it is only a small or specific part of the input that is causing the failure, we work with the concept of shrinking. The failing input instance is iteratively shrunk or trimmed, until a smallest possible failing instance is found. Again, the library provides implementations for shrinkers of the built-in types of the target language; as well as utility and combinators for user defined shrinkers.

In Minigun these two concepts are joined under one type :code:`Generator[A]`: a generator draws values together with their shrink trees. Counter examples are printed with Python's own :code:`repr`.

Every example in this tutorial is a complete program under ``docs/examples`` in the repository, and every one of them is run by Minigun's own test suite; the tutorial cannot drift from the library.

Basic usage
-----------
Lets start with a simple example where we define a law for an interface interaction between list concatenation, list length and integer addition. Then we will define a brief executable section, that when evaluated will check the implementation of the referenced interfaces, against the specification that we defined.

.. literalinclude:: ../../examples/basic.py
   :language: python
   :lines: 3-

Declared at the top are the imports to the relevant dependencies of Minigun. When defining basic specifications, you should not need any other imports than those listed.

Next a law is defined with the name :code:`_list_len_concat_add_dist`. It is decorated with a specification header of :code:`@prop` and :code:`@context`.

The :code:`@context` decorator will quantify the input domain of the law; here positionally giving the parameters :code:`xs` and :code:`ys` the type :code:`list[int]` via :code:`g.lists(g.ints())`.

The :code:`@prop` decorator defines a human readable description for the specification, and in turn converts the law into a property.

At last there is the executable section, where the implementation is checked against the specification with :code:`check`.

.. tip::
    Parameter generators can also be quantified by name, e.g:

    .. code-block:: python

        @context(
            xs = g.lists(g.ints()),
            ys = g.lists(g.ints())
        )

    And in the usual mixed positional and named Pythonic way, e.g:

    .. code-block:: python

        @context(
            g.lists(g.ints()),
            ys = g.lists(g.ints())
        )

.. tip::

    For simple and general input domains such as lists of integers, Minigun is actually able to infer the generator from the typehints annotated for the law's parameters. As such it is not necessary to fully write out the generators if you are quantifying over basic Python types. The following specification would have been valid as well:

    .. code-block:: python

        @prop('Length distributes over concatenation via addition')
        def _list_len_concat_add_dist(xs: list[int], ys: list[int]) -> bool:
            return len(xs + ys) == len(xs) + len(ys)

    Inference covers :code:`bool`, :code:`int`, :code:`float`, :code:`str`, :code:`None`, :code:`X | None`, and :code:`tuple`, :code:`list`, :code:`set` and :code:`dict` of those. Annotating a parameter with :code:`random.Random` gives the law a random source of its own, reproducible from the run seed.

Running tests
^^^^^^^^^^^^^
Save the example above as :code:`test_list.py` and run it directly:

.. code-block:: shell

    $ python3 test_list.py

Minigun also ships with a CLI test runner that discovers and runs test modules with a time budget. A test module is a Python file that exports its specification as a module-level attribute named :code:`spec`:

.. literalinclude:: ../../examples/lists.py
   :language: python
   :lines: 3-

If you have a :code:`tests/` directory with such test modules, you can run:

.. code-block:: shell

    $ minigun --time-budget 30

This will discover all test modules and evaluate every property in every module. There is no calibration phase: the time budget is shared between the properties in proportion to how many attempts their input domains are worth, each property runs until it has spent its share or reached its attempt limit, and time a property leaves unspent flows to the properties after it. The output ends with a summary like:

.. code-block:: text

    Test Summary
    ╭──────────┬───────┬────────┬────────┬──────────┬─────────╮
    │ Module   │ Tests │ Passed │ Failed │ Duration │ Status  │
    ├──────────┼───────┼────────┼────────┼──────────┼─────────┤
    │ lists    │  1    │   1    │   0    │  0.398s  │ PASS    │
    ├──────────┼───────┼────────┼────────┼──────────┼─────────┤
    │ TOTAL    │  1    │   1    │   0    │ 0.412s   │ PASS    │
    ╰──────────┴───────┴────────┴────────┴──────────┴─────────╯

Every run is seeded, and the seed is printed in the run header and again when a property fails. Each property draws from its own random source derived from the run seed and the property's description, so to reproduce a failing run exactly, pass the reported seed back:

.. code-block:: shell

    $ minigun --time-budget 30 --seed 5015299433215186410

See :code:`minigun --help` for all available options, including :code:`--modules` to select specific test modules and :code:`--output quiet` or :code:`--output json` for CI and tool integration.

.. note::

    A property is only as good as the values it is tested on. When a generator discards most of its draws, for example because a :code:`g.filter` predicate is too restrictive, the property fails with a message saying how many attempts were discarded, rather than passing untested.

Composing specifications
------------------------
A specification in Minigun's environment is a value of type :code:`Spec`: a property, or a composition of specifications. You have seen one constructor, namely the decorator :code:`minigun.specify.prop`, but there are others.

``minigun.specify.conj``
    For a check of a conjunction to succeed, checks of all of its terms must succeed. Every term is evaluated and reported, even after a failure.

``minigun.specify.neg``
    For a check of a negation to succeed, the check of its term must fail; that is, a counter example must be found.

A simple example of how to use :code:`conj`, is to extend our example from earlier with an additional specification:

.. literalinclude:: ../../examples/composition.py
   :language: python
   :start-after: # -- start: properties --
   :end-before: # -- end: properties --

Notice that we are testing the conjunction of the two specifications.

Template specifications
-----------------------
We might wish to capture certain concepts as specifications, and repurpose them by instantiating them for different implementations. For example we could wish to define specifications for queues, stacks or some network protocol, or more abstractly for concepts such as monoids or abelian groups.

To do this with Minigun you can use the technique of template specifications (we could also call it parameterized or higher-kinded specifications). Python supports this naturally via functions, so we can template (or parameterize) our specifications as we otherwise would.

.. literalinclude:: ../../examples/templates.py
   :language: python
   :start-after: # -- start: template --
   :end-before: # -- end: template --

.. literalinclude:: ../../examples/templates.py
   :language: python
   :start-after: # -- start: instance --
   :end-before: # -- end: instance --

What we are saying here is that :code:`[]`, :code:`len`, :code:`_push` and :code:`_pop` together implement the specification of :code:`stack`, a relationship which is represented by :code:`spec`. We can then run :code:`check` to test if the implementation adheres to the specification of :code:`stack` (at least for the unit test cases generated during that given run).

The above example is a naive and shallow specification for immutable stacks; it does not capture more complex interactions with the stack interface; and therefore does not challenge the implementation very deeply. A more complete specification would be to model programs over the stack interface; i.e. arbitrary sequences of applications of :code:`push` and :code:`pop`.

.. note::
    For Python implementations you generally do not need to go any deeper that the above example does (in practice). It is mostly for lower level languages where you have to deal with concepts such as under- and over flows, and generally have more administrative implementation details to get right regarding resource management. But if you want to be more complete in your specifications, and want to go deeper, please checkout the section about Modeling.

Refining generators
-------------------
Often the input domains to interfaces are not as general as their types suggests. Therefore to make useful and concise specifications we need to be able to define these more refined generators.

Map
^^^
As our first example, lets consider generators for even and odd natural numbers, both of which are subsets of the Python type :code:`int`.

.. literalinclude:: ../../examples/refine_map.py
   :language: python
   :start-after: # -- start: generators --
   :end-before: # -- end: generators --

Here we :code:`map` over the natural numbers, and use them as indices into the sets of even and odd natural numbers.

To use our new generators, we instantiate them the same as we would other generators defined in :code:`minigun.generate`:

.. literalinclude:: ../../examples/refine_map.py
   :language: python
   :start-after: # -- start: properties --
   :end-before: # -- end: properties --

Bind
^^^^
As another example, lets consider representing directed graphs using the type :code:`dict[int, list[int]]`. Each node in the graph is represented with an index, and the edges are represented with a map from indices to lists of indices.

If we were to simply define the input domain with the following direct translation of the type:

.. code-block:: python

    @context(g.dicts(g.ints(), g.lists(g.ints())))

We would end up generating and testing with instances of dictionaries that do not represent valid directed graphs.

To generate valid instances we need to define a refined generator:

.. literalinclude:: ../../examples/refine_bind.py
   :language: python
   :start-after: # -- start: generators --
   :end-before: # -- end: generators --

Here we define two generators over directed graphs. The first generates directed graphs of a given size, the second is defined using :code:`bind` which draws from the domain of small natural numbers (0 <= n <= 100) and use it as the size argument for the sized generator.

.. note::

    A generator built with :code:`bind` does not know the size of its domain up front, so it reports an unbounded cardinality. When you do know the size, wrap it with :code:`g.with_cardinality`; the runner uses cardinality to decide how many attempts a property is worth.

Choice
^^^^^^
When defining generators for inductive datastructures such as various forms of trees, e.g. ASTs, it is useful to use :code:`choice` and :code:`weighted_choice`. Where :code:`choice` takes a variadic number of generators over the same type, and uniformly selects one during sampling. :code:`weighted_choice` is the weighted version of :code:`choice`, where you additionally define the relative weight for each generator to be chosen.

Lets consider an AST for arithmetic expressions:

.. literalinclude:: ../../examples/refine_choice.py
   :language: python
   :start-after: # -- start: ast --
   :end-before: # -- end: ast --

Now lets define a generator for this abstract datatype :code:`Arith`:

.. literalinclude:: ../../examples/refine_choice.py
   :language: python
   :start-after: # -- start: generators --
   :end-before: # -- end: generators --

The parameter :code:`size` is used here to control the height of the tree; you can think of :code:`size` as fuel for growing the tree. It is used in the application of :code:`weighted_choice` to skew the probability of a branch of the tree from terminating with a leaf, if :code:`size` is relatively large.

.. tip::

    For recursive generators, :code:`minigun.generate.lazy` defers construction of the inner generator until the first sample is drawn. Without it, :code:`sized_arith` would build its subtrees eagerly and the construction cost would grow exponentially with the depth.

Beyond
^^^^^^
You will not be able to compose generators for all datatypes using the combinators that Minigun provide. If you do not see a way to compose one for your specific use case, you can implement your own shrinker and generator. Three pieces are involved:

:Stream:
    :code:`minigun.stream.Stream[A]` is a lazy, re-traversable sequence: a zero-argument function returning a fresh iterator. Nothing is computed until the iterator is advanced, so a stream can describe a large space of values without materializing it, and calling it again walks the same values afresh. Generator functions are the natural way to write one.

:Trimmer:
    :code:`minigun.shrink.Trimmer[A]` takes an instance of :code:`A` and produces a stream of its immediate shrunk alternatives, most aggressive first.

:Shrinker:
    :code:`minigun.shrink.Shrinker[A]` takes an instance of :code:`A` and produces a :code:`Dissection[A]`: the value together with a lazy tree of shrunk alternatives. :code:`minigun.shrink.unfold` builds one from trimmers, applying every trimmer recursively to every alternative.

Consider closed integer intervals, a type whose invariant :code:`lower <= upper` a generic shrinker would break:

.. literalinclude:: ../../examples/custom_generator.py
   :language: python
   :start-after: # -- start: type --
   :end-before: # -- end: type --

Two trimmers describe what a smaller interval is: narrower, and closer to zero. Both reuse the bundled integer shrinker for the numbers involved, so the alternatives come in the same most-aggressive-first order as for plain integers:

.. literalinclude:: ../../examples/custom_generator.py
   :language: python
   :start-after: # -- start: shrinker --
   :end-before: # -- end: shrinker --

A generator is a sampler paired with the cardinality of its domain. A sampler takes the random source, draws with the functions of :code:`minigun.arbitrary`, and returns the dissection of the drawn value, or :code:`None` when the draw is to be discarded:

.. literalinclude:: ../../examples/custom_generator.py
   :language: python
   :start-after: # -- start: generator --
   :end-before: # -- end: generator --

Use :code:`minigun.cardinality.finite(n)` when the domain has :code:`n` values and :code:`minigun.cardinality.INFINITE` when it is unbounded for practical purposes.

The bundled shrinkers cover the primitive types: :code:`s.boolean()` shrinks :code:`True` to :code:`False`; :code:`s.integer(target)` and :code:`s.floating(target)` shrink toward a target; :code:`s.string()` removes chunks of characters, largest first. :code:`s.map` combines dissections with a function, shrinking one argument at a time, and :code:`s.filter` restricts a dissection to values satisfying a predicate. Please also check out the implementation of Minigun, where there are generators and shrinkers for all of Python's built-in types.

Modeling
--------
Modeling in the context of property-based testing is a general technique where we build a simplified, unoptimized and ideally correct reference implementation for an interface under test. We then use this implementation as the ground truth to test other implementations against; think of it as running both systems side-by-side and comparing their behavior. There are various strategies for doing this, depending on what we are testing.

Before we get into specifics, let us put emphasis on simplified and unoptimized; this is such that we have a better argument for correctness; the smaller the reference code is relative to the production code, all else being equal, it should have fewer bugs. Also, If we build the reference implementation in a language which handles various administrative aspects of the runtime, such as memory and other resources, then we again have a better argument for correctness. The same goes for type-safe languages such as Haskell, OCaml and others in that family. Ultimately, if we were to extract the reference implementation from a specification in a proof assistant then we would have the best grip on correctness.

Lets consider modeling strategies for software with different challenges:

:Immutable state:
    E.g. functions or programs without side-effects or mutable state between evaluations. Implement a simpler and correct version of the function, compare the outputs of this implementation against the outputs of the implementation under test.

:Mutable state:
    E.g. datastructures or programs with IO. Create a denotation of programs over the system under test; e.g. for the stack example we can push, pop and get the size; we then implement a generator and shrinker for sequences of these denoted commands. Define a correct reference implementation of the system. Define an interpreter which will evaluate terms of the defined language of programs, while also managing an instance of the state of the system under test, as well an instance of the state of the reference implementation. Compare observable values of the two systems that are important with regards to the specification, e.g. outputs. Report failure and shrink the test case when the two systems diverge under evaluation.

:Nondeterminism:
    E.g. because of concurrency, asynchrony or IO. Generate randomly ordered sequences of modelled operations, representing the possible interleavings that could arise from concurrent access. Run these sequences sequentially against the system under test and verify that it behaves correctly regardless of ordering.

Let us consider the modeling of the stack example from earlier. First the reference model:

.. literalinclude:: ../../examples/modeling.py
   :language: python
   :start-after: # -- start: model --
   :end-before: # -- end: model --

Then a denotation of programs over the stack interface:

.. literalinclude:: ../../examples/modeling.py
   :language: python
   :start-after: # -- start: programs --
   :end-before: # -- end: programs --

A generator of programs, whose trimmer drops one operation at a time so failing programs shrink to the shortest sequence that still diverges:

.. literalinclude:: ../../examples/modeling.py
   :language: python
   :start-after: # -- start: generator --
   :end-before: # -- end: generator --

The evaluator runs a program against both the model and the implementation under test and compares what is observable:

.. literalinclude:: ../../examples/modeling.py
   :language: python
   :start-after: # -- start: evaluator --
   :end-before: # -- end: evaluator --

With all the pieces in place, we can now define a property that generates random stack programs, evaluates them against both the model and our implementation, and reports failure if the two diverge:

.. literalinclude:: ../../examples/modeling.py
   :language: python
   :start-after: # -- start: property --
   :end-before: # -- end: property --

Notice how the property is expressed at a high level: we simply state that running any random stack program should yield the same observable behavior from both the model and the implementation. The generator takes care of producing valid programs, the evaluator compares the two systems, and the shrinker will find a minimal failing program if the implementation diverges.

.. tip::

    If you would like to see an example of modeling in the real world, we would like to plug Typeset (one of our other projects); where modeling is used to test a more complex and performant implementation of a compiler of a DSL for pretty printers, via a much simpler and slower implementation of the compiler.

    `Typeset - An embedded DSL for defining source code pretty printers <https://github.com/soren-n/typeset-py>`_

Nondeterminism
^^^^^^^^^^^^^^
When the system under test may be accessed by multiple clients or processes concurrently, the order in which operations arrive is not under our control. Different runs of the same set of operations may produce different results depending on scheduling decisions made by the runtime.

Rather than actually running things concurrently (which is difficult to reproduce and control), we can model this nondeterminism by generating random interleavings of operations. We then run each interleaving sequentially against the system under test and check that it behaves correctly. This makes our tests deterministic and reproducible (given the same seed), while still exploring the space of possible orderings.

The approach extends the mutable state modeling technique as follows:

1. Define the set of operations that concurrent clients could perform, using the same modeling AST approach as before.
2. Generate randomly ordered interleavings of operations from multiple clients.
3. Execute each generated sequence sequentially against both the reference model and the system under test.
4. Compare results; any valid ordering should produce consistent behavior.

Lets consider a simple example with a shared counter that supports :code:`increment`, :code:`decrement` and :code:`read` operations, together with its reference model:

.. literalinclude:: ../../examples/nondeterminism.py
   :language: python
   :start-after: # -- start: operations --
   :end-before: # -- end: operations --

We then generate random interleavings of operations from multiple clients. The key is that each client has a fixed sequence of operations it wants to perform, but the order in which different clients' operations are interleaved is random:

.. literalinclude:: ../../examples/nondeterminism.py
   :language: python
   :start-after: # -- start: generator --
   :end-before: # -- end: generator --

The property then checks that the system under test produces the same observable results as the model for any random interleaving:

.. literalinclude:: ../../examples/nondeterminism.py
   :language: python
   :start-after: # -- start: property --
   :end-before: # -- end: property --

The key insight here is that the nondeterminism is entirely captured by the generator. We do not need threads, locks, or any concurrency primitives; the generator explores the space of possible interleavings, and the evaluator runs each one sequentially and deterministically. This means that when a counterexample is found, it is perfectly reproducible, and the shrinker can minimize it to a smallest failing interleaving.

Filesystem fixtures
-------------------
Some laws need a place on disk: a file to round-trip through, or a directory of inputs to copy and mutate. :code:`minigun.fixture` provides directories under :code:`.minigun` for this. :code:`temporary_path` gives a fresh directory that is removed when the run ends, optionally populated with a copy of a source directory:

.. literalinclude:: ../../examples/fixtures.py
   :language: python
   :start-after: # -- start: temporary --
   :end-before: # -- end: temporary --

:code:`permanent_path` gives a fresh directory that outlives the run, for artifacts you want to inspect afterwards, such as renderings of generated structures. Create it once, when the module loads, so a run produces one directory rather than one per attempt:

.. literalinclude:: ../../examples/fixtures.py
   :language: python
   :start-after: # -- start: permanent --
   :end-before: # -- end: permanent --

Cleanup is scoped to the run that created the paths: a Minigun test that itself runs Minigun does not disturb the outer run's fixtures.

Running specifications programmatically
---------------------------------------
Tools that embed Minigun have two entry points below the CLI. :code:`minigun.orchestrator.run` is the CLI's behaviour as a library call: a time budget, a seed, and a reporter chosen by :code:`OutputMode`:

.. literalinclude:: ../../examples/programmatic.py
   :language: python
   :start-after: # -- start: run --
   :end-before: # -- end: run --

Below that, :code:`minigun.specify.evaluate` runs a specification with an allowance of your choosing and hands every property's :code:`Outcome` to a callback: whether it held, attempts and discards, the counterexample with the attempt that found it, and the reason when the failure is not a counterexample.

.. literalinclude:: ../../examples/programmatic.py
   :language: python
   :start-after: # -- start: evaluate --
   :end-before: # -- end: evaluate --

Both resolve the specification before anything runs, raising :code:`SpecificationError` for a parameter without a generator or a duplicate description.

Summary
-------

Let us end this tutorial with a brief summary of what we covered:

* Why we want to do testing, and what the problems are.
* What property-based testing is, and what problems it solves.
* QuickCheck is a conceptual framework for property-based testing, and Minigun is an instantiation of it.
* Learned how to define basic specifications.
* Learned how to compose specifications.
* Learned how to abstract over specifications.
* Learned how to make user defined generators and shrinkers.
* Learned about modeling.
* Learned about testing nondeterministic systems by generating random operation orderings.
* Learned about filesystem fixtures and running specifications from your own tools.

Moving on from this tutorial, please:

* Consult the reference to see what else is available in Minigun's toolbox.
* File an issue if you find anything that is broken or missing!

**Happy testing!**
