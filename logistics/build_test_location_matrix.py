"""Build a prototype road matrix for hubs and a temporary Mumbai test origin.

Run from the project root with:

    python -m logistics.build_test_location_matrix

This is a prototype test only. SPIT is in Mumbai while the candidate markets
are in Nashik, so the resulting routes are not representative of the normal
AgroLink operating area. Values are routing estimates, not live traffic
predictions.
"""

import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


INPUT_CSV = Path("data/processed/test_locations.csv")
OUTPUT_CSV = Path("data/processed/test_location_road_matrix.csv")
OSRM_BASE_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT_SECONDS = 30
REQUIRED_COLUMNS = {
    "location_id",
    "location_name",
    "latitude",
    "longitude",
    "location_type",
    "verification_status",
}
OUTPUT_COLUMNS = [
    "source_location_id",
    "source_location_name",
    "destination_location_id",
    "destination_location_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "routing_provider",
    "retrieval_timestamp_utc",
    "status",
]


@dataclass(frozen=True)
class Location:
    """A validated location used in the OSRM request and output."""

    location_id: str
    location_name: str
    latitude: float
    longitude: float


class TestMatrixError(Exception):
    """An expected input, network, or API-response error."""


def read_locations() -> list[Location]:
    """Read the test locations and reject invalid data before network access."""
    if not INPUT_CSV.is_file():
        raise TestMatrixError(f"Input CSV does not exist: {INPUT_CSV}")

    try:
        with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing_columns = sorted(REQUIRED_COLUMNS - columns)
            if missing_columns:
                raise TestMatrixError(
                    "Missing required columns: " + ", ".join(missing_columns)
                )

            locations: list[Location] = []
            for row_number, row in enumerate(reader, start=2):
                location_id = (row.get("location_id") or "").strip()
                location_name = (row.get("location_name") or "").strip()
                latitude_text = (row.get("latitude") or "").strip()
                longitude_text = (row.get("longitude") or "").strip()

                missing_values = [
                    field
                    for field, value in (
                        ("location_id", location_id),
                        ("location_name", location_name),
                        ("latitude", latitude_text),
                        ("longitude", longitude_text),
                    )
                    if not value
                ]
                if missing_values:
                    raise TestMatrixError(
                        f"Row {row_number} has missing values: "
                        + ", ".join(missing_values)
                    )

                try:
                    latitude = float(latitude_text)
                    longitude = float(longitude_text)
                except ValueError as error:
                    raise TestMatrixError(
                        f"Row {row_number} has non-numeric coordinates."
                    ) from error

                if not math.isfinite(latitude) or not math.isfinite(longitude):
                    raise TestMatrixError(
                        f"Row {row_number} has non-finite coordinates."
                    )
                if not -90.0 <= latitude <= 90.0:
                    raise TestMatrixError(
                        f"Row {row_number} latitude must be between -90 and 90."
                    )
                if not -180.0 <= longitude <= 180.0:
                    raise TestMatrixError(
                        f"Row {row_number} longitude must be between -180 and 180."
                    )

                locations.append(
                    Location(location_id, location_name, latitude, longitude)
                )
    except (OSError, UnicodeError, csv.Error) as error:
        raise TestMatrixError(f"Could not read input CSV: {error}") from error

    if not locations:
        raise TestMatrixError("The test-location CSV contains no locations.")
    return locations


def build_table_url(locations: list[Location]) -> str:
    """Build the OSRM URL using required longitude,latitude coordinates."""
    # The CSV stores latitude,longitude; OSRM requires longitude,latitude.
    coordinates = ";".join(
        f"{location.longitude},{location.latitude}" for location in locations
    )
    query = urlencode({"annotations": "distance,duration"})
    return f"{OSRM_BASE_URL}/table/v1/driving/{coordinates}?{query}"


def validate_matrix(value: Any, name: str, size: int) -> None:
    """Ensure an OSRM matrix has one row and column for every location."""
    if not isinstance(value, list) or len(value) != size:
        raise TestMatrixError(f"OSRM {name} matrix must have {size} rows.")
    if any(not isinstance(row, list) or len(row) != size for row in value):
        raise TestMatrixError(f"OSRM {name} matrix must be {size} by {size}.")


def request_table(locations: list[Location]) -> dict[str, Any]:
    """Request and validate one OSRM distance/duration table."""
    request = Request(
        build_table_url(locations),
        headers={"Accept": "application/json", "User-Agent": "AgroLink/1.0"},
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise TestMatrixError(
                    f"OSRM returned HTTP status {response.status}."
                )
            try:
                payload = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise TestMatrixError("OSRM returned invalid JSON.") from error
    except HTTPError as error:
        raise TestMatrixError(
            f"OSRM returned HTTP error {error.code}: {error.reason}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise TestMatrixError(f"Could not connect to OSRM: {error}") from error

    if not isinstance(payload, dict):
        raise TestMatrixError("OSRM response must be a JSON object.")
    if payload.get("code") != "Ok":
        raise TestMatrixError(
            f"OSRM reported an API error: {payload.get('code', 'unknown')}"
        )

    distances = payload.get("distances")
    durations = payload.get("durations")
    validate_matrix(distances, "distances", len(locations))
    validate_matrix(durations, "durations", len(locations))
    return {"distances": distances, "durations": durations}


def retrieval_timestamp() -> str:
    """Return one UTC timestamp for all rows in this retrieval."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_rows(
    locations: list[Location],
    table: dict[str, Any],
    timestamp: str,
) -> list[dict[str, str]]:
    """Create all ordered source-destination rows, including self-pairs."""
    rows: list[dict[str, str]] = []
    distances = table["distances"]
    durations = table["durations"]

    for source_index, source in enumerate(locations):
        for destination_index, destination in enumerate(locations):
            distance_m = distances[source_index][destination_index]
            duration_s = durations[source_index][destination_index]
            distance_km = ""
            duration_minutes = ""
            status = "ok"

            if distance_m is None or duration_s is None:
                status = "no_route"

            if distance_m is not None:
                if not isinstance(distance_m, (int, float)) or not math.isfinite(
                    distance_m
                ):
                    raise TestMatrixError("OSRM returned an invalid distance value.")
                distance_km = f"{distance_m / 1000.0:.3f}"

            if duration_s is not None:
                if not isinstance(duration_s, (int, float)) or not math.isfinite(
                    duration_s
                ):
                    raise TestMatrixError("OSRM returned an invalid duration value.")
                duration_minutes = f"{duration_s / 60.0:.2f}"

            rows.append(
                {
                    "source_location_id": source.location_id,
                    "source_location_name": source.location_name,
                    "destination_location_id": destination.location_id,
                    "destination_location_name": destination.location_name,
                    "road_distance_km": distance_km,
                    "estimated_travel_time_minutes": duration_minutes,
                    "routing_provider": "OSRM Table API",
                    "retrieval_timestamp_utc": timestamp,
                    "status": status,
                }
            )
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    """Write the generated matrix to the requested output path."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise TestMatrixError(f"Could not write output CSV: {error}") from error


def print_report(locations: list[Location], rows: list[dict[str, str]]) -> None:
    """Print the prototype context and every route result."""
    print("Prototype Test Location Road Matrix")
    print("====================================")
    print(
        "Prototype test only: SPIT is in Mumbai, while the candidate markets "
        "are in Nashik."
    )
    print("Routing values are estimates, not live traffic predictions.")
    print()

    for row in rows:
        distance = row["road_distance_km"] or "(empty)"
        duration = row["estimated_travel_time_minutes"] or "(empty)"
        print(
            f"{row['source_location_id']} -> {row['destination_location_id']} | "
            f"distance={distance} km | time={duration} minutes | "
            f"status={row['status']}"
        )

    failed_routes = [row for row in rows if row["status"] != "ok"]
    print()
    print(f"Locations: {len(locations)}; ordered pairs: {len(rows)}")
    print(f"Failed routes: {len(failed_routes)}")
    print(f"Output file: {OUTPUT_CSV}")


def main() -> int:
    """Validate, request, write, and report the prototype matrix."""
    try:
        locations = read_locations()
        print(f"Validated {len(locations)} locations.")
        table = request_table(locations)
        rows = build_rows(locations, table, retrieval_timestamp())
        write_rows(rows)
        print_report(locations, rows)
    except TestMatrixError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
