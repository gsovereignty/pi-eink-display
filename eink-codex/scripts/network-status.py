#!/usr/bin/env python3
"""Privileged fixed-purpose exporter. No keys, tokens, or peer configuration."""
import json,subprocess,time
from pathlib import Path

def command(args):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=5).stdout

result={'time':time.time(),'wireguard':{},'zerotier':{}}
try:
    rows=command(['wg','show','ivpn-openai','latest-handshakes']).splitlines()
    result['wireguard']['latest_handshake']=max((int(r.split()[1]) for r in rows),default=0)
    result['wireguard']['interface']='ivpn-openai'
except Exception as exc:result['wireguard']['error']=type(exc).__name__
try:
    network=next(n for n in json.loads(command(['zerotier-cli','-j','listnetworks'])) if n['id']=='8d1c312afae039bc')
    result['zerotier']={k:network[k] for k in ('id','status','assignedAddresses')}
except Exception as exc:result['zerotier']['error']=type(exc).__name__
path=Path('/run/pi-codex-network.json');temp=path.with_suffix('.tmp')
temp.write_text(json.dumps(result)+'\n');temp.chmod(0o644);temp.replace(path)
