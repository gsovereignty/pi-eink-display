"""Continuous real top output: ten one-second samples per e-paper update."""
import argparse
from collections import deque
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import queue
import threading
import selectors
import signal
import subprocess
import time
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from .artifacts import code_version, save_json, timestamp
from eink_driver.config import Config
from eink_driver.images import pack, split_rows
from .dashboard import Dashboard, LinuxResources, average_resources
from eink_driver.panel import Panel
from eink_driver.preflight import inventory
from eink_driver.transport import Budget, live_transport, mock_transport


CPU_FIELDS = ('us', 'sy', 'ni', 'id', 'wa', 'hi', 'si', 'st')


def memory_mib(value):
    match = re.fullmatch(r'([\d.]+)([kmgt]?)', value.lower())
    if not match:
        raise ValueError(f'Invalid top memory value: {value}')
    return float(match[1]) * {'':1/1024, 'k':1/1024, 'm':1, 'g':1024, 't':1048576}[match[2]]


def process_birth(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        return text[text.rfind(')')+2:].split()[19]  # field 22, after pid/comm
    except (OSError, IndexError):
        return None


def parse_top(text, birth=process_birth):
    lines = text.splitlines()
    cpu_line = next(line for line in lines if line.startswith('%Cpu'))
    cpu = {key:float(value) for value,key in re.findall(r'([\d.]+)\s+(us|sy|ni|id|wa|hi|si|st)\b', cpu_line)}
    if set(cpu) != set(CPU_FIELDS):
        raise ValueError('Incomplete top CPU summary')
    mem_line = next(line for line in lines if line.startswith('MiB Mem'))
    swap_line = next(line for line in lines if line.startswith('MiB Swap'))
    mem = {key:float(value) for value,key in re.findall(r'([\d.]+)\s+(total|free|used|buff/cache)',mem_line)}
    swap_used = float(re.search(r'([\d.]+)\s+used',swap_line)[1])
    tasks = int(re.search(r'Tasks:\s*(\d+)',text)[1])
    load = [float(x) for x in re.search(r'load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)',text).groups()]
    header = next(i for i,line in enumerate(lines) if line.split() and line.split()[0]=='PID')
    fields = lines[header].split()
    expected = ['PID','USER','PR','NI','VIRT','RES','SHR','S','%CPU','%MEM','TIME+','COMMAND']
    if fields != expected:
        raise ValueError(f'Unexpected top columns: {fields}')
    processes = {}
    for line in lines[header+1:]:
        if not line.strip():
            continue
        parts = line.split(None,11)
        if len(parts)!=12:
            raise ValueError(f'Incomplete top process row: {line}')
        pid = int(parts[0]); start = birth(pid)
        key = (pid, start if start is not None else (parts[1],parts[11]))
        processes[key] = {'pid':pid,'user':parts[1],'command':parts[11],
                          'cpu':float(parts[8]),'mem':float(parts[9]),'rss_mib':memory_mib(parts[5])}
    return {'cpu':cpu,'memory':mem,'swap_used_mib':swap_used,'tasks':tasks,'load':load,'processes':processes}


def average_window(samples):
    """Time-weighted intervals; absent processes contribute zero over the window."""
    span = sum(weight for weight,_ in samples)
    if span<=0 or any(weight<=0 for weight,_ in samples):
        raise ValueError('Sample durations must be positive')
    # top's scheduling has small jitter: clip the oldest interval so values
    # describe the last 10.000 seconds rather than ten slightly-longer samples.
    remaining=min(10.0,span);clipped=[]
    for weight,snapshot in reversed(samples):
        included=min(weight,remaining)
        if included>0:clipped.append((included,snapshot))
        remaining-=included
        if remaining<=0:break
    samples=list(reversed(clipped));duration=sum(weight for weight,_ in samples)
    latest = samples[-1][1]
    result = {'window_seconds':duration, 'sample_span_seconds':span, 'sample_count':len(samples), 'cpu':{},'memory':{},
              'swap_used_mib':0,'tasks':latest['tasks'],'load':latest['load'],'processes':[]}
    for field in CPU_FIELDS:
        result['cpu'][field] = sum(weight*s['cpu'][field] for weight,s in samples)/duration
    for field in ('total','free','used','buff/cache'):
        result['memory'][field] = sum(weight*s['memory'][field] for weight,s in samples)/duration
    result['swap_used_mib'] = sum(weight*s['swap_used_mib'] for weight,s in samples)/duration
    # Display processes still present in the latest sample, like top itself.
    for key,process in latest['processes'].items():
        row = dict(process)
        for field in ('cpu','mem','rss_mib'):
            row[field] = sum(weight*s['processes'].get(key,{}).get(field,0) for weight,s in samples)/duration
        result['processes'].append(row)
    result['processes'].sort(key=lambda p:(-p['cpu'],-p['rss_mib'],p['pid']))
    if 'resources' in latest:
        result['resources']=average_resources(samples)
    return result


class TopSource:
    def __init__(self, home):
        environment = dict(os.environ, LC_ALL='C', TZ='Asia/Shanghai', HOME=str(home), XDG_CONFIG_HOME=str(home))
        self.command = ['/usr/bin/top','-b','-d','1','-w','512','-E','m','-e','m','-o','%CPU']
        self.child = subprocess.Popen(self.command,stdout=subprocess.PIPE,env=environment)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.child.stdout,selectors.EVENT_READ)

    def frames(self):
        data = bytearray(); last_data = time.monotonic()
        while True:
            ready = self.selector.select(0.025)
            if ready:
                chunk = os.read(self.child.stdout.fileno(),65536)
                if not chunk:
                    raise RuntimeError(f'top exited: {self.child.poll()}')
                data.extend(chunk); last_data=time.monotonic()
                if len(data)>4_000_000:
                    raise RuntimeError('top frame exceeds bounded buffer')
            elif data:
                text = data.decode('utf-8',errors='replace')
                if not text.lstrip().startswith('top - '):
                    raise RuntimeError('Unexpected top batch output')
                yield time.monotonic(),text
                data.clear()
            elif time.monotonic()-last_data>5:
                raise TimeoutError('top stopped producing one-second samples')

    def close(self):
        self.selector.close()
        if self.child.poll() is None:
            self.child.terminate()
            try:self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.child.kill();self.child.wait(timeout=2)
        self.child.stdout.close()


class TopSampler:
    """Sampling continues while the independent display worker is refreshing."""
    def __init__(self, home, source_factory=TopSource, resource_reader=None):
        self.source=source_factory(home)
        self.resource_reader=resource_reader
        self.queue=queue.Queue(maxsize=2)
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self._sample,name="top-sampler",daemon=True)
        self.thread.start()

    def _publish(self, item):
        try:self.queue.put_nowait(item)
        except queue.Full:
            self.queue.get_nowait()
            self.queue.put_nowait(item)

    def _sample(self):
        previous=None;samples=[];sequence=0;since_publish=0
        try:
            for received,text in self.source.frames():
                if self.stop.is_set():break
                resources=self.resource_reader() if self.resource_reader else None
                if previous is None:
                    previous=received;continue
                snapshot=parse_top(text)
                if resources is not None:snapshot['resources']=resources
                samples.append((received-previous,snapshot))
                previous=received
                since_publish+=1
                span=sum(weight for weight,_ in samples)
                # Retain a rolling window: ten samples can cover less than ten
                # seconds at startup or under scheduling jitter.
                while len(samples)>1 and span-samples[0][0]>=10:
                    span-=samples.pop(0)[0]
                if since_publish>=10 and span>=10:
                    sequence+=1
                    self._publish((received,text,average_window(samples),sequence))
                    since_publish=0
        except BaseException as exc:
            if not self.stop.is_set():self._publish(exc)

    def windows(self):
        while True:
            try:item=self.queue.get(timeout=15)
            except queue.Empty:raise TimeoutError("No ten-second top window received")
            if isinstance(item,BaseException):raise item
            yield item

    def close(self):
        self.stop.set()
        self.source.close()
        self.thread.join(timeout=3)
        if self.thread.is_alive():raise RuntimeError("top sampler did not stop")


def render(summary, sequence, font_path=None):
    paths = [font_path] if font_path else ['/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf','/System/Library/Fonts/Menlo.ttc']
    path = next((p for p in paths if p and Path(p).exists()),None)
    font = ImageFont.truetype(path,11) if path else ImageFont.load_default(size=11)
    title = ImageFont.truetype(path,13) if path else ImageFont.load_default(size=13)
    image = Image.new('1',(400,300),1); draw=ImageDraw.Draw(image)
    now = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S +08:00')
    draw.text((4,2),f'TOP 10s avg #{sequence:04d}  {now}',font=title,fill=0)
    cpu=summary['cpu'];mem=summary['memory']
    lines = [f"CPU us {cpu['us']:4.1f} sy {cpu['sy']:4.1f} id {cpu['id']:4.1f} wa {cpu['wa']:4.1f}",
             f"MEM avg {mem['used']:.0f}/{mem['total']:.0f}MiB  SWAP {summary['swap_used_mib']:.0f}MiB",
             f"Load 1/5/15 {' '.join(f'{v:.2f}' for v in summary['load'])}  Tasks {summary['tasks']}"]
    for i,line in enumerate(lines):draw.text((4,22+i*14),line,font=font,fill=0)
    draw.line((0,65,399,65),fill=0)
    draw.text((4,69),'   PID USER      CPU%  MEM%   MiB COMMAND',font=font,fill=0)
    for i,p in enumerate(summary['processes'][:13]):
        line=f"{p['pid']:6} {p['user'][:8]:8} {p['cpu']:5.1f} {p['mem']:5.1f} {p['rss_mib']:5.0f} {p['command'][:21]}"
        draw.text((4,85+i*14),line,font=font,fill=0)
    draw.line((0,273,399,273),fill=0)
    draw.text((4,279),f"CPU 100%=1 core | {summary['window_seconds']:.2f}s / {summary['sample_count']} samples",font=font,fill=0)
    return image


def display_update(panel, frame, previous_frame, clear_cycle):
    """Explicit black/white/dashboard sequence; stop immediately on any failure."""
    if clear_cycle == "full":
        panel.write_frame(frame)
        busy=panel.refresh()
        panel.power_off()
        return busy,"full"
    if clear_cycle == "black-white":
        stages=[]
        for name,payload in (("black",b"\x00"*15000),("white",b"\xff"*15000),("dashboard",frame)):
            panel.write_frame(payload)
            busy=panel.refresh()
            panel.power_off()
            stages.append({"name":name,"busy_seconds":busy['duration_seconds'],
                           "active_observed":busy['active_observed']})
        return {"duration_seconds":sum(s['busy_seconds'] for s in stages),
                "active_observed":all(s['active_observed'] for s in stages),
                "stages":stages,"bands":[]},"black-white-full"
    if previous_frame is None:
        panel.write_frame(frame);busy=panel.refresh();mode="initial-full"
    else:
        busy=panel.update_changed(previous_frame,frame);mode="partial-full-buffer"
    panel.power_off()
    return busy,mode


def check_inspection(path):
    from eink_driver.cli import validate_inspection
    return validate_inspection(path, Config())


def run(args):
    state=Path(args.state_dir);state.mkdir(parents=True,exist_ok=True)
    isolated_home=state/'top-config';isolated_home.mkdir(exist_ok=True)
    # top-config deliberately contains no toprc: stable columns, no user's config edits.
    c=Config(speed_hz=4_000_000,spacing=0,deadline=60,busy_timeout=20);c.validate()
    if args.hardware:
        inspection=check_inspection(args.inspection)
        deadline=time.monotonic()+30
        while not Path(c.spi_path).exists():
            if time.monotonic()>=deadline:raise TimeoutError('SPI device unavailable at startup')
            time.sleep(0.1)
        preflight=inventory(c)
        if 'FAIL' in preflight['checks'].values():raise RuntimeError('Hardware preflight failed')
        save_json(state/'preflight.json',preflight)
    else:inspection=None
    save_json(state/'startup.json',{'started':timestamp(),'pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'mode':'hardware' if args.hardware else 'mock' if args.mock else 'capture-only',
        'code_version':code_version(),'config':c.record(),'inspection':inspection,'interval_seconds':10,'samples_per_window':10,'layout':args.layout,'clear_cycle':args.clear_cycle})
    source=None;panel=None;budget=Budget(60)
    history=deque(maxlen=120);sequence=0;previous_frame=None
    def emit(event,**fields):
        if event in ('aborted','transport_closed','setup_cleanup_error'):
            print(json.dumps({'time':timestamp(),'event':event,**fields}),flush=True)
    try:
        source=TopSampler(isolated_home,resource_reader=LinuxResources().sample)
        dashboard=Dashboard()
        if args.clear_cycle=='black-white':
            Image.new('1',(400,300),0).save(state/'clear-black.png')
            Image.new('1',(400,300),1).save(state/'clear-white.png')
        if args.hardware or args.mock:
            transport=(live_transport if args.hardware else mock_transport)(c,budget,emit)
            panel=Panel(transport);panel.busy_records=deque(maxlen=128);panel.init()
        for received,text,summary,sequence in source.windows():
            image=dashboard.render(summary,sequence,received) if args.layout=="dashboard" else render(summary,sequence)
            frame=pack(image)
            image.save(state/'latest.png');(state/'latest.frame.bin').write_bytes(frame)
            for name,plane in zip(('cs1','cs2'),split_rows(frame)):(state/f'latest.{name}.bin').write_bytes(plane)
            (state/'latest-top.txt').write_text(text)
            record={'time':timestamp(),'sequence':sequence,'sample_received_monotonic':received,
                    'window_seconds':summary['window_seconds'],'sample_span_seconds':summary['sample_span_seconds'],'sample_count':summary['sample_count'],
                    'frame_sha256':hashlib.sha256(frame).hexdigest(),'summary':summary,'mode':'hardware' if args.hardware else 'mock' if args.mock else 'capture-only'}
            if panel:
                budget.end=budget.clock.now()+60
                started=time.monotonic()
                busy,update_mode=display_update(panel,frame,previous_frame,args.clear_cycle)
                previous_frame=frame
                record.update(update_mode=update_mode,changed_bands=busy.get('bands',[]),refresh_stages=busy.get('stages',[]))
                record.update(display_started_monotonic=started,display_completed_monotonic=time.monotonic(),
                              busy_seconds=busy['duration_seconds'],busy_active_observed=busy['active_observed'])
            history.append({k:v for k,v in record.items() if k!='summary'})
            save_json(state/'latest.json',record);save_json(state/'history.json',list(history))
            print(json.dumps({k:v for k,v in record.items() if k!='summary'}),flush=True)
            if args.windows and sequence>=args.windows:break
    finally:
        if source:source.close()
        if panel:
            budget.end=budget.clock.now()+60
            panel.close()
        save_json(state/'stopped.json',{'time':timestamp(),'sequence':sequence,'physical_power_removed':False})


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group();modes.add_argument('--hardware',action='store_true');modes.add_argument('--mock',action='store_true')
    p.add_argument('--clear-cycle',choices=('full','black-white','off'),default='off')
    p.add_argument('--layout',choices=('dashboard','table'),default='dashboard')
    p.add_argument('--inspection',default=str(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'eink-dashboard'/'inspection.json'))
    p.add_argument('--state-dir',default=str(Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'eink-dashboard'))
    p.add_argument('--windows',type=int,default=0,help='0=continuous; positive=bounded validation')
    args=p.parse_args(argv)
    if args.windows<0:p.error('--windows must be nonnegative')
    def interrupt(signum,frame):raise KeyboardInterrupt()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupt)
    try:run(args)
    except KeyboardInterrupt:return 0
    return 0


if __name__=='__main__':raise SystemExit(main())
