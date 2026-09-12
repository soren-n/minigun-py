"""Nondeterminism: random interleavings of concurrent clients."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import minigun.arbitrary as a
import minigun.cardinality as c
import minigun.generate as g
import minigun.shrink as s
import minigun.stream as fs
from minigun import check
from minigun.specify import Spec, context, prop


# -- start: operations --
@dataclass
class Increment:
    client: int


@dataclass
class Decrement:
    client: int


@dataclass
class Read:
    client: int


type CounterOp = Increment | Decrement | Read
type CounterProg = list[CounterOp]


# Reference model
def model_counter(prog: CounterProg) -> list[int]:
    state = 0
    reads: list[int] = []
    for op in prog:
        match op:
            case Increment():
                state += 1
            case Decrement():
                state -= 1
            case Read():
                reads.append(state)
    return reads


# -- end: operations --


# -- start: generator --
def interleavings(
    num_clients: int, ops_per_client: int
) -> g.Generator[CounterProg]:
    def _trim(prog: CounterProg) -> fs.Stream[CounterProg]:
        def _iterate() -> Iterator[CounterProg]:
            for index in range(len(prog) - 1, -1, -1):
                yield prog[:index] + prog[index + 1 :]

        return _iterate

    def _sample(rng: a.Rng) -> s.Dissection[CounterProg] | None:
        # Build per-client operation sequences
        queues: list[CounterProg] = []
        for client in range(num_clients):
            ops: CounterProg = []
            for _ in range(ops_per_client):
                match a.choice(rng, ["inc", "dec", "read"]):
                    case "inc":
                        ops.append(Increment(client))
                    case "dec":
                        ops.append(Decrement(client))
                    case _:
                        ops.append(Read(client))
            queues.append(ops)

        # Randomly interleave the queues
        prog: CounterProg = []
        indices = [0] * num_clients
        for _ in range(num_clients * ops_per_client):
            active = [
                client
                for client in range(num_clients)
                if indices[client] < len(queues[client])
            ]
            client = a.choice(rng, active)
            prog.append(queues[client][indices[client]])
            indices[client] += 1

        return s.unfold(prog, _trim)

    return g.Generator(_sample, c.INFINITE)


# -- end: generator --


# -- start: property --
def counter_spec(impl_counter: Callable[[CounterProg], list[int]]) -> Spec:
    @context(
        g.bind(
            lambda n: g.bind(lambda m: interleavings(n, m), g.small_nats()),
            g.small_nats(),
        )
    )
    @prop("Counter is consistent under any interleaving")
    def _counter_consistent(prog: CounterProg) -> bool:
        return model_counter(prog) == impl_counter(prog)

    return _counter_consistent


# -- end: property --


def _impl_counter(prog: CounterProg) -> list[int]:
    """An implementation under test; here it happens to be correct."""
    total = 0
    reads: list[int] = []
    for op in prog:
        if isinstance(op, Increment):
            total += 1
        elif isinstance(op, Decrement):
            total -= 1
        else:
            reads.append(total)
    return reads


spec = counter_spec(_impl_counter)

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
