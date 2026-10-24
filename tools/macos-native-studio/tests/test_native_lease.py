import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_lease


class NativeLeaseTests(unittest.TestCase):
    def test_metadata_follows_actual_lock_and_never_claims_early_release(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d)/'visit.lock'; lock.touch(); lease = Path(d)/'lease.json'
            lease.write_text(json.dumps({'history': 'preserve'}))
            with lock.open('r') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                native_lease.started(lease, 'native-run', lock, 'fixture-role')
                native_lease.heartbeat(lease, 'native-run')
                result = native_lease.finished(lease, 'native-run', lock)
                self.assertFalse(result['actual_lock_released'])
                self.assertEqual('native-cleanup-unconfirmed', native_lease.read(lease)['phase'])
            self.assertTrue(native_lease.finished(lease, 'native-run', lock)['actual_lock_released'])
            actual = native_lease.read(lease)
            self.assertIsNone(actual['owner']); self.assertEqual('preserve', actual['history'])
            self.assertEqual('', lock.read_text())

    def test_free_lock_cannot_be_recorded_as_started(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d)/'visit.lock'; lock.touch(); lease = Path(d)/'lease.json'
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
                native_lease.started(lease, 'run', lock)
            self.assertFalse(lease.exists())

    def test_cleanup_and_heartbeat_do_not_overwrite_a_different_owner(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d)/'visit.lock'; lock.touch(); lease = Path(d)/'lease.json'
            lease.write_text(json.dumps({'owner': 'other', 'phase': 'preparation'})); before = lease.read_text()
            result = native_lease.finished(lease, 'old-run', lock)
            self.assertFalse(result['lease_updated'])
            with self.assertRaises(PermissionError):
                native_lease.heartbeat(lease, 'old-run')
            self.assertEqual(before, lease.read_text())


if __name__ == '__main__':
    unittest.main()
