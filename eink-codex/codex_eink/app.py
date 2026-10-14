"""Live Codex status: bounded read-only telemetry and e-paper updates."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from eink_driver.config import Config
from eink_driver.images import pack, split_rows
from eink_driver.panel import Panel
from eink_driver.preflight import inventory
from eink_driver.transport import Budget, live_transport, mock_transport
from eink_driver.cli import validate_inspection
from .artifacts import code_version, save_json, timestamp
from .telemetry import collect
from .render import render
from .fleet import Fleet,DEFAULT_HOSTS
from .auth import AuthRecovery

@contextmanager
def phase_limit(seconds):
    def expired(_signum,_frame):raise TimeoutError('Phase wall-clock deadline exceeded')
    old=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--hardware',action='store_true');mode.add_argument('--mock',action='store_true')
    parser.add_argument('--socket',default=str(Path.home()/'.codex/app-server-control/app-server-control.sock'))
    parser.add_argument('--network-status',default='/run/pi-codex-network.json')
    parser.add_argument('--collector',type=Path,default=Path.home()/'.local/lib/codex-status/query.py')
    parser.add_argument('--local-only',action='store_true',help='Disable remote host queries')
    parser.add_argument('--no-auth-recovery',action='store_true',help='Disable automatic device login on live hardware')
    parser.add_argument('--interval',type=float,default=15)
    parser.add_argument('--windows',type=int,default=0,help='0 continuous; positive bounded poll count')
    parser.add_argument('--fixture',type=Path,help='Offline JSON snapshot; no HTTP requests')
    parser.add_argument('--state-dir',default=str(Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'eink-codex'))
    parser.add_argument('--inspection',default=str(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'eink-codex/inspection.json'))
    args=parser.parse_args(argv)
    if args.interval<5 or args.windows<0:parser.error('interval >= 5 seconds; windows >= 0')
    state=Path(args.state_dir);state.mkdir(parents=True,exist_ok=True)
    def interrupt(_sig,_frame):raise KeyboardInterrupt()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupt)
    config=Config(speed_hz=4_000_000,spacing=0,deadline=60,busy_timeout=20)
    panel=None;budget=Budget(60);sequence=0;previous=None
    cache={}
    try:
        cached=json.loads((state/'hosts-cache.json').read_text())
        if isinstance(cached,dict):cache=cached
    except (OSError,ValueError):pass
    fleet=Fleet(args.collector,hosts=() if args.local_only else DEFAULT_HOSTS,cache=cache)
    recovery=AuthRecovery() if args.hardware and not args.fixture and not args.no_auth_recovery else None
    if args.hardware:
        inspection=validate_inspection(args.inspection,config)
        preflight=inventory(config);save_json(state/'preflight.json',preflight)
        if 'FAIL' in preflight['checks'].values():raise RuntimeError('Preflight failed; stop other display applications')
    else:inspection=None
    save_json(state/'startup.json',{'time':timestamp(),'pid':os.getpid(),'code_version':code_version(),
        'config':config.record(),'inspection':inspection,'socket':args.socket,'collector':str(args.collector),'local_only':args.local_only,'interval':args.interval,
        'mode':'hardware' if args.hardware else 'mock' if args.mock else 'capture-only'})
    def event(name,**fields):
        with (state/'events.jsonl').open('a') as f:f.write(json.dumps({'time':timestamp(),'event':name,**fields})+'\n')
    try:
        while not args.windows or sequence<args.windows:
            started=time.monotonic()
            with phase_limit(35):
                snapshot=json.loads(args.fixture.read_text()) if args.fixture else fleet.poll(lambda:collect(args.socket,Path(args.network_status)))
                if not args.fixture:save_json(state/'hosts-cache.json',fleet.cache)
            if recovery:recovery.tick(snapshot)
            # Network availability does not cause controller retries or a second baseline.
            image=render(snapshot);frame=pack(image);image.save(state/'latest.png')
            save_json(state/'snapshot.json',snapshot)
            (state/'latest.frame.bin').write_bytes(frame)
            for name,data in zip(('cs1','cs2'),split_rows(frame)):(state/f'latest.{name}.bin').write_bytes(data)
            record={'time':timestamp(),'sequence':sequence+1,'telemetry_available':snapshot['available'],'counts':snapshot.get('counts'),'errors':snapshot.get('errors',[]),'fleet_counts':snapshot.get('fleet_counts'),'fleet_complete':snapshot.get('fleet_complete'),'hosts':{k:v['state'] for k,v in snapshot.get('hosts',{}).items()},
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
        if recovery:recovery.close()
        if panel:
            budget.end=budget.clock.now()+60;panel.close()
        save_json(state/'stopped.json',{'time':timestamp(),'windows':sequence,'physical_power_removed':False})
    return 0

if __name__=='__main__':raise SystemExit(main())
