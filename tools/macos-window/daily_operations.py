"""Local per-identity UTC-day reservations for single-use game operations."""
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path


def reserve(config, operation, day=None):
    identity = config.get('identity_text')
    path = Path(config.get('daily_state_file', ''))
    if not identity or not path.is_absolute():
        raise ValueError('Daily operations need identity and an absolute local ledger path')
    day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
    actor = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    key = f'{actor}:{day}:{operation}'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {}
        if key in data:
            raise RuntimeError('Daily operation already reserved: ' + operation)
        data[key] = {'status': 'pending', 'game_day_utc': day, 'operation': operation,
                     'reserved_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return str(path), key


def confirm(reservation):
    path, key = Path(reservation[0]), reservation[1]
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text())
        if data[key]['status'] != 'pending':
            raise RuntimeError('Daily operation reservation is not pending')
        data[key].update(status='confirmed', confirmed_at=dt.datetime.now(dt.timezone.utc).isoformat())
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
