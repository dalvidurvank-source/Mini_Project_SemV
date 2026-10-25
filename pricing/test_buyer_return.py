import unittest
from datetime import datetime, timedelta, timezone
from pricing.buyer_return import offer_plan, financial_outcome, rank_buyers

NOW=datetime(2026,10,24,tzinfo=timezone.utc)


def buyer(**offer):
    return {'id':'test','demo':True,'offer':{'kind':'demo_offer','price_inr_per_kg':10,'max_quantity_kg':1000,
            'partial_sales_supported':True,**offer}}


def outcome(record=None,kg=10,partial=False,transport=25,shelf=True):
    plan=offer_plan(record or buyer(),kg,partial,NOW)
    return financial_outcome(plan,{'total_trip_cost_inr':transport} if transport is not None else None,{'can_select':shelf})


class BuyerReturnTests(unittest.TestCase):
    def test_exact_formula_and_no_double_counting(self):
        record=buyer(selling_charges=[{'label':'Service','type':'fixed','value':5},
                     {'label':'Packing','type':'per_kg','value':0.5},
                     {'label':'Commission','type':'percent_of_gross','value':2}])
        f=outcome(record)
        self.assertEqual(f['gross_sale_inr'],100)
        self.assertEqual(f['other_selling_charges_inr'],12)
        self.assertEqual(f['net_return_inr'],63)
        self.assertEqual(f['net_per_sellable_kg'],6.3)
        self.assertFalse(f['dsr_applied'])
        self.assertIsNone(f['quality_loss_estimate'])

    def test_partial_opt_in_and_buyer_support_are_both_required(self):
        for allow,support in ((False,True),(True,False)):
            p=offer_plan(buyer(max_quantity_kg=5,partial_sales_supported=support),10,allow,NOW)
            self.assertEqual(p['status'],'capacity_exceeded')
            self.assertFalse(p['can_prepare_draft'])
        f=outcome(buyer(max_quantity_kg=5),10,True)
        self.assertEqual(f['sale_quantity_kg'],5)
        self.assertEqual(f['unsold_quantity_kg'],5)
        self.assertEqual(f['gross_sale_inr'],50)
        self.assertEqual(f['net_return_inr'],25)
        self.assertEqual(f['net_per_sellable_kg'],5)

    def test_below_minimum_and_invalid_capacity(self):
        f=outcome(buyer(min_quantity_kg=20))
        self.assertEqual(f['status'],'below_minimum')
        self.assertFalse(f['rankable'])
        for change in ({'max_quantity_kg':0},{'max_quantity_kg':'nan'},{'min_quantity_kg':2000},
                       {'partial_sales_supported':'yes'}):
            self.assertEqual(offer_plan(buyer(**change),10,False,NOW)['status'],'invalid_offer')

    def test_missing_offer_and_price_are_not_forecasts(self):
        for record in ({'id':'none'},buyer(price_inr_per_kg=None)):
            f=outcome(record)
            self.assertEqual(f['status'],'missing_offer')
            self.assertFalse(f['rankable'])
            self.assertIsNone(f['net_return_inr'])
            self.assertTrue(f['can_prepare_draft'])

    def test_invalid_prices_and_fees_cannot_be_ranked(self):
        for price in (0,-1,True,'nan','inf',[],{},1.001):
            with self.subTest(price=price):
                f=outcome(buyer(price_inr_per_kg=price))
                self.assertEqual(f['status'],'invalid_offer')
                self.assertFalse(f['can_prepare_draft'])
        for charge in ({'label':'Fee','type':'percent_of_gross','value':101},
                       {'label':'Fee','type':'fixed','value':-1}, {'label':'Fee','type':'unknown','value':1}):
            self.assertEqual(outcome(buyer(selling_charges=[charge]))['status'],'invalid_offer')

    def test_real_offer_provenance_and_expiry(self):
        invalid=buyer(kind='buyer_offer',source='Buyer quote',valid_until=(NOW+timedelta(days=1)).isoformat())
        self.assertEqual(outcome(invalid)['status'],'invalid_offer')
        record={**invalid,'demo':False}
        self.assertEqual(outcome(record)['offer_label'],'Actual buyer offer')
        for change in ({'source':''},{'valid_until':NOW.isoformat()},{'valid_until':'2026-10-25T00:00:00'}):
            altered={**record,'offer':{**record['offer'],**change}}
            self.assertEqual(outcome(altered)['status'],'invalid_offer')

    def test_expiry_and_missing_route_exclude_financial_ranking(self):
        self.assertFalse(outcome(shelf=False)['rankable'])
        self.assertFalse(outcome(transport=None)['rankable'])
        self.assertIsNone(outcome(transport=None)['net_return_inr'])

    def test_losses_are_not_clipped_and_money_rounds_to_paise(self):
        self.assertEqual(outcome(transport=200)['net_return_inr'],-100)
        f=outcome(buyer(price_inr_per_kg=0.01,min_quantity_kg=0.1),kg=0.5,transport=0)
        self.assertEqual(f['gross_sale_inr'],0.01)
        self.assertEqual(f['net_per_sellable_kg'],0.02)

    def test_rank_only_comparable_quantities_and_preserve_ties(self):
        records=[{'id':'a','shelf_life':{'can_select':True},'financial':outcome()},
                 {'id':'b','shelf_life':{'can_select':True},'financial':outcome()},
                 {'id':'partial','shelf_life':{'can_select':True},'financial':outcome(buyer(max_quantity_kg=5),partial=True)}]
        groups=rank_buyers(records)
        self.assertEqual(len(groups),2)
        self.assertEqual([b['financial']['rank'] for b in records],[1,1,1])
        self.assertTrue(all(b['financial']['is_best'] for b in records))
