"""
Unified Symbolic Cardinality System

Modern cardinality system combining symbolic algebra with O-notation support
for sophisticated complexity analysis and optimal test attempt allocation.

Features:
- Symbolic expressions with automatic simplification
- Big O notation (O, Θ, Ω) for asymptotic complexity
- Algebraic operations with overflow protection
- Type-aware cardinality inference
- Secretary Problem optimization
- Multi-tier allocation strategy
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

###############################################################################
# Core Symbolic Expression System
###############################################################################


class _SymbolicExpr(ABC):
    """Internal symbolic expression base class."""

    @abstractmethod
    def __str__(self) -> str:
        pass

    @abstractmethod
    def evaluate(self, context: dict[str, float] | None = None) -> float:
        pass

    @abstractmethod
    def simplify(self) -> "_SymbolicExpr":
        pass

    @abstractmethod
    def variables(self) -> set[str]:
        pass

    def __add__(self, other):
        if isinstance(other, int | float):
            other = _Const(float(other))
        return _Add(self, other).simplify()

    def __mul__(self, other):
        if isinstance(other, int | float):
            other = _Const(float(other))
        return _Mul(self, other).simplify()

    def __pow__(self, other):
        if isinstance(other, int | float):
            other = _Const(float(other))
        return _Pow(self, other).simplify()

    def __radd__(self, other):
        if isinstance(other, int | float):
            return _Const(float(other)) + self
        return NotImplemented

    def __rmul__(self, other):
        if isinstance(other, int | float):
            return _Const(float(other)) * self
        return NotImplemented


@dataclass(frozen=True)
class _Const(_SymbolicExpr):
    """Constant symbolic expression."""

    value: float

    def __str__(self) -> str:
        if self.value == float("inf"):
            return "∞"
        if self.value == float("-inf"):
            return "-∞"
        if self.value == int(self.value):
            return str(int(self.value))
        return str(self.value)

    def evaluate(self, context: dict[str, float] | None = None) -> float:
        return self.value

    def simplify(self) -> "_SymbolicExpr":
        return self

    def variables(self) -> set[str]:
        return set()


@dataclass(frozen=True)
class _Var(_SymbolicExpr):
    """Variable symbolic expression."""

    name: str

    def __str__(self) -> str:
        return self.name

    def evaluate(self, context: dict[str, float] | None = None) -> float:
        if context and self.name in context:
            return context[self.name]
        return 100.0

    def simplify(self) -> "_SymbolicExpr":
        return self

    def variables(self) -> set[str]:
        return {self.name}


@dataclass(frozen=True)
class _Add(_SymbolicExpr):
    """Addition symbolic expression."""

    left: _SymbolicExpr
    right: _SymbolicExpr

    def __str__(self) -> str:
        return f"({self.left} + {self.right})"

    def evaluate(self, context: dict[str, float] | None = None) -> float:
        return self.left.evaluate(context) + self.right.evaluate(context)

    def variables(self) -> set[str]:
        return self.left.variables() | self.right.variables()

    def simplify(self) -> "_SymbolicExpr":
        left = self.left.simplify()
        right = self.right.simplify()

        if isinstance(left, _Const) and left.value == 0:
            return right
        if isinstance(right, _Const) and right.value == 0:
            return left
        if isinstance(left, _Const) and left.value == float("inf"):
            return left
        if isinstance(right, _Const) and right.value == float("inf"):
            return right
        if isinstance(left, _Const) and isinstance(right, _Const):
            return _Const(left.value + right.value)

        return _Add(left, right)


@dataclass(frozen=True)
class _Mul(_SymbolicExpr):
    """Multiplication symbolic expression."""

    left: _SymbolicExpr
    right: _SymbolicExpr

    def __str__(self) -> str:
        return f"({self.left} × {self.right})"

    def evaluate(self, context: dict[str, float] | None = None) -> float:
        left_val = self.left.evaluate(context)
        right_val = self.right.evaluate(context)

        # Overflow protection
        if left_val > 1e6 and right_val > 1e6:
            return float("inf")
        result = left_val * right_val
        return result if result < 1e10 else float("inf")

    def variables(self) -> set[str]:
        return self.left.variables() | self.right.variables()

    def simplify(self) -> "_SymbolicExpr":
        left = self.left.simplify()
        right = self.right.simplify()

        if isinstance(left, _Const) and left.value == 0:
            return _Const(0)
        if isinstance(right, _Const) and right.value == 0:
            return _Const(0)
        if isinstance(left, _Const) and left.value == 1:
            return right
        if isinstance(right, _Const) and right.value == 1:
            return left
        if isinstance(left, _Const) and left.value == float("inf"):
            return (
                left
                if not (isinstance(right, _Const) and right.value == 0)
                else _Const(0)
            )
        if isinstance(right, _Const) and right.value == float("inf"):
            return (
                right
                if not (isinstance(left, _Const) and left.value == 0)
                else _Const(0)
            )
        if isinstance(left, _Const) and isinstance(right, _Const):
            result = left.value * right.value
            return _Const(result if result < 1e10 else float("inf"))

        return _Mul(left, right)


@dataclass(frozen=True)
class _Pow(_SymbolicExpr):
    """Power symbolic expression."""

    base: _SymbolicExpr
    exponent: _SymbolicExpr

    def __str__(self) -> str:
        return f"{self.base}^{self.exponent}"

    def evaluate(self, context: dict[str, float] | None = None) -> float:
        base_val = self.base.evaluate(context)
        exp_val = self.exponent.evaluate(context)
        try:
            if base_val > 10 and exp_val > 10:
                return float("inf")
            result = base_val**exp_val
            return result if result < 1e10 else float("inf")
        except (OverflowError, ValueError):
            return float("inf")

    def variables(self) -> set[str]:
        return self.base.variables() | self.exponent.variables()

    def simplify(self) -> "_SymbolicExpr":
        base = self.base.simplify()
        exponent = self.exponent.simplify()

        if isinstance(exponent, _Const):
            if exponent.value == 0:
                return _Const(1)
            elif exponent.value == 1:
                return base

        if isinstance(base, _Const):
            if base.value == 0:
                return _Const(0)
            elif base.value == 1:
                return _Const(1)

        if isinstance(base, _Const) and isinstance(exponent, _Const):
            try:
                result = base.value**exponent.value
                return _Const(result if result < 1e10 else float("inf"))
            except (OverflowError, ValueError):
                return _Const(float("inf"))

        return _Pow(base, exponent)


@dataclass(frozen=True)
class _Log(_SymbolicExpr):
    """Logarithm symbolic expression."""

    expr: _SymbolicExpr
    base: _SymbolicExpr | None = None

    def __str__(self) -> str:
        if self.base is None:
            return f"log({self.expr})"
        return f"log_{self.base}({self.expr})"

    def evaluate(self, context: dict[str, float] | None = None) -> float:
        val = self.expr.evaluate(context)
        if val <= 0:
            return 0

        if self.base is None:
            return math.log(val)
        else:
            base_val = self.base.evaluate(context)
            if base_val <= 0 or base_val == 1:
                return 0
            return math.log(val) / math.log(base_val)

    def variables(self) -> set[str]:
        vars = self.expr.variables()
        if self.base is not None:
            vars |= self.base.variables()
        return vars

    def simplify(self) -> "_SymbolicExpr":
        expr = self.expr.simplify()
        base = self.base.simplify() if self.base else None

        if isinstance(expr, _Const) and expr.value == 1:
            return _Const(0)

        return _Log(expr, base)


###############################################################################
# Public Cardinality System
###############################################################################


class Cardinality(ABC):
    """Abstract base class for cardinality expressions."""

    def __init__(self):
        object.__setattr__(self, "_symbolic", None)

    @abstractmethod
    def __str__(self) -> str:
        """String representation of the cardinality expression."""
        pass

    @abstractmethod
    def evaluate(self, context: dict[str, int] | None = None) -> float:
        """Evaluate the cardinality expression to a numeric value."""
        pass

    @abstractmethod
    def simplify(self) -> "Cardinality":
        """Apply algebraic simplification rules."""
        pass

    def _to_symbolic(self) -> _SymbolicExpr:
        """Convert to internal symbolic representation."""
        if self._symbolic is None:
            object.__setattr__(self, "_symbolic", self._create_symbolic())
        return self._symbolic

    @abstractmethod
    def _create_symbolic(self) -> _SymbolicExpr:
        """Create the symbolic representation (subclasses implement)."""
        pass

    def asymptotic_class(self) -> str:
        """Return asymptotic complexity class."""
        symbolic = self._to_symbolic()
        expr_str = str(symbolic)

        if "∞" in expr_str:
            return "O(∞)"
        elif "^" in expr_str and any(
            var in expr_str for var in ["n", "size", "length"]
        ):
            return "O(n^k)"
        elif "×" in expr_str and any(
            var in expr_str for var in ["n", "size", "length"]
        ):
            return "O(n²)"
        elif any(var in expr_str for var in ["n", "size", "length"]):
            return "O(n)"
        elif "log" in expr_str:
            return "O(log n)"
        else:
            return "O(1)"

    def __add__(self, other: "Cardinality") -> "Cardinality":
        """Addition: |A ∪ B| = |A| + |B| (for disjoint A, B)"""
        return Sum(self, other).simplify()

    def __mul__(self, other: "Cardinality") -> "Cardinality":
        """Multiplication: |A × B| = |A| × |B|"""
        return Product(self, other).simplify()

    def __pow__(self, other: "Cardinality") -> "Cardinality":
        """Exponentiation: |A^B| = |A|^|B|"""
        return Exponential(self, other).simplify()


@dataclass(frozen=True)
class Finite(Cardinality):
    """Finite cardinality: |S| = n"""

    value: int

    def __post_init__(self):
        super().__init__()

    def __str__(self) -> str:
        return str(self.value)

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        return float(self.value)

    def simplify(self) -> "Cardinality":
        return self

    def _create_symbolic(self) -> _SymbolicExpr:
        return _Const(float(self.value))


@dataclass(frozen=True)
class Variable(Cardinality):
    """Variable cardinality: |S| = n where n is parameter"""

    name: str

    def __post_init__(self):
        super().__init__()

    def __str__(self) -> str:
        return self.name

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        if context and self.name in context:
            return float(context[self.name])
        return 100.0

    def simplify(self) -> "Cardinality":
        return self

    def _create_symbolic(self) -> _SymbolicExpr:
        return _Var(self.name)


@dataclass(frozen=True)
class Sum(Cardinality):
    """Sum cardinality: |A ∪ B| = |A| + |B| (for disjoint A, B)"""

    left: Cardinality
    right: Cardinality

    def __post_init__(self):
        super().__init__()

    def __str__(self) -> str:
        return f"({self.left} + {self.right})"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        return self.left.evaluate(context) + self.right.evaluate(context)

    def simplify(self) -> "Cardinality":
        left_simplified = self.left.simplify()
        right_simplified = self.right.simplify()

        # Use symbolic simplification
        left_sym = left_simplified._to_symbolic()
        right_sym = right_simplified._to_symbolic()
        combined_sym = (left_sym + right_sym).simplify()

        # Convert back to concrete types if possible
        if isinstance(combined_sym, _Const):
            if combined_sym.value == float("inf"):
                return Infinite()
            return Finite(int(combined_sym.value))
        elif isinstance(combined_sym, _Var):
            return Variable(combined_sym.name)

        # Return as symbolic cardinality
        return SymbolicCardinality(combined_sym)

    def _create_symbolic(self) -> _SymbolicExpr:
        return self.left._to_symbolic() + self.right._to_symbolic()


@dataclass(frozen=True)
class Product(Cardinality):
    """Product cardinality: |A × B| = |A| × |B|"""

    left: Cardinality
    right: Cardinality

    def __post_init__(self):
        super().__init__()

    def __str__(self) -> str:
        return f"({self.left} × {self.right})"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        left_val = self.left.evaluate(context)
        right_val = self.right.evaluate(context)

        # Overflow protection
        if left_val > 1e6 and right_val > 1e6:
            return float("inf")

        result = left_val * right_val
        return result if result < 1e10 else float("inf")

    def simplify(self) -> "Cardinality":
        left_simplified = self.left.simplify()
        right_simplified = self.right.simplify()

        # Use symbolic simplification
        left_sym = left_simplified._to_symbolic()
        right_sym = right_simplified._to_symbolic()
        combined_sym = (left_sym * right_sym).simplify()

        # Convert back to concrete types
        if isinstance(combined_sym, _Const):
            if combined_sym.value == float("inf"):
                return Infinite()
            return Finite(int(combined_sym.value))
        elif isinstance(combined_sym, _Var):
            return Variable(combined_sym.name)

        return SymbolicCardinality(combined_sym)

    def _create_symbolic(self) -> _SymbolicExpr:
        return self.left._to_symbolic() * self.right._to_symbolic()


@dataclass(frozen=True)
class Exponential(Cardinality):
    """Exponential cardinality: |A^B| = |A|^|B|"""

    base: Cardinality
    exponent: Cardinality

    def __post_init__(self):
        super().__init__()

    def __str__(self) -> str:
        return f"({self.base}^{self.exponent})"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        base_val = self.base.evaluate(context)
        exp_val = self.exponent.evaluate(context)

        try:
            if base_val > 10 and exp_val > 10:
                return float("inf")

            result = base_val**exp_val
            return result if result < 1e10 else float("inf")
        except (OverflowError, ValueError):
            return float("inf")

    def simplify(self) -> "Cardinality":
        base_simplified = self.base.simplify()
        exponent_simplified = self.exponent.simplify()

        # Use symbolic simplification
        base_sym = base_simplified._to_symbolic()
        exp_sym = exponent_simplified._to_symbolic()
        combined_sym = (base_sym**exp_sym).simplify()

        # Convert back to concrete types
        if isinstance(combined_sym, _Const):
            if combined_sym.value == float("inf"):
                return Infinite()
            return Finite(int(combined_sym.value))
        elif isinstance(combined_sym, _Var):
            return Variable(combined_sym.name)

        return SymbolicCardinality(combined_sym)

    def _create_symbolic(self) -> _SymbolicExpr:
        return self.base._to_symbolic() ** self.exponent._to_symbolic()


@dataclass(frozen=True)
class Infinite(Cardinality):
    """Infinite cardinality: |S| = ∞"""

    def __post_init__(self):
        super().__init__()

    def __str__(self) -> str:
        return "∞"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        return float("inf")

    def simplify(self) -> "Cardinality":
        return self

    def _create_symbolic(self) -> _SymbolicExpr:
        return _Const(float("inf"))


@dataclass(frozen=True)
class Linear(Cardinality):
    """Linear cardinality: |S| = O(n)"""

    variable: Variable
    coefficient: Cardinality

    def __post_init__(self):
        super().__init__()
        if self.coefficient is None:
            object.__setattr__(self, "coefficient", Finite(1))

    def __str__(self) -> str:
        if isinstance(self.coefficient, Finite) and self.coefficient.value == 1:
            return f"O({self.variable.name})"
        return f"O({self.coefficient} × {self.variable.name})"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        coeff = self.coefficient.evaluate(context)
        var_val = self.variable.evaluate(context)
        return coeff * var_val

    def simplify(self) -> "Cardinality":
        simplified_coeff = self.coefficient.simplify()
        return Linear(self.variable, simplified_coeff)

    def _create_symbolic(self) -> _SymbolicExpr:
        return self.coefficient._to_symbolic() * self.variable._to_symbolic()


@dataclass(frozen=True)
class Polynomial(Cardinality):
    """Polynomial cardinality: |S| = O(n^k)"""

    variable: Variable
    degree: int
    coefficient: Cardinality | None = None

    def __post_init__(self):
        super().__init__()
        if self.coefficient is None:
            object.__setattr__(self, "coefficient", Finite(1))

    def __str__(self) -> str:
        if isinstance(self.coefficient, Finite) and self.coefficient.value == 1:
            if self.degree == 1:
                return f"O({self.variable.name})"
            return f"O({self.variable.name}^{self.degree})"
        if self.degree == 1:
            return f"O({self.coefficient} × {self.variable.name})"
        return f"O({self.coefficient} × {self.variable.name}^{self.degree})"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        coeff = self.coefficient.evaluate(context) if self.coefficient else 1.0
        var_val = self.variable.evaluate(context)
        return coeff * (var_val**self.degree)

    def simplify(self) -> "Cardinality":
        return Polynomial(
            self.variable,
            self.degree,
            (self.coefficient.simplify() if self.coefficient else Finite(1)),
        )

    def _create_symbolic(self) -> _SymbolicExpr:
        coeff_sym = (
            self.coefficient._to_symbolic() if self.coefficient else _Const(1.0)
        )
        var_sym = self.variable._to_symbolic()
        degree_sym = _Const(float(self.degree))
        return coeff_sym * (var_sym**degree_sym)


@dataclass(frozen=True)
class Logarithmic(Cardinality):
    """Logarithmic cardinality: |S| = O(log n)"""

    variable: Variable
    coefficient: Cardinality | None = None

    def __post_init__(self):
        super().__init__()
        if self.coefficient is None:
            object.__setattr__(self, "coefficient", Finite(1))

    def __str__(self) -> str:
        if isinstance(self.coefficient, Finite) and self.coefficient.value == 1:
            return f"O(log {self.variable.name})"
        return f"O({self.coefficient} × log {self.variable.name})"

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        coeff = self.coefficient.evaluate(context) if self.coefficient else 1.0
        var_val = self.variable.evaluate(context)
        return coeff * math.log2(max(1, var_val))

    def simplify(self) -> "Cardinality":
        return Logarithmic(
            self.variable,
            (self.coefficient.simplify() if self.coefficient else Finite(1)),
        )

    def _create_symbolic(self) -> _SymbolicExpr:
        coeff_sym = (
            self.coefficient._to_symbolic() if self.coefficient else _Const(1.0)
        )
        var_sym = self.variable._to_symbolic()
        return coeff_sym * _Log(var_sym)


###############################################################################
# Symbolic Extensions
###############################################################################


class AsymptoticClass(Enum):
    """Asymptotic complexity classes."""

    BIG_O = "O"
    BIG_THETA = "Θ"
    BIG_OMEGA = "Ω"


@dataclass(frozen=True)
class SymbolicCardinality(Cardinality):
    """Cardinality represented by symbolic expressions."""

    symbolic_expr: _SymbolicExpr

    def __post_init__(self):
        super().__init__()
        object.__setattr__(self, "_symbolic", self.symbolic_expr)

    def __str__(self) -> str:
        return str(self.symbolic_expr)

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        float_context = (
            {k: float(v) for k, v in context.items()} if context else None
        )
        return self.symbolic_expr.evaluate(float_context)

    def simplify(self) -> "Cardinality":
        simplified = self.symbolic_expr.simplify()
        return SymbolicCardinality(simplified)

    def _create_symbolic(self) -> _SymbolicExpr:
        return self.symbolic_expr


@dataclass(frozen=True)
class BigO(SymbolicCardinality):
    """Big O notation: O(f(n))"""

    def __init__(self, expr: _SymbolicExpr):
        super().__init__(expr)

    def __str__(self) -> str:
        return f"O({self.symbolic_expr})"

    def simplify(self) -> "Cardinality":
        simplified_expr = self.symbolic_expr.simplify()

        # Drop constant factors: O(c×f) = O(f)
        if isinstance(simplified_expr, _Mul):
            if isinstance(simplified_expr.left, _Const):
                return BigO(simplified_expr.right)
            if isinstance(simplified_expr.right, _Const):
                return BigO(simplified_expr.left)

        # O(c) = O(1) for constants
        if isinstance(simplified_expr, _Const):
            return BigO(_Const(1))

        return BigO(simplified_expr)


###############################################################################
# Calculation Functions
###############################################################################


def calculate_secretary_problem_limit(
    cardinality: Cardinality, context: dict[str, int] | None = None
) -> int:
    """Calculate theoretical Secretary Problem optimal stopping limit (√cardinality)."""
    domain_size = cardinality.evaluate(context)

    if domain_size >= float("inf"):
        return 10000

    return max(1, int(math.sqrt(domain_size)))


def calculate_optimal_attempts(
    cardinality: Cardinality, context: dict[str, int] | None = None
) -> int:
    """Calculate practical test attempts using asymptotic-aware allocation."""
    # Use asymptotic class for better allocation
    asymptotic = cardinality.asymptotic_class()

    if "∞" in asymptotic:
        return 1000
    elif "n^" in asymptotic:  # Exponential/polynomial
        return 50
    elif "n²" in asymptotic:  # Quadratic
        return 100
    elif "n" in asymptotic:  # Linear
        domain_size = cardinality.evaluate(context)
        return max(10, int(math.sqrt(domain_size)))
    elif "log" in asymptotic:  # Logarithmic
        return 200
    else:  # O(1)
        domain_size = cardinality.evaluate(context)
        if domain_size <= 1000:
            return max(10, int(math.sqrt(domain_size)))
        elif domain_size <= 1_000_000:
            base = math.sqrt(1000)
            extra = math.log10(domain_size / 1000)
            return int(base + extra * 10)
        else:
            base = math.sqrt(1000) + math.log10(1000) * 10
            extra = math.log10(domain_size / 1_000_000)
            return int(base + extra * 5)


def calculate_attempts_from_generators(
    generators: dict[str, object], context: dict[str, int] | None = None
) -> int:
    """Calculate optimal attempts from a collection of generators."""
    if not generators:
        return 100

    # Extract cardinalities and calculate product
    total_cardinality = ONE
    for _param, maybe_generator in generators.items():
        if maybe_generator is not None:
            # Handle Maybe[Generator] case
            if hasattr(maybe_generator, "unwrap"):
                try:
                    generator = maybe_generator.unwrap()
                    if isinstance(generator, tuple) and len(generator) == 2:
                        param_cardinality = generator[1]
                    else:
                        param_cardinality = Finite(100)
                    total_cardinality = total_cardinality * param_cardinality
                except Exception:
                    total_cardinality = total_cardinality * Finite(100)
            elif (
                isinstance(maybe_generator, tuple) and len(maybe_generator) == 2
            ):
                param_cardinality = maybe_generator[1]
                total_cardinality = total_cardinality * param_cardinality
            else:
                total_cardinality = total_cardinality * Finite(100)

    return calculate_optimal_attempts(total_cardinality, context)


###############################################################################
# Type Inference
###############################################################################


def infer_cardinality_from_type(type_hint: Any) -> Cardinality:
    """Infer cardinality from Python type hints."""
    # n = Variable('n')  # Available if needed

    if type_hint is bool:
        return Finite(2)
    elif type_hint is int:
        return Infinite()  # Unrestricted integers
    elif type_hint is float:
        return Infinite()  # Unrestricted floats
    elif type_hint is str:
        return BigO(_Const(256) ** _Var("n"))  # Exponential in string length
    elif hasattr(type_hint, "__origin__"):
        origin = type_hint.__origin__
        args = getattr(type_hint, "__args__", ())

        if origin is list:
            if args:
                element_card = infer_cardinality_from_type(args[0])
                return BigO(element_card._to_symbolic() ** _Var("n"))
            return BigO(_Const(256) ** _Var("n"))

        elif origin is dict:
            if len(args) >= 2:
                key_card = infer_cardinality_from_type(args[0])
                val_card = infer_cardinality_from_type(args[1])
                combined = (key_card * val_card)._to_symbolic()
                return BigO(combined ** _Var("n"))
            return BigO(_Const(256) ** _Var("n"))

        elif origin is tuple:
            if args:
                product = ONE
                for arg in args:
                    element_card = infer_cardinality_from_type(arg)
                    product = product * element_card
                return product
            return ONE  # Empty tuple

    # Default fallback
    return BigO(_Var("n"))


###############################################################################
# Constants
###############################################################################

# Common constants
ZERO = Finite(0)
ONE = Finite(1)
INFINITY = Infinite()

# Domain-specific constants
BOOL_CARDINALITY = Finite(2)
BYTE_CARDINALITY = Finite(256)
ASCII_CARDINALITY = Finite(128)
UNICODE_CARDINALITY = Infinite()

# Common variables
N = Variable("n")
SIZE = Variable("size")
LENGTH = Variable("length")
CAPACITY = Variable("capacity")

# Symbolic constants for convenience
O_1 = BigO(_Const(1))
O_N = BigO(_Var("n"))
O_N2 = BigO(_Var("n") ** _Const(2))
O_N_LOG_N = BigO(_Var("n") * _Log(_Var("n")))
