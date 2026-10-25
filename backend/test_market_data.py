import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.market_data import fetch_api, import_csv, observations, refresh_api, status


def record(date="23/10/2026", modal=800, market="APMC Ratnagiri (Nachane)"):
    return {"state": "Maharashtra", "district": "Ratnagiri", "market": market,
            "commodity": "Tomato", "variety": "Other", "grade": "Local",
            "arrival_date": date, "min_price": 600, "max_price": 900,
            "modal_price": modal}


class OfficialMarketDataTests(unittest.TestCase):
    def test_pagination_uses_actual_count_and_detects_truncation(self):
        calls = []
        rows = [record(market=f"M{i}") for i in range(12)]
        def requester(params, timeout):
            calls.append(params.copy())
            offset = int(params["offset"])
            page = rows[offset:offset + 10]  # documented sample-key cap
            return {"status": "ok", "total": 12, "count": len(page), "records": page}
        result, meta = fetch_api("key", page_size=100, requester=requester)
        self.assertEqual(len(result), 12)
        self.assertEqual([call["offset"] for call in calls], [0, 10])
        self.assertEqual(meta["page_count"], 2)

        with self.assertRaisesRegex(RuntimeError, "stopped"):
            fetch_api("key", requester=lambda params, timeout: {
                "status": "ok", "total": 2, "count": 0, "records": []})

    def test_refresh_is_repeatable_and_keeps_raw_separate(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); db = root / "market.sqlite"; raw = root / "raw"
            requester = lambda params, timeout: {
                "status": "ok", "total": 1, "count": 1, "records": [record()]}
            first = refresh_api(api_key="key", db_path=db, raw_dir=raw, requester=requester)
            second = refresh_api(api_key="key", db_path=db, raw_dir=raw, requester=requester)
            self.assertEqual(first["inserted"], 1)
            self.assertEqual(second["status"], "unchanged")
            self.assertEqual(len(observations(db)), 1)
            self.assertTrue(Path(first["payload_path"]).exists())
            self.assertIsNone(observations(db)[0]["weight_unit"])

    def test_failed_refresh_preserves_last_valid_dataset(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); db = root / "market.sqlite"; raw = root / "raw"
            refresh_api(api_key="key", db_path=db, raw_dir=raw,
                        requester=lambda params, timeout: {
                            "status": "ok", "total": 1, "count": 1, "records": [record()]})
            with self.assertRaises(RuntimeError):
                refresh_api(api_key="key", db_path=db, raw_dir=raw,
                            requester=lambda params, timeout: (_ for _ in ()).throw(RuntimeError("offline")))
            self.assertEqual(status(db)["observations"], 1)

    def test_csv_import_validates_units_dates_prices_duplicates_and_conflicts(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); db = root / "market.sqlite"; raw = root / "raw"
            path = root / "official.csv"
            fields = ["State", "District", "Market", "Commodity", "Variety", "Grade",
                      "Arrival Date", "Min Price (Rs./Quintal)",
                      "Max Price (Rs./Quintal)", "Modal Price (Rs./Quintal)"]
            rows = [
                ["Maharashtra","Pune","Pune(Pimpri)","Tomato","Local","Local","22/10/2026",900,1300,1100],
                ["Maharashtra","Pune","Pune(Pimpri)","Tomato","Local","Local","22/10/2026",900,1300,1100],
                ["Maharashtra","Pune","Pune(Pimpri)","Tomato","Local","Local","22/10/2026",900,1400,1200],
                ["Maharashtra","Pune","Pune(Pimpri)","Tomato","Local","Local","bad",900,1300,1100],
                ["Maharashtra","Pune","Pune(Pimpri)","Tomato","Local","Local","21/10/2026",900,1000,1100],
            ]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle); writer.writerow(fields); writer.writerows(rows)
            result = import_csv(path, db_path=db, raw_dir=raw)
            self.assertEqual(result["rows_valid"], 3)
            self.assertEqual(result["rows_rejected"], 2)
            self.assertEqual(result["inserted"], 2)  # exact duplicate prevented
            saved = observations(db)
            self.assertTrue(all(row["weight_unit"] == "quintal" for row in saved))
            self.assertEqual(status(db)["conflicting_keys"], 1)


if __name__ == "__main__":
    unittest.main()
