"""Refining generators with bind: directed graphs of a drawn size."""

import minigun.generate as g
from minigun import check
from minigun.specify import context, prop


# -- start: generators --
def sized_directed_graph(size: int) -> g.Generator[dict[int, list[int]]]:
    def _impl(graph_data: list[list[bool]]) -> dict[int, list[int]]:
        result: dict[int, list[int]] = {}
        for src_index, row_data in enumerate(graph_data):
            result[src_index] = []
            for dst_index, column_data in enumerate(row_data):
                if not column_data:
                    continue
                result[src_index].append(dst_index)
        return result

    return g.map(
        _impl,
        g.bounded_lists(size, size, g.bounded_lists(size, size, g.bools())),
    )


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
