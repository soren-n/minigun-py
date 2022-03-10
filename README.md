[![GitHub](https://img.shields.io/github/license/soren-n/tickle)](https://github.com/soren-n/tickle/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![Discord](https://img.shields.io/discord/931473325543268373?label=discord)](https://discord.gg/bddF43Vk2q)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/soren-n)](https://github.com/sponsors/soren-n)

# Minigun
A QuickCheck-like library for property-based unit-testing of Python programs.

Minigun is inspired by [QCheck](https://github.com/c-cube/qcheck), which in turn was inspired by [QuickCheck](https://github.com/nick8325/quickcheck). Both are libraries that provide implementations for performing property-based unit-testing; for OCaml and Haskell respectively.

If you would like a bit of motivation as to why you should use a QuickCheck-like system for testing your project, then I would recommend that you watch:
- [John Hughes - Testing the Hard Stuff and Staying Sane](https://www.youtube.com/watch?v=zi0rHwfiX1Q)
- [John Hughes - Certifying your car with Erlang](https://vimeo.com/68331689)

If you wish to learn more about the subject, I can recommend Jan Midtgaard's [lecture materials](https://janmidtgaard.dk/quickcheck/index.html); it is OCaml based but translates easily to other QuickCheck-like libraries for other languages.

# Install
Minigun is currently only supported for Python >=3.10, although it might work with older versions. It is distributed with pip and can be installed with the following example command:
```
$ python3 -m pip install minigun-soren-n
```

# Basic usage
```Python
from minigun.testing import prop, domain, check
import minigun.quantify as q

@prop('List length distributes over list concatenation'. 100)
@domain(q.list_of(q.integer()), q.list_of(q.integer()))
def _list_concat_length_dist(xs : list[int], ys : list[int]):
    return len(xs + ys) == len(xs) + len(ys)

if __name__ == '__main__':
    import sys
    success = check(_list_concat_length_dist)
    sys.exit(0 if success else -1)
```
At the top the relevant dependencies are imported.

Then a specification for a property of list concatenation interacting with list length. The `domain` decorator defines the domain of the specification; here the specification is defined over two lists of integers. The `prop` decorator defines a human-readable description of the property, along with number of random test cases to be generated during checking of the property.

The last section is an example of how to check a specification.

# Documentation
TODO: Write and link to reference documentation

# Examples
The following projects use Minigun for testing:
- [Minigun](https://github.com/soren-n/minigun/tree/main/tests)
- [Tickle](https://github.com/soren-n/tickle/tree/main/tests)

If you have used Minigun for testing of a public project, and would like it added to the list, then please file an issue with a link to the project.