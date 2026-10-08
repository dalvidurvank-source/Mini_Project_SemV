"""Dijkstra shortest paths for a pre-filtered AgroLink logistics graph.

Build the supplied graph from the origin, buyer, and only the hubs returned
by ``HubEvaluationBatch.feasible_results``. This module treats its graph as
already perishability-filtered and does not re-evaluate shelf life.
"""

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from math import inf, isclose, isfinite
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Edge:
    """A directed graph edge with distance and transport-cost components."""

    target: str
    distance: float
    transport_cost: float


@dataclass(frozen=True)
class RouteStep:
    """The component costs and composite weight for one path edge."""

    source: str
    target: str
    distance: float
    transport_cost: float
    composite_cost: float


@dataclass(frozen=True)
class DijkstraResult:
    """Shortest-path output; unreachable destinations have an empty path."""

    path: tuple[str, ...]
    total_composite_cost: float
    edges: tuple[RouteStep, ...]

    @property
    def reachable(self) -> bool:
        """Whether the destination was reached from the source."""
        return bool(self.path)


WeightedGraph = Mapping[str, Sequence[Edge]]


def _validate_weights(alpha: float, beta: float) -> None:
    if not isfinite(alpha) or not isfinite(beta):
        raise ValueError("alpha and beta must be finite numbers.")
    if alpha < 0.0 or beta < 0.0:
        raise ValueError("alpha and beta must be non-negative.")
    if not isclose(alpha + beta, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("alpha and beta must sum to 1.")


def _edge_cost(edge: Edge, alpha: float, beta: float) -> float:
    if not isfinite(edge.distance) or edge.distance < 0.0:
        raise ValueError("Edge distance must be finite and non-negative.")
    if not isfinite(edge.transport_cost) or edge.transport_cost < 0.0:
        raise ValueError("Edge transport cost must be finite and non-negative.")

    composite_cost = alpha * edge.distance + beta * edge.transport_cost
    if not isfinite(composite_cost) or composite_cost < 0.0:
        raise ValueError("Dijkstra requires finite, non-negative edge weights.")
    return composite_cost


def dijkstra_shortest_path(
    graph: WeightedGraph,
    source: str,
    destination: str,
    alpha: float = 0.5,
    beta: float = 0.5,
) -> DijkstraResult:
    """Find a minimum-composite-cost path in a feasible-hub subgraph.

    Each directed edge weight is ``alpha * distance + beta * transport_cost``.
    All graph nodes, including nodes with no outgoing edges, must be mapping
    keys. An unreachable destination returns an empty path and infinite cost.

    The caller is responsible for constructing ``graph`` using only feasible
    hubs; that lets later integration consume ``feasible_results`` without
    coupling route search to shelf-life or hub-selection implementation.
    """
    _validate_weights(alpha, beta)
    if not graph:
        raise ValueError("Cannot search an empty graph.")
    if source not in graph:
        raise ValueError(f"Source node {source!r} is not in the graph.")
    if destination not in graph:
        raise ValueError(f"Destination node {destination!r} is not in the graph.")

    edge_costs: dict[tuple[str, int], float] = {}
    for node, edges in graph.items():
        for edge_index, edge in enumerate(edges):
            if edge.target not in graph:
                raise ValueError(
                    f"Edge from {node!r} targets unknown node {edge.target!r}."
                )
            edge_costs[(node, edge_index)] = _edge_cost(edge, alpha, beta)

    distances = {node: inf for node in graph}
    predecessors: dict[str, tuple[str, Edge, float]] = {}
    distances[source] = 0.0

    queue_sequence = count()
    priority_queue: list[tuple[float, int, str]] = [
        (0.0, next(queue_sequence), source)
    ]

    while priority_queue:
        current_cost, _, current_node = heappop(priority_queue)
        if current_cost > distances[current_node]:
            continue
        if current_node == destination:
            break

        for edge_index, edge in enumerate(graph[current_node]):
            edge_cost = edge_costs[(current_node, edge_index)]
            proposed_cost = current_cost + edge_cost
            if proposed_cost < distances[edge.target]:
                distances[edge.target] = proposed_cost
                predecessors[edge.target] = (current_node, edge, edge_cost)
                heappush(
                    priority_queue,
                    (proposed_cost, next(queue_sequence), edge.target),
                )

    if distances[destination] == inf:
        return DijkstraResult(path=(), total_composite_cost=inf, edges=())

    reversed_nodes = [destination]
    reversed_steps: list[RouteStep] = []
    current_node = destination
    while current_node != source:
        previous_node, edge, edge_cost = predecessors[current_node]
        reversed_steps.append(
            RouteStep(
                source=previous_node,
                target=current_node,
                distance=edge.distance,
                transport_cost=edge.transport_cost,
                composite_cost=edge_cost,
            )
        )
        current_node = previous_node
        reversed_nodes.append(current_node)

    return DijkstraResult(
        path=tuple(reversed(reversed_nodes)),
        total_composite_cost=distances[destination],
        edges=tuple(reversed(reversed_steps)),
    )