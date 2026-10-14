"""Read-only Codex managed-daemon JSON-RPC over WebSocket Unix transport."""
import json
import time
from pathlib import Path
from websockets.sync.client import unix_connect
from .usage import normalize

class RPC:
    def __init__(self, path, timeout=30):
        self.end = time.monotonic() + timeout
        self.counter = 0
        self.ws = unix_connect(str(path), uri='ws://localhost/rpc', open_timeout=min(5, timeout), max_size=4*1024*1024, ping_interval=None, close_timeout=1)
        try:
            self.call('initialize', {'clientInfo': {'name':'eink-codex','version':'0.5.0'}, 'capabilities': {'experimentalApi':True}})
            self.ws.send(json.dumps({'method':'initialized','params':{}}))
        except BaseException:
            self.close()
            raise
    def call(self, method, params):
        self.counter += 1
        ident = self.counter
        self.ws.send(json.dumps({'id':ident,'method':method,'params':params}))
        while True:
            remaining = self.end - time.monotonic()
            if remaining <= 0: raise TimeoutError('Telemetry deadline exceeded')
            message = json.loads(self.ws.recv(timeout=remaining))
            if message.get('id') == ident:
                if 'error' in message: raise RuntimeError(str(message['error']))
                return message['result']
            # Notifications are read-only. No answers to approval/tool requests.
    def close(self):
        self.ws.close()


def list_loaded(rpc):
    ids, seen_cursors, cursor = set(), set(), None
    while True:
        response = rpc.call('thread/loaded/list', {'limit':100,'cursor':cursor})
        if not isinstance(response.get('data'), list): raise ValueError('Invalid loaded-thread list')
        ids.update(response['data'])
        cursor = response.get('nextCursor')
        if not cursor: return sorted(ids)
        if cursor in seen_cursors: raise ValueError('Repeated pagination cursor')
        seen_cursors.add(cursor)


def summarize(threads):
    """Count unique loaded sessions, never historical/notLoaded entries."""
    counts = dict(active=0, waiting=0, idle=0, errors=0, roots_active=0, children_active=0, unknown=0, loaded=0)
    rows = []
    for thread in {t['id']:t for t in threads}.values():
        status = thread['status']['type']
        if status == 'notLoaded': continue  # May unload between list and read.
        counts['loaded'] += 1
        flags = thread['status'].get('activeFlags', [])
        waiting = status == 'active' and bool(set(flags) & {'waitingOnApproval','waitingOnUserInput'})
        if status == 'active':
            counts['active'] += 1
            counts['waiting'] += int(waiting)
            counts['children_active' if thread.get('parentThreadId') else 'roots_active'] += 1
        elif status == 'idle': counts['idle'] += 1
        elif status == 'systemError': counts['errors'] += 1
        else: counts['unknown'] += 1
        rows.append({'id':thread['id'], 'parent':thread.get('parentThreadId'),
                     'status':'waiting' if waiting else status,
                     'project':Path(thread.get('cwd') or '/').name or '/',
                     'model':thread.get('model') or '--'})
    rows.sort(key=lambda t:({'active':0,'waiting':1,'systemError':2,'idle':3}.get(t['status'],4),t['id']))
    return counts, rows


def cli_processes(proc=Path('/proc')):
    """Separate CLI process count, not a fabricated agent/state count."""
    result = []
    for path in proc.glob('[0-9]*/cmdline'):
        try:
            args = [a.decode(errors='replace') for a in path.read_bytes().split(b'\0') if a]
            if not args or Path(args[0]).name != 'codex': continue
            if len(args)>1 and args[1] in ('app-server','agents','login','--version'): continue
            result.append(int(path.parent.name))
        except (OSError, ValueError): pass
    return result


def collect(socket_path, network_path=Path('/run/pi-codex-network.json'), factory=RPC):
    snapshot = {'time':time.time(), 'scope':'Pi managed daemon; CLI processes may overlap managed sessions',
                'available':False, 'counts':None, 'threads':[], 'quota':[], 'extra_resets':{'availableCount':None,'credits':[]}, 'errors':[], 'cli_pids':cli_processes()}
    rpc = None
    try:
        rpc = factory(socket_path)
        threads = [rpc.call('thread/read', {'threadId':ident,'includeTurns':False})['thread'] for ident in list_loaded(rpc)]
        snapshot['counts'], snapshot['threads'] = summarize(threads)
        snapshot['available'] = True
        try:
            snapshot['quota'], snapshot['extra_resets'] = normalize(rpc.call('account/rateLimits/read', {}))
        except Exception as exc:
            from .auth import authentication_failed
            snapshot['auth_required'] = authentication_failed(exc)
            snapshot['errors'].append('Quota: '+str(exc)[:150])
    except Exception as exc:
        snapshot['errors'].append(type(exc).__name__+': '+str(exc)[:180])
    finally:
        if rpc: rpc.close()
    try:
        network = json.loads(Path(network_path).read_text())
        network['stale'] = snapshot['time'] - network['time'] > 45
        snapshot['network'] = network
    except (OSError, ValueError, KeyError): snapshot['network'] = {'stale':True}
    return snapshot
