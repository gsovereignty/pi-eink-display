import json
import tempfile
import unittest
from pathlib import Path
from codex_eink.telemetry import summarize,list_loaded,collect
from codex_eink.render import render
from codex_eink.app import main
from eink_driver.images import pack,split_rows

class FakeRPC:
    closed=False
    def __init__(self,path):pass
    def call(self,method,params):
        if method=='thread/loaded/list':return {'data':['a','b','a'],'nextCursor':None}
        if method=='thread/read':return {'thread':{'id':params['threadId'],'status':{'type':'active' if params['threadId']=='a' else 'idle'},'cwd':'/tmp/project','model':'gpt-test'}}
        if method=='account/rateLimits/read':return {'rateLimits':{'primary':{'usedPercent':19,'windowDurationMins':10080,'resetsAt':2000000000}}}
        raise AssertionError(method)
    def close(self):FakeRPC.closed=True

class TelemetryTest(unittest.TestCase):
    def test_states_dedupe_children_waiting_and_unloaded(self):
        threads=[{'id':'a','status':{'type':'active'}},{'id':'b','parentThreadId':'a','status':{'type':'active','activeFlags':['waitingOnApproval']}},{'id':'c','status':{'type':'idle'}},{'id':'d','status':{'type':'systemError'}},{'id':'e','status':{'type':'notLoaded'}}]
        counts,rows=summarize(threads+[threads[0]])
        self.assertEqual(counts,dict(active=2,waiting=1,idle=1,errors=1,roots_active=1,children_active=1,unknown=0,loaded=4))
        self.assertEqual(len(rows),4)
    def test_pagination_and_duplicate_ids(self):
        class Pages:
            def call(self,method,params):
                return {'data':['b','a'],'nextCursor':'next'} if not params['cursor'] else {'data':['b','c'],'nextCursor':None}
        self.assertEqual(list_loaded(Pages()),['a','b','c'])
    def test_repeated_cursor_fails_instead_of_hanging(self):
        class Broken:
            def call(self,*args):return {'data':[],'nextCursor':'same'}
        with self.assertRaises(ValueError):list_loaded(Broken())
    def test_failed_connection_is_unknown_not_zero(self):
        def failed(path):raise OSError('not connected')
        value=collect('unused',Path('/no/status'),failed)
        self.assertFalse(value['available']);self.assertIsNone(value['counts'])
        self.assertTrue(value['network']['stale'])
    def test_read_failure_closes_rpc_and_does_not_report_partial_count(self):
        class Failed(FakeRPC):
            def call(self,method,params):
                if method=='thread/read':raise TimeoutError('deadline')
                return super().call(method,params)
        FakeRPC.closed=False
        value=collect('unused',Path('/no/status'),Failed)
        self.assertTrue(FakeRPC.closed);self.assertFalse(value['available']);self.assertIsNone(value['counts'])
    def test_live_shape_quota_no_account_secrets_and_network_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'network.json';path.write_text(json.dumps({'time':0,'wireguard':{},'zerotier':{}}))
            value=collect('unused',path,FakeRPC)
            self.assertEqual(value['counts']['active'],1)
            self.assertEqual(value['quota'][0]['usedPercent'],19)
            self.assertTrue(value['network']['stale']);self.assertNotIn('accountId',value)
    def test_render_and_row_packing(self):
        value=collect('unused',Path('/no/status'),FakeRPC)
        image=render(value);frame=pack(image)
        self.assertEqual(image.size,(400,300));self.assertEqual(image.mode,'1')
        self.assertEqual(len(frame),15000);self.assertEqual([len(p) for p in split_rows(frame)],[7500,7500])
    def test_fixture_capture_does_not_open_rpc_or_display(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'fixture.json';fixture.write_text(json.dumps(collect('unused',Path('/no/status'),FakeRPC)))
            with patch('codex_eink.app.collect',side_effect=AssertionError('network')),patch('codex_eink.app.live_transport',side_effect=AssertionError('GPIO')):
                self.assertEqual(main(['--fixture',str(fixture),'--windows','1','--state-dir',str(Path(tmp)/'run')]),0)
            self.assertTrue((Path(tmp)/'run/latest.png').exists())
    def test_display_failure_has_no_retry_and_releases_resources(self):
        from unittest.mock import patch, MagicMock
        panel=MagicMock();panel.refresh.side_effect=RuntimeError('stalled')
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'fixture.json';fixture.write_text(json.dumps(collect('unused',Path('/no/status'),FakeRPC)))
            with patch('codex_eink.app.Panel',return_value=panel):
                with self.assertRaisesRegex(RuntimeError,'stalled'):
                    main(['--mock','--fixture',str(fixture),'--windows','3','--state-dir',str(Path(tmp)/'run')])
            panel.refresh.assert_called_once();panel.update_changed.assert_not_called();panel.close.assert_called_once()
    def test_fixture_import_does_not_activate_hardware(self):
        import subprocess,sys
        subprocess.run([sys.executable,'-c','import codex_eink.app'],check=True,capture_output=True)

    def test_mock_uses_one_baseline_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'fixture.json';fixture.write_text(json.dumps(collect('unused',Path('/no/status'),FakeRPC)))
            self.assertEqual(main(['--mock','--fixture',str(fixture),'--windows','1','--state-dir',str(Path(tmp)/'run')]),0)
            events=[json.loads(line) for line in (Path(tmp)/'run/events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(e.get('label')=='full_refresh' for e in events),1)
            self.assertTrue((Path(tmp)/'run/stopped.json').exists())
if __name__=='__main__':unittest.main()
