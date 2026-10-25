"""Contract and unit tests; fixtures here are test-only, never production data."""
import unittest
from unittest.mock import patch
from backend.server import recommend

CONTEXT = {'forecast_month':'2024-03','stale':True,'latest_observation':'2024-02-01'}
PARAMS = dict(crop='Tomato',state='Karnataka',district='Davangere',market='Davangere',variety='Tomato',quantity=500,unit='kg',quality='Unspecified',harvest_date='2024-03-01',selling_date='2024-03-05',transport_cost=800,acknowledge_stale=True)

class RecommendationTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('context',CONTEXT),('catalog',{'quality_grades':['Unspecified','A','B','C']}),('model',{'base':1000,'forecast_date':'2024-03','name':'VAR_LEVEL','lag':1,'metrics':{'MAE':100,'RMSE':120,'MAPE':10}})]:
            p = patch('backend.server.'+name,return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_real_engine_transport_deduction_and_conversion(self):
        r = recommend(PARAMS)
        self.assertEqual(r['breakdown']['transport'],1.6)
        self.assertEqual(r['prices'],{'min_price':8.15,'fair_price':8.4,'max_price':8.65})
        self.assertEqual(r['breakdown']['quality_multiplier'],1)

    def test_quantity_units_equivalent(self):
        a = recommend(PARAMS)
        b = recommend({**PARAMS,'quantity':5,'unit':'quintal'})
        self.assertEqual(a['prices'],b['prices'])

    def test_reject_wrong_forecast_period(self):
        with self.assertRaisesRegex(ValueError,'targets 2024-03'):
            recommend({**PARAMS,'selling_date':'2026-11-01'})

    def test_stale_requires_explicit_acknowledgement(self):
        with self.assertRaisesRegex(ValueError,'Acknowledge'):
            recommend({**PARAMS,'acknowledge_stale':False})

    def test_validation(self):
        for override in [{'quantity':0},{'quantity':float('nan')},{'transport_cost':-1},{'quality':'premium'},{'harvest_date':'2024-04-01'},{'unit':'tonnes'}]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                recommend({**PARAMS,**override})

    def test_forecast_failure_propagates_without_substitution(self):
        with patch('backend.server.model',side_effect=ValueError('Fewer than 12 monthly observations are available.')):
            with self.assertRaisesRegex(ValueError,'Fewer than 12'):
                recommend(PARAMS)

    def test_zero_floor(self):
        r = recommend({**PARAMS,'transport_cost':1000000})
        self.assertEqual(r['prices']['min_price'],0)
        self.assertEqual(r['prices']['fair_price'],0)

if __name__ == '__main__':
    unittest.main()

