import json,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from window_macro import read_frame_ocr,FatalExecutionError
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
   with self.assertRaises(FatalExecutionError):read_frame_ocr(['vision'],time.monotonic()-1,Path(d)/'retry.json')
   run.assert_not_called()
if __name__=='__main__':unittest.main()
