"""
Mutation testing of minigun's own test suite.

Each mutant changes one operator or constant in one function of the core
modules: comparisons are swapped (``<`` and ``<=``, ``==`` and ``!=``, ...),
``and`` and ``or`` exchanged, arithmetic operators replaced, ``not``
dropped, booleans flipped and numbers incremented. A mutant is killed when
the test modules chosen for its file fail, crash or time out; a mutant
that survives marks behavior no test pins down, or a change nothing can
observe (an equivalent mutant), which only reading it can tell apart.

Mutants run in copies of the repository under ``--out``, several at once,
each with a fixed seed and time budget. Because minigun tests itself, a
mutant also changes the harness running the tests: a broken generator
draws the tests' own arguments, so a test can pass by never seeing the
inputs the mutant gets wrong. Survivors are best read with that in mind.

Run from the repository root, so the copies import this checkout::

    uv run python scripts/mutate.py --out /tmp/mutants
    uv run python scripts/mutate.py --out /tmp/mutants --files search shrink

Results are written to ``--out/results.json`` and survivors are printed
with their source lines.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Target:
    """A module to mutate.

    :param functions: The functions whose bodies are mutated, or None for
        the whole module.
    :param modules: The test modules run against each mutant.
    """

    functions: frozenset[str] | None
    modules: tuple[str, ...]


TARGETS: dict[str, Target] = {
    "search": Target(
        frozenset(
            {"assume", "_evaluate", "_same_failure", "_trim"}
            | {"find_counter_example"}
        ),
        ("search", "specify"),
    ),
    "shrink": Target(
        frozenset(
            {"integer", "floating", "chunk_removals", "filter", "map"}
            | {"unfold", "append", "prepend", "string", "boolean"}
        ),
        ("shrink", "search", "algebra"),
    ),
    "budget": Target(
        frozenset(
            {"attempt_limit", "baseline_attempts", "coverage_attempts"}
            | {"share", "_limit"}
            | {"plan", "__init__", "allowance"}
        ),
        ("budget", "orchestrator", "specify"),
    ),
    "specify": Target(
        frozenset(
            {"_judge", "evaluate", "resolve_all", "resolve", "context"}
            | {"prop", "collect", "property_rng"}
        ),
        ("specify", "orchestrator", "algebra"),
    ),
    "orchestrator": Target(
        frozenset({"_resolve_modules", "check", "run", "__post_init__"}),
        ("orchestrator", "specify", "cli"),
    ),
    "generate": Target(
        frozenset(
            {"float_range", "_draw_tiny", "dates", "datetimes", "int_range"}
            | {"nonzero_int_range", "_sized_cardinality", "optional"}
            | {"_sequence_dissection", "_draw_tiered", "_tiered_int"}
            | {"filter", "bind", "map", "strings", "bounded_strings"}
            | {"_check_bounds", "_check_alphabet", "_draw_list", "_draw_dict"}
            | {"_draw_set", "one_of", "subset_of", "weighted_choice"}
            | {"choice", "biased_bool", "infer", "_optional_inner", "lazy"}
            | {"_unsized", "floats"}
        ),
        ("generate", "algebra"),
    ),
    "arbitrary": Target(
        frozenset(
            {"draw_int", "draw_float", "choice", "weighted_choice", "fork"}
            | {"seed", "draw_bool", "probability"}
        ),
        ("arbitrary", "generate"),
    ),
    "cardinality": Target(None, ("cardinality", "generate")),
    "stream": Target(None, ("stream", "shrink")),
}

_SWAP_COMPARE: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

_SWAP_ARITHMETIC: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
    ast.Pow: ast.Mult,
}


###############################################################################
# Mutation
###############################################################################
class _Mutator(ast.NodeTransformer):
    """Numbers the mutation sites of a module; applies the one numbered
    ``target`` (none when negative)."""

    def __init__(self, functions: frozenset[str] | None, target: int = -1):
        self.functions = functions
        self.target = target
        self.count = 0
        self.applied: tuple[int, str] | None = None
        self._stack: list[str] = []
        self._docstrings: set[int] = set()

    def _site(self, node: ast.AST, description: str) -> bool:
        active = self.functions is None or any(
            name in self.functions for name in self._stack
        )
        if not active:
            return False
        index = self.count
        self.count += 1
        if index != self.target:
            return False
        self.applied = (getattr(node, "lineno", 0), description)
        return True

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(
            first.value, ast.Constant
        ):
            self._docstrings.add(id(first.value))
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        for index, op in enumerate(node.ops):
            new = _SWAP_COMPARE.get(type(op))
            if new is not None and self._site(
                node, f"{type(op).__name__} -> {new.__name__}"
            ):
                node.ops[index] = new()
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        new: type[ast.boolop] = (
            ast.Or if isinstance(node.op, ast.And) else ast.And
        )
        if self._site(node, f"{type(node.op).__name__} -> {new.__name__}"):
            node.op = new()
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        new = _SWAP_ARITHMETIC.get(type(node.op))
        if new is not None and self._site(
            node, f"{type(node.op).__name__} -> {new.__name__}"
        ):
            node.op = new()
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._site(node, "drop not"):
            return node.operand
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if id(node) in self._docstrings:
            return node
        value = node.value
        if isinstance(value, bool):
            if self._site(node, f"{value} -> {not value}"):
                return ast.copy_location(ast.Constant(not value), node)
        elif isinstance(value, int | float):
            if self._site(node, f"{value} -> {value + 1}"):
                return ast.copy_location(ast.Constant(value + 1), node)
        return node


def _source(name: str) -> str:
    return (REPO / "minigun" / f"{name}.py").read_text()


def count_sites(name: str) -> int:
    """The number of mutants of a target module."""
    mutator = _Mutator(TARGETS[name].functions)
    mutator.visit(ast.parse(_source(name)))
    return mutator.count


def mutant(name: str, index: int) -> tuple[str, int, str]:
    """The source of a target module with mutation ``index`` applied.

    :return: The source, and the line and description of the mutation.
    """
    mutator = _Mutator(TARGETS[name].functions, index)
    tree = ast.fix_missing_locations(mutator.visit(ast.parse(_source(name))))
    if mutator.applied is None:
        raise IndexError(f"{name} has no mutation {index}")
    line, description = mutator.applied
    return ast.unparse(tree), line, description


###############################################################################
# Running
###############################################################################
@dataclass(frozen=True)
class Result:
    """The fate of one mutant."""

    module: str
    index: int
    line: int
    mutation: str
    status: str


def _copy(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    ignore = shutil.ignore_patterns(
        ".venv", ".git", "dist", "__pycache__", ".minigun", "docs"
    )
    shutil.copytree(REPO, root, ignore=ignore)
    shutil.copytree(REPO / "docs" / "examples", root / "docs" / "examples")


def _run_tests(
    root: Path, modules: tuple[str, ...], budget: float, seed: int
) -> str:
    """Run test modules in a copy: "pass", "fail" or "timeout"."""
    command = [
        sys.executable,
        "-m",
        "minigun.cli",
        "--time-budget",
        str(budget),
        "--seed",
        str(seed),
        "--output",
        "quiet",
        "--modules",
        *modules,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=dict(os.environ, PYTHONPATH=str(root)),
            capture_output=True,
            timeout=budget * 8 + 30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    return "pass" if result.returncode == 0 else "fail"


def _worker(
    root: Path, jobs: list[tuple[str, int]], budget: float, seed: int
) -> list[Result]:
    results = []
    for name, index in jobs:
        source, line, description = mutant(name, index)
        path = root / "minigun" / f"{name}.py"
        path.write_text(source)
        try:
            status = _run_tests(root, TARGETS[name].modules, budget, seed)
        finally:
            path.write_text(_source(name))
        result = Result(name, index, line, description, status)
        print(json.dumps(asdict(result)), flush=True)
        results.append(result)
    return results


def _report(results: list[Result]) -> None:
    print()
    for name in TARGETS:
        own = [r for r in results if r.module == name]
        if own:
            killed = sum(r.status != "pass" for r in own)
            print(f"{name:14} {killed:4}/{len(own)} killed")
    killed = sum(r.status != "pass" for r in results)
    print(f"{'total':14} {killed:4}/{len(results)} killed")
    survivors = [r for r in results if r.status == "pass"]
    if not survivors:
        return
    print("\nSurvivors:")
    lines = {name: _source(name).splitlines() for name in TARGETS}
    for r in sorted(survivors, key=lambda r: (r.module, r.line)):
        text = lines[r.module][r.line - 1].strip()[:70]
        print(f"  {r.module}.py:{r.line:<5} {r.mutation:24} | {text}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--files", nargs="+", choices=list(TARGETS))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--budget", type=float, default=4.0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    out: Path = args.out.resolve()
    if out.is_relative_to(REPO):
        parser.error("--out must lie outside the repository")
    names: list[str] = args.files or list(TARGETS)
    roots = [out / f"worker{i}" for i in range(args.workers)]
    for root in roots:
        _copy(root)

    # Every target's tests must pass unmutated, or no mutant means anything.
    for name in names:
        modules = TARGETS[name].modules
        if _run_tests(roots[0], modules, args.budget, args.seed) != "pass":
            sys.exit(f"The tests of {name} fail without mutation")

    jobs = [(name, i) for name in names for i in range(count_sites(name))]
    shares = [jobs[w :: args.workers] for w in range(args.workers)]
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = [
            pool.submit(_worker, root, share, args.budget, args.seed)
            for root, share in zip(roots, shares, strict=True)
        ]
        results = [r for future in futures for r in future.result()]

    (out / "results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=1)
    )
    _report(results)


if __name__ == "__main__":
    main()
