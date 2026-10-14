"""Bounded, concurrent SSH status collection. Never starts/resumes Codex agents."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time

DEFAULT_HOSTS=(('macbook','MacBook','codex-macbook'),('mini','Mini','codex-mac-mini'))


def query(alias,source,runner=subprocess.run):
    # Deadline runs ON THE MAC too; killing SSH alone need not stop remote Python.
    wrapper="import signal\ndef expired(*args): raise TimeoutError('Remote collector deadline exceeded')\nsignal.signal(signal.SIGALRM,expired)\nsignal.setitimer(signal.ITIMER_REAL,8)\nexec(compile("+repr(source)+",'query.py','exec'),{'__name__':'__main__'})\n"
    result=runner(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=4','-o','ConnectionAttempts=1',
                   '-o','ServerAliveInterval=3','-o','ServerAliveCountMax=1',alias,
                   '/opt/homebrew/bin/python3.14 -'],input=wrapper,text=True,capture_output=True,timeout=12)
    if result.returncode:raise RuntimeError(f'SSH/collector exit {result.returncode}: {result.stderr[-160:].strip()}')
    if len(result.stdout)>1_048_576:raise ValueError('Collector response exceeds 1 MiB')
    return json.loads(result.stdout)


def normalize(data,now):
    if data.get('socketReadable') is not True:raise ValueError('Remote daemon socket unavailable')
    observed=datetime.fromisoformat(data['observedAt'])
    if observed.utcoffset() is None:raise ValueError('Collector timestamp lacks timezone')
    age=now-observed.timestamp()
    if age>45 or age<-30:raise ValueError('Collector timestamp stale or clock differs by over 30s')
    threads=data['threads'];loaded=data['loadedThreadCount']
    if not isinstance(threads,list) or type(loaded) is not int or loaded<0:raise ValueError('Invalid thread list/count')
    unique={}
    for row in threads:
        if not isinstance(row.get('id'),str) or not row['id']:raise ValueError('Invalid thread identity')
        if 'error' in row:raise ValueError('Remote thread read incomplete')
        state=row['runtimeState'];kind=state['type'];flags=state.get('activeFlags',[])
        if kind not in ('active','idle','systemError','notLoaded'):raise ValueError('Unknown runtime state')
        if not isinstance(flags,list) or not all(isinstance(flag,str) for flag in flags):raise ValueError('Invalid active flags')
        if row['id'] in unique and unique[row['id']]['runtimeState']!=state:raise ValueError('Conflicting duplicate state')
        unique[row['id']]={'id':row['id'],'runtimeState':state}
    if loaded not in (len(threads),len(unique)):raise ValueError('Thread count mismatch')
    counts=dict(active=0,waiting=0,idle=0,errors=0,loaded=0)
    for row in unique.values():
        state=row['runtimeState'];kind=state['type']
        if kind=='notLoaded':continue
        counts['loaded']+=1
        if kind=='active':
            counts['active']+=1
            counts['waiting']+=int(bool(set(state.get('activeFlags',[]))&{'waitingOnApproval','waitingOnUserInput'}))
        elif kind=='idle':counts['idle']+=1
        else:counts['errors']+=1
    return {'observedAt':data['observedAt'],'received_at':now,'counts':counts,'threads':list(unique.values())}


class Fleet:
    def __init__(self,collector,hosts=DEFAULT_HOSTS,cache=None,query_fn=query,clock=time.time):
        self.collector=Path(collector);self.hosts=hosts;self.cache=cache or {};self.query=query_fn;self.clock=clock
    def poll(self,local_fn):
        try:source=self.collector.read_text();source_error=None
        except OSError as exc:source=None;source_error=f'Collector unavailable: {exc}'
        with ThreadPoolExecutor(max_workers=max(1,len(self.hosts))) as pool:
            jobs={key:pool.submit(self.query,alias,source) for key,label,alias in self.hosts} if source is not None else {}
            # Pi's local socket read and SSH commands run concurrently.
            snapshot=local_fn()
            hosts={'pi':{'label':'Pi','state':'LIVE' if snapshot['available'] and not (snapshot.get('counts') or {}).get('unknown') else 'OFFLINE',
                         'counts':snapshot.get('counts'),'observedAt':snapshot['time']}}
            for key,label,alias in self.hosts:
                try:
                    if source_error:raise RuntimeError(source_error)
                    value=normalize(jobs[key].result(),self.clock());self.cache[key]=value
                    hosts[key]={'label':label,'alias':alias,'state':'LIVE',**value}
                except Exception as exc:
                    last=self.cache.get(key);now=self.clock()
                    recent=isinstance(last,dict) and isinstance(last.get('received_at'),(int,float)) and 0<=now-last['received_at']<=45
                    hosts[key]={'label':label,'alias':alias,'state':'STALE' if recent else 'OFFLINE','counts':None,
                                'error':f'{type(exc).__name__}: {exc}'[:240], 'last_good':last}
        totals=dict(active=0,waiting=0,idle=0,errors=0,loaded=0)
        fresh=[h for h in hosts.values() if h['state']=='LIVE']
        for host in fresh:
            for key in totals:totals[key]+=host['counts'][key]
        snapshot.update(hosts=hosts,fleet_counts=totals if fresh else None,fleet_complete=len(fresh)==len(hosts),
                        fleet_fresh=len(fresh),fleet_host_count=len(hosts),scope='Pi and SSH host managed daemons; failed/stale hosts excluded')
        return snapshot
