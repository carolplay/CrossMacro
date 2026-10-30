"""Storage preflight and atomic metadata for local run evidence; no device access."""
import json
import os
from pathlib import Path
import shutil
import tempfile


def require_headroom(destination, minimum_bytes=1024**3):
    if type(minimum_bytes) is not int or minimum_bytes < 0:
        raise ValueError('minimum_free_bytes must be a non-negative integer')
    parent = Path(destination).resolve()
    while not parent.exists():
        parent = parent.parent
    available = shutil.disk_usage(parent).free
    if available < minimum_bytes:
        raise OSError('Insufficient evidence storage: %d bytes free, %d required' % (available, minimum_bytes))
    return {'free_bytes': available, 'minimum_bytes': minimum_bytes}


def atomic_json(path, data):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.new', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
