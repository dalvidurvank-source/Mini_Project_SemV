"""Explainable transport scenario estimates; no synthetic training or accuracy claims."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping


def _number(values: Mapping[str, Any], key: str, *, positive: bool = False, default: float | None = None) -> float:
    raw = values.get(key, default)
    if isinstance(raw, bool) or raw is None:
        raise ValueError(f"{key} is required and must be numeric.")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} is required and must be numeric.") from exc
    if not math.isfinite(value) or value < 0 or (positive and value <= 0):
        qualifier = "greater than zero" if positive else "non-negative"
        raise ValueError(f"{key} must be finite and {qualifier}.")
    return value


def estimate_transport(values: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate a dated scenario estimate from caller-supplied route/cost inputs."""
    origin, destination = str(values.get("origin", "")).strip(), str(values.get("destination", "")).strip()
    if not origin or not destination:
        raise ValueError("origin and destination are required for a transport scenario estimate.")
    distance = _number(values, "route_distance_km", positive=True)
    duration = _number(values, "route_duration_hours", positive=True)
    capacity = _number(values, "vehicle_capacity_kg", positive=True)
    shipment = _number(values, "shipment_weight_kg", positive=True)
    if shipment > capacity:
        raise ValueError("shipment_weight_kg cannot exceed vehicle_capacity_kg for a single trip.")
    efficiency = _number(values, "fuel_efficiency_km_per_litre", positive=True)
    fuel_price = _number(values, "fuel_price_inr_per_litre")
    utilization = _number(values, "utilization_factor", positive=True, default=1.0)
    if utilization > 1:
        raise ValueError("utilization_factor must be at most 1.")
    empty_return = _number(values, "empty_return_factor", default=0.0)
    if empty_return > 1:
        raise ValueError("empty_return_factor must be at most 1.")
    effective_distance = distance * (1.0 + empty_return)
    fuel_litres = effective_distance / efficiency
    components = {
        "fuel": fuel_litres * fuel_price,
        "tolls": _number(values, "tolls_inr", default=0.0),
        "loading": _number(values, "loading_inr", default=0.0),
        "unloading": _number(values, "unloading_inr", default=0.0),
        "refrigeration": _number(values, "refrigeration_inr", default=0.0),
        "handling": _number(values, "handling_inr", default=0.0),
    }
    allocated = shipment * utilization
    total = float(sum(components.values()))
    timestamps = {"route": values.get("route_data_timestamp"), "fuel_price": values.get("fuel_price_timestamp")}
    provenance = {"route": values.get("route_provenance"), "fuel_price": values.get("fuel_price_provenance"), "other_costs": values.get("cost_provenance", "user_entered")}
    warnings = []
    if not timestamps["route"] or not timestamps["fuel_price"]:
        warnings.append("One or more source timestamps were not supplied; freshness cannot be verified.")
    if not provenance["route"] or not provenance["fuel_price"]:
        warnings.append("One or more source provenance fields were not supplied.")
    return {
        "kind": "scenario_estimate",
        "label": "Explainable transport scenario estimate (not a forecast)",
        "origin": origin, "destination": destination,
        "vehicle": {"type": str(values.get("vehicle_type", "unspecified")).strip() or "unspecified", "capacity_kg": capacity, "shipment_weight_kg": shipment, "utilization_factor": utilization},
        "route": {"distance_km": distance, "duration_hours": duration, "effective_distance_km": effective_distance, "empty_return_factor": empty_return},
        "fuel": {"efficiency_km_per_litre": efficiency, "price_inr_per_litre": fuel_price, "litres": fuel_litres},
        "components_inr": {key: round(value, 2) for key, value in components.items()},
        "total_trip_cost_inr": round(total, 2),
        "cost_inr_per_km": round(total / effective_distance, 4),
        "cost_inr_per_kg": round(total / allocated, 4),
        "cost_inr_per_quintal": round(total / allocated * 100, 2),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "data_timestamps": timestamps, "provenance": provenance, "warnings": warnings,
    }


def legacy_batch_estimate(total_cost: float, shipment_weight_kg: float) -> dict[str, Any]:
    cost, weight = float(total_cost), float(shipment_weight_kg)
    if not math.isfinite(cost) or cost < 0 or not math.isfinite(weight) or weight <= 0:
        raise ValueError("Legacy transport cost must be non-negative and shipment weight positive.")
    return {"kind": "scenario_estimate", "label": "User-entered batch-cost scenario estimate (not a forecast)", "components_inr": {"user_entered_batch_cost": cost}, "total_trip_cost_inr": cost, "cost_inr_per_km": None, "cost_inr_per_kg": round(cost / weight, 4), "cost_inr_per_quintal": round(cost / weight * 100, 2), "calculated_at": datetime.now(timezone.utc).isoformat(), "data_timestamps": {"route": None, "fuel_price": None}, "provenance": {"total": "user_entered"}, "warnings": ["Route, fuel, toll and handling components were not supplied; only batch allocation is available."]}
