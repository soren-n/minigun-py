[![GitHub](https://img.shields.io/github/license/soren-n/tickle)](https://github.com/soren-n/tickle/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/minigun-soren-n)](https://pypi.org/project/minigun-soren-n/)
[![Discord](https://img.shields.io/discord/931473325543268373?label=discord)](https://discord.gg/bddF43Vk2q)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/soren-n)](https://github.com/sponsors/soren-n)
[![Documentation Status](https://readthedocs.org/projects/minigun/badge/?version=latest)](https://minigun.readthedocs.io/en/latest/?badge=latest)

# Minigun
A QuickCheck-like library for property-based unit-testing of Python programs.

Minigun is inspired by [QCheck](https://github.com/c-cube/qcheck), which in turn was inspired by [QuickCheck](https://github.com/nick8325/quickcheck). Both are libraries that provide implementations for performing property-based unit-testing; for OCaml and Haskell respectively.

If you would like a bit of motivation as to why you should use a QuickCheck-like system for testing your project, then I would recommend that you watch:
- [John Hughes - Testing the Hard Stuff and Staying Sane](https://www.youtube.com/watch?v=zi0rHwfiX1Q)
- [John Hughes - Certifying your car with Erlang](https://vimeo.com/68331689)

If you wish to learn more about the subject, I can recommend Jan Midtgaard's [lecture materials](https://janmidtgaard.dk/quickcheck/index.html); it is OCaml based but translates easily to other QuickCheck-like libraries for other languages.

# Install
Minigun is currently only supported for Python >=3.10. It is distributed with pip and can be installed with the following example command:
```
pip install minigun-soren-n
```

# Documentation
A tutorial as well as reference documentation for the API can be found at [Read The Docs](https://minigun.readthedocs.io/en/latest/).

# Development

## Semantic Versioning
This project uses automated semantic versioning based on conventional commits. See [`SEMANTIC_VERSIONING.md`](SEMANTIC_VERSIONING.md) for details on:
- How to write conventional commit messages
- Automatic version bumps and releases
- Setting up the development environment

To get started with development:
```bash
# Setup semantic versioning tools and git hooks
python scripts/setup_semantic_versioning.py
```

# Testing with Rich Output

Minigun includes beautiful test output with rich formatting, progress indicators, and detailed reporting.

## Basic Testing
```bash
# Run all tests with rich output
uv run python -m tests.main

# Or use the CLI tool
uv run minigun-test
```

## CLI Tool
```bash
# Run all tests with enhanced output
uv run minigun-test

# Run specific test modules
uv run minigun-test --modules positive comprehensive

# Quiet mode (minimal output for CI/CD)
uv run minigun-test --quiet

# List available test modules
uv run minigun-test --list-modules

# Show help
uv run minigun-test --help
```

The rich output provides:
- 🎯 Individual test visibility with names and status
- ⏱️ Timing information for each test and module
- 📊 Progress indicators and statistics
- 🎨 Rich formatting with colors and tables
- 🔍 Detailed counter-examples for failed tests
- 📋 Comprehensive summary reports

# Examples
The following projects use Minigun for testing:
- [Minigun](https://github.com/soren-n/minigun/tree/main/tests)
- [Tickle](https://github.com/soren-n/tickle/tree/main/tests)

If you have used Minigun for testing of a public project, and would like it added to the list, then please file an issue with a link to the project.