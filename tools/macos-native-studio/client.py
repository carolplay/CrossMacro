#!/usr/bin/env python3
"""Read local Studio state, or run an explicitly requested built-in-window probe."""
import argparse,base64,json,re,tempfile,time
from pathlib import Path
from native_backend import NativeBackend

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['status','doctor','windows','self-test']);p.add_argument('--output',type=Path);p.add_argument('--expected-lock');p.add_argument('--execute',action='store_true');a=p.parse_args()
 b=NativeBackend({})
 try:status=b.request('status')
 except (OSError,TimeoutError) as exc:
  if a.operation!='doctor':raise
  from native_doctor import unavailable
  report=unavailable(exc)
  if a.output:a.output.mkdir(parents=True,exist_ok=True);(a.output/'doctor.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(report,ensure_ascii=False,indent=2));return 2
 if a.operation=='status':print(json.dumps(status,ensure_ascii=False,indent=2));return
 if a.operation=='doctor':
  from native_doctor import diagnose,signing_identity
  report=diagnose(status,a.expected_lock)
  try:report['installed_identity']=signing_identity(status['app_path'])
  except (OSError,ValueError) as exc:report['identity_error']=str(exc)
  if report.get('installed_identity',{}).get('bundle_version')!=status.get('version'):report['restart_required']=True
  if a.output:a.output.mkdir(parents=True,exist_ok=True);(a.output/'doctor.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(report,ensure_ascii=False,indent=2));return
 windows=b.request('windows')['windows']
 if a.operation=='windows':print(json.dumps(windows,ensure_ascii=False,indent=2));return
 if not a.execute:p.error('Self-test sends one click to the built-in test window; add --execute after allowing input in the app')
 targets=[w for w in windows if w['bundle_id']=='io.crossmacro.macro-studio' and re.fullmatch(r'Macro Studio Test Target(?: — \d+)?',w['title'])]
 if len(targets)!=1:raise ValueError('Open one fresh built-in test target from Studio first')
 w=targets[0];baseline=int(w['title'].rsplit(' — ',1)[1]) if ' — ' in w['title'] else 0;b.config.update(native_window_id=w['id'],native_expected_size=[w['width'],w['height']],native_lock_file=status['lock_file'])
 report={'version':'0.1.0','client_version':'0.1.2','cua_dependency':False,'target':w,'counter_before':baseline,'started_unix':time.time(),'status':'failed','game_input':False}
 if a.output:a.output.mkdir(parents=True,exist_ok=True)
 try:
  b.start();before=b.request('screenshot');matches=[l for l in before['ocr']['lines'] if '点击计数' in l['text']]
  if len(matches)!=1:raise ValueError('Unique built-in button label not found')
  x,y,width,height=matches[0]['bounds'];point=[round((x+width/2)*before['ocr']['width']),round((y+height/2)*before['ocr']['height'])]
  reply=b.click(point);after=b.request('screenshot');latest=b.request('windows')['windows'];actual=next((x for x in latest if x['id']==w['id']),{})
  if actual.get('title')!='Macro Studio Test Target — '+str(baseline+1):raise ValueError('Input sent but test counter did not increase exactly once; keep window-directed input unverified')
  report.update(status='passed',counter_after=baseline+1,input=reply,window_after=actual,ocr_before=before['ocr'],ocr_after=after['ocr'],verified='one native button click; no claim about WOS/background/lock or key support')
  if a.output:
   a.output.mkdir(parents=True,exist_ok=True)
   for name,frame in [('before',before),('after',after)]: (a.output/(name+'.png')).write_bytes(base64.b64decode(frame['png_base64']))
 except (Exception,KeyboardInterrupt) as exc:
  report.update(error=str(exc),error_type=type(exc).__name__)
  raise
 finally:
  try:b.close()
  finally:
   report['ended_unix']=time.time()
   if a.output:(a.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':raise SystemExit(main())
