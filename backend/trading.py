"""Owner-scoped harvest listings and buyer quotes with shared inventory budgets."""
import base64
import binascii
import json
import math
import uuid
from datetime import datetime, timezone

from backend.accounts import AppError, timestamp
from backend.database import connect
from logistics.shelf_life import assess_delivery, india_now
from logistics.listing_route import VEHICLE, point
from pricing.buyer_return import offer_plan, decimal_value

LISTING_FIELDS=('crop','variety','quantity','unit','harvest_date','harvest_time','produce_condition','selling_date','pickup_at',
                'farm_name','farm_latitude','farm_longitude','allow_partial_sales','grade')+tuple(VEHICLE)


def text(value,label,limit=200,required=True):
    if not isinstance(value,str) or len(value.strip())>limit or (required and not value.strip()):
        raise AppError(422,f'Enter a valid {label} (maximum {limit} characters).')
    return value.strip()


def listing_payload(payload):
    from backend.buyers import validated
    clean={k:payload[k] for k in LISTING_FIELDS if k in payload}
    clean.update(title=text(payload.get('title'),'listing title',120),
                 notes=text(payload.get('notes',''),'harvest notes',2000,False),
                 grade=payload.get('grade','Unspecified'),variety=payload.get('variety','Unspecified'))
    if clean['grade'] not in ('Unspecified','A','B','C'):
        raise AppError(422,'Choose Unspecified, A, B or C for the lot grade.')
    clean['variety']=text(clean['variety'],'variety',80)
    clean['quantity_kg']=validated(clean)
    return clean


def owned(db,table,record_id,user):
    row=db.execute(f'SELECT * FROM {table} WHERE id=? AND owner_id=?',(record_id,user['id'])).fetchone()
    if row is None:
        raise AppError(404,'Record not found.')
    return row


def check_version(version,row,message):
    if isinstance(version,bool) or not isinstance(version,int):
        raise AppError(422,'A numeric record version is required.')
    if version!=row['version']: raise AppError(409,message)


def photos(db,listing_id):
    return [{'id':r['id'],'content_type':r['content_type']} for r in
            db.execute('SELECT id,content_type FROM app_photos WHERE listing_id=?',(listing_id,))]


def serialize_listing(db,row):
    from backend.orders import available, consumed
    data=json.loads(row['payload'])
    try:
        shelf=assess_delivery(data,0)
    except ValueError as exc:
        shelf={'status':'blocked','can_select':False,'reason':str(exc)}
    return {'id':row['id'],'status':row['status'],'version':row['version'], 'harvest':data,
            'created_at':row['created_at'],'updated_at':row['updated_at'],
            'photos':photos(db,row['id']),'delivery_check':shelf,
            'available_quantity_kg':str(available(db,row)),
            'committed_quantity_kg':str(consumed(db,'listing_id',row['id']))}


def my_listings(user):
    with connect() as db:
        return {'listings':[serialize_listing(db,r) for r in db.execute(
            'SELECT * FROM app_listings WHERE owner_id=? ORDER BY updated_at DESC',(user['id'],))]}


def available_listings():
    with connect() as db:
        rows=db.execute("SELECT * FROM app_listings WHERE status='published' ORDER BY updated_at DESC LIMIT 200").fetchall()
        result=[serialize_listing(db,r) for r in rows]
    return {'listings':[r for r in result if r['delivery_check']['can_select'] and float(r['available_quantity_kg'])>0]}


def get_listing(user,record_id):
    with connect() as db:
        if user['role']=='farmer':
            row=owned(db,'app_listings',record_id,user)
        else:
            row=db.execute("SELECT * FROM app_listings WHERE id=? AND status='published'",(record_id,)).fetchone()
            if row is None: raise AppError(404,'Record not found.')
        return serialize_listing(db,row)


def save_listing(user,payload,record_id=None):
    if user['role']!='farmer': raise AppError(403,'Only farmers can manage harvest listings.')
    clean=listing_payload(payload)
    status=payload.get('status','draft')
    if status not in ('draft','published','archived'):
        raise AppError(422,'Choose draft, published or archived.')
    if status=='published' and not assess_delivery(clean,0)['can_select']:
        raise AppError(422,'This lot cannot be published within its current delivery-life window. Save it as a draft or correct its details.')
    now=timestamp()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if record_id:
            row=owned(db,'app_listings',record_id,user)
            check_version(payload.get('version'),row,'This listing changed elsewhere. Reload before saving.')
            from backend.orders import consumed
            if consumed(db,'listing_id',record_id)>0 and clean!=json.loads(row['payload']):
                raise AppError(409,'Harvest terms are locked while reserved or consumed stock exists. Use a separate listing for a different lot.')
            cursor=db.execute('''UPDATE app_listings SET payload=?,status=?,version=version+1,updated_at=?
                                WHERE id=? AND owner_id=? AND version=?''',
                              (json.dumps(clean,allow_nan=False),status,now,record_id,user['id'],row['version']))
            if cursor.rowcount!=1: raise AppError(409,'Listing changed. Reload before saving.')
        else:
            record_id=uuid.uuid4().hex
            db.execute('INSERT INTO app_listings VALUES (?,?,?,?,?,?,?)',
                       (record_id,user['id'],status,1,json.dumps(clean,allow_nan=False),now,now))
        return serialize_listing(db,db.execute('SELECT * FROM app_listings WHERE id=?',(record_id,)).fetchone())


def archive_listing(user,record_id,version):
    if user['role']!='farmer': raise AppError(403,'Only farmers can archive harvests.')
    with connect() as db:
        row=owned(db,'app_listings',record_id,user)
        check_version(version,row,'Listing changed. Reload before archiving.')
        cursor=db.execute("UPDATE app_listings SET status='archived',version=version+1,updated_at=? WHERE id=? AND owner_id=? AND version=?",
                          (timestamp(),record_id,user['id'],version))
        if cursor.rowcount!=1: raise AppError(409,'Listing changed. Reload before archiving.')
    return {'status':'archived'}


def add_photo(user,record_id,payload):
    if user['role']!='farmer': raise AppError(403,'Only farmers can upload harvest photos.')
    mime=payload.get('content_type')
    if mime not in ('image/jpeg','image/png','image/webp'):
        raise AppError(422,'Use a JPEG, PNG or WebP photo.')
    raw=payload.get('data_base64')
    if not isinstance(raw,str) or len(raw)>2_800_000:
        raise AppError(422,'Each photo must be at most 2 MB.')
    try: data=base64.b64decode(raw,validate=True)
    except (ValueError,binascii.Error): raise AppError(422,'Invalid photo data.')
    signatures={'image/jpeg':data.startswith(b'\xff\xd8\xff'),
                'image/png':data.startswith(b'\x89PNG\r\n\x1a\n'),
                'image/webp':data.startswith(b'RIFF') and data[8:12]==b'WEBP'}
    if not data or len(data)>2*1024*1024 or not signatures[mime]:
        raise AppError(422,'Photo content does not match its type or exceeds 2 MB.')
    with connect() as db:
        owned(db,'app_listings',record_id,user)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT count(*) FROM app_photos WHERE listing_id=?',(record_id,)).fetchone()[0]>=3:
            raise AppError(422,'Each listing supports at most three photos.')
        photo_id=uuid.uuid4().hex
        db.execute('INSERT INTO app_photos VALUES (?,?,?,?)',(photo_id,record_id,mime,data))
    return {'id':photo_id,'content_type':mime}


def get_photo(user,photo_id):
    with connect() as db:
        row=db.execute('''SELECT p.*,l.owner_id,l.status FROM app_photos p JOIN app_listings l ON l.id=p.listing_id
                          WHERE p.id=?''',(photo_id,)).fetchone()
    if row is None or not (row['owner_id']==user['id'] or (user['role']=='buyer' and row['status']=='published')):
        raise AppError(404,'Photo not found.')
    return row['content_type'],row['content']


def delete_photo(user,photo_id):
    if user['role']!='farmer': raise AppError(403,'Only farmers can remove photos.')
    with connect() as db:
        row=db.execute('''SELECT p.id FROM app_photos p JOIN app_listings l ON l.id=p.listing_id
                          WHERE p.id=? AND l.owner_id=?''',(photo_id,user['id'])).fetchone()
        if row is None: raise AppError(404,'Photo not found.')
        db.execute('DELETE FROM app_photos WHERE id=?',(photo_id,))
    return {'deleted':True}


def parsed_time(value,label):
    try:
        result=datetime.fromisoformat(value)
        if result.tzinfo is None or result<=datetime.now(timezone.utc): raise ValueError()
        return result.isoformat()
    except (ValueError,TypeError): raise AppError(422,f'{label} must be a future date/time with a timezone.')


def quote_payload(payload,user):
    name=text(payload.get('title'),'offer title',120)
    crop=payload.get('crop','Tomato')
    if crop!='Tomato': raise AppError(422,'Live delivery matching currently supports Tomato.')
    grade=payload.get('accepted_grade','Any')
    if grade not in ('Any','A','B','C','Unspecified'): raise AppError(422,'Choose a valid accepted grade.')
    variety=text(payload.get('accepted_variety','Any'),'accepted variety',80)
    destination=text(payload.get('destination_name'),'destination name',150)
    coords=point(payload,'destination')
    expires=parsed_time(payload.get('valid_until'),'Quote expiry')
    deadline=parsed_time(payload.get('delivery_deadline'),'Delivery deadline')
    if datetime.fromisoformat(expires)>datetime.fromisoformat(deadline):
        raise AppError(422,'Quote expiry cannot be later than its delivery deadline.')
    terms={'kind':'buyer_offer','price_inr_per_kg':payload.get('price_inr_per_kg'),
           'max_quantity_kg':payload.get('max_quantity_kg'),'min_quantity_kg':payload.get('min_quantity_kg',0),
           'partial_sales_supported':payload.get('partial_sales_supported',False),
           'selling_charges':payload.get('selling_charges',[]),'source':f"Account-submitted quote from {user['name']}",
           'valid_until':expires}
    capacity=float(decimal_value(terms['max_quantity_kg'],'Buyer purchase capacity',True))
    check=offer_plan({'demo':False,'offer':terms},capacity,False,india_now())
    if check['status']!='available': raise AppError(422,check['reason'])
    return {'title':name,'crop':crop,'accepted_grade':grade,'accepted_variety':variety,
            'destination_name':destination,'destination_latitude':coords[0],'destination_longitude':coords[1],
            'delivery_deadline':deadline,'offer':terms}


def serialize_offer(row,db=None):
    data=json.loads(row['payload'])
    expired=datetime.fromisoformat(data['offer']['valid_until'])<=datetime.now(timezone.utc)
    from backend.orders import capacity
    return {'id':row['id'],'listing_id':row['listing_id'],'status':row['status'],'expired':expired,
            'capacity_policy':'shared_offer_budget',
            'remaining_capacity_kg':str(capacity(db,row)) if db is not None else None,
            'version':row['version'],'terms':data,'created_at':row['created_at'],'updated_at':row['updated_at']}


def my_offers(user):
    with connect() as db:
        return {'offers':[serialize_offer(r,db) for r in db.execute('SELECT * FROM app_offers WHERE owner_id=? ORDER BY updated_at DESC',(user['id'],))]}


def save_offer(user,payload,record_id=None):
    if user['role']!='buyer': raise AppError(403,'Only buyers can manage offers.')
    clean=quote_payload(payload,user)
    status=payload.get('status','active')
    if status not in ('active','withdrawn'): raise AppError(422,'Choose active or withdrawn.')
    listing_id=payload.get('listing_id') or None
    if listing_id is not None and not isinstance(listing_id,str): raise AppError(422,'Invalid harvest reference.')
    now=timestamp()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if listing_id:
            row=db.execute("SELECT * FROM app_listings WHERE id=? AND status='published'",(listing_id,)).fetchone()
            if row is None: raise AppError(404,'Published harvest not found.')
            h=json.loads(row['payload'])
            if not assess_delivery(h,0)['can_select']: raise AppError(409,'This harvest is no longer available within its planning window.')
            if clean['accepted_grade'] not in ('Any',h['grade']) or clean['accepted_variety'] not in ('Any',h['variety']):
                raise AppError(422,'Offer grade or variety does not match the selected harvest.')
        if record_id:
            row=owned(db,'app_offers',record_id,user)
            check_version(payload.get('version'),row,'Offer changed elsewhere. Reload before saving.')
            from backend.orders import consumed
            if consumed(db,'offer_id',record_id)>0 and (clean!=json.loads(row['payload']) or listing_id!=row['listing_id']):
                raise AppError(409,'Quote terms are locked after reservation or consumption. Withdraw it or post a new offer with a separate purchase budget.')
            cursor=db.execute('UPDATE app_offers SET payload=?,listing_id=?,status=?,version=version+1,updated_at=? WHERE id=? AND owner_id=? AND version=?',
                              (json.dumps(clean,allow_nan=False),listing_id,status,now,record_id,user['id'],row['version']))
            if cursor.rowcount!=1: raise AppError(409,'Offer changed. Reload before saving.')
        else:
            record_id=uuid.uuid4().hex
            db.execute('INSERT INTO app_offers VALUES (?,?,?,?,?,?,?,?)',
                       (record_id,user['id'],listing_id,status,1,json.dumps(clean,allow_nan=False),now,now))
        return serialize_offer(db.execute('SELECT * FROM app_offers WHERE id=?',(record_id,)).fetchone(),db)


def withdraw_offer(user,record_id,version):
    if user['role']!='buyer': raise AppError(403,'Only buyers can withdraw offers.')
    with connect() as db:
        row=owned(db,'app_offers',record_id,user)
        check_version(version,row,'Offer changed. Reload before withdrawing.')
        cursor=db.execute("UPDATE app_offers SET status='withdrawn',version=version+1,updated_at=? WHERE id=? AND owner_id=? AND version=?",
                          (timestamp(),record_id,user['id'],version))
        if cursor.rowcount!=1: raise AppError(409,'Offer changed. Reload before withdrawing.')
    return {'status':'withdrawn'}


def live_matches(user,listing_id,options,selection=False):
    if user['role']!='farmer': raise AppError(403,'Only farmers can compare buyers for their harvests.')
    with connect() as db:
        from backend.orders import available, capacity
        row=owned(db,'app_listings',listing_id,user)
        if row['status']=='archived': raise AppError(409,'Restore this harvest as a draft before comparing offers.')
        h=json.loads(row['payload'])
        saved_harvest=dict(h)
        listing_version=row['version']
        remaining=available(db,row)
        if remaining<=0: raise AppError(409,'This harvest has no remaining available quantity.')
        h.update(quantity=float(remaining),unit='kg')
        offers=db.execute('''SELECT o.*,u.name FROM app_offers o JOIN app_users u ON u.id=o.owner_id
                             WHERE o.status='active' AND (o.listing_id IS NULL OR o.listing_id=?)''',(listing_id,)).fetchall()
        remaining_capacity={o['id']:capacity(db,o) for o in offers}
    records=[]
    for row in offers:
        o=json.loads(row['payload'])
        cap=remaining_capacity[row['id']]
        if cap<=0 or cap<decimal_value(o['offer'].get('min_quantity_kg',0),'Minimum quantity'): continue
        o['offer']['max_quantity_kg']=str(cap)
        if o['crop']!=h['crop'] or o['accepted_grade'] not in ('Any',h['grade']) or o['accepted_variety'] not in ('Any',h['variety']): continue
        if datetime.fromisoformat(o['offer']['valid_until'])<=datetime.now(timezone.utc): continue
        records.append({'id':row['id'],'name':f"{row['name']} — {o['title']}",'crop':o['crop'],'demo':False,
                        'description':'Account-submitted offer; identity and crop quality have not been independently verified.',
                        'coordinates':{'latitude':o['destination_latitude'],'longitude':o['destination_longitude']},
                        'coordinate_evidence':'Buyer-entered delivery point','offer':o['offer'],
                        'delivery_deadline':o['delivery_deadline']})
    # Live proposals must agree to the same saved assumptions shown in preview.
    # Edit the listing to change its transport settings or partial-sale consent.
    payload=h
    from backend.buyers import suggestions,select_buyer
    if selection:
        payload.update(buyer_id=options.get('buyer_id'),acknowledge_warning=options.get('acknowledge_warning'))
        result=select_buyer(payload,records=records)
        chosen=next(o for o in offers if o['id']==options.get('buyer_id'))
        result.update(listing_version=listing_version,offer_version=chosen['version'],
                      proposal_terms={'harvest':saved_harvest,'quote':json.loads(chosen['payload'])})
        return result
    result=suggestions(payload,records=records)
    versions={o['id']:o['version'] for o in offers}
    for buyer in result['buyers']: buyer['offer_version']=versions[buyer['id']]
    result['listing_version']=listing_version
    return result
