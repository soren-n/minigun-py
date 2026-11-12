"""Stateful testing: a key-value store against a dict model."""

import minigun.generate as g
from minigun import check
from minigun.specify import Spec, conj, context, prop
from minigun.stateful import Machine, Program, command, machine, programs


# -- start: system --
class Store:
    """A key-value store that keeps a count of its entries."""

    def __init__(self) -> None:
        self.entries: dict[str, int] = {}
        self.count = 0

    def put(self, key: str, value: int) -> None:
        if key not in self.entries:
            self.count += 1
        self.entries[key] = value

    def get(self, key: str) -> int | None:
        return self.entries.get(key)

    def delete(self, key: str) -> None:
        del self.entries[key]
        self.count -= 1

    def size(self) -> int:
        return self.count


class LeakyStore(Store):
    """Forgets to count down when a key is deleted."""

    def delete(self, key: str) -> None:
        del self.entries[key]


# -- end: system --


# -- start: machine --
# The model is a dict that is never changed in place: each next state
# is a new dict.
type Model = dict[str, int]

KEYS = g.one_of(["a", "b", "c"])


def _put(model: Model, args: tuple[str, int]) -> Model:
    key, value = args
    return {**model, key: value}


def _delete(model: Model, key: str) -> Model:
    return {k: v for k, v in model.items() if k != key}


store: Machine[Model, Store] = machine(
    {},
    command(
        "put",
        lambda system, args: system.put(*args),
        arguments=g.tuples(KEYS, g.int_range(0, 9)),
        next_state=_put,
    ),
    command(
        "get",
        lambda system, key: system.get(key),
        arguments=KEYS,
        postcondition=lambda model, key, result: result == model.get(key),
    ),
    command(
        "delete",
        lambda system, key: system.delete(key),
        # Only keys the model holds; none to delete in an empty store.
        arguments=lambda model: g.one_of(sorted(model)) if model else None,
        precondition=lambda model, key: key in model,
        next_state=_delete,
    ),
    command(
        "size",
        lambda system, _: system.size(),
        postcondition=lambda model, _, result: result == len(model),
    ),
)
# -- end: machine --


# -- start: property --
def behaves(desc: str, make: type[Store]) -> Spec:
    @context(programs(store))
    @prop(desc)
    def _behaves(program: Program[Model, Store]) -> bool:
        return program.run(make())

    return _behaves


spec = conj(behaves("the store behaves like a dict", Store))
# -- end: property --


if __name__ == "__main__":
    check(spec)
