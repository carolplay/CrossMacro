#!/usr/bin/env python3
"""V3 fixed action batch. Device lock and input session are owned by Macro Studio.app."""
import argparse
import importlib
import json
from pathlib import Path
import signal
import sys
import time
import uuid

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package-root',required=True,type=Path)
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--log-root',required=True,type=Path)
    p.add_argument('--manifest',required=True,type=Path)
    p.add_argument('--profile',required=True,choices=['main','mature-test','under30-test'])
    p.add_argument('--tasks',nargs='+',help='Explicit targeted subset; never silently expands')
    p.add_argument('--execute',action='store_true')
    a=p.parse_args();engine=Path(__file__).resolve().parents[1]/'macos-window'
    sys.path.insert(0,str(engine));sys.path.insert(0,str(a.package_root.resolve()/'scripts'))
    import macro_package,window_macro,task_batch,workflow_versions
    from native_backend import NativeBackend,NATIVE_VERSION
    selected,identity=macro_package.load_manifest(a.manifest.resolve(),a.profile,a.package_root.resolve())
    if a.tasks:
        available={name for name,_ in selected}
        if set(a.tasks)-available: p.error('Task outside selected profile')
        selected=[x for x in selected if x[0] in a.tasks];identity['run_scope']='targeted-development';identity['targeted_tasks']=a.tasks
    for _,flow in selected:window_macro.validate_workflow(flow)
    frozen=workflow_versions.suite_identity(selected)
    if not a.execute:
        print(json.dumps({'validation':'passed','backend':'native-macos','backend_version':NATIVE_VERSION,'cua_dependency':False,'package':identity,'versions':frozen,'game_input':False},ensure_ascii=False));return 0
    config=json.loads(a.config.read_text());folder=a.log_root/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True);config['log_dir']=str(folder);config['native_run_id']=folder.name
    # No independent local lock: the native app acquires the real shared lock at begin.
    # Never remove guard_command or other configured policy when adapting a profile.
    backend=NativeBackend(config);started=time.time();summary={'tasks':[],'versions':frozen}
    def cancel(signum,frame):raise KeyboardInterrupt('Visit cancelled')
    signal.signal(signal.SIGTERM,cancel)
    try:
        backend.start();summary=task_batch.run_batch(config,selected,backend)
    except (Exception,KeyboardInterrupt) as exc:
        summary['startup_or_batch_error']=str(exc)
        done={t['task'] for t in summary['tasks']};summary['tasks'].extend({'task':name,'status':'not_executed','reason':'Native startup or batch stopped'} for name,_ in selected if name not in done)
    finally:
        try:backend.close()
        except Exception as exc:summary['close_error']=str(exc)
        summary.update(package=identity,backend={'name':'native-macos','version':NATIVE_VERSION,'cua_dependency':False,'status':backend.status},started_unix=started,ended_unix=time.time(),elapsed_seconds=time.time()-started)
        summary['status']='passed' if len(summary['tasks'])==len(selected) and all(t['status']=='passed' for t in summary['tasks']) and not summary.get('close_error') else 'completed_with_deviations'
        (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'summary':str(folder/'summary.json'),'status':summary['status']}))
    return 0 if summary['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
