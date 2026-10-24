import fcntl
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'macos-window'))
import native_backend
import native_visit


class VisitLeaseTests(unittest.TestCase):
    def run_fixture(self, directory, backend, batch):
        base = Path(directory); package = base/'package'; package.mkdir(); (package/'scripts').mkdir()
        lock = base/'visit.lock'; lock.touch(); lease = base/'lease.json'; config = base/'profile.json'
        config.write_text(json.dumps({'native_lock_file': str(lock), 'native_lease_file': str(lease), 'native_role': 'fixture'}))
        flow = {'action_id': 'fixture', 'action_version': '1.0.0', 'reference_size': [100, 100], 'steps': [{'name': 'observe', 'action': 'observe', 'before': ['READY']}]}
        pkg = types.ModuleType('macro_package'); pkg.load_manifest = lambda *args: ([('fixture', flow)], {'package_version': 'fixture'})
        batches = types.ModuleType('task_batch'); batches.run_batch = batch
        argv = ['native_visit.py', '--package-root', str(package), '--config', str(config), '--manifest', str(package/'manifest.json'), '--profile', 'main', '--log-root', str(base/'runs'), '--execute']
        with patch.dict(sys.modules, {'macro_package': pkg, 'task_batch': batches}), patch.object(native_backend, 'NativeBackend', return_value=backend), patch.object(sys, 'argv', argv), patch('builtins.print'):
            code = native_visit.main()
        summary = json.loads(next((base/'runs').glob('*/summary.json')).read_text())
        return code, summary, lease

    def test_denied_native_start_never_writes_lease_or_runs_tasks(self):
        backend = Mock(); backend.status = {}; backend.start.side_effect = PermissionError('not enabled')
        batch = Mock()
        with tempfile.TemporaryDirectory() as directory:
            code, summary, lease = self.run_fixture(directory, backend, batch)
            self.assertFalse(lease.exists())
        self.assertEqual(1, code); batch.assert_not_called(); backend.close.assert_called_once()
        self.assertEqual('not_executed', summary['tasks'][0]['status'])

    def test_successful_batch_records_actual_lock_and_releases_metadata_after_close(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory)/'visit.lock'; lock.touch(); held = lock.open('r')
            backend = Mock(); backend.status = {'backend': 'native-macos'}
            backend.start.side_effect = lambda: fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def close():
                fcntl.flock(held, fcntl.LOCK_UN); held.close()
            backend.close.side_effect = close
            def batch(config, tasks, actual):
                lease = json.loads(Path(config['native_lease_file']).read_text())
                self.assertEqual(config['native_run_id'], lease['owner'])
                self.assertEqual('native-macro', lease['phase'])
                actual.activity_callback()
                return {'tasks': [{'task': 'fixture', 'status': 'passed'}]}
            code, summary, lease = self.run_fixture(directory, backend, batch)
            final = json.loads(lease.read_text())
        self.assertEqual(0, code)
        self.assertTrue(summary['lease_cleanup']['actual_lock_released'])
        self.assertEqual('released', final['phase']); self.assertIsNone(final['owner'])


if __name__ == '__main__':
    unittest.main()
