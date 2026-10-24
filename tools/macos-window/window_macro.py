#!/usr/bin/env python3
"""Deterministic window macros for CrossMacro's existing Shell action.

Requires the user's installed CUA MCP runtime; does not bundle it or call models.
Only fixed observe/click operations are supported. All identity and machine
configuration belongs outside the repository, as do screenshots and run logs.
"""
import argparse
import base64
import copy
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
from workflow_versions import SUITE_VERSION, workflow_identity


class FatalExecutionError(RuntimeError):
    """Identity or environment failure; recovery must not send more input."""


def read_frame_ocr(command, deadline, retry_log):
    """Retry one local OCR timeout on the same saved image, never UI input."""
    events = []
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FatalExecutionError('Workflow timeout before local OCR')
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    check=True, timeout=min(15, remaining))
        except subprocess.TimeoutExpired:
            events.append({'attempt': attempt + 1, 'error': 'local-ocr-timeout',
                           'same_saved_frame': True, 'input_sent': False})
            Path(retry_log).write_text(json.dumps(events, indent=2))
            if attempt == 1 or time.monotonic() >= deadline:
                raise
        else:
            if events:
                events.append({'attempt': attempt + 1, 'status': 'recovered',
                               'same_saved_frame': True, 'input_sent': False})
                Path(retry_log).write_text(json.dumps(events, indent=2))
            return result


def blank_observation_frame(path):
    """Reject an almost entirely white transport/transition frame, at any size.

    This is an observation-quality check, never evidence that input is allowed.
    A legitimate white transition must also settle before page anchors can pass.
    """
    from PIL import Image
    with Image.open(path) as source:
        pixels = source.convert('RGB')
        histogram = pixels.histogram()
        count = pixels.width * pixels.height
    # Each channel may have up to 3% non-white pixels. By the union bound at
    # least 91% of pixels are near-white in all three channels.
    return all(sum(histogram[c * 256 + 250:c * 256 + 256]) / count >= .97
               for c in range(3))


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).translate(str.maketrans({'級':'级'})).split())


def number_in_region(observation, bounds, min_confidence=.5):
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
        if (left <= cx <= right and top <= cy <= bottom and line.get('confidence', 0) >= min_confidence
            and re.fullmatch(r'[0-9]+', value)):
            values.append(int(value))
    if len(values) != 1 and observation.ocr_config:
        # Read the same calibrated pixels in isolation before declaring an OCR
        # deviation. Never capture another image or repeat a business action.
        key = ('inventory', *bounds)
        if key not in observation.timer_regions:
            from PIL import Image
            derived = Path(observation.image_path).parent / 'derived'
            derived.mkdir(exist_ok=True)
            crop = derived / (Path(observation.image_path).stem + '-inventory-' + '-'.join(map(str,bounds)) + '.png')
            with Image.open(observation.image_path) as image:
                region = image.crop(bounds)
                region.resize((region.width*4,region.height*4),Image.Resampling.LANCZOS).save(crop)
            raw = subprocess.run([observation.ocr_config['binary'],str(crop),observation.ocr_config['language']],
                                 capture_output=True,text=True,check=True,timeout=15)
            data = json.loads(raw.stdout)
            crop.with_name(crop.stem + '-ocr.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
            observation.timer_regions[key] = data['lines']
        values = []
        for line in observation.timer_regions[key]:
            value = normalize(line['text']).replace(',', '').rstrip('+')
            if line.get('confidence',0) >= min_confidence and re.fullmatch(r'[0-9]+',value):
                values.append(int(value))
        observation.visual_checks.append({'inventory_crop_bounds':bounds,'integer_candidates':values})
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
        unknown = set(required) - {'all', 'any', 'none', 'timer_seconds', 'timer_regions', 'green_regions', 'blue_regions', 'red_regions', 'text_regions', 'white_regions', 'page_text_regions', 'page_text_only', 'template_regions'}
        if unknown:
            raise ValueError('Unknown OCR conditions: ' + ', '.join(sorted(unknown)))
        if required.get('page_text_only') and not required.get('page_text_regions'):
            raise ValueError('Scoped page text requires explicit crop regions')
        page_text = '' if required.get('page_text_only') else str(text)
        for bounds in required.get('page_text_regions', []):
            if not isinstance(text, Observation) or not text.ocr_config:
                raise RuntimeError('Page crop assertions require a fresh local image')
            key = ('page', *bounds)
            if key not in text.timer_regions:
                from PIL import Image
                derived = Path(text.image_path).parent / 'derived'
                derived.mkdir(exist_ok=True)
                crop = derived / (Path(text.image_path).stem + '-page-' + '-'.join(map(str,bounds)) + '.png')
                with Image.open(text.image_path) as image:
                    region = image.crop(bounds)
                    region.resize((region.width * 2, region.height * 2), Image.Resampling.LANCZOS).save(crop)
                raw = subprocess.run([text.ocr_config['binary'],str(crop),text.ocr_config['language']],
                                     capture_output=True,text=True,check=True,timeout=15)
                data = json.loads(raw.stdout)
                crop.with_name(crop.stem + '-ocr.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
                text.timer_regions[key] = [line['text'] for line in data['lines'] if line.get('confidence',0) >= .5]
            labels = text.timer_regions[key]
            page_text += '\n' + '\n'.join(labels)
            text.visual_checks.append({'page_crop_bounds':bounds,'labels':labels})
        require_text(page_text, required.get('all', []))
        for timer in required.get('timer_regions',[]):
            require_text(text,{'timer_seconds':timer})
        for spec in required.get('template_regions', []):
            from image_targets import match
            found=match(text,spec)['score'] >= spec.get('min_score',.85)
            if found != spec.get('present',True):
                raise RuntimeError('Image template presence condition failed: '+spec['template'])
        value = normalize(page_text)
        choices = required.get('any', [])
        if choices and not any(normalize(s) in value for s in choices):
            raise RuntimeError('OCR condition failed: no alternative matched')
        if any(normalize(s) in value for s in required.get('none', [])):
            raise RuntimeError('OCR condition failed: forbidden text remains')
        for region in required.get('text_regions', []):
            if not isinstance(text, Observation) or not text.ocr_data:
                raise RuntimeError('Regional text requires fresh OCR geometry')
            if region.get('prefer_frame_ocr'):
                left, top, right, bottom = region['bounds']
                data = text.ocr_data
                matches = []
                for line in data['lines']:
                    x, y, w, h = line['bounds']
                    cx, cy = (x + w / 2) * data['width'], (y + h / 2) * data['height']
                    if (left <= cx <= right and top <= cy <= bottom
                        and line.get('confidence', 0) >= region.get('min_confidence', .5)
                        and re.fullmatch(region['pattern'], normalize(line['text']))):
                        matches.append(line['text'])
                if len(matches) == 1:
                    text.visual_checks.append({'regional_text': matches[0],
                        'bounds': region['bounds'], 'source': 'full-frame-preferred'})
                    continue
            if region.get('crop_ocr'):
                if not text.ocr_config:
                    raise RuntimeError('Cropped text requires local OCR configuration')
                key=('text',*region['bounds'])
                if key not in text.timer_regions:
                    from PIL import Image
                    derived=Path(text.image_path).parent/'derived';derived.mkdir(exist_ok=True)
                    stem=Path(text.image_path).stem+'-text-'+('-'.join(map(str,region['bounds'])))
                    crop=derived/(stem+'.png')
                    with Image.open(text.image_path) as image:
                        clipped=image.crop(region['bounds'])
                        clipped.resize((clipped.width*4,clipped.height*4),Image.Resampling.LANCZOS).save(crop)
                    raw=subprocess.run([text.ocr_config['binary'],str(crop),text.ocr_config['language']],capture_output=True,text=True,check=True,timeout=15)
                    data=json.loads(raw.stdout);(derived/(stem+'-ocr.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
                    text.timer_regions[key]=data['lines']
                lines=text.timer_regions[key]
                matches=[line['text'] for line in lines if line.get('confidence',0)>=region.get('min_confidence',.5)
                         and re.fullmatch(region['pattern'],normalize(line['text']))]
                if len(matches)!=1:
                    raise RuntimeError('Expected exactly one matching cropped text value')
                text.visual_checks.append({'cropped_text':matches[0],'bounds':region['bounds']})
                continue
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
        for region in required.get('blue_regions', []):
            if not isinstance(text,Observation):raise RuntimeError('Color conditions require a fresh image')
            from PIL import Image
            with Image.open(text.image_path) as image:
                pixels=image.convert('RGB').crop(region['bounds']).tobytes()
            ratio=sum(b>130 and b>1.25*r and b>1.05*g
                      for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3]))/(len(pixels)//3)
            text.visual_checks.append({'bounds':region['bounds'],'blue_fraction':ratio})
            if not region.get('min',0)<=ratio<=region.get('max',1):raise RuntimeError('Blue button condition failed')
        for region in required.get('red_regions', []):
            if not isinstance(text,Observation):raise RuntimeError('Color conditions require a fresh image')
            from PIL import Image
            with Image.open(text.image_path) as image:
                pixels=image.convert('RGB').crop(region['bounds']).tobytes()
            ratio=sum(r>140 and r>1.4*g and r>1.4*b
                      for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3]))/(len(pixels)//3)
            text.visual_checks.append({'bounds':region['bounds'],'red_fraction':ratio})
            if not region.get('min',0)<=ratio<=region.get('max',1):raise RuntimeError('Red indicator condition failed')
        for region in required.get('white_regions', []):
            if not isinstance(text,Observation):raise RuntimeError('Color conditions require a fresh image observation')
            from PIL import Image
            with Image.open(text.image_path) as image:
                pixels=image.convert('RGB').crop(region['bounds']).tobytes()
            ratio=sum(min(r,g,b)>225 and max(r,g,b)-min(r,g,b)<25
                      for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3]))/(len(pixels)//3)
            text.visual_checks.append({'bounds':region['bounds'],'white_fraction':ratio})
            if not region.get('min',0)<=ratio<=region.get('max',1):raise RuntimeError('White badge condition failed')
        return
    missing = [s for s in required if not s or normalize(s) not in normalize(text)]
    if missing:
        raise RuntimeError('OCR condition failed: ' + ', '.join(missing))


def validate_image_spec(spec,size,target=False):
    allowed={'template','bounds','min_score','mode'} | ({'offset'} if target else {'present'})
    bounds=spec.get('bounds',[])
    if (set(spec)-allowed or not isinstance(spec.get('template'),str)
        or not re.fullmatch(r'[a-z0-9_-]{1,80}',spec['template'])
        or len(bounds)!=4 or any(type(v) is not int for v in bounds)
        or not 0<=bounds[0]<bounds[2]<=size[0] or not 0<=bounds[1]<bounds[3]<=size[1]
        or type(spec.get('min_score',.85)) not in (int,float)
        or not .6<=spec.get('min_score',.85)<=1
        or spec.get('mode','white-glyph') not in ('white-glyph','grayscale')
        or type(spec.get('present',True)) is not bool):
        raise ValueError('Invalid bounded image template specification')
    offset=spec.get('offset',[0,0])
    if not isinstance(offset,list) or len(offset)!=2 or any(type(v) is not int or abs(v)>max(size) for v in offset):
        raise ValueError('Invalid image template offset')


def validate_condition(condition, size):
    if isinstance(condition, list):
        if not condition or any(not isinstance(s,str) or not s for s in condition):
            raise ValueError('OCR conditions must contain nonempty text')
        return
    if not isinstance(condition, dict) or not condition:
        raise ValueError('Expected OCR text list or condition object')
    if set(condition) - {'all','any','none','timer_seconds','timer_regions','green_regions','blue_regions','red_regions','text_regions','white_regions','page_text_regions','page_text_only','template_regions'}:
        raise ValueError('Unknown local observation condition')
    if not condition.get('all') and not condition.get('any'):
        raise ValueError('Conditions require a positive page-text assertion')
    if 'page_text_only' in condition and (type(condition['page_text_only']) is not bool
        or condition['page_text_only'] and not condition.get('page_text_regions')):
        raise ValueError('Scoped page text requires explicit crop regions and a boolean flag')
    if 'timer_regions' in condition:
        regions=condition['timer_regions']
        if not isinstance(regions,list) or not 1<=len(regions)<=4:
            raise ValueError('Expected one to four timer regions')
        for timer in regions:
            validate_condition({'all':['PAGE'],'timer_seconds':timer},size)
    if 'template_regions' in condition:
        regions=condition['template_regions']
        if not isinstance(regions,list) or not 1<=len(regions)<=4:
            raise ValueError('Image conditions require one to four templates')
        for spec in regions:
            validate_image_spec(spec,size)
    for key in ('all','any','none'):
        if key in condition:
            validate_condition(condition[key],size)
    if 'page_text_regions' in condition:
        regions = condition['page_text_regions']
        if not isinstance(regions,list) or not 1 <= len(regions) <= 4:
            raise ValueError('Page text crops require one to four regions')
        for bounds in regions:
            if (not isinstance(bounds,list) or len(bounds)!=4 or any(type(v) is not int for v in bounds)
                or not 0 <= bounds[0] < bounds[2] <= size[0]
                or not 0 <= bounds[1] < bounds[3] <= size[1]):
                raise ValueError('Invalid page text crop bounds')
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
    for region in condition.get('green_regions',[])+condition.get('blue_regions',[])+condition.get('white_regions',[])+condition.get('red_regions',[]):
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
            or not 0<=region.get('min_confidence',.5)<=1
            or type(region.get('crop_ocr',False)) is not bool
            or type(region.get('prefer_frame_ocr',False)) is not bool
            or (region.get('prefer_frame_ocr') and not region.get('crop_ocr'))):
            raise ValueError('Invalid regional text assertion')
        re.compile(region['pattern'])



def resolve_point(step, observation, size):
    """Resolve one bounded OCR label locally; ambiguity never sends input."""
    if step.get('image_target'):
        from image_targets import match
        spec=step['image_target'];result=match(observation,spec)
        if result['score'] < spec.get('min_score',.85):
            raise RuntimeError('Image target below threshold: '+spec['template'])
        point=[a+b for a,b in zip(result['point'],spec.get('offset',[0,0]))]
        if not all(0<=v<size[i] for i,v in enumerate(point)):
            raise RuntimeError('Image target outside reference window')
        return point
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
    data=observation.ocr_data;origin=[0,0];extent=size
    if target.get('crop_ocr'):
        if not observation.ocr_config:
            raise RuntimeError('Cropped targets require local OCR configuration')
        key=('target',left,top,right,bottom)
        if key not in observation.timer_regions:
            from PIL import Image
            derived=Path(observation.image_path).parent/'derived';derived.mkdir(exist_ok=True)
            stem=Path(observation.image_path).stem+'-target-'+('-'.join(map(str,target['bounds'])))
            crop=derived/(stem+'.png')
            with Image.open(observation.image_path) as image:
                clipped=image.crop(target['bounds'])
                clipped.resize((clipped.width*4,clipped.height*4),Image.Resampling.LANCZOS).save(crop)
            raw=subprocess.run([observation.ocr_config['binary'],str(crop),observation.ocr_config['language']],capture_output=True,text=True,check=True,timeout=15)
            data=json.loads(raw.stdout);(derived/(stem+'-ocr.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
            observation.timer_regions[key]=data
        data=observation.timer_regions[key];origin=[left,top];extent=[right-left,bottom-top]
        observation.visual_checks.append({'target_crop_bounds':target['bounds'],'labels':[line['text'] for line in data['lines']]})
    for line in data['lines']:
        value=normalize(line['text']);label=normalize(target['text'])
        if target.get('regex',False):
            if not re.fullmatch(target['text'],value):continue
        elif not (value==label if target.get('exact',True) else label in value):continue
        if line.get('confidence',0)<target.get('min_confidence',.8):continue
        x,y,w,h=line['bounds'];cx,cy=origin[0]+(x+w/2)*extent[0],origin[1]+(y+h/2)*extent[1]
        if left<=cx<=right and top<=cy<=bottom:
            offset=target.get('offset',[0,0])
            point=[round(cx)+offset[0],round(cy)+offset[1]]
            if not all(0 <= v < size[i] for i,v in enumerate(point)):
                raise RuntimeError('OCR target resolves outside the reference window')
            matches.append(point)
    if target.get('select')=='top-left' and matches:
        return min(matches,key=lambda point:(point[1],point[0]))
    if len(matches)!=1:raise RuntimeError('Expected exactly one confident text target; found '+str(len(matches)))
    return matches[0]


def workflow_steps(workflow, steps):
    """Repeat an explicitly bounded tail with isolated branch names per round."""
    marker = workflow.get('repeat_from')
    if not marker or steps is not workflow['steps']:
        yield from steps
        return
    start = next(i for i, step in enumerate(steps) if step['name'] == marker)
    yield from steps[:start]
    iteration = 0
    while True:
        iteration += 1
        mapping = {step['name']: f"round-{iteration}-{step['name']}" for step in steps[start:]}
        for source in steps[start:]:
            step = copy.deepcopy(source)
            step['name'] = mapping[source['name']]
            dependency = step.get('skip_if_step_skipped')
            if dependency in mapping:
                step['skip_if_step_skipped'] = mapping[dependency]
            yield step


def validate_workflow(workflow):
    budget = workflow.get('execution_timeout_seconds', 120)
    if type(budget) is not int or not 1 <= budget <= 1800:
        raise ValueError('execution_timeout_seconds must be an integer from1 to1800')
    marker = workflow.get('repeat_from')
    if marker is not None:
        candidates = [s for s in workflow['steps'] if s['name'] == marker]
        if ('execution_timeout_seconds' not in workflow or len(candidates) != 1
                or candidates[0].get('action') != 'observe' or not candidates[0].get('finish_if')):
            raise ValueError('Repeated tail requires explicit timeout and an observe completion anchor')
    size = workflow['reference_size']
    if len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError('reference_size must contain two positive integers')
    names = set()
    for step in workflow['steps']:
        if step['name'] in names:
            raise ValueError('Step names must be unique')
        if step.get('skip_if_step_skipped') is not None and step['skip_if_step_skipped'] not in names:
            raise ValueError('Skip dependency must reference an earlier step')
        names.add(step['name'])
        if step['action'] not in ('observe', 'click', 'key') or not step.get('before'):
            raise ValueError('Every step requires an observe/click action and OCR preconditions')
        for key in ('before','after','skip_if','finish_if'):
            if key in step:
                validate_condition(step[key],size)
        for condition in step.get('skip_if_any', []):
            validate_condition(condition,size)
        checks = step.get('budget_checks', [])
        if not isinstance(checks,list) or len(checks)>8:
            raise ValueError('Invalid local budget checks')
        for item in checks:
            bounds = item.get('bounds', [])
            if (set(item)-{'bounds','max_config','min'} or len(bounds)!=4
                or any(type(v) is not int for v in bounds)
                or not 0 <= bounds[0] < bounds[2] <= size[0]
                or not 0 <= bounds[1] < bounds[3] <= size[1]
                or not isinstance(item.get('max_config'),str)
                or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}',item['max_config'])
                or type(item.get('min',0)) is not int or item.get('min',0)<0):
                raise ValueError('Invalid local budget check')
        if step['action'] == 'click':
            if sum(key in step for key in ('point','text_target','green_target','image_target'))!=1:
                raise ValueError('A click requires exactly one point, text_target or green_target')
            if 'image_target' in step:
                validate_image_spec(step['image_target'],size,target=True)
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
                if (set(target)-{'text','bounds','exact','min_confidence','offset','regex','select','crop_ocr'}
                    or not isinstance(target.get('text'),str) or not normalize(target['text'])
                    or type(target.get('exact',True)) is not bool
                    or type(target.get('regex',False)) is not bool
                    or type(target.get('crop_ocr',False)) is not bool
                    or target.get('select','unique') not in ('unique','top-left')
                    or len(target.get('text',''))>200
                    or not isinstance(target.get('offset',[0,0]),list)
                    or len(target.get('offset',[0,0])) != 2
                    or any(type(v) is not int or abs(v)>max(size) for v in target.get('offset',[0,0]))
                    or not 0 <= target.get('min_confidence',.8) <= 1
                    or len(bounds)!=4 or any(type(v) is not int for v in bounds)
                    or not 0<=bounds[0]<bounds[2]<=size[0]
                    or not 0<=bounds[1]<bounds[3]<=size[1]):
                    raise ValueError('Invalid bounded OCR text target')
                if target.get('regex',False):re.compile(target['text'])
            point = step.get('point',[0,0])
            if len(point) != 2 or any(type(v) is not int or not 0 <= v < size[i] for i, v in enumerate(point)):
                raise ValueError('Click is outside reference window')
            if not step.get('after'):
                raise ValueError('Every click requires OCR completion conditions')
        if step['action'] == 'key':
            if (step.get('key') not in ('Up','Down','Left','Right')
                or type(step.get('key_count',1)) is not int
                or not 1 <= step.get('key_count',1) <= 20
                or type(step.get('duration_ms',600)) is not int
                or not 1<=step.get('duration_ms',600)<=1000 or not step.get('after')):
                raise ValueError('Key steps require a bounded navigation arrow and completion conditions')
        if step.get('once_per_game_day') and (step['action'] != 'click' or not isinstance(step['once_per_game_day'],str) or not re.fullmatch(r'[a-z0-9_-]{1,80}',step['once_per_game_day'])):
            raise ValueError('Invalid daily operation key')
        interval = step.get('observe_interval_seconds', 0)
        if (type(interval) not in (int, float) or not 0 <= interval <= 5
                or interval and step['action'] != 'observe'):
            raise ValueError('Observation retry interval requires observe and must be from0 to5 seconds')
        attempts = step.get('observe_attempts', 1)
        if type(attempts) is not int or not 1 <= attempts <= 30:
            raise ValueError('observe_attempts must be between 1 and 30')
        for key in ('remember_numbers', 'unchanged_numbers', 'increased_numbers'):
            for item in step.get(key, []):
                bounds = item.get('bounds', [])
                if (not isinstance(item.get('name'), str) or not item['name']
                    or type(item.get('min_confidence',.5)) not in (int,float)
                    or not .3 <= item.get('min_confidence',.5) <= 1
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
                    and meta.get('tool_name') in set(self.config.get('authorized_tools',[])) & {'get_app_state','get_app_screenshot','click','press_key'})
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

    def original_screenshot_bytes(self):
        result = self.js('var cmOriginalObservation=await target.getAXStateAndScreenshot({emit:false}); nodeRepl.write(JSON.stringify({originalScreenshotBase64:Buffer.from(cmOriginalObservation.screenshot).toString("base64")}));')
        for block in result.get('content', []):
            if block.get('type') != 'text':
                continue
            try:
                value = json.loads(block['text'])
            except (ValueError, KeyError):
                continue
            if isinstance(value, dict) and isinstance(value.get('originalScreenshotBase64'), str):
                return base64.b64decode(value['originalScreenshotBase64'], validate=True)
        raise FatalExecutionError('Original screenshot unavailable after invalid image response')

    def observe(self, folder, label, expected_size):
        import viewport_calibration as viewport
        calibrated = viewport.calibration(self.config, expected_size)
        native_expected = calibrated["native_size"] if calibrated else expected_size
        try:
            result = self.js('await target.getAXStateAndScreenshot();')
        except RuntimeError as exc:
            # The host can remove its own transient screenshot before delivery.
            # Only this precise observation error gets one fresh atomic read;
            # permission, missing-window and unrelated file errors still stop.
            message = str(exc)
            if not all(marker in message for marker in (
                    'ENOENT: no such file or directory',
                    '/com.openai.sky.CUAService/', 'Screenshot ')):
                raise
            data = self.original_screenshot_bytes()
            (folder / (label + '-missing-screenshot.json')).write_text(json.dumps({
                'error': message, 'input_sent': False,
                'method': 'one-fresh-atomic-read'}, indent=2))
            result = {'content': [{'type': 'image', 'mimeType': 'image/jpeg',
                                   'data': base64.b64encode(data).decode()}]}
        images = [c for c in result.get('content',[]) if c.get('type') == 'image']
        if len(images) != 1:
            raise RuntimeError('Expected one target-window screenshot')
        data = base64.b64decode(images[0]['data'], validate=True)
        mime = images[0].get('mimeType')
        if mime not in ('image/png','image/jpeg'):
            raise RuntimeError('Unsupported screenshot image type: ' + str(mime))
        path = folder / (label + ('.png' if mime == 'image/png' else '.jpg'))
        path.write_bytes(data)
        # Image content may be a placeholder or transport-resized thumbnail.
        # Verify against original bytes from the same documented screenshot API;
        # never scale pixels or send another input to recover an observation.
        from PIL import Image
        with Image.open(path) as captured:
            captured_size = list(captured.size)
        if captured_size != native_expected or blank_observation_frame(path):
            unusable = path.with_name(path.stem + '-unusable-frame' + path.suffix)
            path.rename(unusable)
            path.write_bytes(self.original_screenshot_bytes())
            with Image.open(path) as captured:
                captured_size = list(captured.size)
        pending_viewport = None
        invalid_sizes = []
        invalid_reasons = []
        for attempt in range(3):
            blank_frame = blank_observation_frame(path)
            if captured_size == native_expected and not blank_frame:
                break
            import viewport_preflight
            pending_viewport = None if blank_frame else viewport_preflight.candidate(
                self.config, expected_size, captured_size,
                locked=getattr(self, '_viewport_locked', False))
            if pending_viewport is not None and not blank_frame:
                calibrated = pending_viewport[0]
                break
            invalid_sizes.append(captured_size)
            invalid_reasons.append('blank-frame' if blank_frame else 'size-mismatch')
            path.with_name(path.stem+'-invalid-original-'+str(attempt)+path.suffix).write_bytes(path.read_bytes())
            if attempt == 2:
                raise FatalExecutionError('Invalid screenshot frame (%s): %s; expected %s. No input sent.' % (invalid_reasons[-1], captured_size, native_expected))
            # Read-only bounded recovery. Permission errors propagate immediately;
            # no input, coordinate changes, or alternative backend is attempted.
            path.write_bytes(self.original_screenshot_bytes())
            with Image.open(path) as captured:
                captured_size = list(captured.size)
        if invalid_sizes:
            (folder/(label+'-frame-recovery.json')).write_text(json.dumps({
                'invalid_sizes': invalid_sizes, 'accepted_size': captured_size,
                'invalid_reasons': invalid_reasons,
                'extra_original_reads': len(invalid_sizes), 'input_sent': False,
                'method': 'bounded-same-backend-original-read'}, indent=2))
        if calibrated:
            viewport.normalize_frame(path, calibrated)
        raw = read_frame_ocr([self.config['ocr_binary'],str(path),self.config.get('language','en-US')],
            self.deadline, folder/(label+'-ocr-recovery.json'))
        ocr = json.loads(raw.stdout)
        (folder/(label+'-ocr.json')).write_text(json.dumps(ocr,ensure_ascii=False,indent=2))
        size = [ocr['width'],ocr['height']]
        if size != expected_size:
            raise FatalExecutionError('Window size changed: %s; expected %s. Recalibrate before input.' % (size,expected_size))
        observation = Observation('\n'.join(line['text'] for line in ocr['lines']), path, ocr, {'binary':self.config['ocr_binary'],'language':self.config.get('language','en-US'),'templates':self.config.get('image_templates',{})})
        if pending_viewport:
            try:
                require_text(observation, pending_viewport[1])
            except (RuntimeError, ValueError) as exc:
                raise FatalExecutionError('Validated viewport entry anchor failed; no input sent: ' + str(exc)) from exc
            event = {'previous': self.config.get('viewport_calibration'),
                     'selected': calibrated, 'observed_size': captured_size,
                     'evidence': str(path), 'input_sent': False,
                     'method': 'startup-exact-validated-profile', 'window_resized': False}
            (folder/(label+'-viewport-preflight.json')).write_text(json.dumps(event, ensure_ascii=False, indent=2))
            self.config['viewport_calibration'] = calibrated
        # Freeze for this backend's lifetime; a later resize still stops input.
        self._viewport_locked = True
        return observation

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
            'runtime_model_calls':0,'chat_identity_supplied':False,'steps':[],
            'suite_version':SUITE_VERSION,'workflow':workflow_identity(workflow),
            'viewport_calibration':copy.deepcopy(config.get('viewport_calibration'))}
        client = backend
        try:
            if client is None:
                client = CuaMcp(config)
                client.start()
            client.deadline = time.monotonic() + workflow.get('execution_timeout_seconds', min(120, config.get('timeout_seconds',45)))
            inventory = {}
            for index, step in enumerate(workflow_steps(workflow, steps)):
                if time.monotonic() >= client.deadline:
                    raise FatalExecutionError('Workflow execution timeout')
                # A skipped branch has no business action or observation to do.
                # The next eligible step always observes afresh before any input.
                if any(entry['name'] == step.get('skip_if_step_skipped') and entry.get('skipped') for entry in report['steps']):
                    report['steps'].append({'name':step['name'],'skipped':True,
                        'reason':'Earlier branch skipped; no observation or input required','visual_checks':[]})
                    continue
                before = client.observe(folder, '%02d-before'%index, workflow['reference_size'])
                report['viewport_calibration'] = copy.deepcopy(config.get('viewport_calibration'))
                if step.get('finish_if'):
                    try:
                        require_text(before,step['finish_if'])
                    except RuntimeError:
                        pass
                    else:
                        report['steps'].append({'name':step['name'],'finished_early':True,
                            'reason':'Declared completion condition matched',
                            'visual_checks':getattr(before,'visual_checks',[])})
                        break
                skipped = any(entry['name'] == step.get('skip_if_step_skipped') and entry.get('skipped')
                              for entry in report['steps'])
                for attempt in range(step.get('observe_attempts', 1)):
                    if skipped:
                        break
                    skip_conditions=step.get('skip_if_any', []) + ([step['skip_if']] if step.get('skip_if') else [])
                    for skip_condition in skip_conditions:
                        try:
                            require_text(before, skip_condition)
                        except RuntimeError:
                            pass
                        else:
                            skipped = True
                            break
                    if skipped:
                        break
                    try:
                        require_text(before, step['before'])
                        break
                    except RuntimeError:
                        if attempt + 1 == step.get('observe_attempts', 1):
                            raise
                        interval = step.get('observe_interval_seconds', 0)
                        if interval:
                            if time.monotonic() + interval >= client.deadline:
                                raise FatalExecutionError('Workflow timeout before next observation retry')
                            time.sleep(interval)
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
                for item in step.get('budget_checks', []):
                    limit = config.get(item['max_config'])
                    if type(limit) is not int or limit < item.get('min',0):
                        raise RuntimeError('Missing or invalid local budget: ' + item['max_config'])
                    value = number_in_region(before,item['bounds'])
                    if not item.get('min',0) <= value <= limit:
                        raise RuntimeError('Selected amount exceeds local budget: ' + item['max_config'])
                    entry.setdefault('budget_checks',[]).append({'config_key':item['max_config'],
                        'selected':value,'maximum':limit})
                for item in step.get('remember_numbers', []):
                    inventory[item['name']] = number_in_region(before, item['bounds'], item.get('min_confidence',.5))
                    entry.setdefault('remembered_numbers', {})[item['name']] = inventory[item['name']]
                for item in step.get('unchanged_numbers', []):
                    value = number_in_region(before, item['bounds'], item.get('min_confidence',.5))
                    if item['name'] not in inventory or value != inventory[item['name']]:
                        raise FatalExecutionError('Inventory changed unexpectedly: ' + item['name'])
                    entry.setdefault('unchanged_numbers', {})[item['name']] = value
                for item in step.get('increased_numbers', []):
                    for read_attempt in range(step.get('observe_attempts',1)):
                        try:
                            value = number_in_region(before,item['bounds'],item.get('min_confidence',.5))
                            if item['name'] not in inventory or value <= inventory[item['name']]:
                                raise RuntimeError('Expected inventory increase: '+item['name'])
                            break
                        except RuntimeError:
                            if read_attempt+1 == step.get('observe_attempts',1):raise
                            before=client.observe(folder,'%02d-increase-retry-%02d'%(index,read_attempt+1),workflow['reference_size'])
                            require_text(before,step['before'])
                    entry.setdefault('increased_numbers',{})[item['name']] = {
                        'before':inventory[item['name']], 'after':value,
                        'increase':value-inventory[item['name']], 'read_attempts':read_attempt+1}
                if step['action'] == 'key':
                    entry['key_unix']=time.time()
                    import backend_input
                    backend_input.key(client, step['key'], step.get('key_count',1), step.get('duration_ms',600))
                    for attempt in range(step.get('observe_attempts',1)):
                        after=client.observe(folder,'%02d-after-%02d'%(index,attempt),workflow['reference_size'])
                        try:require_text(after,step['after']);break
                        except RuntimeError:
                            if attempt+1==step.get('observe_attempts',1):raise
                    entry.update(after_verified=True,after_observations=attempt+1)
                if step['action'] == 'click':
                    import backend_input
                    point=resolve_point(step,before,workflow['reference_size'])
                    entry['resolved_point']=point
                    import viewport_calibration as viewport
                    point=viewport.point(config,point,workflow['reference_size'])
                    entry['native_resolved_point']=point
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
                    daily_reservation = None
                    if step.get('once_per_game_day'):
                        from daily_operations import reserve
                        daily_reservation = reserve(config,step['once_per_game_day'])
                        entry['daily_reservation_key'] = daily_reservation[1]
                    entry['click_unix'] = time.time()
                    try:
                        backend_input.click(client, point)
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
                    if daily_reservation:
                        from daily_operations import confirm
                        confirm(daily_reservation)
                        entry['daily_operation_confirmed'] = True
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
