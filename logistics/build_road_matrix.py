"""Build a long-form road-distance matrix with the OSRM Table API.

Run this module from the project root:

    python -m logistics.build_road_matrix

The returned values are routing estimates. They are not live traffic
predictions and should not be interpreted as guaranteed travel times.
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


# These paths are intentionally relative to the project root. Run this file
# as a module from the project root so these paths resolve correctly.
INPUT_CSV = Path("data/processed/nashik_hubs_coordinates_updated.csv")
OUTPUT_CSV = Path("data/processed/hub_road_distance_matrix.csv")
OSRM_BASE_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT_SECONDS = 30

REQUIRED_COLUMNS = {"hub_id", "hub_name", "latitude", "longitude"}
OUTPUT_COLUMNS = [
    "source_hub_id",
    "source_hub_name",
    "destination_hub_id",
    "destination_hub_name",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "routing_provider",
    "retrieval_timestamp_utc",
    "status",
]


@dataclass(frozen=True)
class Hub:
    """The fields needed for an OSRM request and output report."""

    hub_id: str
    hub_name: str
    latitude: float
    longitude: float


class RoadMatrixError(Exception):
    """An expected input, network, or OSRM response error."""


def read_hubs() -> list[Hub]:
    """Read and validate all hubs before making a network request."""
    if not INPUT_CSV.is_file():
        raise RoadMatrixError(f"Input CSV does not exist: {INPUT_CSV}")

    try:
        with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing_columns = sorted(REQUIRED_COLUMNS - columns)
            if missing_columns:
                raise RoadMatrixError(
                    "Missing required CSV columns: " + ", ".join(missing_columns)
                )

            hubs: list[Hub] = []
            for row_number, row in enumerate(reader, start=2):
                hub_id = (row.get("hub_id") or "").strip()
                hub_name = (row.get("hub_name") or "").strip()
                latitude_text = (row.get("latitude") or "").strip()
                longitude_text = (row.get("longitude") or "").strip()

                missing_fields = [
                    field
                    for field, value in (
                        ("hub_id", hub_id),
                        ("hub_name", hub_name),
                        ("latitude", latitude_text),
                        ("longitude", longitude_text),
                    )
                    if not value
                ]
                if missing_fields:
                    raise RoadMatrixError(
                        f"Row {row_number} has missing values: "
                        + ", ".join(missing_fields)
                    )

                try:
                    latitude = float(latitude_text)
                    longitude = float(longitude_text)
                except ValueError as error:
                    raise RoadMatrixError(
                        f"Row {row_number} has non-numeric coordinates."
                    ) from error

                if not math.isfinite(latitude) or not math.isfinite(longitude):
                    raise RoadMatrixError(
                        f"Row {row_number} has non-finite coordinates."
                    )
                if not -90.0 <= latitude <= 90.0:
                    raise RoadMatrixError(
                        f"Row {row_number} latitude must be between -90 and 90."
                    )
                if not -180.0 <= longitude <= 180.0:
                    raise RoadMatrixError(
                        f"Row {row_number} longitude must be between -180 and 180."
                    )

                hubs.append(Hub(hub_id, hub_name, latitude, longitude))
    except (OSError, UnicodeError, csv.Error) as error:
        raise RoadMatrixError(f"Could not read input CSV: {error}") from error

    if not hubs:
        raise RoadMatrixError("The input CSV contains no hubs.")
    return hubs


def build_table_url(hubs: list[Hub]) -> str:
    """Build an OSRM URL, reversing CSV latitude/longitude order."""
    # CSV values are latitude,longitude. OSRM requires longitude,latitude.
    coordinates = ";".join(
        f"{hub.longitude},{hub.latitude}" for hub in hubs
    )
    query = urlencode({"annotations": "distance,duration"})
    return f"{OSRM_BASE_URL}/table/v1/driving/{coordinates}?{query}"


def request_table(hubs: list[Hub]) -> dict[str, Any]:
    """Request and validate one complete OSRM distance/duration table."""
    request = Request(
        build_table_url(hubs),
        headers={"Accept": "application/json", "User-Agent": "AgroLink/1.0"},
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise RoadMatrixError(
                    f"OSRM returned HTTP status {response.status}."
                )
            try:
                payload = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise RoadMatrixError("OSRM returned invalid JSON.") from error
    except HTTPError as error:
        raise RoadMatrixError(
            f"OSRM returned HTTP error {error.code}: {error.reason}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise RoadMatrixError(f"Could not connect to OSRM: {error}") from error

    if not isinstance(payload, dict):
        raise RoadMatrixError("OSRM response must be a JSON object.")
    if payload.get("code") != "Ok":
        raise RoadMatrixError(
            f"OSRM reported an API error: {payload.get('code', 'unknown')}"
        )

    distances = payload.get("distances")
    durations = payload.get("durations")
    expected_size = len(hubs)
    validate_matrix(distances, "distances", expected_size)
    validate_matrix(durations, "durations", expected_size)
    return {"distances": distances, "durations": durations}


def validate_matrix(value: Any, name: str, expected_size: int) -> None:
    """Check that an OSRM matrix has exactly one row per hub and column."""
    if not isinstance(value, list) or len(value) != expected_size:
        raise RoadMatrixError(
            f"OSRM {name} matrix must have {expected_size} rows."
        )
    if any(not isinstance(row, list) or len(row) != expected_size for row in value):
        raise RoadMatrixError(
            f"OSRM {name} matrix must be {expected_size} by {expected_size}."
        )


def utc_timestamp() -> str:
    """Return a UTC timestamp suitable for every row in this retrieval."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_rows(
    hubs: list[Hub],
    table: dict[str, Any],
    retrieval_timestamp: str,
) -> list[dict[str, str]]:
    """Convert OSRM's matrices into one row for every ordered hub pair."""
    rows: list[dict[str, str]] = []
    distances = table["distances"]
    durations = table["durations"]

    for source_index, source in enumerate(hubs):
        for destination_index, destination in enumerate(hubs):
            distance_m = distances[source_index][destination_index]
            duration_s = durations[source_index][destination_index]
            status = "ok"
            distance_km = ""
            travel_minutes = ""

            if distance_m is None or duration_s is None:
                status = "no_route"

            if distance_m is not None:
                if not isinstance(distance_m, (int, float)):
                    raise RoadMatrixError(
                        "OSRM returned a non-numeric distance value."
                    )
                if not math.isfinite(distance_m):
                    raise RoadMatrixError(
                        "OSRM returned a non-finite distance value."
                    )
                distance_km = f"{distance_m / 1000.0:.3f}"

            if duration_s is not None:
                if not isinstance(duration_s, (int, float)):
                    raise RoadMatrixError(
                        "OSRM returned a non-numeric duration value."
                    )
                if not math.isfinite(duration_s):
                    raise RoadMatrixError(
                        "OSRM returned a non-finite duration value."
                    )
                travel_minutes = f"{duration_s / 60.0:.2f}"

            rows.append(
                {
                    "source_hub_id": source.hub_id,
                    "source_hub_name": source.hub_name,
                    "destination_hub_id": destination.hub_id,
                    "destination_hub_name": destination.hub_name,
                    "road_distance_km": distance_km,
                    "estimated_travel_time_minutes": travel_minutes,
                    "routing_provider": "OSRM Table API",
                    "retrieval_timestamp_utc": retrieval_timestamp,
                    "status": status,
                }
            )
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    """Write the completed matrix without changing the input CSV."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise RoadMatrixError(f"Could not write output CSV: {error}") from error


def print_report(rows: list[dict[str, str]]) -> None:
    """Print a readable summary of the generated matrix."""
    print("OSRM Road Distance Matrix Report")
    print("=================================")
    print("Provider: OSRM Table API")
    print(
        "Note: These are routing estimates, not live traffic predictions. "
        "All hubs and directions were retained."
    )
    print()

    for row in rows:
        distance = row["road_distance_km"] or "(empty)"
        duration = row["estimated_travel_time_minutes"] or "(empty)"
        print(
            f"{row['source_hub_id']} -> {row['destination_hub_id']} | "
            f"distance={distance} km | time={duration} minutes | "
            f"status={row['status']}"
        )

    failed_routes = [row for row in rows if row["status"] != "ok"]
    print()
    if failed_routes:
        print(f"Failed routes: {len(failed_routes)}")
        for row in failed_routes:
            print(
                f"  {row['source_hub_id']} -> {row['destination_hub_id']}: "
                f"{row['status']}"
            )
    else:
        print("Failed routes: none")
    print(f"Output file: {OUTPUT_CSV}")


def main() -> int:
    """Run validation, request OSRM data, write the matrix, and report."""
    try:
        hubs = read_hubs()
        print(f"Validated {len(hubs)} hubs; requesting one OSRM table...")
        table = request_table(hubs)
        rows = build_rows(hubs, table, utc_timestamp())
        write_rows(rows)
        print_report(rows)
    except RoadMatrixError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
