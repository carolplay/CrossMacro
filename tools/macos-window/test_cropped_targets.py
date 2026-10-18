import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
import window_macro as macro
class CroppedTargetTests(unittest.TestCase):
 def flow(self):return {'reference_size':[788,1079],'steps':[{'name':'select','action':'click','text_target':{'text':'Wood','bounds':[100,700,300,850],'offset':[0,-25],'crop_ocr':True},'before':['Search'],'after':['Resource']}]}
 def test_crop_geometry_and_same_frame_cache(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'frame.jpg';Image.new('RGB',(788,1079)).save(path);obs=macro.Observation('Search',path,{'lines':[],'width':788,'height':1079},{'binary':'fixture','language':'en-US'})
   line={'text':'Wood','confidence':1,'bounds':[.25,.4,.2,.2]};raw=Mock(stdout=json.dumps({'lines':[line],'width':800,'height':600}))
   with patch.object(macro.subprocess,'run',return_value=raw) as ocr:
    for _ in range(2):self.assertEqual([170,750],macro.resolve_point(self.flow()['steps'][0],obs,[788,1079]))
   self.assertEqual(1,ocr.call_count)
 def test_ambiguous_crop_sends_no_input(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'frame.jpg';Image.new('RGB',(788,1079)).save(path);obs=macro.Observation('Search',path,{'lines':[],'width':788,'height':1079},{'binary':'fixture','language':'en-US'})
   lines=[{'text':'Wood','confidence':1,'bounds':[x,.4,.1,.2]} for x in [.1,.7]]
   with patch.object(macro.subprocess,'run',return_value=Mock(stdout=json.dumps({'lines':lines}))):
    with self.assertRaisesRegex(RuntimeError,'found 2'):macro.resolve_point(self.flow()['steps'][0],obs,[788,1079])
 def test_crop_flag_must_be_boolean(self):
  flow=self.flow();flow['steps'][0]['text_target']['crop_ocr']='yes'
  with self.assertRaises(ValueError):macro.validate_workflow(flow)
if __name__=='__main__':unittest.main()
