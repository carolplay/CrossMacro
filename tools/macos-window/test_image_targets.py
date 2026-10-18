import tempfile
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
import window_macro as macro
from image_targets import match

class ImageTargetsTests(unittest.TestCase):
    def test_bounded_translated_template_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            r=Path(directory);rng=np.random.default_rng(71)
            source=rng.integers(0,256,(100,140,3),dtype=np.uint8)
            template=rng.integers(0,256,(18,22,3),dtype=np.uint8);source[38:56,63:85]=template
            Image.fromarray(source).save(r/'source.png');Image.fromarray(template).save(r/'template.png')
            obs=macro.Observation('PAGE',r/'source.png',{}, {'templates':{'target':str(r/'template.png')}})
            spec={'template':'target','bounds':[40,20,120,85],'mode':'grayscale','min_score':.95}
            self.assertEqual([74,47],match(obs,spec)['point'])
            self.assertGreater(match(obs,spec)['score'],.99)
            macro.require_text(obs,{'all':['PAGE'],'template_regions':[spec]})
            self.assertEqual([74,47],macro.resolve_point({'image_target':spec},obs,[140,100]))
            absent={**spec,'bounds':[0,0,40,35]}
            macro.require_text(obs,{'all':['PAGE'],'template_regions':[{**absent,'present':False}]})
            with self.assertRaises(RuntimeError):macro.resolve_point({'image_target':absent},obs,[140,100])
    def test_invalid_targets_rejected(self):
        for spec in [{'template':'../file','bounds':[0,0,40,40]}, {'template':'x','bounds':[0,0,101,40]}, {'template':'x','bounds':[0,0,40,40],'min_score':.2}]:
            with self.assertRaises(ValueError):macro.validate_image_spec(spec,[100,100])
    def test_missing_binding_does_not_guess_a_target(self):
        with self.assertRaisesRegex(RuntimeError,'Missing configured'):
            match(macro.Observation('PAGE','unused'),{'template':'x','bounds':[0,0,40,40]})
