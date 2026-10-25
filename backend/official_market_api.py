"""Read-only API service over normalized official market observations."""
from datetime import date
from copy import deepcopy
from pathlib import Path
import os

import pandas as pd

from backend.market_data import observations, status
from forecasting.price_only import Policy, backtest


def _frame():
    rows = observations()
    columns = ["source","market_key","state","district","market","commodity",
               "variety","grade","observation_date","retrieved_at","min_price",
               "max_price","modal_price","currency","weight_unit","unit_evidence",
               "provenance"]
    data = pd.DataFrame(rows, columns=columns)
    if data.empty:
        return data
    data["t"] = pd.to_datetime(data["observation_date"], format="%Y-%m-%d")
    data["p_min"] = data["min_price"].astype(float)
    data["p_max"] = data["max_price"].astype(float)
    data["p_modal"] = data["modal_price"].astype(float)
    data["cmdty"] = data["commodity"]
    data["market_id"] = data["market_key"]
    data["market_name"] = data["market"]
    data["state_name"] = data["state"]
    data["district_name"] = data["district"]
    # The source contract provides labels but no numeric location IDs.  These
    # exact labels satisfy the shared series-consistency checks without
    # inventing identifiers.
    data["state_id"] = data["state"]
    data["district_id"] = data["district"]
    data["source_files"] = data.apply(lambda r: [f"raw import {r.retrieved_at}"], axis=1)
    return data


def catalog():
    data = _frame()
    if data.empty:
        markets = []
    else:
        records = data[["state","district","market","market_key","variety","grade"]].drop_duplicates().sort_values(
            ["state","district","market","variety","grade"], na_position="last").rename(
            columns={"market_key":"market_id"})
        markets = records.astype(object).where(pd.notna(records), None).to_dict("records")
    return {"crops":["Tomato"], "markets":markets,
            "quality_grades":["Unspecified","A","B","C"], "persistence":True,
            "weather":{"available":False,"reason":"No live weather source is configured."},
            "source_id":"official", "source_status":status(),
            "methods":[{"id":"auto","label":"Backtest-selected: last price / recent mean / exponential smoothing"}],
            "modes":["recorded","historical","future"],
            "supported_horizons":[{"value":1,"unit":"reporting_session","target_date":None}]}


def selection(p):
    data = _frame()
    market_id = p.get("market_id")
    rows = data[(data.market_key == market_id) & (data.variety == p.get("variety"))].copy()
    requested_grade = p.get("market_grade") or None
    rows = rows[rows.grade.fillna("") == (requested_grade or "")]
    if rows.empty:
        raise ValueError("Unknown official market identity / variety / grade combination.")
    for key in ("state","district","market"):
        if not p.get(key) or not rows[key].eq(p[key]).all():
            raise ValueError(f"{key} does not match the selected official identity. No substitution was made.")
    return rows.sort_values("t")


def _unit(rows):
    values = rows[["currency","weight_unit","unit_evidence"]].drop_duplicates()
    configured = len(values) == 1 and values.notna().all(axis=None)
    if configured:
        row = values.iloc[0]
        unit = f"{row.currency}/{row.weight_unit}"
        return {"configured":True,"unit":unit,"currency":row.currency,
                "weight_unit":row.weight_unit,"evidence":row.unit_evidence,"reason":None}
    return {"configured":False,"unit":"unverified source price units",
            "currency":None,"weight_unit":None,"evidence":None,
            "reason":"The official API schema does not declare currency or weight unit. Import an official CSV with explicit unit headers, or supply documented unit evidence during import, before fair-price conversion."}


def _conflict(rows):
    return rows.groupby("t")[["p_min","p_max","p_modal"]].nunique().max(axis=1).gt(1).any()


def _public_provenance(value):
    text = str(value)
    if "\\" in text or "/" in text:
        return "Archived official import: " + Path(text).name
    return text


def context(p):
    rows = selection(p)
    units = _unit(rows)
    factor = 0.01 if units["unit"] == "INR/quintal" else 1 if units["unit"] == "INR/kg" else 1
    latest = rows.t.max().date()
    age = (date.today() - latest).days
    policy = Policy.environment()
    report = backtest(rows, policy) if not _conflict(rows) else {
        "status":"unavailable", "reason":"Conflicting official observations exist for the same market, variety, grade and date. Resolve the import conflict first.",
        "policy":vars(policy), "horizon":{"value":1,"unit":"reporting_session"}}
    freshness_days = int(os.environ.get("AGROLINK_FRESHNESS_DAYS", "7"))
    if freshness_days < 0:
        raise ValueError("AGROLINK_FRESHNESS_DAYS must be non-negative")
    eligibility = {k:v for k,v in report.items() if k != "prediction"}
    return {"source_id":"official", "source":"Official data.gov.in / AGMARKNET records stored locally",
            "resource_id":status().get("resource_id"), "market_identifier_kind":"AgroLink internal key over the exact official identity; the source supplies no market ID",
            "latest_observation":latest.isoformat(), "age_days":age,
            "freshness_days":freshness_days, "stale":age > freshness_days,
            "observed_sessions":int(rows.t.nunique()), "frequency":"reporting_session",
            "forecast_origin":latest.isoformat(), "forecast_date":None,
            "unit":"INR/kg" if units["configured"] else "unverified source price units",
            "units":units, "retrieval_timestamps":sorted(rows.retrieved_at.unique().tolist()),
            "history":[{"date":r.t.date().isoformat(),"min_price":float(r.p_min)*factor,
                        "max_price":float(r.p_max)*factor,"modal_price":float(r.p_modal)*factor,
                        "price":float(r.p_modal)*factor,"grade":r.grade,
                        "retrieved_at":r.retrieved_at,"provenance":_public_provenance(r.provenance)}
                       for r in rows.itertuples()],
            "eligibility":eligibility,
            "can_recommend":report.get("status") == "eligible" and units["configured"] and age <= freshness_days,
            "weather":catalog()["weather"]}


def analyze(p):
    mode = p.get("mode")
    if mode not in ("recorded","historical","future"):
        raise ValueError("Select recorded, historical or future mode explicitly.")
    rows = selection(p)
    ctx = context(p)
    target = p.get("target_date") or ""
    if mode in ("recorded","historical"):
        try:
            target_ts = pd.Timestamp(date.fromisoformat(target))
        except (TypeError, ValueError):
            raise ValueError("A valid recorded target date is required.")
        actual_rows = rows[rows.t == target_ts]
        if actual_rows.empty:
            raise ValueError("No recorded observation exists for the requested date and exact market identity.")
        if _conflict(actual_rows):
            raise ValueError("Conflicting records exist for the requested date.")
        actual = actual_rows.iloc[0]
        actual_payload = {"date":target,"min_price":float(actual.p_min),
                          "max_price":float(actual.p_max),"modal_price":float(actual.p_modal),
                          "unit":ctx["units"]["unit"],"retrieved_at":actual.retrieved_at,
                          "grade":actual.grade,"provenance":_public_provenance(actual.provenance)}
        if mode == "recorded":
            return {"kind":"recorded_price","mode":mode,"context":ctx,
                    "actual":actual_payload,"forecast":None,
                    "warnings":["This is recorded market data, not a forecast."]}
        training = rows[rows.t < target_ts]
        if training.empty:
            raise ValueError("No observations strictly before the target date are available for training.")
        report = backtest(training, Policy.environment())
        if report["status"] != "eligible":
            raise ValueError("Historical forecast unavailable: " + report["reason"])
        return _forecast_result(mode, p, ctx, report, actual_payload, target,
                                training.t.max().date().isoformat())
    if target:
        raise ValueError("Future forecasts use the next reporting session; clear the exact target date.")
    if ctx["stale"] and p.get("acknowledge_stale") is not True:
        raise ValueError(f"Acknowledge the stale-data limitation: latest observation is {ctx['age_days']} days old; freshness policy allows {ctx['freshness_days']}.")
    report = backtest(rows, Policy.environment())
    if report["status"] != "eligible":
        raise ValueError("Future forecast unavailable: " + report["reason"])
    result = _forecast_result(mode, p, ctx, report, None, None,
                              rows.t.max().date().isoformat())
    if ctx["stale"]:
        result["warnings"].insert(0, "This is a stale-data next-session projection from the historical forecast origin, not a current market-price forecast.")
    return result


def _forecast_result(mode, p, ctx, report, actual, target_date, training_end):
    prediction = float(report["prediction"])
    report_view = deepcopy(report)
    if mode == "historical":
        report_view["warnings"] = [w for w in report_view["warnings"] if not w.startswith("Forecast is for the next reporting session")]
        report_view["warnings"].insert(0, f"Forecast targets the recorded reporting session {target_date}; training ends strictly before it.")
    forecast = {"source_id":"official","name":report["selected_model"],
                "prediction_native":prediction,
                "metrics":{k:report["evaluation"][k] for k in ("MAE","RMSE")},
                "metric_unit":ctx["units"]["unit"],"report":report_view,
                "origin":training_end,"target_label":target_date or "Next reporting session (calendar date unknown)",
                "horizon":{"value":1,"unit":"reporting_session"},
                "forecast_date":target_date}
    warnings = list(report_view["warnings"])
    if mode == "historical":
        warnings.append("Training used only observations strictly before the target date. Historical publication availability timestamps are unavailable, so this is not claimed as a fully point-in-time simulation.")
    return {"kind":"market_forecast","mode":mode,"crop":"Tomato",
            "market":p["market"],"variety":p["variety"],"context":ctx,
            "actual":actual,"forecast":forecast,"warnings":warnings,
            "training":{"first_date":report["segment_start"],"last_date":training_end,
                        "sessions":report["segment_sessions"],"strictly_before_target":True}}
