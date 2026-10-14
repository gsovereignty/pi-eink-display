import sys
import unittest
from unittest.mock import Mock,patch
from eink_driver.config import Config
from eink_driver.preflight import inventory


class PreflightTest(unittest.TestCase):
    def test_busy_sample_claims_input_only_and_releases(self):
        gpio=Mock();gpio.gpiochip_open.return_value=22
        gpio.gpio_get_line_info.side_effect=lambda h,n:[6,n,65536,f"GPIO{n}",""]
        gpio.gpio_read.return_value=1
        with patch.dict(sys.modules,{"lgpio":gpio}), \
             patch("eink_driver.preflight.discover_chip",return_value=(6,"/dev/gpiochip6","pinctrl-rp1")), \
             patch("eink_driver.preflight.command",return_value={}),patch("eink_driver.preflight.time.sleep"):
            result=inventory(Config(),sample_busy=True)
        self.assertEqual(result["busy_samples"],[1]*20)
        gpio.gpio_claim_input.assert_called_once_with(22,24)
        gpio.gpio_claim_output.assert_not_called()
        gpio.gpio_write.assert_not_called()
        gpio.gpio_free.assert_called_once_with(22,24)
        self.assertEqual(gpio.gpiochip_close.call_count,2)

    def test_busy_read_error_still_releases_input(self):
        gpio=Mock();gpio.gpiochip_open.return_value=22
        gpio.gpio_get_line_info.side_effect=lambda h,n:[6,n,65536,f"GPIO{n}",""]
        gpio.gpio_read.side_effect=OSError("Injected read error")
        with patch.dict(sys.modules,{"lgpio":gpio}), \
             patch("eink_driver.preflight.discover_chip",return_value=(6,"/dev/gpiochip6","pinctrl-rp1")), \
             patch("eink_driver.preflight.command",return_value={}):
            result=inventory(Config(),sample_busy=True)
        self.assertEqual(result["checks"]["gpio_access"],"FAIL")
        gpio.gpio_free.assert_called_once_with(22,24)
        gpio.gpio_write.assert_not_called()
        self.assertEqual(gpio.gpiochip_close.call_count,2)
