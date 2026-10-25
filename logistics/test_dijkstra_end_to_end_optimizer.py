"""Local tests for the end-to-end Dijkstra adapter; no network calls."""

import unittest

from .dijkstra_end_to_end_optimizer import (
    BUYER_ID,
    FARMER_ID,
    build_graph,
    run_objective,
)


class DijkstraEndToEndOptimizerTests(unittest.TestCase):
    """Test each objective and route-exclusion behavior."""

    @staticmethod
    def road_row(source: str, destination: str, distance: str, minutes: str, status: str = "ok") -> dict[str, str]:
        return {
            "source_location_id": source,
            "source_location_name": source + " name",
            "destination_location_id": destination,
            "destination_location_name": destination + " name",
            "road_distance_km": distance,
            "estimated_travel_time_minutes": minutes,
            "status": status,
        }

    @staticmethod
    def report_row(hub_id: str, status: str = "included", feasibility: str = "feasible") -> dict[str, str]:
        return {
            "hub_id": hub_id,
            "hub_name": hub_id + " name",
            "inclusion_status": status,
            "farmer_hub_feasibility_status": feasibility,
        }

    def setUp(self) -> None:
        self.roads = [
            self.road_row(FARMER_ID, "HUB_A", "100", "60"),
            self.road_row("HUB_A", BUYER_ID, "50", "180"),
            self.road_row(FARMER_ID, "HUB_B", "80", "120"),
            self.road_row("HUB_B", BUYER_ID, "80", "60"),
        ]
        self.reports = [self.report_row("HUB_A"), self.report_row("HUB_B")]

    def test_shortest_distance_selection(self) -> None:
        graph, candidates, _ = build_graph(self.roads, self.reports)
        result = run_objective(graph, candidates, "distance_km")

        self.assertEqual(result.dijkstra_result.path, (FARMER_ID, "HUB_A", BUYER_ID))
        self.assertEqual(result.selected_route.hub_id, "HUB_A")
        self.assertAlmostEqual(result.edge_sum_distance, 150.0)
        self.assertTrue(result.edge_sums_match)

    def test_fastest_time_selection(self) -> None:
        graph, candidates, _ = build_graph(self.roads, self.reports)
        result = run_objective(graph, candidates, "time_minutes")

        self.assertEqual(result.dijkstra_result.path, (FARMER_ID, "HUB_B", BUYER_ID))
        self.assertEqual(result.selected_route.hub_id, "HUB_B")
        self.assertAlmostEqual(result.edge_sum_time, 180.0)

    def test_excluded_infeasible_hub_is_not_in_graph(self) -> None:
        reports = [self.report_row("HUB_A"), self.report_row("HUB_B", "excluded", "rejected_shelf_life")]
        graph, candidates, _ = build_graph(self.roads, reports)

        self.assertNotIn("HUB_B", graph)
        self.assertNotIn("HUB_B", candidates)

    def test_missing_route_is_excluded(self) -> None:
        roads = [self.roads[0], self.roads[1], self.roads[2]]
        graph, candidates, _ = build_graph(roads, self.reports)

        self.assertIn("HUB_A", candidates)
        self.assertNotIn("HUB_B", candidates)

    def test_no_feasible_route_is_handled(self) -> None:
        reports = [self.report_row("HUB_A", "excluded", "rejected_shelf_life")]
        graph, candidates, _ = build_graph(self.roads, reports)
        result = run_objective(graph, candidates, "distance_km")

        self.assertFalse(result.dijkstra_result.reachable)
        self.assertIsNone(result.selected_route)
        self.assertIsNone(result.edge_sum_distance)


if __name__ == "__main__":
    unittest.main()
