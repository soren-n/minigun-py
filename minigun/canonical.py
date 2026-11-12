"""
Canonical text of values

``text`` renders a value like ``repr``, except that the parts of a
``repr`` that depend on the process rather than on the value are made
stable: set elements are ordered by their own text instead of by hash
(string hashes are salted per process), a ``random.Random`` is shown by
a digest of its state, and memory addresses are elided. The same value
drawn in two processes therefore has the same text, which is what lets
a regressions file recognise that a recorded draw still draws what it
drew when it was recorded.

Lists, tuples, dicts, named tuples and dataclass instances are rendered
element by element so the elements' own text is canonical too. Dicts
keep their insertion order, which a generator decides like any other
part of the value. Anything else is its ``repr`` with addresses elided,
so a type whose ``repr`` shows other per-process state still renders
differently between processes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import random
import re
from typing import Any

__all__ = ["text"]

_ADDRESS = re.compile(r" at 0x[0-9A-Fa-f]+")


def _state_digest(rng: random.Random) -> str:
    state = repr(rng.getstate()).encode("ascii")
    return hashlib.sha256(state).hexdigest()[:16]


def text(value: Any) -> str:
    """The canonical text of a value: its ``repr``, made the same in
    every process for the same value. A container that contains itself
    is shown, where it recurs, as ``repr`` shows it: ``[...]``, ``{...}``
    or ``...``."""
    return _text(value, set())


#: What a container shows where it contains itself, as ``repr`` does.
_RECURRING: dict[type, str] = {list: "[...]", dict: "{...}"}


def _text(value: Any, active: set[int]) -> str:
    """``text``, with ``active`` the ids of the containers being shown
    around the value."""
    kind = type(value)
    if kind is random.Random:
        return f"random.Random(state={_state_digest(value)})"
    rendered = _container(value, kind, active)
    if rendered is not None:
        return rendered
    return _ADDRESS.sub(" at ...", repr(value))


def _container(value: Any, kind: type, active: set[int]) -> str | None:
    """The text of a container shown element by element, or None for a
    value that is not one."""
    named_tuple = isinstance(value, tuple) and hasattr(kind, "_fields")
    if not (
        isinstance(value, (set, frozenset))
        or kind in (list, tuple, dict)
        or named_tuple
        or _generated_repr(kind)
    ):
        return None
    if id(value) in active:
        return _RECURRING.get(kind, "...")
    active.add(id(value))
    try:
        return _elements(value, kind, named_tuple, active)
    finally:
        active.discard(id(value))


def _elements(
    value: Any, kind: type, named_tuple: bool, active: set[int]
) -> str:
    def _items(values: Any) -> str:
        return ", ".join(_text(item, active) for item in values)

    def _fields(name: str, pairs: list[tuple[str, Any]]) -> str:
        inner = ", ".join(
            f"{field}={_text(item, active)}" for field, item in pairs
        )
        return f"{name}({inner})"

    if isinstance(value, (set, frozenset)):
        elements = ", ".join(sorted(_text(item, active) for item in value))
        if kind is set:
            return f"{{{elements}}}" if value else "set()"
        if kind is frozenset:
            return f"frozenset({{{elements}}})" if value else "frozenset()"
        return f"{kind.__name__}({{{elements}}})"
    if kind is list:
        return f"[{_items(value)}]"
    if kind is tuple:
        if len(value) == 1:
            return f"({_text(value[0], active)},)"
        return f"({_items(value)})"
    if named_tuple:
        names: tuple[str, ...] = value._fields
        return _fields(kind.__name__, list(zip(names, value, strict=True)))
    if kind is dict:
        inner = ", ".join(
            f"{_text(key, active)}: {_text(item, active)}"
            for key, item in value.items()
        )
        return f"{{{inner}}}"
    return _fields(
        kind.__qualname__,
        [
            (field.name, getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.repr
        ],
    )


def _generated_repr(kind: type) -> bool:
    """Whether a class's ``repr`` is one dataclasses generated: the class
    that defines it is a dataclass with ``repr=True``, and the method is
    not one the class defines itself, which dataclasses keeps."""
    for base in kind.__mro__:
        method = base.__dict__.get("__repr__")
        if method is not None:
            params = base.__dict__.get("__dataclass_params__")
            # The generated method is wrapped by reprlib.recursive_repr.
            wrapped = getattr(method, "__wrapped__", None)
            return (
                params is not None
                and bool(params.repr)
                and "__create_fn__" in getattr(wrapped, "__qualname__", "")
            )
    return False
