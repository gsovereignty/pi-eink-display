import unittest
from codex_eink.usage import normalize,countdown,window_view,credit_page

class UsageTest(unittest.TestCase):
    def test_primary_seven_day_secondary_five_hour_identified_by_duration(self):
        quota,extra=normalize({'rateLimits':{'primary':{'usedPercent':30,'windowDurationMins':10080,'resetsAt':500000},'secondary':{'usedPercent':28,'windowDurationMins':300,'resetsAt':10000}}})
        snapshot={'time':1000,'quota':quota,'extra_resets':extra}
        self.assertEqual(window_view(snapshot,300),{'remaining':72,'reset':'2h 30m'})
        self.assertEqual(window_view(snapshot,10080)['remaining'],70)
    def test_missing_five_hour_is_unavailable_not_full_allowance(self):
        quota,_=normalize({'rateLimits':{'primary':{'usedPercent':30,'windowDurationMins':10080,'resetsAt':500000}}})
        self.assertEqual(window_view({'time':1000,'quota':quota},300),{'remaining':None,'reset':'unavailable'})
    def test_unknown_duration_or_duplicate_window_not_assumed(self):
        snapshot={'time':100,'quota':[{'usedPercent':10,'windowDurationMins':100,'resetsAt':1000}]}
        self.assertIsNone(window_view(snapshot,300)['remaining'])
        snapshot['quota']=[{'usedPercent':10,'windowDurationMins':300,'resetsAt':1000}]*2
        self.assertIsNone(window_view(snapshot,300)['remaining'])
    def test_countdown_ceil_minute_and_day_boundaries(self):
        self.assertEqual(countdown(1061,1000),'2m')
        self.assertEqual(countdown(1000+25*3600+61,1000),'1d 1h 2m')
        self.assertEqual(countdown(None,1000),'unavailable')
    def test_due_window_does_not_fabricate_refill(self):
        snapshot={'time':1000,'quota':[{'usedPercent':95,'windowDurationMins':300,'resetsAt':999}]}
        self.assertEqual(window_view(snapshot,300),{'remaining':5,'reset':'Due / awaiting API'})
    def test_over_limit_shows_zero_remaining(self):
        snapshot={'time':1000,'quota':[{'usedPercent':103,'windowDurationMins':300,'resetsAt':2000}]}
        self.assertEqual(window_view(snapshot,300)['remaining'],0)
    def test_extra_count_expiry_order_no_private_fields(self):
        _,extra=normalize({'rateLimitResetCredits':{'availableCount':3,'credits':[
            {'status':'available','expiresAt':5000,'id':'private-credit-id','description':'private'},
            {'status':'redeemed','expiresAt':2000},
            {'status':'available','expiresAt':3000},
            {'status':'available','expiresAt':None}]}})
        self.assertEqual(extra,{'availableCount':3,'credits':[{'expiresAt':3000},{'expiresAt':5000},{'expiresAt':None}]})
        page=credit_page({'time':1000,'extra_resets':extra})
        self.assertEqual(page['available'],3);self.assertEqual(page['rows'][0]['expires'],'34m')
        self.assertEqual(page['rows'][2]['expires'],'unavailable')
    def test_expired_credit_never_shows_negative_countdown(self):
        page=credit_page({'time':1000,'extra_resets':{'availableCount':1,'credits':[{'expiresAt':999}]}})
        self.assertEqual(page['rows'][0]['expires'],'EXPIRED')
    def test_missing_extra_data_is_distinct_from_zero(self):
        _,extra=normalize({})
        self.assertIsNone(extra['availableCount'])
        _,extra=normalize({'rateLimitResetCredits':{'availableCount':0,'credits':[]}})
        self.assertEqual(extra['availableCount'],0)
    def test_extra_pages_cover_every_credit_at_minute_cadence(self):
        credits=[{'expiresAt':10000+i*100} for i in range(7)]
        seen=set()
        for now in (0,60,120):
            page=credit_page({'time':now,'extra_resets':{'availableCount':7,'credits':credits}})
            self.assertLessEqual(len(page['rows']),3);seen.update(r['index'] for r in page['rows'])
        self.assertEqual(seen,set(range(1,8)))
    def test_invalid_usage_and_expiry_numbers_rejected(self):
        for value in (True,float('nan'),float('inf'),-1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                normalize({'rateLimits':{'primary':{'usedPercent':value,'windowDurationMins':300,'resetsAt':1000}}})
        with self.assertRaises(ValueError):normalize({'rateLimitResetCredits':{'availableCount':1.5}})
        with self.assertRaises(ValueError):normalize({'rateLimitResetCredits':{'availableCount':1,'credits':[{'status':'available','expiresAt':float('nan')}]}})
if __name__=='__main__':unittest.main()
