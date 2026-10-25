"""Farmer-side buyer discovery and authoritative delivery eligibility.

This phase prepares drafts only. Directory entries are explicitly demo buyers;
there are no buyer accounts, accepted orders or reservations.
"""
import json
import math
import os
from pathlib import Path
from datetime import datetime

from logistics.listing_route import plan_route, route_transport, saved_locations, point
from logistics.shelf_life import assess_delivery, india_now
from pricing.buyer_return import offer_plan, financial_outcome, rank_buyers

DIRECTORY = Path(__file__).resolve().parents[1]/'data/buyers.demo.json'


def directory():
    path=Path(os.environ.get('AGROLINK_BUYERS_FILE',DIRECTORY))
    return json.loads(path.read_text(encoding='utf-8'))


def validated(payload):
    from backend.server import number
    if payload.get('crop') != 'Tomato':
        raise ValueError('Only Tomato has a configured delivery-life policy.')
    if not isinstance(payload.get('allow_partial_sales',False),bool):
        raise ValueError('Partial-sale permission must be true or false.')
    qty = number(payload,'quantity')
    if qty <= 0 or payload.get('unit') not in ('kg','quintal'):
        raise ValueError('Enter a positive quantity in kg or quintal.')
    kg = qty*(100 if payload['unit']=='quintal' else 1)
    if not math.isfinite(kg) or kg > 10_000_000:
        raise ValueError('Shipment quantity must not exceed 10,000,000 kg.')
    point(payload,'farm')
    # Validate dates and policy before contacting routing services.
    assess_delivery(payload,0)
    return kg


def evaluate_buyer(payload, buyer, kg, now):
    plan=offer_plan(buyer,kg,payload.get('allow_partial_sales',False),now)
    pin = buyer.get('coordinates') or saved_locations().get(buyer.get('location_id'))
    if not pin:
        raise ValueError('Buyer destination has no configured road-routing pin.')
    # Destination and identity are server-owned. Caller overrides are ignored.
    route = plan_route({**payload,'market':buyer['name'],
                        'destination_latitude':pin['latitude'],'destination_longitude':pin['longitude']})
    transport = route_transport(payload,route,plan['transport_quantity_kg'])
    shelf = assess_delivery(payload,route['duration_minutes']/60,transport['trips'],
                            transport['route']['empty_return_factor'],now)
    if buyer.get('delivery_deadline') and datetime.fromisoformat(shelf['estimated_last_delivery_at'])>datetime.fromisoformat(buyer['delivery_deadline']):
        shelf.update(status='blocked',can_select=False,requires_acknowledgment=False,
                     reason='Estimated last delivery is later than this buyer’s delivery deadline.')
    public={k:buyer[k] for k in ('id','name','location_id','crop','description') if k in buyer}
    return {**public,'demo':buyer.get('demo',True),'coordinate_evidence':buyer.get('coordinate_evidence',pin.get('verification_status','Buyer-entered pin')),
            'shelf_life':shelf,'transport':transport,'financial':financial_outcome(plan,transport,shelf),
            'selection_allowed':shelf['can_select'] and plan['can_prepare_draft']}


def suggestions(payload,records=None):
    kg = validated(payload)
    now = india_now()
    buyers = []
    for buyer in (directory() if records is None else records):
        if buyer['crop'] != payload['crop']:
            continue
        try:
            buyers.append(evaluate_buyer(payload,buyer,kg,now))
        except ValueError as exc:
            shelf={'status':'unavailable','can_select':False,'requires_acknowledgment':False,'reason':str(exc)}
            public={k:buyer[k] for k in ('id','name','location_id','crop','description') if k in buyer}
            plan=offer_plan(buyer,kg,payload.get('allow_partial_sales',False),now)
            buyers.append({**public,'demo':buyer.get('demo',True),'shelf_life':shelf,'transport':None,
                           'financial':financial_outcome(plan,None,shelf),'selection_allowed':False})
    groups=rank_buyers(buyers)
    return {'demo':any(b['demo'] for b in buyers),'evaluated_at':now.isoformat(),'refresh_after_seconds':60,
            'listing':{'crop':payload['crop'],'quantity_kg':kg,'harvest_date':payload['harvest_date']},
            'buyers':buyers,'comparison_groups':groups,
            'ranking_policy':'Compare estimated net returns only within the same sale quantity. Full-harvest and partial sales are separate. Missing offers are unranked; DSR is not applied.',
            'notice':'Directory entries retain their demo status. Demo terms, if configured, are illustrative rather than real offers or demand. Missing prices are not invented. Selections are drafts only.'}


def select_buyer(payload,records=None):
    if not any(b['id']==payload.get('buyer_id') for b in (directory() if records is None else records)):
        raise ValueError('Select a buyer from the current directory.')
    # Reuse the entire discovery pipeline to recheck terms, route, eligibility,
    # actual sale quantity, finances and comparison position in one snapshot.
    comparison=suggestions(payload,records=records)
    checked=next((b for b in comparison['buyers'] if b['id']==payload['buyer_id']),None)
    if checked is None:
        raise ValueError('Buyer is no longer available for this crop. Refresh suggestions.')
    shelf = checked['shelf_life']
    if not shelf['can_select']:
        raise ValueError(f"Selling unavailable for this buyer: {shelf['reason']}")
    if not checked['financial']['can_prepare_draft']:
        raise ValueError(f"Selling unavailable for this buyer: {checked['financial']['reason']}")
    if shelf['requires_acknowledgment'] and payload.get('acknowledge_warning') is not True:
        raise ValueError('Acknowledge the limited delivery window before preparing this sale draft.')
    return {'status':'draft_only','demo':checked['demo'],'buyer':checked,
            'financial_mode':'priced_scenario' if checked['financial']['status']=='available' else 'unpriced_enquiry',
            'notice':'Eligibility, buyer terms, transport costs and financial totals were rechecked by the server. No order was placed or sent. An unpriced draft is an enquiry, not an agreed sale.'}
