"""Generate the market/horizon eligibility and source-contract report."""
from datetime import datetime, timezone
from pathlib import Path
import json

from backend import official_market_api, price_only_api
from backend.market_data import RESOURCE_ID, SOURCE_PAGE, status
from forecasting.price_only import Policy, cached_backtest, market_catalog


def generate(output=None):
    out = Path(output) if output else Path(__file__).resolve().parents[1] / "reports"
    out.mkdir(parents=True, exist_ok=True)
    policy = Policy.environment()
    root = []
    for market in market_catalog():
        report = cached_backtest(market["market_id"], market["variety"], policy)
        root.append({**market,"supported_mode":"recorded; historical when >= policy history; future only when fresh",
                     "supported_horizon":"1 reporting session; no calendar date",
                     "status":report["status"],"reason":report.get("reason"),
                     "sessions":report.get("segment_sessions"),"latest":report.get("forecast_origin"),
                     "selected_model":report.get("selected_model"),
                     "final_mae":report.get("evaluation",{}).get("MAE"),
                     "final_rmse":report.get("evaluation",{}).get("RMSE"),
                     "final_count":report.get("evaluation",{}).get("count"),
                     "baseline_final_mae":report.get("baseline_evaluation",{}).get("MAE")})
    official = []
    for market in official_market_api.catalog()["markets"]:
        ctx = official_market_api.context({**market,"market_grade":market.get("grade")})
        eligibility = ctx["eligibility"]
        official.append({**market,"supported_mode":"recorded",
                         "supported_horizon":"none until enough history is imported and evaluated",
                         "status":eligibility["status"],"reason":eligibility.get("reason"),
                         "sessions":ctx["observed_sessions"],"latest":ctx["latest_observation"],
                         "units":ctx["units"]["unit"],"fresh":not ctx["stale"]})
    pune_params={"source":"price_only","crop":"Tomato","state":"Maharashtra",
                 "district":"Pune","market":"Pune","market_id":"172","variety":"Local"}
    pune_context=price_only_api.context(pune_params)
    historical=price_only_api.analyze({**pune_params,"mode":"historical",
                                       "target_date":pune_context["latest_observation"]})
    official_market=official_market_api.catalog()["markets"][0] if official else None
    recorded=(official_market_api.analyze({**official_market,
              "market_grade":official_market.get("grade"),"mode":"recorded",
              "target_date":"2026-10-23"}) if official_market else None)
    tested_examples={"recorded":({"market":official_market["market"],
          "date":recorded["actual"]["date"],"modal_price":recorded["actual"]["modal_price"],
          "unit":recorded["actual"]["unit"],"forecast":recorded["forecast"]} if recorded else None),
      "historical":{"market":"Pune","market_id":"172",
          "target_date":historical["actual"]["date"],
          "training_last_date":historical["training"]["last_date"],
          "actual_modal":historical["actual"]["modal_price"],
          "forecast":historical["forecast"]["prediction_native"],
          "unit":historical["forecast"]["metric_unit"],
          "selected_model":historical["forecast"]["name"],
          "final_MAE":historical["forecast"]["metrics"]["MAE"],
          "final_RMSE":historical["forecast"]["metrics"]["RMSE"],
          "final_count":historical["forecast"]["report"]["evaluation"]["count"],
          "baseline_final_MAE":historical["forecast"]["report"]["baseline_evaluation"]["MAE"]}}
    result = {"generated_at":datetime.now(timezone.utc).isoformat(),
      "official_contract":{"source_page":SOURCE_PAGE,"resource_id":RESOURCE_ID,
        "endpoint":f"https://api.data.gov.in/resource/{RESOURCE_ID}",
        "authentication":"api-key query parameter required; personal key obtained after portal login",
        "sample_key_limit":"Official OAS text states maximum 10 records per response",
        "pagination":"offset and limit; importer advances by actual returned count and verifies total",
        "filters":["state.keyword","district","market","commodity","variety","grade"],
        "fields":["state","district","market","commodity","variety","grade","arrival_date","min_price","max_price","modal_price"],
        "tested_live":"2026-10-23 query for Maharashtra/Tomato returned 2 records, both dated 2026-10-23",
        "rate_limit":"HTTP 429 observed after live access; no numeric quota or Retry-After was published in the tested OAS page",
        "units":"Live API schema does not declare currency/weight unit; no unit is inferred",
        "market_ids":"No market identifier field is supplied; AgroLink hashes the exact identity for internal selection",
        "date_coverage":"Tested current resource behaved as a daily snapshot; it did not provide 60–90 historical sessions"},
      "local_store":status(),"policy":vars(policy),"tested_examples":tested_examples,
      "root_exports":root,"official_imports":official}
    (out/"market_horizon_eligibility.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    lines=["# Market and horizon eligibility report","",
      f"Generated: {result['generated_at']}","",
      "## Verified official-source contract","",
      f"- Resource: `{RESOURCE_ID}` ([official page]({SOURCE_PAGE})).",
      "- Authentication: `api-key` is required. A personal key requires portal login; the documented sample key is capped at 10 rows per response.",
      "- Pagination: `offset` and `limit`. The importer advances by the returned count, checks `count`, and refuses changing/truncated totals.",
      "- Available filters: state, district, market, commodity, variety and grade. No observation-date filter is exposed.",
      "- Fields: state, district, market, commodity, variety, grade, arrival date, minimum, maximum and modal price.",
      "- The API supplies no market ID and does not declare price currency/weight units. AgroLink does not infer either.",
      "- Live test on 2026-10-23 returned two Maharashtra tomato records dated 2026-10-23. A subsequent command received HTTP 429; the OAS page gave no numeric quota.",
      "- The current resource is a snapshot and did not supply 60–90 historical sessions. Import official historical CSV exports to build an eligible series.","",
      "## Tested examples","",
      f"- Recorded: {tested_examples['recorded']['market']} on {tested_examples['recorded']['date']} had modal price {tested_examples['recorded']['modal_price']} in unverified source units. The response contains `forecast: null`.",
      f"- Historical evaluation: Pune ID 172 target {tested_examples['historical']['target_date']}; training ended {tested_examples['historical']['training_last_date']}; actual {tested_examples['historical']['actual_modal']} and forecast {tested_examples['historical']['forecast']} {tested_examples['historical']['unit']}. The selected {tested_examples['historical']['selected_model']} model had final MAE {tested_examples['historical']['final_MAE']:.2f}, RMSE {tested_examples['historical']['final_RMSE']:.2f} over {tested_examples['historical']['final_count']} targets; last-price baseline MAE {tested_examples['historical']['baseline_final_MAE']:.2f}.","",
      "## Eligibility","",
      "| Source | Market / variety / grade | Sessions | Latest | Recorded | Historical evaluation | Future | Reason |",
      "| --- | --- | ---: | --- | --- | --- | --- | --- |"]
    for row in official:
        lines.append(f"| Official import | {row['market']} / {row['variety']} / {row.get('grade') or 'not supplied'} | {row['sessions']} | {row['latest']} | yes | no | no | {row['reason']} |")
    for row in root:
        hist = "yes" if row["status"] == "eligible" else "no"
        lines.append(f"| Root exports | {row['market']} (ID {row['market_id']}) / {row['variety']} | {row.get('sessions') or 0} | {row.get('latest') or 'n/a'} | yes | {hist} | no (stale) | {row.get('reason') or 'One-session model evaluated; future blocked by freshness'} |")
    lines += ["","Historical mode forecasts a known reporting session and always trains on dates strictly before the target. Publication timestamps are unavailable, so results are not described as fully point-in-time simulations.",
              "Future mode supports only one subsequent reporting session, never an exact calendar date. Longer horizons remain unavailable."]
    (out/"market_horizon_eligibility.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Wrote {len(root)} root and {len(official)} official series to {out}")
    return result


if __name__ == "__main__":
    generate()
