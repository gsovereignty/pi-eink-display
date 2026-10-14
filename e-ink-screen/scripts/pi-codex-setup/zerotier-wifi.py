#!/usr/bin/env python3
"""Route ZeroTier service sockets over wlan0 only; never inherit VPN /32 routes."""
import argparse
import json
import subprocess
from pathlib import Path

TABLE=42000
PRIORITY=1050
MARK='0x5a54'
INTERFACE='wlan0'
CGROUP='system.slice/zerotier-one.service'


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout


def route_commands(routes, family):
    """Dedicated table contains only Wi-Fi routes and terminal unreachable fallback."""
    prefix=['ip',family,'route']
    commands=[prefix+['flush','table',str(TABLE)],
              prefix+['replace','unreachable','default','metric','42760','table',str(TABLE)]]
    for route in routes:
        if route.get('dev')!=INTERFACE or route.get('type','unicast')!='unicast':continue
        command=prefix+['replace',route['dst'],'table',str(TABLE)]
        if route.get('gateway'):command+=['via',route['gateway']]
        command+=['dev',INTERFACE]
        if route.get('prefsrc'):command+=['src',route['prefsrc']]
        if route.get('scope')=='link':command+=['scope','link']
        command+=['metric',str(route.get('metric',600))]
        commands.append(command)
    return commands


def ruleset():
    return f'''table inet zt_wifi_only {{
 chain mark_output {{
  type route hook output priority mangle; policy accept;
  socket cgroupv2 level 2 "{CGROUP}" counter meta mark set {MARK}
 }}
 chain enforce_egress {{
  type filter hook postrouting priority filter; policy accept;
  meta mark {MARK} oifname != {{ "{INTERFACE}", "lo" }} counter drop
 }}
}}
'''


def configure(routing_only=False):
    if not routing_only:
        # Resolve cgroup at every daemon start; stale cgroup IDs must not survive restart.
        exists=subprocess.run(['nft','list','table','inet','zt_wifi_only'],capture_output=True).returncode==0
        script=('delete table inet zt_wifi_only\n' if exists else '')+ruleset()
        run(['nft','-c','-f','-'],input=script)
        run(['nft','-f','-'],input=script)  # Atomic replacement of our table only.
    for family in ('-4','-6'):
        routes=json.loads(run(['ip','-j',family,'route','show','table','main']))
        # Ensure table exists before flushing it on first installation.
        run(['ip',family,'route','replace','unreachable','default','metric','42760','table',str(TABLE)])
        for command in route_commands(routes,family):run(command)
        rules=json.loads(run(['ip','-j',family,'rule','show']))
        owned=[rule for rule in rules if rule.get('priority')==PRIORITY]
        expected=str(TABLE)
        if owned:
            if len(owned)!=1 or str(owned[0].get('table'))!=expected or str(owned[0].get('fwmark'))!=MARK:
                raise RuntimeError('Policy rule priority already belongs to another configuration')
        else:
            run(['ip',family,'rule','add','priority',str(PRIORITY),'fwmark',MARK,'lookup',str(TABLE)])
    print(json.dumps({'interface':INTERFACE,'table':TABLE,'mark':MARK,'routing_only':routing_only}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes-only',action='store_true')
    configure(parser.parse_args().routes_only)
