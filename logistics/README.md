# AgroLink Logistics Module

This module demonstrates distance-based hub evaluation, tomato shelf-life filtering, and minimum composite-cost routing through feasible hubs. Hub locations and buyer-edge routing values are synthetic demonstration data; they do not represent real logistics facilities or measured routes.

## Implemented Pipeline

```text
Farmer GPS
  -> Haversine distance to each synthetic hub
  -> Farmer-to-hub shelf-life filter
  -> Complete farmer-to-hub-to-buyer feasibility check
  -> Dijkstra on the complete-route-feasible graph
  -> Minimum composite-cost route
```

The hub selector first rejects hubs whose estimated farmer-to-hub transit does not meet the shelf-life constraint. The route optimizer then checks total transit time for each remaining hub, including the hub-to-buyer leg. Only routes that pass this complete-route check are added to the graph supplied to Dijkstra. Dijkstra chooses by composite edge weight, not by nearest hub or lowest transport cost alone.

## Haversine Distance

`haversine.py` implements the great-circle Haversine formula. Latitude and longitude are supplied in degrees and converted to radians before calculation:

```text
a = sin^2(DeltaLatitude / 2)
    + cos(latitude_1) * cos(latitude_2) * sin^2(DeltaLongitude / 2)
central_angle = 2 * atan2(sqrt(a), sqrt(1 - a))
distance_km = R * central_angle
```

The Earth radius is `R = 6371 km`. Coordinates are range-checked and invalid values raise `ValueError`.

## Tomato Shelf-Life Rule

All transit and handling times are in days. The shared `is_route_feasible()` function in `shelf_life.py` implements:

```text
TravelTime + HandlingTime <= RemainingShelfLife - SafetyMargin
```

Current hub-selector demonstration values:

- `REMAINING_SHELF_LIFE_DAYS = 4.0`
- `HANDLING_TIME_DAYS = 0.5`
- `SAFETY_MARGIN_DAYS = 0.5`

Therefore, allowable travel time is `4.0 - 0.5 - 0.5 = 3.0 days`; equality passes. At the route-optimization stage, both transit legs are combined and checked by the same `is_route_feasible()` function. A hub that passes the first-leg check can still be rejected if the complete route fails.

## Composite Route Cost

For each directed graph edge, `dijkstra.py` computes:

```text
W(u, v) = alpha * Distance(u, v) + beta * TransportCost(u, v)
```

`alpha` and `beta` are configurable, non-negative weights that must sum to `1`. They default to `0.5` each. The Dijkstra search uses a priority queue and returns the selected node path, total composite cost, and per-edge `RouteStep` details.

## Files and Responsibilities

- `haversine.py` provides `haversine_distance(lat1, lon1, lat2, lon2)` for validated great-circle distance in kilometres.
- `shelf_life.py` provides `is_route_feasible(...)` for the shared time feasibility rule and `remaining_allowable_travel_time(...)` for the travel-time budget.
- `hub_selector.py` defines `Hub`, `HubEvaluation`, and `HubEvaluationBatch`. `evaluate_hubs(...)` computes distance and travel time for each synthetic hub, returns results ranked by distance, and exposes `feasible_results` separately from `rejected_results`.
- `dijkstra.py` defines weighted graph `Edge`, per-edge `RouteStep`, and `DijkstraResult`. `dijkstra_shortest_path(graph, source, destination, alpha, beta)` searches a supplied graph and returns its minimum-composite-cost path.
- `route_optimizer.py` defines synthetic `HubBuyerRoute` data and `RouteOptimizationResult`. `build_feasible_routing_graph(...)` includes only selector-feasible hubs whose complete farmer-to-hub-to-buyer transit passes the shelf-life check. `optimize_route(...)` evaluates hubs when no evaluation batch is supplied, applies the complete-route check, delegates path selection to Dijkstra, and reports feasible candidates and rejected complete routes.
- `test_logistics.py` contains the standard-library unit tests for Haversine, shelf-life checks, hub filtering, Dijkstra, and route-optimizer integration. Running it also prints the hub-filtering demo.

The synthetic hub records are in `hub_selector.HARD_CODED_HUBS`. Synthetic hub-to-buyer edge values are in `route_optimizer.DEMO_HUB_TO_BUYER_ROUTES`; these are static example values that can be edited for demonstrations.

## Demonstration Data and Limitations

The four hubs are labeled `Demo Hub 1` through `Demo Hub 4` and are synthetic. The buyer-edge route data is also synthetic and currently provided for Demo Hub 2 and Demo Hub 3. No external map or routing data is queried.

Current routing uses synthetic/static edge data. Live traffic and live GPS are not implemented. Min-Cost Max-Flow is not implemented yet. APIs, databases, road-map graph construction, and a GUI are also outside this module's current scope.

## Run Tests and Demo

Run these commands from the AgroLink project root:

```powershell
python -m logistics.test_logistics
python -m logistics.route_optimizer
```

The first command runs the logistics test suite and prints the hub-filtering demonstration. The second prints the route-optimization demonstration, including the selected route, composite cost, route steps, complete-route-feasible candidates, and complete routes rejected by shelf life.
