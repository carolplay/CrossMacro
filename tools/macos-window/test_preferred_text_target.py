import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import window_macro as macro


def line(text='盾兵', confidence=1, x=.2):
    return {'text': text, 'confidence': confidence, 'bounds': [x, .3, .2, .1]}


def target():
    return {'text': '盾兵', 'bounds': [10, 20, 70, 70], 'offset': [10, 5],
            'min_confidence': .5, 'crop_ocr': True, 'prefer_frame_ocr': True}


class PreferredTargetTests(unittest.TestCase):
    def observation(self, path, lines):
        return macro.Observation('PAGE', path, {'width': 100, 'height': 100, 'lines': lines}, {'binary': 'fixture', 'language': 'zh-Hans'})

    def test_unique_inbounds_fullframe_target_skips_crop(self):
        observed = self.observation('not-needed', [line(confidence=.5)])
        with patch.object(macro.subprocess, 'run') as crop:
            self.assertEqual([40, 40], macro.resolve_point({'text_target': target()}, observed, [100, 100]))
        crop.assert_not_called()
        self.assertEqual('full-frame-preferred', observed.visual_checks[-1]['text_target_source'])

    def test_ambiguous_lowconfidence_outside_and_missing_use_sameframe_crop(self):
        for lines in ([line(), line(x=.4)], [line(confidence=.49)], [line(x=.8)], []):
            with self.subTest(lines=lines), tempfile.TemporaryDirectory() as d:
                path = Path(d)/'frame.png'; Image.new('RGB', (100, 100)).save(path)
                observed = self.observation(path, lines)
                result = Mock(stdout=json.dumps({'lines': [line()]}))
                with patch.object(macro.subprocess, 'run', return_value=result) as crop:
                    self.assertEqual([38, 43], macro.resolve_point({'text_target': target()}, observed, [100, 100]))
                    self.assertEqual(1, crop.call_count)

    def test_outside_resolved_point_is_rejected_without_crop_fallback(self):
        observed = self.observation('not-needed', [line()]); spec = target(); spec['offset'] = [90, 0]
        with patch.object(macro.subprocess, 'run') as crop:
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                macro.resolve_point({'text_target': spec}, observed, [100, 100])
        crop.assert_not_called()

    def test_regex_and_substring_modes_share_same_scope(self):
        for spec in [{**target(), 'text': '盾.*', 'regex': True}, {**target(), 'text': '盾', 'exact': False}]:
            self.assertEqual([40, 40], macro.resolve_point({'text_target': spec}, self.observation('unused', [line()]), [100, 100]))

    def test_preference_is_optin_and_requires_crop_fallback(self):
        for change in [{'prefer_frame_ocr': 'yes'}, {'crop_ocr': False}]:
            flow = {'reference_size': [100, 100], 'steps': [{'name': 'click', 'action': 'click', 'text_target': {**target(), **change}, 'before': ['PAGE'], 'after': ['DONE']}]}
            with self.assertRaises(ValueError):
                macro.validate_workflow(flow)


if __name__ == '__main__':
    unittest.main()
