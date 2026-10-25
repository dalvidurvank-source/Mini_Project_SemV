"""Unit tests for observed Nashik tomato market-price data."""

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from .market_data import (
    DEFAULT_DATA_PATH,
    load_market_data,
    summarize_market_data,
    summarize_monthly_prices,
)


class TestMarketData(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _write_csv(self, rows: list[dict[str, object]]) -> Path:
        path = Path(self.temp_dir.name) / "market_data.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    @staticmethod
    def _valid_row(**overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "t": "2025-10-30",
            "cmdty": "Tomato",
            "market_id": 170,
            "market_name": "Pimpalgaon",
            "state_id": 27,
            "state_name": "Maharashtra",
            "district_id": 516,
            "district_name": "Nashik",
            "variety": "Other",
            "p_min": 200,
            "p_max": 1700,
            "p_modal": 1055,
        }
        row.update(overrides)
        return row

    def test_loads_custom_csv_and_summarizes_observed_records(self) -> None:
        rows = [
            self._valid_row(
                t="2025-10-30",
                cmdty=" tomato ",
                state_name=" MAHARASHTRA ",
                district_name=" Nashik ",
                market_id=170,
                p_min=50,
                p_modal=100,
            ),
            self._valid_row(
                t="2025-10-31",
                market_id=168,
                p_modal=200,
            ),
            self._valid_row(
                t="2025-11-01",
                market_id=170,
                p_modal=300,
            ),
        ]
        data = load_market_data(self._write_csv(rows))

        self.assertEqual(len(data), 3)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(data["t"]))
        for column in ("p_min", "p_max", "p_modal"):
            self.assertTrue(pd.api.types.is_numeric_dtype(data[column]))

        summary = summarize_market_data(data)
        self.assertEqual(summary["total_records"], 3)
        self.assertEqual(summary["unique_markets"], 2)
        self.assertEqual(summary["unique_observed_dates"], 3)
        self.assertEqual(summary["earliest_date"], pd.Timestamp("2025-10-30"))
        self.assertEqual(summary["latest_date"], pd.Timestamp("2025-11-01"))

        monthly = summarize_monthly_prices(data)
        self.assertEqual(monthly["month"].tolist(), ["2025-10", "2025-11"])
        self.assertEqual(monthly["average_modal_price"].tolist(), [150.0, 300.0])
        self.assertEqual(monthly["observation_count"].tolist(), [2, 1])
        self.assertEqual(monthly["unique_markets"].tolist(), [2, 1])

    def test_default_path_is_resolved_from_project_root(self) -> None:
        self.assertTrue(DEFAULT_DATA_PATH.is_absolute())
        self.assertTrue(DEFAULT_DATA_PATH.is_file())
        previous_directory = Path.cwd()
        self.addCleanup(os.chdir, previous_directory)
        os.chdir(self.temp_dir.name)
        data = load_market_data()
        self.assertGreater(len(data), 0)

    def test_missing_required_column_raises_informative_error(self) -> None:
        row = self._valid_row()
        del row["market_name"]

        with self.assertRaisesRegex(ValueError, "market_name"):
            load_market_data(self._write_csv([row]))

    def test_invalid_date_raises_informative_error(self) -> None:
        path = self._write_csv([self._valid_row(t="not-a-date")])

        with self.assertRaisesRegex(ValueError, "invalid dates.*CSV data row 2"):
            load_market_data(path)

    def test_nonnumeric_price_raises_informative_error(self) -> None:
        path = self._write_csv([self._valid_row(p_modal="unknown")])

        with self.assertRaisesRegex(ValueError, "p_modal.*CSV data row 2"):
            load_market_data(path)

    def test_negative_and_inconsistent_prices_raise_informative_errors(self) -> None:
        invalid_rows = (
            self._valid_row(p_min=-1),
            self._valid_row(p_min=100, p_modal=50),
        )
        for row in invalid_rows:
            with self.subTest(row=row):
                with self.assertRaisesRegex(ValueError, "Invalid market prices"):
                    load_market_data(self._write_csv([row]))

    def test_records_from_other_district_or_commodity_are_rejected(self) -> None:
        incorrect_records = (
            ("district_name", "Pune"),
            ("cmdty", "Onion"),
            ("state_name", "Gujarat"),
        )
        for column, incorrect_value in incorrect_records:
            with self.subTest(column=column):
                path = self._write_csv(
                    [self._valid_row(**{column: incorrect_value})]
                )
                with self.assertRaisesRegex(ValueError, column):
                    load_market_data(path)


if __name__ == "__main__":
    unittest.main()
