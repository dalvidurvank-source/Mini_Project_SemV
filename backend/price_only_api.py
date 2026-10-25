"""Price-only API contracts, kept separate from the existing VAR adapter."""
from datetime import date
from copy import deepcopy
import math
import os
import pandas as pd

from forecasting.price_only import (Policy, backtest, cached_backtest, market_catalog,
                                    series_for, source_data, unit_configuration)


def catalog():
    return {'crops':['Tomato'], 'markets':market_catalog(),
            'quality_grades':['Unspecified','A','B','C'], 'persistence':False,
            'weather':{'available':False,'reason':'No live weather source is configured.'},
            'source_id':'price_only', 'units':unit_configuration(),
            'modes':['recorded','historical','future'],
            'methods':[{'id':'auto','label':'Backtest-selected: last price / recent mean / exponential smoothing'}],
            'supported_horizons':[{'value':1,'unit':'reporting_session','target_date':None}]}


def selection(p):
    if p.get('crop','Tomato') != 'Tomato':
        raise ValueError('Only Tomato is supported.')
    if not isinstance(p.get('variety'), str) or not str(p.get('market_id','')).isdigit():
        raise ValueError('A valid market ID and variety are required.')
    rows = series_for(str(p['market_id']), p['variety'])
    for key, col in [('state','state_name'),('district','district_name'),('market','market_name')]:
        if not p.get(key) or not rows[col].eq(p[key]).all():
            raise ValueError(f'{key} does not match the selected market ID. No substitution was made.')
    return rows


def context(p):
    rows = selection(p)
    report = cached_backtest(str(p['market_id']), p['variety'], Policy.environment())
    config = unit_configuration()
    factor = 1 if config['unit'] == 'INR/kg' else 0.01 if config['unit'] == 'INR/quintal' else None
    latest = rows.t.max().date()
    age = (date.today() - latest).days
    freshness_days = int(os.environ.get('AGROLINK_FRESHNESS_DAYS','7'))
    if freshness_days < 0:
        raise ValueError('AGROLINK_FRESHNESS_DAYS must be non-negative.')
    # The full forecast value is released only by the acknowledged analysis action.
    eligibility = {k:v for k,v in report.items() if k != 'prediction'}
    files = sorted({f for values in rows.source_files for f in values})
    return {'source_id':'price_only', 'source':'Repository price-only CSV exports; completeness is unverified. Units follow the recorded confirmation.' if config['configured'] else 'Repository price-only CSV exports; upstream completeness and units require confirmation.',
            'source_files':files, 'latest_observation':latest.isoformat(), 'age_days':age,
            'freshness_days':freshness_days, 'stale':age > freshness_days,
            'observed_sessions':len(rows), 'frequency':'reporting_session', 'forecast_month':None,
            'forecast_origin': report.get('forecast_origin',latest.isoformat()), 'forecast_date':None,
            'unit':'INR/kg' if factor is not None else 'unverified source price units', 'units':config,
            'history':[{'date':r.t.date().isoformat(),
                        'min_price':float(r.p_min) * factor if factor is not None else float(r.p_min),
                        'max_price':float(r.p_max) * factor if factor is not None else float(r.p_max),
                        'modal_price':float(r.p_modal) * factor if factor is not None else float(r.p_modal),
                        'price':float(r.p_modal) * factor if factor is not None else float(r.p_modal),
                        'source_files':r.source_files} for r in rows.itertuples()],
            'eligibility':eligibility, 'can_recommend': report['status'] == 'eligible' and config['configured'],
            'weather':catalog()['weather']}


def analyze(p):
    """Recorded, historical-target, or fresh future reporting-session result."""
    mode = p.get('mode')
    if mode not in ('recorded','historical','future'):
        raise ValueError('Select recorded, historical or future mode explicitly.')
    rows = selection(p).sort_values('t')
    ctx = context(p)
    target = p.get('target_date') or ''
    if mode in ('recorded','historical'):
        try:
            target_ts = pd.Timestamp(date.fromisoformat(target))
        except (TypeError, ValueError):
            raise ValueError('A valid recorded target date is required.')
        matches = rows[rows.t == target_ts]
        if matches.empty:
            raise ValueError('No recorded observation exists for the requested date and exact market identity.')
        prices = matches[['p_min','p_max','p_modal']].drop_duplicates()
        if len(prices) != 1:
            raise ValueError('Conflicting records exist for the requested date.')
        actual_row = matches.iloc[0]
        actual = {'date':target,'min_price':float(actual_row.p_min),
                  'max_price':float(actual_row.p_max),'modal_price':float(actual_row.p_modal),
                  'unit':ctx['units']['unit'],'source_files':actual_row.source_files}
        if mode == 'recorded':
            return {'kind':'recorded_price','mode':mode,'context':ctx,'actual':actual,
                    'forecast':None,'warnings':['This is recorded market data, not a forecast.']}
        training = rows[rows.t < target_ts]
        if training.empty:
            raise ValueError('No observations strictly before the target date are available for training.')
        report = backtest(training, Policy.environment())
        if report['status'] != 'eligible':
            raise ValueError('Historical forecast unavailable: ' + report['reason'])
        result = _analysis_forecast(p, ctx, report, actual, target,
                                    training.t.max().date().isoformat(), mode)
        result['warnings'].append('Historical publication availability timestamps are unavailable, so this is not claimed as a fully point-in-time simulation.')
        return result
    if target:
        raise ValueError('Future forecasts use the next reporting session; clear the exact target date.')
    if ctx['stale'] and p.get('acknowledge_stale') is not True:
        raise ValueError(f"Acknowledge the stale-data limitation: latest observation is {ctx['age_days']} days old; freshness policy allows {ctx['freshness_days']}.")
    report = cached_backtest(str(p['market_id']), p['variety'], Policy.environment())
    if report['status'] != 'eligible':
        raise ValueError('Future forecast unavailable: ' + report['reason'])
    result = _analysis_forecast(p, ctx, report, None, None, ctx['forecast_origin'], mode)
    if ctx['stale']:
        result['warnings'].insert(0, 'This is a stale-data next-session projection from the historical forecast origin, not a current market-price forecast.')
    return result


def _analysis_forecast(p, ctx, report, actual, target_date, training_end, mode):
    prediction = float(report['prediction'])
    report_view = deepcopy(report)
    if mode == 'historical':
        report_view['warnings'] = [w for w in report_view['warnings'] if not w.startswith('Forecast is for the next reporting session')]
        report_view['warnings'].insert(0, f'Forecast targets the recorded reporting session {target_date}; training ends strictly before it.')
    forecast_result = {'source_id':'price_only','name':report['selected_model'],
        'prediction_native':prediction,
        'metrics':{k:report['evaluation'][k] for k in ('MAE','RMSE')},
        'metric_unit':ctx['units']['unit'],'report':report_view,'origin':training_end,
        'target_label':target_date or 'Next reporting session (calendar date unknown)',
        'horizon':{'value':1,'unit':'reporting_session'},'forecast_date':target_date}
    return {'kind':'market_forecast','mode':mode,'crop':'Tomato','market':p['market'],
            'variety':p['variety'],'context':ctx,'actual':actual,
            'forecast':forecast_result,'warnings':list(report_view['warnings']),
            'training':{'first_date':report['segment_start'],'last_date':training_end,
                        'sessions':report['segment_sessions'],'strictly_before_target':True}}


def forecast(p, ctx=None):
    ctx = ctx or context(p)
    if p.get('method','auto') != 'auto':
        raise ValueError('Only backtest-selected auto mode is supported; a model cannot bypass evaluation.')
    if isinstance(p.get('horizon',1), bool) or p.get('horizon',1) != 1 or p.get('horizon_unit','reporting_session') != 'reporting_session':
        raise ValueError('Only one subsequent reporting session is supported; no calendar date is assigned.')
    if p.get('selling_date'):
        raise ValueError('Price-only forecasts have no known selling date. Clear the calendar-date request and explicitly select the next reporting session.')
    if p.get('harvest_date'):
        try:
            harvest = date.fromisoformat(p['harvest_date'])
        except (TypeError, ValueError):
            raise ValueError('Harvest date is invalid.')
        if harvest > date.fromisoformat(ctx['forecast_origin']):
            raise ValueError('Historical harvest date must be on or before the forecast origin. No 2026 forecast is available.')
    if ctx['stale'] and p.get('acknowledge_stale') is not True:
        raise ValueError('Acknowledge stale observations before running historical analysis.')
    report = cached_backtest(str(p['market_id']), p['variety'], Policy.environment())
    if report['status'] != 'eligible':
        raise ValueError(report['reason'])
    prediction = report['prediction']
    if not math.isfinite(prediction) or prediction <= 0:
        raise ValueError('Unusable forecast output.')
    return {'source_id':'price_only', 'name':report['selected_model'], 'prediction_native':prediction,
            'metrics':{k:v for k,v in report['evaluation'].items() if k in ('MAE','RMSE')},
            'metric_unit':ctx['units']['unit'], 'report':report,
            'origin':ctx['forecast_origin'], 'target_label':'Next reporting session (calendar date unknown)',
            'horizon':{'value':1,'unit':'reporting_session'}, 'forecast_date':None}


def preview(p):
    ctx = context(p)
    result = forecast(p, ctx)
    return {'kind':'forecast_preview','crop':'Tomato','market':p['market'],'variety':p['variety'],
            'context':ctx,'forecast':result,'warnings':result['report']['warnings'] +
            ([ctx['units']['reason']] if not ctx['units']['configured'] else [])}


def audit():
    _, files = source_data()
    return {'files':files,'unit_configuration':unit_configuration(),'policy':vars(Policy.environment())}
