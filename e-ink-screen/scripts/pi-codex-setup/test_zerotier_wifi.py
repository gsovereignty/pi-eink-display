import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('wifi',Path(__file__).with_name('zerotier-wifi.py'))
wifi=importlib.util.module_from_spec(spec);spec.loader.exec_module(wifi)
class WifiTest(unittest.TestCase):
    def test_ignores_wireguard_and_overlay_routes(self):
        routes=[{'dst':'default','gateway':'192.168.50.1','dev':'wlan0','prefsrc':'192.168.50.191','metric':600}, {'dst':'192.168.50.0/24','dev':'wlan0','scope':'link'}, {'dst':'162.159.140.245','dev':'ivpn-openai'}, {'dst':'10.46.107.0/24','dev':'zt123'}]
        commands=wifi.route_commands(routes,'-4')
        self.assertEqual(len(commands),4)
        self.assertTrue(all('ivpn-openai' not in c and 'zt123' not in c for c in commands))
        self.assertIn('unreachable',commands[1]);self.assertIn('default',commands[2])
    def test_wifi_absent_is_unreachable_not_main_fallback(self):
        commands=wifi.route_commands([],'-6')
        self.assertEqual(len(commands),2);self.assertIn('unreachable',commands[1])
    def test_rules_cover_service_sockets_not_port_guesses(self):
        rules=wifi.ruleset()
        self.assertIn('socket cgroupv2 level 2 "system.slice/zerotier-one.service"',rules)
        self.assertIn('type route hook output',rules)
        self.assertIn('type filter hook postrouting',rules)
        self.assertIn('oifname != { "wlan0", "lo" } counter drop',rules)
        self.assertNotIn('9993',rules)
if __name__=='__main__':unittest.main()
