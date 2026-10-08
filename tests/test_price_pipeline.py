import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from pricing.price_pipeline import generate_agrolink_price


class PricePipelineTests(unittest.TestCase):
    @patch("pricing.price_pipeline.get_model_report")
    @patch("pricing.price_pipeline.predict_base_price")
    def test_var_base_price_flows_into_fair_price_engine(
        self,
        predict_base_price: MagicMock,
        get_model_report: MagicMock,
    ) -> None:
        historical_data = pd.DataFrame({"Market Name": ["Davangere"]})
        var_price = 812.345678
        predict_base_price.return_value = var_price
        get_model_report.return_value = {
            "selected_model": "VAR_LOG",
            "selected_lag": 3,
        }

        result = generate_agrolink_price(
            historical_data=historical_data,
            p_lags=None,
            total_regional_supply=9000,
            total_regional_demand=10000,
            quality_grade="A",
            quality_multipliers={"A": 1.05},
            location_multiplier=1.0,
            total_transport_cost=800,
            quantity_kg=500,
            dsr_sensitivity=0.1,
            band_lower_offset=25,
            band_upper_offset=25,
        )

        predict_base_price.assert_called_once_with(historical_data, None)
        get_model_report.assert_called_once_with(historical_data, p_lags=None)

        self.assertGreaterEqual(result["var_base_price"], 0)
        self.assertEqual(result["var_base_price"], var_price)
        self.assertGreaterEqual(result["fair_price"], 0)
        self.assertLessEqual(result["price_band"]["min"], result["price_band"]["fair"])
        self.assertLessEqual(result["price_band"]["fair"], result["price_band"]["max"])
        self.assertEqual(result["forecast_model"], "VAR_LOG")
        self.assertEqual(result["forecast_lag"], 3)

    @patch("pricing.price_pipeline.get_model_report")
    @patch("pricing.price_pipeline.predict_base_price", return_value=-1.0)
    def test_rejects_negative_var_base_price(
        self,
        _predict_base_price: MagicMock,
        get_model_report: MagicMock,
    ) -> None:
        get_model_report.return_value = {
            "selected_model": "VAR_LOG",
            "selected_lag": 3,
        }

        with self.assertRaises(ValueError):
            generate_agrolink_price(
                historical_data=pd.DataFrame(),
                p_lags=None,
                total_regional_supply=1,
                total_regional_demand=1,
                quality_grade="A",
                quality_multipliers={"A": 1.0},
                location_multiplier=1.0,
                total_transport_cost=0,
                quantity_kg=100,
                dsr_sensitivity=0.1,
                band_lower_offset=0,
                band_upper_offset=0,
            )


if __name__ == "__main__":
    unittest.main()