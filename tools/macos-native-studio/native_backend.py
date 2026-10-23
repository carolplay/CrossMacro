"""Typed local backend. No CUA process, generated JS, model, or session credentials."""
import base64
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import time
import uuid

NATIVE_VERSION = '0.1.0'

class NativeBackend:
    native_protocol = True
    def __init__(self, config):
        self.config = config
        self.socket_path = Path(config.get('native_socket', str(Path.home() / 'Library/Application Support/Macro Studio/control.sock')))
        self.session = None
        self.deadline = time.monotonic() + 120
        self.status = None
    def request(self, op, **params):
        st = self.socket_path.stat()
        if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise PermissionError('Native socket ownership/mode invalid')
        params.update(op=op)
        if self.session: params['session'] = self.session
        timeout = min(60, self.deadline - time.monotonic())
        if timeout <= 0: raise TimeoutError('Native operation deadline exceeded')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout); s.connect(str(self.socket_path)); s.sendall(json.dumps(params).encode() + b'\n')
            data = bytearray()
            while b'\n' not in data:
                chunk = s.recv(65536)
                if not chunk: raise ConnectionError('Native app closed response')
                data.extend(chunk)
                if len(data) > 32 * 1024 * 1024: raise ValueError('Native response exceeds frame limit')
        reply = json.loads(data.split(b'\n', 1)[0])
        if not reply.get('ok'): raise PermissionError('Native operation blocked: ' + str(reply.get('error')))
        return reply['result']
    def start(self):
        self.status = self.request('status')
        if self.status.get('cua_dependency') is not False: raise ValueError('Native backend capability mismatch')
        if not self.status.get('input_enabled'): raise PermissionError('Enable input in Macro Studio first')
        expected = self.config.get('native_expected_size')
        wid = self.config.get('native_window_id')
        if not isinstance(wid, int) or not isinstance(expected, list): raise ValueError('Explicit native window ID and size required')
        actual_lock = Path(self.status['lock_file']).resolve()
        required_lock = Path(self.config['native_lock_file']).resolve()
        if actual_lock != required_lock: raise ValueError('Native app must use the configured shared device lock')
        self.session = self.request('begin', window_id=wid, expected_size=expected,
                                    run_id=self.config.get('native_run_id', str(uuid.uuid4())))['session']
        # OCR executable belongs to the same built app; it only reads saved files.
        ocr = Path(self.status['app_path']) / 'Contents/Tools/vision-ocr'
        if not ocr.is_file(): self.close(); raise FileNotFoundError('Bundled OCR missing')
        self.config['ocr_binary'] = str(ocr)
    def click(self, point): return self.request('click', point=point)
    def key(self, key, count=1, duration_ms=600):
        if type(count) is not int or not 1 <= count <= 20: raise ValueError('Invalid key count')
        for _ in range(count): self.request('key', key=key, duration_ms=duration_ms)
    def observe(self, folder, label, expected_size):
        import viewport_calibration as viewport
        from window_macro import Observation, FatalExecutionError
        reply = self.request('screenshot')
        data = base64.b64decode(reply['png_base64'], validate=True)
        path = Path(folder) / (label + '.png'); path.write_bytes(data)
        from PIL import Image
        with Image.open(path) as im: size = list(im.size)
        calibrated = viewport.calibration(self.config, expected_size)
        native_size = calibrated['native_size'] if calibrated else expected_size
        if size != native_size: raise FatalExecutionError('Window size changed: %s expected %s' % (size, native_size))
        ocr = reply['ocr']
        if calibrated:
            viewport.normalize_frame(path, calibrated)
            result = subprocess.run([self.config['ocr_binary'], str(path), self.config.get('language', 'zh-Hans')],
                                    capture_output=True, text=True, check=True, timeout=15)
            ocr = json.loads(result.stdout)
        if [ocr['width'], ocr['height']] != expected_size: raise FatalExecutionError('Native OCR size mismatch')
        (Path(folder)/(label+'-ocr.json')).write_text(json.dumps(ocr,ensure_ascii=False,indent=2))
        return Observation('\n'.join(line['text'] for line in ocr['lines']), path, ocr,
                           {'binary':self.config['ocr_binary'], 'language':self.config.get('language','zh-Hans'),
                            'templates':self.config.get('image_templates',{})})
    def close(self):
        if self.session:
            self.deadline = time.monotonic() + 10  # Cleanup only; never extends input retries.
            try: self.request('end')
            finally: self.session = None
