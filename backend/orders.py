"""Mutually agreed sales with transactional stock and shared quote budgets.

Proposing explicitly agrees as farmer; only the named buyer can accept.
Before collection, deadline expiry releases reservations. Once collected, stock
and quote capacity stay consumed, including any rejected delivered weight.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from backend.accounts import AppError, timestamp
from backend.database import connect
from backend import trading
from pricing.buyer_return import decimal_value

HELD = ('accepted', 'ready', 'collected', 'delivered', 'completed')


def now():
    return datetime.now(timezone.utc)


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def key(payload):
    return trading.text(payload.get('request_key'), 'unique request key', 100)


def event(db, order_id, status, actor=None, details=None):
    db.execute('INSERT INTO app_order_events(order_id,actor_id,status,occurred_at,details) VALUES (?,?,?,?,?)',
               (order_id, actor, status, timestamp(), dump(details or {})))


def expire(db):
    """Lazy durable sweep, invoked on order reads and order operations.

    Consumption also checks deadlines, so even a rolled-back sweep cannot hold
    expired stock. No timer or browser session is required to release capacity.
    """
    for row in db.execute("SELECT * FROM app_orders WHERE status IN ('proposed','accepted','ready')").fetchall():
        if datetime.fromisoformat(row['expires_at']) <= now():
            changed = db.execute("UPDATE app_orders SET status='expired',version=version+1,updated_at=? WHERE id=? AND version=?",
                                 (timestamp(), row['id'], row['version']))
            if changed.rowcount:
                event(db, row['id'], 'expired', details={'reason': 'Agreement deadline elapsed; uncollected reservations released.'})


def consumed(db, column, record_id):
    if column not in ('listing_id', 'offer_id'):
        raise ValueError('Invalid inventory reference.')
    rows = db.execute(f'SELECT quantity_kg,status,expires_at FROM app_orders WHERE {column}=?', (record_id,))
    return sum((Decimal(r['quantity_kg']) for r in rows if r['status'] in HELD and
                (r['status'] not in ('accepted', 'ready') or datetime.fromisoformat(r['expires_at']) > now())), Decimal(0))


def available(db, listing_row):
    return max(Decimal(0), Decimal(str(json.loads(listing_row['payload'])['quantity_kg'])) - consumed(db, 'listing_id', listing_row['id']))


def capacity(db, offer_row):
    total = Decimal(str(json.loads(offer_row['payload'])['offer']['max_quantity_kg']))
    return max(Decimal(0), total - consumed(db, 'offer_id', offer_row['id']))


def participant(db, order_id, user):
    row = db.execute('SELECT * FROM app_orders WHERE id=? AND (farmer_id=? OR buyer_id=?)',
                     (order_id, user['id'], user['id'])).fetchone()
    if row is None:
        raise AppError(404, 'Order not found.')
    return row


def serialize(db, row):
    events = [dict(r) for r in db.execute('SELECT sequence,actor_id,status,occurred_at,details FROM app_order_events WHERE order_id=? ORDER BY sequence', (row['id'],))]
    for e in events:
        e['details'] = json.loads(e['details'])
    return {k: row[k] for k in ('id', 'farmer_id', 'buyer_id', 'listing_id', 'offer_id', 'status', 'version',
                               'quantity_kg', 'expires_at', 'created_at', 'updated_at')} | {
        'terms': json.loads(row['snapshot']), 'actuals': json.loads(row['actuals']) if row['actuals'] else None,
        'events': events}


def list_orders(user, order_id=None):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        if order_id:
            return serialize(db, participant(db, order_id, user))
        return {'orders': [serialize(db, r) for r in db.execute(
            'SELECT * FROM app_orders WHERE farmer_id=? OR buyer_id=? ORDER BY created_at DESC,id', (user['id'], user['id']))]}


def rows(db, user, listing_id, offer_id):
    listing = trading.owned(db, 'app_listings', listing_id, user)
    offer = db.execute('SELECT o.*,u.name FROM app_offers o JOIN app_users u ON u.id=o.owner_id WHERE o.id=?', (offer_id,)).fetchone()
    if listing['status'] != 'published':
        raise AppError(409, 'Publish the harvest before proposing an order.')
    if offer is None or offer['status'] != 'active' or offer['listing_id'] not in (None, listing_id):
        raise AppError(409, 'This offer is no longer available for this harvest.')
    h, o = json.loads(listing['payload']), json.loads(offer['payload'])
    if o['crop'] != h['crop'] or o['accepted_grade'] not in ('Any', h['grade']) or o['accepted_variety'] not in ('Any', h['variety']):
        raise AppError(409, 'The offer no longer matches the harvest.')
    if datetime.fromisoformat(o['offer']['valid_until']) <= now():
        raise AppError(409, 'This quote has expired.')
    return listing, offer


def checked_terms(listing, offer, quantity, acknowledgment):
    """Evaluate only saved terms, and freeze attributable route/cost assumptions."""
    from backend.buyers import evaluate_buyer
    from logistics.shelf_life import india_now
    h, o = json.loads(listing['payload']), json.loads(offer['payload'])
    minimum = decimal_value(o['offer'].get('min_quantity_kg', 0), 'Minimum quantity')
    maximum = decimal_value(o['offer']['max_quantity_kg'], 'Maximum quantity', True)
    if quantity < minimum or quantity > maximum or quantity > Decimal(str(h['quantity_kg'])):
        raise AppError(409, 'Quantity falls outside the saved harvest or quote limits.')
    if quantity < Decimal(str(h['quantity_kg'])) and not (h.get('allow_partial_sales') is True and o['offer'].get('partial_sales_supported') is True):
        raise AppError(409, 'A partial sale requires both parties to allow it.')
    buyer = {'id': offer['id'], 'name': offer['name'], 'crop': o['crop'], 'demo': False,
             'offer': o['offer'], 'delivery_deadline': o['delivery_deadline'],
             'coordinates': {'latitude': o['destination_latitude'], 'longitude': o['destination_longitude']}}
    evaluated = evaluate_buyer(h, buyer, float(quantity), india_now())
    if not evaluated['selection_allowed'] or evaluated['financial']['status'] != 'available':
        raise AppError(409, 'Order unavailable: ' + (evaluated['shelf_life']['reason'] if not evaluated['shelf_life']['can_select'] else evaluated['financial']['reason']))
    if evaluated['shelf_life']['requires_acknowledgment'] and acknowledgment is not True:
        raise AppError(422, 'Acknowledge the limited delivery window before agreeing.')
    return {'harvest': h, 'quote': o, 'farmer_id': listing['owner_id'], 'buyer_id': offer['owner_id'],
            'buyer_name': offer['name'], 'listing_version': listing['version'], 'offer_version': offer['version'],
            'quantity_kg': str(quantity), 'evaluation': evaluated,
            'capacity_policy': 'Shared lifetime purchase budget per offer; cancelled and expired uncollected orders release capacity.',
            'transport_source': 'Farmer planning assumptions; not a carrier quotation.'}


def recheck_delivery(terms, acknowledgment):
    """Recheck time eligibility at collection using the agreed dependable route."""
    from logistics.shelf_life import assess_delivery, india_now
    transport = terms['evaluation']['transport']
    current = india_now()
    harvest = dict(terms['harvest'])
    # These fields describe the earliest agreed pickup. Once that wait has
    # elapsed, assess departure now rather than rejecting an immutable snapshot
    # merely because midnight or its scheduled pickup has passed.
    if harvest['selling_date'] < current.date().isoformat():
        harvest['selling_date'] = current.date().isoformat()
    if harvest.get('pickup_at'):
        pickup = datetime.fromisoformat(harvest['pickup_at'])
        if pickup.tzinfo is None:
            pickup = pickup.replace(tzinfo=current.tzinfo)
        if pickup < current:
            harvest['pickup_at'] = ''
    assessment = assess_delivery(harvest, transport['route_plan']['duration_minutes']/60,
                                 transport['trips'], transport['route']['empty_return_factor'], current)
    if not assessment['can_select'] or datetime.fromisoformat(assessment['estimated_last_delivery_at']) > datetime.fromisoformat(terms['quote']['delivery_deadline']):
        raise AppError(409, 'Collection is blocked by the current delivery window or agreed deadline. Cancel the uncollected order to release stock.')
    if assessment['requires_acknowledgment'] and acknowledgment is not True:
        raise AppError(422, 'Acknowledge the limited delivery window before collecting.')
    return assessment


def propose(user, payload):
    if user['role'] != 'farmer':
        raise AppError(403, 'Only farmers can propose orders for their own harvests.')
    if payload.get('agree_terms') is not True:
        raise AppError(422, 'Explicit agreement to the proposed terms is required.')
    request_key = key(payload)
    quantity = decimal_value(payload.get('quantity_kg'), 'Proposed quantity', True)
    if quantity > 10_000_000 or quantity.normalize().as_tuple().exponent < -6:
        raise AppError(422, 'Quantity must be at most 10,000,000 kg with at most six decimal places.')
    listing_id = trading.text(payload.get('listing_id'), 'harvest reference', 100)
    offer_id = trading.text(payload.get('offer_id'), 'offer reference', 100)
    intent = fingerprint({'listing_id': listing_id, 'offer_id': offer_id, 'quantity': str(quantity.normalize()),
                          'listing_version': payload.get('listing_version'), 'offer_version': payload.get('offer_version')})
    with connect() as db:
        previous = db.execute('SELECT * FROM app_orders WHERE farmer_id=? AND request_key=?', (user['id'], request_key)).fetchone()
        if previous:
            if previous['request_fingerprint'] != intent:
                raise AppError(409, 'This request key was already used for different terms.')
            return list_orders(user, previous['id'])
        listing, offer = rows(db, user, listing_id, offer_id)
        trading.check_version(payload.get('listing_version'), listing, 'Harvest changed; refresh before proposing.')
        trading.check_version(payload.get('offer_version'), offer, 'Offer changed; refresh before proposing.')
    # Network routing is deliberately outside the SQLite write lock.
    terms = checked_terms(listing, offer, quantity, payload.get('acknowledge_warning'))
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        previous = db.execute('SELECT * FROM app_orders WHERE farmer_id=? AND request_key=?', (user['id'], request_key)).fetchone()
        if previous:
            if previous['request_fingerprint'] != intent:
                raise AppError(409, 'Request key conflict.')
            return serialize(db, previous)
        current_listing, current_offer = rows(db, user, listing_id, offer_id)
        if current_listing['version'] != listing['version'] or current_offer['version'] != offer['version']:
            raise AppError(409, 'Harvest or offer changed during evaluation. Refresh and retry.')
        if quantity > available(db, current_listing) or quantity > capacity(db, current_offer):
            raise AppError(409, 'Insufficient remaining harvest quantity or shared quote capacity.')
        order_id, created = uuid.uuid4().hex, timestamp()
        db.execute('''INSERT INTO app_orders(id,farmer_id,buyer_id,listing_id,offer_id,status,quantity_kg,snapshot,
                      expires_at,created_at,updated_at,request_key,request_fingerprint) VALUES (?,?,?,?,?,'proposed',?,?,?,?,?,?,?)''',
                   (order_id, user['id'], offer['owner_id'], listing_id, offer_id, str(quantity), dump(terms),
                    terms['quote']['offer']['valid_until'], created, created, request_key, intent))
        event(db, order_id, 'proposed', user['id'], {'farmer_agreed': True, 'warning_acknowledged': payload.get('acknowledge_warning') is True})
        return serialize(db, participant(db, order_id, user))


def transition(user, order_id, payload):
    action = payload.get('action')
    request_key = key(payload)
    intent = fingerprint({**{k: v for k, v in payload.items() if k != 'request_key'}, 'order_id': order_id})
    # Read/revalidate route before acquiring the inventory write lock.
    fresh = None
    with connect() as db:
        row = participant(db, order_id, user)
        previous = db.execute('SELECT * FROM app_order_requests WHERE actor_id=? AND request_key=?', (user['id'], request_key)).fetchone()
        if previous:
            if previous['fingerprint'] != intent:
                raise AppError(409, 'This request key was already used for another action.')
            return list_orders(user, order_id)
        if action == 'accept':
            if user['id'] != row['buyer_id']:
                raise AppError(403, 'Only the named buyer can accept this proposal.')
            if payload.get('agree_terms') is not True:
                raise AppError(422, 'Explicit agreement to the saved terms is required.')
            if row['status'] != 'proposed' or datetime.fromisoformat(row['expires_at']) <= now():
                raise AppError(409, 'Proposal is no longer open.')
            terms = json.loads(row['snapshot'])
            listing, offer = rows(db, {'id': row['farmer_id']}, row['listing_id'], row['offer_id'])
            if listing['version'] != terms['listing_version'] or offer['version'] != terms['offer_version']:
                raise AppError(409, 'Harvest or quote changed. Request a new proposal.')
    if action == 'accept':
        fresh = checked_terms(listing, offer, Decimal(row['quantity_kg']), payload.get('acknowledge_warning'))
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db)
        row = participant(db, order_id, user)
        previous = db.execute('SELECT * FROM app_order_requests WHERE actor_id=? AND request_key=?', (user['id'], request_key)).fetchone()
        if previous:
            if previous['fingerprint'] != intent:
                raise AppError(409, 'Request key conflict.')
            return serialize(db, row)
        trading.check_version(payload.get('version'), row, 'Order changed. Refresh before continuing.')
        status, expiry, actuals = row['status'], row['expires_at'], row['actuals']
        details = {}
        is_farmer = user['id'] == row['farmer_id']
        if action == 'accept' and status == 'proposed':
            l, o = rows(db, {'id': row['farmer_id']}, row['listing_id'], row['offer_id'])
            if l['version'] != fresh['listing_version'] or o['version'] != fresh['offer_version']:
                raise AppError(409, 'Harvest or quote changed during evaluation.')
            qty = Decimal(row['quantity_kg'])
            if qty > available(db, l) or qty > capacity(db, o):
                raise AppError(409, 'Another agreement consumed the remaining harvest or shared quote capacity.')
            target, expiry = 'accepted', fresh['quote']['delivery_deadline']
            details = {'buyer_agreed': True, 'warning_acknowledged': payload.get('acknowledge_warning') is True,
                       'delivery_recheck': fresh['evaluation']['shelf_life']}
        elif action == 'reject' and status == 'proposed' and not is_farmer:
            target = 'rejected'
        elif action == 'cancel' and status in ('proposed', 'accepted', 'ready'):
            target = 'cancelled'
        elif action == 'ready' and status == 'accepted' and is_farmer:
            target = 'ready'
        elif action == 'collect' and status == 'ready' and not is_farmer:
            target = 'collected'
            details = {'delivery_recheck': recheck_delivery(json.loads(row['snapshot']), payload.get('acknowledge_warning'))}
        elif action == 'deliver' and status == 'collected' and not is_farmer:
            weight = decimal_value(payload.get('accepted_weight_kg'), 'Actual accepted weight')
            if weight > Decimal(row['quantity_kg']):
                raise AppError(422, 'Actual accepted weight cannot exceed the reserved quantity.')
            grade = payload.get('actual_grade')
            if grade not in ('Unspecified', 'A', 'B', 'C'):
                raise AppError(422, 'Choose a valid actual grade.')
            notes = trading.text(payload.get('notes', ''), 'delivery notes / rejection reasons', 2000, False)
            if weight < Decimal(row['quantity_kg']) and not notes:
                raise AppError(422, 'Explain rejected or short-delivered weight in delivery notes.')
            target = 'delivered'
            actuals = dump({'accepted_weight_kg': str(weight), 'grade': grade, 'notes': notes,
                            'recorded_by': user['id'], 'recorded_at': timestamp()})
            details = json.loads(actuals)
        elif action == 'complete' and status == 'delivered' and is_farmer:
            if payload.get('agree_actuals') is not True:
                raise AppError(422, 'Acknowledge the recorded delivery outcomes before completing.')
            target, details = 'completed', {'farmer_acknowledged_actuals': True}
        else:
            raise AppError(409, 'This action is unavailable for your role or the current order state.')
        db.execute('UPDATE app_orders SET status=?,expires_at=?,actuals=?,version=version+1,updated_at=? WHERE id=?',
                   (target, expiry, actuals, timestamp(), order_id))
        event(db, order_id, target, user['id'], details)
        db.execute('INSERT INTO app_order_requests VALUES (?,?,?,?)', (user['id'], request_key, order_id, intent))
        return serialize(db, participant(db, order_id, user))
