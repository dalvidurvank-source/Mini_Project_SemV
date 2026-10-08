"""Configurable fair-price logic for AgroLink."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

MIN_DSR_MULTIPLIER = 0.85
MAX_DSR_MULTIPLIER = 1.15


def _non_negative_finite(value: float, name: str) -> float:
    """Validate that a value is finite and non-negative."""

    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return number


def calculate_dsr(
    total_regional_supply: float,
    total_regional_demand: float,
) -> float:
    """Return supply divided by demand for a valid region-level DSR."""

    supply = _non_negative_finite(total_regional_supply, "total_regional_supply")
    demand = _non_negative_finite(total_regional_demand, "total_regional_demand")
    if demand == 0:
        raise ValueError(
            "total_regional_demand must be greater than zero to calculate DSR."
        )
    return supply / demand


def calculate_dsr_multiplier(dsr: float, dsr_sensitivity: float) -> float:
    """Apply an explicit, bounded DSR sensitivity mapping.

    The project-configured formula is:
        1 + sensitivity * (1 - dsr)
    """

    ratio = _non_negative_finite(dsr, "dsr")
    sensitivity = _non_negative_finite(dsr_sensitivity, "dsr_sensitivity")
    multiplier = 1.0 + sensitivity * (1.0 - ratio)
    return min(MAX_DSR_MULTIPLIER, max(MIN_DSR_MULTIPLIER, multiplier))


def get_quality_multiplier(
    quality_grade: str,
    quality_multipliers: Mapping[str, float],
    default: float | None = None,
) -> float:
    """Return the configured quality multiplier for a known grade."""

    grade = str(quality_grade).strip()
    if not grade:
        raise ValueError("quality_grade must not be empty.")

    if grade in quality_multipliers:
        return _non_negative_finite(quality_multipliers[grade], "quality multiplier")
    if default is not None:
        return _non_negative_finite(default, "default quality multiplier")
    raise ValueError(f"Unknown quality grade: {grade!r}.")


def get_location_multiplier(location_factor: float) -> float:
    """Validate and return the configured location multiplier."""

    return _non_negative_finite(location_factor, "location_factor")


def calculate_transport_cost_per_quintal(
    total_transport_cost: float,
    quantity_kg: float,
) -> float:
    """Convert total transport cost into INR per quintal."""

    cost = _non_negative_finite(total_transport_cost, "total_transport_cost")
    quantity = _non_negative_finite(quantity_kg, "quantity_kg")
    if quantity == 0:
        raise ValueError("quantity_kg must be greater than zero.")
    quintals = quantity / 100.0
    return cost / quintals


def calculate_fair_price(
    base_price: float,
    dsr_multiplier: float,
    quality_multiplier: float,
    location_multiplier: float,
    transport_cost_per_quintal: float,
) -> float:
    """Apply the configured pricing factors and transport deduction."""

    base = _non_negative_finite(base_price, "base_price")
    dsr_factor = _non_negative_finite(dsr_multiplier, "dsr_multiplier")
    quality_factor = _non_negative_finite(quality_multiplier, "quality_multiplier")
    location_factor = _non_negative_finite(location_multiplier, "location_multiplier")
    transport = _non_negative_finite(
        transport_cost_per_quintal,
        "transport_cost_per_quintal",
    )

    if not MIN_DSR_MULTIPLIER <= dsr_factor <= MAX_DSR_MULTIPLIER:
        raise ValueError(
            f"dsr_multiplier must be between {MIN_DSR_MULTIPLIER} and "
            f"{MAX_DSR_MULTIPLIER}."
        )

    fair_price = base * dsr_factor * quality_factor * location_factor - transport
    return round(max(0.0, fair_price), 2)


def create_fair_price_band(
    fair_price: float,
    lower_offset: float,
    upper_offset: float,
) -> dict[str, float]:
    """Create a configurable min/fair/max band around the fair price."""

    fair = _non_negative_finite(fair_price, "fair_price")
    lower = _non_negative_finite(lower_offset, "lower_offset")
    upper = _non_negative_finite(upper_offset, "upper_offset")
    return {
        "min_price": round(max(0.0, fair - lower), 2),
        "fair_price": round(fair, 2),
        "max_price": round(max(0.0, fair + upper), 2),
    }


def calculate_price_from_var_base(
    var_base_price: float,
    total_regional_supply: float,
    total_regional_demand: float,
    quality_grade: str,
    quality_multipliers: Mapping[str, float],
    location_multiplier: float,
    total_transport_cost: float,
    quantity_kg: float,
    dsr_sensitivity: float,
    band_lower_offset: float,
    band_upper_offset: float,
) -> dict[str, Any]:
    """Apply the documented pricing pipeline and return all explainable values."""

    base_price = _non_negative_finite(var_base_price, "var_base_price")
    dsr = calculate_dsr(total_regional_supply, total_regional_demand)
    dsr_multiplier = calculate_dsr_multiplier(dsr, dsr_sensitivity)
    quality_factor = get_quality_multiplier(quality_grade, quality_multipliers)
    location_factor = get_location_multiplier(location_multiplier)
    transport_per_quintal = calculate_transport_cost_per_quintal(
        total_transport_cost,
        quantity_kg,
    )
    fair_price = calculate_fair_price(
        base_price,
        dsr_multiplier,
        quality_factor,
        location_factor,
        transport_per_quintal,
    )
    band = create_fair_price_band(
        fair_price,
        band_lower_offset,
        band_upper_offset,
    )

    return {
        "var_base_price": base_price,
        "dsr": dsr,
        "dsr_multiplier": dsr_multiplier,
        "quality_multiplier": quality_factor,
        "location_multiplier": location_factor,
        "transport_cost_per_quintal": transport_per_quintal,
        **band,
    }


if __name__ == "__main__":
    demonstration = calculate_price_from_var_base(
        var_base_price=743.05,
        total_regional_supply=9000,
        total_regional_demand=10000,
        quality_grade="A",
        quality_multipliers={"A": 1.05, "B": 1.00, "C": 0.95},
        location_multiplier=1.00,
        total_transport_cost=800,
        quantity_kg=500,
        dsr_sensitivity=0.10,
        band_lower_offset=25,
        band_upper_offset=25,
    )

    print("DEMONSTRATION ONLY: configurable example inputs, not calibrated values")
    print(f"VAR Base Price: INR {demonstration['var_base_price']:.2f}/quintal")
    print(f"DSR: {demonstration['dsr']:.4f}")
    print(f"DSR multiplier: {demonstration['dsr_multiplier']:.4f}")
    print(f"Quality multiplier: {demonstration['quality_multiplier']:.4f}")
    print(f"Location multiplier: {demonstration['location_multiplier']:.4f}")
    print(
        "Transport cost per quintal: "
        f"INR {demonstration['transport_cost_per_quintal']:.2f}"
    )
    print(f"Final Fair Price: INR {demonstration['fair_price']:.2f}/quintal")
    print(f"Min Price: INR {demonstration['min_price']:.2f}/quintal")
    print(f"Max Price: INR {demonstration['max_price']:.2f}/quintal")