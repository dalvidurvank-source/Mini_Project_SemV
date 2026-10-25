import unittest
from unittest.mock import patch

from backend import official_market_api


def stored_rows(count=25, conflict=False):
    rows=[]
    for i in range(count):
        day = i + 1
        rows.append({"source":"official_csv","market_key":"official:test",
          "external_market_id":None,"state":"Maharashtra","district":"Pune",
          "market":"Pune(Pimpri)","commodity":"Tomato","variety":"Local",
          "grade":"Local","observation_date":f"2026-09-{day:02d}",
          "retrieved_at":"2026-10-01T00:00:00+00:00","min_price":900,
          "max_price":1300,"modal_price":1000 + i,"currency":"INR",
          "weight_unit":"quintal","unit_evidence":"Official CSV header",
          "provenance":"C:\\private\\fixture.csv"})
    if conflict:
        rows.append({**rows[-1],"modal_price":1200,"max_price":1400})
    return rows


class OfficialMarketApiTests(unittest.TestCase):
    def setUp(self):
        patches=[patch('backend.official_market_api.observations',return_value=stored_rows()),
                 patch('backend.official_market_api.status',return_value={'resource_id':'resource'})]
        for item in patches:
            item.start(); self.addCleanup(item.stop)
        self.params={"source":"official","crop":"Tomato","state":"Maharashtra",
                     "district":"Pune","market":"Pune(Pimpri)",
                     "market_id":"official:test","market_grade":"Local","variety":"Local"}

    def test_catalog_preserves_grade_and_exact_internal_identity(self):
        market=official_market_api.catalog()['markets'][0]
        self.assertEqual(market['market_id'],'official:test')
        self.assertEqual(market['grade'],'Local')

    def test_recorded_and_historical_semantics(self):
        recorded=official_market_api.analyze({**self.params,"mode":"recorded","target_date":"2026-09-25"})
        self.assertEqual(recorded['kind'],'recorded_price')
        self.assertIsNone(recorded['forecast'])
        self.assertEqual(recorded['actual']['provenance'],'Archived official import: fixture.csv')
        historical=official_market_api.analyze({**self.params,"mode":"historical","target_date":"2026-09-22"})
        self.assertEqual(historical['actual']['date'],'2026-09-22')
        self.assertLess(historical['training']['last_date'],historical['actual']['date'])
        self.assertEqual(historical['forecast']['forecast_date'],'2026-09-22')

    def test_conflicting_records_block_series(self):
        with patch('backend.official_market_api.observations',return_value=stored_rows(conflict=True)):
            context=official_market_api.context(self.params)
            self.assertEqual(context['eligibility']['status'],'unavailable')
            self.assertIn('Conflicting',context['eligibility']['reason'])

    def test_future_requires_stale_acknowledgement(self):
        with self.assertRaisesRegex(ValueError,'Acknowledge the stale-data limitation'):
            official_market_api.analyze({**self.params,"mode":"future","target_date":""})
        result = official_market_api.analyze({**self.params,"mode":"future","target_date":"","acknowledge_stale":True})
        self.assertEqual(result["kind"], "market_forecast")
        self.assertIn("not a current market-price forecast", result["warnings"][0])


if __name__ == '__main__':
    unittest.main()
