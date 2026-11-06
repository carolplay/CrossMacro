"""Optional workspace lease metadata; the native App's real flock is authority."""
import json
from pathlib import Path
import os
import tempfile
import time
from native_doctor import probe_device_lock


def read(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else {}


def save(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def started(path, run_id, lock_file, role=None):
    """Call only after native begin succeeded; this grants no device permission."""
    probe = probe_device_lock(lock_file)
    if not probe.get('checked') or probe.get('free_at_check'):
        raise RuntimeError('Native device lock not confirmed after begin')
    value = read(path)
    value.update(owner=run_id, phase='native-macro', role=role,
                 started_unix=time.time(), deadline_unix=time.time()+120,
                 lock_file=str(lock_file), backend='native-macos',
                 authority='Actual App-held flock; this JSON is observability only',
                 lock_probe_after_begin=probe)
    save(path, value)


def heartbeat(path, run_id):
    value = read(path)
    if value.get('owner') != run_id:
        raise PermissionError('Workspace lease owner changed')
    value.update(deadline_unix=time.time()+120, heartbeat_unix=time.time())
    save(path, value)


def finished(path, run_id, lock_file):
    probe = probe_device_lock(lock_file)
    value = read(path)
    if value.get('owner') != run_id:
        return {'lease_updated': False, 'reason': 'owner_changed', 'lock_probe': probe}
    released = probe.get('checked') and probe.get('free_at_check')
    value.update(phase='released' if released else 'native-cleanup-unconfirmed',
                 last_owner=run_id, lock_probe_after_close=probe,
                 cleanup_unix=time.time())
    if released:
        value.update(owner=None, role=None, released_unix=time.time())
    else:
        value['deadline_unix'] = time.time()+130
    save(path, value)
    return {'lease_updated': True, 'actual_lock_released': bool(released), 'lock_probe': probe}
