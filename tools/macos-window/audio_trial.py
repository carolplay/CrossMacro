"""Run an existing CrossMacro macro with target-only audio and an offline audit.

Shadow mode deliberately retains visual verification until real sound templates
have held-out positive and negative samples. It does not call any model API.
"""
import argparse,json,os,subprocess,time
from pathlib import Path
from audio_feedback import AudioCapture
from check_run import check


def run(config_path, workflow_path, player, macro, folder):
    config=json.loads(Path(config_path).read_text())
    workflow=json.loads(Path(workflow_path).read_text())
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    started=time.time();capture=None;audio={'usable_audio':False,'reason':'Audio capture not configured'}
    try:
        spec=config['audio_capture']
        capture=AudioCapture(spec['binary'],config['target']['bundle_id'],folder/'capture',120)
        capture.wait_ready()
    except Exception as exc:
        audio={'usable_audio':False,'reason':str(exc)}
        if capture:audio.update(capture.stop());capture=None
    if capture:capture.mark('crossmacro-start')
    try:
        process=subprocess.run([str(player),'play',str(macro),'--json'],capture_output=True,text=True,timeout=120)
    except (subprocess.TimeoutExpired,OSError) as exc:
        process=subprocess.CompletedProcess([str(player)],124,stdout='',stderr=str(exc))
    finally:
        if capture:
            capture.mark('crossmacro-end');audio=capture.stop()
    reports=[];events=[]
    for path in Path(config['log_dir']).glob('*/result.json'):
        data=json.loads(path.read_text())
        if started<=data.get('started_unix',0)<=time.time():
            reports.append(path)
            for step in data.get('steps',[]):
                if step.get('click_unix'):events.append({'name':step['name'],'unix':step['click_unix']})
    audit=check(reports,[s['name'] for s in workflow['steps']])
    if not audio.get('usable_audio'):
        issue={'type':'audio_unavailable','step':None,'reason':audio.get('reason','No usable target-app audio; retained OCR fallback')}
        audit['issues'].append(issue);audit['recheck_queue'].append(issue);audit['status']='needs_review'
    result={'mode':'audio-shadow','audio':audio,'events':sorted(events,key=lambda e:e['unix']),
            'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr,
            'elapsed_seconds':time.time()-started,'screenshots_removed':0,'ocr_calls_removed':0,
            'runtime_model_calls':0,'check':audit}
    (folder/'trial.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','workflow','player','macro','folder'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.config,a.workflow,a.player,a.macro,a.folder),ensure_ascii=False))
