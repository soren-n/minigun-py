from dataclasses import dataclass
from typing import Any, Callable
from pathlib import Path

from returns.maybe import Maybe

from . import (
    domain as d,
    generate as g,
    pretty as p
)

@dataclass
class Spec: ...

@dataclass
class _Prop[**P](Spec):
    desc: str
    attempts: int
    law: Callable[P, bool]
    ordering: list[str]
    generators: dict[str, Maybe[g.Generator[Any]]]
    printers: dict[str, Maybe[p.Printer[Any]]]

def prop[**P](desc: str) -> Callable[[Callable[P, bool]], Spec]: ...

@dataclass
class _Neg(Spec):
    spec: Spec

def neg(spec: Spec) -> Spec: ...

@dataclass
class _Conj(Spec):
    specs: tuple[Spec, ...]

def conj(*specs: Spec) -> Spec: ...

@dataclass
class _Disj(Spec):
    specs: tuple[Spec, ...]

def disj(*specs: Spec) -> Spec: ...

@dataclass
class _Impl(Spec):
    premise: Spec
    conclusion: Spec

def impl(premise: Spec, conclusion: Spec) -> Spec: ...

def context(
    *lparams: d.Domain[Any],
    **kparams: d.Domain[Any]
    ) -> Callable[[Spec], Spec]: ...

def temporary_path(dir_path: Path | None = None) -> Path: ...

def permanent_path(dir_path: Path | None = None) -> Path: ...

def check(spec: Spec) -> bool: ...
