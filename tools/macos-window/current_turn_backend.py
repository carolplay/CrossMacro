"""Typed file handoff to the official CUA tool in the active conversation.

This module never launches CUA, obtains host identity, or grants permissions.
One request is consumed once by the reviewed controller; ambiguous input stops.
"""
import base64
import json
import os
import time
from pathlib import Path
from window_macro import CuaMcp, FatalExecutionError, WorkflowBudgetExceeded

BRIDGE_VERSION = '0.1.2'


class CurrentTurnBackend(CuaMcp):
    native_protocol = True  # Use typed click/key dispatch, not generated JavaScript.

    def __init__(self, config):
        self.config = config
        self.root = Path(config['current_turn_bridge']).resolve()
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.next_id = 0
        self.deadline = time.monotonic() + 120
        self.failed = False
        self.closed = False
        Path(config['log_dir']).mkdir(parents=True, exist_ok=True)
        self.journal = Path(config['log_dir']) / 'current-turn-transport.jsonl'

    def _write(self, path, value):
        tmp = path.with_suffix('.new')
        tmp.write_text(json.dumps(value, ensure_ascii=False))
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    def _request(self, operation, **parameters):
        if self.closed or self.failed:
            raise FatalExecutionError('Current-turn transport stopped; no automatic retry')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise WorkflowBudgetExceeded('Budget exhausted before current-turn request')
        self.next_id += 1
        request = {'protocol': 1, 'id': self.next_id, 'operation': operation,
                   'parameters': parameters, 'expires_unix': time.time() + remaining}
        self._write(self.root / 'request.json', request)
        try:
            while time.monotonic() < self.deadline:
                response = self.root / 'response.json'
                if response.exists():
                    value = json.loads(response.read_text())
                    if value.get('id') != self.next_id:
                        raise FatalExecutionError('Current-turn response ID mismatch')
                    response.unlink()
                    if not value.get('ok'):
                        raise FatalExecutionError('Official current-turn CUA stopped: ' + str(value.get('error')))
                    with self.journal.open('a') as log:
                        log.write(json.dumps({'id': self.next_id, 'operation': operation,
                                              'parameters': parameters, 'completed_unix': time.time()}) + '\n')
                    return value
                time.sleep(0.05)
            raise TimeoutError('Current-turn request timed out; effect unknown, never replay automatically')
        except BaseException:
            self.failed = True
            self._write(self.root / 'stopped.json', {'id': self.next_id, 'reason': 'failed_or_ambiguous'})
            raise

    def start(self):
        self._request('bind', app_path=self.config['target']['app_path'])

    def click(self, point):
        if len(point) != 2 or any(type(v) not in (int, float) for v in point):
            raise ValueError('Expected native point')
        return self._request('click', point=list(point))

    def key(self, key, count=1, duration_ms=600):
        if not isinstance(key, str) or not 1 <= count <= 100 or not 1 <= duration_ms <= 2000:
            raise ValueError('Invalid typed key request')
        # One input per handoff keeps each official tool operation bounded.
        result = None
        for _ in range(count):
            result = self._request('key', key=key, count=1, duration_ms=duration_ms)
        return result

    def original_screenshot_bytes(self):
        value = self._request('observe')
        path = self.root / ('frame-%s.bin' % value['id'])
        try:
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    def js(self, code):
        # The inherited image/OCR pipeline has one fixed observation call.
        if code != 'await target.getAXStateAndScreenshot();':
            raise ValueError('Arbitrary JavaScript is not supported by current-turn transport')
        data = self.original_screenshot_bytes()
        mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
        return {'content': [{'type': 'image', 'mimeType': mime,
                             'data': base64.b64encode(data).decode('ascii')}]}

    def close(self):
        self.closed = True
        self._write(self.root / 'closed.json', {'closed_unix': time.time(), 'failed': self.failed})
        if hasattr(self, '_observation_store'):
            self._observation_store.close()
            del self._observation_store
        for path in self.root.glob('frame-*.bin'):
            path.unlink()
