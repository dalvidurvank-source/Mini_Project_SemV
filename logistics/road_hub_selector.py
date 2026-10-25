"""Select feasible hubs using the generated OSRM road matrix.

Run this module from the project root with:

    python -m logistics.road_hub_selector

This is a single-origin selection step for FARMER_TEST_SPIT, a temporary
Mumbai prototype origin. It is not a full farmer-to-hub-to-buyer optimizer.
Distance and travel time are ranked separately; no cost score is invented.
"""

import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROAD_MATRIX_CSV = Path("data/processed/test_location_road_matrix.csv")
FEASIBILITY_CSV = Path("data/processed/farmer_hub_feasibility.csv")
OUTPUT_CSV = Path("data/processed/road_hub_selection_report.csv")
FARMER_LOCATION_ID = "FARMER_TEST_SPIT"

ROAD_REQUIRED_COLUMNS = {
    "source_location_id",
    "source_location_name",
    "destination_location_id",
    "destination_location_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "routing_provider",
    "retrieval_timestamp_utc",
    "status",
}
FEASIBILITY_REQUIRED_COLUMNS = {
    "farmer_location_id",
    "farmer_location_name",
    "hub_id",
    "hub_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "feasibility_status",
    "explanation",
}
OUTPUT_COLUMNS = [
    "farmer_location_id",
    "farmer_location_name",
    "hub_id",
    "hub_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "route_status",
    "feasibility_status",
    "selection_status",
    "exclusion_reason",
    "distance_rank",
    "time_rank",
    "routing_provider",
    "retrieval_timestamp_utc",
]


class SelectionError(Exception):
    """An expected input or output error."""


@dataclass
class SelectionRow:
    """One candidate hub and the result of applying all input checks."""

    farmer_location_id: str
    farmer_location_name: str
    hub_id: str
    hub_name: str
    road_distance_km: str
    estimated_travel_time_minutes: str
    route_status: str
    feasibility_status: str
    selection_status: str
    exclusion_reason: str
    distance_rank: str = ""
    time_rank: str = ""
    routing_provider: str = ""
    retrieval_timestamp_utc: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return a CSV-ready dictionary."""
        return {
            "farmer_location_id": self.farmer_location_id,
            "farmer_location_name": self.farmer_location_name,
            "hub_id": self.hub_id,
            "hub_name": self.hub_name,
            "road_distance_km": self.road_distance_km,
            "estimated_travel_time_minutes": self.estimated_travel_time_minutes,
            "route_status": self.route_status,
            "feasibility_status": self.feasibility_status,
            "selection_status": self.selection_status,
            "exclusion_reason": self.exclusion_reason,
            "distance_rank": self.distance_rank,
            "time_rank": self.time_rank,
            "routing_provider": self.routing_provider,
            "retrieval_timestamp_utc": self.retrieval_timestamp_utc,
        }


def read_csv_rows(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    """Read a CSV and validate its required headers."""
    if not path.is_file():
        raise SelectionError(f"Input file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing = sorted(required_columns - columns)
            if missing:
                raise SelectionError(
                    f"{path} is missing required columns: {', '.join(missing)}"
                )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise SelectionError(f"Could not read {path}: {error}") from error

    if not rows:
        raise SelectionError(f"{path} contains no data rows.")
    return rows


def parse_metric(value: str, field_name: str) -> float:
    """Parse a finite, non-negative road-matrix metric."""
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is not numeric") from error
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return number


def group_rows(rows: Iterable[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    """Group rows by a hub ID so missing or duplicate joins can be reported."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        value = (row.get(key) or "").strip()
        if value:
            grouped.setdefault(value, []).append(row)
    return grouped


def build_selection_report(
    road_rows: list[dict[str, str]],
    feasibility_rows: list[dict[str, str]],
    farmer_location_id: str = FARMER_LOCATION_ID,
) -> list[SelectionRow]:
    """Join one farmer's road and feasibility rows and rank valid candidates."""
    road_candidates = [
        row
        for row in road_rows
        if row.get("source_location_id") == farmer_location_id
        and (row.get("destination_location_id") or "").startswith("HUB_")
    ]
    feasibility_candidates = [
        row
        for row in feasibility_rows
        if row.get("farmer_location_id") == farmer_location_id
        and (row.get("hub_id") or "").startswith("HUB_")
    ]
    roads_by_hub = group_rows(road_candidates, "destination_location_id")
    feasibility_by_hub = group_rows(feasibility_candidates, "hub_id")
    hub_ids = sorted(set(roads_by_hub) | set(feasibility_by_hub))

    if not hub_ids:
        raise SelectionError(
            f"No candidate HUB_ destinations found for {farmer_location_id}."
        )

    report: list[SelectionRow] = []
    for hub_id in hub_ids:
        road_matches = roads_by_hub.get(hub_id, [])
        feasibility_matches = feasibility_by_hub.get(hub_id, [])
        road = road_matches[0] if road_matches else {}
        feasibility = feasibility_matches[0] if feasibility_matches else {}
        reasons: list[str] = []

        if len(road_matches) != 1:
            reasons.append(
                "missing road-matrix row"
                if not road_matches
                else "duplicate road-matrix rows"
            )
        if len(feasibility_matches) != 1:
            reasons.append(
                "missing feasibility row"
                if not feasibility_matches
                else "duplicate feasibility rows"
            )

        route_status = road.get("status", "")
        if route_status != "ok":
            reasons.append(f"route status is {route_status or 'missing'}")

        distance_text = road.get("road_distance_km", "")
        time_text = road.get("estimated_travel_time_minutes", "")
        try:
            distance = parse_metric(distance_text, "road_distance_km")
            time_minutes = parse_metric(time_text, "estimated_travel_time_minutes")
            distance_text = f"{distance:.3f}"
            time_text = f"{time_minutes:.2f}"
        except ValueError as error:
            reasons.append(str(error))

        feasibility_status = feasibility.get("feasibility_status", "")
        if feasibility_status != "feasible":
            reasons.append(
                f"feasibility status is {feasibility_status or 'missing'}"
            )

        report.append(
            SelectionRow(
                farmer_location_id=farmer_location_id,
                farmer_location_name=(
                    road.get("source_location_name")
                    or feasibility.get("farmer_location_name", "")
                ),
                hub_id=hub_id,
                hub_name=(
                    road.get("destination_location_name")
                    or feasibility.get("hub_name", "")
                ),
                road_distance_km=distance_text if not reasons[:1] else distance_text,
                estimated_travel_time_minutes=time_text,
                route_status=route_status,
                feasibility_status=feasibility_status,
                selection_status="feasible" if not reasons else "excluded",
                exclusion_reason="; ".join(reasons),
                routing_provider=road.get("routing_provider", ""),
                retrieval_timestamp_utc=road.get("retrieval_timestamp_utc", ""),
            )
        )

    feasible_rows = [row for row in report if row.selection_status == "feasible"]
    for rank, row in enumerate(
        sorted(feasible_rows, key=lambda item: (float(item.road_distance_km), item.hub_id)),
        start=1,
    ):
        row.distance_rank = str(rank)
    for rank, row in enumerate(
        sorted(
            feasible_rows,
            key=lambda item: (float(item.estimated_travel_time_minutes), item.hub_id),
        ),
        start=1,
    ):
        row.time_rank = str(rank)

    return report


def write_report(rows: list[SelectionRow]) -> None:
    """Write all candidates, including excluded candidates, to the report."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(row.as_dict() for row in rows)
    except OSError as error:
        raise SelectionError(f"Could not write selection report: {error}") from error


def print_report(rows: list[SelectionRow]) -> None:
    """Print separate distance and travel-time rankings."""
    print("Road-Based Hub Selection Report")
    print("================================")
    print(
        "Origin: FARMER_TEST_SPIT — a temporary Mumbai prototype test origin, "
        "not a real tomato farm in Nashik."
    )
    print("Road distance and estimated travel time are ranked separately.")
    print("No transport-cost score or lowest-cost claim is made.")
    print()

    print("Candidate hubs")
    print("--------------")
    for row in rows:
        print(
            f"{row.hub_id} | {row.hub_name} | "
            f"{row.road_distance_km or '(empty)'} km | "
            f"{row.estimated_travel_time_minutes or '(empty)'} minutes | "
            f"{row.selection_status}"
        )
        if row.exclusion_reason:
            print(f"  Excluded: {row.exclusion_reason}")

    feasible = [row for row in rows if row.selection_status == "feasible"]
    distance_ranked = sorted(feasible, key=lambda row: int(row.distance_rank))
    time_ranked = sorted(feasible, key=lambda row: int(row.time_rank))
    print()
    print("Shortest road-distance ranking")
    for row in distance_ranked:
        print(f"  {row.distance_rank}. {row.hub_id} — {row.road_distance_km} km")
    if not distance_ranked:
        print("  none")
    print("Fastest estimated-travel-time ranking")
    for row in time_ranked:
        print(
            f"  {row.time_rank}. {row.hub_id} — "
            f"{row.estimated_travel_time_minutes} minutes"
        )
    if not time_ranked:
        print("  none")
    print(f"Report written to: {OUTPUT_CSV}")


def main() -> int:
    """Read, join, rank, write, and print the single-origin report."""
    try:
        road_rows = read_csv_rows(ROAD_MATRIX_CSV, ROAD_REQUIRED_COLUMNS)
        feasibility_rows = read_csv_rows(
            FEASIBILITY_CSV,
            FEASIBILITY_REQUIRED_COLUMNS,
        )
        report = build_selection_report(road_rows, feasibility_rows)
        write_report(report)
        print_report(report)
    except SelectionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
