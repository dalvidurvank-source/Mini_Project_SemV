"""Exercise the real HTTP listing flow and repository data without network calls.

Run: python -m backend.verify_listing_flow
"""
import contextlib
import io
import json
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.server import Handler


def main():
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api'
    def call(path, payload=None):
        req = Request(base+path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=180) as response:
                return response.status,json.load(response)
        except HTTPError as error:
            with error:
                return error.code,json.load(error)
    try:
        status, defaults = call('/listing-defaults')
        assert status == 200
        farm = defaults['logistics']['demo_farm']
        pin = defaults['logistics']['market_pins'][0]
        payload = {**defaults['default_market'], **defaults['logistics']['vehicle'],
                   'crop':'Tomato','quantity':500,'unit':'kg','harvest_date':defaults['listing_date'],
                   'selling_date':defaults['listing_date'],'farm_name':'SPIT Mumbai (sample pickup)',
                   'farm_latitude':farm['latitude'],'farm_longitude':farm['longitude'],
                   'destination_latitude':pin['latitude'],'destination_longitude':pin['longitude']}
        with contextlib.redirect_stdout(io.StringIO()):
            status, result = call('/listing-estimate', payload)
        assert status == 200, result
        assert result['listing']['demo']
        assert result['transport']['route_plan']['mode'] == 'saved_road_matrix'
        assert result['market_balance']['multiplier'] == 1
        assert result['transport']['total_trip_cost_inr'] > 0
        assert abs(result['economics']['net_revenue_inr'] -
                   (result['economics']['gross_revenue_inr']-result['transport']['total_trip_cost_inr'])) < 0.01
        cases = [{'case':'sample_route','status':status}]
        for name,changes,expected in (
            ('quintal_equivalence',{'quantity':5,'unit':'quintal'},200),
            ('multiple_trips',{'quantity':1500},200),
            ('farmer_dsr_rejected',{'regional_supply':500,'regional_demand':1000},422),
            ('bad_coordinate',{'farm_latitude':91},422),
            ('negative_fuel_price',{'fuel_price_inr_per_litre':-1},422),
            ('invalid_date',{'selling_date':'not-a-date'},422),
        ):
            status, response = call('/listing-estimate',{**payload,**changes})
            assert status == expected, (name,response)
            if name == 'quintal_equivalence':
                assert response['prices'] == result['prices']
                assert response['economics'] == result['economics']
            if name == 'multiple_trips':
                assert response['transport']['trips'] == 2
                assert response['transport']['total_trip_cost_inr'] == 2*result['transport']['total_trip_cost_inr']
            cases.append({'case':name,'status':status})
        report = {'verified_at':datetime.now(timezone.utc).isoformat(), 'cases':cases,
                  'sample_input':payload,'sample_result':result}
        output = Path(__file__).resolve().parents[1]/'reports/listing_flow_check.json'
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'passed_http_cases':len(cases), 'model':result['forecast']['name'],
                          'target':result['listing']['target_month'],
                          'distance_km':result['transport']['route_plan']['distance_km'],
                          'transport_inr':result['transport']['total_trip_cost_inr'],
                          'net_inr_per_kg':result['economics']['net_inr_per_kg'], 'report':str(output)}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
