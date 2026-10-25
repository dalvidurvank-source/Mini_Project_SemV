"""Connect feasible hub evaluations to the Dijkstra route finder.

This module builds a small synthetic farmer-to-hub-to-buyer graph. Only hubs
from ``HubEvaluationBatch.feasible_results`` are included; all shortest-path
and composite-weight calculations are delegated to ``dijkstra.py``.
"""

from dataclasses import dataclass
from typing import Mapping

from .dijkstra import DijkstraResult, Edge, RouteStep, WeightedGraph, dijkstra_shortest_path
from .hub_selector import (
    HANDLING_TIME_DAYS,
    REMAINING_SHELF_LIFE_DAYS,
    SAFETY_MARGIN_DAYS,
    Hub,
    HubEvaluation,
    HubEvaluationBatch,
    evaluate_hubs,
)
from .shelf_life import is_route_feasible

FARMER_NODE = "farmer"


@dataclass(frozen=True)
class HubBuyerRoute:
    """Synthetic directed edge data from a hub to the buyer."""

    distance_km: float
    transport_cost: float
    travel_time_days: float


@dataclass(frozen=True)
class CompleteRouteCandidate:
    """A selector-feasible hub evaluated with its complete transit time."""

    hub_evaluation: HubEvaluation
    buyer_route: HubBuyerRoute
    total_travel_time_days: float
    feasible: bool
    reason: str


@dataclass(frozen=True)
class RouteOptimizationResult:
    """Selected route and complete-route candidates considered by Dijkstra."""

    selected_path: tuple[str, ...]
    total_composite_cost: float
    route_steps: tuple[RouteStep, ...]
    feasible_hubs_considered: tuple[CompleteRouteCandidate, ...]
    rejected_complete_routes: tuple[CompleteRouteCandidate, ...]
    reachable: bool


# Synthetic example data only; values are simple and easy to replace.
DEMO_HUB_TO_BUYER_ROUTES: dict[str, HubBuyerRoute] = {
    "Demo Hub 2": HubBuyerRoute(
        distance_km=1200.0,
        transport_cost=1500.0,
        travel_time_days=0.5,
    ),
    "Demo Hub 3": HubBuyerRoute(
        distance_km=400.0,
        transport_cost=100.0,
        travel_time_days=0.5,
    ),
}


def _hub_node_name(hub: Hub) -> str:
    return f"hub:{hub.name}"


def build_feasible_routing_graph(
    hub_evaluations: HubEvaluationBatch,
    buyer_node: str,
    hub_to_buyer_routes: Mapping[str, HubBuyerRoute],
    remaining_shelf_life_days: float = REMAINING_SHELF_LIFE_DAYS,
    handling_time_days: float = HANDLING_TIME_DAYS,
    safety_margin_days: float = SAFETY_MARGIN_DAYS,
) -> dict[str, list[Edge]]:
    """Build a graph containing only complete-route-feasible hub paths.

    Farmer-to-hub edge distance and cost come directly from each evaluation
    and its hub. A hub-to-buyer edge is added only when the existing
    shelf-life predicate accepts the sum of both leg travel times.
    """
    if not buyer_node or buyer_node == FARMER_NODE:
        raise ValueError("Buyer node must be non-empty and distinct from farmer.")

    graph: dict[str, list[Edge]] = {FARMER_NODE: [], buyer_node: []}
    feasible_hubs = hub_evaluations.feasible_results
    hub_nodes = [_hub_node_name(result.hub) for result in feasible_hubs]
    if len(set(hub_nodes)) != len(hub_nodes):
        raise ValueError("Feasible hubs must have unique names.")
    if buyer_node in hub_nodes:
        raise ValueError("Buyer node conflicts with a feasible hub node.")

    for evaluation, hub_node in zip(feasible_hubs, hub_nodes):
        buyer_route = hub_to_buyer_routes.get(evaluation.hub.name)
        if buyer_route is not None:
            total_travel_time_days = (
                evaluation.travel_time_days + buyer_route.travel_time_days
            )
            if not is_route_feasible(
                total_travel_time_days,
                remaining_shelf_life_days,
                handling_time_days,
                safety_margin_days,
            ):
                continue

            graph[hub_node] = []
            graph[FARMER_NODE].append(
                Edge(
                    target=hub_node,
                    distance=evaluation.distance_km,
                    transport_cost=evaluation.hub.transport_cost,
                )
            )
            graph[hub_node].append(
                Edge(
                    target=buyer_node,
                    distance=buyer_route.distance_km,
                    transport_cost=buyer_route.transport_cost,
                )
            )

    return graph


def optimize_route(
    farmer_latitude: float,
    farmer_longitude: float,
    buyer_node: str,
    hub_to_buyer_routes: Mapping[str, HubBuyerRoute] = DEMO_HUB_TO_BUYER_ROUTES,
    alpha: float = 0.5,
    beta: float = 0.5,
    *,
    hub_evaluations: HubEvaluationBatch | None = None,
    hubs: list[Hub] | None = None,
    remaining_shelf_life_days: float = REMAINING_SHELF_LIFE_DAYS,
    handling_time_days: float = HANDLING_TIME_DAYS,
    safety_margin_days: float = SAFETY_MARGIN_DAYS,
) -> RouteOptimizationResult:
    """Find the minimum-composite-cost route through feasible hubs.

    If ``hub_evaluations`` is not provided, hubs are evaluated from the given
    farmer GPS coordinates. A supplied batch is treated as the selector's
    authoritative result and should correspond to those coordinates.
    """
    evaluations = hub_evaluations or evaluate_hubs(
        farmer_latitude,
        farmer_longitude,
        hubs,
    )
    candidate_routes: list[CompleteRouteCandidate] = []
    for evaluation in evaluations.feasible_results:
        buyer_route = hub_to_buyer_routes.get(evaluation.hub.name)
        if buyer_route is None:
            continue
        total_travel_time_days = evaluation.travel_time_days + buyer_route.travel_time_days
        feasible = is_route_feasible(
            total_travel_time_days,
            remaining_shelf_life_days,
            handling_time_days,
            safety_margin_days,
        )
        candidate_routes.append(
            CompleteRouteCandidate(
                hub_evaluation=evaluation,
                buyer_route=buyer_route,
                total_travel_time_days=total_travel_time_days,
                feasible=feasible,
                reason=(
                    "Complete route is feasible."
                    if feasible
                    else (
                        f"Total travel time of {total_travel_time_days:.3f} days "
                        "violates the shelf-life constraint."
                    )
                ),
            )
        )
    feasible_routes = tuple(route for route in candidate_routes if route.feasible)
    rejected_routes = tuple(route for route in candidate_routes if not route.feasible)
    graph = build_feasible_routing_graph(
        evaluations,
        buyer_node,
        hub_to_buyer_routes,
        remaining_shelf_life_days,
        handling_time_days,
        safety_margin_days,
    )
    dijkstra_result: DijkstraResult = dijkstra_shortest_path(
        graph,
        FARMER_NODE,
        buyer_node,
        alpha=alpha,
        beta=beta,
    )
    return RouteOptimizationResult(
        selected_path=dijkstra_result.path,
        total_composite_cost=dijkstra_result.total_composite_cost,
        route_steps=dijkstra_result.edges,
        feasible_hubs_considered=feasible_routes,
        rejected_complete_routes=rejected_routes,
        reachable=dijkstra_result.reachable,
    )


def print_demo() -> None:
    """Print a deterministic route-optimization example."""
    result = optimize_route(
        farmer_latitude=20.0110,
        farmer_longitude=73.7900,
        buyer_node="buyer",
    )
    print("Route optimization demo (synthetic edge data)")
    print(f"Reachable: {'Yes' if result.reachable else 'No'}")
    if not result.reachable:
        print("Buyer is unreachable from the farmer through feasible hubs.")
        return

    print(f"Selected path: {' -> '.join(result.selected_path)}")
    print(f"Total composite cost: {result.total_composite_cost:.2f}")
    print("Route steps:")
    for step in result.route_steps:
        print(
            f"- {step.source} -> {step.target}: distance={step.distance:.2f} km, "
            f"transport_cost={step.transport_cost:.2f}, "
            f"composite_cost={step.composite_cost:.2f}"
        )
    print("Feasible hubs considered:")
    for evaluation in result.feasible_hubs_considered:
        print(
            f"- {evaluation.hub_evaluation.hub.name}: "
            f"{evaluation.total_travel_time_days:.3f} days total transit"
        )
    print("Complete routes rejected by shelf life:")
    for evaluation in result.rejected_complete_routes:
        print(f"- {evaluation.hub_evaluation.hub.name}: {evaluation.reason}")


if __name__ == "__main__":
    print_demo()