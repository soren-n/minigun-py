# DEVELOPMENT_WORKFLOW.md

## Development Workflow and Setup

This document covers the development environment setup, tools, and workflows for contributing to Minigun. It's designed to help coding agents understand the complete development lifecycle.

## Development Environment Setup

### 1. Python Environment Requirements
- **Python Version:** >=3.12 (Required for modern typing features)
- **Package Manager:** `uv` (preferred) or `pip`
- **Virtual Environment:** Automatically managed by `uv`

### 2. Project Setup
```bash
# Clone the repository
git clone https://github.com/soren-n/minigun-py.git
cd minigun-py

# Install dependencies with uv (recommended)
uv sync

# Alternative: install with pip
pip install -e .[dev,quality]
```

### 3. Dependency Categories
**Runtime Dependencies:**
```toml
dependencies = [
    "returns>=0.25.0",      # Monadic types (Maybe, etc.)
    "tqdm>=4.67.1",         # Progress bars
    "typeset-soren-n>=2.0.8",  # Type utilities
    "rich>=13.0.0",         # Terminal formatting
]
```

**Development Dependencies:**
```toml
[dependency-groups]
dev = [
    "mypy>=1.15.0",         # Static type checking
    "sphinx>=8.2.3",        # Documentation generation
    "sphinx-rtd-theme>=3.0.2",  # Documentation theme
]

quality = [
    "ruff>=0.6.0",          # Code formatting and linting
    "coverage>=7.6.0",      # Code coverage
    "pre-commit>=4.3.0",    # Git hooks
]
```

## Code Quality Tools

### 1. Type Checking with MyPy
**Configuration:** `pyproject.toml` contains MyPy settings

```bash
# Run type checking
uv run mypy minigun/

# Check specific file
uv run mypy minigun/generate.py
```

**Type Checking Standards:**
- **100% coverage** - All functions must have type annotations
- **Strict mode** - No `Any` types without explicit justification
- **Generic parameters** - Use type variables for reusable functions
- **Return types** - Always annotate return types explicitly

### 2. Code Formatting and Linting
**Ruff for all formatting and linting:**

```bash
# Format code
uv run ruff format minigun/ tests/

# Lint with Ruff
uv run ruff check minigun/ tests/

# Auto-fix with Ruff
uv run ruff check --fix minigun/ tests/
```

**Formatting Standards:**
- **Line length:** 80 characters (strict limit for readability)
- **Import organization:** Standard library, third-party, local
- **String quotes:** Double quotes preferred
- **Trailing commas:** In multi-line structures

### 3. Pre-commit Hooks
**Setup:**
```bash
# Install pre-commit hooks
uv run pre-commit install

# Run hooks manually
uv run pre-commit run --all-files
```

**Hook Configuration (`.pre-commit-config.yaml`):**
```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: ruff format
        language: system
        types: [python]

      - id: ruff-check
        name: ruff check
        entry: ruff check
        language: system
        types: [python]

      - id: mypy
        name: mypy
        entry: mypy
        language: system
        types: [python]
```

## Testing Workflow

### 1. Running Tests
**Basic test execution (v2.2.0 with required time budget):**
```bash
# Run all tests with time budget (required parameter)
uv run minigun-test --time-budget 30

# Run specific test modules with time budget
uv run minigun-test --time-budget 45 --modules positive comprehensive

# Run tests in quiet mode (CI/CD)
uv run minigun-test --time-budget 60 --quiet

# Run tests with JSON output (tool integration)
uv run minigun-test --time-budget 30 --json

# List available test modules
uv run minigun-test --list-modules

# Alternative test runner (legacy)
uv run test
```

**New CLI Features in v2.2.0:**
- **`--time-budget`** - Required parameter for time-based test allocation (in seconds)
- **`--json`** - JSON output format for tool integration and CI/CD
- **Two-phase execution** - Automatic calibration phase followed by optimized execution
- **Budget allocation** - Intelligent attempt distribution based on cardinality analysis

### 2. Test Development Process
1. **Write property** - Define what should be true
2. **Choose domain** - Select appropriate test data
3. **Implement test** - Use `@prop` and `@context` decorators
4. **Verify failure** - Test with `@neg` if expecting failure
5. **Run tests** - Check property holds
6. **Debug shrinking** - Ensure counterexamples are minimal

**Example development cycle:**
```python
# 1. Start with simple property
@prop("basic property")
def test_simple(x: int) -> bool:
    return some_operation(x) >= 0

# 2. Add context for better test data
@context(d.int_range(0, 100))
@prop("property with domain")
def test_with_domain(x: int) -> bool:
    return some_operation(x) >= 0

# 3. Test edge cases
@context(d.one_of([0, -1, 1]))
@prop("edge case behavior")
def test_edge_cases(x: int) -> bool:
    return some_operation(x) >= 0
```

### 3. Coverage Analysis
```bash
# Run tests with coverage
uv run coverage run --source=minigun -m pytest tests/

# Generate coverage report
uv run coverage report

# Generate HTML coverage report
uv run coverage html
```

## Documentation Workflow

### 1. Sphinx Documentation
**Build documentation:**
```bash
cd docs/readthedocs
make html

# Windows
make.bat html
```

**Documentation structure:**
```
docs/
├── readthedocs/
│   ├── source/
│   │   ├── conf.py          # Sphinx configuration
│   │   ├── index.rst        # Main documentation page
│   │   ├── tutorial.rst     # User tutorial
│   │   ├── reference.rst    # API reference
│   │   └── minigun.rst      # Module documentation
│   └── build/html/          # Generated HTML
└── context/                 # Coding agent context docs
```

### 2. API Documentation Standards
**Docstring format (Sphinx-compatible):**
```python
def function_name(param1: Type1, param2: Type2) -> ReturnType:
    """Brief description of function purpose.

    Longer description with examples if needed:

    .. code-block:: python

        result = function_name(arg1, arg2)
        assert result.property == expected

    :param param1: Description of first parameter
    :type param1: Type1
    :param param2: Description of second parameter
    :type param2: Type2
    :return: Description of return value
    :rtype: ReturnType
    :raises ValueError: When parameter is invalid
    """
```

### 3. Context Documentation
**Maintain coding agent context docs in `docs/context/`:**
- **PROJECT_OVERVIEW.md** - High-level project understanding
- **ARCHITECTURE_GUIDE.md** - Module structure and dependencies
- **CORE_CONCEPTS.md** - Property-based testing concepts
- **GENERATOR_SYSTEM.md** - Deep dive into generators
- **API_PATTERNS.md** - Common patterns and conventions
- **TESTING_STRATEGY.md** - How the project tests itself
- **DEVELOPMENT_WORKFLOW.md** - This document
- **CODING_STYLE_IMPROVEMENTS.md** - Coding style requirements

## Git Workflow

### 1. Branch Strategy
**Main branches:**
- **`main`** - Stable, production-ready code
- **Feature branches** - For new features and bug fixes
- **`docs/*`** - For documentation updates

**Branch naming:**
```bash
feature/add-new-generator
bugfix/fix-shrinking-issue
docs/update-tutorial
refactor/improve-performance
```

### 2. Commit Standards
**Commit message format:**
```
type(scope): brief description

Longer explanation if needed, explaining what and why,
not how. Include any breaking changes.

Fixes #123
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `style` - Code style changes (formatting, etc.)
- `refactor` - Code refactoring without feature changes
- `test` - Adding or updating tests
- `chore` - Maintenance tasks

### 3. Pull Request Process
1. **Create feature branch** from `main`
2. **Implement changes** following coding standards
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Run quality checks** (pre-commit hooks)
6. **Create pull request** with descriptive title and body
7. **Address review feedback**
8. **Merge** when approved

## Release Process

### 1. Version Management
**Semantic versioning (SemVer):**
- **Major** (X.0.0) - Breaking changes
- **Minor** (x.Y.0) - New features, backward compatible
- **Patch** (x.y.Z) - Bug fixes, backward compatible

**Update version in:**
- `pyproject.toml` - Project version
- `minigun/__init__.py` - Package version
- Documentation if needed

### 2. Release Checklist
1. **Update version** numbers
2. **Update CHANGELOG.md** with release notes
3. **Run full test suite** and verify all pass
4. **Build documentation** and verify it renders correctly
5. **Create release tag** in Git
6. **Build and upload** to PyPI
7. **Update GitHub release** with changelog

### 3. PyPI Publishing
```bash
# Build package
uv build

# Upload to PyPI (requires credentials)
uv publish
```

## Performance Optimization

### 1. Profiling
**Profile test performance:**
```bash
# Profile test execution
python -m cProfile -o profile.stats -m minigun.cli

# Analyze profile results
python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"
```

### 2. Memory Usage
**Monitor memory during testing:**
```python
import tracemalloc

tracemalloc.start()
# Run tests
current, peak = tracemalloc.get_traced_memory()
print(f"Current memory usage: {current / 1024 / 1024:.1f} MB")
print(f"Peak memory usage: {peak / 1024 / 1024:.1f} MB")
```

### 3. Generator Performance
**Optimize slow generators:**
- **Profile individual generators** to find bottlenecks
- **Use lazy evaluation** for large data structures
- **Limit shrinking depth** for complex types
- **Cache expensive computations** when appropriate

## Debugging Strategies

### 1. Property Debugging
**When properties fail:**
1. **Examine counterexample** - Minigun provides minimal failing case
2. **Add print statements** - Debug property logic
3. **Isolate the issue** - Create focused test for specific case
4. **Check assumptions** - Verify understanding of expected behavior

### 2. Generator Debugging
**When generators behave unexpectedly:**
1. **Test generator directly** - Generate samples manually
2. **Check distribution** - Verify generator produces expected range
3. **Examine shrinking** - Ensure shrinking works correctly
4. **Profile performance** - Check for efficiency issues

### 3. Common Issues
**Infinite generation loops:**
- Add bounds to prevent infinite generation
- Use timeouts in test execution
- Check filter predicates for feasibility

**Memory issues:**
- Use lazy evaluation for large structures
- Limit collection sizes appropriately
- Monitor memory usage during testing

**Slow tests:**
- Profile to find bottlenecks
- Reduce sample sizes for development
- Optimize generator composition

This workflow ensures consistent, high-quality development while maintaining the functional programming principles and testing practices that make Minigun effective.
