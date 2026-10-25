"""Comparable buyer-offer scenarios. Monetary arithmetic uses Decimal/paise.

Terms come from the server directory, never the farmer's financial totals.
There is no defensible spoilage-loss estimate, forecast substitution or DSR.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PAISE = Decimal('0.01')


def decimal_value(value, label, positive=False):
    try:
        if isinstance(value,bool) or value is None:
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or (positive and result <= 0) or result > Decimal('1000000000000'):
            raise ValueError()
        return result
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError(f'{label} must be finite and {"positive" if positive else "non-negative"}.')


def money(value):
    return float(value.quantize(PAISE,rounding=ROUND_HALF_UP))


def offer_plan(buyer, harvest_kg, allow_partial, now):
    harvest = Decimal(str(harvest_kg))
    base = {'status':'missing_offer','reason':'No buyer offer has been provided. No forecast is substituted for an offer.',
            'offer_kind':None,'offer_label':'Offer unavailable','price_inr_per_kg':None,
            'buyer_capacity_kg':None,'minimum_quantity_kg':None,'sale_quantity_kg':float(harvest),
            'unsold_quantity_kg':None,'sale_scope':'unconfirmed','acceptance_status':'unknown',
            'can_prepare_draft':True,'selling_charges':[], 'transport_quantity_kg':float(harvest),
            'offer_source':None,'valid_until':None}
    terms = buyer.get('offer')
    if terms is None:
        return base
    try:
        if not isinstance(terms,dict):
            raise ValueError('Offer terms must be an object.')
        kind = terms.get('kind')
        if kind not in ('demo_offer','buyer_offer'):
            raise ValueError('Offer kind must explicitly distinguish demo and actual buyer offers.')
        if buyer.get('demo',True) and kind != 'demo_offer':
            raise ValueError('A demo buyer cannot be presented as an actual buyer offer.')
        capacity = decimal_value(terms.get('max_quantity_kg'),'Buyer purchase capacity',True)
        minimum = decimal_value(terms.get('min_quantity_kg',0),'Minimum purchase quantity')
        if minimum > capacity:
            raise ValueError('Minimum purchase quantity exceeds buyer capacity.')
        if not isinstance(terms.get('partial_sales_supported',False),bool):
            raise ValueError('Partial-sale support must be a boolean.')
        if kind == 'buyer_offer':
            if not isinstance(terms.get('source'),str) or not terms['source'].strip():
                raise ValueError('Actual buyer offer needs attributable evidence.')
            expires = datetime.fromisoformat(terms['valid_until'])
            if expires.tzinfo is None or expires <= now:
                raise ValueError('Buyer offer is expired or lacks a timezone.')
        if terms.get('valid_until') and kind == 'demo_offer':
            expires = datetime.fromisoformat(terms['valid_until'])
            if expires.tzinfo is None or expires <= now:
                raise ValueError('Demo offer has expired or lacks a timezone.')
        partial = harvest > capacity
        sale = min(harvest,capacity)
        scope = 'partial' if partial else 'full_harvest'
        base.update(offer_kind=kind,offer_label='Illustrative demo offer' if kind=='demo_offer' else 'Actual buyer offer',
                    buyer_capacity_kg=float(capacity),minimum_quantity_kg=float(minimum),sale_scope=scope,
                    offer_source=terms.get('source') if isinstance(terms.get('source'),str) else None,
                    valid_until=terms.get('valid_until'))
        if partial and not (allow_partial and terms.get('partial_sales_supported',False)):
            return {**base,'status':'capacity_exceeded','reason':'Buyer cannot take the full harvest. Partial sales require both farmer opt-in and buyer support.',
                    'sale_quantity_kg':0,'unsold_quantity_kg':float(harvest),'acceptance_status':'rejected','can_prepare_draft':False}
        if sale < minimum:
            return {**base,'status':'below_minimum','reason':'The sale quantity is below the buyer minimum.',
                    'sale_quantity_kg':0,'unsold_quantity_kg':float(harvest),'acceptance_status':'rejected','can_prepare_draft':False}
        base.update(sale_quantity_kg=float(sale),unsold_quantity_kg=float(harvest-sale),
                    transport_quantity_kg=float(sale),acceptance_status='accepted')
        charges = terms.get('selling_charges',[])
        if not isinstance(charges,list) or len(charges)>20:
            raise ValueError('Selling charges must be a list of at most 20 items.')
        clean = []
        for c in charges:
            if not isinstance(c,dict) or not isinstance(c.get('label'),str) or not c['label'].strip():
                raise ValueError('Each selling charge needs a label.')
            if c.get('type') not in ('fixed','per_kg','percent_of_gross'):
                raise ValueError('Unknown selling-charge type.')
            val = decimal_value(c.get('value'),'Selling charge')
            if c['type']=='percent_of_gross' and val > 100:
                raise ValueError('Percentage selling charge cannot exceed 100.')
            clean.append({'label':c['label'][:120],'type':c['type'],'value':float(val)})
        base['selling_charges'] = clean
        if terms.get('price_inr_per_kg') is None:
            return {**base,'reason':'Buyer price is missing; capacity is known, but financial ranking is unavailable.'}
        price = decimal_value(terms['price_inr_per_kg'],'Buyer offer price',True)
        if price != price.quantize(PAISE,rounding=ROUND_HALF_UP):
            raise ValueError('Buyer offer price must use at most two decimal places per kg.')
        return {**base,'status':'available','reason':'Server-owned buyer offer terms; estimated costs remain planning assumptions.',
                'price_inr_per_kg':float(price)}
    except (ValueError,KeyError,TypeError,OverflowError) as exc:
        return {**base,'status':'invalid_offer','acceptance_status':'rejected','can_prepare_draft':False,
                'price_inr_per_kg':None,'reason':f'Invalid buyer offer: {exc}'}


def financial_outcome(plan, transport, shelf):
    result = {**plan,'rankable':False,'rank':None,'comparison_group':None,'is_best':False,
              'gross_sale_inr':None,'transport_cost_inr':None,'other_selling_charges_inr':None,
              'net_return_inr':None,'net_per_sellable_kg':None,'charge_breakdown':[],
              'dsr_applied':False,'quality_loss_estimate':None,
              'assumptions':['No defensible spoilage-quantity or quality-price loss estimate is available; no measured loss is assumed.',
                             'Price applies to the planned sale quantity; actual grading and delivered weight are unverified.',
                             'Unsold produce has no assumed resale value. Production cost, driver hire and maintenance are not included.',
                             'Listed selling charges are included once. Unspecified charges are not estimated. No DSR is applied.']}
    if transport:
        result['transport_cost_inr']=transport['total_trip_cost_inr']
    if plan['status']!='available' or not transport:
        result['ranking_reason']=plan['reason'] if transport else 'No dependable road route; financial ranking is unavailable.'
        return result
    quantity = Decimal(str(plan['sale_quantity_kg']))
    gross = (quantity*Decimal(str(plan['price_inr_per_kg']))).quantize(PAISE,rounding=ROUND_HALF_UP)
    charges = Decimal(0)
    for charge in plan['selling_charges']:
        value = Decimal(str(charge['value']))
        amount = value if charge['type']=='fixed' else value*quantity if charge['type']=='per_kg' else value*gross/100
        amount = amount.quantize(PAISE,rounding=ROUND_HALF_UP)
        charges += amount
        result['charge_breakdown'].append({**charge,'amount_inr':float(amount)})
    net = gross-Decimal(str(transport['total_trip_cost_inr']))-charges
    group = 'full_harvest' if plan['sale_scope']=='full_harvest' else f'partial:{quantity.normalize()}'
    result.update(gross_sale_inr=float(gross),other_selling_charges_inr=money(charges),net_return_inr=money(net),
                  net_per_sellable_kg=money(net/quantity),comparison_group=group,
                  rankable=shelf['can_select'],
                  ranking_reason='Delivery check failed; excluded from financial ranking.' if not shelf['can_select'] else '')
    return result


def rank_buyers(buyers):
    groups = {}
    for buyer in buyers:
        f = buyer['financial']
        if f['rankable']:
            groups.setdefault(f['comparison_group'],[]).append(buyer)
    descriptions=[]
    for key,items in groups.items():
        # Stable identifier resolves exact ties without silently ranking by distance.
        items.sort(key=lambda b:(-b['financial']['net_return_inr'],b['id']))
        best = items[0]['financial']['net_return_inr']
        rank=0;previous=None
        for index,buyer in enumerate(items):
            f=buyer['financial'];net=f['net_return_inr']
            if net!=previous: rank=index+1
            f.update(rank=rank,is_best=net==best)
            label=f"{f['sale_quantity_kg']:g} kg {'full harvest' if key=='full_harvest' else 'partial sale'}"
            difference=round(best-net,2)
            f['ranking_reason']=(f'Highest estimated net return among comparable {label} offers.' if net==best else
                                  f'Estimated net return is INR {difference:,.2f} below the best comparable {label} offer after transport and listed charges.')
            previous=net
        descriptions.append({'id':key,'quantity_kg':items[0]['financial']['sale_quantity_kg'],
                             'scope':items[0]['financial']['sale_scope'],'buyer_count':len(items)})
    descriptions.sort(key=lambda g:(g['scope']!='full_harvest',-g['quantity_kg']))
    group_order={g['id']:i for i,g in enumerate(descriptions)}
    buyers.sort(key=lambda b:(0,group_order[b['financial']['comparison_group']],b['financial']['rank'],b['id'])
                if b['financial']['rankable'] else (1 if b['shelf_life']['can_select'] else 2,0,0,b['id']))
    return descriptions
