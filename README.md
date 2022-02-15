[![GitHub](https://img.shields.io/github/license/soren-n/tickle)](https://github.com/soren-n/tickle/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![Discord](https://img.shields.io/discord/931473325543268373?label=discord)](https://discord.gg/bddF43Vk2q)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/soren-n)](https://github.com/sponsors/soren-n)

# Minigun
A library for property-based unit-testing of Python programs.

Minigun is inspired by [QCheck](https://github.com/c-cube/qcheck), which in turn was inspired by [QuickCheck](https://github.com/nick8325/quickcheck). Both are libraries that provide implementations for performing property-based unit-testing; for OCaml and Haskell respectively. If you wish to learn more about the subject, I can recommend Jan Midtgaard's [lecture materials](https://janmidtgaard.dk/quickcheck/index.html).

# Install
Minigun is currently only supported for Python >=3.10, although it might work with older versions. It is distributed with pip and can be installed with the following example command:
```
$ python3 -m pip install minigun-soren-n
```

# Basic usage
```Python
from minigun.testing import Context, Suite, test, domain
from minigun.quantify import list_of, integer

@test('List length distributes over list concatenation'. 100)
@domain(list_of(integer()), list_of(integer()))
def _list_concat_length_dist(ctx : Context, xs : list[int], ys : list[int]):
    return len(xs + ys) == len(xs) + len(ys)

if __name__ == '__main__':
    import sys
    tests = Suite(
        _list_concat_length_dist
    )
    success = test.evaluate(sys.argv)
    sys.exit(0 if success else -1)
```

# Documentation
TODO: Write and link to reference documentation