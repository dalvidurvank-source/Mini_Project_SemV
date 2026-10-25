"""Build a prototype seven-location OSRM road matrix.

Run from the project root with:

    python -m logistics.build_prototype_buyer_matrix

The farmer and buyer are temporary prototype locations. SPIT is in Mumbai and
the buyer is a city-centre test coordinate in Chhatrapati Sambhajinagar; these
are not production farm or buyer locations. OSRM values are estimates, not
live traffic predictions.
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


INPUT_CSV = Path("data/processed/prototype_locations_with_buyer.csv")
OUTPUT_CSV = Path("data/processed/prototype_buyer_road_matrix.csv")
OSRM_BASE_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT_SECONDS = 30
EXPECTED_LOCATION_COUNT = 7
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
    """A validated location used in the OSRM request."""

    location_id: str
    location_name: str
    latitude: float
    longitude: float


class MatrixBuildError(Exception):
    """An expected input, network, or OSRM response error."""


def read_locations() -> list[Location]:
    """Read exactly seven unique locations and validate their coordinates."""
    if not INPUT_CSV.is_file():
        raise MatrixBuildError(f"Input CSV does not exist: {INPUT_CSV}")

    try:
        with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing = sorted(REQUIRED_COLUMNS - columns)
            if missing:
                raise MatrixBuildError(
                    "Missing required columns: " + ", ".join(missing)
                )

            locations: list[Location] = []
            seen_ids: set[str] = set()
            for row_number, row in enumerate(reader, start=2):
                location_id = (row.get("location_id") or "").strip()
                location_name = (row.get("location_name") or "").strip()
                latitude_text = (row.get("latitude") or "").strip()
                longitude_text = (row.get("longitude") or "").strip()
                if not location_id or not location_name:
                    raise MatrixBuildError(
                        f"Row {row_number} is missing a location ID or name."
                    )
                if location_id in seen_ids:
                    raise MatrixBuildError(
                        f"Row {row_number} repeats location ID {location_id!r}."
                    )
                try:
                    latitude = float(latitude_text)
                    longitude = float(longitude_text)
                except ValueError as error:
                    raise MatrixBuildError(
                        f"Row {row_number} has non-numeric coordinates."
                    ) from error
                if not math.isfinite(latitude) or not math.isfinite(longitude):
                    raise MatrixBuildError(
                        f"Row {row_number} has non-finite coordinates."
                    )
                if not -90.0 <= latitude <= 90.0:
                    raise MatrixBuildError(
                        f"Row {row_number} latitude must be between -90 and 90."
                    )
                if not -180.0 <= longitude <= 180.0:
                    raise MatrixBuildError(
                        f"Row {row_number} longitude must be between -180 and 180."
                    )
                seen_ids.add(location_id)
                locations.append(
                    Location(location_id, location_name, latitude, longitude)
                )
    except (OSError, UnicodeError, csv.Error) as error:
        raise MatrixBuildError(f"Could not read input CSV: {error}") from error

    if len(locations) != EXPECTED_LOCATION_COUNT:
        raise MatrixBuildError(
            f"Expected {EXPECTED_LOCATION_COUNT} locations, found {len(locations)}."
        )
    return locations


def build_table_url(locations: list[Location]) -> str:
    """Build the OSRM URL, reversing CSV latitude/longitude order."""
    # CSV stores latitude,longitude. OSRM requires longitude,latitude.
    coordinates = ";".join(
        f"{location.longitude},{location.latitude}" for location in locations
    )
    query = urlencode({"annotations": "distance,duration"})
    return f"{OSRM_BASE_URL}/table/v1/driving/{coordinates}?{query}"


def validate_matrix(value: Any, name: str, size: int) -> None:
    """Require a square OSRM matrix matching the location count."""
    if not isinstance(value, list) or len(value) != size:
        raise MatrixBuildError(f"OSRM {name} matrix must have {size} rows.")
    if any(not isinstance(row, list) or len(row) != size for row in value):
        raise MatrixBuildError(f"OSRM {name} matrix must be {size} by {size}.")


def request_table(locations: list[Location]) -> dict[str, Any]:
    """Request and validate one OSRM table response."""
    request = Request(
        build_table_url(locations),
        headers={"Accept": "application/json", "User-Agent": "AgroLink/1.0"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise MatrixBuildError(
                    f"OSRM returned HTTP status {response.status}."
                )
            try:
                payload = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise MatrixBuildError("OSRM returned invalid JSON.") from error
    except HTTPError as error:
        raise MatrixBuildError(
            f"OSRM returned HTTP error {error.code}: {error.reason}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise MatrixBuildError(f"Could not connect to OSRM: {error}") from error

    if not isinstance(payload, dict):
        raise MatrixBuildError("OSRM response must be a JSON object.")
    if payload.get("code") != "Ok":
        raise MatrixBuildError(
            f"OSRM reported an API error: {payload.get('code', 'unknown')}"
        )
    distances = payload.get("distances")
    durations = payload.get("durations")
    validate_matrix(distances, "distances", len(locations))
    validate_matrix(durations, "durations", len(locations))
    return {"distances": distances, "durations": durations}


def build_rows(
    locations: list[Location],
    table: dict[str, Any],
    timestamp: str,
) -> list[dict[str, str]]:
    """Convert OSRM metres/seconds into all ordered output rows."""
    rows: list[dict[str, str]] = []
    distances = table["distances"]
    durations = table["durations"]
    for source_index, source in enumerate(locations):
        for destination_index, destination in enumerate(locations):
            distance_m = distances[source_index][destination_index]
            duration_s = durations[source_index][destination_index]
            if distance_m is not None and (
                not isinstance(distance_m, (int, float))
                or not math.isfinite(distance_m)
                or distance_m < 0
            ):
                raise MatrixBuildError("OSRM returned an invalid distance value.")
            if duration_s is not None and (
                not isinstance(duration_s, (int, float))
                or not math.isfinite(duration_s)
                or duration_s < 0
            ):
                raise MatrixBuildError("OSRM returned an invalid duration value.")

            rows.append(
                {
                    "source_location_id": source.location_id,
                    "source_location_name": source.location_name,
                    "destination_location_id": destination.location_id,
                    "destination_location_name": destination.location_name,
                    "road_distance_km": (
                        "" if distance_m is None else f"{distance_m / 1000.0:.3f}"
                    ),
                    "estimated_travel_time_minutes": (
                        "" if duration_s is None else f"{duration_s / 60.0:.2f}"
                    ),
                    "routing_provider": "OSRM Table API",
                    "retrieval_timestamp_utc": timestamp,
                    "status": (
                        "no_route"
                        if distance_m is None or duration_s is None
                        else "ok"
                    ),
                }
            )
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    """Write the generated matrix without changing the input CSV."""
    try:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise MatrixBuildError(f"Could not write output CSV: {error}") from error


def main() -> int:
    """Validate locations, call OSRM, and write the prototype matrix."""
    try:
        locations = read_locations()
        table = request_table(locations)
        rows = build_rows(
            locations,
            table,
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        write_rows(rows)
        print("Prototype OSRM buyer matrix generated.")
        print(
            "SPIT and the Sambhajinagar buyer are temporary prototype locations; "
            "values are not live traffic predictions."
        )
        print(f"Locations: {len(locations)}; ordered pairs: {len(rows)}")
        print(f"Output file: {OUTPUT_CSV}")
    except MatrixBuildError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
