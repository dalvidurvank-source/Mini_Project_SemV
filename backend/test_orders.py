"""HTTP integration regressions for inventory, consent and durable sale history."""
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.database import connect
from backend import test_workspace as workspace
from backend.test_workspace import Client, quote


class OrderTests(unittest.TestCase):
    setUpClass = classmethod(workspace.WorkspaceTests.setUpClass.__func__)
    tearDownClass = classmethod(workspace.WorkspaceTests.tearDownClass.__func__)
    saved = workspace.WorkspaceTests.saved
    offered = workspace.WorkspaceTests.offered

    def setUp(self):
        with connect() as db:
            for table in ('app_order_requests', 'app_order_events', 'app_orders', 'app_photos', 'app_offers', 'app_listings'):
                db.execute('DELETE FROM '+table)

    def propose(self, listing=None, offer=None, quantity=500, client=None, **extra):
        listing = listing or self.saved(status='published', allow_partial_sales=True)
        offer = offer or self.offered(listing_id=listing['id'])
        body = dict(listing_id=listing['id'], offer_id=offer['id'], quantity_kg=quantity,
                    listing_version=listing['version'], offer_version=offer['version'],
                    agree_terms=True, acknowledge_warning=True, request_key=uuid.uuid4().hex)
        body.update(extra)
        status, result = (client or self.farmer).call('/api/app/orders', body)
        return status, result, body

    def proposed(self, **kwargs):
        status, result, _ = self.propose(**kwargs)
        self.assertEqual(status, 200, result)
        return result

    def act(self, order, action, client=None, **extra):
        body = dict(action=action, version=order['version'], request_key=uuid.uuid4().hex,
                    agree_terms=True, acknowledge_warning=True)
        body.update(extra)
        return (client or self.buyer).call('/api/app/orders/'+order['id'], body)

    def test_explicit_consent_authoritative_terms_and_private_orders(self):
        status, _, _ = self.propose(agree_terms=False)
        self.assertEqual(status, 422)
        l = self.saved(status='published')
        o = self.offered(listing_id=l['id'], selling_charges=[{'type':'per_kg','label':'Sorting','value':'0.33'}])
        status, order, _ = self.propose(l, o, price_inr_per_kg=9999, farmer_id='forged', buyer_id='forged', net_return_inr=999999)
        self.assertEqual(status, 200, order)
        self.assertEqual(order['terms']['quote']['offer']['price_inr_per_kg'], 23)
        self.assertEqual(order['terms']['evaluation']['financial']['other_selling_charges_inr'], 165)
        self.assertEqual(order['status'], 'proposed')
        self.assertEqual(self.farmer.call('/api/app/listings/'+l['id'])[1]['available_quantity_kg'], '500.0')
        for c in (self.other_farmer, self.other_buyer):
            self.assertEqual(c.call('/api/app/orders/'+order['id'])[0], 404)
            self.assertEqual(c.call('/api/app/orders')[1]['orders'], [])
            self.assertEqual(self.act(order, 'accept', c)[0], 404)
        self.assertEqual(Client(self.base).call('/api/app/orders')[0], 401)
        self.assertEqual(self.propose(l, o, client=self.buyer)[0], 403)
        self.assertEqual(self.act(order,'accept',self.farmer)[0], 403)
        self.assertEqual(self.act(order,'accept',agree_terms=False)[0], 422)
        self.assertEqual(self.buyer.call('/api/app/orders/'+order['id'],{},headers={'X-CSRF-Token':''})[0],403)

    def test_order_lifecycle_and_actuals_are_separate_from_terms(self):
        order = self.proposed()
        snapshot = order['terms']
        self.assertEqual(self.act(order,'collect')[0],409)
        for action, actor in (('accept',self.buyer),('ready',self.farmer),('collect',self.buyer)):
            status, order = self.act(order,action,actor)
            self.assertEqual(status,200,order)
        self.assertEqual(self.act(order,'cancel')[0],409)
        self.assertEqual(self.act(order,'deliver',accepted_weight_kg=501,actual_grade='B')[0],422)
        self.assertEqual(self.act(order,'deliver',accepted_weight_kg=490,actual_grade='B')[0],422)
        status, order = self.act(order,'deliver',accepted_weight_kg='490.25',actual_grade='B',notes='9.75 kg rejected for damage')
        self.assertEqual(status,200,order)
        self.assertEqual(order['terms'],snapshot)
        self.assertEqual(order['actuals']['accepted_weight_kg'],'490.25')
        self.assertEqual(self.act(order,'complete',self.farmer,agree_actuals=False)[0],422)
        status, order = self.act(order,'complete',self.farmer,agree_actuals=True)
        self.assertEqual(status,200,order)
        self.assertEqual([e['status'] for e in order['events']],['proposed','accepted','ready','collected','delivered','completed'])
        self.assertTrue(all(e['occurred_at'] for e in order['events']))
        listing = self.farmer.call('/api/app/listings/'+order['listing_id'])[1]
        self.assertEqual(float(listing['available_quantity_kg']),0)
        self.assertEqual(float(listing['committed_quantity_kg']),500)
        # New connection and session still see immutable terms and the event history.
        fresh = Client(self.base)
        from backend.test_workspace import PASSWORD
        fresh.call('/api/auth/login',{'email':'farmer@example.test','password':PASSWORD})
        self.assertEqual(fresh.call('/api/app/orders/'+order['id'])[1],order)

    def test_retries_are_idempotent_and_conflicting_keys_rejected(self):
        status, order, body = self.propose()
        self.assertEqual(status,200,order)
        self.assertEqual(self.farmer.call('/api/app/orders',body)[1]['id'],order['id'])
        self.assertEqual(self.farmer.call('/api/app/orders',{**body,'quantity_kg':1})[0],409)
        accept = dict(action='accept',version=order['version'],agree_terms=True,acknowledge_warning=True,request_key='repeat-action')
        status, accepted = self.buyer.call('/api/app/orders/'+order['id'],accept)
        self.assertEqual(status,200,accepted)
        status, retry = self.buyer.call('/api/app/orders/'+order['id'],accept)
        self.assertEqual(status,200,retry)
        self.assertEqual(retry,accepted)
        self.assertEqual(self.buyer.call('/api/app/orders/'+order['id'],{**accept,'action':'cancel'})[0],409)
        self.assertEqual(len(self.farmer.call('/api/app/orders')[1]['orders']),1)
        other=self.proposed()
        # A caller-supplied path identity cannot disguise key reuse on another order.
        self.assertEqual(self.buyer.call('/api/app/orders/'+other['id'],{**accept,'order_id':order['id']})[0],409)
        self.assertEqual(self.farmer.call('/api/app/orders/'+other['id'])[1]['status'],'proposed')

    def test_competing_buyers_cannot_oversell_one_harvest(self):
        l = self.saved(status='published',allow_partial_sales=True)
        first = self.offered(listing_id=l['id'])
        status, second = self.other_buyer.call('/api/app/offers',quote(listing_id=l['id']))
        self.assertEqual(status,200,second)
        a,b = self.proposed(listing=l,offer=first,quantity=300), self.proposed(listing=l,offer=second,quantity=300)
        barrier = threading.Barrier(2)
        def accept(order,client):
            barrier.wait()
            return self.act(order,'accept',client)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [f.result() for f in (pool.submit(accept,a,self.buyer),pool.submit(accept,b,self.other_buyer))]
        self.assertEqual(sorted(r[0] for r in results),[200,409],results)
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+l['id'])[1]['available_quantity_kg']),200)

    def test_general_offer_budget_is_shared_across_harvests(self):
        o = self.offered(max_quantity_kg=600)
        a,b = self.proposed(offer=o,quantity=400),self.proposed(offer=o,quantity=400)
        self.assertEqual(self.act(a,'accept')[0],200)
        self.assertEqual(self.act(b,'accept')[0],409)
        saved = self.buyer.call('/api/app/offers')[1]['offers'][0]
        self.assertEqual(saved['remaining_capacity_kg'],'200')
        status, comparison = self.farmer.call('/api/app/listings/'+b['listing_id']+'/buyers',{})
        self.assertEqual(status,200,comparison)
        self.assertEqual(comparison['buyers'][0]['financial']['sale_quantity_kg'],200)

    def test_fractional_stock_is_consumed_with_decimal_arithmetic(self):
        l=self.saved(status='published',allow_partial_sales=True,quantity='0.3')
        o=self.offered(listing_id=l['id'],max_quantity_kg='0.3')
        a,b=self.proposed(listing=l,offer=o,quantity='0.1'),self.proposed(listing=l,offer=o,quantity='0.2')
        for order in (a,b): self.assertEqual(self.act(order,'accept')[0],200)
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+l['id'])[1]['available_quantity_kg']),0)
        self.assertEqual(float(self.buyer.call('/api/app/offers')[1]['offers'][0]['remaining_capacity_kg']),0)
        self.assertEqual(self.propose(l,o,quantity='0.000001')[0],409)

    def test_simultaneous_acceptance_shares_general_offer_budget(self):
        o=self.offered(max_quantity_kg=500)
        a,b=self.proposed(offer=o,quantity=300),self.proposed(offer=o,quantity=300)
        barrier=threading.Barrier(2)
        def accept(order):
            barrier.wait()
            return self.act(order,'accept')
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(accept,v) for v in (a,b)]
            results=[f.result() for f in futures]
        self.assertEqual(sorted(r[0] for r in results),[200,409],results)

    def test_collection_rechecks_deadline_without_changing_saved_terms(self):
        order=self.proposed()
        _,order=self.act(order,'accept')
        _,order=self.act(order,'ready',self.farmer)
        # Acceptance remains reserved, but starting the journey too late is blocked.
        future=datetime.now(timezone.utc)+timedelta(hours=11)
        from logistics.shelf_life import INDIA
        with patch('logistics.shelf_life.india_now',return_value=future.astimezone(INDIA)):
            self.assertEqual(self.act(order,'collect')[0],409)
        # A pickup whose earliest time is past is not by itself a failed crop check.
        from backend.orders import recheck_delivery
        terms=order['terms']
        terms['harvest']['pickup_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        self.assertTrue(recheck_delivery(terms,True)['can_select'])

    def test_cancellation_releases_stock_and_budget(self):
        order = self.proposed(quantity=300)
        status, order = self.act(order,'accept')
        self.assertEqual(status,200,order)
        status, order = self.act(order,'cancel',self.farmer)
        self.assertEqual(status,200,order)
        self.assertEqual(order['status'],'cancelled')
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+order['listing_id'])[1]['available_quantity_kg']),500)
        self.assertEqual(float(self.buyer.call('/api/app/offers')[1]['offers'][0]['remaining_capacity_kg']),1000)
        self.assertEqual(self.act(order,'accept')[0],409)

    def test_expiry_releases_uncollected_reservations_but_not_collected_stock(self):
        a,b = self.proposed(quantity=300),self.proposed(quantity=200)
        for order in (a,b):
            status, accepted = self.act(order,'accept')
            self.assertEqual(status,200,accepted)
            if order['id']==b['id']:
                _,ready=self.act(accepted,'ready',self.farmer)
                self.assertEqual(self.act(ready,'collect')[0],200)
        with connect() as db:
            db.execute("UPDATE app_orders SET expires_at='2000-01-01T00:00:00+00:00'")
        # Availability doesn't need the sweep or a background thread to release expired stock.
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+a['listing_id'])[1]['available_quantity_kg']),500)
        orders = self.farmer.call('/api/app/orders')[1]['orders']
        arow,brow = [next(o for o in orders if o['id']==v['id']) for v in (a,b)]
        self.assertEqual(arow['status'],'expired')
        self.assertIsNone(arow['events'][-1]['actor_id'])
        self.assertEqual(brow['status'],'collected')
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+b['listing_id'])[1]['available_quantity_kg']),300)
        self.assertEqual(self.act(arow,'accept')[0],409)

    def test_expired_proposals_and_rejections_do_not_reserve(self):
        order=self.proposed()
        self.assertEqual(self.act(order,'reject',self.farmer)[0],409)
        status,rejected=self.act(order,'reject')
        self.assertEqual(status,200,rejected)
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+order['listing_id'])[1]['available_quantity_kg']),500)
        order=self.proposed()
        with connect() as db:db.execute("UPDATE app_orders SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(order['id'],))
        self.assertEqual(self.act(order,'accept')[0],409)
        self.assertEqual(self.farmer.call('/api/app/orders/'+order['id'])[1]['status'],'expired')

    def test_changed_listing_or_quote_needs_new_mutual_agreement(self):
        l=self.saved(status='published')
        o=self.offered(listing_id=l['id'])
        order=self.proposed(listing=l,offer=o)
        self.assertEqual(self.buyer.call('/api/app/offers/'+o['id'],{**quote(),'listing_id':l['id'],'version':o['version'],'price_inr_per_kg':24},'PATCH')[0],200)
        self.assertEqual(self.act(order,'accept')[0],409)
        self.assertEqual(order['terms']['quote']['offer']['price_inr_per_kg'],23)
        self.assertEqual(self.propose(l,o)[0],409)

    def test_committed_records_cannot_be_edited_to_reset_inventory(self):
        l=self.saved(status='published',allow_partial_sales=True)
        o=self.offered(listing_id=l['id'])
        order=self.proposed(listing=l,offer=o,quantity=300)
        status,order=self.act(order,'accept')
        self.assertEqual(status,200,order)
        self.assertEqual(self.farmer.call('/api/app/listings/'+l['id'],{**l['harvest'],'quantity':900,'version':l['version']},'PATCH')[0],409)
        self.assertEqual(self.buyer.call('/api/app/offers/'+o['id'],{**quote(),'listing_id':l['id'],'version':o['version'],'max_quantity_kg':9000},'PATCH')[0],409)
        self.assertEqual(self.buyer.call('/api/app/offers/'+o['id'],{'version':o['version']},'DELETE')[0],200)
        self.assertEqual(self.act(order,'ready',self.farmer)[0],200)
        self.assertEqual(self.act(order,'cancel',version=1)[0],409)

    def test_routes_and_delivery_are_rechecked_on_acceptance(self):
        order=self.proposed()
        with patch('backend.buyers.plan_route',side_effect=ValueError('Road routing unavailable')):
            self.assertEqual(self.act(order,'accept')[0],422)
        later=datetime.now(timezone.utc)+timedelta(hours=40)
        with patch('logistics.shelf_life.india_now',return_value=later):
            self.assertIn(self.act(order,'accept')[0],(409,422))
        self.assertEqual(float(self.farmer.call('/api/app/listings/'+order['listing_id'])[1]['available_quantity_kg']),500)

    def test_partial_permissions_and_precision(self):
        l=self.saved(status='published')
        o=self.offered(listing_id=l['id'])
        self.assertEqual(self.propose(l,o,quantity=300)[0],409)
        for quantity in (0,-1,True,'NaN','0.0000001'):
            self.assertEqual(self.propose(l,o,quantity=quantity)[0],422)

    def test_additive_v1_migration_preserves_existing_records(self):
        l=self.saved()
        o=self.offered()
        with connect() as db:
            for table in ('app_order_requests','app_order_events','app_orders'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=1')
        with connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertIsNotNone(db.execute('SELECT * FROM app_listings WHERE id=?',(l['id'],)).fetchone())
            self.assertIsNotNone(db.execute('SELECT * FROM app_offers WHERE id=?',(o['id'],)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM app_users').fetchone()[0],4)
        self.assertEqual(self.farmer.call('/api/app/listings/'+l['id'])[0],200)


if __name__ == '__main__':
    unittest.main()
