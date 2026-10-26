import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_backend import NativeOperationBlocked,failure_details

class ErrorLayerTests(unittest.TestCase):
 def test_app_refusals_remain_fatal_but_distinguish_layers(self):
  for code,category in [('permission_denied:screen_recording','system_permission'),('permission_denied:input','system_permission'),('input_not_enabled_in_app','input_activation_or_session'),('session_inactive','session'),('active_executor','execution_lock'),('lock_admission_timeout','execution_lock'),('lock_admission_cancelled','session'),('window_size_changed_or_target_gone','target_window'),('png_encoding_failed','native_operation')]:
   with self.subTest(code=code):
    error=NativeOperationBlocked(code)
    self.assertIsInstance(error,PermissionError)
    details=failure_details(error)
    self.assertEqual(category,details['error_category']);self.assertEqual(code,details['error_code'])
 def test_unspecified_permission_and_transport_not_called_tcc(self):
  self.assertEqual('access_or_policy_unspecified',failure_details(PermissionError('socket mode'))['error_category'])
  self.assertEqual('transport_or_app_unavailable',failure_details(TimeoutError('timeout'))['error_category'])
  self.assertNotIn('error_code',failure_details(RuntimeError('unexpected')))
 def test_development_expiry_is_not_missing_os_permission(self):
  self.assertEqual('input_activation_or_session',failure_details(NativeOperationBlocked('development_authorization_expired'))['error_category'])
