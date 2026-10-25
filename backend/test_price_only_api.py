import json
import os
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from backend import price_only_api
from backend.server import Handler, recommend
from forecasting.price_only import backtest, unit_configuration
from forecasting.test_price_only import observations

PARAMS = dict(source='price_only',crop='Tomato',state='Maharashtra',district='Pune',market='Pune',market_id='172',variety='Local',quality='Unspecified',quantity=500,unit='kg',transport_cost=800,harvest_date='2025-09-20',selling_date='',horizon=1,horizon_unit='reporting_session',method='auto',acknowledge_stale=True)


class PriceOnlyContractTests(unittest.TestCase):
    def setUp(self):
        rows=observations(values=[1000.]*25)
        report=backtest(rows)
        record={'state':'Maharashtra','district':'Pune','market':'Pune','market_id':'172','variety':'Local'}
        for name,value in [('series_for',rows),('cached_backtest',report),('market_catalog',[record])]:
            p=patch('backend.price_only_api.'+name,return_value=value)
            p.start()
            self.addCleanup(p.stop)
        env=patch.dict(os.environ,{},clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('AGROLINK_PRICE_ONLY_UNIT',None)
        os.environ.pop('AGROLINK_PRICE_ONLY_UNIT_EVIDENCE',None)
        config = patch('forecasting.price_only.UNIT_CONFIG',Path(__file__).with_name('nonexistent_test_unit_config.json'))
        config.start()
        self.addCleanup(config.stop)

    def configure(self,unit='INR/quintal'):
        os.environ['AGROLINK_PRICE_ONLY_UNIT']=unit
        os.environ['AGROLINK_PRICE_ONLY_UNIT_EVIDENCE']='Test-only fixture unit contract, not production confirmation'

    def test_unknown_units_allow_only_native_preview(self):
        r=price_only_api.preview(PARAMS)
        self.assertEqual(r['forecast']['prediction_native'],1000)
        self.assertNotIn('prices',r)
        self.assertFalse(r['context']['can_recommend'])
        with self.assertRaisesRegex(ValueError,'units are unverified'):
            recommend(PARAMS)

    def test_unit_requires_evidence_and_supported_unit(self):
        os.environ['AGROLINK_PRICE_ONLY_UNIT']='INR/quintal'
        self.assertFalse(unit_configuration()['configured'])
        self.configure('USD/kg')
        self.assertFalse(unit_configuration()['configured'])

    def test_persisted_confirmation_and_partial_override(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'units.json'
            path.write_text(json.dumps({'unit':'INR/quintal','evidence':'Fixture owner confirmation','files':['price_data.csv','price_data (25-26).csv']}),encoding='utf-8')
            with patch('forecasting.price_only.UNIT_CONFIG',path):
                self.assertTrue(unit_configuration()['configured'])
                self.assertEqual(unit_configuration()['unit'],'INR/quintal')
                os.environ['AGROLINK_PRICE_ONLY_UNIT']='INR/kg'
                self.assertFalse(unit_configuration()['configured'])

    def test_confirmation_for_different_files_is_not_reused(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'units.json'
            path.write_text(json.dumps({'unit':'INR/quintal','evidence':'Other source','files':['other.csv']}),encoding='utf-8')
            with patch('forecasting.price_only.UNIT_CONFIG',path):
                self.assertFalse(unit_configuration()['configured'])

    def test_quintal_conversion_and_real_transport_engine(self):
        self.configure()
        r=recommend(PARAMS)
        self.assertEqual(r['prices']['fair_price'],8.4)
        self.assertEqual(r['breakdown']['transport'],1.6)
        self.assertEqual(r['forecast']['base'],1000)
        self.assertEqual(r['forecast']['metric_unit'],'INR/quintal')

    def test_kg_source_conversion(self):
        self.configure('INR/kg')
        r=recommend(PARAMS)
        self.assertEqual(r['forecast']['base'],100000)
        self.assertEqual(r['prices']['fair_price'],998.4)

    def test_quantity_units_are_equivalent(self):
        self.configure()
        self.assertEqual(recommend(PARAMS)['prices'],recommend({**PARAMS,'quantity':5,'unit':'quintal'})['prices'])

    def test_no_date_horizon_or_model_substitution(self):
        for override in ({'selling_date':'2026-10-23'},{'harvest_date':'2026-10-01'},{'horizon':7},{'horizon':True},{'horizon_unit':'day'},{'method':'SES'},{'state':'Karnataka'},{'market':'Other market'},{'acknowledge_stale':False}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                price_only_api.preview({**PARAMS,**override})

    def test_history_exposes_eligibility_but_no_prediction_before_action(self):
        r=price_only_api.context(PARAMS)
        self.assertEqual(r['eligibility']['status'],'eligible')
        self.assertNotIn('prediction',r['eligibility'])
        self.assertEqual(r['unit'],'unverified source price units')
        self.assertEqual(r['history'][0]['source_files'],['test.csv'])

    def test_recorded_price_is_never_labelled_forecast(self):
        result = price_only_api.analyze({**PARAMS,'mode':'recorded','target_date':'2025-09-10'})
        self.assertEqual(result['kind'],'recorded_price')
        self.assertIsNone(result['forecast'])
        self.assertEqual(result['actual']['date'],'2025-09-10')
        self.assertIn('not a forecast',result['warnings'][0])

    def test_historical_forecast_excludes_target_observation(self):
        result = price_only_api.analyze({**PARAMS,'mode':'historical','target_date':'2025-09-22'})
        self.assertEqual(result['kind'],'market_forecast')
        self.assertEqual(result['forecast']['forecast_date'],'2025-09-22')
        self.assertEqual(result['actual']['date'],'2025-09-22')
        self.assertLess(result['training']['last_date'],result['actual']['date'])
        self.assertTrue(result['training']['strictly_before_target'])
        self.assertFalse(any('No target calendar date is known' in w for w in result['warnings']))
        self.assertIn('2025-09-22',result['warnings'][0])

    def test_future_forecast_requires_stale_acknowledgement(self):
        with self.assertRaisesRegex(ValueError,'Acknowledge the stale-data limitation'):
            price_only_api.analyze({**PARAMS,'mode':'future','target_date':'','acknowledge_stale':False})
        result = price_only_api.analyze({**PARAMS,'mode':'future','target_date':'','acknowledge_stale':True})
        self.assertEqual(result['kind'],'market_forecast')
        self.assertIn('not a current market-price forecast', result['warnings'][0])

    def test_insufficient_history_preview_fails(self):
        unavailable=backtest(observations(4))
        with patch('backend.price_only_api.cached_backtest',return_value=unavailable):
            with self.assertRaisesRegex(ValueError,'Insufficient history'):
                price_only_api.preview({**PARAMS,'harvest_date':'2025-09-01'})

    def test_http_contracts(self):
        class Quiet(Handler):
            def log_message(self,*args):
                pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def request(path,payload=None):
            req=Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=10) as response:
                return json.load(response)
        try:
            self.assertEqual(len(request('/api/sources')['sources']),3)
            self.assertEqual(request('/api/catalog?source=price_only')['markets'][0]['market_id'],'172')
            r=request('/api/forecast-preview',PARAMS)
            self.assertEqual(r['kind'],'forecast_preview')
            recorded=request('/api/market-analysis',{**PARAMS,'mode':'recorded','target_date':'2025-09-10'})
            self.assertEqual(recorded['kind'],'recorded_price')
            self.assertIsNone(recorded['forecast'])
            with self.assertRaises(HTTPError) as exc:
                request('/api/recommendations',PARAMS)
            self.assertEqual(exc.exception.code,422)
            self.configure()
            self.assertEqual(request('/api/recommendations',PARAMS)['prices']['fair_price'],8.4)
            with self.assertRaises(HTTPError) as invalid:
                request('/api/catalog?source=unknown')
            self.assertEqual(invalid.exception.code,422)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
