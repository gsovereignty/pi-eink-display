import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hink_diag.cli import main
from hink_diag.config import Config
from hink_diag.transport import mock_transport


class BenchmarkTest(unittest.TestCase):
    def test_reference_speed_limit(self):
        Config(speed_hz=4_000_000).validate()
        with self.assertRaises(ValueError):Config(speed_hz=4_000_001).validate()

    def test_three_frames_one_power_cycle_and_rate(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(['benchmark','--mock','--spacing','0','--speed-hz','4000000','--runs',d,'--run-id','burst']),0)
            r=json.loads((Path(d)/'burst/result.json').read_text())
            self.assertEqual(r['refresh_count'],3)
            self.assertTrue(all(s['status']=='PASS' for s in r['steps']))
            intervals=(r['steps'][-1]['completion_monotonic_seconds']-r['steps'][0]['completion_monotonic_seconds'])/2
            self.assertAlmostEqual(r['benchmark']['observed_full_frame_rate_hz'],1/intervals)
            events=[json.loads(s) for s in (Path(d)/'burst/events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(e['event']=='busy_wait' and e.get('label')=='power_on' for e in events),1)
            self.assertEqual(sum(e['event']=='busy_wait' and e.get('label')=='power_off' for e in events),1)
            self.assertEqual((Path(d)/'burst/patterns/burst-2.frame.bin').stat().st_size,15000)
            a=(Path(d)/'burst/patterns/burst-1.frame.bin').read_bytes()
            b=(Path(d)/'burst/patterns/burst-2.frame.bin').read_bytes()
            self.assertNotEqual(a,b)
            self.assertTrue(events[-1]['normal_sleep'])
            self.assertTrue((Path(d)/'burst/benchmark.csv').exists())

    def test_burst_failure_has_no_later_refresh(self):
        def transport(c,b,e):
            t=mock_transport(c,b,e)
            original=t.spi.writebytes2
            refreshes=0
            armed=False
            def send(data):
                nonlocal refreshes,armed
                if refreshes==1 and t.gpio.values[25] and len(data)>100:
                    raise OSError('Second framebuffer fault')
                if not t.gpio.values[25] and bytes(data)==b'\x22':armed=True
                elif armed and t.gpio.values[25]:
                    if bytes(data)==b'\xc4':refreshes+=1
                    armed=False
                original(data)
            t.spi.writebytes2=send
            return t
        with tempfile.TemporaryDirectory() as d,patch('hink_diag.cli.mock_transport',side_effect=transport):
            self.assertEqual(main(['benchmark','--mock','--spacing','0','--runs',d,'--run-id','failed']),1)
            r=json.loads((Path(d)/'failed/result.json').read_text())
            self.assertEqual(r['refresh_count'],1)
            self.assertEqual(r['steps'][2]['status'],'NOT RUN')
            self.assertNotIn('benchmark',r)

    def test_burst_dry_run_and_gate_never_open_transport(self):
        with tempfile.TemporaryDirectory() as d,patch('hink_diag.cli.live_transport') as live:
            self.assertEqual(main(['benchmark','--spacing','0','--runs',d,'--run-id','dry']),0)
            self.assertEqual(main(['benchmark','--hardware','--spacing','0','--runs',d,'--run-id','blocked']),2)
            live.assert_not_called()
