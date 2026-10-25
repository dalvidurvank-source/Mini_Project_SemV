"""Leakage-safe monthly crop-price model selection and forecasting.

This module deliberately keeps evaluation and future fitting separate.  Candidate
selection uses rolling origins before a final holdout; the holdout never chooses a
model.  Missing calendar months are regularized inside each training fold by the
legacy VAR preparation code, so future observations cannot influence imputation.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

from forecasting.var_forecaster import (
    MODEL_COLUMNS,
    _fit_and_forecast_model,
    choose_lag_order,
    prepare_for_var,
)

CANDIDATES = ("last_observed", "seasonal_naive", "recent_mean", "exponential_smoothing", "VAR_LEVEL", "VAR_LOG")
BASELINES = CANDIDATES[:4]
SUPPORTED_HORIZONS = (1, 2, 3)
MIN_MONTHS = 48
SELECTION_MONTHS = 12
HOLDOUT_MONTHS = 6
MIN_RESIDUALS_FOR_BAND = 5


def _monthly(data: pd.DataFrame) -> pd.DataFrame:
    if not set(MODEL_COLUMNS).issubset(data.columns):
        raise ValueError(f"Monthly data must contain {MODEL_COLUMNS}.")
    result = data[MODEL_COLUMNS].copy()
    result.index = pd.to_datetime(result.index).to_period("M").to_timestamp()
    result = result[~result.index.duplicated(keep="last")].sort_index()
    result = result.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    result = result[(result.wholesale_price > 0) & (result.arrival_volume >= 0)]
    if len(result) < MIN_MONTHS:
        raise ValueError(f"At least {MIN_MONTHS} valid observed months are required; found {len(result)}.")
    if result.index[-1].to_period("M").ordinal - result.index[0].to_period("M").ordinal + 1 > len(result) / 0.85:
        raise ValueError("Monthly coverage is below 85%; VAR and calendar-horizon evaluation are unavailable.")
    return result


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "MAE": None, "RMSE": None}
    errors = np.asarray([r["prediction"] - r["actual"] for r in rows], dtype=float)
    return {"count": len(rows), "MAE": float(np.mean(np.abs(errors))), "RMSE": float(np.sqrt(np.mean(errors ** 2)))}


def _baseline(history: pd.DataFrame, name: str, steps: int) -> list[float]:
    price = history.wholesale_price.astype(float)
    if name == "last_observed":
        return [float(price.iloc[-1])] * steps
    if name == "seasonal_naive":
        if len(price) < 12:
            raise ValueError("Seasonal naive requires at least 12 months.")
        return [float(price.iloc[-12 + ((i - 1) % 12)]) for i in range(1, steps + 1)]
    if name == "recent_mean":
        return [float(price.iloc[-3:].mean())] * steps
    if name == "exponential_smoothing":
        if len(price) >= 24:
            fit = ExponentialSmoothing(price.to_numpy(), trend=None, seasonal="add", seasonal_periods=12, initialization_method="estimated").fit(optimized=True)
        else:
            fit = SimpleExpSmoothing(price.to_numpy(), initialization_method="estimated").fit(optimized=True)
        return [max(0.0, float(v)) for v in fit.forecast(steps)]
    raise ValueError(f"Unknown baseline {name!r}.")


def _var(history: pd.DataFrame, name: str, lag: int, steps: int) -> tuple[list[float], list[float]]:
    report = _fit_and_forecast_model(history, p_lags=lag, transform_log=name == "VAR_LOG", steps=steps)
    return report["predicted_prices"], report["predicted_arrivals"]


def _safe_lag(history: pd.DataFrame, transform_log: bool) -> int:
    prepared, _, _, _, _ = prepare_for_var(history, transform_log=transform_log)
    return choose_lag_order(prepared, max_lags=6)


def _evaluate(data: pd.DataFrame, targets: pd.DatetimeIndex, lags: dict[str, int]) -> tuple[dict[str, dict[int, list[dict[str, Any]]]], dict[str, str]]:
    rows: dict[str, dict[int, list[dict[str, Any]]]] = {name: defaultdict(list) for name in CANDIDATES}
    failures: dict[str, str] = {}
    for target in targets:
        for horizon in SUPPORTED_HORIZONS:
            origin = (target.to_period("M") - horizon).to_timestamp()
            history = data[data.index <= origin]
            actual_row = data[data.index == target]
            if history.empty or actual_row.empty:
                continue
            actual = float(actual_row.wholesale_price.iloc[0])
            for name in CANDIDATES:
                if name in failures:
                    continue
                try:
                    if name.startswith("VAR_"):
                        predicted, arrivals = _var(history, name, lags[name], horizon)
                        value, arrival = predicted[-1], arrivals[-1]
                    else:
                        value, arrival = _baseline(history, name, horizon)[-1], None
                    if np.isfinite(value):
                        rows[name][horizon].append({"origin": origin.strftime("%Y-%m"), "target": target.strftime("%Y-%m"), "actual": actual, "prediction": float(value), "arrival_prediction": arrival})
                except (ValueError, TypeError, np.linalg.LinAlgError) as exc:
                    failures[name] = str(exc)
    return rows, failures


def _summarize(rows: dict[str, dict[int, list[dict[str, Any]]]]) -> dict[str, Any]:
    report = {}
    for name in CANDIDATES:
        by_horizon = {str(h): _metrics(rows[name][h]) for h in SUPPORTED_HORIZONS}
        combined = [row for h in SUPPORTED_HORIZONS for row in rows[name][h]]
        report[name] = {**_metrics(combined), "by_horizon": by_horizon}
    return report


def forecast_monthly(data: pd.DataFrame, horizon: int = 1) -> dict[str, Any]:
    """Select on rolling origins, freeze, evaluate on a holdout, then forecast."""
    if not isinstance(horizon, int) or horizon not in SUPPORTED_HORIZONS:
        raise ValueError("horizon must be 1, 2, or 3 calendar months.")
    monthly = _monthly(data)
    observed = monthly.index
    holdout_targets = observed[-HOLDOUT_MONTHS:]
    selection_targets = observed[-(HOLDOUT_MONTHS + SELECTION_MONTHS):-HOLDOUT_MONTHS]
    initial_training = monthly[monthly.index < selection_targets[0]]
    selection_lags = {name: _safe_lag(initial_training, name == "VAR_LOG") for name in ("VAR_LEVEL", "VAR_LOG")}
    selection_rows, selection_failures = _evaluate(monthly, selection_targets, selection_lags)
    selection = _summarize(selection_rows)
    eligible = [name for name in CANDIDATES if selection[name]["count"] and name not in selection_failures and selection[name]["MAE"] is not None]
    if not eligible:
        raise ValueError("No candidate produced enough leakage-safe validation forecasts.")
    winner = min(eligible, key=lambda name: (selection[name]["MAE"], selection[name]["RMSE"], CANDIDATES.index(name)))

    freeze_training = monthly[monthly.index < holdout_targets[0]]
    frozen_lags = {name: _safe_lag(freeze_training, name == "VAR_LOG") for name in ("VAR_LEVEL", "VAR_LOG")}
    holdout_rows, holdout_failures = _evaluate(monthly, holdout_targets, frozen_lags)
    holdout = _summarize(holdout_rows)
    if not holdout[winner]["count"]:
        raise ValueError(f"Frozen winner {winner} could not be evaluated on the final holdout.")

    if winner.startswith("VAR_"):
        prices, arrivals = _var(monthly, winner, frozen_lags[winner], horizon)
        lag = frozen_lags[winner]
    else:
        prices, arrivals, lag = _baseline(monthly, winner, horizon), [None] * horizon, None

    origin = observed[-1].to_period("M")
    forecasts = []
    for step in range(1, horizon + 1):
        residuals = [r["actual"] - r["prediction"] for r in selection_rows[winner][step]]
        band = None
        if len(residuals) >= MIN_RESIDUALS_FOR_BAND:
            low, high = np.quantile(np.asarray(residuals), [0.10, 0.90])
            band = {"level": "empirical_80_percent", "lower": max(0.0, float(prices[step - 1] + low)), "upper": max(0.0, float(prices[step - 1] + high)), "residual_count": len(residuals)}
        forecasts.append({
            "horizon_months": step,
            "origin_date": origin.to_timestamp(how="end").date().isoformat(),
            "target_month": (origin + step).strftime("%Y-%m"),
            "prediction_inr_per_quintal": float(prices[step - 1]),
            "arrival_prediction_tonnes": arrivals[step - 1],
            "model": winner,
            "lag": lag,
            "training_range": {"start": observed[0].strftime("%Y-%m"), "end": observed[-1].strftime("%Y-%m"), "observed_months": len(monthly)},
            "MAE": holdout[winner]["by_horizon"][str(step)]["MAE"],
            "RMSE": holdout[winner]["by_horizon"][str(step)]["RMSE"],
            "baseline_comparison": {name: holdout[name]["by_horizon"][str(step)] for name in BASELINES},
            "prediction_band": band,
            "warnings": [] if band else ["Uncertainty unavailable: fewer than five rolling validation residuals exist for this horizon."],
        })
    return {
        "selected_model": winner,
        "selected_lag": lag,
        "selection": selection,
        "final_holdout": holdout,
        "selection_failures": selection_failures,
        "holdout_failures": holdout_failures,
        "partitions": {"selection_targets": [d.strftime("%Y-%m") for d in selection_targets], "holdout_targets": [d.strftime("%Y-%m") for d in holdout_targets], "model_frozen_before": holdout_targets[0].strftime("%Y-%m")},
        "forecasts": forecasts,
    }
