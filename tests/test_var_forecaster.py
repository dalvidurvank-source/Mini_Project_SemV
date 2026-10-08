import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from forecasting.var_forecaster import (
    _evaluate_single_model,
    _fit_and_forecast_model,
    _validate_var_matrix,
    choose_lag_order,
    regularize_monthly_series,
)


class VarForecasterTests(unittest.TestCase):
    @patch("forecasting.var_forecaster._fit_and_forecast_model")
    @patch("forecasting.var_forecaster.choose_lag_order", return_value=2)
    def test_rolling_predictions_reuse_selected_lag(
        self,
        choose_lag_order_mock: MagicMock,
        fit_forecast_mock: MagicMock,
    ) -> None:
        index = pd.date_range("2020-01-01", periods=30, freq="MS")
        steps = np.arange(len(index), dtype=np.float64)
        monthly = pd.DataFrame(
            {
                "wholesale_price": 400 + 1.2 * steps + np.sin(steps / 3),
                "arrival_volume": 200 + 2.1 * steps + np.cos(steps / 4),
            },
            index=index,
        )
        fit_forecast_mock.return_value = {"predicted_price": 500.0}

        _evaluate_single_model(
            monthly,
            test_size=0.20,
            transform_log=True,
        )

        choose_lag_order_mock.assert_called_once()
        self.assertEqual(fit_forecast_mock.call_count, 6)
        for call in fit_forecast_mock.call_args_list:
            self.assertEqual(call.kwargs["p_lags"], 2)
            self.assertTrue(call.kwargs["transform_log"])

    def test_reports_when_all_lag_aic_values_are_non_finite(self) -> None:
        model_data = pd.DataFrame(
            {
                "wholesale_price": range(40),
                "arrival_volume": range(40),
            },
            index=pd.date_range("2020-01-01", periods=40, freq="MS"),
        )
        fitted_model = MagicMock()
        fitted_model.aic = float("inf")
        var_model = MagicMock()
        var_model.fit.return_value = fitted_model

        with patch("forecasting.var_forecaster.VAR", return_value=var_model):
            with self.assertRaisesRegex(
                ValueError,
                "No numerically stable VAR model could be fitted",
            ):
                choose_lag_order(model_data)

    def test_regularizes_sparse_monthly_series_to_finite_month_starts(self) -> None:
        index = pd.date_range("2020-01-01", periods=36, freq="MS").delete(12)
        model_data = pd.DataFrame(
            {
                "wholesale_price": np.linspace(400, 700, len(index)),
                "arrival_volume": np.linspace(100, 250, len(index)),
            },
            index=index,
        )

        regular = regularize_monthly_series(model_data)

        self.assertEqual(len(regular), 36)
        self.assertEqual(regular.index.freqstr, "MS")
        self.assertFalse(regular.isna().any().any())
        self.assertTrue(np.isfinite(regular.to_numpy()).all())

    def test_sparse_input_can_be_forecast_directly(self) -> None:
        index = pd.date_range("2018-01-01", periods=48, freq="MS").delete(17)
        steps = np.arange(len(index), dtype=np.float64)
        model_data = pd.DataFrame(
            {
                "wholesale_price": 500 + 1.5 * steps + 20 * np.sin(steps / 4),
                "arrival_volume": 800 + 2.0 * steps + 40 * np.cos(steps / 5),
            },
            index=index,
        )

        result = _fit_and_forecast_model(model_data, p_lags=1)

        self.assertEqual(result["model_data"].index.freqstr, "MS")
        self.assertTrue(np.isfinite(result["predicted_price"]))

    def test_validator_reports_nan_counts_and_date_range(self) -> None:
        model_data = pd.DataFrame(
            {
                "wholesale_price": [10.0, 12.0],
                "arrival_volume": [100.0, 120.0],
            },
            index=pd.to_datetime(["2020-01-01", "2020-03-01"]),
        )

        with self.assertRaisesRegex(
            ValueError,
            r"wholesale_price.*1.*arrival_volume.*1.*Rows=3.*2020-01-01.*2020-03-01",
        ):
            _validate_var_matrix(model_data)


if __name__ == "__main__":
    unittest.main()
