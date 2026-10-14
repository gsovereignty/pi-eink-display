from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from codex_eink.fleet import Fleet,normalize,query
from codex_eink.render import render

def remote(states,now=1000):
    return {'observedAt':datetime.fromtimestamp(now,timezone.utc).isoformat(),'socketReadable':True,
            'loadedThreadCount':len(states),'threads':[{'id':ident,'runtimeState':state} for ident,state in states]}

def local(available=True):
    return {'time':1000,'available':available,'counts':dict(active=1,waiting=0,idle=2,errors=0,loaded=3,unknown=0) if available else None,
            'threads':[],'quota':[],'extra_resets':{},'errors':[],'network':{'stale':True}}

class FleetTest(unittest.TestCase):
    def test_dedup_waiting_and_unloaded(self):
        rows=[('a',{'type':'active','activeFlags':['waitingOnApproval']}),('b',{'type':'idle'}),('c',{'type':'systemError'}),('d',{'type':'notLoaded'})]
        value=normalize(remote(rows+[rows[0]]),1000)
        self.assertEqual(value['counts'],dict(active=1,waiting=1,idle=1,errors=1,loaded=3))
    def test_bad_timestamp_count_socket_error_and_unknown_state_rejected(self):
        for change in ({'observedAt':'bad'},{'observedAt':'1970-01-01T00:00:00'},{'observedAt':datetime.fromtimestamp(950,timezone.utc).isoformat()},
                       {'socketReadable':False},{'loadedThreadCount':True},{'loadedThreadCount':7},
                       {'threads':[{'id':'a','error':'not loaded'}]}, {'threads':[{'id':'a','runtimeState':{'type':'futureState'}}]}):
            value=remote([('a',{'type':'active'})]);value.update(change)
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):normalize(value,1000)
    def test_query_uses_exact_alias_and_remote_and_local_deadlines(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append((args,kwargs));return subprocess.CompletedProcess(args,0,json.dumps(remote([])),'')
        query('codex-macbook','print("snapshot")',runner)
        args,kwargs=calls[0]
        self.assertIn('codex-macbook',args);self.assertIn('BatchMode=yes',args)
        self.assertEqual(kwargs['timeout'],12);self.assertIn('ITIMER_REAL,8',kwargs['input'])
        self.assertNotIn('app-server start',kwargs['input'])
    def test_query_failure_not_retried_or_interpreted_as_empty(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(args);return subprocess.CompletedProcess(args,2,'{}','socket unavailable')
        with self.assertRaisesRegex(RuntimeError,'exit 2'):query('alias','source',runner)
        self.assertEqual(len(calls),1)
    def fleet(self,tmp,query_fn,cache=None,now=1000):
        path=Path(tmp)/'query.py';path.write_text('pass')
        return Fleet(path,cache=cache,query_fn=query_fn,clock=lambda:now)
    def test_totals_namespace_same_thread_id_per_machine_and_usage_not_summed(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=self.fleet(tmp,lambda *_:remote([('same',{'type':'active'})]))
            def pi():
                s=local();s['quota']=[{'usedPercent':30,'windowDurationMins':10080,'resetsAt':100000}];return s
            value=f.poll(pi)
            self.assertEqual(value['fleet_counts']['active'],3)
            self.assertTrue(value['fleet_complete']);self.assertEqual(value['quota'][0]['usedPercent'],30)
    def test_recent_failure_stale_excluded_then_offline_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=self.fleet(tmp,lambda *_:remote([('a',{'type':'active'})]));f.poll(local)
            def failed(*args):raise TimeoutError('host asleep')
            f.query=failed;value=f.poll(local)
            self.assertEqual(value['hosts']['macbook']['state'],'STALE')
            self.assertIsNone(value['hosts']['macbook']['counts']);self.assertEqual(value['fleet_counts']['active'],1)
            self.assertFalse(value['fleet_complete'])
            f.clock=lambda:1046;value=f.poll(local)
            self.assertEqual(value['hosts']['macbook']['state'],'OFFLINE')
            f.clock=lambda:1000;f.query=lambda *_:remote([]);value=f.poll(local)
            self.assertEqual(value['hosts']['macbook']['state'],'LIVE');self.assertTrue(value['fleet_complete'])
    def test_no_hosts_available_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            def failed(*args):raise OSError('unreachable')
            value=self.fleet(tmp,failed).poll(lambda:local(False))
            self.assertIsNone(value['fleet_counts']);self.assertEqual(value['fleet_fresh'],0)
            self.assertEqual(render(value).size,(400,300))
    def test_missing_collector_keeps_pi_and_displays_remote_offline(self):
        def forbidden(*args):raise AssertionError('SSH called')
        value=Fleet('/no/collector',query_fn=forbidden,clock=lambda:1000).poll(local)
        self.assertEqual(value['fleet_counts']['active'],1);self.assertEqual(value['hosts']['mini']['state'],'OFFLINE')
    def test_both_queries_started_before_local_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            both=threading.Barrier(3,timeout=2)
            def remote_fn(*args):both.wait();return remote([])
            def pi():both.wait();return local()
            value=self.fleet(tmp,remote_fn).poll(pi)
            self.assertTrue(value['fleet_complete'])
    def test_local_failure_does_not_hide_fresh_remote_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=self.fleet(tmp,lambda *_:remote([('a',{'type':'active'})])).poll(lambda:local(False))
            self.assertEqual(value['fleet_counts']['active'],2);self.assertEqual(value['fleet_fresh'],2)
    def test_renderer_uses_space_for_hosts_and_omits_five_hour_panel(self):
        from unittest.mock import patch
        from PIL import ImageDraw
        labels=[];original=ImageDraw.ImageDraw.text
        def record(draw,xy,text,*args,**kwargs):
            labels.append(str(text));return original(draw,xy,text,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            value=self.fleet(tmp,lambda *_:remote([])).poll(local)
            with patch.object(ImageDraw.ImageDraw,'text',record):render(value)
        self.assertIn('MacBook',labels);self.assertIn('Mini',labels);self.assertIn('STATUS',labels)
        self.assertIn('7-DAY WINDOW',labels);self.assertNotIn('5-HOUR WINDOW',labels)
        self.assertNotIn('CODEX / USAGE',labels)
    def test_local_only_never_runs_ssh(self):
        def forbidden(*args):raise AssertionError('SSH called')
        value=Fleet('/no/collector',hosts=(),query_fn=forbidden,clock=lambda:1000).poll(local)
        self.assertTrue(value['fleet_complete']);self.assertEqual(value['fleet_host_count'],1)
if __name__=='__main__':unittest.main()
