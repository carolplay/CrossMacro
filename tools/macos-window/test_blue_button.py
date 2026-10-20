import tempfile,unittest
from pathlib import Path
from PIL import Image
from window_macro import Observation,require_text,validate_condition

class BlueButtonTests(unittest.TestCase):
 def test_enabled_blue_disabled_gray_and_wait_color(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'button.png'
   for color,enabled in [((60,160,240),True),((92,100,110),False),((30,65,95),False)]:
    Image.new('RGB',(30,20),color).save(p)
    o=Observation('全部执行',p,{},None)
    condition={'all':['全部执行'],'blue_regions':[{'bounds':[0,0,30,20],'min':.4}]}
    validate_condition(condition,[30,20])
    if enabled:require_text(o,condition)
    else:
     with self.assertRaises(RuntimeError):require_text(o,condition)
 def test_outside_bounds_rejected_before_execution(self):
  with self.assertRaises(ValueError):validate_condition({'blue_regions':[{'bounds':[0,0,31,20]}]},[30,20])
