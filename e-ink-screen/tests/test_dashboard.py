import unittest
from hink_diag.dashboard import cpu_counters,net_counters,disk_counters,counter_rates,average_resources,Dashboard
from hink_diag.top_display import average_window,parse_top
from hink_diag.images import pack,split_rows
from tests.test_top_display import FRAME

class DashboardTest(unittest.TestCase):
    def resources(self,value):
        return dict(cores={'cpu0':value},network={'wlan0':[value,value*2]},disk_rates=[value*3,value*4],disk_device='mmcblk0',temperature_c=42,uptime_seconds=12345,disk_free_bytes=10*1024**3,disk_total_bytes=30*1024**3,wifi_dbm={'wlan0':-41},throttled=0)
    def test_cpu_guest_not_counted_twice_and_net_no_loopback(self):
        self.assertEqual(cpu_counters('cpu0 10 2 3 80 5 1 1 0 10 2\ncpu 1 2'),{'cpu0':(102,85)})
        row='1 0 0 0 0 0 0 0 2 0 0 0 0 0 0 0'
        self.assertEqual(net_counters('lo: '+row+'\nwlan0: '+row),{'wlan0':(1,2)})
    def test_physical_disk_only_and_512_byte_sectors(self):
        text='179 0 mmcblk0 1 0 4 0 2 0 8 0 0 0 0\n179 2 mmcblk0p2 1 0 4 0 2 0 8 0 0 0 0'
        self.assertEqual(disk_counters(text,'mmcblk0'),(2048,4096))
        self.assertIsNone(disk_counters(text,'missing'))
    def test_rates_reset_unavailable_and_duration(self):
        self.assertEqual(counter_rates((100,300),(200,500),2),[50,100])
        self.assertIsNone(counter_rates((200,0),(100,1),1))
        self.assertIsNone(counter_rates(None,(100,1),1))
    def test_resources_weighted_with_full_window_clipping(self):
        a=parse_top(FRAME);a['resources']=self.resources(10)
        b=parse_top(FRAME);b['resources']=self.resources(20)
        r=average_window([(6,a),(6,b)])['resources']
        self.assertEqual(r['cores']['cpu0'],16)
        self.assertEqual(r['network']['wlan0'],[16,32])
        self.assertEqual(r['disk_rates'],[48,64])
        a['resources']['disk_rates']=None
        self.assertEqual(average_window([(5,a),(5,b)])['resources']['disk_rates'],[None,None])
    def test_dashboard_frame_packing_and_real_time_history(self):
        s=average_window([(10,parse_top(FRAME))]);s['resources']=self.resources(20)
        dashboard=Dashboard()
        for t in range(0,411,10):image=dashboard.render(s,t,t)
        self.assertEqual(image.size,(400,300));self.assertEqual(image.mode,'1')
        self.assertEqual(len(dashboard.history),31);self.assertEqual(dashboard.history[0][0],110)
        frame=pack(image);self.assertEqual(len(frame),15000);self.assertEqual([len(p) for p in split_rows(frame)],[7500,7500])
        self.assertNotEqual(frame,b'\xff'*15000)
    def test_unavailable_metrics_render_without_invented_values(self):
        s=average_window([(10,parse_top(FRAME))]);image=Dashboard().render(s,1,1)
        self.assertEqual(image.size,(400,300))

    def test_network_minute_clips_old_interval_and_warmup(self):
        from hink_diag.dashboard import NetworkMinute
        n=NetworkMinute()
        rates,span=n.sample(0,{'wlan0':(1000,2000)})
        self.assertEqual(span,0);self.assertEqual(rates['wlan0'],[None,None])
        rates,span=n.sample(10,{'wlan0':(1100,2200)})
        self.assertEqual(span,10);self.assertEqual(rates['wlan0'],[600,1200])
        n.sample(60,{'wlan0':(2100,4200)})
        rates,span=n.sample(65,{'wlan0':(2150,4300)})
        self.assertEqual(span,60)
        self.assertEqual(rates['wlan0'],[1100,2200])
    def test_network_reset_and_interface_creation_do_not_fake_rates(self):
        from hink_diag.dashboard import NetworkMinute
        n=NetworkMinute();n.sample(0,{'wlan0':(100,100)})
        rates,_=n.sample(1,{'wlan0':(1,1),'eth0':(99,99)})
        self.assertEqual(rates['wlan0'],[None,None]);self.assertEqual(rates['eth0'],[None,None])
        rates,span=n.sample(62,{'wlan0':(62,62),'eth0':(160,160)})
        self.assertEqual(span,60);self.assertEqual(rates['wlan0'],[60,60])
    def test_addresses_ipv4_ipv6_and_no_loopback(self):
        from hink_diag.dashboard import ip_addresses
        records=[{'ifname':'lo','addr_info':[{'family':'inet','local':'127.0.0.1'}]},
                 {'ifname':'wlan0','addr_info':[{'family':'inet6','local':'fe80::1','scope':'link'},{'family':'inet','local':'192.168.50.191'}]}]
        self.assertEqual([x['address'] for x in ip_addresses(records)],['192.168.50.191','fe80::1'])
    def test_latest_network_totals_not_averaged_across_window(self):
        a=parse_top(FRAME);a['resources']=self.resources(10);a['resources']['network_since_boot']={'wlan0':(100,200)}
        b=parse_top(FRAME);b['resources']=self.resources(20);b['resources']['network_since_boot']={'wlan0':(300,600)}
        self.assertEqual(average_window([(5,a),(5,b)])['resources']['network_since_boot'],{'wlan0':(300,600)})
