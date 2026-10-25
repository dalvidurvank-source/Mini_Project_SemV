"""Contracts for the farmer listing flow, using deterministic model fixtures."""
import unittest
from datetime import date
from unittest.mock import patch
from backend.listing import estimate

MARKET = dict(state='Karnataka', district='Kolar', market='Kolar', variety='Tomato')

class ListingTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch('backend.listing.today', return_value=date(2026,10,24)),
            patch('backend.server.context', return_value={'latest_observation':'2024-02-01', 'stale':True, 'forecast_month':'2024-03'}),
            patch('backend.server.catalog', return_value={'quality_grades':['Unspecified','A','B','C']}),
            patch('backend.server.model', return_value={'base':1000, 'origin':'2024-02-29', 'forecast_date':'2024-03', 'name':'VAR_LEVEL', 'metrics':{'MAE':100,'RMSE':120}}),
            patch('backend.listing.plan_route', return_value={'distance_km':50,'duration_minutes':60,
                'origin':{'name':'Test farm'},'destination':{'name':'Test market'},'provider':'Test road graph',
                'retrieved_at':'2026-10-24T00:00:00Z','warnings':[]}),
            patch('backend.listing.market_balance',return_value={'status':'unavailable','ratio':None,'multiplier':1,
                'source':None,'reason':'No measured demand','period':'2024-03'})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.payload = {**MARKET, 'quantity':500,'unit':'kg','harvest_date':'2026-10-24',
                        'fuel_efficiency_km_per_litre':10,'fuel_price_inr_per_litre':80,'loading_inr':0,'unloading_inr':0}

    def test_today_listing_preserves_dates_and_labels_historical_demo(self):
        r = estimate(self.payload)
        self.assertTrue(r['listing']['demo'])
        self.assertEqual(r['listing']['date'],'2026-10-24')
        self.assertEqual(r['listing']['harvest_date'],'2026-10-24')
        self.assertEqual(r['listing']['target_month'],'2024-03')
        self.assertAlmostEqual(r['prices']['fair_price'],8.4)
        self.assertIsNone(r['listing']['dsr'])

    def test_transport_and_quantity_unit_equivalence(self):
        a = estimate(self.payload)
        b = estimate({**self.payload,'quantity':5,'unit':'quintal'})
        self.assertEqual(a['prices'], b['prices'])
        self.assertEqual(estimate({**self.payload,'fuel_price_inr_per_litre':0})['prices']['fair_price'],10)

    def test_engine_owned_dsr_changes_price(self):
        with patch('backend.listing.market_balance',return_value={'status':'available','ratio':0.5,'multiplier':1.05,
                        'source':'Test backend evidence','reason':'Matched evidence'}):
            low = estimate(self.payload)
        self.assertAlmostEqual(low['prices']['fair_price'],8.9)
        self.assertEqual(low['market_balance']['source'],'Test backend evidence')

    def test_invalid_inputs(self):
        for override in ({'regional_supply':1},{'regional_demand':1},{'regional_supply':1,'regional_demand':0},
                         {'regional_supply':-1,'regional_demand':1},{'quantity':0},{'fuel_price_inr_per_litre':-1},
                         {'harvest_date':'2026-10-25'},{'harvest_date':'invalid'}, {'quantity':1e308}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                estimate({**self.payload,**override})

    def test_transport_cannot_create_negative_return(self):
        r = estimate({**self.payload,'fuel_price_inr_per_litre':999999})
        self.assertEqual(r['prices']['fair_price'],0)
        self.assertLess(r['economics']['net_revenue_inr'],0)

    def test_transport_and_dsr_cannot_be_overridden_by_caller(self):
        self.assertEqual(estimate({**self.payload,'transport_cost':0,'route_distance_km':1})['prices']['fair_price'],8.4)
        for key in ('dsr','dsr_multiplier','demand_supply_multiplier'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                estimate({**self.payload,key:1.15})

    def test_additional_trips_change_cost_and_net_return(self):
        r = estimate({**self.payload,'quantity':1500})
        self.assertEqual(r['transport']['trips'],2)
        self.assertEqual(r['transport']['total_trip_cost_inr'],1600)
        self.assertEqual(r['economics']['net_revenue_inr'],13400)

    def test_selling_date_validation(self):
        for selling in ('2026-10-23','invalid'):
            with self.subTest(selling=selling), self.assertRaises(ValueError):
                estimate({**self.payload,'selling_date':selling})

    def test_fresh_data_targets_listing_month(self):
        with patch('backend.server.context',return_value={'latest_observation':'2026-09-30','stale':False,'forecast_month':'2026-10'}), patch('backend.server.model', return_value={'base':1000,'origin':'2026-09-30','forecast_date':'2026-10','name':'VAR_LEVEL','metrics':{'MAE':100,'RMSE':120}}):
            r = estimate(self.payload)
        self.assertFalse(r['listing']['demo'])
        self.assertEqual(r['listing']['target_month'],'2026-10')

if __name__ == '__main__':
    unittest.main()

