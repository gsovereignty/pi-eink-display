#!/usr/bin/env python3
"""One real managed turn: observe active then idle. No delegated agents."""
import json,time
from pathlib import Path
from codex_eink.telemetry import RPC,collect
from codex_eink.artifacts import save_json,timestamp
socket=Path.home()/'.codex/app-server-control/app-server-control.sock'
path=Path.home()/'.local/state/eink-codex/verification.json'
rpc=RPC(socket,timeout=120)
try:
    thread=rpc.call('thread/start',{'cwd':str(Path.home()),'approvalPolicy':'never','sandbox':'danger-full-access'})['thread']['id']
    turn=rpc.call('turn/start',{'threadId':thread,'input':[{'type':'text','text':'This is a dashboard telemetry validation. Run python3 -c "import time; time.sleep(25)" once, then reply exactly DASHBOARD_LIVE_OK. Do not edit files, access network, or spawn agents.'}]})['turn']['id']
    records=[];active_seen=False;deadline=time.monotonic()+110
    while time.monotonic()<deadline:
        snapshot=collect(socket)
        row=next((t for t in snapshot['threads'] if t['id']==thread),None)
        records.append({'time':timestamp(),'row':row,'counts':snapshot['counts']})
        if row and row['status']=='active':active_seen=True
        if active_seen and row and row['status']=='idle':break
        time.sleep(2)
    else:
        rpc.call('turn/interrupt',{'threadId':thread,'turnId':turn})
        raise TimeoutError('Active-to-idle validation exceeded deadline')
    result={'thread':thread,'active_seen':active_seen,'idle_seen':row['status']=='idle','records':records}
    save_json(path,result);print(json.dumps(result))
finally:rpc.close()
