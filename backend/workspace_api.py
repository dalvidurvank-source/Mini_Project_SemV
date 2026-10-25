"""HTTP adapter for authenticated account, listing and offer operations."""
import json
import logging
from urllib.parse import urlparse

from backend import accounts, trading, orders
from backend.accounts import AppError


def read_body(handler):
    if handler.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
        raise AppError(415,'Send JSON request data.')
    size=int(handler.headers.get('Content-Length',0))
    limit=2_900_000 if handler.path.endswith('/photos') else 32768
    if size<=0 or size>limit: raise AppError(413,'Request is empty or too large.')
    def invalid_number(value): raise ValueError('Non-finite JSON numbers are not accepted.')
    payload=json.loads(handler.rfile.read(size),parse_constant=invalid_number)
    if not isinstance(payload,dict): raise AppError(422,'Expected a JSON object.')
    return payload


def operation(handler):
    path=urlparse(handler.path).path
    method=handler.command
    mutation=method!='GET'
    if mutation: accounts.check_origin(handler)
    if path=='/api/auth/me' and method=='GET':
        user=accounts.current(handler.headers,False)
        return {'user':{k:user[k] for k in ('id','email','name','role')} if user else None,
                'csrf':user['csrf'] if user else ''},None
    if path in ('/api/auth/register','/api/auth/login') and method=='POST':
        payload=read_body(handler)
        response,cookie=accounts.register(payload,handler.client_address[0]) if path.endswith('register') else accounts.login(payload,handler.client_address[0])
        return response,{'Set-Cookie':cookie}
    user=accounts.require(handler.headers,mutation=mutation)
    if path=='/api/app/config' and method=='GET':
        from logistics.shelf_life import policy
        from logistics.listing_route import VEHICLE
        return {'shelf_life_policy':policy(),'logistics':{'vehicle':VEHICLE}},None
    if path=='/api/auth/logout' and method=='POST':
        response,cookie=accounts.logout(user)
        return response,{'Set-Cookie':cookie}
    parts=path.strip('/').split('/')
    if path=='/api/app/orders':
        if method=='GET': return orders.list_orders(user),None
        if method=='POST': return orders.propose(user,read_body(handler)),None
    if len(parts)==4 and parts[:3]==['api','app','orders']:
        if method=='GET': return orders.list_orders(user,parts[3]),None
        if method=='POST': return orders.transition(user,parts[3],read_body(handler)),None
    if path=='/api/app/listings':
        if method=='GET':
            return (trading.my_listings(user) if user['role']=='farmer' else trading.available_listings()),None
        if method=='POST':
            return trading.save_listing(user,read_body(handler)),None
    if path=='/api/app/offers':
        if user['role']!='buyer': raise AppError(403,'Only buyers can manage offers.')
        if method=='GET': return trading.my_offers(user),None
        if method=='POST': return trading.save_offer(user,read_body(handler)),None
    if len(parts)>=4 and parts[:3]==['api','app','listings']:
        record_id=parts[3]
        if len(parts)==4:
            if method=='GET': return trading.get_listing(user,record_id),None
            if method=='PATCH': return trading.save_listing(user,read_body(handler),record_id),None
            if method=='DELETE': return trading.archive_listing(user,record_id,read_body(handler).get('version')),None
        if len(parts)==5 and method=='POST':
            if parts[4]=='photos': return trading.add_photo(user,record_id,read_body(handler)),None
            if parts[4] in ('buyers','selection'):
                return trading.live_matches(user,record_id,read_body(handler),parts[4]=='selection'),None
    if len(parts)==4 and parts[:3]==['api','app','offers']:
        if method=='PATCH': return trading.save_offer(user,read_body(handler),parts[3]),None
        if method=='DELETE': return trading.withdraw_offer(user,parts[3],read_body(handler).get('version')),None
    if len(parts)==4 and parts[:3]==['api','app','photos']:
        if method=='GET':
            mime,data=trading.get_photo(user,parts[3])
            return data,{'Content-Type':mime}
        if method=='DELETE': return trading.delete_photo(user,parts[3]),None
    raise AppError(404,'Endpoint not found.')


def handle(handler):
    if not urlparse(handler.path).path.startswith(('/api/auth/','/api/app/')):
        return False
    try:
        response,headers=operation(handler)
        handler.reply(200,response,headers)
    except AppError as exc:
        handler.reply(exc.status,{'message':str(exc)})
    except (ValueError,KeyError,TypeError) as exc:
        handler.reply(422,{'message':str(exc) if isinstance(exc,ValueError) else 'Invalid request fields.'})
    except Exception:
        logging.exception('Account/workspace request failed')
        handler.reply(500,{'message':'Could not complete this request. Please retry.'})
    return True
