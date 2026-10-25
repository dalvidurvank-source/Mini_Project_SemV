"""Reproduce the complete source audit and per-series eligibility report.

Run: python -m backend.report_price_only
All reported prices/errors remain in original source units, not assumed INR.
"""
import csv
import json
from pathlib import Path

from forecasting.price_only import Policy, cached_backtest, market_catalog, source_data, unit_configuration


def generate(output=None):
    output = Path(output) if output else Path(__file__).resolve().parents[1] / 'reports'
    output.mkdir(parents=True, exist_ok=True)
    _, audit = source_data()
    policy = Policy.environment()
    details, summary = [], []
    for market in market_catalog():
        report = cached_backtest(market['market_id'], market['variety'], policy)
        details.append({'market':market, 'backtest':report})
        model = report.get('selected_model')
        select = report.get('selection',{}).get(model,{})
        final = report.get('evaluation',{})
        summary.append({**market, 'status':report['status'], 'reason':report.get('reason'),
                        'segment_sessions':report.get('segment_sessions'), 'segment_start':report.get('segment_start'),
                        'forecast_origin':report.get('forecast_origin'), 'target':'Next reporting session; calendar date unknown',
                        'missing_calendar_days':report.get('missing_calendar_days'),
                        'excluded_earlier_sessions':report.get('gap_info',{}).get('excluded_earlier_sessions'),
                        'selected_model':model, 'prediction_source_units':report.get('prediction'),
                        'selection_MAE_source_units':select.get('MAE'), 'selection_targets':select.get('count'),
                        'final_MAE_source_units':final.get('MAE'), 'final_RMSE_source_units':final.get('RMSE'),
                        'final_targets':final.get('count'), 'final_first_target':final.get('first_target'),
                        'final_last_target':final.get('last_target'),
                        'baseline_final_MAE_source_units':report.get('baseline_evaluation',{}).get('MAE')})
    full = {'source_audit':audit, 'units':unit_configuration(), 'policy':vars(policy),
            'semantics':'One reporting session, not one calendar day. No target date assigned. Prices and errors below use original source units.',
            'eligible_count':sum(r['status']=='eligible' for r in summary), 'series_count':len(summary), 'series':details}
    (output / 'price_only_backtesting.json').write_text(json.dumps(full,indent=2,allow_nan=False),encoding='utf-8')
    with (output / 'price_only_eligibility.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(f"Eligible: {full['eligible_count']} / {full['series_count']}. Reports written to {output}")
    return full


if __name__ == '__main__':
    generate()
