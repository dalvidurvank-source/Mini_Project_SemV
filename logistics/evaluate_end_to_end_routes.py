"""Evaluate prototype farmer-to-hub-to-buyer routes.

Run from the project root with:

    python -m logistics.evaluate_end_to_end_routes

SPIT and the buyer are temporary prototype locations. This report is not a
claim about real farm operations, live traffic, or transportation cost.
"""

import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from .shelf_life import is_route_feasible
except ImportError:
    from logistics.shelf_life import is_route_feasible


ROAD_MATRIX_CSV = Path("data/processed/prototype_buyer_road_matrix.csv")
FEASIBILITY_CSV = Path("data/processed/farmer_hub_feasibility.csv")
OUTPUT_CSV = Path("data/processed/end_to_end_route_report.csv")
FARMER_ID = "FARMER_TEST_SPIT"
BUYER_ID = "BUYER_TEST_CHH_SAMBHAJINAGAR"

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
    "remaining_shelf_life_days",
    "handling_time_days",
    "safety_margin_days",
    "feasibility_status",
}
OUTPUT_COLUMNS = [
    "farmer_location_id",
    "farmer_location_name",
    "hub_id",
    "hub_name",
    "buyer_location_id",
    "buyer_location_name",
    "farmer_to_hub_distance_km",
    "farmer_to_hub_time_minutes",
    "hub_to_buyer_distance_km",
    "hub_to_buyer_time_minutes",
    "total_road_distance_km",
    "total_travel_time_minutes",
    "remaining_shelf_life_days",
    "handling_time_days",
    "safety_margin_days",
    "total_time_consumed_days",
    "remaining_shelf_life_margin_days",
    "farmer_hub_feasibility_status",
    "farmer_hub_route_status",
    "hub_buyer_route_status",
    "inclusion_status",
    "exclusion_reason",
    "total_distance_rank",
    "routing_provider",
    "retrieval_timestamp_utc",
]


class EndToEndRouteError(Exception):
    """An expected input or output error."""


@dataclass
class RouteReportRow:
    """One hub's complete two-leg route evaluation."""

    values: dict[str, str]

    def as_dict(self) -> dict[str, str]:
        return self.values


def read_csv_rows(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    """Read a CSV with standard-library validation and clear errors."""
    if not path.is_file():
        raise EndToEndRouteError(f"Input file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            missing = sorted(required_columns - set(reader.fieldnames or []))
            if missing:
                raise EndToEndRouteError(
                    f"{path} is missing required columns: {', '.join(missing)}"
                )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise EndToEndRouteError(f"Could not read {path}: {error}") from error
    if not rows:
        raise EndToEndRouteError(f"{path} contains no data rows.")
    return rows


def group_by_pair(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, str], list[dict[str, str]]]:
    """Group road rows by their directed source and destination IDs."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        source = (row.get("source_location_id") or "").strip()
        destination = (row.get("destination_location_id") or "").strip()
        if source and destination:
            grouped.setdefault((source, destination), []).append(row)
    return grouped


def group_by_hub(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group feasibility rows by candidate hub ID."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        hub_id = (row.get("hub_id") or "").strip()
        if hub_id.startswith("HUB_"):
            grouped.setdefault(hub_id, []).append(row)
    return grouped


def parse_non_negative(value: str, field_name: str) -> float:
    """Parse a finite, non-negative road or shelf-life value."""
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is not numeric") from error
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return number


def route_metrics(
    row: dict[str, str] | None,
    label: str,
) -> tuple[float | None, float | None, str, list[str]]:
    """Read one directed road leg, preserving null/error reasons."""
    if row is None:
        return None, None, "missing", [f"{label} route is missing"]
    status = row.get("status", "")
    reasons: list[str] = []
    if status != "ok":
        reasons.append(f"{label} route status is {status or 'missing'}")
    try:
        distance = parse_non_negative(row.get("road_distance_km", ""), f"{label} distance")
        minutes = parse_non_negative(
            row.get("estimated_travel_time_minutes", ""),
            f"{label} travel time",
        )
    except ValueError as error:
        return None, None, status, reasons + [str(error)]
    return distance, minutes, status, reasons


def build_end_to_end_report(
    road_rows: list[dict[str, str]],
    feasibility_rows: list[dict[str, str]],
) -> list[RouteReportRow]:
    """Evaluate every hub in the existing farmer feasibility report."""
    road_by_pair = group_by_pair(road_rows)
    feasibility_by_hub = group_by_hub(feasibility_rows)
    hub_ids = sorted(feasibility_by_hub)
    if not hub_ids:
        raise EndToEndRouteError("No HUB_ candidates found in the feasibility report.")

    report: list[RouteReportRow] = []
    for hub_id in hub_ids:
        feasibility_matches = feasibility_by_hub[hub_id]
        feasibility = feasibility_matches[0]
        reasons: list[str] = []
        if len(feasibility_matches) != 1:
            reasons.append("duplicate feasibility rows")

        farmer_hub_matches = road_by_pair.get((FARMER_ID, hub_id), [])
        hub_buyer_matches = road_by_pair.get((hub_id, BUYER_ID), [])
        if len(farmer_hub_matches) > 1:
            reasons.append("duplicate farmer-to-hub road rows")
        if len(hub_buyer_matches) > 1:
            reasons.append("duplicate hub-to-buyer road rows")
        farmer_hub = farmer_hub_matches[0] if farmer_hub_matches else None
        hub_buyer = hub_buyer_matches[0] if hub_buyer_matches else None

        farmer_hub_distance, farmer_hub_minutes, farmer_hub_status, route_reasons = route_metrics(
            farmer_hub, "farmer-to-hub"
        )
        reasons.extend(route_reasons)
        hub_buyer_distance, hub_buyer_minutes, hub_buyer_status, route_reasons = route_metrics(
            hub_buyer, "hub-to-buyer"
        )
        reasons.extend(route_reasons)

        existing_status = feasibility.get("feasibility_status", "")
        if existing_status != "feasible":
            reasons.append(
                f"existing farmer-to-hub feasibility is {existing_status or 'missing'}"
            )

        shelf_life = handling = safety = None
        try:
            shelf_life = parse_non_negative(
                feasibility.get("remaining_shelf_life_days", ""),
                "remaining shelf life",
            )
            handling = parse_non_negative(
                feasibility.get("handling_time_days", ""), "handling time"
            )
            safety = parse_non_negative(
                feasibility.get("safety_margin_days", ""), "safety margin"
            )
        except ValueError as error:
            reasons.append(str(error))

        total_distance = None
        total_minutes = None
        total_days = None
        remaining_margin = None
        if (
            farmer_hub_distance is not None
            and hub_buyer_distance is not None
            and farmer_hub_minutes is not None
            and hub_buyer_minutes is not None
            and shelf_life is not None
            and handling is not None
            and safety is not None
        ):
            total_distance = farmer_hub_distance + hub_buyer_distance
            total_minutes = farmer_hub_minutes + hub_buyer_minutes
            # OSRM minutes must become days before using shelf_life.py.
            total_travel_days = total_minutes / (24.0 * 60.0)
            total_days = total_travel_days + handling + safety
            remaining_margin = shelf_life - total_days
            try:
                if not is_route_feasible(
                    total_travel_days,
                    shelf_life,
                    handling,
                    safety,
                ):
                    reasons.append("complete journey fails the shelf-life check")
            except ValueError as error:
                reasons.append(f"shelf-life validation failed: {error}")

        values = {
            "farmer_location_id": FARMER_ID,
            "farmer_location_name": (
                (farmer_hub or {}).get("source_location_name")
                or feasibility.get("farmer_location_name", "")
            ),
            "hub_id": hub_id,
            "hub_name": (
                (farmer_hub or {}).get("destination_location_name")
                or feasibility.get("hub_name", "")
            ),
            "buyer_location_id": BUYER_ID,
            "buyer_location_name": (hub_buyer or {}).get("destination_location_name", ""),
            "farmer_to_hub_distance_km": (
                "" if farmer_hub_distance is None else f"{farmer_hub_distance:.3f}"
            ),
            "farmer_to_hub_time_minutes": (
                "" if farmer_hub_minutes is None else f"{farmer_hub_minutes:.2f}"
            ),
            "hub_to_buyer_distance_km": (
                "" if hub_buyer_distance is None else f"{hub_buyer_distance:.3f}"
            ),
            "hub_to_buyer_time_minutes": (
                "" if hub_buyer_minutes is None else f"{hub_buyer_minutes:.2f}"
            ),
            "total_road_distance_km": (
                "" if total_distance is None else f"{total_distance:.3f}"
            ),
            "total_travel_time_minutes": (
                "" if total_minutes is None else f"{total_minutes:.2f}"
            ),
            "remaining_shelf_life_days": feasibility.get("remaining_shelf_life_days", ""),
            "handling_time_days": feasibility.get("handling_time_days", ""),
            "safety_margin_days": feasibility.get("safety_margin_days", ""),
            "total_time_consumed_days": (
                "" if total_days is None else f"{total_days:.4f}"
            ),
            "remaining_shelf_life_margin_days": (
                "" if remaining_margin is None else f"{remaining_margin:.4f}"
            ),
            "farmer_hub_feasibility_status": existing_status,
            "farmer_hub_route_status": farmer_hub_status,
            "hub_buyer_route_status": hub_buyer_status,
            "inclusion_status": "included" if not reasons else "excluded",
            "exclusion_reason": "; ".join(reasons),
            "total_distance_rank": "",
            "routing_provider": (farmer_hub or {}).get("routing_provider", ""),
            "retrieval_timestamp_utc": (farmer_hub or {}).get(
                "retrieval_timestamp_utc", ""
            ),
        }
        report.append(RouteReportRow(values))

    included = [row for row in report if row.values["inclusion_status"] == "included"]
    included.sort(key=lambda row: (float(row.values["total_road_distance_km"]), row.values["hub_id"]))
    for rank, row in enumerate(included, start=1):
        row.values["total_distance_rank"] = str(rank)
    return report


def write_report(rows: list[RouteReportRow]) -> None:
    """Write all five candidates and their inclusion/exclusion reasons."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(row.as_dict() for row in rows)
    except OSError as error:
        raise EndToEndRouteError(f"Could not write route report: {error}") from error


def print_report(rows: list[RouteReportRow]) -> None:
    """Print the end-to-end evaluation and total-distance ranking."""
    print("Prototype End-to-End Route Evaluation")
    print("=======================================")
    print(
        "Origin: FARMER_TEST_SPIT (temporary SPIT Mumbai prototype location). "
        "Buyer: BUYER_TEST_CHH_SAMBHAJINAGAR (temporary city-centre test location)."
    )
    print("This does not demonstrate actual transportation cost savings.")
    print()
    for row in rows:
        values = row.values
        print(
            f"{values['hub_id']} | total distance={values['total_road_distance_km'] or '(empty)'} km | "
            f"total travel={values['total_travel_time_minutes'] or '(empty)'} min | "
            f"{values['inclusion_status']}"
        )
        if values["exclusion_reason"]:
            print(f"  Excluded: {values['exclusion_reason']}")

    print()
    print("Shortest-distance feasible routes")
    ranked = [row for row in rows if row.values["total_distance_rank"]]
    for row in sorted(ranked, key=lambda item: int(item.values["total_distance_rank"])):
        print(
            f"  {row.values['total_distance_rank']}. {row.values['hub_id']} — "
            f"{row.values['total_road_distance_km']} km"
        )
    if not ranked:
        print("  none")
    print(f"Report written to: {OUTPUT_CSV}")


def main() -> int:
    """Read both inputs, evaluate complete routes, and write the report."""
    try:
        road_rows = read_csv_rows(ROAD_MATRIX_CSV, ROAD_REQUIRED_COLUMNS)
        feasibility_rows = read_csv_rows(
            FEASIBILITY_CSV,
            FEASIBILITY_REQUIRED_COLUMNS,
        )
        report = build_end_to_end_report(road_rows, feasibility_rows)
        write_report(report)
        print_report(report)
    except EndToEndRouteError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
