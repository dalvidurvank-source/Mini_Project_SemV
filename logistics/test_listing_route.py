import unittest
import io
import json
from unittest.mock import patch
from logistics.listing_route import plan_route, solve, route_transport, _live_route


class RoutingTests(unittest.TestCase):
    def test_saved_road_route_runs_real_algorithms(self):
        route = plan_route({'farm_latitude':19.1236,'farm_longitude':72.8361,
                            'destination_latitude':20.015063587300105,'destination_longitude':73.79766078270252})
        self.assertEqual(route['mode'],'saved_road_matrix')
        self.assertGreater(route['distance_km'],route['straight_line_km'])
        self.assertAlmostEqual(route['distance_km'],sum(l['distance_km'] for l in route['legs']))
        self.assertAlmostEqual(route['duration_minutes'],sum(l['duration_minutes'] for l in route['legs']))
        self.assertEqual(route['path'][0]['id'],'FARMER_TEST_SPIT')

    def test_dijkstra_uses_time_and_directed_edges(self):
        nodes = {'a':(0,0),'b':(0,1),'c':(1,1)}
        legs = [dict(source='a',destination='b',distance_km=100,duration_minutes=2),
                dict(source='b',destination='c',distance_km=100,duration_minutes=2),
                dict(source='a',destination='c',distance_km=150,duration_minutes=10)]
        r = solve(nodes,legs,'a','c',{})
        self.assertEqual([p['id'] for p in r['path']],['a','b','c'])
        self.assertEqual(r['distance_km'],200)
        with self.assertRaisesRegex(ValueError,'No connected'):
            solve(nodes,legs,'c','a',{})

    def test_invalid_and_same_location(self):
        for origin in ((91,1),(float('nan'),1),(True,1),('',1)):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                plan_route(dict(farm_latitude=origin[0],farm_longitude=origin[1],destination_latitude=20,destination_longitude=73))
        with self.assertRaisesRegex(ValueError,'same location'):
            plan_route(dict(farm_latitude=20,farm_longitude=73,destination_latitude=20,destination_longitude=73))

    def test_nearby_farm_never_uses_saved_prototype_route(self):
        with patch('logistics.listing_route._live_route',side_effect=ValueError('No road route')) as live:
            with self.assertRaisesRegex(ValueError,'No road route'):
                plan_route(dict(farm_latitude=19.12,farm_longitude=72.83,destination_latitude=20.015063587300105,destination_longitude=73.79766078270252))
        live.assert_called_once()

    def test_no_straight_line_fallback_on_network_failure(self):
        _live_route.cache_clear()
        with patch('logistics.listing_route.urlopen',side_effect=OSError('Offline')):
            with self.assertRaisesRegex(ValueError,'Straight-line distance will not be substituted'):
                _live_route((19,73),(20,74),12345)

    def test_live_matrix_units_and_unreachable_cells(self):
        # No corridor hubs for these points; metric values come from the service.
        response = {'code':'Ok','distances':[[0,150000],[None,0]],'durations':[[0,7200],[None,0]]}
        _live_route.cache_clear()
        with patch('logistics.listing_route.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            route = _live_route((0,0),(0,1),22222)
        self.assertEqual(route['distance_km'],150)
        self.assertEqual(route['duration_minutes'],120)
        self.assertEqual(route['mode'],'online_road_matrix')

    def test_incomplete_live_matrix_is_rejected(self):
        _live_route.cache_clear()
        with patch('logistics.listing_route.urlopen',return_value=io.BytesIO(b'{"code":"Ok","distances":[],"durations":[]}')):
            with self.assertRaisesRegex(ValueError,'Road routing is unavailable'):
                _live_route((0,0),(0,1),33333)

    def test_transport_multiple_trips_and_allocation(self):
        route = dict(distance_km=100,duration_minutes=120,origin={'name':'Farm'},destination={'name':'Market'},
                     provider='Test',retrieved_at='2026-10-24T00:00:00Z',warnings=[])
        p = dict(vehicle_capacity_kg=1000,fuel_efficiency_km_per_litre=10,fuel_price_inr_per_litre=100,
                 empty_return_factor=1,loading_inr=100,unloading_inr=100,tolls_inr=50)
        a = route_transport(p,route,1500)
        self.assertEqual(a['trips'],2)
        self.assertEqual(a['total_trip_cost_inr'],4500)
        self.assertEqual(a['cost_inr_per_kg'],3)
        self.assertEqual(sum(a['components_inr'].values()),4500)
        for key,val in (('vehicle_capacity_kg',0),('fuel_efficiency_km_per_litre',0),('empty_return_factor',2),('fuel_price_inr_per_litre',-1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                route_transport({**p,key:val},route,500)
