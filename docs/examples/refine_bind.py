"""Refining generators with bind: directed graphs of a drawn size."""

import minigun.generate as g
from minigun import check
from minigun.specify import context, prop


# -- start: generators --
def sized_directed_graph(size: int) -> g.Generator[dict[int, list[int]]]:
    def _graph(matrix: list[list[bool]]) -> dict[int, list[int]]:
        """Node ``src`` has an edge to ``dst`` where ``matrix[src][dst]``."""
        return {
            src: [dst for dst, edge in enumerate(row) if edge]
            for src, row in enumerate(matrix)
        }

    row = g.bounded_lists(size, size, g.bools())
    return g.map(_graph, g.bounded_lists(size, size, row))


def directed_graph() -> g.Generator[dict[int, list[int]]]:
    return g.bind(sized_directed_graph, g.small_nats())


# -- end: generators --


@context(directed_graph())
@prop("Every edge of a directed graph points at a node of the graph")
def _edges_are_nodes(graph: dict[int, list[int]]) -> bool:
    return all(dst in graph for edges in graph.values() for dst in edges)


spec = _edges_are_nodes

if __name__ == "__main__":
    import sys

    sys.exit(0 if check(spec) else 1)
