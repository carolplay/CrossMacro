#!/usr/bin/env python3
"""Read local Studio state, or run an explicitly requested built-in-window probe."""
import argparse,base64,json,tempfile,time
from pathlib import Path
from native_backend import NativeBackend

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['status','windows','self-test']);p.add_argument('--output',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
 b=NativeBackend({});status=b.request('status')
 if a.operation=='status':print(json.dumps(status,ensure_ascii=False,indent=2));return
 windows=b.request('windows')['windows']
 if a.operation=='windows':print(json.dumps(windows,ensure_ascii=False,indent=2));return
 if not a.execute:p.error('Self-test sends one click to the built-in test window; add --execute after allowing input in the app')
 targets=[w for w in windows if w['bundle_id']=='io.crossmacro.macro-studio' and w['title']=='Macro Studio Test Target']
 if len(targets)!=1:raise ValueError('Open one fresh built-in test target from Studio first')
 w=targets[0];b.config.update(native_window_id=w['id'],native_expected_size=[w['width'],w['height']],native_lock_file=status['lock_file'])
 report={'version':'0.1.0','cua_dependency':False,'target':w,'started_unix':time.time(),'status':'failed','game_input':False}
 try:
  b.start();before=b.request('screenshot');matches=[l for l in before['ocr']['lines'] if '点击计数' in l['text']]
  if len(matches)!=1:raise ValueError('Unique built-in button label not found')
  x,y,width,height=matches[0]['bounds'];point=[round((x+width/2)*before['ocr']['width']),round((y+height/2)*before['ocr']['height'])]
  reply=b.click(point);after=b.request('screenshot');latest=b.request('windows')['windows'];actual=next((x for x in latest if x['id']==w['id']),{})
  if actual.get('title')!='Macro Studio Test Target — 1':raise ValueError('Input sent but test counter did not become 1; keep window-directed input unverified')
  report.update(status='passed',input=reply,window_after=actual,ocr_before=before['ocr'],ocr_after=after['ocr'],verified='one native button click; no claim about WOS/background/lock or key support')
  if a.output:
   a.output.mkdir(parents=True,exist_ok=True)
   for name,frame in [('before',before),('after',after)]: (a.output/(name+'.png')).write_bytes(base64.b64decode(frame['png_base64']))
 finally:
  try:b.close()
  finally:
   report['ended_unix']=time.time()
   if a.output:(a.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
