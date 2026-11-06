import json,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from window_macro import read_frame_ocr,read_crop_ocr,Observation,WorkflowBudgetExceeded
class OcrTimeoutTests(unittest.TestCase):
 def test_timeout_retries_same_saved_command_once_and_keeps_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'retry.json';cmd=['vision','saved.jpg','zh-Hans'];ok=subprocess.CompletedProcess(cmd,0,'{}')
   with patch('window_macro.subprocess.run',side_effect=[subprocess.TimeoutExpired(cmd,15),ok]) as run:
    self.assertIs(read_frame_ocr(cmd,time.monotonic()+60,p),ok)
   self.assertEqual(run.call_count,2);self.assertEqual(run.call_args_list[0].args,run.call_args_list[1].args)
   self.assertEqual(json.loads(p.read_text())[0]['error'],'local-ocr-timeout');self.assertEqual(json.loads(p.read_text())[1]['status'],'recovered')
 def test_persistent_timeout_stops_after_two_attempts(self):
  with tempfile.TemporaryDirectory() as d,patch('window_macro.subprocess.run',side_effect=subprocess.TimeoutExpired(['vision'],15)) as run:
   with self.assertRaises(subprocess.TimeoutExpired):read_frame_ocr(['vision'],time.monotonic()+60,Path(d)/'retry.json')
   self.assertEqual(run.call_count,2)
 def test_non_timeout_failure_not_retried(self):
  with tempfile.TemporaryDirectory() as d,patch('window_macro.subprocess.run',side_effect=PermissionError('denied')) as run:
   with self.assertRaises(PermissionError):read_frame_ocr(['vision'],time.monotonic()+60,Path(d)/'retry.json')
   self.assertEqual(run.call_count,1)
 def test_expired_deadline_never_starts_ocr(self):
  with tempfile.TemporaryDirectory() as d,patch('window_macro.subprocess.run') as run:
   with self.assertRaises(WorkflowBudgetExceeded):read_frame_ocr(['vision'],time.monotonic()-1,Path(d)/'retry.json')
   run.assert_not_called()
 def test_local_process_exit_retries_same_image_and_preserves_stderr(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'retry.json';cmd=['vision','saved.png','zh-Hans'];ok=subprocess.CompletedProcess(cmd,0,'{}')
   error=subprocess.CalledProcessError(1,cmd,stderr='Vision request failed')
   with patch('window_macro.subprocess.run',side_effect=[error,ok]) as run:
    self.assertIs(read_frame_ocr(cmd,time.monotonic()+60,p),ok)
   self.assertEqual(run.call_count,2)
   self.assertEqual(run.call_args_list[0].args,run.call_args_list[1].args)
   self.assertEqual(json.loads(p.read_text())[0]['stderr'],'Vision request failed')
 def test_explicit_permission_error_is_logged_without_retry(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'retry.json';error=subprocess.CalledProcessError(1,['vision'],stderr='Operation not permitted')
   with patch('window_macro.subprocess.run',side_effect=error) as run:
    with self.assertRaises(subprocess.CalledProcessError):read_frame_ocr(['vision'],time.monotonic()+60,p)
   self.assertEqual(run.call_count,1);self.assertFalse(json.loads(p.read_text())[0]['retryable'])
 def test_crop_reuses_saved_path_and_remaining_workflow_budget(self):
  with tempfile.TemporaryDirectory() as d:
   crop=Path(d)/'page.png';obs=Observation('',Path(d)/'source.jpg',{},
       {'binary':'vision','language':'zh-Hans','deadline':20})
   ok=subprocess.CompletedProcess([],0,'{}')
   with patch('window_macro.time.monotonic',side_effect=[10,10,12,12]),patch('window_macro.subprocess.run',side_effect=[subprocess.TimeoutExpired([],10),ok]) as run:
    self.assertIs(read_crop_ocr(obs,crop),ok)
   self.assertEqual(run.call_args_list[0].kwargs['timeout'],10)
   self.assertEqual(run.call_args_list[1].kwargs['timeout'],8)
   self.assertEqual(run.call_args_list[0].args,run.call_args_list[1].args)
   self.assertTrue(crop.with_name('page-ocr-recovery.json').exists())
 def test_persistent_exit_is_bounded(self):
  with tempfile.TemporaryDirectory() as d,patch('window_macro.subprocess.run',side_effect=subprocess.CalledProcessError(1,['vision'],stderr='Vision failed')) as run:
   with self.assertRaises(subprocess.CalledProcessError):read_frame_ocr(['vision'],time.monotonic()+60,Path(d)/'retry.json')
   self.assertEqual(run.call_count,2)
if __name__=='__main__':unittest.main()
