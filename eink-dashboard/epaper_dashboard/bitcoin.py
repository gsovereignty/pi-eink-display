"""Bitcoin mainnet dashboard: public API, cached failures, bounded e-paper updates."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from PIL import Image, ImageDraw, ImageFont
from eink_driver.config import Config
from eink_driver.images import pack, split_rows
from eink_driver.panel import Panel
from eink_driver.preflight import inventory
from eink_driver.transport import Budget, live_transport, mock_transport
from eink_driver.cli import validate_inspection
from .artifacts import code_version, save_json, timestamp

ENDPOINTS={'price':'/v1/prices','fees':'/v1/fees/recommended','mempool':'/mempool',
           'blocks':'/v1/blocks','difficulty':'/v1/difficulty-adjustment'}
TZ=ZoneInfo('Asia/Shanghai')


def number(value, minimum=0):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<minimum:
        raise ValueError('Invalid numeric API field')
    return value


def validate(name,data):
    """Validate rendered fields before replacing last known good endpoint response."""
    if name=='blocks':
        if not isinstance(data,list) or not data:raise ValueError('Empty block list')
        for block in data[:3]:
            for key in ('height','timestamp','tx_count','weight'):number(block[key])
        if any(data[i]['height']<=data[i+1]['height'] for i in range(min(2,len(data)-1))):
            raise ValueError('Blocks must be newest first')
    else:
        if not isinstance(data,dict):raise ValueError('Expected API object')
        fields={'price':('USD','time'),'fees':('fastestFee','halfHourFee','hourFee','minimumFee'),
                'mempool':('count','vsize'),'difficulty':('remainingBlocks','progressPercent','difficultyChange')}[name]
        for key in fields:number(data[key],-100 if key=='difficultyChange' else 0)
        if name=='price' and data['USD']==0:raise ValueError('Zero USD quote')
        if name=='difficulty' and data['progressPercent']>100:raise ValueError('Invalid retarget progress')
    return data


@contextmanager
def phase_limit(seconds):
    """Wall-clock bound, including blocked network/kernel calls, on POSIX main thread."""
    def expired(_signum,_frame):raise TimeoutError('Phase wall-clock deadline exceeded')
    old=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old)


def fetch_json(base,path):
    request=Request(base.rstrip('/')+path,headers={'User-Agent':'eink-bitcoin/0.2.0','Accept':'application/json'})
    with phase_limit(8):
        with urlopen(request,timeout=6) as response:
            raw=response.read(1_048_577)
    if len(raw)>1_048_576:raise ValueError('API response exceeds 1 MiB')
    return json.loads(raw)


class Client:
    def __init__(self,base='https://mempool.space/api',cache=None,fetch=fetch_json,clock=time.time):
        self.base=base;self.fetch=fetch;self.clock=clock;self.entries={}
        if isinstance(cache,dict):
            for name,entry in cache.items():
                try:
                    if name in ENDPOINTS:
                        validate(name,entry['data']);number(entry['fetched_at']);self.entries[name]=entry
                except (ValueError,TypeError,KeyError):pass
    def poll(self):
        errors={}
        for name,path in ENDPOINTS.items():
            try:
                data=validate(name,self.fetch(self.base,path))
                self.entries[name]={'data':data,'fetched_at':self.clock()}
            except Exception as exc:
                errors[name]=f'{type(exc).__name__}: {exc}'[:240]
        return {'time':self.clock(),'entries':dict(self.entries),'errors':errors,'source':self.base}


def cached(snapshot,name):
    entry=snapshot.get('entries',{}).get(name)
    return bool(entry and (name in snapshot.get('errors',{}) or snapshot['time']-entry['fetched_at']>180))


def age(seconds):
    seconds=max(0,seconds)
    return f'{seconds/60:.0f}m' if seconds<3600 else f'{seconds/3600:.1f}h'


def render(snapshot):
    image=Image.new('1',(400,300),1);draw=ImageDraw.Draw(image)
    paths=['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/System/Library/Fonts/Supplemental/Arial.ttf']
    path=next((p for p in paths if Path(p).exists()),None)
    def font(size):return ImageFont.truetype(path,size) if path else ImageFont.load_default(size=size)
    def text(x,y,value,size=12,fill=0):draw.text((x,y),str(value),font=font(size),fill=fill)
    def value(name):return snapshot.get('entries',{}).get(name,{}).get('data')
    def label(name,title):return title+(' *' if cached(snapshot,name) else '')
    now=snapshot['time'];price=value('price');fees=value('fees');pool=value('mempool');blocks=value('blocks');difficulty=value('difficulty')
    draw.rectangle((0,0,399,23),fill=0)
    text(8,3,'BITCOIN / MAINNET',13,1)
    text(285,4,datetime.fromtimestamp(now,TZ).strftime('%H:%M')+' +08',12,1)
    text(8,29,label('price','BTC / USD'),11)
    text(5,42,f'${price["USD"]:,.0f}' if price else '--',36)
    text(8,85,f'{100_000_000/price["USD"]:,.0f} sats/$  |  quote {age(now-price["time"])} old' if price else 'PRICE UNAVAILABLE',10)
    draw.line((246,29,246,95),fill=0)
    text(260,29,label('blocks','BLOCK HEIGHT'),10)
    text(257,45,f'{blocks[0]["height"]:,}' if blocks else '--',21)
    text(260,77,f'Last block {age(now-blocks[0]["timestamp"])} ago' if blocks else 'NO BLOCK DATA',10)
    draw.line((8,103,391,103),fill=0)
    text(8,107,label('fees','FEE ESTIMATES / sat/vB'),11)
    for i,(key,title) in enumerate((('fastestFee','~10 MIN'),('halfHourFee','~30 MIN'),('hourFee','~60 MIN'))):
        x=8+i*132;draw.rounded_rectangle((x,126,x+120,177),radius=4,outline=0)
        text(x+8,128,f'{fees[key]:g}' if fees else '--',24)
        text(x+8,159,title,10)
    text(8,184,label('mempool','MEMPOOL'),10)
    text(8,197,f'{pool["count"]:,} tx' if pool else '--',18)
    text(235,197,f'{pool["vsize"]/1e6:.1f} MvB' if pool else '--',18)
    text(8,222,'RECENT BLOCKS',10)
    for i in range(3):
        x=8+i*132;block=blocks[i] if blocks and len(blocks)>i else None
        if block:
            text(x,236,f'#{block["height"]:,}',12)
            text(x,253,f'{block["tx_count"]:,} tx / {age(now-block["timestamp"])}',10)
        else:text(x,239,'--',12)
    draw.line((8,272,391,272),fill=0)
    text(8,276,label('difficulty',f'Retarget {difficulty["difficultyChange"]:+.1f}% est / {difficulty["remainingBlocks"]:,} blocks') if difficulty else 'RETARGET UNAVAILABLE',10)
    entries=snapshot.get('entries',{});oldest=max((now-e['fetched_at'] for e in entries.values()),default=0)
    error_count=len(snapshot.get('errors',{}))
    status=f'* CACHED / {error_count} API errors' if error_count else 'STALE CACHE' if any(cached(snapshot,n) for n in entries) else 'API OK' if len(entries)==5 else 'DATA UNAVAILABLE'
    text(8,289,f'mempool.space | {status} | fetched {age(oldest)} ago',9)
    return image


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--hardware',action='store_true');mode.add_argument('--mock',action='store_true')
    parser.add_argument('--api-base',default='https://mempool.space/api')
    parser.add_argument('--interval',type=float,default=60)
    parser.add_argument('--windows',type=int,default=0,help='0 continuous; positive bounded poll count')
    parser.add_argument('--fixture',type=Path,help='Offline JSON snapshot; no HTTP requests')
    parser.add_argument('--state-dir',default=str(Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'eink-bitcoin'))
    parser.add_argument('--inspection',default=str(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'eink-dashboard/inspection.json'))
    args=parser.parse_args(argv)
    if args.interval<30 or args.windows<0:parser.error('interval >= 30 seconds; windows >= 0')
    if not args.api_base.startswith(('https://','http://')):parser.error('API base must be an HTTP(S) URL')
    state=Path(args.state_dir);state.mkdir(parents=True,exist_ok=True)
    def interrupt(_sig,_frame):raise KeyboardInterrupt()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupt)
    config=Config(speed_hz=4_000_000,spacing=0,deadline=60,busy_timeout=20)
    panel=None;budget=Budget(60);sequence=0;previous=None
    cache={}
    try:cache=json.loads((state/'cache.json').read_text())
    except (OSError,ValueError):pass
    client=Client(args.api_base,cache)
    if args.hardware:
        inspection=validate_inspection(args.inspection,config)
        preflight=inventory(config);save_json(state/'preflight.json',preflight)
        if 'FAIL' in preflight['checks'].values():raise RuntimeError('Preflight failed; stop other display applications')
    else:inspection=None
    save_json(state/'startup.json',{'time':timestamp(),'pid':os.getpid(),'code_version':code_version(),
        'config':config.record(),'inspection':inspection,'api':args.api_base,'interval':args.interval,
        'mode':'hardware' if args.hardware else 'mock' if args.mock else 'capture-only'})
    def event(name,**fields):
        with (state/'events.jsonl').open('a') as f:f.write(json.dumps({'time':timestamp(),'event':name,**fields})+'\n')
    try:
        while not args.windows or sequence<args.windows:
            started=time.monotonic()
            snapshot=json.loads(args.fixture.read_text()) if args.fixture else client.poll()
            # Network availability does not cause controller retries or a second baseline.
            image=render(snapshot);frame=pack(image);image.save(state/'latest.png')
            save_json(state/'cache.json',snapshot['entries']);save_json(state/'snapshot.json',snapshot)
            (state/'latest.frame.bin').write_bytes(frame)
            for name,data in zip(('cs1','cs2'),split_rows(frame)):(state/f'latest.{name}.bin').write_bytes(data)
            record={'time':timestamp(),'sequence':sequence+1,'api_errors':snapshot.get('errors',{}),
                'frame_sha256':hashlib.sha256(frame).hexdigest(),'hardware_visual_status':'INCONCLUSIVE' if args.hardware else 'NOT RUN'}
            if args.hardware or args.mock:
                budget.end=budget.clock.now()+60
                with phase_limit(60):
                    if panel is None:
                        panel=Panel((live_transport if args.hardware else mock_transport)(config,budget,event));panel.init()
                    if previous is None:panel.write_frame(frame);result=panel.refresh();update='initial-full'
                    else:result=panel.update_changed(previous,frame);update='partial-full-buffer'
                    panel.power_off();record.update(update_mode=update,busy_seconds=result['duration_seconds'],busy_active_observed=result['active_observed'])
            previous=frame;sequence+=1;save_json(state/'latest.json',record)
            print(json.dumps(record),flush=True)
            if args.windows and sequence>=args.windows:break
            time.sleep(max(0,args.interval-(time.monotonic()-started)))
    except KeyboardInterrupt:event('interrupted')
    except Exception as exc:event('failed',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        if panel:
            budget.end=budget.clock.now()+60;panel.close()
        save_json(state/'stopped.json',{'time':timestamp(),'windows':sequence,'physical_power_removed':False})
    return 0

if __name__=='__main__':raise SystemExit(main())
