import unittest

from pricing.fair_price_engine import (
    calculate_dsr,
    calculate_dsr_multiplier,
    calculate_fair_price,
    calculate_price_from_var_base,
    calculate_transport_cost_per_quintal,
    create_fair_price_band,
    get_location_multiplier,
    get_quality_multiplier,
)


class FairPriceEngineTests(unittest.TestCase):
    def test_calculate_dsr_and_reject_zero_demand(self) -> None:
        self.assertEqual(calculate_dsr(9000, 10000), 0.9)
        with self.assertRaises(ValueError):
            calculate_dsr(1, 0)

    def test_dsr_multiplier_adjustments_and_bounds(self) -> None:
        self.assertGreater(calculate_dsr_multiplier(1.2, 0.1), 0.85)
        self.assertLess(calculate_dsr_multiplier(1.2, 0.1), 1.0)
        self.assertGreater(calculate_dsr_multiplier(0.8, 0.1), 1.0)
        self.assertEqual(calculate_dsr_multiplier(1.0, 0.1), 1.0)
        self.assertEqual(calculate_dsr_multiplier(100, 1), 0.85)
        self.assertEqual(calculate_dsr_multiplier(0, 1), 1.15)

    def test_quality_multiplier_configuration_and_default(self) -> None:
        configured = {"A": 1.05, "B": 1.0, "C": 0.95}
        self.assertEqual(get_quality_multiplier("A", configured), 1.05)
        self.assertEqual(get_quality_multiplier("unknown", configured, 1.0), 1.0)
        with self.assertRaises(ValueError):
            get_quality_multiplier("unknown", configured)

    def test_location_multiplier_is_configurable_and_validated(self) -> None:
        self.assertEqual(get_location_multiplier(1.0), 1.0)
        with self.assertRaises(ValueError):
            get_location_multiplier(-0.1)

    def test_transport_cost_conversion(self) -> None:
        self.assertEqual(calculate_transport_cost_per_quintal(800, 500), 160.0)
        with self.assertRaises(ValueError):
            calculate_transport_cost_per_quintal(-1, 500)
        with self.assertRaises(ValueError):
            calculate_transport_cost_per_quintal(800, 0)

    def test_fair_price_formula_rounding_and_dsr_bounds(self) -> None:
        price = calculate_fair_price(743.05, 1.01, 1.05, 1.0, 160)
        self.assertEqual(price, 628.0)
        with self.assertRaises(ValueError):
            calculate_fair_price(100, 1.16, 1, 1, 0)
        with self.assertRaises(ValueError):
            calculate_fair_price(-1, 1, 1, 1, 0)

    def test_fair_price_never_returns_negative(self) -> None:
        self.assertEqual(calculate_fair_price(10, 1, 1, 1, 100), 0.0)

    def test_band_uses_configured_offsets_and_clamps_minimum(self) -> None:
        self.assertEqual(
            create_fair_price_band(20, 25, 25),
            {"min_price": 0.0, "fair_price": 20.0, "max_price": 45.0},
        )

    def test_public_pipeline_returns_explainable_band(self) -> None:
        result = calculate_price_from_var_base(
            var_base_price=743.05,
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
        self.assertEqual(result["dsr"], 0.9)
        self.assertEqual(result["transport_cost_per_quintal"], 160.0)
        self.assertEqual(result["min_price"], 603.0)
        self.assertEqual(result["fair_price"], 628.0)
        self.assertEqual(result["max_price"], 653.0)


if __name__ == "__main__":
    unittest.main()