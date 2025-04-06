from typing import Any
from builtins import (
    bool as _bool,
    float as _float,
    int as _int,
    list as _list,
    tuple as _tuple
)

type State = _tuple[Any, ...]

def seed(value: _int | None = None) -> State: ...

def bool(state: State) -> _tuple[State, _bool]: ...

def nat(
    state: State,
    lower_bound: _int,
    upper_bound: _int
    ) -> _tuple[State, _int]: ...

def int(
    state: State,
    lower_bound: _int,
    upper_bound: _int
    ) -> _tuple[State, _int]: ...

def probability(state: State) -> _tuple[State, _float]: ...

def float(
    state: State,
    lower_bound: _float,
    upper_bound: _float
    ) -> _tuple[State, _float]: ...

def weighted_choice[T](
    state: State,
    weights: _list[_int],
    choices: _list[T]
    ) -> _tuple[State, T]: ...

def choice[T](
    state: State,
    choices: _list[T]
    ) -> tuple[State, T]: ...
