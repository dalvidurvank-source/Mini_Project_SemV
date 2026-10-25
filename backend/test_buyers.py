import json
import threading
import unittest
from datetime import timedelta
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from backend.buyers import suggestions, select_buyer
from backend.server import Handler
from logistics.test_delivery_life import NOW, lot


def payload(age=12, **changes):
    return {**lot(age),'quantity':500,'unit':'kg','farm_latitude':19.1236,'farm_longitude':72.8361,**changes}


class BuyerTests(unittest.TestCase):
    def setUp(self):
        for target in ('backend.buyers.india_now','logistics.shelf_life.india_now'):
            p=patch(target,return_value=NOW)
            p.start();self.addCleanup(p.stop)

    def test_real_saved_routes_rank_and_disable_far_buyer(self):
        r=suggestions(payload(38))
        by_id={b['id']:b for b in r['buyers']}
        self.assertTrue(r['demo'])
        self.assertEqual(by_id['demo-nasik-yard']['shelf_life']['status'],'warning')
        self.assertEqual(by_id['demo-sambhajinagar']['shelf_life']['status'],'blocked')
        self.assertTrue(all(b['demo'] for b in r['buyers']))

    def test_blocked_buyer_cannot_be_selected_by_direct_request(self):
        with self.assertRaisesRegex(ValueError,'Selling unavailable'):
            select_buyer(payload(38,buyer_id='demo-sambhajinagar',acknowledge_warning=True,
                                  can_select=True,shelf_life_hours=10000,destination_latitude=19.12,destination_longitude=72.83))

    def test_warning_requires_explicit_acknowledgment(self):
        p=payload(38,buyer_id='demo-nasik-yard')
        with self.assertRaisesRegex(ValueError,'Acknowledge'):
            select_buyer(p)
        self.assertEqual(select_buyer({**p,'acknowledge_warning':True})['status'],'draft_only')
        with self.assertRaisesRegex(ValueError,'Acknowledge'):
            select_buyer({**p,'acknowledge_warning':'true'})

    def test_selection_reevaluates_time(self):
        p=payload(38,buyer_id='demo-nasik-yard',acknowledge_warning=True)
        self.assertTrue(suggestions(p)['buyers'][0]['shelf_life']['can_select'])
        with patch('backend.buyers.india_now',return_value=NOW+timedelta(hours=4)):
            with self.assertRaisesRegex(ValueError,'Selling unavailable'):
                select_buyer(p)

    def test_route_failure_disables_buyer_without_direct_distance_fallback(self):
        with patch('backend.buyers.plan_route',side_effect=ValueError('Road service unavailable')):
            r=suggestions(payload())
        self.assertTrue(all(b['shelf_life']['status']=='unavailable' for b in r['buyers']))
        self.assertTrue(all(not b['shelf_life']['can_select'] for b in r['buyers']))

    def test_invalid_inputs_and_unknown_buyers(self):
        for changes in ({'quantity':0},{'unit':'tonnes'},{'farm_latitude':91},{'crop':'Potato'},{'quantity':float('nan')}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                suggestions(payload(**changes))
        with self.assertRaisesRegex(ValueError,'Select a buyer'):
            select_buyer(payload(buyer_id='forged'))

    def test_quantity_units_and_last_load(self):
        a=suggestions(payload())
        b=suggestions(payload(quantity=5,unit='quintal'))
        self.assertEqual([x['transport']['total_trip_cost_inr'] for x in a['buyers']],
                         [x['transport']['total_trip_cost_inr'] for x in b['buyers']])
        r=suggestions(payload(35,quantity=1500))
        self.assertTrue(all(not x['shelf_life']['can_select'] for x in r['buyers']))

    def test_http_rejects_blocked_selection(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            req=Request(f'http://127.0.0.1:{server.server_port}/api/buyer-selection',
                        data=json.dumps(payload(38,buyer_id='demo-sambhajinagar',acknowledge_warning=True)).encode(),
                        headers={'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as caught:
                urlopen(req)
            with caught.exception as error:
                self.assertEqual(error.code,422)
                self.assertIn('Selling unavailable',json.load(error)['message'])
        finally:
            server.shutdown();server.server_close();thread.join()
