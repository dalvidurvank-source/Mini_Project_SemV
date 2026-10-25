"""Produce an academic-style evaluation of the current routing prototype.

Run from the project root with:

    python -m logistics.evaluate_prototype_metrics

This script evaluates generated routing estimates and software calculations. It
does not make network requests, train a model, or claim real-world cost or
prediction performance.
"""

import csv
import math
import sys
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Iterable

try:
    from .shelf_life import is_route_feasible
except ImportError:
    from logistics.shelf_life import is_route_feasible


ROAD_MATRIX_CSV = Path("data/processed/prototype_buyer_road_matrix.csv")
TEST_MATRIX_CSV = Path("data/processed/test_location_road_matrix.csv")
FEASIBILITY_CSV = Path("data/processed/farmer_hub_feasibility.csv")
SELECTION_CSV = Path("data/processed/road_hub_selection_report.csv")
END_TO_END_CSV = Path("data/processed/end_to_end_route_report.csv")
OUTPUT_REPORT = Path("data/processed/prototype_evaluation_report.txt")

FARMER_ID = "FARMER_TEST_SPIT"
BUYER_ID = "BUYER_TEST_CHH_SAMBHAJINAGAR"

END_TO_END_COLUMNS = {
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
    "total_distance_rank",
}
ROAD_COLUMNS = {
    "source_location_id",
    "destination_location_id",
    "road_distance_km",
    "estimated_travel_time_minutes",
    "status",
}


class MetricsError(Exception):
    """An expected input or report-writing error."""


def read_csv_rows(path: Path, required_columns: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV with standard-library validation."""
    if not path.is_file():
        raise MetricsError(f"Missing input file: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            headers = reader.fieldnames or []
            missing = sorted(required_columns - set(headers))
            if missing:
                raise MetricsError(
                    f"{path} is missing columns: {', '.join(missing)}"
                )
            return headers, list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise MetricsError(f"Could not read {path}: {error}") from error


def number(value: str, field_name: str) -> float:
    """Parse one finite, non-negative numeric value."""
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is not numeric") from error
    if not math.isfinite(parsed) or parsed < 0.0:
        raise ValueError(f"{field_name} is not finite and non-negative")
    return parsed


def finite_number(value: str, field_name: str) -> float:
    """Parse a finite number when negative margins are meaningful."""
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is missing")
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{field_name} is not numeric") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} is not finite")
    return parsed


def percentage(part: int, whole: int) -> str:
    """Format a percentage without dividing by zero."""
    return "0.00%" if whole == 0 else f"{part / whole * 100.0:.2f}%"


def routing_coverage(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    """Count successful and unavailable all-entry and distinct-location routes."""
    distinct_rows = [
        row
        for row in rows
        if row.get("source_location_id") != row.get("destination_location_id")
    ]

    def counts(selected_rows: list[dict[str, str]]) -> dict[str, int]:
        successful = sum(row.get("status") == "ok" for row in selected_rows)
        return {
            "total": len(selected_rows),
            "same_location": sum(
                row.get("source_location_id") == row.get("destination_location_id")
                for row in selected_rows
            ),
            "successful": successful,
            "unavailable": len(selected_rows) - successful,
        }

    return {"all_entries": counts(rows), "distinct_locations": counts(distinct_rows)}


def summary(values: Iterable[float]) -> dict[str, float | int]:
    """Return descriptive statistics for the supplied observations.

    Population standard deviation is used because the report summarizes the
    complete set of five generated candidate routes, not a sample estimate.
    """
    observations = list(values)
    if not observations:
        return {"count": 0}
    return {
        "count": len(observations),
        "mean": mean(observations),
        "median": median(observations),
        "minimum": min(observations),
        "maximum": max(observations),
        "range": max(observations) - min(observations),
        "standard_deviation": pstdev(observations),
    }


def shelf_life_check(row: dict[str, str]) -> dict[str, float | bool]:
    """Recalculate journey time and apply the existing day-based rule."""
    farmer_to_hub_minutes = number(
        row["farmer_to_hub_time_minutes"],
        "farmer-to-hub travel time",
    )
    hub_to_buyer_minutes = number(
        row["hub_to_buyer_time_minutes"],
        "hub-to-buyer travel time",
    )
    stored_total_minutes = number(
        row["total_travel_time_minutes"],
        "stored total travel time",
    )
    total_minutes = farmer_to_hub_minutes + hub_to_buyer_minutes
    handling = number(row["handling_time_days"], "handling time")
    safety = number(row["safety_margin_days"], "safety margin")
    shelf_life = number(row["remaining_shelf_life_days"], "remaining shelf life")
    stored_total = number(row["total_time_consumed_days"], "stored total days")
    stored_margin = finite_number(
        row["remaining_shelf_life_margin_days"],
        "stored shelf-life margin",
    )

    total_travel_days = total_minutes / (24.0 * 60.0)
    calculated_total = total_travel_days + handling + safety
    calculated_margin = shelf_life - calculated_total
    feasible = is_route_feasible(
        total_travel_days,
        shelf_life,
        handling,
        safety,
    )
    return {
        "total_travel_days": total_travel_days,
        "calculated_total_minutes": total_minutes,
        "stored_total_minutes": stored_total_minutes,
        "travel_time_consistent": math.isclose(
            total_minutes,
            stored_total_minutes,
            rel_tol=0.0,
            abs_tol=0.01,
        ),
        "calculated_total_days": calculated_total,
        "calculated_margin_days": calculated_margin,
        "stored_total_days": stored_total,
        "stored_margin_days": stored_margin,
        "feasible": feasible,
        "total_consistent": math.isclose(
            calculated_total,
            stored_total,
            rel_tol=0.0,
            abs_tol=0.0001,
        ),
        "margin_consistent": math.isclose(
            calculated_margin,
            stored_margin,
            rel_tol=0.0,
            abs_tol=0.0001,
        ),
    }


def line_stats(label: str, values: list[float], unit: str) -> list[str]:
    """Format one descriptive-statistics section."""
    stats = summary(values)
    if not stats.get("count"):
        return [f"{label}: no valid observations"]
    return [
        f"{label} ({stats['count']} observations, {unit}):",
        f"  mean={stats['mean']:.3f}, median={stats['median']:.3f}",
        f"  minimum={stats['minimum']:.3f}, maximum={stats['maximum']:.3f}",
        f"  range={stats['range']:.3f}, population standard deviation={stats['standard_deviation']:.3f}",
    ]


def prediction_metrics_note(headers_by_file: dict[str, list[str]]) -> list[str]:
    """Explain why supervised prediction metrics are not reported."""
    target_words = ("actual", "observed", "target", "predicted", "prediction")
    matching_headers = {
        header
        for headers in headers_by_file.values()
        for header in headers
        if any(word in header.lower() for word in target_words)
    }
    model_suffixes = {".pkl", ".joblib", ".onnx", ".h5", ".pt"}
    model_files: list[str] = []
    for path in Path(".").rglob("*"):
        if not path.is_file() or any(
            part == ".git"
            or part.startswith(".venv")
            or part == "__pycache__"
            for part in path.parts
        ):
            continue
        if path.suffix.lower() in model_suffixes:
            model_files.append(str(path))

    if not matching_headers and not model_files:
        return [
            "Prediction-model metrics: Not applicable to the current routing-only prototype.",
            "  No predicted-versus-actual target columns or recognized trained-model artifacts were found.",
            "  R-squared, MAE, RMSE, MAPE, accuracy, precision, recall, F1, and a confusion matrix require",
            "  observed ground-truth travel outcomes plus model predictions (and class labels for classification).",
        ]
    return [
        "Prediction-model metrics: Not reported.",
        f"  Potential target-like columns found: {sorted(matching_headers) or 'none'}.",
        f"  Recognized model artifacts found: {model_files or 'none'}.",
        "  The current files still do not provide a validated predicted-versus-actual evaluation dataset.",
    ]


def build_report() -> str:
    """Read all inputs and build the complete evaluation report text."""
    road_headers, road_rows = read_csv_rows(ROAD_MATRIX_CSV, ROAD_COLUMNS)
    test_headers, test_rows = read_csv_rows(TEST_MATRIX_CSV, ROAD_COLUMNS)
    feasibility_headers, feasibility_rows = read_csv_rows(
        FEASIBILITY_CSV,
        {"hub_id", "feasibility_status"},
    )
    selection_headers, selection_rows = read_csv_rows(
        SELECTION_CSV,
        {"hub_id", "selection_status", "road_distance_km", "estimated_travel_time_minutes"},
    )
    end_headers, end_rows = read_csv_rows(END_TO_END_CSV, END_TO_END_COLUMNS)

    location_ids = {
        row["source_location_id"] for row in road_rows
    } | {row["destination_location_id"] for row in road_rows}
    candidate_hubs = sorted({row["hub_id"] for row in feasibility_rows})
    coverage = routing_coverage(road_rows)
    all_coverage = coverage["all_entries"]
    distinct_coverage = coverage["distinct_locations"]
    feasible_hubs = sum(
        row.get("selection_status") in {"feasible", "included"}
        for row in selection_rows
    )
    excluded_hubs = len(selection_rows) - feasible_hubs

    included_rows = [row for row in end_rows if row.get("inclusion_status") == "included"]
    valid_distances: list[float] = []
    valid_times: list[float] = []
    consistency_issues: list[str] = []
    route_details: list[str] = []
    for row in end_rows:
        try:
            distance = number(row["total_road_distance_km"], "total road distance")
            travel_time = number(row["total_travel_time_minutes"], "total travel time")
            valid_distances.append(distance)
            valid_times.append(travel_time)
            check = shelf_life_check(row)
            if not check["travel_time_consistent"]:
                consistency_issues.append(
                    f"{row['hub_id']}: stored total minutes={check['stored_total_minutes']:.2f}, "
                    f"computed from legs={check['calculated_total_minutes']:.2f}"
                )
            if not check["total_consistent"]:
                consistency_issues.append(
                    f"{row['hub_id']}: stored total days={check['stored_total_days']:.4f}, "
                    f"computed={check['calculated_total_days']:.4f}"
                )
            if not check["margin_consistent"]:
                consistency_issues.append(
                    f"{row['hub_id']}: stored margin={check['stored_margin_days']:.4f}, "
                    f"computed={check['calculated_margin_days']:.4f}"
                )
            stored_included = row.get("inclusion_status") == "included"
            if bool(check["feasible"]) != stored_included:
                consistency_issues.append(
                    f"{row['hub_id']}: computed feasibility={check['feasible']}, "
                    f"stored inclusion={row.get('inclusion_status')}"
                )
            route_details.append(
                f"  {row['hub_id']}: distance={distance:.3f} km, time={travel_time:.2f} min, "
                f"handling={float(row['handling_time_days']):.2f} days, "
                f"safety margin={float(row['safety_margin_days']):.2f} days"
            )
        except (KeyError, ValueError) as error:
            consistency_issues.append(f"{row.get('hub_id', 'unknown')}: invalid values ({error})")

    if included_rows:
        shortest = min(included_rows, key=lambda row: float(row["total_road_distance_km"]))
        fastest = min(included_rows, key=lambda row: float(row["total_travel_time_minutes"]))
        selected_distance = float(shortest["total_road_distance_km"])
        selected_time = float(shortest["total_travel_time_minutes"])
    else:
        shortest = fastest = None
        selected_distance = selected_time = 0.0

    differences: list[str] = []
    for row in sorted(end_rows, key=lambda item: item["hub_id"]):
        try:
            distance_difference = float(row["total_road_distance_km"]) - selected_distance
            time_difference = float(row["total_travel_time_minutes"]) - selected_time
            differences.append(
                f"  {row['hub_id']}: distance difference={distance_difference:+.3f} km, "
                f"time difference={time_difference:+.2f} min"
            )
        except (KeyError, ValueError):
            differences.append(f"  {row.get('hub_id', 'unknown')}: differences unavailable")

    lines = [
        "AgroLink Prototype Evaluation Report",
        "====================================",
        "",
        "Scope and prototype labels",
        "--------------------------",
        "FARMER_TEST_SPIT is Sardar Patel Institute of Technology (SPIT), Mumbai,",
        "a temporary prototype origin rather than a verified tomato farm in Nashik.",
        "BUYER_TEST_CHH_SAMBHAJINAGAR is a temporary city-centre test destination.",
        "OSRM durations are route estimates, not verified observed travel times.",
        "",
        "1. Dataset and routing coverage",
        "--------------------------------",
        f"Locations in prototype buyer matrix: {len(location_ids)}",
        f"Candidate hubs in feasibility report: {len(candidate_hubs)}",
        "All ordered matrix entries (including same-location pairs):",
        f"  total ordered entries: {all_coverage['total']}",
        f"  same-location pairs: {all_coverage['same_location']}",
        f"  distinct-location pairs: {distinct_coverage['total']}",
        f"  successful: {all_coverage['successful']} ({percentage(all_coverage['successful'], all_coverage['total'])})",
        f"  unavailable: {all_coverage['unavailable']} ({percentage(all_coverage['unavailable'], all_coverage['total'])})",
        "Distinct-location routes (excluding source_location_id == destination_location_id):",
        f"  total distinct-location pairs: {distinct_coverage['total']}",
        f"  successful: {distinct_coverage['successful']} ({percentage(distinct_coverage['successful'], distinct_coverage['total'])})",
        f"  unavailable: {distinct_coverage['unavailable']} ({percentage(distinct_coverage['unavailable'], distinct_coverage['total'])})",
        f"Feasible candidate hubs: {feasible_hubs} ({percentage(feasible_hubs, len(selection_rows))})",
        f"Excluded candidate hubs: {excluded_hubs} ({percentage(excluded_hubs, len(selection_rows))})",
        f"Supporting five-location test matrix rows inspected: {len(test_rows)}",
        "",
        "2. Route-selection performance",
        "-------------------------------",
        f"Shortest-distance feasible candidate: {shortest['hub_id']} ({shortest['total_road_distance_km']} km)" if shortest else "Shortest-distance feasible candidate: none",
        f"Fastest estimated-time feasible candidate: {fastest['hub_id']} ({fastest['total_travel_time_minutes']} minutes)" if fastest else "Fastest estimated-time feasible candidate: none",
        "Candidate totals:",
        *route_details,
        "Differences from the shortest-distance selected route (alternative minus selected):",
        *differences,
        "Baseline comparison: not available. The existing inputs contain routing estimates,",
        "not an observed historical route baseline with comparable end-to-end measurements.",
        "Transportation cost savings: not calculated; validated transport prices are unavailable.",
        "",
        "3. Shelf-life and constraint verification",
        "------------------------------------------",
        "For each candidate: total travel time in minutes was converted to days, then",
        "handling time and safety margin were added separately before applying shelf_life.py.",
        "",
        f"Computed/stored consistency issues: {len(consistency_issues)}",
        *( ["  none"] if not consistency_issues else [f"  {issue}" for issue in consistency_issues]),
        "",
        "4. Statistical summaries",
        "------------------------",
        *line_stats("Total candidate route distance", valid_distances, "km"),
        *line_stats("Total candidate estimated travel time", valid_times, "minutes"),
        "These are descriptive summaries of the small prototype candidate set, not",
        "generalizable statistical claims about AgroLink or real-world traffic.",
        "",
        "5. Prediction-model metrics",
        "----------------------------",
        *prediction_metrics_note({
            str(ROAD_MATRIX_CSV): road_headers,
            str(TEST_MATRIX_CSV): test_headers,
            str(FEASIBILITY_CSV): feasibility_headers,
            str(SELECTION_CSV): selection_headers,
            str(END_TO_END_CSV): end_headers,
        }),
        "",
        "6. Reliability and limitations",
        "--------------------------------",
        "Successful unit tests demonstrate software behavior on local test data; they",
        "do not establish predictive accuracy or validate observed travel performance.",
        "The prototype lacks observed arrival times, actual route durations, traffic",
        "conditions, repeated trips, weather/seasonal data, shipment outcomes, and",
        "validated transport prices. A real evaluation would require those observations",
        "plus a defined prediction target and a held-out evaluation dataset.",
        "No Haversine distance was substituted for an OSRM road value in this analysis.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    """Build and save the evaluation report."""
    try:
        report = build_report()
        try:
            OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_REPORT.write_text(report, encoding="utf-8")
        except OSError as error:
            raise MetricsError(f"Could not write {OUTPUT_REPORT}: {error}") from error
        print(report)
        print(f"Saved report to: {OUTPUT_REPORT}")
    except MetricsError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
