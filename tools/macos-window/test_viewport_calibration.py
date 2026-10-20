import unittest,tempfile
from pathlib import Path
from PIL import Image
import viewport_calibration as v
class ViewportTests(unittest.TestCase):
 def cfg(self):return {'viewport_calibration':{'id':'fixture','reference_size':[788,1079],'native_size':[769,1055],'titlebar_height':29}}
 def test_profile_and_footer_points(self):
  c=self.cfg();self.assertEqual(v.point(c,[138,65],[788,1079]),[135,64]);self.assertEqual(v.point(c,[640,1022],[788,1079]),[625,999]);self.assertEqual(v.point(c,[132,20],[788,1079]),[129,20])
 def test_unknown_or_large_layout_rejected(self):
  c=self.cfg();c['viewport_calibration']['native_size']=[600,800]
  with self.assertRaises(ValueError):v.calibration(c,[788,1079])
 def test_centered_content_requires_explicit_anchor_validation(self):
  c=self.cfg();c['viewport_calibration'].update(native_size=[642,948],mapping='centered-content')
  with self.assertRaises(ValueError):v.calibration(c,[788,1079])
  c['viewport_calibration']['validated_anchors']=['profile','city-footer']
  self.assertEqual(v.point(c,[138,65],[788,1079]),[97,61])
  self.assertEqual(v.point(c,[640,1022],[788,1079]),[536,898])
 def test_centered_content_normalization_preserves_target_position(self):
  c=self.cfg()['viewport_calibration'];c.update(native_size=[642,948],mapping='centered-content',validated_anchors=['fixture'])
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'frame.png';im=Image.new('RGB',(642,948),'blue')
   from PIL import ImageDraw
   ImageDraw.Draw(im).rectangle((92,56,102,66),fill='red');im.save(p);v.normalize_frame(p,c)
   with Image.open(p) as result:
    self.assertGreater(result.getpixel((138,65))[0],200)
    self.assertEqual(result.size,(788,1079))
 def test_keeps_chrome_height_and_raw_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'frame.png';im=Image.new('RGB',(769,1055),'blue');im.paste('red',(0,0,769,29));im.save(p);v.normalize_frame(p,self.cfg()['viewport_calibration'])
   with Image.open(p) as result:self.assertEqual(result.size,(788,1079));self.assertEqual(result.getpixel((100,28)),(255,0,0));self.assertEqual(result.getpixel((100,29)),(0,0,255))
   self.assertTrue(p.with_name('frame-native.png').exists())
