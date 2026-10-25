import unittest
from datetime import datetime, timedelta
from logistics.shelf_life import INDIA, assess_delivery

NOW = datetime(2026,10,24,12,tzinfo=INDIA)


def lot(age=12, **changes):
    harvest = NOW-timedelta(hours=age)
    return {'crop':'Tomato','harvest_date':harvest.date().isoformat(),'harvest_time':harvest.strftime('%H:%M'),
            'selling_date':NOW.date().isoformat(),'produce_condition':'firm_ripe',**changes}


class DeliveryLifeTests(unittest.TestCase):
    def test_near_buyer_passes_far_buyer_is_blocked(self):
        near = assess_delivery(lot(38),2,now=NOW)
        far = assess_delivery(lot(38),5,now=NOW)
        self.assertEqual(near['status'],'warning')
        self.assertEqual(near['slack_hours'],2)
        self.assertTrue(near['requires_acknowledgment'])
        self.assertEqual(far['status'],'blocked')
        self.assertFalse(far['can_select'])

    def test_fresh_crop_and_boundary(self):
        self.assertEqual(assess_delivery(lot(),2,now=NOW)['status'],'eligible')
        self.assertEqual(assess_delivery(lot(40),2,now=NOW)['status'],'warning')
        self.assertEqual(assess_delivery(lot(40),2.1,now=NOW)['status'],'blocked')

    def test_waiting_for_pickup_consumes_life(self):
        r=assess_delivery(lot(30,pickup_at=(NOW+timedelta(hours=12)).isoformat()),2,now=NOW)
        self.assertEqual(r['waiting_hours'],12)
        self.assertEqual(r['status'],'blocked')

    def test_last_trip_includes_return_and_handling(self):
        single=assess_delivery(lot(35),2,now=NOW)
        last=assess_delivery(lot(35),2,trips=2,empty_return_factor=1,now=NOW)
        self.assertTrue(single['can_select'])
        self.assertEqual(last['prior_trips_hours'],6)
        self.assertEqual(last['status'],'blocked')

    def test_date_only_is_conservative_and_no_fake_spoilage_percentage(self):
        r=assess_delivery(lot(harvest_time=''),1,now=NOW)
        self.assertEqual(r['harvest_age_hours'],12)
        self.assertTrue(r['date_only_harvest'])
        self.assertNotIn('spoilage_percentage',r)

    def test_damaged_or_expired_lot_cannot_be_selected(self):
        self.assertEqual(assess_delivery(lot(produce_condition='damaged'),0,now=NOW)['status'],'blocked')
        self.assertEqual(assess_delivery(lot(60),0,now=NOW)['status'],'blocked')

    def test_unknown_conditions_are_conservative(self):
        self.assertEqual(assess_delivery(lot(1,produce_condition='unknown'),1,now=NOW)['status'],'warning')
        self.assertEqual(assess_delivery(lot(20,produce_condition='very_ripe'),1,now=NOW)['status'],'blocked')

    def test_invalid_dates_and_forged_policy_do_not_bypass(self):
        for changes in ({'harvest_date':'bad'},{'harvest_time':'25:00'}, {'harvest_date':'2026-10-25'},
                        {'produce_condition':'unlimited'}, {'produce_condition':[]}, {'pickup_at':'2026-10-23T10:00'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                assess_delivery(lot(**changes),1,now=NOW)
        r=assess_delivery(lot(60,shelf_life_hours=100000,can_select=True),1,now=NOW)
        self.assertFalse(r['can_select'])
