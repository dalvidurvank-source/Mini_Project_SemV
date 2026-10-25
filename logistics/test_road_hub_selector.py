"""Local tests for road_hub_selector; no network calls are made."""

import unittest

from .road_hub_selector import build_selection_report


class RoadHubSelectorTests(unittest.TestCase):
    """Verify joins, exclusions, and separate ranking objectives."""

    def setUp(self) -> None:
        self.road_rows = [
            self.road_row("HUB_A", "10.000", "20.00", "ok"),
            self.road_row("HUB_B", "5.000", "30.00", "ok"),
            self.road_row("HUB_C", "1.000", "1.00", "ok"),
        ]
        self.feasibility_rows = [
            self.feasibility_row("HUB_A", "feasible"),
            self.feasibility_row("HUB_B", "feasible"),
            self.feasibility_row("HUB_C", "rejected_shelf_life"),
        ]

    @staticmethod
    def road_row(hub_id: str, distance: str, minutes: str, status: str) -> dict[str, str]:
        return {
            "source_location_id": "FARMER_TEST_SPIT",
            "source_location_name": "Temporary SPIT Mumbai prototype",
            "destination_location_id": hub_id,
            "destination_location_name": hub_id + " name",
            "road_distance_km": distance,
            "estimated_travel_time_minutes": minutes,
            "routing_provider": "local test data",
            "retrieval_timestamp_utc": "2026-01-01T00:00:00Z",
            "status": status,
        }

    @staticmethod
    def feasibility_row(hub_id: str, status: str) -> dict[str, str]:
        return {
            "farmer_location_id": "FARMER_TEST_SPIT",
            "farmer_location_name": "Temporary SPIT Mumbai prototype",
            "hub_id": hub_id,
            "hub_name": hub_id + " name",
            "road_distance_km": "not authoritative",
            "estimated_travel_time_minutes": "not authoritative",
            "feasibility_status": status,
            "explanation": "local test data",
        }

    def test_excludes_non_feasible_hub_and_uses_road_values(self) -> None:
        report = build_selection_report(self.road_rows, self.feasibility_rows)
        by_id = {row.hub_id: row for row in report}

        self.assertEqual(set(by_id), {"HUB_A", "HUB_B", "HUB_C"})
        self.assertEqual(by_id["HUB_A"].road_distance_km, "10.000")
        self.assertEqual(by_id["HUB_A"].estimated_travel_time_minutes, "20.00")
        self.assertEqual(by_id["HUB_C"].selection_status, "excluded")
        self.assertIn("feasibility status is rejected_shelf_life", by_id["HUB_C"].exclusion_reason)

    def test_distance_and_time_rankings_are_independent(self) -> None:
        report = build_selection_report(self.road_rows, self.feasibility_rows)
        by_id = {row.hub_id: row for row in report}

        # HUB_B is shortest, while HUB_A is fastest among feasible hubs.
        self.assertEqual(by_id["HUB_B"].distance_rank, "1")
        self.assertEqual(by_id["HUB_A"].distance_rank, "2")
        self.assertEqual(by_id["HUB_A"].time_rank, "1")
        self.assertEqual(by_id["HUB_B"].time_rank, "2")
        self.assertEqual(by_id["HUB_C"].distance_rank, "")

    def test_non_ok_route_is_excluded(self) -> None:
        road_rows = list(self.road_rows)
        road_rows[0] = self.road_row("HUB_A", "10.000", "20.00", "no_route")
        report = build_selection_report(road_rows, self.feasibility_rows)
        hub_a = next(row for row in report if row.hub_id == "HUB_A")

        self.assertEqual(hub_a.selection_status, "excluded")
        self.assertIn("route status is no_route", hub_a.exclusion_reason)


if __name__ == "__main__":
    unittest.main()
