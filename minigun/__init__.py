import importlib.metadata

from minigun import generate
from minigun.orchestrator import check
from minigun.specify import (
    Conj,
    Discard,
    Neg,
    Prop,
    Spec,
    SpecificationError,
    assume,
    conj,
    context,
    discard,
    neg,
    prop,
)

# The version is recorded once, in pyproject.toml.
__version__ = importlib.metadata.version("minigun-soren-n")

__all__ = [
    "Conj",
    "Discard",
    "Neg",
    "Prop",
    "Spec",
    "SpecificationError",
    "__version__",
    "assume",
    "check",
    "conj",
    "context",
    "discard",
    "generate",
    "neg",
    "prop",
]
