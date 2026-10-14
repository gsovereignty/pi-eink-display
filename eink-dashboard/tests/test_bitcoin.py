import copy
import json
import signal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from epaper_dashboard.bitcoin import Client,ENDPOINTS,cached,render,validate,main,phase_limit
from eink_driver.images import pack,split_rows

FIXTURE=json.loads((Path(__file__).parent/'fixtures/bitcoin.json').read_text())

class BitcoinTest(unittest.TestCase):
    def test_independent_endpoint_failure_preserves_good_value_and_age(self):
        def fetch(_base,path):
            if path==ENDPOINTS['fees']:raise TimeoutError('offline')
            name=next(n for n,p in ENDPOINTS.items() if p==path)
            return FIXTURE['entries'][name]['data']
        cache=copy.deepcopy(FIXTURE['entries']);old=cache['fees']['fetched_at']
        snapshot=Client(cache=cache,fetch=fetch,clock=lambda:old+600).poll()
        self.assertEqual(snapshot['entries']['fees']['fetched_at'],old)
        self.assertEqual(snapshot['entries']['price']['fetched_at'],old+600)
        self.assertEqual(set(snapshot['errors']),{'fees'})
        self.assertTrue(cached(snapshot,'fees'));self.assertFalse(cached(snapshot,'price'))
    def test_cold_network_failure_shows_unavailable_never_fake_numbers(self):
        def fail(*_):raise ConnectionError('offline')
        snapshot=Client(fetch=fail).poll()
        self.assertEqual(snapshot['entries'],{});self.assertEqual(len(snapshot['errors']),5)
        self.assertEqual(len(pack(render(snapshot))),15000)
    def test_invalid_response_does_not_replace_cache(self):
        original=copy.deepcopy(FIXTURE['entries']);before=copy.deepcopy(original)
        snapshot=Client(cache=original,fetch=lambda *_:None).poll()
        self.assertEqual(snapshot['entries'],before);self.assertEqual(len(snapshot['errors']),5)
    def test_bad_cache_ignored(self):
        snapshot=Client(cache={'price':{'data':{'USD':0,'time':1},'fetched_at':1}},fetch=lambda *_:None).poll()
        self.assertNotIn('price',snapshot['entries'])
    def test_nonobject_cache_ignored(self):
        self.assertEqual(Client(cache=["broken"]).entries,{})
    def test_wall_clock_timeout_restores_handler(self):
        previous=signal.getsignal(signal.SIGALRM)
        with self.assertRaises(TimeoutError):
            with phase_limit(8):signal.raise_signal(signal.SIGALRM)
        self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
    def test_numeric_validation_rejects_nonfinite_negative_and_bool(self):
        for bad in (float('nan'),float('inf'),-1,True,'100'):
            with self.assertRaises(ValueError):validate('price',{'USD':bad,'time':1})
        with self.assertRaises(ValueError):validate('price',{'USD':0,'time':1})
    def test_fractional_fees_and_negative_difficulty_are_valid(self):
        validate('fees',dict(fastestFee=.5,halfHourFee=.3,hourFee=.1,minimumFee=.1))
        validate('difficulty',dict(remainingBlocks=100,progressPercent=95,difficultyChange=-9))
    def test_bad_block_order_is_rejected(self):
        blocks=copy.deepcopy(FIXTURE['entries']['blocks']['data']);blocks.reverse()
        with self.assertRaises(ValueError):validate('blocks',blocks)
    def test_expired_cache_marked_even_without_current_error(self):
        snapshot=copy.deepcopy(FIXTURE);snapshot['time']+=181
        self.assertTrue(all(cached(snapshot,n) for n in ENDPOINTS))
    def test_monochrome_preview_and_both_controller_planes(self):
        image=render(FIXTURE);self.assertEqual(image.mode,'1');self.assertEqual(image.size,(400,300))
        left,right=split_rows(pack(image));self.assertEqual((len(left),len(right)),(7500,7500))
        self.assertNotEqual(left,right);self.assertNotEqual(pack(image),b'\xff'*15000)
    def test_fixture_capture_has_no_network_or_display_access(self):
        with tempfile.TemporaryDirectory() as directory,patch('epaper_dashboard.bitcoin.fetch_json',side_effect=AssertionError('HTTP forbidden')),patch('epaper_dashboard.bitcoin.live_transport',side_effect=AssertionError('GPIO forbidden')),patch('epaper_dashboard.bitcoin.Panel',side_effect=AssertionError('panel forbidden')):
            main(['--fixture',str(Path(__file__).parent/'fixtures/bitcoin.json'),'--windows','1','--state-dir',directory])
            self.assertTrue((Path(directory)/'latest.png').exists())
            self.assertEqual((Path(directory)/'latest.frame.bin').stat().st_size,15000)
    def test_fixture_mock_one_bounded_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            main(['--mock','--fixture',str(Path(__file__).parent/'fixtures/bitcoin.json'),'--windows','1','--state-dir',directory])
            record=json.loads((Path(directory)/'latest.json').read_text())
            self.assertEqual(record['update_mode'],'initial-full');self.assertTrue(record['busy_active_observed'])
    def test_interval_cannot_accidentally_become_endurance_loop(self):
        with self.assertRaises(SystemExit):main(['--interval','0'])
