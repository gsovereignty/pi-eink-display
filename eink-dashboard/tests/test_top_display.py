import unittest
from unittest.mock import patch
from pathlib import Path
from epaper_dashboard.app import parse_top,average_window,render,memory_mib,TopSampler
from eink_driver.images import pack,split_rows

FRAME='''top - 10:00:00 up 1 day, 1 user, load average: 0.10, 0.20, 0.30
Tasks: 3 total, 1 running, 2 sleeping, 0 stopped, 0 zombie
%Cpu(s): 10.0 us, 5.0 sy, 0.0 ni, 85.0 id, 0.0 wa, 0.0 hi, 0.0 si, 0.0 st
MiB Mem : 8000.0 total, 6000.0 free, 1000.0 used, 1000.0 buff/cache
MiB Swap: 2000.0 total, 1900.0 free, 100.0 used. 6000.0 avail Mem

PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
100 gareth 20 0 100.0m 80.0m 5.0m R 40.0 1.0 0:00.10 worker process
200 root 20 0 100.0m 40.0m 5.0m S 20.0 0.5 0:00.10 other
'''

class TopDisplayTest(unittest.TestCase):
    def sample(self,text=FRAME,birth=lambda pid:'123'):
        return parse_top(text,birth)
    def test_parser_actual_top_columns_and_command_spaces(self):
        s=self.sample()
        self.assertEqual(s['processes'][(100,'123')]['command'],'worker process')
        self.assertEqual(s['memory']['used'],1000)
        self.assertEqual(s['cpu']['id'],85)
        self.assertEqual(s['processes'][(100,'123')]['rss_mib'],80)
        self.assertEqual(s['load'],[0.1,0.2,0.3])
    def test_weighted_cpu_and_memory_average(self):
        a=self.sample();b=self.sample(FRAME.replace('40.0 1.0','80.0 1.0').replace('1000.0 used','2000.0 used'))
        r=average_window([(3,a),(7,b)])
        self.assertEqual(r['processes'][0]['cpu'],68)
        self.assertEqual(r['memory']['used'],1700)
        self.assertEqual(r['window_seconds'],10)
    def test_pid_reuse_and_new_process_zero_before_birth(self):
        a=self.sample(birth=lambda pid:'old');b=self.sample(birth=lambda pid:'new')
        r=average_window([(9,a),(1,b)])
        self.assertEqual(r['processes'][0]['cpu'],4)
        self.assertEqual(r['processes'][0]['rss_mib'],8)
    def test_exited_process_omitted_from_current_top_view(self):
        a=self.sample();b=self.sample();del b['processes'][(100,'123')]
        self.assertEqual([p['pid'] for p in average_window([(5,a),(5,b)])['processes']],[200])
    def test_invalid_columns_or_summary_stops(self):
        for text in (FRAME.replace('PID USER PR','PID USER BAD'),FRAME.replace('0.0 st','missing')):
            with self.assertRaises(ValueError):self.sample(text)
    def test_memory_units_and_invalid_duration(self):
        self.assertEqual(memory_mib('1.5g'),1536)
        self.assertEqual(memory_mib('1024'),1)
        with self.assertRaises(ValueError):average_window([(0,self.sample())])
    def test_readable_framebuffer_and_half_streams(self):
        r=average_window([(1,self.sample())]*10)
        image=render(r,1)
        self.assertEqual(image.size,(400,300))
        frame=pack(image)
        self.assertEqual(len(frame),15000)
        self.assertEqual([len(p) for p in split_rows(frame)],[7500,7500])
        self.assertNotEqual(frame,b'\xff'*15000)
    def test_sampler_discards_boot_frame_and_publishes_ten_intervals(self):
        class Source:
            def __init__(self,home):pass
            def frames(self):
                yield 0,FRAME.replace('40.0 1.0','999.0 1.0')
                for t in range(1,11):yield float(t),FRAME
            def close(self):pass
        with patch('epaper_dashboard.app.process_birth',return_value='123'):
            sampler=TopSampler(Path('.'),Source)
            received,text,r,sequence=next(sampler.windows())
            sampler.close()
        self.assertEqual(sequence,1)
        self.assertEqual(r['sample_count'],10)
        self.assertEqual(r['window_seconds'],10)
        self.assertEqual(r['processes'][0]['cpu'],40)
    def test_sampler_propagates_child_error(self):
        class Source:
            def __init__(self,home):pass
            def frames(self):raise RuntimeError('child failed');yield
            def close(self):pass
        sampler=TopSampler(Path('.'),Source)
        with self.assertRaisesRegex(RuntimeError,'child failed'):next(sampler.windows())
        sampler.close()

    def test_last_ten_seconds_excludes_older_sample_fraction(self):
        a=self.sample();b=self.sample(FRAME.replace('40.0 1.0','80.0 1.0'))
        result=average_window([(6,a),(6,b)])
        self.assertEqual(result['window_seconds'],10)
        self.assertEqual(result['sample_span_seconds'],12)
        self.assertEqual(result['processes'][0]['cpu'],64)

    def test_short_startup_and_later_jitter_keep_full_window(self):
        class Source:
            def __init__(self,home):pass
            def frames(self):
                yield 0,FRAME
                for t in range(1,22):yield t*0.98,FRAME
            def close(self):pass
        sampler=TopSampler(Path('.'),Source)
        windows=sampler.windows()
        first=next(windows);second=next(windows);sampler.close()
        self.assertAlmostEqual(first[0],10.78)
        self.assertAlmostEqual(second[0]-first[0],9.8)
        for record in (first,second):
            self.assertAlmostEqual(record[2]['window_seconds'],10)
            self.assertEqual(record[2]['sample_count'],11)
