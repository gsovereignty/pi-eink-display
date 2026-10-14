import unittest
from eink_driver.config import Config
from eink_driver.images import pack,pattern
from eink_driver.panel import BusyNotObserved,BusyTimeout,INIT,LUT_FULL,Panel
from eink_driver.transport import Budget,DeadlineExceeded,FakeClock,mock_transport


def commands(transport):
    result=[]
    for targets,dc,payload in transport.spi.writes:
        if not dc:result.append([targets,payload[0],bytearray()])
        else:result[-1][2].extend(payload)
    return result


class PanelTest(unittest.TestCase):
    def make(self, config=None,busy=None):
        c=config or Config(busy_timeout=0.1)
        t=mock_transport(c,Budget(c.deadline,FakeClock()),busy_values=busy)
        return Panel(t),t

    def test_init_does_not_enable_booster_or_refresh(self):
        p,t=self.make();p.init()
        trace=commands(t)
        self.assertNotIn(0x20,[x[1] for x in trace])
        self.assertEqual([(c,bytes(d)) for _,c,d in trace[:5]],list(INIT))
        self.assertEqual(bytes(trace[-1][2]),LUT_FULL)
        self.assertEqual(len(LUT_FULL),30)
        p.close();self.assertFalse(p.powered)

    def test_full_frame_distribution_and_select_swap(self):
        for swap in (False,True):
            p,t=self.make(Config(swap_cs=swap));p.init()
            p.write_frame(pack(pattern('halves','ID')))
            planes=[(target,bytes(data)) for target,c,data in commands(t) if c==0x24]
            self.assertEqual(planes,[(('cs2' if swap else 'cs1',),b'\0'*7500),
                                     (('cs1' if swap else 'cs2',),b'\xff'*7500)])
            p.close()

    def test_busy_transitions_spacing_sleep_wake(self):
        p,t=self.make();p.init();p.write_frame(b'\xff'*15000)
        p.refresh();first=p.last_refresh;p.power_off();p.sleep();p.init()
        p.write_frame(b'\0'*15000);p.refresh()
        self.assertGreaterEqual(p.last_refresh-first,180)
        refresh=[r for r in p.busy_records if r['label']=='full_refresh']
        self.assertEqual(len(refresh),2)
        self.assertTrue(all(r['active_observed'] for r in refresh))
        self.assertTrue(all([t['level'] for t in r['transitions']]==[1,0] for r in refresh))
        p.close();self.assertEqual(p.refresh_count,2)

    def test_stuck_high_before_init_aborts_without_any_command(self):
        p,t=self.make(busy=[1])
        with self.assertRaises(BusyTimeout):p.init()
        p.close()
        self.assertEqual(t.spi.writes,[])
        self.assertTrue(t.closed)

    def test_stuck_low_during_refresh_no_further_commands(self):
        p,t=self.make();p.init();p.power_on()
        t.gpio.busy_values=iter([0]);t.gpio.last_busy=0
        with self.assertRaises(BusyNotObserved):p.refresh()
        count=len(t.spi.writes)
        with self.assertRaises(RuntimeError):p.refresh()
        p.close()
        self.assertEqual(len(t.spi.writes),count)
        self.assertEqual(commands(t)[-1][1],0x20)

    def test_stuck_high_refresh_no_sleep_into_busy(self):
        p,t=self.make();p.init();p.power_on()
        # All commands see ready; active becomes stuck immediately after final 0x20.
        original=t.spi.writebytes2
        def send(data):
            original(data)
            if not t.gpio.values[25] and data==b'\x20':
                t.gpio.busy_values=iter([1]);t.gpio.last_busy=1
        t.spi.writebytes2=send
        with self.assertRaises(BusyTimeout):p.refresh()
        count=len(t.spi.writes);p.close()
        self.assertEqual(len(t.spi.writes),count)
        self.assertNotIn(0x10,[x[1] for x in commands(t)])

    def test_exception_during_ram_does_not_trigger_refresh_or_cleanup_command(self):
        p,t=self.make();p.init();t.spi.fail_at=len(t.spi.writes)+3
        with self.assertRaises(OSError):p.write_frame(b'\xff'*15000)
        count=len(t.spi.writes);p.close()
        self.assertEqual(len(t.spi.writes),count)
        self.assertEqual(p.refresh_count,0)
        self.assertTrue(t.gpio.closed and t.spi.closed)

    def test_interrupt_reset_and_cleanup(self):
        p,t=self.make();original=t.budget.sleep
        def interrupted(seconds):
            if t.gpio.values[17]==0:raise KeyboardInterrupt()
            original(seconds)
        t.budget.sleep=interrupted
        with self.assertRaises(KeyboardInterrupt):p.init()
        p.close()
        self.assertEqual(t.spi.writes,[])
        self.assertTrue(t.closed)

    def test_overall_timeout_during_spacing_no_second_refresh(self):
        p,t=self.make(Config(deadline=100));p.init();p.refresh();p.power_off()
        with self.assertRaises(DeadlineExceeded):p.refresh()
        p.abort();count=len(t.spi.writes);p.close()
        self.assertEqual(p.refresh_count,1);self.assertEqual(count,len(t.spi.writes))

    def test_no_otp_or_unknown_commands(self):
        p,t=self.make();p.init()
        for cmd in (0x2a,0x28,0x30,0x31,0x39):
            with self.assertRaises(ValueError):p.command(cmd)
        p.close()
