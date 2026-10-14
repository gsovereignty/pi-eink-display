import unittest
from unittest.mock import Mock
from epaper_dashboard.app import display_update
from eink_driver.panel import Panel
from eink_driver.transport import Budget,FakeClock,mock_transport
from eink_driver.config import Config
from tests.test_panel import commands

class ClearCycleTest(unittest.TestCase):
    def test_three_full_frames_black_white_then_dashboard(self):
        t=mock_transport(Config(spacing=0),Budget(60,FakeClock()));p=Panel(t);p.init()
        frame=bytes(range(250))*60
        r,mode=display_update(p,frame,frame,'black-white')
        ram=[bytes(data) for _,cmd,data in commands(t) if cmd==0x24]
        self.assertEqual(ram[:2],[b'\0'*7500]*2)
        self.assertEqual(ram[2:4],[b'\xff'*7500]*2)
        self.assertEqual(p.refresh_count,3)
        self.assertEqual([s['name'] for s in r['stages']],['black','white','dashboard'])
        self.assertEqual(mode,'black-white-full');self.assertFalse(p.powered)
        self.assertEqual([bytes(data) for _,cmd,data in commands(t) if cmd==0x22].count(b'\xc4'),3)
        p.close()
    def test_failed_black_refresh_never_sends_white_or_dashboard(self):
        p=Mock();p.refresh.side_effect=TimeoutError('stalled')
        with self.assertRaises(TimeoutError):display_update(p,b'\xff'*15000,None,'black-white')
        p.write_frame.assert_called_once_with(b'\0'*15000)
        p.refresh.assert_called_once();p.power_off.assert_not_called()
    def test_off_keeps_existing_partial_behavior(self):
        p=Mock();p.update_changed.return_value={'duration_seconds':1,'active_observed':True}
        _,mode=display_update(p,b'a',b'b','off')
        p.update_changed.assert_called_once_with(b'b',b'a');p.refresh.assert_not_called()
        self.assertEqual(mode,'partial-full-buffer')

    def test_full_mode_one_dashboard_refresh_per_update(self):
        p=Mock();p.refresh.return_value={'duration_seconds':1.6,'active_observed':True}
        frame=b'\xa5'*15000
        for previous in (None,frame):
            _,mode=display_update(p,frame,previous,'full')
            self.assertEqual(mode,'full')
        self.assertEqual(p.write_frame.call_count,2)
        self.assertTrue(all(call.args==(frame,) for call in p.write_frame.call_args_list))
        self.assertEqual(p.refresh.call_count,2)
        self.assertEqual(p.power_off.call_count,2)
        p.update_changed.assert_not_called()
    def test_full_mode_stall_does_not_send_clearing_images(self):
        p=Mock();p.refresh.side_effect=TimeoutError('stalled')
        frame=b'\xa5'*15000
        with self.assertRaises(TimeoutError):display_update(p,frame,None,'full')
        p.write_frame.assert_called_once_with(frame)
        p.refresh.assert_called_once();p.power_off.assert_not_called()
