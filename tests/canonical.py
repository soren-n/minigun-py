"""Properties of canonical text."""

import base64
import dataclasses
import os
import pickle
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

import minigun.arbitrary as a
import minigun.canonical as cn
import minigun.generate as g
from minigun import check
from minigun.parallel import Shown
from minigun.specify import conj, context, prop
from tests._support import Program, interpret, programs


def _has_set(value: Any) -> bool:
    if isinstance(value, (set, frozenset)):
        return True
    if isinstance(value, (list, tuple)):
        return any(_has_set(item) for item in value)
    if isinstance(value, dict):
        return any(_has_set(k) or _has_set(v) for k, v in value.items())
    return False


def _draw(program: Program, seed: int) -> Any:
    dissection = interpret(program).sample(a.seed(seed))
    return None if dissection is None else dissection.head


@context(programs(), g.ints())
@prop("the canonical text of a value without sets is its repr")
def _repr(program: Program, seed: int) -> bool:
    value = _draw(program, seed)
    return _has_set(value) or cn.text(value) == repr(value)


def _rebuilt(value: Any) -> Any:
    """The value with every set built again in the reverse order."""
    if isinstance(value, (set, frozenset)):
        items = [_rebuilt(item) for item in reversed(list(value))]
        return type(value)(items)
    if isinstance(value, list):
        return [_rebuilt(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_rebuilt(item) for item in value)
    if isinstance(value, dict):
        return {_rebuilt(k): _rebuilt(v) for k, v in value.items()}
    return value


@context(programs(), g.ints())
@prop("the canonical text of a value does not depend on how its sets grew")
def _order(program: Program, seed: int) -> bool:
    value = _draw(program, seed)
    return cn.text(value) == cn.text(_rebuilt(value))


_ROOT = Path(__file__).resolve().parent.parent

_CHILD = """
import base64, pickle, sys
import minigun.arbitrary as a
import minigun.canonical as cn
from tests._support import interpret
program, seed = pickle.loads(base64.b64decode(sys.argv[1]))
dissection = interpret(program).sample(a.seed(seed))
print(cn.text(None if dissection is None else dissection.head), end="")
"""


# A process takes a few hundred milliseconds to start, so few attempts.
@context(programs(), g.ints(), g.int_range(1, 2**32 - 1))
@prop(
    "a value drawn again in another process has the same canonical text",
    attempts=4,
)
def _processes(program: Program, seed: int, hash_seed: int) -> bool:
    argument = base64.b64encode(pickle.dumps((program, seed))).decode()
    child = subprocess.run(
        [sys.executable, "-c", _CHILD, argument],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=_ROOT,
        env={**os.environ, "PYTHONHASHSEED": str(hash_seed)},
        check=True,
    )
    return child.stdout == cn.text(_draw(program, seed))


@context(g.lists(g.strings()), g.lists(g.ints()))
@prop("sets and frozensets show their elements ordered by canonical text")
def _sets(words: list[str], numbers: list[int]) -> bool:
    for items in (set(words), set(numbers)):
        inner = ", ".join(sorted(repr(item) for item in items))
        if cn.text(items) != (f"{{{inner}}}" if items else "set()"):
            return False
        frozen = frozenset(items)
        expected = f"frozenset({{{inner}}})" if items else "frozenset()"
        if cn.text(frozen) != expected:
            return False

    class Tags(frozenset[int]):
        pass

    tagged = Tags(numbers)
    inner = ", ".join(sorted(repr(item) for item in tagged))
    return cn.text(tagged) == f"Tags({{{inner}}})"


class _Pair(NamedTuple):
    left: Any
    right: Any


@dataclasses.dataclass
class _Record:
    shown: Any
    hidden: Any = dataclasses.field(repr=False)


@dataclasses.dataclass
class _Custom:
    value: Any

    def __repr__(self) -> str:
        return "custom"


class _Derived(_Record):
    pass


class _Overriding(_Record):
    def __repr__(self) -> str:
        return "overriding"


@context(g.sets(g.strings()), g.ints())
@prop("named tuples and dataclasses show their fields as canonical text")
def _records(items: set[str], number: int) -> bool:
    inner = cn.text(items)
    return (
        cn.text(_Pair(items, number)) == f"_Pair(left={inner}, right={number})"
        and cn.text(_Record(items, number)) == f"_Record(shown={inner})"
        and cn.text(_Derived(items, number)) == f"_Derived(shown={inner})"
        and cn.text(_Custom(items)) == "custom"
        and cn.text(_Overriding(items, number)) == "overriding"
        and cn.text((items,)) == f"({inner},)"
        and cn.text([items, number]) == f"[{inner}, {number}]"
        and cn.text({number: items}) == f"{{{number}: {inner}}}"
    )


@dataclasses.dataclass
class _Node:
    value: Any
    link: Any = None


@context(programs(), g.ints())
@prop(
    "a value containing itself is shown as repr shows it, a shared one in full"
)
def _cycles(program: Program, seed: int) -> bool:
    value = _draw(program, seed)
    inner = cn.text(value)
    cyclic: list[Any] = [value]
    cyclic.append(cyclic)
    table: dict[str, Any] = {"v": value}
    table["me"] = table
    node = _Node(value)
    node.link = node
    shared = [value, value]
    return (
        cn.text(cyclic) == f"[{inner}, [...]]"
        and cn.text(table) == f"{{'v': {inner}, 'me': {{...}}}}"
        and cn.text(node) == f"_Node(value={inner}, link=...)"
        and cn.text((cyclic,)) == f"([{inner}, [...]],)"
        and cn.text([shared, shared])
        == f"[[{inner}, {inner}], [{inner}, {inner}]]"
    )


class _Fielded:
    """Not a tuple, though it has fields like a named tuple's."""

    _fields = ("a",)

    def __repr__(self) -> str:
        return "fielded"


@prop("only tuples are shown as named tuples")
def _fielded(seed: int) -> bool:
    return cn.text(_Fielded()) == "fielded"


@context(g.ints(), g.int_range(1, 5))
@prop("a random source shows a digest of its state")
def _rngs(seed: int, draws: int) -> bool:
    rng = random.Random(seed)
    same = random.Random(seed)
    before = cn.text(rng)
    for _ in range(draws):
        rng.random()
    return (
        before == cn.text(same)
        and before.startswith("random.Random(state=")
        and cn.text(rng) != before
    )


@context(programs(), g.ints())
@prop("addresses are elided and canonical text is its own canonical text")
def _addresses(program: Program, seed: int) -> bool:
    value = _draw(program, seed)
    marker = object()
    return (
        cn.text(marker) == "<object object at ...>"
        and cn.text([marker]) == "[<object object at ...>]"
        and cn.text(Shown(cn.text(value))) == cn.text(value)
    )


spec = conj(
    _repr,
    _order,
    _processes,
    _sets,
    _records,
    _fielded,
    _cycles,
    _rngs,
    _addresses,
)


if __name__ == "__main__":
    sys.exit(0 if check(spec) else 1)
