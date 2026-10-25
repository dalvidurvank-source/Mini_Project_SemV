"""Local tests for end_to_end_routes; no network calls are made."""

import unittest

from .evaluate_end_to_end_routes import build_end_to_end_report


class EndToEndRouteTests(unittest.TestCase):
    """Verify two-leg joins, shelf-life checks, and distance ranking."""

    @staticmethod
    def road_row(source: str, destination: str, distance: str, minutes: str, status: str = "ok") -> dict[str, str]:
        return {
            "source_location_id": source,
            "source_location_name": source + " name",
            "destination_location_id": destination,
            "destination_location_name": destination + " name",
            "road_distance_km": distance,
            "estimated_travel_time_minutes": minutes,
            "routing_provider": "local test data",
            "retrieval_timestamp_utc": "2026-01-01T00:00:00Z",
            "status": status,
        }

    @staticmethod
    def feasibility_row(hub_id: str, status: str = "feasible") -> dict[str, str]:
        return {
            "farmer_location_id": "FARMER_TEST_SPIT",
            "farmer_location_name": "Temporary SPIT prototype",
            "hub_id": hub_id,
            "hub_name": hub_id + " name",
            "remaining_shelf_life_days": "4.0",
            "handling_time_days": "0.5",
            "safety_margin_days": "0.5",
            "feasibility_status": status,
        }

    def test_uses_two_road_legs_and_ranks_by_total_distance(self) -> None:
        roads = [
            self.road_row("FARMER_TEST_SPIT", "HUB_A", "100", "60"),
            self.road_row("HUB_A", "BUYER_TEST_CHH_SAMBHAJINAGAR", "50", "60"),
            self.road_row("FARMER_TEST_SPIT", "HUB_B", "40", "120"),
            self.road_row("HUB_B", "BUYER_TEST_CHH_SAMBHAJINAGAR", "40", "120"),
        ]
        report = build_end_to_end_report(
            roads,
            [self.feasibility_row("HUB_A"), self.feasibility_row("HUB_B")],
        )
        by_hub = {row.values["hub_id"]: row.values for row in report}

        self.assertEqual(by_hub["HUB_A"]["total_road_distance_km"], "150.000")
        self.assertEqual(by_hub["HUB_A"]["total_travel_time_minutes"], "120.00")
        self.assertEqual(by_hub["HUB_A"]["inclusion_status"], "included")
        self.assertEqual(by_hub["HUB_A"]["total_distance_rank"], "2")
        self.assertEqual(by_hub["HUB_B"]["total_distance_rank"], "1")

    def test_shelf_life_equality_passes_and_safety_is_not_travel(self) -> None:
        roads = [
            # Three travel days plus 0.5 handling plus 0.5 safety equals 4 days.
            self.road_row("FARMER_TEST_SPIT", "HUB_A", "10", "1440"),
            self.road_row("HUB_A", "BUYER_TEST_CHH_SAMBHAJINAGAR", "10", "2880"),
        ]
        report = build_end_to_end_report(roads, [self.feasibility_row("HUB_A")])
        values = report[0].values

        self.assertEqual(values["total_travel_time_minutes"], "4320.00")
        self.assertEqual(values["total_time_consumed_days"], "4.0000")
        self.assertEqual(values["safety_margin_days"], "0.5")
        self.assertEqual(values["inclusion_status"], "included")

    def test_missing_or_failed_leg_is_excluded(self) -> None:
        roads = [
            self.road_row("FARMER_TEST_SPIT", "HUB_A", "10", "60"),
            self.road_row(
                "HUB_A",
                "BUYER_TEST_CHH_SAMBHAJINAGAR",
                "",
                "",
                "no_route",
            ),
        ]
        report = build_end_to_end_report(roads, [self.feasibility_row("HUB_A")])
        values = report[0].values

        self.assertEqual(values["inclusion_status"], "excluded")
        self.assertIn("hub-to-buyer route status is no_route", values["exclusion_reason"])


if __name__ == "__main__":
    unittest.main()
