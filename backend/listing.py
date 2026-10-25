"""Farmer-facing defaults and estimates from the repository's monthly dataset."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd
from pricing.fair_price_engine import calculate_fair_price, create_fair_price_band
from pricing.market_balance import market_balance
from logistics.listing_route import location_defaults, plan_route, route_transport
from logistics.shelf_life import policy as shelf_life_policy, assess_delivery


def today():
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def defaults():
    from backend.server import catalog
    data = catalog()
    preferred = next((m for m in data['markets'] if m['state'] == 'Maharashtra' and m['market'] == 'Nasik' and m['variety'] == 'Other'), None)
    return {**data, 'default_market': preferred or data['markets'][0], 'listing_date': today().isoformat(),
            'dataset': 'Tomato.csv', 'logistics':location_defaults(), 'shelf_life_policy':shelf_life_policy(),
            'description': 'Historical tomato prices and arrival volumes; model selection is automatic.'}


def estimate(payload):
    from backend.server import context, recommend, number
    if any(payload.get(k) not in (None, '') for k in ('regional_supply','regional_demand','dsr','dsr_multiplier','demand_supply_multiplier')):
        raise ValueError('Supply/demand is calculated by the engine from backend evidence; farmer-supplied DSR overrides are not accepted.')
    # Only explicitly supported crop fields reach the legacy recommendation API.
    p = {k:payload[k] for k in ('crop','state','district','market','variety','quantity','unit') if k in payload}
    p.update(source='var', crop=payload.get('crop','Tomato'), quality='Unspecified')
    listing_date = today()
    try:
        harvest = date.fromisoformat(payload.get('harvest_date', listing_date.isoformat()))
        selling = date.fromisoformat(payload.get('selling_date', listing_date.isoformat()))
    except (TypeError, ValueError):
        raise ValueError('Enter valid harvest and expected selling dates.')
    if harvest > listing_date:
        raise ValueError('Harvest date cannot be later than today for this listing.')
    if selling < listing_date or selling < harvest:
        raise ValueError('Expected selling date must be today or later, and on or after harvest.')
    qty = number(p, 'quantity')
    if qty <= 0 or p.get('unit') not in ('kg','quintal'):
        raise ValueError('Quantity must be greater than zero, in kg or quintal.')
    kg = qty * (100 if p['unit'] == 'quintal' else 1)
    if not math.isfinite(kg) or kg > 10_000_000:
        raise ValueError('Shipment quantity must not exceed 10,000,000 kg.')
    ctx = context(p)
    latest_month = pd.Period(ctx['latest_observation'], freq='M')
    horizon = pd.Period(selling, freq='M').ordinal - latest_month.ordinal
    demo = ctx['stale'] or horizon not in (1, 2, 3)
    horizon = 1 if demo else horizon
    target = (latest_month + horizon).strftime('%Y-%m')
    route = plan_route(payload)
    transport = route_transport(payload, route, kg)
    shelf = assess_delivery(payload,route['duration_minutes']/60,transport['trips'],
                            transport['route']['empty_return_factor'])
    # Evidence must have been available at the forecast origin; no future leakage.
    balance = market_balance(p, target, date.fromisoformat(ctx['latest_observation']))
    multiplier = balance['multiplier']
    # Historical simulation dates are internal; preserve the farmer's actual date separately.
    result = recommend({**p, 'mode': 'demo' if demo else 'future', 'horizon': horizon,
                        'acknowledge_stale': demo,
                        'harvest_date': ctx['latest_observation'] if demo else harvest.isoformat(),
                        'selling_date': target + '-01' if demo else selling.isoformat(),
                        'transport_cost':transport['total_trip_cost_inr']})
    base = result['forecast']['base']
    result['transport'] = transport
    deduction = transport['cost_inr_per_quintal']
    fair = calculate_fair_price(base, multiplier, 1, 1, deduction)
    offset = result['breakdown']['band_offset'] * 100
    result['prices'] = {k: v / 100 for k, v in create_fair_price_band(fair, offset, offset).items()}
    result['breakdown']['demand_supply_multiplier'] = multiplier
    result['breakdown']['transport'] = deduction / 100
    result['breakdown']['transport_batch'] = transport['total_trip_cost_inr']
    result['farm_gate'].update(formula='max(0, market_forecast * dsr_multiplier - transport_per_quintal)',
                               farm_gate_inr_per_quintal=fair, farm_gate_inr_per_kg=fair / 100)
    result['listing'] = {'date': listing_date.isoformat(), 'harvest_date': harvest.isoformat(),
                         'selling_date':selling.isoformat(),
                         'demo': demo, 'target_month': target, 'dsr': balance['ratio'],
                         'dsr_source': balance['source'] or balance['reason'],
                         'dsr_sensitivity': balance.get('sensitivity'),
                         'notice': ('Demo estimate from historical data, not today\'s market prediction. Update the dataset to estimate a current listing.' if demo
                                    else 'Monthly estimate for the listing month, not a daily price prediction.')}
    result['context'] = {**result['context'], 'forecast_month': target}
    result['market_balance'] = balance
    result['shelf_life'] = shelf
    gross = round(base / 100 * multiplier * kg, 2)
    result['economics'] = {'market_price_inr_per_kg':base/100, 'adjusted_market_price_inr_per_kg':base/100*multiplier,
                           'gross_revenue_inr':gross, 'transport_cost_inr':transport['total_trip_cost_inr'],
                           'net_revenue_inr':round(gross-transport['total_trip_cost_inr'],2),
                           'net_inr_per_kg':(gross-transport['total_trip_cost_inr'])/kg}
    result['forecast_horizon'] = f'{horizon} calendar month(s); target {target}'
    result['warnings'] = [w for w in result['warnings'] if 'demand/supply adjustments are neutral' not in w
                          and 'Route, fuel, toll and handling components were not supplied' not in w]
    result['warnings'].append('Quality and location multipliers are neutral; no calibrated premiums are available.')
    result['warnings'] += transport['warnings'] + [balance['reason']]
    if shelf['status'] != 'eligible':
        result['warnings'].append(shelf['reason'])
    if result['economics']['net_revenue_inr'] < 0:
        result['warnings'].append('Transport exceeds estimated sale proceeds. The fair-price policy floors its price at zero; the net revenue below includes the loss.')
    return result

