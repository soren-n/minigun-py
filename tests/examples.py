"""The tutorial examples, run as specifications.

Every file under docs/examples exports a ``spec``; each is evaluated here
so the tutorial cannot drift from the library.
"""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import minigun.specify as sp
from minigun import check
from minigun.specify import Spec, conj, prop

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "examples"


def _load(name: str) -> sp.Spec:
    path = EXAMPLES / f"{name}.py"
    qualified = f"minigun_examples.{name}"
    module_spec = importlib.util.spec_from_file_location(qualified, path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"Cannot load example {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[qualified] = module
    module_spec.loader.exec_module(module)
    spec = module.spec
    if not sp.is_spec(spec):
        raise TypeError(f"Example {name} does not export a specification")
    return spec


def _holds(spec: sp.Spec, seed: int, attempts: int) -> bool:
    with contextlib.redirect_stdout(io.StringIO()):
        return sp.evaluate(
            seed,
            spec,
            lambda resolved: sp.Allowance(attempts),
            lambda p: None,
            lambda outcome: None,
        )


def _example(name: str, attempts: int = 30) -> Spec:
    @prop(f"example {name} holds")
    def _runs(seed: int) -> bool:
        return _holds(_load(name), seed, attempts)

    return _runs


@prop("every example file is covered by a property")
def _all_covered(seed: int) -> bool:
    files = {path.stem for path in EXAMPLES.glob("*.py")}
    return files == set(_NAMES)


_NAMES = [
    "basic",
    "lists",
    "composition",
    "templates",
    "refine_map",
    "refine_bind",
    "refine_choice",
    "custom_generator",
    "modeling",
    "nondeterminism",
    "fixtures",
    "programmatic",
]

spec = conj(_all_covered, *[_example(name) for name in _NAMES])


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
