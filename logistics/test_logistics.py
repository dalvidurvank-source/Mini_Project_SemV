"""Assertions and console demo for the logistics hub evaluator."""

import unittest

from .haversine import haversine_distance
from .dijkstra import Edge, RouteStep, dijkstra_shortest_path
from .hub_selector import (
    HARD_CODED_HUBS,
    HANDLING_TIME_DAYS,
    REMAINING_SHELF_LIFE_DAYS,
    SAFETY_MARGIN_DAYS,
    Hub,
    evaluate_hubs,
)
from .route_optimizer import (
    DEMO_HUB_TO_BUYER_ROUTES,
    HubBuyerRoute,
    build_feasible_routing_graph,
    optimize_route,
)
from .shelf_life import is_route_feasible, remaining_allowable_travel_time

FARMER_LATITUDE = 20.0110
FARMER_LONGITUDE = 73.7900


class TestHaversineDistance(unittest.TestCase):
    def test_same_coordinate_returns_zero(self) -> None:
        self.assertEqual(haversine_distance(20.0, 73.0, 20.0, 73.0), 0.0)

    def test_known_coordinate_pair(self) -> None:
        distance = haversine_distance(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(distance, 111.1949, places=4)

    def test_invalid_latitude_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            haversine_distance(0.0, 0.0, 91.0, 0.0)

    def test_invalid_longitude_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            haversine_distance(0.0, 0.0, 0.0, 181.0)


class TestShelfLife(unittest.TestCase):
    def test_required_travel_time_cases(self) -> None:
        expected_results = (
            (1.0, True),
            (3.0, True),
            (3.1, False),
            (5.0, False),
        )
        for travel_time_days, expected in expected_results:
            with self.subTest(travel_time_days=travel_time_days):
                self.assertEqual(
                    is_route_feasible(travel_time_days, 4.0, 0.5, 0.5),
                    expected,
                )

    def test_remaining_allowable_travel_time(self) -> None:
        self.assertEqual(remaining_allowable_travel_time(4.0, 0.5, 0.5), 3.0)

    def test_negative_allowable_time_is_preserved(self) -> None:
        self.assertEqual(remaining_allowable_travel_time(1.0, 0.5, 1.0), -0.5)
        self.assertFalse(is_route_feasible(0.0, 1.0, 0.5, 1.0))

    def test_negative_inputs_raise_value_error(self) -> None:
        invalid_inputs = (
            (-1.0, 4.0, 0.5, 0.5),
            (1.0, -1.0, 0.5, 0.5),
            (1.0, 4.0, -0.5, 0.5),
            (1.0, 4.0, 0.5, -0.5),
        )
        for arguments in invalid_inputs:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    is_route_feasible(*arguments)

    def test_non_finite_inputs_raise_value_error(self) -> None:
        for invalid_value in (float("nan"), float("inf"), float("-inf")):
            for argument_index in range(4):
                arguments = [1.0, 4.0, 0.5, 0.5]
                arguments[argument_index] = invalid_value
                with self.subTest(value=invalid_value, argument_index=argument_index):
                    with self.assertRaises(ValueError):
                        is_route_feasible(*arguments)

            for argument_index in range(3):
                arguments = [4.0, 0.5, 0.5]
                arguments[argument_index] = invalid_value
                with self.subTest(
                    helper_value=invalid_value,
                    argument_index=argument_index,
                ):
                    with self.assertRaises(ValueError):
                        remaining_allowable_travel_time(*arguments)


class TestHubSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.batch = evaluate_hubs(FARMER_LATITUDE, FARMER_LONGITUDE)

    def test_evaluates_exactly_four_hardcoded_hubs(self) -> None:
        self.assertEqual(len(HARD_CODED_HUBS), 4)
        self.assertEqual(len(self.batch.ranked_results), 4)

    def test_results_and_candidate_collections_are_distance_ranked(self) -> None:
        for results in (self.batch.ranked_results, self.batch.feasible_results,
                        self.batch.rejected_results):
            self.assertEqual(
                [item.distance_km for item in results],
                sorted(item.distance_km for item in results),
            )

    def test_feasible_and_rejected_results_match_flags(self) -> None:
        self.assertGreaterEqual(len(self.batch.feasible_results), 2)
        self.assertGreaterEqual(len(self.batch.rejected_results), 1)
        self.assertTrue(all(item.feasible for item in self.batch.feasible_results))
        self.assertTrue(all(not item.feasible for item in self.batch.rejected_results))

    def test_travel_time_uses_distance_divided_by_speed_and_24(self) -> None:
        for result in self.batch.ranked_results:
            expected_days = result.distance_km / result.hub.average_speed_kmph / 24.0
            self.assertAlmostEqual(result.travel_time_days, expected_days)

    def test_short_trip_passes_and_slow_far_trip_fails(self) -> None:
        hubs = [
            Hub("Short synthetic trip", 0.0, 0.01, 40.0, 100.0),
            Hub("Slow synthetic trip", 0.0, 45.0, 1.0, 10.0),
        ]
        batch = evaluate_hubs(0.0, 0.0, hubs)
        results_by_name = {item.hub.name: item for item in batch.ranked_results}
        self.assertTrue(results_by_name["Short synthetic trip"].feasible)
        self.assertFalse(results_by_name["Slow synthetic trip"].feasible)

    def test_invalid_farmer_coordinates_raise_value_error_without_hubs(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_hubs(91.0, 0.0, [])
        with self.assertRaises(ValueError):
            evaluate_hubs(0.0, 181.0, [])

    def test_no_shelf_life_violating_hub_is_accepted(self) -> None:
        for result in self.batch.feasible_results:
            self.assertTrue(
                is_route_feasible(
                    result.travel_time_days,
                    REMAINING_SHELF_LIFE_DAYS,
                    HANDLING_TIME_DAYS,
                    SAFETY_MARGIN_DAYS,
                )
            )
        for result in self.batch.rejected_results:
            self.assertFalse(
                is_route_feasible(
                    result.travel_time_days,
                    REMAINING_SHELF_LIFE_DAYS,
                    HANDLING_TIME_DAYS,
                    SAFETY_MARGIN_DAYS,
                )
            )


class TestDijkstra(unittest.TestCase):
    def test_simple_three_node_shortest_path(self) -> None:
        graph = {
            "farmer": [Edge("hub", 2.0, 2.0)],
            "hub": [Edge("buyer", 3.0, 3.0)],
            "buyer": [],
        }

        result = dijkstra_shortest_path(graph, "farmer", "buyer")

        self.assertEqual(result.path, ("farmer", "hub", "buyer"))
        self.assertEqual(result.total_composite_cost, 5.0)

    def test_cheaper_multi_hop_path_beats_direct_path(self) -> None:
        graph = {
            "farmer": [Edge("buyer", 10.0, 10.0), Edge("hub", 2.0, 2.0)],
            "hub": [Edge("buyer", 2.0, 2.0)],
            "buyer": [],
        }

        result = dijkstra_shortest_path(graph, "farmer", "buyer")

        self.assertEqual(result.path, ("farmer", "hub", "buyer"))
        self.assertEqual(result.total_composite_cost, 4.0)

    def test_unreachable_destination_returns_empty_path(self) -> None:
        graph = {"farmer": [], "buyer": []}

        result = dijkstra_shortest_path(graph, "farmer", "buyer")

        self.assertFalse(result.reachable)
        self.assertEqual(result.path, ())
        self.assertEqual(result.total_composite_cost, float("inf"))

    def test_zero_weight_edge_is_supported(self) -> None:
        graph = {"farmer": [Edge("hub", 0.0, 0.0)], "hub": []}

        result = dijkstra_shortest_path(graph, "farmer", "hub")

        self.assertEqual(result.path, ("farmer", "hub"))
        self.assertEqual(result.total_composite_cost, 0.0)

    def test_negative_edge_weight_is_rejected(self) -> None:
        graph = {
            "farmer": [Edge("buyer", 1.0, -2.0)],
            "buyer": [],
        }

        with self.assertRaises(ValueError):
            dijkstra_shortest_path(graph, "farmer", "buyer")

    def test_path_reconstruction_includes_edge_details(self) -> None:
        graph = {
            "farmer": [Edge("hub", 6.0, 4.0)],
            "hub": [Edge("buyer", 2.0, 8.0)],
            "buyer": [],
        }

        result = dijkstra_shortest_path(
            graph,
            "farmer",
            "buyer",
            alpha=0.75,
            beta=0.25,
        )

        self.assertEqual(result.path, ("farmer", "hub", "buyer"))
        self.assertEqual(len(result.edges), 2)
        self.assertEqual(
            result.edges,
            (
                RouteStep("farmer", "hub", 6.0, 4.0, 5.5),
                RouteStep("hub", "buyer", 2.0, 8.0, 3.5),
            ),
        )
        self.assertEqual(result.total_composite_cost, 9.0)

    def test_unequal_alpha_beta_use_exact_composite_weight_formula(self) -> None:
        graph = {
            "farmer": [Edge("buyer", 10.0, 2.0)],
            "buyer": [],
        }

        result = dijkstra_shortest_path(
            graph,
            "farmer",
            "buyer",
            alpha=0.8,
            beta=0.2,
        )

        expected_weight = 0.8 * 10.0 + 0.2 * 2.0
        self.assertEqual(result.total_composite_cost, expected_weight)
        self.assertEqual(result.edges[0].composite_cost, expected_weight)

    def test_source_equals_destination_returns_zero_cost_single_node_path(self) -> None:
        graph = {"farmer": [Edge("hub", 1.0, 1.0)], "hub": []}

        result = dijkstra_shortest_path(graph, "farmer", "farmer")

        self.assertEqual(result.path, ("farmer",))
        self.assertEqual(result.total_composite_cost, 0.0)
        self.assertEqual(result.edges, ())

    def test_empty_graph_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dijkstra_shortest_path({}, "farmer", "buyer")

    def test_unknown_source_node_is_rejected(self) -> None:
        graph = {"farmer": [], "buyer": []}
        with self.assertRaises(ValueError):
            dijkstra_shortest_path(graph, "unknown", "buyer")

    def test_unknown_destination_node_is_rejected(self) -> None:
        graph = {"farmer": [], "buyer": []}
        with self.assertRaises(ValueError):
            dijkstra_shortest_path(graph, "farmer", "unknown")

    def test_negative_alpha_or_beta_is_rejected(self) -> None:
        graph = {"farmer": [], "buyer": []}
        for alpha, beta in ((-0.1, 1.1), (1.1, -0.1)):
            with self.subTest(alpha=alpha, beta=beta):
                with self.assertRaises(ValueError):
                    dijkstra_shortest_path(graph, "farmer", "buyer", alpha, beta)

    def test_non_finite_alpha_or_beta_is_rejected(self) -> None:
        graph = {"farmer": [], "buyer": []}
        for alpha, beta in (
            (float("nan"), 1.0),
            (float("inf"), 0.0),
            (0.0, float("-inf")),
        ):
            with self.subTest(alpha=alpha, beta=beta):
                with self.assertRaises(ValueError):
                    dijkstra_shortest_path(graph, "farmer", "buyer", alpha, beta)

    def test_alpha_plus_beta_must_equal_one(self) -> None:
        graph = {"farmer": [], "buyer": []}
        for alpha, beta in ((0.4, 0.4), (0.6, 0.5)):
            with self.subTest(alpha=alpha, beta=beta):
                with self.assertRaises(ValueError):
                    dijkstra_shortest_path(graph, "farmer", "buyer", alpha, beta)


class TestRouteOptimizer(unittest.TestCase):
    def setUp(self) -> None:
        self.farmer_latitude = 0.0
        self.farmer_longitude = 0.0
        self.hubs = [
            Hub("Feasible A", 0.0, 0.01, 40.0, 100.0),
            Hub("Feasible B", 0.0, 0.02, 40.0, 100.0),
            Hub("Complete Route Fail", 0.0, 0.03, 40.0, 100.0),
            Hub("Rejected Near", 0.0, 0.001, 0.00001, 1.0),
        ]
        self.evaluations = evaluate_hubs(
            self.farmer_latitude,
            self.farmer_longitude,
            self.hubs,
        )
        self.routes = {
            "Feasible A": HubBuyerRoute(100.0, 100.0, 1.0),
            "Feasible B": HubBuyerRoute(1.0, 1.0, 1.0),
            "Complete Route Fail": HubBuyerRoute(1.0, 1.0, 3.1),
            "Rejected Near": HubBuyerRoute(0.0, 0.0, 0.0),
        }

    def test_feasible_hub_is_used_in_route(self) -> None:
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
        )

        feasible_node_names = {
            f"hub:{item.hub.name}" for item in self.evaluations.feasible_results
        }
        self.assertTrue(result.reachable)
        self.assertIn(result.selected_path[1], feasible_node_names)

    def test_rejected_hub_is_not_added_to_graph(self) -> None:
        graph = build_feasible_routing_graph(self.evaluations, "buyer", self.routes)

        self.assertNotIn("hub:Rejected Near", graph)
        self.assertNotIn(
            "hub:Rejected Near",
            {edge.target for edge in graph["farmer"]},
        )

    def test_complete_route_passes(self) -> None:
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
        )

        self.assertTrue(
            any(
                candidate.hub_evaluation.hub.name == "Feasible A"
                for candidate in result.feasible_hubs_considered
            )
        )

    def test_complete_route_fails_after_farmer_to_hub_passes(self) -> None:
        evaluation = next(
            item
            for item in self.evaluations.feasible_results
            if item.hub.name == "Complete Route Fail"
        )
        self.assertTrue(evaluation.feasible)

        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
        )

        rejected = next(
            candidate
            for candidate in result.rejected_complete_routes
            if candidate.hub_evaluation.hub.name == "Complete Route Fail"
        )
        self.assertFalse(rejected.feasible)
        self.assertGreater(rejected.total_travel_time_days, 3.0)

    def test_rejected_complete_route_is_not_inserted_into_graph(self) -> None:
        graph = build_feasible_routing_graph(self.evaluations, "buyer", self.routes)

        self.assertNotIn("hub:Complete Route Fail", graph)
        self.assertNotIn(
            "hub:Complete Route Fail",
            {edge.target for edge in graph["farmer"]},
        )

    def test_dijkstra_selects_lower_composite_cost_feasible_route(self) -> None:
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
        )

        self.assertEqual(
            result.selected_path,
            ("farmer", "hub:Feasible B", "buyer"),
        )

    def test_closer_infeasible_hub_cannot_be_selected(self) -> None:
        rejected = next(
            item for item in self.evaluations.ranked_results if item.hub.name == "Rejected Near"
        )
        self.assertLess(
            rejected.distance_km,
            min(item.distance_km for item in self.evaluations.feasible_results),
        )
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
        )
        self.assertNotIn("hub:Rejected Near", result.selected_path)

    def test_unreachable_buyer_is_reported(self) -> None:
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            {},
            hub_evaluations=self.evaluations,
        )

        self.assertFalse(result.reachable)
        self.assertEqual(result.selected_path, ())
        self.assertEqual(result.total_composite_cost, float("inf"))

    def test_alpha_beta_change_the_selected_composite_route(self) -> None:
        competing_routes = {
            "Feasible A": HubBuyerRoute(1.0, 1000.0, 1.0),
            "Feasible B": HubBuyerRoute(100.0, 1.0, 1.0),
        }
        distance_focused = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            competing_routes,
            alpha=1.0,
            beta=0.0,
            hub_evaluations=self.evaluations,
        )
        cost_focused = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            competing_routes,
            alpha=0.0,
            beta=1.0,
            hub_evaluations=self.evaluations,
        )

        self.assertEqual(distance_focused.selected_path[1], "hub:Feasible A")
        self.assertEqual(cost_focused.selected_path[1], "hub:Feasible B")

    def test_selected_path_is_farmer_hub_buyer(self) -> None:
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
        )

        self.assertEqual(result.selected_path[0], "farmer")
        self.assertEqual(result.selected_path[-1], "buyer")
        self.assertEqual(len(result.selected_path), 3)

    def test_dijkstra_route_steps_are_preserved(self) -> None:
        result = optimize_route(
            self.farmer_latitude,
            self.farmer_longitude,
            "buyer",
            self.routes,
            hub_evaluations=self.evaluations,
            alpha=0.75,
            beta=0.25,
        )

        self.assertEqual(len(result.route_steps), 2)
        self.assertEqual(
            tuple((step.source, step.target) for step in result.route_steps),
            (("farmer", "hub:Feasible B"), ("hub:Feasible B", "buyer")),
        )
        self.assertEqual(
            result.route_steps[1].distance,
            self.routes["Feasible B"].distance_km,
        )
        self.assertEqual(
            result.route_steps[1].transport_cost,
            self.routes["Feasible B"].transport_cost,
        )
        self.assertEqual(
            result.route_steps[1].distance,
            self.routes["Feasible B"].distance_km,
        )

    def test_default_synthetic_demo_routes_cover_default_feasible_hubs(self) -> None:
        default_evaluations = evaluate_hubs(20.0110, 73.7900)
        self.assertTrue(
            {item.hub.name for item in default_evaluations.feasible_results}
            <= DEMO_HUB_TO_BUYER_ROUTES.keys()
        )


def run_assertions() -> None:
    test_suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(test_class)
        for test_class in (
            TestHaversineDistance,
            TestShelfLife,
            TestHubSelector,
            TestDijkstra,
            TestRouteOptimizer,
        )
    )
    test_result = unittest.TextTestRunner().run(test_suite)
    if not test_result.wasSuccessful():
        raise AssertionError("Logistics unit tests failed.")


def print_demo() -> None:
    batch = evaluate_hubs(FARMER_LATITUDE, FARMER_LONGITUDE)
    print(
        f"{'Hub':<24} {'Distance (km)':>14} {'Speed (km/h)':>14} "
        f"{'Travel time (days)':>19} {'Cost (₹)':>12} {'Status':>8}  Reason"
    )
    for result in batch.ranked_results:
        print(
            f"{result.hub.name:<24} {result.distance_km:>14.2f} "
            f"{result.hub.average_speed_kmph:>14.4f} {result.travel_time_days:>19.3f} "
            f"{result.hub.transport_cost:>12.2f} {result.feasibility_status:>8}  "
            f"{result.reason}"
        )

    print("\nFeasible candidate hubs:")
    for result in batch.feasible_results:
        print(f"- {result.hub.name}")

    print("\nRejected hubs:")
    for result in batch.rejected_results:
        print(f"- {result.hub.name}: {result.reason}")


def main() -> None:
    run_assertions()
    print_demo()


if __name__ == "__main__":
    main()