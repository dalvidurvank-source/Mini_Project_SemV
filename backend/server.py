"""Local MVP API. Run from the repository root: python -m backend.server."""
from datetime import date, datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import logging
import math
import os
from threading import RLock

# Each HTTP request may fit small statistical models. Large default BLAS thread
# pools oversubscribe this workload; explicit deployment settings still win.
for _thread_setting in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(_thread_setting,'1')

import pandas as pd
from backend import official_market_api, price_only_api
from backend.market_data import status as market_data_status
from forecasting.var_forecaster import load_mandi_csv, clean_mandi_data, create_monthly_series
from forecasting.monthly_forecaster import forecast_monthly
from logistics.transport_estimator import estimate_transport, legacy_batch_estimate
from pricing.fair_price_engine import calculate_fair_price, create_fair_price_band, calculate_transport_cost_per_quintal

CSV = Path(os.environ.get('AGROLINK_CSV', Path(__file__).resolve().parents[1] / 'data/raw/Tomato.csv'))


DATA_LOCK=RLock()


@lru_cache(maxsize=1)
def _load_dataset():
    return clean_mandi_data(load_mandi_csv(str(CSV)))


def dataset():
    # lru_cache alone permits concurrent cache misses to load duplicate copies.
    with DATA_LOCK:
        return _load_dataset()


@lru_cache(maxsize=1)
def _load_catalog():
    records = dataset()[['State Name', 'District Name', 'Market Name', 'Variety']].dropna().drop_duplicates()
    return {'crops': ['Tomato'], 'markets': [dict(zip(('state', 'district', 'market', 'variety'), row)) for row in records.itertuples(index=False, name=None)],
            'weather': {'available': False, 'reason': 'No live weather integration is configured.'},
            'persistence': False, 'quality_grades': ['Unspecified', 'A', 'B', 'C']}


def catalog():
    with DATA_LOCK:
        return _load_catalog()


def source_id(p):
    value = p.get('source','var')
    if value not in ('var','price_only','official'):
        raise ValueError('Unknown data source. Select VAR history, price-only exports, or official imports explicitly.')
    return value


def get_catalog(p):
    source = source_id(p)
    if source == 'price_only':
        return price_only_api.catalog()
    if source == 'official':
        return official_market_api.catalog()
    return catalog()


def selected(p):
    if p.get('crop', 'Tomato') != 'Tomato':
        raise ValueError('Only Tomato is supported by this dataset.')
    for key in ('state', 'district', 'market', 'variety'):
        if not isinstance(p.get(key), str) or not p[key].strip():
            raise ValueError(f'{key} is required.')
    data = dataset()
    mask = (data['State Name'] == p['state']) & (data['Market Name'] == p['market']) & (data['Variety'] == p['variety']) & (data['District Name'] == p['district'])
    rows = data.loc[mask].copy()
    if rows.empty:
        raise ValueError('The selected district and market combination is unavailable.')
    return rows


def context(p):
    if source_id(p) == 'price_only':
        return price_only_api.context(p)
    if source_id(p) == 'official':
        return official_market_api.context(p)
    rows = selected(p)
    monthly = create_monthly_series(rows, minimum_observations=0)
    last = rows['Reported Date'].max().date()
    forecast_month = (monthly.index[-1].to_period('M') + 1).strftime('%Y-%m') if len(monthly) else None
    age = (date.today() - last).days
    freshness_days = int(os.environ.get('AGROLINK_VAR_FRESHNESS_DAYS', '45'))
    forecast_months = [(monthly.index[-1].to_period('M') + step).strftime('%Y-%m') for step in (1, 2, 3)] if len(monthly) else []
    return {'source': 'Repository Tomato.csv (mandi observations; upstream provenance not verified)',
            'source_id': 'var', 'latest_observation': last.isoformat(), 'age_days': age, 'freshness_days': freshness_days, 'stale': age > freshness_days,
            'observed_months': len(monthly), 'forecast_month': forecast_month,
            'forecast_months': forecast_months, 'supported_horizons': [1, 2, 3],
            'history': [{'date': i.date().isoformat(), 'price': float(r.wholesale_price) / 100} for i, r in monthly.iterrows()],
            'weather': catalog()['weather'], 'unit': 'INR/kg'}


@lru_cache(maxsize=96)
def model(state, district, market, variety, horizon=1, as_of_month=None):
    rows = selected(dict(state=state, district=district, market=market, variety=variety))
    monthly = create_monthly_series(rows)
    if as_of_month:
        monthly = monthly[monthly.index <= pd.Period(as_of_month, freq='M').to_timestamp()]
    report = forecast_monthly(monthly, int(horizon))
    chosen = report['forecasts'][-1]
    base = float(chosen['prediction_inr_per_quintal'])
    if not math.isfinite(base) or base <= 0:
        raise ValueError('The model produced an unusable forecast. No recommendation is available.')
    return {'base': base, 'name': report['selected_model'], 'lag': report['selected_lag'],
            'origin': chosen['origin_date'], 'forecast_date': chosen['target_month'],
            'metrics': {'MAE': chosen['MAE'], 'RMSE': chosen['RMSE']},
            'forecasts': report['forecasts'], 'report': report, 'metric_unit': 'INR/quintal'}


def number(p, key, default=None):
    value = p.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f'{key} must be a number.')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{key} must be a number.')
    if not math.isfinite(result) or result < 0:
        raise ValueError(f'{key} must be finite and non-negative.')
    return result


def recommend(p):
    source = source_id(p)
    po = source in ('price_only','official')
    qty = number(p, 'quantity')
    if qty <= 0 or p.get('unit') not in ('kg', 'quintal'):
        raise ValueError('Quantity must be greater than zero, in kg or quintal.')
    if p.get('quality') not in get_catalog(p)['quality_grades']:
        raise ValueError('Select a valid quality grade.')
    try:
        harvest = date.fromisoformat(p['harvest_date'])
        selling = None if po or p.get('mode') == 'historical' else date.fromisoformat(p['selling_date'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Valid harvest and selling dates are required.')
    if selling is not None and selling < harvest:
        raise ValueError('Selling date must be on or after harvest date.')
    ctx = context(p)
    if ctx['stale'] and not po and p.get('mode') == 'future':
        raise ValueError(f"Current forecasts require an observation no older than {ctx['freshness_days']} days. Use historical mode for an explicitly historical evaluation; stale current forecasts cannot be acknowledged into availability.")
    if ctx['stale'] and (not po or not p.get('mode')) and p.get('acknowledge_stale') is not True:
        raise ValueError('Acknowledge the stale observations before running historical analysis.')
    transport = number(p, 'transport_cost', 0)
    kg = qty * (100 if p['unit'] == 'quintal' else 1)
    analysis = None
    if po:
        if p.get('mode'):
            analysis = price_only_api.analyze(p) if source == 'price_only' else official_market_api.analyze(p)
            if analysis['kind'] != 'market_forecast':
                raise ValueError('Recorded-price mode returns an observation and cannot be used as a forecast recommendation.')
            forecast = analysis['forecast']
        else:
            if source != 'price_only':
                raise ValueError('Official-source recommendations require an explicit forecast mode.')
            forecast = price_only_api.forecast(p, ctx)
        if not ctx['units']['configured']:
            raise ValueError(ctx['units']['reason'])
        if harvest > date.fromisoformat(forecast['origin']):
            raise ValueError('For this historical next-session analysis, harvest date must be on or before the forecast origin.')
        conversion = 100 if ctx['units']['unit'] == 'INR/kg' else 1
        forecast['base'] = forecast['prediction_native'] * conversion
        # Existing result contract expresses model MAE/RMSE in INR/quintal.
        forecast['metrics'] = {k:v * conversion for k,v in forecast['metrics'].items()}
        forecast['metric_unit'] = 'INR/quintal'
    else:
        try:
            horizon = int(p.get('horizon', 1))
        except (TypeError, ValueError):
            raise ValueError('horizon must be 1, 2, or 3 calendar months.')
        if horizon not in (1, 2, 3):
            raise ValueError('horizon must be 1, 2, or 3 calendar months.')
        as_of = None
        if p.get('mode') == 'historical':
            try:
                target = pd.Period(p['target_date'], freq='M')
            except (KeyError, TypeError, ValueError):
                raise ValueError('Historical monthly evaluation requires target_date.')
            as_of = (target - horizon).strftime('%Y-%m')
        forecast = model(p['state'], p['district'], p['market'], p['variety'], horizon, as_of)
        if p.get('mode') == 'historical':
            if forecast['forecast_date'] != target.strftime('%Y-%m'):
                raise ValueError('Historical target and forecast horizon do not align.')
        elif selling is not None and selling.strftime('%Y-%m') != forecast['forecast_date']:
            raise ValueError(f"The selected {horizon}-month horizon targets {forecast['forecast_date']}; choose a selling date in that month.")
    detailed_transport = any(p.get(key) not in (None, '') for key in ('origin','destination','route_distance_km','fuel_efficiency_km_per_litre','fuel_price_inr_per_litre'))
    if detailed_transport:
        transport_result = estimate_transport({**p, 'shipment_weight_kg': kg})
    else:
        transport_result = legacy_batch_estimate(transport, kg)
    deduction = transport_result['cost_inr_per_quintal']
    # No reliable demand series or calibrated quality/location factors exist.
    # Explicit neutral factors bypass these optional adjustments without inventing inputs.
    fair = calculate_fair_price(forecast['base'], 1, 1, 1, deduction)
    # A transparent configurable policy band, not a statistical confidence interval.
    offset = float(os.environ.get('AGROLINK_BAND_OFFSET', '25'))
    band = create_fair_price_band(fair, offset, offset)
    return {'crop': 'Tomato', 'state': p['state'], 'district': p['district'], 'market': p['market'], 'variety': p['variety'],
            'quantity_kg': kg, 'quality': p['quality'], 'calculated_at': datetime.now(timezone.utc).isoformat(),
            **({'actual':analysis['actual'],'mode':analysis['mode'],'training':analysis['training']} if analysis else {}),
            'context': ctx, 'forecast': forecast, 'transport': transport_result,
            'forecast_horizon': (f"One historical reporting session on {forecast['forecast_date']}; training ended {forecast['origin']}" if po and forecast.get('forecast_date')
                                 else 'One subsequent reporting session; calendar date unknown' if po
                                 else 'One calendar month after the latest observed month'),
            'prices': {k: v / 100 for k, v in band.items()},
            'farm_gate': {'formula':'max(0, crop_market_forecast_inr_per_quintal - transport_cost_inr_per_quintal)',
                          'market_forecast_inr_per_quintal':forecast['base'], 'transport_cost_inr_per_quintal':deduction,
                          'farm_gate_inr_per_quintal':fair, 'farm_gate_inr_per_kg':fair / 100},
            'breakdown': {'base': forecast['base'] / 100, 'transport': deduction / 100, 'transport_batch': transport,
                          'quality_multiplier': 1, 'location_multiplier': 1, 'demand_supply_multiplier': 1, 'band_offset': offset / 100},
            'warnings': ['Transport is deducted by the existing engine: this is an estimated farm-gate return, not a delivered-cost asking price.',
                         'Quality is recorded but no calibrated quality adjustment is configured. Location and demand/supply adjustments are neutral.',
                         'Packaging, handling, production costs, weather and live demand are not included.',
                         'The price band is a configured policy offset, not a statistical confidence interval.'] +
                        transport_result['warnings'] +
                        (['Stale observations: this is historical analysis and is not a current selling-price forecast.'] if ctx['stale'] else []) +
                        (forecast['report']['warnings'] if po else [])}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, headers=None):
        headers=headers or {}
        body = payload if isinstance(payload,bytes) else json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', headers.get('Content-Type','application/json; charset=utf-8'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', os.environ.get('AGROLINK_FRONTEND_ORIGIN', 'http://localhost:5173'))
        self.send_header('Access-Control-Allow-Credentials','true')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        for key,value in headers.items():
            if key!='Content-Type': self.send_header(key,value)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', os.environ.get('AGROLINK_FRONTEND_ORIGIN', 'http://localhost:5173'))
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-CSRF-Token, X-Agrolink-Client')
        self.send_header('Access-Control-Allow-Credentials','true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.end_headers()

    def dispatch(self, operation):
        try:
            self.reply(200, operation())
        except (ValueError, KeyError) as exc:
            self.reply(422, {'message': str(exc), 'code': 'UNAVAILABLE_OR_INVALID'})
        except Exception:
            logging.exception('AgroLink request failed')
            self.reply(500, {'message': 'The calculation service could not complete this request. Please retry or select another market.'})

    def do_GET(self):
        from backend.workspace_api import handle
        if handle(self): return
        url = urlparse(self.path)
        if url.path == '/api/listing-defaults':
            from backend.listing import defaults
            self.dispatch(defaults)
        elif url.path == '/api/catalog':
            self.dispatch(lambda: get_catalog({k:v[0] for k,v in parse_qs(url.query).items()}))
        elif url.path == '/api/history':
            self.dispatch(lambda: context({k: v[0] for k, v in parse_qs(url.query).items()}))
        elif url.path == '/api/health':
            self.reply(200, {'status': 'ok'})
        elif url.path == '/api/sources':
            self.reply(200, {'sources':[{'id':'var','label':'Tomato.csv â€” monthly VAR (price + arrivals)'},
                                       {'id':'price_only','label':'Root CSV exports â€” price-only reporting sessions'},
                                       {'id':'official','label':'Official data.gov.in / AGMARKNET imports'}]})
        elif url.path == '/api/price-only/audit':
            self.dispatch(price_only_api.audit)
        elif url.path == '/api/market-data/status':
            self.dispatch(market_data_status)
        else:
            self.reply(404, {'message': 'Endpoint not found.'})

    def do_POST(self):
        from backend.workspace_api import handle
        if handle(self): return
        if self.path not in ('/api/recommendations','/api/forecast-preview','/api/market-analysis','/api/listing-estimate','/api/buyer-suggestions','/api/buyer-selection'):
            return self.reply(404, {'message': 'Endpoint not found.'})
        def run():
            size = int(self.headers.get('Content-Length', 0))
            if size <= 0 or size > 16384:
                raise ValueError('Invalid request size.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object.')
            if self.path == '/api/buyer-suggestions':
                from backend.buyers import suggestions
                return suggestions(payload)
            if self.path == '/api/buyer-selection':
                from backend.buyers import select_buyer
                return select_buyer(payload)
            if self.path == '/api/listing-estimate':
                from backend.listing import estimate
                return estimate(payload)
            if self.path == '/api/forecast-preview':
                if source_id(payload) != 'price_only':
                    raise ValueError('Forecast preview is supported only for the price-only source.')
                return price_only_api.preview(payload)
            if self.path == '/api/market-analysis':
                source = source_id(payload)
                if source == 'var':
                    raise ValueError('Recorded/historical/future modes are available for price-only and official sources.')
                return price_only_api.analyze(payload) if source == 'price_only' else official_market_api.analyze(payload)
            return recommend(payload)
        self.dispatch(run)

    def do_PATCH(self):
        from backend.workspace_api import handle
        if not handle(self): self.reply(404,{'message':'Endpoint not found.'})

    def do_DELETE(self):
        from backend.workspace_api import handle
        if not handle(self): self.reply(404,{'message':'Endpoint not found.'})


if __name__ == '__main__':
    port = int(os.environ.get('AGROLINK_PORT', '8000'))
    print(f'AgroLink API: http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()

