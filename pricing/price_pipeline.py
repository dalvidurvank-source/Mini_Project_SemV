"""Orchestration for the AgroLink VAR-to-fair-price flow."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from forecasting.var_forecaster import (
    clean_mandi_data,
    create_monthly_series,
    find_dense_markets,
    get_model_report,
    load_mandi_csv,
    predict_base_price,
)
from pricing.fair_price_engine import calculate_price_from_var_base


def _market_name(historical_data: pd.DataFrame) -> str:
    """Return the single market label when the input is already market-specific."""

    if "Market Name" not in historical_data.columns:
        return "unspecified"

    markets = historical_data["Market Name"].dropna().astype(str).str.strip().unique()
    if len(markets) == 1:
        return str(markets[0])
    return "unspecified"


def generate_agrolink_price(
    historical_data: pd.DataFrame,
    p_lags: int | None,
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
    """Generate a VAR base price and pass it into the fair-price engine."""

    base_price = predict_base_price(historical_data, p_lags)
    if isinstance(base_price, bool) or not isinstance(base_price, (int, float)):
        raise TypeError("predict_base_price must return a numeric base price.")
    if base_price < 0:
        raise ValueError("predict_base_price returned a negative base price.")

    report = get_model_report(historical_data, p_lags=p_lags)
    pricing = calculate_price_from_var_base(
        var_base_price=base_price,
        total_regional_supply=total_regional_supply,
        total_regional_demand=total_regional_demand,
        quality_grade=quality_grade,
        quality_multipliers=quality_multipliers,
        location_multiplier=location_multiplier,
        total_transport_cost=total_transport_cost,
        quantity_kg=quantity_kg,
        dsr_sensitivity=dsr_sensitivity,
        band_lower_offset=band_lower_offset,
        band_upper_offset=band_upper_offset,
    )

    return {
        "commodity": "Tomato",
        "market": _market_name(historical_data),
        "forecast_model": report["selected_model"],
        "forecast_lag": report["selected_lag"],
        "var_base_price": pricing["var_base_price"],
        "dsr": pricing["dsr"],
        "dsr_multiplier": pricing["dsr_multiplier"],
        "quality_multiplier": pricing["quality_multiplier"],
        "location_multiplier": pricing["location_multiplier"],
        "transport_cost_per_quintal": pricing["transport_cost_per_quintal"],
        "fair_price": pricing["fair_price"],
        "price_band": {
            "min": pricing["min_price"],
            "fair": pricing["fair_price"],
            "max": pricing["max_price"],
        },
    }


def _run_demonstration() -> None:
    """Run a real Tomato VAR forecast followed by the example fair-price pipeline."""

    csv_path = Path(__file__).resolve().parents[1] / "data" / "Tomato.csv"
    raw = load_mandi_csv(str(csv_path))
    candidates = find_dense_markets(
        raw,
        min_months=60,
        min_coverage=0.70,
        top_n=10,
    )
    selected = candidates[
        (candidates["State Name"].astype(str).str.casefold() == "karnataka")
        & (candidates["Market Name"].astype(str).str.casefold() == "davangere")
        & (candidates["Variety"].astype(str).str.casefold() == "tomato")
    ]
    if selected.empty:
        msg = "Karnataka / Davangere / Tomato is not a dense market candidate."
        raise ValueError(msg)

    state = str(selected.iloc[0]["State Name"])
    market = str(selected.iloc[0]["Market Name"])
    variety = str(selected.iloc[0]["Variety"])
    cleaned = clean_mandi_data(raw, state=state, market=market, variety=variety)
    historical_data = create_monthly_series(cleaned)
    historical_data["State Name"] = state
    historical_data["Market Name"] = market

    example_parameters = {
        "total_regional_supply": 9000,
        "total_regional_demand": 10000,
        "quality_grade": "A",
        "quality_multipliers": {"A": 1.05, "B": 1.00, "C": 0.95},
        "location_multiplier": 1.00,
        "total_transport_cost": 800,
        "quantity_kg": 500,
        "dsr_sensitivity": 0.10,
        "band_lower_offset": 25,
        "band_upper_offset": 25,
    }

    result = generate_agrolink_price(
        historical_data=historical_data,
        p_lags=None,
        **example_parameters,
    )

    print("=" * 40)
    print("AGROLINK PRICE PIPELINE")
    print("=" * 40)
    print("Commodity: Tomato")
    print(f"State: {state}")
    print(f"Market: {market}")
    print("Configurable demonstration inputs (not calibrated market values):")
    print(
        "  Supply / demand: "
        f"{example_parameters['total_regional_supply']} / "
        f"{example_parameters['total_regional_demand']}"
    )
    print(
        "  Quality grade / multipliers: "
        f"{example_parameters['quality_grade']} / "
        f"{example_parameters['quality_multipliers']}"
    )
    print(
        "  Location multiplier: "
        f"{example_parameters['location_multiplier']:.2f}"
    )
    print(
        "  Total transport cost: "
        f"INR {example_parameters['total_transport_cost']:.2f} "
        f"for {example_parameters['quantity_kg']} kg"
    )
    print(f"  DSR sensitivity: {example_parameters['dsr_sensitivity']:.2f}")
    print(
        "  Band offsets: "
        f"-{example_parameters['band_lower_offset']:.2f} / "
        f"+{example_parameters['band_upper_offset']:.2f} INR/quintal"
    )
    print()
    print(f"VAR Model: {result['forecast_model']}")
    print(f"VAR Lag: {result['forecast_lag']}")
    print(f"VAR Base Price: INR {result['var_base_price']:.2f}/quintal")
    print(f"DSR: {result['dsr']:.4f}")
    print(f"DSR Multiplier: {result['dsr_multiplier']:.4f}")
    print(f"Quality Multiplier: {result['quality_multiplier']:.4f}")
    print(f"Location Multiplier: {result['location_multiplier']:.4f}")
    print(
        "Transport Cost / Quintal: "
        f"INR {result['transport_cost_per_quintal']:.2f}"
    )
    print(f"Fair Price: INR {result['fair_price']:.2f}/quintal")
    print("Price Band:")
    print(f"    Min : INR {result['price_band']['min']:.2f}")
    print(f"    Fair: INR {result['price_band']['fair']:.2f}")
    print(f"    Max : INR {result['price_band']['max']:.2f}")
    print("=" * 40)


if __name__ == "__main__":
    _run_demonstration()