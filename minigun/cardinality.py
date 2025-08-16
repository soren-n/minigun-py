# External module dependencies
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import reduce

###############################################################################
# Symbolic Cardinality Expression System
###############################################################################


class Cardinality(ABC):
    """Abstract base class for symbolic cardinality expressions.

    This forms the foundation of a symbolic algebra system for tracking
    domain cardinalities compositionally through generator combinators.
    """

    @abstractmethod
    def __str__(self) -> str:
        """String representation of the cardinality expression."""
        pass

    @abstractmethod
    def evaluate(self, context: dict[str, int] | None = None) -> float:
        """Evaluate the cardinality expression to a numeric value.

        :param context: Variable bindings for symbolic parameters
        :return: Numeric cardinality estimate
        """
        pass

    @abstractmethod
    def simplify(self) -> "Cardinality":
        """Apply algebraic simplification rules."""
        pass

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

    def __str__(self) -> str:
        return str(self.value)

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        return float(self.value)

    def simplify(self) -> "Cardinality":
        return self


@dataclass(frozen=True)
class Variable(Cardinality):
    """Variable cardinality: |S| = n where n is parameter"""

    name: str

    def __str__(self) -> str:
        return self.name

    def evaluate(self, context: dict[str, int] | None = None) -> float:
        if context and self.name in context:
            return float(context[self.name])
        # Default heuristic for unknown variables
        return 100.0

    def simplify(self) -> "Cardinality":
        return self


# ... (file continues with more classes and functions)
