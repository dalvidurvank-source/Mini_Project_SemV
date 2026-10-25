"""Evaluate hardcoded logistics hubs against distance and shelf life."""

from dataclasses import dataclass
from math import isfinite

from .haversine import haversine_distance
from .shelf_life import is_route_feasible

REMAINING_SHELF_LIFE_DAYS = 4.0
HANDLING_TIME_DAYS = 0.5
SAFETY_MARGIN_DAYS = 0.5


@dataclass(frozen=True)
class Hub:
    name: str
    latitude: float
    longitude: float
    average_speed_kmph: float
    transport_cost: float

    def __post_init__(self) -> None:
        haversine_distance(self.latitude, self.longitude, self.latitude, self.longitude)
        if not isfinite(self.average_speed_kmph) or self.average_speed_kmph <= 0.0:
            raise ValueError("Hub average speed must be a finite number greater than zero.")
        if not isfinite(self.transport_cost) or self.transport_cost < 0.0:
            raise ValueError("Hub transport cost must be a finite, non-negative number.")


@dataclass(frozen=True)
class HubEvaluation:
    hub: Hub
    distance_km: float
    travel_time_hours: float
    travel_time_days: float
    feasible: bool
    reason: str

    @property
    def feasibility_status(self) -> str:
        return "PASS" if self.feasible else "FAIL"


@dataclass(frozen=True)
class HubEvaluationBatch:
    ranked_results: tuple[HubEvaluation, ...]

    @property
    def feasible_results(self) -> tuple[HubEvaluation, ...]:
        """Return viable hubs in the same distance-ranked order."""
        return tuple(result for result in self.ranked_results if result.feasible)

    @property
    def rejected_results(self) -> tuple[HubEvaluation, ...]:
        """Return shelf-life-infeasible hubs in distance-ranked order."""
        return tuple(result for result in self.ranked_results if not result.feasible)


# Synthetic demonstration values only; coordinates do not represent real hubs.
# Hub 1 is geographically close but intentionally too slow for the shelf life.
HARD_CODED_HUBS = [
    Hub("Demo Hub 1", 20.0, 90.0, 18.0, 700.0),
    Hub("Demo Hub 2", 0.0, 74.0, 40.0, 1400.0),
    Hub("Demo Hub 3", 20.0, 100.0, 50.0, 2100.0),
    Hub("Demo Hub 4", 40.0, 74.0, 15.0, 950.0),
]


def evaluate_hubs(
    farmer_latitude: float,
    farmer_longitude: float,
    hubs: list[Hub] | None = None,
    remaining_shelf_life_days: float = REMAINING_SHELF_LIFE_DAYS,
    handling_time_days: float = HANDLING_TIME_DAYS,
    safety_margin_days: float = SAFETY_MARGIN_DAYS,
) -> HubEvaluationBatch:
    """Evaluate every hub, rank by distance, and expose feasible candidates.

    Every hub is evaluated and sorted by Haversine distance. Feasible and
    rejected results are exposed separately, in that same order. No final
    route or lowest-cost hub is selected.
    """
    candidate_hubs = HARD_CODED_HUBS if hubs is None else hubs
    # Validate farmer coordinates even when the caller supplies no hubs.
    haversine_distance(farmer_latitude, farmer_longitude, farmer_latitude, farmer_longitude)
    results: list[HubEvaluation] = []

    for hub in candidate_hubs:
        distance_km = haversine_distance(
            farmer_latitude,
            farmer_longitude,
            hub.latitude,
            hub.longitude,
        )
        travel_time_hours = distance_km / hub.average_speed_kmph
        travel_time_days = travel_time_hours / 24.0
        feasible = is_route_feasible(
            travel_time_days,
            remaining_shelf_life_days,
            handling_time_days,
            safety_margin_days,
        )
        reason = "Feasible" if feasible else (
            f"Estimated travel time of {travel_time_days:.3f} days violates "
            "the shelf-life constraint."
        )
        results.append(
            HubEvaluation(
                hub=hub,
                distance_km=distance_km,
                travel_time_hours=travel_time_hours,
                travel_time_days=travel_time_days,
                feasible=feasible,
                reason=reason,
            )
        )

    results.sort(key=lambda result: result.distance_km)
    return HubEvaluationBatch(ranked_results=tuple(results))