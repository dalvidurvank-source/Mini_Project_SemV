import csv
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from pricing.market_balance import market_balance, FIELDS

SELECTION = dict(crop='Tomato',state='Maharashtra',district='Nashik',market='Nasik',variety='Other')


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'balance.csv'
        self.env = patch.dict(os.environ,{'AGROLINK_BALANCE_CSV':str(self.path),'AGROLINK_DSR_SENSITIVITY':'0.10'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.row = {**SELECTION,'period_start':'2024-03-01','period_end':'2024-03-31','supply_kg':500,
                    'demand_kg':1000,'source':'Test-only fixture, not live evidence','available_on':'2024-02-01'}

    def write(self, rows):
        with self.path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)

    def balance(self):
        return market_balance(SELECTION,'2024-03',date(2024,2,29))

    def test_missing_demand_stays_neutral(self):
        self.assertEqual(self.balance()['multiplier'],1)
        self.assertIsNone(self.balance()['ratio'])

    def test_matched_backend_evidence_adjusts_price(self):
        self.write([self.row])
        r = self.balance()
        self.assertEqual(r['status'],'available')
        self.assertEqual(r['ratio'],0.5)
        self.assertEqual(r['multiplier'],1.05)

    def test_future_evidence_never_leaks_into_forecast(self):
        self.write([{**self.row,'available_on':'2024-03-01'}])
        self.assertEqual(self.balance()['status'],'unavailable')

    def test_wrong_market_variety_or_period_does_not_match(self):
        for change in ({'market':'Kolar'},{'variety':'Tomato'},{'period_end':'2024-03-30'}):
            self.write([{**self.row,**change}])
            self.assertEqual(self.balance()['status'],'unavailable')

    def test_invalid_conflicting_evidence_stays_neutral(self):
        for rows in ([self.row,self.row],[{**self.row,'demand_kg':0}],[{**self.row,'supply_kg':'nan'}],[{**self.row,'source':''}]):
            self.write(rows)
            r = self.balance()
            self.assertEqual(r['status'],'invalid_evidence')
            self.assertEqual(r['multiplier'],1)

    def test_extreme_ratio_is_bounded(self):
        self.write([{**self.row,'supply_kg':100000}])
        self.assertEqual(self.balance()['multiplier'],0.85)
