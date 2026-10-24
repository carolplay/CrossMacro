import base64,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
import window_macro as m

def encoded(size):
 data=io.BytesIO();Image.new('RGB',size,'navy').save(data,format='PNG');return base64.b64encode(data.getvalue()).decode()
def frame(size):return {'content':[{'type':'image','mimeType':'image/png','data':encoded(size)}]}
def original(size):return {'content':[{'type':'text','text':json.dumps({'originalScreenshotBase64':encoded(size)})}]}
def white_frame(size, raw=False):
 data=io.BytesIO();Image.new('RGB',size,'white').save(data,format='PNG')
 encoded_white=base64.b64encode(data.getvalue()).decode()
 if raw:return {'content':[{'type':'text','text':json.dumps({'originalScreenshotBase64':encoded_white})}]}
 return {'content':[{'type':'image','mimeType':'image/png','data':encoded_white}]}
class PlaceholderTests(unittest.TestCase):
 def client(self,replies):
  c=m.CuaMcp.__new__(m.CuaMcp);c.config={'ocr_binary':'unused','language':'en-US'};c.js=Mock(side_effect=replies);return c
 def test_placeholder_reads_original_pixels_without_input(self):
  c=self.client([frame((1,1)),original((10,12))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=Mock(stdout=json.dumps({'width':10,'height':12,'lines':[]}))) as ocr:
   c.observe(Path(d),'frame',[10,12]);self.assertIn('getAXStateAndScreenshot({emit:false})',c.js.call_args_list[1].args[0]);self.assertNotIn('click',c.js.call_args_list[1].args[0]);self.assertTrue((Path(d)/'frame-unusable-frame.png').exists());ocr.assert_called_once()
 def test_transport_thumbnail_uses_original_not_scaling(self):
  c=self.client([frame((5,6)),original((10,12))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=Mock(stdout=json.dumps({'width':10,'height':12,'lines':[]}))):
   obs=c.observe(Path(d),'frame',[10,12]);self.assertEqual(Image.open(obs.image_path).size,(10,12))
 def test_persistent_placeholder_stops_before_ocr(self):
  c=self.client([frame((1,1)),original((1,1)),original((1,1)),original((1,1))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run') as ocr:
   with self.assertRaises(m.FatalExecutionError):c.observe(Path(d),'frame',[10,12])
   self.assertEqual(c.js.call_count,4);ocr.assert_not_called()
 def test_original_window_resize_stops(self):
  c=self.client([frame((20,24)),original((20,24)),original((20,24)),original((20,24))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run') as ocr:
   with self.assertRaises(m.FatalExecutionError):c.observe(Path(d),'frame',[10,12])
   self.assertEqual(c.js.call_count,4);ocr.assert_not_called()
 def test_transient_original_size_recovers_without_input_or_scaling(self):
  c=self.client([frame((5,6)),original((5,6)),original((10,12))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=Mock(stdout=json.dumps({'width':10,'height':12,'lines':[]}))):
   obs=c.observe(Path(d),'frame',[10,12])
   with Image.open(obs.image_path) as image:self.assertEqual(image.size,(10,12))
   event=json.loads((Path(d)/'frame-frame-recovery.json').read_text())
   self.assertEqual(event['invalid_sizes'],[[5,6]]);self.assertFalse(event['input_sent'])
   self.assertTrue((Path(d)/'frame-invalid-original-0.png').exists())
   self.assertFalse(any('click' in call.args[0] for call in c.js.call_args_list))
 def test_permission_failure_is_not_retried(self):
  c=self.client([frame((1,1)),PermissionError('access denied')])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run') as ocr:
   with self.assertRaises(PermissionError):c.observe(Path(d),'frame',[10,12])
   self.assertEqual(c.js.call_count,2);ocr.assert_not_called()
 def test_full_size_white_placeholder_reads_original(self):
  c=self.client([white_frame((10,12)),original((10,12))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=Mock(stdout=json.dumps({'width':10,'height':12,'lines':[]}))) as ocr:
   c.observe(Path(d),'frame',[10,12]);self.assertEqual(c.js.call_count,2);ocr.assert_called_once()
 def test_persistent_full_size_white_frame_stops_before_ocr(self):
  c=self.client([white_frame((10,12))]+[white_frame((10,12),raw=True)]*3)
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run') as ocr:
   with self.assertRaises(m.FatalExecutionError):c.observe(Path(d),'frame',[10,12])
   self.assertEqual(c.js.call_count,4);ocr.assert_not_called()
 def test_transient_white_original_is_retried_without_input(self):
  c=self.client([white_frame((10,12)),white_frame((10,12),raw=True),original((10,12))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=Mock(stdout=json.dumps({'width':10,'height':12,'lines':[]}))):
   c.observe(Path(d),'frame',[10,12]);event=json.loads((Path(d)/'frame-frame-recovery.json').read_text())
   self.assertEqual(event['invalid_reasons'],['blank-frame']);self.assertFalse(event['input_sent'])
 def test_missing_host_screenshot_gets_one_fresh_atomic_read(self):
  error=RuntimeError("ENOENT: no such file or directory, open '/tmp/com.openai.sky.CUAService/Game Screenshot 2026.jpeg'")
  c=self.client([error,original((10,12))])
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=Mock(stdout=json.dumps({'width':10,'height':12,'lines':[]}))):
   c.observe(Path(d),'frame',[10,12]);self.assertTrue((Path(d)/'frame-missing-screenshot.json').exists());self.assertEqual(c.js.call_count,2)
 def test_unrelated_missing_file_or_window_is_not_retried(self):
  for message in ["ENOENT: no such file or directory, open '/tmp/other.jpeg'", 'noWindowsAvailable', 'Permission denied']:
   c=self.client([RuntimeError(message)])
   with self.subTest(message=message),tempfile.TemporaryDirectory() as d:
    with self.assertRaises(RuntimeError):c.observe(Path(d),'frame',[10,12])
    self.assertEqual(c.js.call_count,1)
