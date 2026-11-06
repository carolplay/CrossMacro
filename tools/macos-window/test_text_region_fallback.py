import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
import window_macro as m

class TextRegionFallbackTests(unittest.TestCase):
 def condition(self):return {'text_regions':[{'bounds':[2,4,18,10],'pattern':'.*每日免费礼包.*','crop_ocr':True,'prefer_frame_ocr':True,'min_confidence':.3}]}
 def observation(self,path,text='VIP8每日免费礼包',confidence=.9,bounds=None):
  Image.new('RGB',(20,20),'navy').save(path)
  line={'text':text,'confidence':confidence,'bounds':bounds or [.1,.2,.8,.3]}
  return m.Observation(text,path,{'width':20,'height':20,'lines':[line]},{'binary':'fixture','language':'zh-Hans'})
 def cropped(self,text='VIP8每日免费礼包'):return Mock(stdout=json.dumps({'lines':[{'text':text,'confidence':.9}]}))
 def test_confident_scoped_full_frame_needs_no_second_ocr(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run') as ocr:
   obs=self.observation(Path(d)/'frame.png');m.require_text(obs,self.condition());ocr.assert_not_called();self.assertEqual(obs.visual_checks[0]['source'],'full-frame-preferred')
 def test_bad_full_frame_falls_back_to_same_image_crop(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=self.cropped()) as ocr:
   obs=self.observation(Path(d)/'frame.png','VIP8每囗免费礼包');m.require_text(obs,self.condition());ocr.assert_called_once();self.assertTrue((Path(d)/'derived/frame-text-2-4-18-10.png').exists())
 def test_title_outside_free_area_cannot_satisfy_condition(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=self.cropped('VIP8尊享礼包')) as ocr:
   obs=self.observation(Path(d)/'frame.png',bounds=[.1,.8,.8,.1])
   with self.assertRaises(RuntimeError):m.require_text(obs,self.condition())
   ocr.assert_called_once()
 def test_low_confidence_full_frame_is_not_accepted(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run',return_value=self.cropped()) as ocr:
   obs=self.observation(Path(d)/'frame.png',confidence=.1);m.require_text(obs,self.condition());ocr.assert_called_once()
 def test_flag_requires_crop_and_boolean(self):
  for patch_value in [{'prefer_frame_ocr':'yes'},{'crop_ocr':False}]:
   c=self.condition();c['text_regions'][0].update(patch_value)
   with self.assertRaises(ValueError):m.validate_condition(c,[20,20])

if __name__=='__main__':unittest.main()
