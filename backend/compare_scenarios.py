"""Real-data HTTP integration matrix. Run: python -m backend.compare_scenarios.

Uses an isolated loopback server, actual CSVs and the real forecasting/pricing
code. No forecast mocks, production data changes, or persisted listings.
"""
import csv
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.server import Handler


def run():
    class Quiet(Handler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    results, comparisons, failures = [], [], []

    def request(path, payload=None):
        req = Request(base+path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type':'application/json'})
        try:
            with urlopen(req, timeout=180) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def check(name, payload, expected=200):
        status, body = request('/api/recommendations', payload)
        ok = status == expected
        row = {'case':name, 'source':payload['source'], 'state':payload['state'],
               'district':payload['district'], 'market':payload['market'], 'variety':payload['variety'],
               'quality':payload['quality'], 'harvest_date':payload['harvest_date'],
               'selling_date':payload.get('selling_date',''), 'quantity':payload['quantity'], 'unit':payload['unit'],
               'transport_batch_INR':payload['transport_cost'], 'status':status, 'expected_status':expected,
               'passed':ok, 'origin':body.get('context',{}).get('latest_observation'),
               'model':body.get('forecast',{}).get('name'), 'base_INR_kg':body.get('breakdown',{}).get('base'),
               'transport_INR_kg':body.get('breakdown',{}).get('transport'),
               'lower_INR_kg':body.get('prices',{}).get('min_price'),
               'midpoint_INR_kg':body.get('prices',{}).get('fair_price'),
               'upper_INR_kg':body.get('prices',{}).get('max_price'), 'error':body.get('message','')}
        results.append(row)
        if not ok:
            failures.append(f'{name}: expected HTTP {expected}, got {status}: {body}')
        return body if status == 200 else None

    def expect(condition, message):
        if not condition:
            failures.append(message)

    try:
        status, catalog = request('/api/catalog?source=price_only')
        if status != 200 or not catalog['units']['configured']:
            raise RuntimeError('Price-only catalog and confirmed source units are required.')
        for market in catalog['markets']:
            params = {'source':'price_only','crop':'Tomato',**market}
            status, ctx = request('/api/history?'+urlencode(params))
            if status != 200:
                raise RuntimeError(f'History unavailable: {params}: {ctx}')
            payload = {**params,'quality':'Unspecified','quantity':500,'unit':'kg','transport_cost':800,
                       'harvest_date':ctx['latest_observation'],'selling_date':'','method':'auto','horizon':1,
                       'horizon_unit':'reporting_session','acknowledge_stale':True}
            eligible = ctx['eligibility']['status'] == 'eligible'
            initial = check('market baseline',payload,200 if eligible else 422)
            if not eligible:
                continue
            comparisons.append({**market,'origin':ctx['latest_observation'],
                'model':initial['forecast']['name'], 'base':initial['breakdown']['base'], **initial['prices']})
            for grade in ('A','B','C'):
                r = check('quality '+grade,{**payload,'quality':grade})
                expect(r is not None and r['prices'] == initial['prices'],f'{market}: unexplained quality premium for {grade}')
            for days in (7,21):
                harvest = (date.fromisoformat(payload['harvest_date'])-timedelta(days=days)).isoformat()
                r = check(f'harvest {days} days earlier',{**payload,'harvest_date':harvest})
                expect(r is not None and r['prices'] == initial['prices'],f'{market}: harvest date silently shifted forecast')
            r = check('equivalent quintal quantity',{**payload,'quantity':5,'unit':'quintal'})
            expect(r is not None and r['prices'] == initial['prices'],f'{market}: kg/quintal allocation mismatch')
            for cost in (0,1600):
                r = check('transport '+str(cost),{**payload,'transport_cost':cost})
                expected_fair = round(max(0, initial['forecast']['base'] - cost/(500/100)),2)/100
                expect(r is not None and abs(r['prices']['fair_price']-expected_fair)<1e-9,f'{market}: incorrect transport allocation')
            for override in ({'harvest_date':'2026-10-23'},{'selling_date':'2025-10-31'},
                             {'selling_date':'2026-10-23'},{'harvest_date':'2025-02-30'},
                             {'quality':'Premium'},{'horizon':7},{'acknowledge_stale':False}):
                check('rejected '+next(iter(override)),{**payload,**override},422)

        # Preserve the legacy monthly VAR workflow and its period restrictions.
        var_markets = [dict(state='Karnataka',district='Davangere',market='Davangere',variety='Tomato'),
                       dict(state='Karnataka',district='Kolar',market='Kolar',variety='Tomato'),
                       dict(state='Andhra Pradesh',district='Kurnool',market='Adoni',variety='Tomato')]
        for market in var_markets:
            p = {'source':'var','crop':'Tomato',**market}
            status, ctx = request('/api/history?'+urlencode(p))
            if status != 200:
                failures.append(f'VAR history failed: {market}: {ctx}')
                continue
            selling = ctx['forecast_month']+'-05'
            payload = {**p,'quantity':500,'unit':'kg','transport_cost':800,'quality':'Unspecified',
                       'harvest_date':ctx['forecast_month']+'-01','selling_date':selling,'acknowledge_stale':True}
            expected = 422 if market['market']=='Adoni' else 200
            initial = check('VAR market baseline',payload,expected)
            if initial:
                for grade in ('A','B','C'):
                    r = check('VAR quality '+grade,{**payload,'quality':grade})
                    expect(r is not None and r['prices']==initial['prices'],f'VAR {market}: unexpected quality premium')
                r = check('VAR later day same month',{**payload,'selling_date':ctx['forecast_month']+'-20'})
                expect(r is not None and r['prices']==initial['prices'],f'VAR {market}: date changed monthly reference')
                check('VAR current selling month',{**payload,'selling_date':'2026-10-23'},422)
                check('VAR selling before harvest',{**payload,'selling_date':'2024-01-01'},422)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    output = Path(__file__).resolve().parents[1]/'reports'
    output.mkdir(exist_ok=True)
    with (output/'scenario_comparison.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    details = {'http_cases':len(results),'passed_http_cases':sum(r['passed'] for r in results),
               'failures':failures,'market_comparisons':comparisons,'cases':results,
               'conditions':{'quantity_kg':500,'transport_batch_INR':800,'band_offset_INR_quintal':25,
                  'quality':'Self-reported metadata; no premium is configured.',
                  'dates':'Harvest dates do not retarget forecasts. Price-only horizon is the next reporting session after the latest observation, not a requested calendar date.'}}
    (output/'scenario_comparison.json').write_text(json.dumps(details,indent=2,allow_nan=False),encoding='utf-8')
    lines = ['# Location, date and quality comparison','',
             f'{len(results)} real-data HTTP cases; {sum(r["passed"] for r in results)} returned the expected status. {len(failures)} assertion failures.',
             '', 'All price-only market/variety combinations were tested. Costs are INR 800 per 500 kg batch unless a case explicitly changes them. All prices below are INR/kg.',
             '', '| Market | Variety | Origin | Model | Forecast | Lower | Midpoint | Upper |',
             '| --- | --- | --- | --- | ---: | ---: | ---: | ---: |']
    for r in comparisons:
        lines.append(f'| {r["market"]} | {r["variety"]} | {r["origin"]} | {r["model"]} | {r["base"]:.2f} | {r["min_price"]:.2f} | {r["fair_price"]:.2f} | {r["max_price"]:.2f} |')
    lines += ['', 'Quality A, B, C and Unspecified must give identical prices: no calibrated quality coefficients are configured. Market differences reflect different observed series and varieties; the location multiplier itself remains neutral.',
              '', 'Earlier harvest dates leave the forecast origin unchanged. They are not an as-of-date backtest. Current 2026 harvest requests and any calendar selling-date requests are rejected by the price-only path. Monthly VAR permits different selling days within its supported month; it does not produce day-specific prices.',
              '', 'All results are historical decision support. Missing history is rejected, not filled or replaced by another market.',
              '', 'See [all HTTP cases](scenario_comparison.csv) and [full results](scenario_comparison.json).']
    if failures:
        lines += ['', '## Failures', *['- '+message for message in failures]]
    (output/'scenario_comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(results),'passed_http_cases':sum(r['passed'] for r in results),'assertion_failures':failures,'eligible_price_only_series':len(comparisons)},indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    run()
