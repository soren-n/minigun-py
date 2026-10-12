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
from tests._support import isolated_fixtures

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


def _holds(
    name: str, seed: int, attempts: int, roots: list[Path] | None = None
) -> bool:
    """Load and evaluate an example under a fixture root of its own,
    removed with every fixture the example created.

    Loading happens under that root because an example may create a
    permanent artifact directory at import time.

    :param roots: Receives the fixture root used.
    """
    with isolated_fixtures() as root:
        if roots is not None:
            roots.append(root)
        with contextlib.redirect_stdout(io.StringIO()):
            return sp.evaluate(
                seed,
                _load(name),
                lambda resolved: sp.Allowance(attempts),
                lambda p: None,
                lambda outcome: None,
            )


def _example(name: str, attempts: int = 30) -> Spec:
    @prop(f"example {name} holds")
    def _runs(seed: int) -> bool:
        return _holds(name, seed, attempts)

    return _runs


@prop("examples leave no fixtures behind once reclaimed")
def _no_litter(seed: int) -> bool:
    roots: list[Path] = []
    _holds("fixtures", seed, 5, roots)
    return len(roots) == 1 and not roots[0].exists()


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
    "domains",
    "preconditions",
    "modeling",
    "nondeterminism",
    "fixtures",
    "programmatic",
]

spec = conj(_all_covered, _no_litter, *[_example(name) for name in _NAMES])


if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
