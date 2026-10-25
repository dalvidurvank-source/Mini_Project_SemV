"""Haversine screening and Dijkstra over measured, directed OSRM route legs.

The graph is a location/road-leg graph, not a local copy of the street network.
OSRM supplies fastest-driving legs; Dijkstra minimizes their combined time.
"""
import csv
import json
import math
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from logistics.dijkstra import Edge, dijkstra_shortest_path
from logistics.haversine import haversine_distance
from logistics.transport_estimator import estimate_transport

ROOT = Path(__file__).resolve().parents[1]
LOCATION_FILE = ROOT / 'data/processed/prototype_locations_with_buyer.csv'
MATRIX_FILE = ROOT / 'data/processed/prototype_buyer_road_matrix.csv'
NASIK_PIN = 'HUB_NASHIK_KRUSHI_UTPANNA_BAZAR_SAMITI'
VEHICLE = dict(vehicle_type='Small goods vehicle', vehicle_capacity_kg=1000,
               fuel_efficiency_km_per_litre=12, fuel_price_inr_per_litre=95,
               empty_return_factor=1, loading_inr=100, unloading_inr=100,
               tolls_inr=0)


@lru_cache(maxsize=1)
def saved_locations():
    with LOCATION_FILE.open(encoding='utf-8-sig', newline='') as f:
        return {r['location_id']: {**r, 'latitude': float(r['latitude']),
                                  'longitude': float(r['longitude'])} for r in csv.DictReader(f)}


def location_defaults():
    points = saved_locations()
    farm = points['FARMER_TEST_SPIT']
    return {'vehicle': VEHICLE, 'demo_farm': farm,
            'market_pins': [{'state':'Maharashtra', 'district':'Nashik', 'market':'Nasik',
                             **points[NASIK_PIN]}],
            'notice': 'Saved Nashik yard pins are user supplied. Confirm the destination entrance. The sample Mumbai origin is a college, not a real farm.',
            'fuel_notice': 'Vehicle and fuel values are editable planning assumptions, not live rates.'}


def point(payload, prefix):
    try:
        raw = (payload[f'{prefix}_latitude'], payload[f'{prefix}_longitude'])
        if any(isinstance(v, bool) or v in ('', None) for v in raw):
            raise ValueError()
        lat, lon = map(float, raw)
        haversine_distance(lat, lon, lat, lon)
    except (KeyError, TypeError, ValueError):
        raise ValueError(f'Enter valid {prefix} latitude and longitude, or use GPS / the sample route.')
    return lat, lon


def _saved_id(coords):
    # Reuse a measured matrix only at the saved point, never for a nearby farm.
    return next((key for key, p in saved_locations().items()
                 if haversine_distance(*coords, p['latitude'], p['longitude']) < 0.001), None)


def solve(nodes, legs, source, destination, provenance):
    graph = {key: [] for key in nodes}
    valid = {}
    for leg in legs:
        a, b = leg['source'], leg['destination']
        if a not in graph or b not in graph or a == b:
            continue
        distance, minutes = leg['distance_km'], leg['duration_minutes']
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
               not math.isfinite(v) or v <= 0 for v in (distance, minutes)):
            continue
        if (a, b) in valid:
            raise ValueError('The routing matrix contains duplicate directed legs.')
        graph[a].append(Edge(b, distance, minutes))
        valid[a, b] = leg
    result = dijkstra_shortest_path(graph, source, destination, alpha=0, beta=1)
    if not result.reachable:
        raise ValueError('No connected road route was found for these locations. Check the pins or routing service.')
    chosen = [valid[e.source, e.target] for e in result.edges]
    return {**provenance, 'algorithm': 'Haversine + Dijkstra',
            'objective': 'Lowest travel time over available directed road legs',
            'distance_km': sum(e.distance for e in result.edges),
            'duration_minutes': sum(e.transport_cost for e in result.edges),
            'straight_line_km': haversine_distance(*nodes[source], *nodes[destination]),
            'path': [{'id': k, 'latitude': nodes[k][0], 'longitude': nodes[k][1]} for k in result.path],
            'legs': chosen, 'candidate_nodes': len(nodes),
            'warnings': ['Routes are driving estimates, not live traffic or truck-clearance checks. No shelf-life or cold-chain guarantee is applied.']}


def cached_route(source, destination):
    nodes = {k: (p['latitude'], p['longitude']) for k, p in saved_locations().items()}
    legs = []
    with MATRIX_FILE.open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r['status'] != 'ok':
                continue
            try:
                legs.append({'source': r['source_location_id'], 'destination': r['destination_location_id'],
                             'distance_km': float(r['road_distance_km']),
                             'duration_minutes': float(r['estimated_travel_time_minutes']),
                             'provider': r['routing_provider'], 'retrieved_at': r['retrieval_timestamp_utc']})
            except (TypeError, ValueError):
                continue
    route = solve(nodes, legs, source, destination,
                  {'provider':'Saved OSRM Table API matrix', 'mode':'saved_road_matrix',
                   'coordinate_evidence':'Repository user-supplied / prototype coordinates',
                   'road_data_version': None})
    route['retrieved_at'] = min(l['retrieved_at'] for l in route['legs'])
    return route


@lru_cache(maxsize=64)
def _live_route(origin, destination, hour_bucket):
    hubs = sorted((p for p in saved_locations().values() if p['location_type'] == 'hub'),
                  key=lambda p: haversine_distance(*origin, p['latitude'], p['longitude']) +
                                haversine_distance(p['latitude'], p['longitude'], *destination))[:3]
    direct = haversine_distance(*origin, *destination)
    nodes = {'farm': origin, 'destination': destination}
    for p in hubs:
        coords = (p['latitude'], p['longitude'])
        detour = haversine_distance(*origin, *coords) + haversine_distance(*coords, *destination)
        if detour <= max(direct * 1.5, direct + 10) and all(haversine_distance(*coords, *v) > 0.1 for v in nodes.values()):
            nodes[p['location_id']] = coords
    coords = ';'.join(f'{lon:.6f},{lat:.6f}' for lat, lon in nodes.values())
    base = os.environ.get('AGROLINK_OSRM_URL', 'https://router.project-osrm.org').rstrip('/')
    radiuses = ';'.join(['1000'] * len(nodes))
    url = f'{base}/table/v1/driving/{coords}?annotations=distance,duration&radiuses={radiuses}'
    try:
        req = Request(url, headers={'User-Agent':'AgroLink-local-project/1.0'})
        with urlopen(req, timeout=20) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Routing response was too large.')
        data = json.loads(raw)
        if data.get('code') != 'Ok' or data.get('fallback_speed_cells'):
            raise ValueError('No measured road matrix returned.')
        keys = list(nodes)
        if any(len(data[k]) != len(keys) or any(len(row) != len(keys) for row in data[k])
               for k in ('distances', 'durations')):
            raise ValueError('Incomplete road matrix returned.')
        timestamp = datetime.now(timezone.utc).isoformat()
        legs = []
        for i, a in enumerate(keys):
            for j, b in enumerate(keys):
                dist, duration = data['distances'][i][j], data['durations'][i][j]
                if dist is None or duration is None:
                    continue
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (dist, duration)):
                    raise ValueError('Invalid road metrics returned.')
                legs.append({'source': a, 'destination': b, 'distance_km': dist/1000,
                             'duration_minutes': duration/60, 'provider':'OSRM Table API', 'retrieved_at':timestamp})
        return solve(nodes, legs, 'farm', 'destination',
                     {'provider':'OSRM Table API', 'mode':'online_road_matrix', 'retrieved_at':timestamp,
                      'coordinate_evidence':'User-entered/GPS points; road snapping limited to 1 km',
                      'road_data_version':data.get('data_version')})
    except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('Road routing is unavailable for these pins. Check your connection and coordinates, or try the saved sample route. Straight-line distance will not be substituted for road distance.') from exc


def plan_route(payload):
    origin, destination = point(payload, 'farm'), point(payload, 'destination')
    if haversine_distance(*origin, *destination) < 0.01:
        raise ValueError('Farm and destination are the same location. Choose distinct pins for road transport.')
    source, target = _saved_id(origin), _saved_id(destination)
    route = cached_route(source, target) if source and target else _live_route(origin, destination, int(time.time()//3600))
    # Cached values are immutable from callers' perspective.
    route = json.loads(json.dumps(route))
    route['origin'] = {'latitude':origin[0], 'longitude':origin[1], 'name':str(payload.get('farm_name') or 'Your farm')[:120]}
    route['destination'] = {'latitude':destination[0], 'longitude':destination[1], 'name':str(payload.get('market') or 'Selling destination')[:120]}
    if route['mode'] == 'saved_road_matrix':
        route['warnings'].append('Saved route distances were retrieved in October 2026; they are not a fresh road or traffic check. The sample origin is a prototype location.')
    return route


def route_transport(payload, route, quantity_kg):
    settings = {**VEHICLE, **{k: payload[k] for k in VEHICLE if payload.get(k) not in (None, '')}}
    try:
        capacity = float(settings['vehicle_capacity_kg'])
        if isinstance(settings['vehicle_capacity_kg'], bool) or not math.isfinite(capacity) or capacity <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Vehicle capacity must be greater than zero.')
    if not math.isfinite(quantity_kg/capacity) or quantity_kg/capacity > 10000:
        raise ValueError('Shipment requires too many trips. Increase vehicle capacity or split the listing.')
    trips = math.ceil(quantity_kg / capacity)
    one = estimate_transport({**settings, 'origin': route['origin']['name'], 'destination':route['destination']['name'],
                              'route_distance_km':route['distance_km'], 'route_duration_hours':route['duration_minutes']/60,
                              'shipment_weight_kg':min(quantity_kg, capacity),
                              'route_provenance':route['provider'], 'route_data_timestamp':route['retrieved_at'],
                              'fuel_price_provenance':'Editable planning assumption; not a live fuel quote',
                              'cost_provenance':'Editable per-trip planning assumptions'})
    total = round(one['total_trip_cost_inr'] * trips, 2)
    if not math.isfinite(total):
        raise ValueError('Transport cost is too large. Check vehicle and fuel assumptions.')
    one.update(trips=trips, total_trip_cost_inr=total, cost_inr_per_kg=round(total/quantity_kg,4),
               cost_inr_per_quintal=round(total/quantity_kg*100,2),
               components_inr={k:round(v*trips,2) for k,v in one['components_inr'].items()},
               per_trip_cost_inr=round(total/trips,2), allocation_quantity_kg=quantity_kg,
               total_fuel_litres=one['fuel']['litres']*trips,
               route_plan=route, label='Route-based transport planning estimate',
               warnings=one['warnings'] + route['warnings'] +
               ['Fuel, loading, unloading and toll values are assumptions; driver hire, maintenance and other charges are not included. Return travel uses the configured empty-return factor, not a separately routed return journey.'])
    return one
