import json
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.buyers import suggestions, select_buyer
from backend.test_buyers import payload
from logistics.test_delivery_life import NOW


class BuyerRankingTests(unittest.TestCase):
    def setUp(self):
        self.records=json.loads((Path(__file__).parent/'test_fixtures/buyer_offers.demo.json').read_text(encoding='utf-8'))
        p=patch('backend.buyers.directory',return_value=self.records);p.start();self.addCleanup(p.stop)
        for target in ('backend.buyers.india_now','logistics.shelf_life.india_now'):
            p=patch(target,return_value=NOW);p.start();self.addCleanup(p.stop)

    def test_farther_offer_provides_more_net_return(self):
        r=suggestions(payload())
        self.assertEqual(r['buyers'][0]['id'],'demo-pimpalgaon')
        by_id={b['id']:b for b in r['buyers']}
        far,near=by_id['demo-pimpalgaon'],by_id['demo-nasik-yard']
        self.assertGreater(far['transport']['route_plan']['distance_km'],near['transport']['route_plan']['distance_km'])
        self.assertGreater(far['financial']['net_return_inr'],near['financial']['net_return_inr'])
        self.assertTrue(far['financial']['is_best'])
        self.assertFalse(by_id['demo-sambhajinagar']['financial']['rankable'])

    def test_fuel_assumption_changes_ranking(self):
        normal=suggestions(payload())
        expensive=suggestions(payload(fuel_price_inr_per_litre=400))
        self.assertEqual(normal['buyers'][0]['id'],'demo-pimpalgaon')
        self.assertEqual(expensive['buyers'][0]['id'],'demo-nasik-yard')

    def test_sale_quantity_controls_transport_trips_and_shelf_life(self):
        r=suggestions(payload(quantity=1500,allow_partial_sales=True))
        by_id={b['id']:b for b in r['buyers']}
        full,partial=by_id['demo-nasik-yard'],by_id['demo-pimpalgaon']
        self.assertEqual(full['transport']['trips'],2)
        self.assertEqual(partial['transport']['trips'],1)
        self.assertEqual(partial['financial']['sale_quantity_kg'],1000)
        self.assertEqual(partial['financial']['unsold_quantity_kg'],500)
        self.assertEqual(partial['shelf_life']['trips'],1)
        self.assertNotEqual(full['financial']['comparison_group'],partial['financial']['comparison_group'])
        r=suggestions(payload(quantity=1500))
        excluded=next(b for b in r['buyers'] if b['id']=='demo-pimpalgaon')
        self.assertFalse(excluded['selection_allowed'])
        with self.assertRaisesRegex(ValueError,'Buyer cannot take'):
            select_buyer(payload(quantity=1500,buyer_id='demo-pimpalgaon'))

    def test_different_partial_quantities_are_separate(self):
        self.records[0]['offer']['max_quantity_kg']=300
        self.records[1]['offer']['max_quantity_kg']=400
        with patch('backend.buyers.directory',return_value=self.records):
            r=suggestions(payload(allow_partial_sales=True))
        groups=r['comparison_groups']
        self.assertEqual({g['quantity_kg'] for g in groups},{300,400})
        self.assertTrue(all(g['buyer_count']==1 for g in groups))

    def test_invalid_offers_and_unavailable_pins_are_explicit(self):
        self.records[0]['offer']['price_inr_per_kg']=-1
        self.records[1]['location_id']='missing'
        with patch('backend.buyers.directory',return_value=self.records):
            r=suggestions(payload())
            with self.assertRaisesRegex(ValueError,'Invalid buyer offer'):
                select_buyer(payload(buyer_id='demo-nasik-yard'))
        by_id={b['id']:b for b in r['buyers']}
        self.assertEqual(by_id['demo-nasik-yard']['financial']['status'],'invalid_offer')
        self.assertEqual(by_id['demo-pimpalgaon']['shelf_life']['status'],'unavailable')
        self.assertTrue(all(not b['financial']['rankable'] for b in r['buyers']))

    def test_expired_crop_has_no_financial_recommendation(self):
        r=suggestions(payload(60))
        self.assertEqual(r['comparison_groups'],[])
        self.assertTrue(all(not b['financial']['rankable'] for b in r['buyers']))
        self.assertTrue(all(not b['selection_allowed'] for b in r['buyers']))

    def test_manipulated_financial_results_are_ignored(self):
        p=payload(buyer_id='demo-nasik-yard')
        expected=select_buyer(p)['buyer']['financial']
        forged=select_buyer({**p,'price_inr_per_kg':999999,'offer':{'price_inr_per_kg':999999},
                 'transport_cost':0,'total_trip_cost_inr':0,'route_distance_km':1,
                 'selling_charges':[],'net_return_inr':999999,'rank':1,'dsr_multiplier':1.15,
                 'financial':{'net_return_inr':999999,'rank':1}})['buyer']['financial']
        self.assertEqual(forged,expected)
        self.assertEqual(forged['price_inr_per_kg'],20)
        self.assertFalse(forged['dsr_applied'])

    def test_changed_server_offer_is_recalculated_at_selection(self):
        before=suggestions(payload())
        old=next(b for b in before['buyers'] if b['id']=='demo-nasik-yard')['financial']['net_return_inr']
        self.records[0]['offer']['price_inr_per_kg']=15
        with patch('backend.buyers.directory',return_value=self.records):
            selected=select_buyer(payload(buyer_id='demo-nasik-yard'))
        self.assertLess(selected['buyer']['financial']['net_return_inr'],old)
        self.assertEqual(selected['buyer']['financial']['price_inr_per_kg'],15)

    def test_missing_offer_can_only_prepare_unpriced_enquiry(self):
        r=select_buyer(payload(buyer_id='demo-sambhajinagar'))
        self.assertEqual(r['financial_mode'],'unpriced_enquiry')
        self.assertIsNone(r['buyer']['financial']['net_return_inr'])

    def test_invalid_partial_permission_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Partial-sale permission'):
            suggestions(payload(allow_partial_sales='true'))

    def test_directory_without_offers_never_invents_returns(self):
        for record in self.records:
            record.pop('offer',None)
        r=suggestions(payload())
        self.assertEqual(r['comparison_groups'],[])
        self.assertTrue(all(b['financial']['net_return_inr'] is None for b in r['buyers']))
        self.assertTrue(all(b['financial']['status']=='missing_offer' for b in r['buyers']))
