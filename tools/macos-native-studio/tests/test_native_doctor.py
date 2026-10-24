import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_doctor import diagnose
import client


def ready():
    return {'screen_recording': True, 'accessibility': True, 'on_console': True,
            'session_available': True, 'screen_locked_diagnostic': False,
            'cua_dependency': False, 'input_enabled': True, 'run_id': None,
            'lock_file': '/tmp/shared.lock', 'app_path': '/tmp/Studio.app',
            'version': '0.1.0', 'bundle_id': 'io.crossmacro.macro-studio'}


class DoctorTests(unittest.TestCase):
    def test_ready_means_test_target_only_not_wos_acceptance(self):
        report = diagnose(ready(), '/tmp/shared.lock')
        self.assertTrue(report['ready_for_test_window'])
        self.assertFalse(report['wos_accepted'])
        self.assertFalse(report['input_sent'])

    def test_missing_permissions_and_session_report_separately(self):
        s = ready(); s.update(screen_recording=False, accessibility=False,
                              screen_locked_diagnostic=True, input_enabled=False)
        report = diagnose(s)
        self.assertIn('screen_recording_not_ready', report['blockers'])
        self.assertIn('accessibility_not_ready', report['blockers'])
        self.assertIn('screen_locked_or_unknown', report['blockers'])
        self.assertFalse(report['ready_for_test_window'])

    def test_unknown_state_and_active_executor_do_not_pass(self):
        self.assertFalse(diagnose({})['ready_for_test_window'])
        s = ready(); s['run_id'] = 'busy'
        self.assertIn('executor_already_active', diagnose(s)['blockers'])
        self.assertIn('shared_lock_mismatch', diagnose(ready(), '/tmp/other.lock')['blockers'])

    def test_doctor_only_reads_status_and_marks_running_disk_version_mismatch(self):
        b = Mock(); b.request.return_value = ready()
        with tempfile.TemporaryDirectory() as d, \
             patch.object(client, 'NativeBackend', return_value=b), \
             patch('native_doctor.signing_identity', return_value={'bundle_version': '0.2.0'}), \
             patch.object(sys, 'argv', ['client.py', 'doctor', '--output', d]), \
             patch('builtins.print'):
            client.main()
            import json
            result = json.loads((Path(d)/'doctor.json').read_text())
            self.assertTrue(result['restart_required'])
            self.assertFalse(result['input_sent'])
        b.request.assert_called_once_with('status')
        b.start.assert_not_called()
        b.click.assert_not_called()

    def self_test_backend(self, after_count):
        b = Mock(); b.config = {}
        window = {'id': 1, 'bundle_id': 'io.crossmacro.macro-studio',
                  'title': 'Macro Studio Test Target — 7', 'width': 600, 'height': 420}
        image = {'ocr': {'width': 600, 'height': 420, 'lines': [
            {'text': '点击计数 +1', 'bounds': [0.2, 0.3, 0.2, 0.1]}]}}
        b.request.side_effect = [ready(), {'windows': [window]}, image, image,
            {'windows': [{**window, 'title': 'Macro Studio Test Target — '+str(after_count)}]}]
        b.click.return_value = {'sent': True, 'effect_verified': False}
        return b

    def test_repeat_test_verifies_increment_from_actual_counter(self):
        b = self.self_test_backend(8)
        with patch.object(client, 'NativeBackend', return_value=b), \
             patch.object(sys, 'argv', ['client.py', 'self-test', '--execute']), \
             patch('builtins.print'):
            client.main()
        b.click.assert_called_once_with([180, 147])
        b.close.assert_called_once()

    def test_sent_event_without_effect_never_passes_test(self):
        b = self.self_test_backend(7)
        with patch.object(client, 'NativeBackend', return_value=b), \
             patch.object(sys, 'argv', ['client.py', 'self-test', '--execute']):
            with self.assertRaisesRegex(ValueError, 'did not increase'):
                client.main()
        b.close.assert_called_once()

class DiagnosticFailureTests(unittest.TestCase):
    def test_stopped_app_saves_unavailable_report_without_other_operations(self):
        import json
        b = Mock(); b.request.side_effect = FileNotFoundError('no socket')
        with tempfile.TemporaryDirectory() as d, patch.object(client, 'NativeBackend', return_value=b), patch.object(sys, 'argv', ['client.py', 'doctor', '--output', d]), patch('builtins.print'):
            self.assertEqual(2, client.main())
            report = json.loads((Path(d)/'doctor.json').read_text())
        self.assertFalse(report['ready_for_test_window'])
        self.assertEqual(['native_app_unavailable'], report['blockers'])
        b.request.assert_called_once_with('status'); b.start.assert_not_called()

    def test_failed_probe_creates_evidence_directory_and_preserves_error(self):
        import json
        b = DoctorTests().self_test_backend(7)
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/'new'/'evidence'
            with patch.object(client, 'NativeBackend', return_value=b), patch.object(sys, 'argv', ['client.py', 'self-test', '--execute', '--output', str(output)]):
                with self.assertRaisesRegex(ValueError, 'did not increase'):
                    client.main()
            report = json.loads((output/'result.json').read_text())
        self.assertEqual('failed', report['status'])
        self.assertEqual('ValueError', report['error_type'])
        b.close.assert_called_once()

class SharedLockProbeTests(unittest.TestCase):
    def test_existing_busy_lock_is_not_ready_and_contents_unchanged(self):
        import fcntl
        from native_doctor import probe_device_lock
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'visit.lock'; path.write_text('preserve')
            with path.open('r') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertFalse(probe_device_lock(path)['free_at_check'])
            self.assertTrue(probe_device_lock(path)['free_at_check'])
            self.assertEqual('preserve', path.read_text())

    def test_missing_lock_is_not_created_and_symlink_is_not_followed(self):
        from native_doctor import probe_device_lock
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'missing.lock'
            self.assertFalse(probe_device_lock(path)['checked']); self.assertFalse(path.exists())
            target = Path(d)/'real.lock'; target.touch()
            path.symlink_to(target)
            self.assertFalse(probe_device_lock(path)['checked'])

    def test_doctor_detects_another_executor_even_when_app_has_no_run(self):
        import json
        b = Mock(); b.request.return_value = ready()
        with tempfile.TemporaryDirectory() as d, patch.object(client, 'NativeBackend', return_value=b), patch('native_doctor.probe_device_lock', return_value={'checked': True, 'free_at_check': False}), patch('native_doctor.signing_identity', return_value={'bundle_version': '0.1.0'}), patch.object(sys, 'argv', ['client.py', 'doctor', '--output', d]), patch('builtins.print'):
            client.main()
            report = json.loads((Path(d)/'doctor.json').read_text())
        self.assertFalse(report['ready_for_test_window'])
        self.assertIn('shared_lock_busy', report['blockers'])
        b.start.assert_not_called()
