import base64
import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime,timedelta,timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,build_opener,HTTPCookieProcessor
from urllib.error import HTTPError
from unittest.mock import patch

from backend.database import connect
from backend.server import Handler
from logistics.shelf_life import india_now

PASSWORD='FarmProject!2026'


class QuietHandler(Handler):
    def log_message(self,format,*args): pass


class Client:
    def __init__(self,base):
        self.base=base;self.jar=http.cookiejar.CookieJar();self.opener=build_opener(HTTPCookieProcessor(self.jar));self.csrf=''
    def call(self,path,body=None,method=None,headers=None):
        h={'X-Agrolink-Client':'1','Origin':'http://127.0.0.1:15173'}
        if body is not None:h['Content-Type']='application/json'
        if self.csrf:h['X-CSRF-Token']=self.csrf
        h.update(headers or {})
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                    headers=h,method=method or ('POST' if body is not None else 'GET'))
        try: response=self.opener.open(req,timeout=60)
        except HTTPError as exc: response=exc
        with response:
            raw=response.read();data=json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
            self.last_headers=response.headers
            if isinstance(data,dict) and 'csrf' in data:self.csrf=data['csrf']
            return response.status,data


def harvest(title='Test tomatoes',**changes):
    now=india_now()
    return dict(crop='Tomato',title=title,notes='',quantity=500,unit='kg',variety='Other',grade='A',
                harvest_date=now.date().isoformat(),harvest_time=now.strftime('%H:%M'),selling_date=now.date().isoformat(),
                produce_condition='firm_ripe',farm_name='Test pickup',farm_latitude=19.1236,farm_longitude=72.8361,
                status='draft',**changes)


def quote(**changes):
    now=datetime.now(timezone.utc)
    return dict(title='Test offer',crop='Tomato',price_inr_per_kg=23,max_quantity_kg=1000,min_quantity_kg=0,
                accepted_grade='Any',accepted_variety='Any',destination_name='Nashik test yard',
                destination_latitude=20.015063587300105,destination_longitude=73.79766078270252,
                valid_until=(now+timedelta(hours=4)).isoformat(),delivery_deadline=(now+timedelta(hours=12)).isoformat(),
                partial_sales_supported=True,selling_charges=[],**changes)


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.env=patch.dict(os.environ,{'AGROLINK_APP_DB':str(Path(cls.tmp.name)/'app.sqlite3'),
                                     'AGROLINK_FRONTEND_ORIGIN':'http://127.0.0.1:15173'})
        cls.env.start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.farmer=Client(cls.base);cls.other_farmer=Client(cls.base);cls.buyer=Client(cls.base);cls.other_buyer=Client(cls.base)
        for client,email,role in ((cls.farmer,'farmer@example.test','farmer'),(cls.other_farmer,'otherfarmer@example.test','farmer'),
                                  (cls.buyer,'buyer@example.test','buyer'),(cls.other_buyer,'otherbuyer@example.test','buyer')):
            status,result=client.call('/api/auth/register',dict(email=email,password=PASSWORD,name=role+' test',role=role))
            assert status==200,result

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.env.stop();cls.tmp.cleanup()

    def saved(self,**changes):
        body=harvest();body.update(changes)
        status,r=self.farmer.call('/api/app/listings',body)
        self.assertEqual(status,200,r);return r

    def offered(self,**changes):
        body=quote();body.update(changes)
        status,r=self.buyer.call('/api/app/offers',body)
        self.assertEqual(status,200,r);return r

    def test_authentication_roles_and_private_ownership(self):
        anonymous=Client(self.base)
        self.assertEqual(anonymous.call('/api/app/listings')[0],401)
        l=self.saved()
        self.assertEqual(self.other_farmer.call('/api/app/listings/'+l['id'])[0],404)
        self.assertEqual(self.buyer.call('/api/app/listings/'+l['id'])[0],404)
        self.assertEqual(self.buyer.call('/api/app/listings',harvest())[0],403)
        self.assertEqual(self.farmer.call('/api/app/offers',quote())[0],403)
        self.assertEqual(self.farmer.call('/api/app/offers')[0],403)
        self.assertEqual(self.other_farmer.call('/api/app/listings/'+l['id'],{**harvest(),'version':l['version']},'PATCH')[0],404)

    def test_password_storage_cookie_logout_and_expiry(self):
        client=Client(self.base)
        status,r=client.call('/api/auth/login',{'email':'farmer@example.test','password':PASSWORD,'role':'buyer'})
        self.assertEqual(status,200)
        self.assertEqual(r['user']['role'],'farmer')
        self.assertIn('HttpOnly',client.last_headers['Set-Cookie'])
        self.assertIn('SameSite=Lax',client.last_headers['Set-Cookie'])
        raw_token=next(c.value for c in client.jar if c.name=='agrolink_session')
        with connect() as db:
            row=db.execute("SELECT password_hash FROM app_users WHERE email='farmer@example.test'").fetchone()
            self.assertNotIn(PASSWORD,row[0]);self.assertTrue(row[0].startswith('pbkdf2_sha256$600000$'))
            self.assertIsNone(db.execute('SELECT * FROM app_sessions WHERE token_hash=?',(raw_token,)).fetchone())
        self.assertEqual(client.call('/api/auth/logout',{})[0],200)
        self.assertEqual(client.call('/api/app/listings')[0],401)
        client.call('/api/auth/login',{'email':'farmer@example.test','password':PASSWORD})
        from backend.accounts import token_hash
        token=next(c.value for c in client.jar if c.name=='agrolink_session')
        with connect() as db:db.execute('UPDATE app_sessions SET expires_at=0 WHERE token_hash=?',(token_hash(token),))
        self.assertEqual(client.call('/api/app/listings')[0],401)

    def test_csrf_and_origin_protection(self):
        self.assertEqual(self.farmer.call('/api/app/listings',harvest(),headers={'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.farmer.call('/api/app/listings',harvest(),headers={'Origin':'https://attacker.example'})[0],403)
        self.assertEqual(self.farmer.call('/api/app/listings',harvest(),headers={'X-Agrolink-Client':''})[0],403)
        self.assertEqual(self.farmer.call('/api/app/listings',[])[0],422)

    def test_registration_validation_and_login_throttling(self):
        c=Client(self.base)
        self.assertEqual(c.call('/api/auth/register',dict(email='farmer@example.test',password=PASSWORD,name='Test',role='farmer'))[0],409)
        self.assertEqual(c.call('/api/auth/register',dict(email='admin@example.test',password=PASSWORD,name='Test',role='admin'))[0],422)
        self.assertEqual(c.call('/api/auth/register',dict(email='bad',password='weak',name='Test',role='buyer'))[0],422)
        for i in range(5):self.assertEqual(c.call('/api/auth/login',dict(email='locked@example.test',password=PASSWORD))[0],401)
        self.assertEqual(c.call('/api/auth/login',dict(email='locked@example.test',password=PASSWORD))[0],429)

    def test_registration_rate_limit(self):
        import time
        from backend.accounts import token_hash
        key=token_hash('register|127.0.0.1')
        with connect() as db:
            db.executemany('INSERT INTO app_login_failures VALUES (?,?)',[(key,time.time()) for _ in range(20)])
        try:
            c=Client(self.base)
            self.assertEqual(c.call('/api/auth/register',dict(email='limited@example.test',password=PASSWORD,name='Test',role='farmer'))[0],429)
        finally:
            with connect() as db:db.execute('DELETE FROM app_login_failures WHERE key=?',(key,))

    def test_multiple_listings_persistence_and_version_conflicts(self):
        a=self.saved(title='Lot one');b=self.saved(title='Lot two')
        c=Client(self.base);c.call('/api/auth/login',{'email':'farmer@example.test','password':PASSWORD})
        status,r=c.call('/api/app/listings');self.assertEqual(status,200)
        self.assertTrue({a['id'],b['id']}.issubset({x['id'] for x in r['listings']}))
        body={**a['harvest'],'title':'Edited lot','version':a['version']}
        self.assertEqual(c.call('/api/app/listings/'+a['id'],body,'PATCH')[0],200)
        self.assertEqual(c.call('/api/app/listings/'+a['id'],body,'PATCH')[0],409)
        self.assertEqual(self.other_farmer.call('/api/app/listings/'+b['id'],{'version':b['version']},'DELETE')[0],404)

    def test_publishing_and_archiving(self):
        l=self.saved(status='published')
        self.assertEqual(self.buyer.call('/api/app/listings/'+l['id'])[0],200)
        self.assertEqual(self.farmer.call('/api/app/listings/'+l['id'],{'version':l['version']},'DELETE')[0],200)
        self.assertEqual(self.buyer.call('/api/app/listings/'+l['id'])[0],404)
        bad=harvest();bad.update(status='published',produce_condition='damaged')
        self.assertEqual(self.farmer.call('/api/app/listings',bad)[0],422)

    def test_photos_are_owner_and_visibility_scoped(self):
        l=self.saved()
        # Tiny PNG fixture, stored and served without image transformations.
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        body={'content_type':'image/png','data_base64':base64.b64encode(raw).decode()}
        status,p=self.farmer.call(f"/api/app/listings/{l['id']}/photos",body);self.assertEqual(status,200,p)
        self.assertEqual(self.farmer.call('/api/app/photos/'+p['id'])[1],raw)
        self.assertEqual(self.other_farmer.call('/api/app/photos/'+p['id'])[0],404)
        self.assertEqual(self.buyer.call('/api/app/photos/'+p['id'])[0],404)
        self.assertEqual(self.buyer.call(f"/api/app/listings/{l['id']}/photos",body)[0],403)
        self.farmer.call('/api/app/listings/'+l['id'],{**l['harvest'],'status':'published','version':l['version']},'PATCH')
        self.assertEqual(self.buyer.call('/api/app/photos/'+p['id'])[0],200)
        self.assertEqual(self.other_farmer.call('/api/app/photos/'+p['id'],{},'DELETE')[0],404)
        self.assertEqual(self.farmer.call('/api/app/photos/'+p['id'],{},'DELETE')[0],200)
        self.assertEqual(self.farmer.call(f"/api/app/listings/{l['id']}/photos",{'content_type':'image/svg+xml','data_base64':'AA=='})[0],422)

    def test_offer_ownership_immutability_and_invalid_terms(self):
        o=self.offered()
        body={**quote(),'version':o['version'],'owner_id':'forged','price_inr_per_kg':25}
        self.assertEqual(self.other_buyer.call('/api/app/offers/'+o['id'],body,'PATCH')[0],404)
        self.assertEqual(self.buyer.call('/api/app/offers/'+o['id'],body,'PATCH')[0],200)
        self.assertEqual(self.buyer.call('/api/app/offers/'+o['id'],body,'PATCH')[0],409)
        for changes in ({'price_inr_per_kg':-1},{'max_quantity_kg':0},{'destination_latitude':91},
                        {'valid_until':'2020-01-01T00:00:00+00:00'},{'delivery_deadline':'bad'}):
            body=quote();body.update(changes)
            self.assertEqual(self.buyer.call('/api/app/offers',body)[0],422)

    def test_live_ranking_uses_saved_lot_and_buyer_terms(self):
        l=self.saved(status='published')
        o=self.offered(listing_id=l['id'])
        path=f"/api/app/listings/{l['id']}"
        self.assertEqual(self.other_farmer.call(path+'/buyers',{})[0],404)
        self.assertEqual(self.buyer.call(path+'/buyers',{})[0],403)
        status,r=self.farmer.call(path+'/buyers',{'quantity':99999,'price_inr_per_kg':99999,'harvest_date':'2099-01-01'})
        self.assertEqual(status,200,r)
        match=next(b for b in r['buyers'] if b['id']==o['id'])
        self.assertFalse(match['demo']);self.assertEqual(match['financial']['sale_quantity_kg'],500)
        self.assertEqual(match['financial']['price_inr_per_kg'],23)
        status,s=self.farmer.call(path+'/selection',{'buyer_id':o['id'],'net_return_inr':999999,'transport_cost':0})
        self.assertEqual(status,200,s);self.assertEqual(s['status'],'draft_only')
        self.assertGreater(s['buyer']['financial']['transport_cost_inr'],0)
        self.assertEqual(self.buyer.call('/api/app/offers/'+o['id'],{'version':o['version']},'DELETE')[0],200)
        self.assertEqual(self.farmer.call(path+'/selection',{'buyer_id':o['id']})[0],422)

    def test_grade_and_buyer_deadline_are_enforced(self):
        l=self.saved(status='published')
        body=quote();body.update(listing_id=l['id'],accepted_grade='B')
        self.assertEqual(self.buyer.call('/api/app/offers',body)[0],422)
        now=datetime.now(timezone.utc)
        o=self.offered(listing_id=l['id'],valid_until=(now+timedelta(minutes=10)).isoformat(),delivery_deadline=(now+timedelta(minutes=30)).isoformat())
        status,r=self.farmer.call(f"/api/app/listings/{l['id']}/buyers",{})
        self.assertEqual(status,200,r)
        b=next(b for b in r['buyers'] if b['id']==o['id'])
        self.assertFalse(b['selection_allowed']);self.assertIn('deadline',b['shelf_life']['reason'])

    def test_role_owner_fields_cannot_escalate(self):
        l=self.saved(owner_id='forged',role='buyer')
        self.assertEqual(self.farmer.call('/api/auth/me')[1]['user']['role'],'farmer')
        self.assertEqual(self.other_farmer.call('/api/app/listings/'+l['id'])[0],404)
