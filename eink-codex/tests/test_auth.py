import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from codex_eink.auth import AuthRecovery, authentication_failed
from codex_eink.render import render
from codex_eink.telemetry import collect
from tests.test_telemetry import FakeRPC


class AuthTest(unittest.TestCase):
    def snapshot(self, required=True, active=0):
        return {'auth_required': required, 'available': True, 'counts': {'active': active}}

    def wait_for(self, recovery, predicate, snapshot):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            value = recovery.tick(snapshot())
            if predicate(value):
                return value
            time.sleep(.01)
        self.fail('Recovery did not reach expected state')

    def executable(self, directory):
        path = directory / 'codex'
        path.write_text(f'''#!{sys.executable}
import pathlib, sys, time
directory = pathlib.Path(__file__).parent
if sys.argv[1] == 'login':
    with (directory / 'starts').open('a') as f: f.write('login\\n')
    print('https://auth.openai.com/codex/device', flush=True)
    print('  ABCD-EFGHI', flush=True)
    while not (directory / 'complete').exists(): time.sleep(.01)
    print('Successfully logged in', flush=True)
else:
    (directory / 'restarted').write_text('yes')
''')
        path.chmod(0o700)
        return path

    def test_expired_token_detected_before_error_truncation(self):
        class Expired(FakeRPC):
            def call(self, method, params):
                if method == 'account/rateLimits/read':
                    raise RuntimeError('x' * 200 + 'token_expired')
                return super().call(method, params)
        value = collect('unused', Path('/no/status'), Expired)
        self.assertTrue(value['auth_required'])
        self.assertTrue(value['available'])
        self.assertNotIn('token_expired', value['errors'][0])
        for error in ('timeout', '403 Forbidden', 'connection refused', '500 Internal Server Error'):
            self.assertFalse(authentication_failed(error))
        self.assertTrue(authentication_failed('codex account authentication required to read rate limits'))

    def test_one_login_code_then_reload_waits_for_idle_pi(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            executable = self.executable(directory)
            recovery = AuthRecovery(executable, restart_command=[str(executable), 'app-server', 'daemon', 'restart'])
            try:
                value = self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('code'), self.snapshot)
                self.assertEqual(value['auth_recovery']['code'], 'ABCD-EFGHI')
                for _ in range(5): recovery.tick(self.snapshot())
                self.assertEqual((directory / 'starts').read_text(), 'login\n')
                (directory / 'complete').touch()
                self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('state') == 'reload_pending', lambda: self.snapshot(active=1))
                self.assertFalse((directory / 'restarted').exists())
                recovery.tick({'available': False, 'counts': None, 'auth_required': True})
                self.assertFalse((directory / 'restarted').exists())
                self.wait_for(recovery, lambda v: (directory / 'restarted').exists() and recovery.process is None, lambda: self.snapshot(False))
                self.assertNotIn('auth_recovery', recovery.tick(self.snapshot(False)))
            finally: recovery.close()

    def test_expiry_removes_old_code_and_retry_issues_new_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            clock = [0]
            recovery = AuthRecovery(self.executable(directory), clock=lambda: clock[0])
            try:
                self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('code'), self.snapshot)
                clock[0] = 901
                value = recovery.tick(self.snapshot())
                self.assertEqual(value['auth_recovery']['state'], 'retry')
                self.assertIsNone(value['auth_recovery']['code'])
                recovery.tick(self.snapshot())
                self.assertEqual((directory / 'starts').read_text(), 'login\n')
                clock[0] = 962
                self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('code'), self.snapshot)
                self.assertEqual((directory / 'starts').read_text(), 'login\nlogin\n')
            finally: recovery.close()

    def test_missing_executable_retries_with_cooldown_and_healthy_poll_does_not_start(self):
        clock = [0]
        recovery = AuthRecovery('/missing/codex', clock=lambda: clock[0])
        self.assertNotIn('auth_recovery', recovery.tick(self.snapshot(False)))
        value = recovery.tick(self.snapshot())
        self.assertEqual(value['auth_recovery']['state'], 'retry')
        with patch('codex_eink.auth.subprocess.Popen', side_effect=AssertionError('retry too early')):
            recovery.tick(self.snapshot())
        recovery.close()

    def test_reload_failure_does_not_request_another_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            clock = [0]
            recovery = AuthRecovery(self.executable(directory), clock=lambda: clock[0],
                                    restart_command=[sys.executable, '-c', 'raise SystemExit(1)'])
            try:
                self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('code'), self.snapshot)
                (directory / 'complete').touch()
                self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('state') == 'reload_retry', self.snapshot)
                for _ in range(3): recovery.tick(self.snapshot())
                self.assertEqual((directory / 'starts').read_text(), 'login\n')
                clock[0] = 61
                self.wait_for(recovery, lambda v: v.get('auth_recovery', {}).get('state') == 'reload_retry', self.snapshot)
                self.assertEqual((directory / 'starts').read_text(), 'login\n')
            finally: recovery.close()

    def test_fixture_and_mock_do_not_start_auth_recovery(self):
        from codex_eink.app import main
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            snapshot = collect('unused', Path('/no/status'), FakeRPC)
            snapshot['auth_required'] = True
            fixture = directory / 'fixture.json'
            fixture.write_text(json.dumps(snapshot))
            with patch('codex_eink.app.AuthRecovery', side_effect=AssertionError('login in fixture')):
                self.assertEqual(main(['--fixture', str(fixture), '--windows', '1', '--state-dir', str(directory / 'capture')]), 0)
                self.assertEqual(main(['--mock', '--fixture', str(fixture), '--windows', '1', '--state-dir', str(directory / 'mock')]), 0)

    def test_login_render_preserves_agents_and_displays_code(self):
        snapshot = collect('unused', Path('/no/status'), FakeRPC)
        original = render(snapshot)
        snapshot['auth_recovery'] = {'state': 'login', 'code': 'ABCD-EFGHI', 'expires_in_minutes': 14}
        from PIL import ImageDraw
        real = ImageDraw.ImageDraw.text
        labels = []
        def record(draw, xy, text, *args, **kwargs):
            labels.append(text)
            return real(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', record):
            image = render(snapshot)
        self.assertEqual(original.crop((0, 0, 400, 140)).tobytes(), image.crop((0, 0, 400, 140)).tobytes())
        self.assertIn('ABCD-EFGHI', labels)
        self.assertIn('auth.openai.com/codex/device', labels)


if __name__ == '__main__':
    unittest.main()
