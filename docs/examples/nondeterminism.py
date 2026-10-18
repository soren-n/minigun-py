"""Nondeterminism: replicas that converge under any delivery order."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import minigun.generate as g
from minigun import check
from minigun.specify import Spec, context, prop

#: The number of replicas in the simulated network.
NODES = 3


# -- start: replica --
@dataclass(frozen=True)
class Message:
    time: int
    sender: int
    value: int


class Replica:
    """A last-writer-wins register: of all writes it has seen, a replica
    holds the one with the latest time, the writing node breaking ties."""

    def __init__(self, node: int) -> None:
        self.node = node
        self.stamp = (-1, -1)
        self.value: int | None = None

    def write(self, value: int, time: int) -> Message:
        message = Message(time, self.node, value)
        self.receive(message)
        return message

    def receive(self, message: Message) -> None:
        stamp = (message.time, message.sender)
        if stamp > self.stamp:
            self.stamp = stamp
            self.value = message.value


class RacyReplica(Replica):
    """Compares times only, so of two writes at the same time the one
    that arrives last wins."""

    def receive(self, message: Message) -> None:
        if message.time >= self.stamp[0]:
            self.stamp = (message.time, message.sender)
            self.value = message.value


# -- end: replica --


# -- start: events --
@dataclass(frozen=True)
class Write:
    node: int
    value: int
    time: int


@dataclass(frozen=True)
class Receive:
    node: int
    sender: int


type Event = Write | Receive
# -- end: events --


# -- start: simulation --
def simulate(
    replica: Callable[[int], Replica], events: list[Event]
) -> list[int | None]:
    """Run events against replicas joined by first-in first-out channels,
    then deliver every message still in flight; the replicas' values."""
    replicas = [replica(node) for node in range(NODES)]
    channels: dict[tuple[int, int], deque[Message]] = {
        (sender, receiver): deque()
        for sender in range(NODES)
        for receiver in range(NODES)
        if sender != receiver
    }
    for event in events:
        match event:
            case Write(node, value, time):
                message = replicas[node].write(value, time)
                for receiver in range(NODES):
                    if receiver != node:
                        channels[node, receiver].append(message)
            case Receive(node, sender):
                # Receiving from an empty channel is waiting: nothing yet.
                if channels[sender, node]:
                    replicas[node].receive(channels[sender, node].popleft())
    for (_, receiver), channel in channels.items():
        while channel:
            replicas[receiver].receive(channel.popleft())
    return [replica.value for replica in replicas]


# -- end: simulation --


# -- start: generator --
def node_events(node: int) -> g.Generator[list[Event]]:
    """What one node does: write values at times on a coarse clock, and
    receive from the others."""
    senders = [sender for sender in range(NODES) if sender != node]
    event: g.Generator[Event] = g.choice(
        g.map(partial(Write, node), g.small_nats(), g.int_range(0, 9)),
        g.map(partial(Receive, node), g.one_of(senders)),
    )
    return g.lists(event)


def schedules() -> g.Generator[list[Event]]:
    return g.interleave(*[node_events(node) for node in range(NODES)])


# -- end: generator --


# -- start: property --
def converges(desc: str, replica: Callable[[int], Replica]) -> Spec:
    @context(schedules())
    @prop(desc)
    def _converges(events: list[Event]) -> bool:
        values = simulate(replica, events)
        return all(value == values[0] for value in values)

    return _converges


spec = converges("replicas converge under any delivery order", Replica)
# -- end: property --

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
