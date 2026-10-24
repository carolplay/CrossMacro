import copy
import unittest
import viewport_preflight as v
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import window_macro as macro
from test_screenshot_placeholder import frame, original


class PreflightTests(unittest.TestCase):
    def config(self):
        return {'validated_viewport_profiles': [{
            'id': 'known-reference', 'reference_size': [788, 1079],
            'native_size': [788, 1079], 'titlebar_height': 28,
            'validated_anchors': ['live-profile', 'live-city-footer'],
            'entry_condition': {'all': ['英雄', '背包', '野外']}}]}

    def test_exact_known_profile_without_mutating_configuration(self):
        c = self.config(); before = copy.deepcopy(c)
        profile, condition = v.candidate(c, [788, 1079], [788, 1079])
        self.assertEqual(profile['id'], 'known-reference')
        self.assertEqual(condition['all'], ['英雄', '背包', '野外'])
        self.assertEqual(c, before)

    def test_unknown_size_and_midrun_change_never_adapt(self):
        self.assertIsNone(v.candidate(self.config(), [788, 1079], [790, 1080]))
        self.assertIsNone(v.candidate(self.config(), [788, 1079], [788, 1079], locked=True))

    def test_missing_evidence_or_condition_rejected(self):
        for key in ('validated_anchors', 'entry_condition'):
            c = self.config(); del c['validated_viewport_profiles'][0][key]
            with self.assertRaises(ValueError): v.candidate(c, [788, 1079], [788, 1079])

    def test_ambiguous_profile_and_invalid_mapping_rejected(self):
        c = self.config(); c['validated_viewport_profiles'] *= 2
        with self.assertRaises(ValueError): v.candidate(c, [788, 1079], [788, 1079])

    def client(self, lines):
        c = macro.CuaMcp.__new__(macro.CuaMcp)
        c.config = self.config()
        c.config.update(ocr_binary='unused', viewport_calibration={
            'id': 'old', 'reference_size': [788, 1079],
            'native_size': [769, 1055], 'titlebar_height': 28})
        c.js = Mock(side_effect=[frame((788, 1079)), original((788, 1079))])
        ocr = Mock(stdout=json.dumps({'width': 788, 'height': 1079,
                                     'lines': [{'text': t} for t in lines]}))
        return c, ocr

    def test_known_size_anchor_adopted_and_later_resize_stops(self):
        c, ocr = self.client(['英雄', '背包', '野外'])
        with tempfile.TemporaryDirectory() as d, patch.object(macro.subprocess, 'run', return_value=ocr):
            c.observe(Path(d), 'first', [788, 1079])
            self.assertEqual(c.config['viewport_calibration']['native_size'], [788, 1079])
            self.assertTrue((Path(d)/'first-viewport-preflight.json').exists())
            c.js = Mock(side_effect=[frame((769, 1055)), original((769, 1055)),
                                    original((769, 1055)), original((769, 1055))])
            with self.assertRaises(macro.FatalExecutionError):
                c.observe(Path(d), 'changed', [788, 1079])

    def test_wrong_page_does_not_adopt_calibration(self):
        c, ocr = self.client(['充值礼包'])
        with tempfile.TemporaryDirectory() as d, patch.object(macro.subprocess, 'run', return_value=ocr):
            with self.assertRaises(macro.FatalExecutionError):
                c.observe(Path(d), 'wrong-page', [788, 1079])
            self.assertEqual(c.config['viewport_calibration']['id'], 'old')
            self.assertFalse(any('click' in call.args[0] for call in c.js.call_args_list))

    def test_action_report_records_selected_profile(self):
        with tempfile.TemporaryDirectory() as d:
            config = {'log_dir': d, 'viewport_calibration': {'id': 'previous'}}
            client = Mock()
            def observe(*args):
                config['viewport_calibration'] = {'id': 'selected'}
                return 'CITY'
            client.observe.side_effect = observe
            flow = {'reference_size': [788, 1079], 'steps': [
                {'name': 'entry', 'action': 'observe', 'before': ['CITY']}]}
            macro.execute(config, flow, 'all', backend=client)
            result = json.loads(next(Path(d).glob('*/result.json')).read_text())
            self.assertEqual(result['viewport_calibration']['id'], 'selected')
        c = self.config(); c['validated_viewport_profiles'][0]['reference_size'] = [900, 1200]
        with self.assertRaises(ValueError): v.candidate(c, [788, 1079], [788, 1079])
