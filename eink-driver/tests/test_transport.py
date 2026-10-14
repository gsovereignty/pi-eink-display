import unittest
from unittest.mock import Mock, patch
import sys
from eink_driver.config import Config, PINS, HEADER
from eink_driver.transport import Budget, DeadlineExceeded, FakeClock, LGPIO, discover_chip, live_transport, mock_transport


class TransportTest(unittest.TestCase):
    def make(self, seconds=10):
        return mock_transport(Config(), Budget(seconds, FakeClock()))

    def test_bcm_header_and_busy_input(self):
        self.assertEqual(PINS, {"mosi":10,"clock":11,"reset":17,"dc":25,"cs1":8,"cs2":7,"busy":24})
        self.assertEqual(HEADER["busy"], 18)
        t=self.make()
        self.assertEqual(t.gpio.claims[24], "input")
        self.assertEqual(set(t.gpio.claims), {7,8,17,24,25})
        with self.assertRaises(RuntimeError): t.gpio.write(24, 1)
        t.close()
        self.assertFalse(any(pin==24 for _,pin,_ in t.gpio.events))

    def test_independent_and_simultaneous_selects_dc(self):
        t=self.make()
        t.write(("cs1",), False, b"\x24")
        t.write(("cs1",), True, b"\xaa")
        t.write(("cs2",), True, b"\x55")
        t.write(("cs1","cs2"), False, b"\x01")
        self.assertEqual(t.spi.writes, [(("cs1",),0,b"\x24"),(("cs1",),1,b"\xaa"),
                                      (("cs2",),1,b"\x55"),(("cs1","cs2"),0,b"\x01")])
        self.assertEqual(t.gpio.values[7],1); self.assertEqual(t.gpio.values[8],1)
        events=t.gpio.events
        dc_events=[(i,ts) for i,(ts,pin,value) in enumerate(events) if pin==25]
        for i,ts in dc_events:
            following=[event for event in events[i+1:] if event[1] in (7,8) and event[2]==0]
            self.assertGreaterEqual(following[0][0]-ts, 0.000009)

    def test_reset_timing(self):
        t=self.make(); t.reset()
        edges=[(round(ts,3),value) for ts,pin,value in t.gpio.events if pin==17]
        self.assertEqual(edges,[(0.0,1),(0.01,0),(0.02,1)])
        self.assertAlmostEqual(t.budget.clock.now(),0.03)

    def test_exception_deassert_and_close(self):
        t=self.make(); t.spi.fail_at=0
        with self.assertRaises(OSError): t.write(("cs1","cs2"),True,b"123")
        self.assertEqual(t.gpio.values[7],1); self.assertEqual(t.gpio.values[8],1)
        t.close(); t.close()
        self.assertTrue(t.spi.closed and t.gpio.closed)

    def test_deadline_cleanup_still_works(self):
        t=self.make(0.001); t.budget.clock.sleep(0.002)
        with self.assertRaises(DeadlineExceeded): t.write(("cs1",),False,b"\x20")
        t.close(); self.assertTrue(t.closed)
        self.assertEqual(t.spi.writes,[])

    def test_busy_real_claim_is_input(self):
        m=Mock(); g=LGPIO(m,100); g.claim(); g.close()
        m.gpio_claim_input.assert_called_once_with(100,24)
        self.assertEqual([c.args[1] for c in m.gpio_claim_output.call_args_list],[8,7,25,17])
        self.assertEqual([c.args[2] for c in m.gpio_claim_output.call_args_list],[1,1,0,1])

    def test_chip_discovery_no_fixed_index_and_symlink_dedup(self):
        m=Mock(); m.gpiochip_open.side_effect=lambda n:n
        m.gpio_get_chip_info.side_effect=lambda h:(h,54,"gpiochip", "pinctrl-rp1" if h==6 else "other")
        m.gpio_get_line_info.side_effect=lambda h,n:(h,n,0,f"GPIO{n}","")
        with patch("eink_driver.transport.glob.glob",return_value=["/dev/gpiochip6","/dev/gpiochip4","/dev/gpiochip1"]), \
             patch("eink_driver.transport.os.path.realpath",side_effect=lambda p:p.replace("chip4","chip6")):
            self.assertEqual(discover_chip(m)[0],6)
        self.assertEqual(m.gpiochip_open.call_count,2)

    def test_config_refuses_unvalidated_parameters(self):
        for c in (Config(speed_hz=8_000_000),Config(busy_active=0),Config(spacing=-1),Config(reset_seconds=0.1)):
            with self.assertRaises(ValueError):c.validate()

    def test_kernel_owned_cs_blocks_spi_open_and_claims(self):
        gpio=Mock();gpio.gpiochip_open.return_value=20
        gpio.gpio_get_line_info.side_effect=lambda h,n:[6,n,1,f"GPIO{n}","spi0"]
        spi=Mock();device=spi.SpiDev.return_value
        with patch.dict(sys.modules,{"lgpio":gpio,"spidev":spi}), \
             patch("eink_driver.transport.discover_chip",return_value=(6,"/dev/gpiochip6","pinctrl-rp1")):
            with self.assertRaisesRegex(RuntimeError,"owned"):
                live_transport(Config(),Budget(10,FakeClock()))
        gpio.gpio_claim_output.assert_not_called()
        device.open_path.assert_not_called()
        gpio.gpiochip_close.assert_called_once_with(20)

    def test_deassert_failure_still_attempts_other_cs_and_closes(self):
        t=self.make();original=t.gpio.write
        def failed(pin,value):
            if pin==8:raise OSError("Injected GPIO failure")
            original(pin,value)
        t.gpio.write=failed
        with self.assertRaisesRegex(RuntimeError,"Cleanup errors"):
            t.close()
        self.assertTrue(t.gpio.closed and t.spi.closed)
        self.assertEqual(t.gpio.events[-1][1:],(7,1))

    def test_spidev_36_open_fallback_and_cleanup(self):
        gpio=Mock();gpio.gpiochip_open.return_value=20
        gpio.gpio_get_line_info.side_effect=lambda h,n:[0,n,65536,f"GPIO{n}",""]
        device=Mock(spec=["open","close","writebytes2","no_cs","mode","max_speed_hz","bits_per_word","lsbfirst"])
        spi=Mock();spi.SpiDev.return_value=device
        with patch.dict(sys.modules,{"lgpio":gpio,"spidev":spi}), \
             patch("eink_driver.transport.discover_chip",return_value=(0,"/dev/gpiochip0","pinctrl-rp1")):
            t=live_transport(Config(),Budget(10,FakeClock()))
            device.open.assert_called_once_with(0,0)
            self.assertTrue(device.no_cs)
            self.assertEqual(device.mode,0)
            self.assertEqual(device.max_speed_hz,100000)
            t.close()
        device.close.assert_called_once()
        gpio.gpio_claim_input.assert_called_once_with(20,24)
        self.assertEqual(gpio.gpio_free.call_count,5)

    def test_no_cs_einval_requires_routing_evidence(self):
        import errno
        from unittest.mock import PropertyMock
        gpio=Mock();gpio.gpiochip_open.return_value=20
        gpio.gpio_get_line_info.side_effect=lambda h,n:[0,n,65536,f"GPIO{n}",""]
        device=Mock();spi=Mock();spi.SpiDev.return_value=device
        with patch.dict(sys.modules,{"lgpio":gpio,"spidev":spi}), \
             patch("eink_driver.transport.discover_chip",return_value=(0,"/dev/gpiochip0","pinctrl-rp1")), \
             patch.object(type(device),"no_cs",new_callable=PropertyMock,create=True) as no_cs, \
             patch("eink_driver.transport.verify_unrouted_kernel_cs") as verify:
            no_cs.side_effect=OSError(errno.EINVAL,"unsupported")
            verify.side_effect=RuntimeError("Kernel CS GPIO routing is not empty")
            with self.assertRaisesRegex(RuntimeError,"routing"):
                live_transport(Config(),Budget(10,FakeClock()))
            verify.assert_called_once_with("/dev/spidev0.0")
            device.close.assert_called_once()
            self.assertEqual(gpio.gpio_free.call_count,5)
