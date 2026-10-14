import re
import unittest
from pathlib import Path
from eink_driver.panel import Panel,LUT_PART,changed_bands,BusyTimeout
from eink_driver.transport import Budget,FakeClock,mock_transport
from eink_driver.config import Config
from tests.test_panel import commands

class PartialTest(unittest.TestCase):
    def make(self,swap=False):
        t=mock_transport(Config(spacing=0,busy_timeout=.1,swap_cs=swap),Budget(60,FakeClock()))
        p=Panel(t);p.init();p.write_frame(b'\xff'*15000);p.refresh();p.power_off()
        t.spi.writes.clear()
        return p,t
    def test_waveform_exact_pinned_reference(self):
        source=(Path(__file__).parents[1]/'eink_driver/upstream/GxEPD2_2IC_420_A03.cpp').read_text()
        table=source.split('LUTDefault_part[] PROGMEM =')[1].split('};')[0]
        table=re.sub(r'//[^\n]*','',table)
        self.assertEqual(bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]+)',table))[1:],LUT_PART)
    def test_changes_group_rows_and_skip_identical(self):
        a=b'\xff'*15000;b=bytearray(a)
        for y in (1,3,20,299):b[y*50]=0
        self.assertEqual(changed_bands(a,b),[(1,3),(20,20),(299,299)])
        p,t=self.make();r=p.update_changed(a,a)
        self.assertEqual(r['bands'],[]);self.assertEqual(t.spi.writes,[]);p.close()
    def test_full_buffer_upload_seam_and_no_full_waveform(self):
        for swap in (False,True):
            p,t=self.make(swap)
            a=b'\xff'*15000;b=bytearray(a)
            b[20*50+24]=0x12;b[20*50+25]=0x34
            r=p.update_changed(a,b)
            trace=commands(t)
            ram=[(target,bytes(data)) for target,c,data in trace if c==0x24]
            self.assertEqual(r['bands'],[(20,20)])
            self.assertEqual(ram,[(('cs2' if swap else 'cs1',),b'\xff'*(20*25+24)+b'\x12'+b'\xff'*(7500-20*25-25)),(('cs1' if swap else 'cs2',),b'\xff'*(20*25)+b'\x34'+b'\xff'*(7500-20*25-1))])
            self.assertTrue(all(bytes(d)==b'\x00\x00\x2b\x01' for _,c,d in trace if c==0x45))
            self.assertEqual([bytes(d) for _,c,d in trace if c==0x22],[b'\xc0',b'\x04'])
            p.close()
    def test_requires_baseline_and_invalid_frames(self):
        t=mock_transport(Config(),Budget(60,FakeClock()));p=Panel(t);p.init()
        with self.assertRaises(RuntimeError):p.update_changed(b'\xff'*15000,b'\0'*15000)
        with self.assertRaises(ValueError):changed_bands(b'',b'')
        p.close()
    def test_stalled_partial_no_retry_or_cleanup_commands(self):
        p,t=self.make();p.power_on();original=t.spi.writebytes2
        def send(data):
            original(data)
            if not t.gpio.values[25] and data==b'\x20':t.gpio.busy_values=iter([1]);t.gpio.last_busy=1
        t.spi.writebytes2=send
        b=bytearray(b'\xff'*15000);b[0]=0
        with self.assertRaises(BusyTimeout):p.update_changed(b'\xff'*15000,b)
        count=len(t.spi.writes)
        with self.assertRaises(RuntimeError):p.update_changed(b'\xff'*15000,b)
        p.close();self.assertEqual(len(t.spi.writes),count)

    def test_all_dirty_writes_then_full_window_and_one_activation(self):
        from eink_driver.panel import RAM_AREA
        p,t=self.make();old=b'\xff'*15000;frame=bytearray(old)
        for y in (0,100,299):frame[y*50+25]=0
        p.update_changed(old,frame);trace=commands(t)
        last_ram=max(i for i,(_,c,_) in enumerate(trace) if c==0x24)
        self.assertEqual([(targets,c,bytes(data)) for targets,c,data in trace[last_ram+1:last_ram+6]],
                         [(('cs1','cs2'),c,data) for c,data in RAM_AREA])
        self.assertEqual([bytes(data) for _,c,data in trace if c==0x22],[b'\xc0',b'\x04'])
        self.assertEqual(len([c for _,c,_ in trace if c==0x20]),2)
        self.assertEqual(p.refresh_count,2);p.close()
    def test_band_upload_fault_never_activates_or_retries(self):
        p,t=self.make();t.spi.fail_at=len(t.spi.writes)+30
        with self.assertRaises(OSError):p.update_changed(b'\xff'*15000,b'\0'*15000)
        count=len(t.spi.writes);p.close()
        self.assertEqual(len(t.spi.writes),count)
        self.assertNotIn(0x20,[c for _,c,_ in commands(t)])
