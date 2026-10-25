"""Run separate Dijkstra objectives over the prototype two-leg route graph.

Run from the project root with:

    python -m logistics.dijkstra_end_to_end_optimizer

The graph contains only FARMER_TEST_SPIT -> one hub -> BUYER_TEST_CHH_SAMBHAJINAGAR.
SPIT and the buyer are temporary prototype locations. No monetary cost is used.
"""

import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from .dijkstra import DijkstraResult, Edge, WeightedGraph, dijkstra_shortest_path
except ImportError:
    from logistics.dijkstra import DijkstraResult, Edge, WeightedGraph, dijkstra_shortest_path


ROAD_MATRIX_CSV = Path("data/processed/prototype_buyer_road_matrix.csv")
END_TO_END_CSV = Path("data/processed/end_to_end_route_report.csv")
OUTPUT_CSV = Path("data/processed/dijkstra_end_to_end_results.csv")
FARMER_ID = "FARMER_TEST_SPIT"
BUYER_ID = "BUYER_TEST_CHH_SAMBHAJINAGAR"

ROAD_REQUIRED_COLUMNS = {
    "source_location_id",
    "source_location_name",
    "destination_location_id",
    "destination_location_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "status",
}
REPORT_REQUIRED_COLUMNS = {
    "hub_id",
    "hub_name",
    "inclusion_status",
    "farmer_hub_feasibility_status",
}
OUTPUT_COLUMNS = [
    "objective",
    "source_location_id",
    "source_location_name",
    "selected_hub_id",
    "selected_hub_name",
    "destination_location_id",
    "destination_location_name",
    "selected_path",
    "total_distance_km",
    "total_time_minutes",
    "edge_sum_distance_km",
    "edge_sum_time_minutes",
    "edge_sums_match",
    "feasibility_status",
    "selection_status",
    "exclusion_reason",
]


class OptimizerError(Exception):
    """An expected input, graph, or output error."""


@dataclass(frozen=True)
class CandidateRoute:
    """A validated candidate represented by two directed road legs."""

    hub_id: str
    hub_name: str
    farmer_to_hub_distance: float
    farmer_to_hub_time: float
    hub_to_buyer_distance: float
    hub_to_buyer_time: float

    @property
    def total_distance(self) -> float:
        return self.farmer_to_hub_distance + self.hub_to_buyer_distance

    @property
    def total_time(self) -> float:
        return self.farmer_to_hub_time + self.hub_to_buyer_time


@dataclass(frozen=True)
class ObjectiveResult:
    """One Dijkstra result plus independently verified route totals."""

    objective: str
    dijkstra_result: DijkstraResult
    selected_route: CandidateRoute | None
    edge_sum_distance: float | None
    edge_sum_time: float | None
    edge_sums_match: bool


def read_csv_rows(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    """Read a CSV and validate its required headers."""
    if not path.is_file():
        raise OptimizerError(f"Input file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            missing = sorted(required_columns - set(reader.fieldnames or []))
            if missing:
                raise OptimizerError(
                    f"{path} is missing columns: {', '.join(missing)}"
                )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise OptimizerError(f"Could not read {path}: {error}") from error
    if not rows:
        raise OptimizerError(f"{path} contains no data rows.")
    return rows


def parse_weight(value: str, field_name: str) -> float:
    """Parse a finite, non-negative road-matrix weight."""
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is not numeric") from error
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} is invalid")
    return number


def group_road_rows(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, str], list[dict[str, str]]]:
    """Group directed matrix rows by source and destination IDs."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        source = (row.get("source_location_id") or "").strip()
        destination = (row.get("destination_location_id") or "").strip()
        if source and destination:
            grouped.setdefault((source, destination), []).append(row)
    return grouped


def build_graph(
    road_rows: list[dict[str, str]],
    end_to_end_rows: list[dict[str, str]],
) -> tuple[WeightedGraph, dict[str, CandidateRoute], dict[str, str]]:
    """Build only feasible farmer -> hub -> buyer paths.

    Dijkstra's existing ``Edge`` calls its second numeric component
    ``transport_cost``. Here it deliberately stores estimated travel minutes
    in that field, and callers use one-hot alpha/beta values so distance and
    time are optimized separately rather than combined.
    """
    road_by_pair = group_road_rows(road_rows)
    candidates: dict[str, CandidateRoute] = {}
    names = {
        "farmer": "",
        "buyer": "",
    }
    for row in road_rows:
        if row.get("source_location_id") == FARMER_ID:
            names["farmer"] = row.get("source_location_name", "")
        if row.get("destination_location_id") == BUYER_ID:
            names["buyer"] = row.get("destination_location_name", "")

    end_rows_by_hub: dict[str, list[dict[str, str]]] = {}
    for row in end_to_end_rows:
        hub_id = (row.get("hub_id") or "").strip()
        if hub_id.startswith("HUB_"):
            end_rows_by_hub.setdefault(hub_id, []).append(row)

    graph: dict[str, list[Edge]] = {FARMER_ID: [], BUYER_ID: []}
    for hub_id in sorted(end_rows_by_hub):
        report_rows = end_rows_by_hub[hub_id]
        if len(report_rows) != 1:
            continue
        report_row = report_rows[0]
        if report_row.get("inclusion_status") != "included":
            continue
        if report_row.get("farmer_hub_feasibility_status") != "feasible":
            continue

        first_rows = road_by_pair.get((FARMER_ID, hub_id), [])
        second_rows = road_by_pair.get((hub_id, BUYER_ID), [])
        if len(first_rows) != 1 or len(second_rows) != 1:
            continue
        first = first_rows[0]
        second = second_rows[0]
        if first.get("status") != "ok" or second.get("status") != "ok":
            continue
        try:
            first_distance = parse_weight(first.get("road_distance_km", ""), "farmer-to-hub distance")
            first_time = parse_weight(first.get("estimated_travel_time_minutes", ""), "farmer-to-hub time")
            second_distance = parse_weight(second.get("road_distance_km", ""), "hub-to-buyer distance")
            second_time = parse_weight(second.get("estimated_travel_time_minutes", ""), "hub-to-buyer time")
        except ValueError:
            continue

        route = CandidateRoute(
            hub_id=hub_id,
            hub_name=report_row.get("hub_name", "") or first.get("destination_location_name", ""),
            farmer_to_hub_distance=first_distance,
            farmer_to_hub_time=first_time,
            hub_to_buyer_distance=second_distance,
            hub_to_buyer_time=second_time,
        )
        candidates[hub_id] = route
        graph[hub_id] = []
        graph[FARMER_ID].append(
            Edge(target=hub_id, distance=first_distance, transport_cost=first_time)
        )
        graph[hub_id].append(
            Edge(target=BUYER_ID, distance=second_distance, transport_cost=second_time)
        )

    return graph, candidates, names


def run_objective(
    graph: WeightedGraph,
    candidates: dict[str, CandidateRoute],
    objective: str,
) -> ObjectiveResult:
    """Run existing Dijkstra once for exactly one objective."""
    if objective == "distance_km":
        alpha, beta = 1.0, 0.0
    elif objective == "time_minutes":
        alpha, beta = 0.0, 1.0
    else:
        raise ValueError(f"Unknown objective: {objective}")

    result = dijkstra_shortest_path(
        graph,
        FARMER_ID,
        BUYER_ID,
        alpha=alpha,
        beta=beta,
    )
    if not result.reachable:
        return ObjectiveResult(objective, result, None, None, None, False)

    if len(result.path) != 3 or len(result.edges) != 2:
        raise OptimizerError("Selected path does not contain exactly two directed legs.")
    selected_hub_id = result.path[1]
    selected_route = candidates.get(selected_hub_id)
    if selected_route is None:
        raise OptimizerError("Dijkstra selected a hub absent from candidate metadata.")

    edge_sum_distance = sum(edge.distance for edge in result.edges)
    edge_sum_time = sum(edge.transport_cost for edge in result.edges)
    edge_sums_match = (
        math.isclose(edge_sum_distance, selected_route.total_distance, abs_tol=0.001)
        and math.isclose(edge_sum_time, selected_route.total_time, abs_tol=0.01)
    )
    if not edge_sums_match:
        raise OptimizerError("Selected edge sums do not match candidate route totals.")
    return ObjectiveResult(
        objective,
        result,
        selected_route,
        edge_sum_distance,
        edge_sum_time,
        edge_sums_match,
    )


def result_row(result: ObjectiveResult, names: dict[str, str]) -> dict[str, str]:
    """Convert one objective result to a CSV row."""
    route = result.selected_route
    return {
        "objective": result.objective,
        "source_location_id": FARMER_ID,
        "source_location_name": names.get("farmer", ""),
        "selected_hub_id": "" if route is None else route.hub_id,
        "selected_hub_name": "" if route is None else route.hub_name,
        "destination_location_id": BUYER_ID,
        "destination_location_name": names.get("buyer", ""),
        "selected_path": " -> ".join(result.dijkstra_result.path),
        "total_distance_km": "" if route is None else f"{route.total_distance:.3f}",
        "total_time_minutes": "" if route is None else f"{route.total_time:.2f}",
        "edge_sum_distance_km": (
            "" if result.edge_sum_distance is None else f"{result.edge_sum_distance:.3f}"
        ),
        "edge_sum_time_minutes": (
            "" if result.edge_sum_time is None else f"{result.edge_sum_time:.2f}"
        ),
        "edge_sums_match": str(result.edge_sums_match),
        "feasibility_status": "feasible" if route is not None else "no_feasible_route",
        "selection_status": "selected" if route is not None else "unavailable",
        "exclusion_reason": "" if route is not None else "No included, valid two-leg route was available.",
    }


def write_report(rows: list[dict[str, str]]) -> None:
    """Write the two objective results."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise OptimizerError(f"Could not write {OUTPUT_CSV}: {error}") from error


def print_result(result: ObjectiveResult) -> None:
    """Print one objective's selected path and verification state."""
    label = "minimum total road distance" if result.objective == "distance_km" else "minimum total estimated time"
    print(f"{label}:")
    if result.selected_route is None:
        print("  No feasible route available.")
        return
    print(f"  Path: {' -> '.join(result.dijkstra_result.path)}")
    print(f"  Hub: {result.selected_route.hub_id} ({result.selected_route.hub_name})")
    print(f"  Total distance: {result.selected_route.total_distance:.3f} km")
    print(f"  Total estimated time: {result.selected_route.total_time:.2f} minutes")
    print("  Feasibility: feasible according to the existing end-to-end report")
    print(f"  Independent edge-sum verification: {'passed' if result.edge_sums_match else 'failed'}")


def main() -> int:
    """Read inputs, run both objectives, write, and print the report."""
    try:
        road_rows = read_csv_rows(ROAD_MATRIX_CSV, ROAD_REQUIRED_COLUMNS)
        end_rows = read_csv_rows(END_TO_END_CSV, REPORT_REQUIRED_COLUMNS)
        graph, candidates, names = build_graph(road_rows, end_rows)
        distance_result = run_objective(graph, candidates, "distance_km")
        time_result = run_objective(graph, candidates, "time_minutes")
        write_report([
            result_row(distance_result, names),
            result_row(time_result, names),
        ])
        print("Prototype Dijkstra end-to-end optimizer")
        print("========================================")
        print(
            "SPIT and Chhatrapati Sambhajinagar are temporary prototype locations."
        )
        print("No monetary cost optimization is being performed.")
        print_result(distance_result)
        print_result(time_result)
        print(f"Generated report: {OUTPUT_CSV}")
    except (OptimizerError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
