#!/usr/bin/env python3
"""Deterministic window macros for CrossMacro's existing Shell action.

Requires the user's installed CUA MCP runtime; does not bundle it or call models.
Only fixed observe/click operations are supported. All identity and machine
configuration belongs outside the repository, as do screenshots and run logs.
"""
import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import queue
import re
import shlex
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import unicodedata
import uuid


class FatalExecutionError(RuntimeError):
    """Identity or environment failure; recovery must not send more input."""


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).translate(str.maketrans({'級':'级'})).split())


def number_in_region(observation, bounds):
    """Read exactly one integer from a calibrated inventory region."""
    if not isinstance(observation, Observation) or not observation.ocr_data:
        raise RuntimeError('Inventory checks require fresh local OCR geometry')
    values = []
    data = observation.ocr_data
    left, top, right, bottom = bounds
    for line in data['lines']:
        x, y, w, h = line['bounds']
        cx, cy = (x + w / 2) * data['width'], (y + h / 2) * data['height']
        # The game's adjacent plus icon is sometimes merged into the number.
        value = normalize(line['text']).replace(',', '')
        if value.endswith('+'): value = value[:-1]
        if (left <= cx <= right and top <= cy <= bottom and line.get('confidence', 0) >= .5
            and re.fullmatch(r'[0-9]+', value)):
            values.append(int(value))
    if len(values) != 1:
        raise RuntimeError('Expected exactly one inventory integer in region')
    return values[0]


class Observation(str):
    def __new__(cls, text, image_path, ocr_data=None, ocr_config=None):
        value = super().__new__(cls, text)
        value.image_path = image_path
        value.ocr_data = ocr_data
        value.ocr_config = ocr_config
        value.timer_regions = {}
        value.visual_checks = []
        return value


def require_text(text, required):
    if isinstance(required, dict):
        unknown = set(required) - {'all', 'any', 'none', 'timer_seconds', 'green_regions', 'text_regions'}
        if unknown:
            raise ValueError('Unknown OCR conditions: ' + ', '.join(sorted(unknown)))
        require_text(text, required.get('all', []))
        value = normalize(text)
        choices = required.get('any', [])
        if choices and not any(normalize(s) in value for s in choices):
            raise RuntimeError('OCR condition failed: no alternative matched')
        if any(normalize(s) in value for s in required.get('none', [])):
            raise RuntimeError('OCR condition failed: forbidden text remains')
        for region in required.get('text_regions', []):
            if not isinstance(text, Observation) or not text.ocr_data:
                raise RuntimeError('Regional text requires fresh OCR geometry')
            left, top, right, bottom = region['bounds']
            data = text.ocr_data
            matches = []
            for line in data['lines']:
                x, y, w, h = line['bounds']
                cx, cy = (x + w / 2) * data['width'], (y + h / 2) * data['height']
                if (left <= cx <= right and top <= cy <= bottom and line.get('confidence', 0) >= region.get('min_confidence',.5)
                    and re.fullmatch(region['pattern'], normalize(line['text']))):
                    matches.append(line['text'])
            if len(matches) != 1:
                raise RuntimeError('Expected exactly one matching regional text value')
            text.visual_checks.append({'regional_text': matches[0], 'bounds': region['bounds']})
        if 'timer_seconds' in required:
            # Preserve line boundaries: joining a timer to the following
            # numeric hourly rate makes an otherwise valid timer unreadable.
            limits = required['timer_seconds']
            timer_text = text
            if 'bounds' in limits:
                if not isinstance(text, Observation) or not text.ocr_data:
                    raise RuntimeError('Regional timers require fresh local OCR geometry')
                left, top, right, bottom = limits['bounds']
                data = text.ocr_data
                selected = []
                for line in data['lines']:
                    x,y,w,h = line['bounds']
                    cx,cy = (x+w/2)*data['width'],(y+h/2)*data['height']
                    if left <= cx <= right and top <= cy <= bottom:
                        selected.append(line['text'])
                timer_text = '\n'.join(selected)
            timer_text = unicodedata.normalize('NFKC', timer_text)
            timers = re.findall(r'(?<!\d)(\d{2})\s*:\s*(\d{2})\s*:\s*(\d{2})(?!\d)', timer_text)
            if len(timers) != 1 and 'bounds' in limits and isinstance(text,Observation) and text.ocr_config:
                # Retry OCR on an enlarged local crop; never guess missing digits
                # or capture another image merely to recover tiny punctuation.
                key=tuple(limits['bounds'])
                if key not in text.timer_regions:
                    from PIL import Image
                    derived=Path(text.image_path).parent/'derived';derived.mkdir(exist_ok=True)
                    stem=Path(text.image_path).stem+'-timer-'+('-'.join(map(str,key)))
                    crop=derived/(stem+'.png')
                    with Image.open(text.image_path) as image:
                        region=image.crop(key);region.resize((region.width*4,region.height*4),Image.Resampling.LANCZOS).save(crop)
                    raw=subprocess.run([text.ocr_config['binary'],str(crop),text.ocr_config['language']],capture_output=True,text=True,check=True,timeout=15)
                    data=json.loads(raw.stdout);(derived/(stem+'-ocr.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
                    text.timer_regions[key]='\n'.join(line['text'] for line in data['lines'])
                timer_text=unicodedata.normalize('NFKC',text.timer_regions[key])
                timers=re.findall(r'(?<!\d)(\d{2})\s*:\s*(\d{2})\s*:\s*(\d{2})(?!\d)',timer_text)
                if len(timers)!=1:
                    # A calibrated timer-only crop may lose a separator, never
                    # a digit. Accept exactly six digits and known separators;
                    # the normal clock/range checks below still apply.
                    recovered=re.fullmatch(r'\s*(\d{2})\s*[:.;,]?\s*(\d{2})\s*[:.;,]?\s*(\d{2})\s*',timer_text)
                    if recovered:
                        timers=[recovered.groups()]
                        text.visual_checks.append({'timer_format_recovered':'six_digits_in_timer_only_crop','raw_ocr':timer_text})
            if len(timers) != 1:
                raise RuntimeError('Expected exactly one readable HH:MM:SS timer')
            hours, minutes, seconds = map(int, timers[0])
            if minutes > 59 or seconds > 59:
                raise RuntimeError('Invalid OCR timer')
            total = hours * 3600 + minutes * 60 + seconds
            if isinstance(text, Observation):
                text.visual_checks.append({'timer_seconds':total,'bounds':limits.get('bounds')})
            if not limits.get('min', 0) <= total <= limits.get('max', 359999):
                raise RuntimeError('OCR timer outside required range: ' + str(total))
        for region in required.get('green_regions', []):
            if not isinstance(text, Observation):
                raise RuntimeError('Color conditions require a fresh image observation')
            from PIL import Image
            with Image.open(text.image_path) as image:
                left, top, right, bottom = region['bounds']
                if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                    raise ValueError('Color region is outside the observed window')
                pixels = image.convert('RGB').crop((left,top,right,bottom)).tobytes()
            ratio = sum(g > 100 and g > 1.25*r and g > 1.1*b
                        for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3])) / (len(pixels)//3)
            text.visual_checks.append({'bounds':region['bounds'], 'green_fraction':ratio})
            if not region.get('min', 0) <= ratio <= region.get('max', 1):
                raise RuntimeError('Button color condition failed: green fraction ' + str(ratio))
        return
    missing = [s for s in required if not s or normalize(s) not in normalize(text)]
    if missing:
        raise RuntimeError('OCR condition failed: ' + ', '.join(missing))


def validate_condition(condition, size):
    if isinstance(condition, list):
        if not condition or any(not isinstance(s,str) or not s for s in condition):
            raise ValueError('OCR conditions must contain nonempty text')
        return
    if not isinstance(condition, dict) or not condition:
        raise ValueError('Expected OCR text list or condition object')
    if set(condition) - {'all','any','none','timer_seconds','green_regions','text_regions'}:
        raise ValueError('Unknown local observation condition')
    if not condition.get('all') and not condition.get('any'):
        raise ValueError('Conditions require a positive page-text assertion')
    for key in ('all','any','none'):
        if key in condition:
            validate_condition(condition[key],size)
    if 'timer_seconds' in condition:
        limits = condition['timer_seconds']
        if (not isinstance(limits,dict) or not limits or set(limits)-{'min','max','bounds'}
            or any(type(v) is not int or v < 0 for k,v in limits.items() if k != 'bounds')
            or limits.get('min',0) > limits.get('max',359999)):
            raise ValueError('Invalid timer limits')
        if 'bounds' in limits:
            bounds=limits['bounds']
            if (not isinstance(bounds,list) or len(bounds)!=4
                or any(type(v) is not int for v in bounds)
                or not 0 <= bounds[0] < bounds[2] <= size[0]
                or not 0 <= bounds[1] < bounds[3] <= size[1]):
                raise ValueError('Invalid timer OCR region')
    for region in condition.get('green_regions',[]):
        bounds = region['bounds']
        if (len(bounds) != 4 or any(type(v) is not int for v in bounds)
            or not 0 <= bounds[0] < bounds[2] <= size[0]
            or not 0 <= bounds[1] < bounds[3] <= size[1]
            or not 0 <= region.get('min',0) <= region.get('max',1) <= 1):
            raise ValueError('Invalid button color region')
    for region in condition.get('text_regions', []):
        bounds=region.get('bounds', [])
        if (len(bounds)!=4 or any(type(v) is not int for v in bounds)
            or not 0<=bounds[0]<bounds[2]<=size[0] or not 0<=bounds[1]<bounds[3]<=size[1]
            or not isinstance(region.get('pattern'),str) or len(region['pattern'])>200
            or not 0<=region.get('min_confidence',.5)<=1):
            raise ValueError('Invalid regional text assertion')
        re.compile(region['pattern'])



def resolve_point(step, observation, size):
    """Resolve one bounded OCR label locally; ambiguity never sends input."""
    if step.get('green_target'):
        from PIL import Image
        target=step['green_target'];left,top,right,bottom=target['bounds']
        with Image.open(observation.image_path) as image:
            data=image.convert('RGB').crop((left,top,right,bottom)).tobytes()
        width=right-left
        pixels={i for i,(r,g,b) in enumerate(zip(data[::3],data[1::3],data[2::3]))
                if g>100 and g>1.5*r and g>1.8*b}
        matches=[]
        while pixels:
            first=pixels.pop();component=[first];pending=[first]
            while pending:
                n=pending.pop();x=n%width
                neighbors=[n-width,n+width]+([n-1] if x else [])+([n+1] if x+1<width else [])
                for neighbor in neighbors:
                    if neighbor in pixels:pixels.remove(neighbor);pending.append(neighbor);component.append(neighbor)
            xs=[n%width for n in component];ys=[n//width for n in component]
            if target.get('min_pixels',80)<=len(component)<=target.get('max_pixels',2000) and max(xs)-min(xs)<=70 and max(ys)-min(ys)<=70:
                dx,dy=target.get('offset',[0,0]);matches.append([left+(min(xs)+max(xs))//2+dx,top+(min(ys)+max(ys))//2+dy])
        if len(matches)!=1:raise RuntimeError('Expected one calibrated green marker; found '+str(len(matches)))
        point=matches[0]
        if not all(0<=v<size[i] for i,v in enumerate(point)):raise RuntimeError('Green target outside reference window')
        return point
    target=step.get('text_target')
    if not target:
        return step['point']
    if not isinstance(observation,Observation) or not observation.ocr_data:
        raise RuntimeError('Text targets require fresh local OCR geometry')
    left,top,right,bottom=target['bounds'];matches=[]
    for line in observation.ocr_data['lines']:
        value=normalize(line['text']);label=normalize(target['text'])
        if not (value==label if target.get('exact',True) else label in value):continue
        if line.get('confidence',0)<target.get('min_confidence',.8):continue
        x,y,w,h=line['bounds'];cx,cy=(x+w/2)*size[0],(y+h/2)*size[1]
        if left<=cx<=right and top<=cy<=bottom:
            offset=target.get('offset',[0,0])
            point=[round(cx)+offset[0],round(cy)+offset[1]]
            if not all(0 <= v < size[i] for i,v in enumerate(point)):
                raise RuntimeError('OCR target resolves outside the reference window')
            matches.append(point)
    if len(matches)!=1:raise RuntimeError('Expected exactly one confident text target; found '+str(len(matches)))
    return matches[0]


def validate_workflow(workflow):
    size = workflow['reference_size']
    if len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError('reference_size must contain two positive integers')
    names = set()
    for step in workflow['steps']:
        if step['name'] in names:
            raise ValueError('Step names must be unique')
        names.add(step['name'])
        if step['action'] not in ('observe', 'click') or not step.get('before'):
            raise ValueError('Every step requires an observe/click action and OCR preconditions')
        for key in ('before','after','skip_if'):
            if key in step:
                validate_condition(step[key],size)
        if step['action'] == 'click':
            if sum(key in step for key in ('point','text_target','green_target'))!=1:
                raise ValueError('A click requires exactly one point, text_target or green_target')
            if 'green_target' in step:
                target=step['green_target'];bounds=target.get('bounds',[]);offset=target.get('offset',[0,0])
                if (set(target)-{'bounds','offset','min_pixels','max_pixels'} or len(bounds)!=4
                    or any(type(v) is not int for v in bounds+offset) or len(offset)!=2
                    or not 0<=bounds[0]<bounds[2]<=size[0] or not 0<=bounds[1]<bounds[3]<=size[1]
                    or not 1<=target.get('min_pixels',80)<=target.get('max_pixels',2000)<=5000):
                    raise ValueError('Invalid calibrated green marker target')
            if 'text_target' in step:
                target=step['text_target']
                if not isinstance(target,dict):raise ValueError('text_target must be an object')
                bounds=target.get('bounds',[])
                if (set(target)-{'text','bounds','exact','min_confidence','offset'}
                    or not isinstance(target.get('text'),str) or not normalize(target['text'])
                    or type(target.get('exact',True)) is not bool
                    or not isinstance(target.get('offset',[0,0]),list)
                    or len(target.get('offset',[0,0])) != 2
                    or any(type(v) is not int or abs(v)>max(size) for v in target.get('offset',[0,0]))
                    or not 0 <= target.get('min_confidence',.8) <= 1
                    or len(bounds)!=4 or any(type(v) is not int for v in bounds)
                    or not 0<=bounds[0]<bounds[2]<=size[0]
                    or not 0<=bounds[1]<bounds[3]<=size[1]):
                    raise ValueError('Invalid bounded OCR text target')
            point = step.get('point',[0,0])
            if len(point) != 2 or any(type(v) is not int or not 0 <= v < size[i] for i, v in enumerate(point)):
                raise ValueError('Click is outside reference window')
            if not step.get('after'):
                raise ValueError('Every click requires OCR completion conditions')
        attempts = step.get('observe_attempts', 1)
        if type(attempts) is not int or not 1 <= attempts <= 30:
            raise ValueError('observe_attempts must be between 1 and 30')
        for key in ('remember_numbers', 'unchanged_numbers'):
            for item in step.get(key, []):
                bounds = item.get('bounds', [])
                if (not isinstance(item.get('name'), str) or not item['name']
                    or len(bounds) != 4 or any(type(v) is not int for v in bounds)
                    or not 0 <= bounds[0] < bounds[2] <= size[0]
                    or not 0 <= bounds[1] < bounds[3] <= size[1]):
                    raise ValueError('Invalid inventory snapshot region')


class CuaMcp:
    def __init__(self, config):
        Path(config['log_dir']).expanduser().mkdir(parents=True, exist_ok=True)
        server = json.loads(Path(config['mcp_manifest']).read_text())['mcpServers']['cua_repl']
        env = {k: os.environ[k] for k in ('HOME','PATH','TMPDIR','USER','LOGNAME','LANG') if k in os.environ}
        # No caller session identity, sockets, tokens, or approval context.
        # Copy only launcher settings, not arbitrary secret environment values.
        for key, value in server.get('env', {}).items():
            if key.startswith(('NODE_REPL_', 'CUA_REPL_', 'BROWSER_USE_')) or key in ('SKY_CUA_SERVICE_PATH','CODEX_CLI_PATH'):
                env[key] = value
        env['CUA_REPL_ENABLED_SURFACES'] = 'computer'
        self.proc = subprocess.Popen([server['command'], *server['args']], env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True, cwd=config['log_dir'])
        self.config, self.messages, self.errors, self.next_id = config, queue.Queue(), [], 0
        self.deadline = time.monotonic() + min(120, config.get('timeout_seconds',45))
        self.reader_thread=threading.Thread(target=self._read,daemon=True)
        self.error_thread=threading.Thread(target=self._read_errors,daemon=True)
        self.reader_thread.start()
        self.error_thread.start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                pass
        self.messages.put({'closed':True})

    def _read_errors(self):
        for line in self.proc.stderr:
            if len(self.errors) < 30:
                self.errors.append(line[:1000])

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + '\n')
        self.proc.stdin.flush()

    def request(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        self.send({'jsonrpc':'2.0','id':request_id,'method':method,'params':params})
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('MCP operation deadline exceeded')
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError('MCP timed out during %s: %s' % (method, ''.join(self.errors)[-1500:])) from exc
            if message.get('closed'):
                raise RuntimeError('MCP closed: ' + ''.join(self.errors)[-1500:])
            if message.get('method') == 'elicitation/create':
                meta = message.get('params',{}).get('_meta',{})
                # Local config represents the user's authorization. Never
                # accept a different connector, application, or capability.
                allowed = (meta.get('connector_id') == 'computer-use'
                    and meta.get('tool_params',{}).get('app') == self.config['target']['bundle_id']
                    and meta.get('tool_name') in set(self.config.get('authorized_tools',[])) & {'get_app_state','get_app_screenshot','click'})
                self.send({'jsonrpc':'2.0','id':message['id'],'result':
                    {'action':'accept','content':{}} if allowed else {'action':'decline'}})
                continue
            if 'method' in message:
                if 'id' in message:
                    self.send({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Unsupported client method'}})
                continue
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(str(message['error']))
                result = message['result']
                if result.get('isError'):
                    raise RuntimeError('MCP operation failed: ' + str(result.get('content'))[:1000])
                return result

    def start(self):
        self.request('initialize', {'protocolVersion':'2025-06-18',
            'capabilities':{'elicitation':{'form':{}}},
            'clientInfo':{'name':'crossmacro-window-macro','version':'0.1'}})
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
        self.js('var target = await cua.getApp(%s);' % json.dumps(self.config['target']['app_path']))

    def js(self, code):
        return self.request('tools/call', {'name':'js','arguments':{'code':code,'title':'CrossMacro authorized window macro'}})

    def observe(self, folder, label, expected_size):
        result = self.js('await target.getAXStateAndScreenshot();')
        images = [c for c in result.get('content',[]) if c.get('type') == 'image']
        if len(images) != 1:
            raise RuntimeError('Expected one target-window screenshot')
        data = base64.b64decode(images[0]['data'], validate=True)
        mime = images[0].get('mimeType')
        if mime not in ('image/png','image/jpeg'):
            raise RuntimeError('Unsupported screenshot image type: ' + str(mime))
        path = folder / (label + ('.png' if mime == 'image/png' else '.jpg'))
        path.write_bytes(data)
        raw = subprocess.run([self.config['ocr_binary'],str(path),self.config.get('language','en-US')],
            capture_output=True,text=True,check=True,timeout=15)
        ocr = json.loads(raw.stdout)
        (folder/(label+'-ocr.json')).write_text(json.dumps(ocr,ensure_ascii=False,indent=2))
        size = [ocr['width'],ocr['height']]
        if size != expected_size:
            raise FatalExecutionError('Window size changed: %s; expected %s. Recalibrate before input.' % (size,expected_size))
        return Observation('\n'.join(line['text'] for line in ocr['lines']), path, ocr, {'binary':self.config['ocr_binary'],'language':self.config.get('language','en-US')})

    def close(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
        self.reader_thread.join(timeout=1)
        self.error_thread.join(timeout=1)
        self.proc.stdin.close()
        if not self.reader_thread.is_alive(): self.proc.stdout.close()
        if not self.error_thread.is_alive(): self.proc.stderr.close()


def execute(config, workflow, step_name, backend=None):
    validate_workflow(workflow)
    steps = workflow['steps'] if step_name == 'all' else [s for s in workflow['steps'] if s['name'] == step_name]
    if not steps:
        raise ValueError('Unknown step: ' + step_name)
    log_dir = Path(config['log_dir']).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir/'.window-macro.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard = config.get('guard_command',[])
        if guard:
            state = json.loads(subprocess.check_output(guard,text=True,timeout=10))
            if state.get('active') is not None:
                raise FatalExecutionError('Existing game coordinator has an active executor')
        folder = log_dir / (time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        folder.mkdir()
        report = {'status':'running','step':step_name,'started_unix':time.time(),
            'runtime_model_calls':0,'chat_identity_supplied':False,'steps':[]}
        client = backend
        try:
            if client is None:
                client = CuaMcp(config)
                client.start()
            else:
                client.deadline = time.monotonic() + min(120,config.get('timeout_seconds',45))
            inventory = {}
            for index, step in enumerate(steps):
                before = client.observe(folder, '%02d-before'%index, workflow['reference_size'])
                skipped = False
                for attempt in range(step.get('observe_attempts', 1)):
                    if step.get('skip_if'):
                        try:
                            require_text(before, step['skip_if'])
                        except RuntimeError:
                            pass
                        else:
                            skipped = True
                            break
                    try:
                        require_text(before, step['before'])
                        break
                    except RuntimeError:
                        if attempt + 1 == step.get('observe_attempts', 1):
                            raise
                        before = client.observe(folder, '%02d-before-retry-%02d' % (index, attempt + 1), workflow['reference_size'])
                if skipped:
                    report['steps'].append({'name':step['name'], 'skipped':True,
                                           'reason':'Explicit local observation skip condition matched',
                                           'visual_checks':getattr(before,'visual_checks',[])})
                    print(json.dumps({'status':'step_skipped','step':step['name']},ensure_ascii=False),flush=True)
                    continue
                if step.get('verify_identity'):
                    identity = config.get('identity_text',[])
                    if not identity:
                        raise FatalExecutionError('Identity assertions are required in local config')
                    try:
                        require_text(before, identity)
                    except RuntimeError as exc:
                        raise FatalExecutionError('Identity mismatch: ' + str(exc)) from exc
                entry = {'name':step['name'],'before_verified':True,
                         'verified_before_conditions':step['before'],
                         'identity_verified':bool(step.get('verify_identity')),
                         'visual_checks':getattr(before,'visual_checks',[])}
                report['steps'].append(entry)
                for item in step.get('remember_numbers', []):
                    inventory[item['name']] = number_in_region(before, item['bounds'])
                    entry.setdefault('remembered_numbers', {})[item['name']] = inventory[item['name']]
                for item in step.get('unchanged_numbers', []):
                    value = number_in_region(before, item['bounds'])
                    if item['name'] not in inventory or value != inventory[item['name']]:
                        raise FatalExecutionError('Inventory changed unexpectedly: ' + item['name'])
                    entry.setdefault('unchanged_numbers', {})[item['name']] = value
                if step['action'] == 'click':
                    point=resolve_point(step,before,workflow['reference_size'])
                    entry['resolved_point']=point
                    capture = None
                    audio_spec = config.get('audio_feedback',{}).get(step.get('audio_event'))
                    if audio_spec:
                        try:
                            from audio_feedback import AudioCapture
                            capture = AudioCapture(config['audio_capture']['binary'],config['target']['bundle_id'],folder/'audio',audio_spec.get('window_seconds',2))
                            capture.wait_ready()
                        except Exception as exc:
                            entry['audio_feedback']={'status':'unavailable','reason':str(exc)}
                            if capture: capture.stop();capture=None
                    entry['click_unix'] = time.time()
                    try:
                        client.js('await target.click(%s); await target.getAXState();' % json.dumps(point))
                    finally:
                        if capture:
                            try: capture.proc.wait(timeout=audio_spec.get('window_seconds',2)+3)
                            except subprocess.TimeoutExpired: pass
                            entry['audio_capture']=capture.stop()
                    if capture and entry['audio_capture'].get('usable_audio'):
                        from audio_feedback import classify
                        try:
                            feedback=classify(entry['audio_capture']['wav'],{step['audio_event']:audio_spec['template']},audio_spec.get('threshold',.8))
                        except Exception as exc:
                            feedback={'status':'unavailable','reason':str(exc)}
                        entry['audio_feedback']=feedback
                        if feedback['status']=='candidate':
                            entry['after_deferred_to_check']=True
                            entry['deferred_after_conditions']=step['after']
                            entry['screenshots_removed']=1
                            entry['ocr_calls_removed']=1
                            print(json.dumps({'status':'audio_confirmed_transition','step':step['name']},ensure_ascii=False),flush=True)
                            continue
                    # Re-observe after the action; no blind retries or model.
                    # Retry observations only: an animation must never cause a
                    # duplicate claim, purchase or other repeated input.
                    for attempt in range(step.get('observe_attempts', 1)):
                        after = client.observe(folder,'%02d-after-%02d'%(index,attempt), workflow['reference_size'])
                        try:
                            require_text(after,step['after'])
                            break
                        except RuntimeError:
                            if attempt + 1 == step.get('observe_attempts', 1):
                                raise
                    entry['after_verified'] = True
                    entry['after_observations'] = attempt + 1
                    entry['after_visual_checks'] = getattr(after,'visual_checks',[])
                print(json.dumps({'status':'step_passed','step':step['name']},ensure_ascii=False),flush=True)
            report['status'] = 'passed'
        except (Exception, KeyboardInterrupt) as exc:
            report.update(status='failed',error=str(exc))
            raise
        finally:
            if client is not None and backend is None:
                client.close()
            report['ended_unix'] = time.time()
            (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({'status':report['status'],'result':str(folder/'result.json')}),flush=True)


def export_macro(config_path, workflow_path, output):
    workflow = json.loads(workflow_path.read_text())
    validate_workflow(workflow)
    lines = ['# Name: '+workflow['name'], '# Format: CrossMacroFormatV4', '# IsAbsolute: False',
             '# SkipInitialZero: True', '[Script]']
    for step in workflow['steps']:
        argv = [sys.executable,str(Path(__file__).resolve()),'request','--config',str(config_path.resolve()),
                '--workflow',str(workflow_path.resolve()),'--step',step['name']]
        # CrossMacro expands $variables before /bin/sh parses the command.
        # Reject such paths rather than emitting a subtly different command.
        command = shlex.join(argv)
        if '$' in command or '\n' in command or '\r' in command:
            raise ValueError('Export paths cannot contain $, CR or LF')
        lines.append('shell '+json.dumps(command,ensure_ascii=False)+' 0 0 60000')
    lines.append('[Events]')
    output.write_text('\n'.join(lines)+'\n')
    print(str(output.resolve()))


def receive_json(connection):
    data = bytearray()
    while b'\n' not in data:
        chunk = connection.recv(4096)
        if not chunk:
            raise RuntimeError('Worker connection closed')
        data.extend(chunk)
        if len(data) > 65536:
            raise ValueError('Worker message too large')
    return json.loads(data.split(b'\n',1)[0])


def worker_request(config, step):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(100)
        connection.connect(config['worker_socket'])
        connection.sendall((json.dumps({'step':step})+'\n').encode())
        result = receive_json(connection)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if not result.get('ok'):
            raise RuntimeError(result.get('error','Window worker failed'))


def serve(config, workflow):
    """Serialize fixed workflow requests; no arbitrary code or config over IPC."""
    validate_workflow(workflow)
    path = Path(config['worker_socket'])
    if not path.is_absolute():
        raise ValueError('worker_socket must be absolute')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.parent.stat().st_uid != os.getuid() or stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise ValueError('Worker socket directory must be private to the current user (0700)')
    if path.exists():
        # Do not replace an active worker or a non-socket file.
        if not stat.S_ISSOCK(path.stat().st_mode):
            raise ValueError('Refusing to replace a non-socket file')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise RuntimeError('Window worker is already running')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path))
        os.chmod(path,0o600)
        server.listen(1)
        backend = CuaMcp(config)
        try:
            backend.start()
            print(json.dumps({'status':'worker_ready','socket':str(path),'pid':os.getpid()}),flush=True)
            while True:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(100)
                    try:
                        request = receive_json(connection)
                        if set(request) != {'step'} or not isinstance(request['step'],str):
                            raise ValueError('Only a fixed workflow step name is accepted')
                        execute(config,workflow,request['step'],backend=backend)
                        result = {'ok':True,'step':request['step']}
                    except Exception as exc:
                        result = {'ok':False,'error':str(exc)}
                    connection.sendall((json.dumps(result)+'\n').encode())
        finally:
            backend.close()
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['execute','export','serve','request'])
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--workflow',type=Path,required=True)
    parser.add_argument('--step',default='all')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.command == 'export':
        if args.output is None:
            parser.error('export requires --output')
        export_macro(args.config,args.workflow,args.output)
    elif args.command == 'serve':
        serve(json.loads(args.config.read_text()),json.loads(args.workflow.read_text()))
    elif args.command == 'request':
        worker_request(json.loads(args.config.read_text()),args.step)
    else:
        execute(json.loads(args.config.read_text()),json.loads(args.workflow.read_text()),args.step)


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Window macro cancelled')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
