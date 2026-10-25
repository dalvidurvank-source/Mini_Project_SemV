"""Validate hub coordinates and report distances between all valid hubs.

Run this script from the project root with:

    python logistics/check_hub_coordinates.py

The distances in this report are Haversine straight-line distances. They are
not road distances and should not be used as a replacement for road routing.
"""

import csv
import math
import sys
from pathlib import Path

try:
    # This import works when the script is run from the project root.
    from logistics.haversine import haversine_distance
except ModuleNotFoundError:
    # This also supports running the file directly in environments where only
    # the logistics directory is on Python's import path.
    from haversine import haversine_distance


CSV_PATH = Path("data/processed/nashik_hubs_coordinates_updated.csv")
REQUIRED_COLUMNS = {
    "hub_id",
    "hub_name",
    "latitude",
    "longitude",
    "verification_status",
    "source_or_reference",
    "notes",
}
NEARBY_DISTANCE_KM = 0.5


def add_error(errors: list[str], message: str) -> None:
    """Add an error message to the current report."""
    errors.append(message)


def validate_rows(rows: list[dict[str, str | float | list[str]]]) -> list[str]:
    """Validate required row values and return file-level errors."""
    errors: list[str] = []

    if not rows:
        errors.append("The CSV contains no data rows.")
        return errors

    for row_number, row in enumerate(rows, start=2):
        row_errors = row["errors"]

        for field in ("hub_id", "hub_name", "latitude", "longitude"):
            value = row.get(field)
            if value is None or not str(value).strip():
                add_error(row_errors, f"missing {field}")

        for field in ("latitude", "longitude"):
            raw_value = row.get(field)
            value = "" if raw_value is None else str(raw_value).strip()
            if not value:
                continue

            try:
                number = float(value)
            except ValueError:
                add_error(row_errors, f"{field} is not numeric")
                continue

            row[field] = number
            if not math.isfinite(number):
                add_error(row_errors, f"{field} is not finite")
            elif field == "latitude" and not -90.0 <= number <= 90.0:
                add_error(row_errors, "latitude is outside -90 to 90 degrees")
            elif field == "longitude" and not -180.0 <= number <= 180.0:
                add_error(row_errors, "longitude is outside -180 to 180 degrees")

        if row["errors"]:
            errors.append(f"Row {row_number}: {', '.join(row_errors)}")

    return errors


def duplicate_warnings(rows: list[dict[str, str | float | list[str]]]) -> list[str]:
    """Return warnings for repeated IDs, names, and coordinate pairs."""
    warnings: list[str] = []
    checks = (
        ("hub_id", "duplicate hub ID"),
        ("hub_name", "duplicate hub name"),
    )

    for field, label in checks:
        grouped: dict[str, list[str]] = {}
        for row in rows:
            raw_value = row.get(field)
            value = "" if raw_value is None else str(raw_value).strip()
            if value:
                hub_id = row.get("hub_id")
                hub_id_text = "" if hub_id is None else str(hub_id).strip()
                grouped.setdefault(value, []).append(hub_id_text)
        for value, hub_ids in grouped.items():
            if len(hub_ids) > 1:
                warnings.append(f"{label}: {value!r} (hub IDs: {', '.join(hub_ids)})")

    grouped_coordinates: dict[tuple[float, float], list[str]] = {}
    for row in rows:
        if row["errors"]:
            continue
        coordinates = (float(row["latitude"]), float(row["longitude"]))
        grouped_coordinates.setdefault(coordinates, []).append(str(row["hub_id"]))

    for coordinates, hub_ids in grouped_coordinates.items():
        if len(hub_ids) > 1:
            warnings.append(
                "identical coordinate pair "
                f"{coordinates}: hub IDs {', '.join(hub_ids)}"
            )

    return warnings


def print_report(
    rows: list[dict[str, str | float | list[str]]],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Print a readable validation report."""
    print("Hub Coordinate Validation Report")
    print("=" * 34)
    print(f"CSV: {CSV_PATH}")
    print(
        "Distance note: Haversine distance is straight-line distance, "
        "not road distance."
    )
    valid_rows = [row for row in rows if not row["errors"]]

    print()

    print("Hub coordinates")
    print("---------------")
    for row in rows:
        status = "VALID" if not row["errors"] else "ERROR"
        print(
            f"{status:5} | {row['hub_id']} | {row['hub_name']} | "
            f"latitude={row['latitude']} | longitude={row['longitude']}"
        )
        for message in row["errors"]:
            print(f"       ERROR: {message}")

    print()
    nearby_warnings: list[str] = []
    for index, first in enumerate(valid_rows):
        for second in valid_rows[index + 1 :]:
            distance = haversine_distance(
                float(first["latitude"]),
                float(first["longitude"]),
                float(second["latitude"]),
                float(second["longitude"]),
            )
            if distance < NEARBY_DISTANCE_KM:
                nearby_warnings.append(
                    f"hubs {first['hub_id']} and {second['hub_id']} are "
                    f"{distance:.3f} km apart; manual review recommended"
                )

    print("Warnings")
    print("--------")
    all_warnings = warnings + nearby_warnings
    if all_warnings:
        for warning in all_warnings:
            print(f"WARNING: {warning}")
    else:
        print("No duplicate or nearby-hub warnings.")

    print()
    print("Pairwise Haversine distances (km)")
    print("---------------------------------")
    if len(valid_rows) < 2:
        print("Not enough valid hubs to calculate pairwise distances.")
    else:
        for index, first in enumerate(valid_rows):
            for second in valid_rows[index + 1 :]:
                distance = haversine_distance(
                    float(first["latitude"]),
                    float(first["longitude"]),
                    float(second["latitude"]),
                    float(second["longitude"]),
                )
                print(
                    f"{first['hub_id']} <-> {second['hub_id']}: "
                    f"{distance:.3f} km"
                )
                if distance < NEARBY_DISTANCE_KM:
                    print(
                        "  WARNING: hubs are less than 0.5 km apart; "
                        "manual review recommended."
                    )

    print()
    print("Validation errors")
    print("------------------")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
    else:
        print("No validation errors found.")


def load_csv() -> tuple[list[dict[str, str | float | list[str]]], list[str]]:
    """Read the CSV and return rows plus file-level validation errors."""
    if not CSV_PATH.is_file():
        return [], [f"CSV file does not exist: {CSV_PATH}"]

    try:
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing_columns = sorted(REQUIRED_COLUMNS - columns)
            if missing_columns:
                return [], [
                    "Missing required columns: " + ", ".join(missing_columns)
                ]

            rows = []
            for row in reader:
                row["errors"] = []
                rows.append(row)
    except (OSError, UnicodeError, csv.Error) as error:
        return [], [f"Could not read CSV file: {error}"]

    return rows, validate_rows(rows)


def main() -> int:
    rows, errors = load_csv()
    warnings = duplicate_warnings(rows) if rows else []
    print_report(rows, errors, warnings)

    if errors:
        print("\nRESULT: VALIDATION FAILED")
        return 1

    print("\nRESULT: VALIDATION PASSED (warnings, if any, require manual review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
