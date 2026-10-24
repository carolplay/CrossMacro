import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import runtime_storage as storage

class StorageTests(unittest.TestCase):
 def test_failed_atomic_write_preserves_previous_checkpoint(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'checkpoint.json';path.write_text('{"old":true}')
   def fail(data,stream,**kwargs):
    stream.write('partial');raise OSError('disk full')
   with patch.object(storage.json,'dump',side_effect=fail):
    with self.assertRaises(OSError):storage.atomic_json(path,{'new':True})
   self.assertEqual({'old':True},json.loads(path.read_text()));self.assertEqual([path],list(Path(d).iterdir()))
   storage.atomic_json(path,{'new':True});self.assertEqual({'new':True},json.loads(path.read_text()))
 def test_space_checked_at_existing_ancestor_without_creating_run(self):
  with tempfile.TemporaryDirectory() as d:
   target=Path(d)/'missing'/'runs'
   with patch.object(storage.shutil,'disk_usage',return_value=type('Usage',(),{'free':100})()):
    with self.assertRaises(OSError):storage.require_headroom(target,101)
    self.assertEqual(100,storage.require_headroom(target,100)['free_bytes'])
   self.assertFalse(target.parent.exists())
 def test_low_space_observation_stops_before_capture_request(self):
  from native_backend import NativeBackend
  from unittest.mock import Mock
  backend=NativeBackend({});backend.request=Mock()
  with patch.object(storage,'require_headroom',side_effect=OSError('storage reserve exhausted')):
   with self.assertRaises(OSError):backend.observe('/tmp','frame',[100,100])
  backend.request.assert_not_called()
 def test_invalid_threshold_rejected(self):
  for threshold in [True,-1,1.5]:
   with self.assertRaises(ValueError):storage.require_headroom('/tmp',threshold)
