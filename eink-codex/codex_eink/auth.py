"""Nonblocking device login for the live Pi display; never launches agents."""
import os
from pathlib import Path
import pty
import re
import subprocess
import time


def authentication_failed(error):
    value = str(error).lower()
    return any(marker in value for marker in (
        '401 unauthorized', 'token_expired', 'refresh_token_reused',
        'refresh_token_expired', 'refresh_token_invalid',
        'codex account authentication required to read rate limits',
    ))


class AuthRecovery:
    def __init__(self, executable=None, clock=time.monotonic, restart_command=None):
        self.executable = str(executable or Path.home() / '.local/bin/codex')
        # Keep restarted daemon outside display service's KillMode=control-group.
        self.restart_command = restart_command or [
            'systemd-run', '--user', '--scope', '--quiet', self.executable,
            'app-server', 'daemon', 'restart',
        ]
        self.clock = clock
        self.process = None
        self.master = None
        self.output = ''
        self.started = 0
        self.retry_at = 0
        self.stage = None
        self.code = None

    def _start_login(self):
        master, slave = pty.openpty()
        try:
            self.process = subprocess.Popen(
                [self.executable, 'login', '--device-auth'], stdin=slave,
                stdout=slave, stderr=slave, start_new_session=True,
            )
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self.master = master
        os.set_blocking(master, False)
        self.started = self.clock()
        self.stage = 'starting'
        self.output = ''
        self.code = None

    def _read(self):
        if self.master is None:
            return
        # Bound reads so a noisy child cannot stall telemetry/display updates.
        for _ in range(8):
            try:
                chunk = os.read(self.master, 4096)
            except (BlockingIOError, OSError):
                break
            if not chunk:
                break
            self.output = (self.output + chunk.decode(errors='replace'))[-16384:]
        plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', self.output)
        code = re.search(r'(?m)^\s*([A-Z0-9]{4}-[A-Z0-9]{5})\s*$', plain)
        if 'https://auth.openai.com/codex/device' in plain and code:
            self.code = code.group(1)
            self.stage = 'login'

    def _release(self):
        if self.master is not None:
            os.close(self.master)
            self.master = None
        self.process = None
        self.code = None

    def _failed(self, reloading=False):
        self._release()
        self.stage = 'reload_retry' if reloading else 'retry'
        self.retry_at = self.clock() + 60

    def tick(self, snapshot):
        now = self.clock()
        required = snapshot.get('auth_required', False)
        if self.process is not None:
            if self.stage != 'reloading':
                self._read()
            result = self.process.poll()
            deadline = 30 if self.stage == 'reloading' else 15 * 60
            if result is None and now - self.started >= deadline:
                reloading = self.stage == 'reloading'
                self.close()
                self._failed(reloading)
            elif result is not None:
                success = result == 0 and (
                    self.stage == 'reloading' or 'Successfully logged in' in self.output)
                reloading = self.stage == 'reloading'
                self._release()
                if success:
                    self.stage = None if reloading else 'reload_pending'
                    self.retry_at = now + 60 if reloading else 0
                else:
                    self._failed(reloading)
        if self.stage == 'reload_retry' and now >= self.retry_at:
            self.stage = 'reload_pending'
        if self.stage == 'reload_pending':
            # Restart only after observed local agents are inactive. Remote agents
            # are unaffected; unavailable local counts cannot prove it is safe.
            if snapshot.get('available') and snapshot.get('counts', {}).get('active') == 0:
                try:
                    self.process = subprocess.Popen(
                        self.restart_command,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, start_new_session=True,
                        env={**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}'},
                    )
                    self.started = now
                    self.stage = 'reloading'
                except OSError:
                    self._failed(reloading=True)
        elif self.process is None and self.stage != 'reload_retry':
            if not required:
                self.stage = None
            elif now >= self.retry_at:
                try:
                    self._start_login()
                except OSError:
                    self._failed()
        if self.stage:
            snapshot['auth_recovery'] = {
                'state': self.stage,
                'url': 'https://auth.openai.com/codex/device',
                'code': self.code,
                # Slightly conservative: login could issue the code after launch.
                'expires_in_minutes': max(0, int((900 - (now - self.started)) / 60)),
            }
        return snapshot

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self._release()
