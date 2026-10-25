"""Unit tests for prototype metric calculations; no network calls."""

import unittest

from .evaluate_prototype_metrics import routing_coverage, shelf_life_check, summary


class PrototypeMetricsTests(unittest.TestCase):
    """Test calculations with small local values."""

    def test_routing_coverage_separates_same_location_pairs(self) -> None:
        rows = [
            {"source_location_id": "A", "destination_location_id": "A", "status": "ok"},
            {"source_location_id": "A", "destination_location_id": "B", "status": "ok"},
            {"source_location_id": "B", "destination_location_id": "A", "status": "no_route"},
        ]

        result = routing_coverage(rows)

        self.assertEqual(result["all_entries"]["total"], 3)
        self.assertEqual(result["all_entries"]["same_location"], 1)
        self.assertEqual(result["all_entries"]["successful"], 2)
        self.assertEqual(result["all_entries"]["unavailable"], 1)
        self.assertEqual(result["distinct_locations"]["total"], 2)
        self.assertEqual(result["distinct_locations"]["same_location"], 0)
        self.assertEqual(result["distinct_locations"]["successful"], 1)
        self.assertEqual(result["distinct_locations"]["unavailable"], 1)

    def test_summary_reports_population_statistics_and_count(self) -> None:
        result = summary([10.0, 20.0, 30.0])

        self.assertEqual(result["count"], 3)
        self.assertEqual(result["mean"], 20.0)
        self.assertEqual(result["median"], 20.0)
        self.assertEqual(result["minimum"], 10.0)
        self.assertEqual(result["maximum"], 30.0)
        self.assertEqual(result["range"], 20.0)
        self.assertAlmostEqual(result["standard_deviation"], 8.1649658)

    def test_shelf_life_check_converts_minutes_and_adds_constraints(self) -> None:
        row = {
            "farmer_to_hub_time_minutes": "600",
            "hub_to_buyer_time_minutes": "840",
            "total_travel_time_minutes": "1440",
            "handling_time_days": "0.5",
            "safety_margin_days": "0.5",
            "remaining_shelf_life_days": "2.0",
            "total_time_consumed_days": "2.0000",
            "remaining_shelf_life_margin_days": "0.0000",
        }

        result = shelf_life_check(row)

        self.assertAlmostEqual(result["total_travel_days"], 1.0)
        self.assertTrue(result["feasible"])
        self.assertTrue(result["total_consistent"])
        self.assertTrue(result["margin_consistent"])

    def test_shelf_life_check_rejects_over_limit(self) -> None:
        row = {
            "farmer_to_hub_time_minutes": "700",
            "hub_to_buyer_time_minutes": "741",
            "total_travel_time_minutes": "1441",
            "handling_time_days": "0.5",
            "safety_margin_days": "0.5",
            "remaining_shelf_life_days": "1.0",
            "total_time_consumed_days": "2.0007",
            "remaining_shelf_life_margin_days": "-1.0007",
        }

        result = shelf_life_check(row)

        self.assertFalse(result["feasible"])
        self.assertTrue(result["total_consistent"])
        self.assertTrue(result["margin_consistent"])


if __name__ == "__main__":
    unittest.main()
