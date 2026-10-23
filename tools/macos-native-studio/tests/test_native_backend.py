import json,sys,unittest,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'macos-window'))
from native_backend import NativeBackend
import backend_input
class NativeTests(unittest.TestCase):
 def test_native_dispatch_sends_no_javascript(self):
  b=Mock();b.native_protocol=True
  backend_input.click(b,[3,4]);backend_input.key(b,'Up',2,600)
  b.click.assert_called_once_with([3,4]);b.key.assert_called_once_with('Up',count=2,duration_ms=600);b.js.assert_not_called()
 def test_cua_dispatch_unchanged(self):
  b=Mock();backend_input.click(b,[3,4]);self.assertIn('target.click([3, 4])',b.js.call_args.args[0]);b.click.assert_not_called()
 def test_disabled_native_never_begins(self):
  b=NativeBackend({});b.request=Mock(return_value={'cua_dependency':False,'input_enabled':False})
  with self.assertRaises(PermissionError):b.start()
  self.assertEqual([('status',)],[c.args for c in b.request.call_args_list])
 def test_wrong_lock_never_begins(self):
  b=NativeBackend({'native_window_id':123,'native_expected_size':[100,100],'native_lock_file':'/tmp/right'})
  b.request=Mock(return_value={'cua_dependency':False,'input_enabled':True,'lock_file':'/tmp/wrong'})
  with self.assertRaises(ValueError):b.start()
  self.assertEqual(1,b.request.call_count)
 def test_close_clears_session_even_if_app_stopped(self):
  b=NativeBackend({});b.session='own-local-session';b.request=Mock(side_effect=ConnectionError('stopped'))
  with self.assertRaises(ConnectionError):b.close()
  self.assertIsNone(b.session)
 def test_existing_engine_uses_typed_native_inputs(self):
  import window_macro
  with tempfile.TemporaryDirectory() as d:
   b=Mock();b.native_protocol=True;b.observe.side_effect=['READY','DONE','DONE','DONE']
   flow={'reference_size':[100,100],'steps':[{'name':'click','action':'click','point':[30,40],'before':['READY'],'after':['DONE']},{'name':'key','action':'key','key':'Up','before':['DONE'],'after':['DONE']}]}
   window_macro.execute({'log_dir':d},flow,'all',backend=b)
   b.click.assert_called_once_with([30,40]);b.key.assert_called_once_with('Up',count=1,duration_ms=600);b.js.assert_not_called()
 def test_native_permission_error_stops_remaining_batch(self):
  import task_batch
  with tempfile.TemporaryDirectory() as d:
   b=Mock();b.native_protocol=True;b.observe.side_effect=PermissionError('permission_denied:input')
   flow={'reference_size':[100,100],'steps':[{'name':'observe','action':'observe','before':['READY']}]}
   result=task_batch.run_batch({'log_dir':d},[('first',flow),('next',flow)],b)
   self.assertEqual(['fatal','not_executed'],[x['status'] for x in result['tasks']]);b.js.assert_not_called();b.click.assert_not_called()
 def test_no_interpreter(self):
  self.assertFalse(hasattr(NativeBackend,'js'))
if __name__=='__main__':unittest.main()
