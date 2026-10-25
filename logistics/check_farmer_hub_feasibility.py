"""Check a temporary farmer-to-hub route against shelf-life constraints.

Run from the project root with:

    python -m logistics.check_farmer_hub_feasibility

This is a prototype test for SPIT in Mumbai. SPIT is not an actual tomato
farm in Nashik, and this script does not rank hubs by transport cost.
"""

import csv
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Direct file execution puts only the logistics directory on sys.path.
    # Add the project root so the package imports below still work.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from logistics.hub_selector import (
        HANDLING_TIME_DAYS,
        REMAINING_SHELF_LIFE_DAYS,
        SAFETY_MARGIN_DAYS,
    )
    from logistics.shelf_life import is_route_feasible, remaining_allowable_travel_time
else:
    # Module execution uses package-relative imports.
    from .hub_selector import (
        HANDLING_TIME_DAYS,
        REMAINING_SHELF_LIFE_DAYS,
        SAFETY_MARGIN_DAYS,
    )
    from .shelf_life import is_route_feasible, remaining_allowable_travel_time


INPUT_CSV = Path("data/processed/test_location_road_matrix.csv")
OUTPUT_CSV = Path("data/processed/farmer_hub_feasibility.csv")
FARMER_ID = "FARMER_TEST_SPIT"
PROVIDER = "OSRM Table API"

REQUIRED_COLUMNS = {
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
OUTPUT_COLUMNS = [
    "farmer_location_id",
    "farmer_location_name",
    "hub_id",
    "hub_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "remaining_shelf_life_days",
    "handling_time_days",
    "safety_margin_days",
    "total_time_consumed_days",
    "remaining_time_after_constraints_days",
    "routing_provider",
    "retrieval_timestamp_utc",
    "feasibility_status",
    "explanation",
]


class FeasibilityCheckError(Exception):
    """An expected input or output validation error."""


def parse_non_negative_number(value: str, field_name: str) -> float:
    """Parse one finite, non-negative numeric matrix value."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is not numeric") from error
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return number


def read_candidate_rows() -> list[dict[str, str]]:
    """Read farmer-to-hub rows and validate the matrix structure."""
    if not INPUT_CSV.is_file():
        raise FeasibilityCheckError(f"Input matrix does not exist: {INPUT_CSV}")

    try:
        with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing_columns = sorted(REQUIRED_COLUMNS - columns)
            if missing_columns:
                raise FeasibilityCheckError(
                    "Missing required matrix columns: " + ", ".join(missing_columns)
                )

            candidate_rows = []
            for row in reader:
                if row.get("source_location_id") != FARMER_ID:
                    continue
                if not (row.get("destination_location_id") or "").startswith("HUB_"):
                    continue
                candidate_rows.append(row)
    except (OSError, UnicodeError, csv.Error) as error:
        raise FeasibilityCheckError(f"Could not read input matrix: {error}") from error

    if not candidate_rows:
        raise FeasibilityCheckError(
            f"No rows found from {FARMER_ID} to a destination beginning with HUB_."
        )
    return candidate_rows


def evaluate_row(row: dict[str, str]) -> dict[str, str]:
    """Evaluate one candidate without substituting straight-line distance."""
    farmer_name = row.get("source_location_name", "")
    hub_id = row.get("destination_location_id", "")
    hub_name = row.get("destination_location_name", "")
    provider = row.get("routing_provider", "")
    timestamp = row.get("retrieval_timestamp_utc", "")
    status = row.get("status", "")

    base = {
        "farmer_location_id": FARMER_ID,
        "farmer_location_name": farmer_name,
        "hub_id": hub_id,
        "hub_name": hub_name,
        "road_distance_km": row.get("road_distance_km", ""),
        "estimated_travel_time_minutes": row.get(
            "estimated_travel_time_minutes", ""
        ),
        "remaining_shelf_life_days": f"{REMAINING_SHELF_LIFE_DAYS:.2f}",
        "handling_time_days": f"{HANDLING_TIME_DAYS:.2f}",
        "safety_margin_days": f"{SAFETY_MARGIN_DAYS:.2f}",
        "total_time_consumed_days": "",
        "remaining_time_after_constraints_days": "",
        "routing_provider": provider or PROVIDER,
        "retrieval_timestamp_utc": timestamp,
        "feasibility_status": "unavailable",
        "explanation": "",
    }

    # A route must be explicitly marked ok. Missing, null, or other statuses
    # are unavailable; we never assume that such a route can be used.
    if status != "ok":
        base["explanation"] = (
            f"Route status is {status or 'missing'}; route is unavailable."
        )
        return base

    try:
        distance_km = parse_non_negative_number(
            base["road_distance_km"], "road_distance_km"
        )
        travel_minutes = parse_non_negative_number(
            base["estimated_travel_time_minutes"],
            "estimated_travel_time_minutes",
        )
    except ValueError as error:
        base["explanation"] = f"Route is unavailable: {error}."
        return base

    base["road_distance_km"] = f"{distance_km:.3f}"
    base["estimated_travel_time_minutes"] = f"{travel_minutes:.2f}"

    # OSRM gives minutes, while shelf-life rules use days. Convert before
    # calling the existing day-based shelf-life implementation.
    travel_days = travel_minutes / (24.0 * 60.0)
    total_days = travel_days + HANDLING_TIME_DAYS + SAFETY_MARGIN_DAYS
    remaining_days = REMAINING_SHELF_LIFE_DAYS - total_days
    base["total_time_consumed_days"] = f"{total_days:.4f}"
    base["remaining_time_after_constraints_days"] = f"{remaining_days:.4f}"

    feasible = is_route_feasible(
        travel_days,
        REMAINING_SHELF_LIFE_DAYS,
        HANDLING_TIME_DAYS,
        SAFETY_MARGIN_DAYS,
    )
    # This call documents and uses the project's established allowable-time
    # calculation: 4.0 - 0.5 - 0.5 = 3.0 days available for travel.
    allowable_travel_days = remaining_allowable_travel_time(
        REMAINING_SHELF_LIFE_DAYS,
        HANDLING_TIME_DAYS,
        SAFETY_MARGIN_DAYS,
    )
    if feasible:
        base["feasibility_status"] = "feasible"
        base["explanation"] = (
            f"Travel fits within {allowable_travel_days:.1f} allowable travel days."
        )
    else:
        base["feasibility_status"] = "rejected_shelf_life"
        base["explanation"] = (
            f"Travel takes {travel_days:.4f} days, exceeding the "
            f"{allowable_travel_days:.1f} allowable travel days."
        )
    return base


def write_report(rows: list[dict[str, str]]) -> None:
    """Write the feasibility report as a CSV."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise FeasibilityCheckError(f"Could not write report: {error}") from error


def print_summary(rows: list[dict[str, str]]) -> None:
    """Print feasible, rejected, and unavailable hubs without cost ranking."""
    print("Farmer-to-Hub Shelf-Life Feasibility")
    print("=====================================")
    print(
        "Prototype origin: FARMER_TEST_SPIT — Sardar Patel Institute of "
        "Technology (SPIT), Mumbai. This is not an actual tomato farm in Nashik."
    )
    print("No transport-cost ranking was performed.")
    print()

    for row in rows:
        print(
            f"{row['hub_id']} | {row['hub_name']} | "
            f"{row['road_distance_km'] or '(empty)'} km | "
            f"{row['estimated_travel_time_minutes'] or '(empty)'} minutes | "
            f"{row['feasibility_status']}"
        )
        print(f"  {row['explanation']}")

    feasible = [row for row in rows if row["feasibility_status"] == "feasible"]
    rejected = [
        row for row in rows if row["feasibility_status"] == "rejected_shelf_life"
    ]
    unavailable = [
        row for row in rows if row["feasibility_status"] == "unavailable"
    ]
    print()
    print("Feasible hubs:")
    print("  " + (", ".join(row["hub_id"] for row in feasible) or "none"))
    print("Rejected by shelf life:")
    print("  " + (", ".join(row["hub_id"] for row in rejected) or "none"))
    print("Unavailable hubs:")
    print("  " + (", ".join(row["hub_id"] for row in unavailable) or "none"))
    print(f"Report written to: {OUTPUT_CSV}")


def main() -> int:
    """Read the existing matrix, evaluate it, and write the report."""
    try:
        input_rows = read_candidate_rows()
        report_rows = [evaluate_row(row) for row in input_rows]
        write_report(report_rows)
        print_summary(report_rows)
    except FeasibilityCheckError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
