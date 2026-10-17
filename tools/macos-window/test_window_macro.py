import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import window_macro as macro


class WindowMacroTests(unittest.TestCase):
    def workflow(self):
        return json.loads((Path(__file__).parent/'wos-profile.json').read_text())

    def test_ocr_accepts_whitespace_and_width_variants(self):
        macro.require_text('ＩＤ： １２３\n领主 档案',['ID:123','领主档案'])

    def test_ocr_rejects_missing_identity(self):
        with self.assertRaises(RuntimeError):
            macro.require_text('ID:123',['124'])

    def test_claim_verification_rejects_unchanged_reward_dialog(self):
        condition = {'any':['获得奖励','点击任意'], 'none':['挂机时间']}
        with self.assertRaises(RuntimeError):
            macro.require_text('挂机时间 09:00:00 获得奖励', condition)
        macro.require_text('获得奖励 点击任意位置继续', condition)

    def test_reset_verification_rejects_old_or_ambiguous_timer(self):
        condition = {'all':['挂机收益'], 'timer_seconds':{'max':60}}
        macro.require_text('挂机收益 00:00:05',condition)
        for text in ('挂机收益 09:00:00', '挂机收益', '挂机收益 00:00:05 00:00:06'):
            with self.assertRaises(RuntimeError):
                macro.require_text(text,condition)

    def test_timer_preserves_boundary_before_numeric_hourly_rate(self):
        macro.require_text('挂机收益\n00:10:22\n3,400/小时',
                           {'all':['挂机收益'],'timer_seconds':{'min':60,'max':32400}})

    def test_regional_timer_ignores_unrelated_vip_expiry(self):
        data={'width':100,'height':100,'lines':[
            {'text':'05:00:00','bounds':[.5,.5,.2,.1]},
            {'text':'16d 03:00:00','bounds':[.2,.9,.4,.1]}]}
        text=macro.Observation('VIP 每日免费礼包 05:00:00 16d 03:00:00','unused',data)
        condition={'all':['VIP','每日免费礼包'],'timer_seconds':{'bounds':[40,40,80,70],'min':1,'max':86400}}
        macro.require_text(text,condition)
        self.assertEqual(18000,text.visual_checks[-1]['timer_seconds'])
        with self.assertRaises(RuntimeError):
            macro.require_text(str(text),condition)
        condition['timer_seconds']['max']=10
        with self.assertRaises(RuntimeError):
            macro.require_text(text,condition)

    def test_animation_observation_retry_does_not_repeat_click(self):
        workflow = self.workflow()
        workflow['steps'][1]['observe_attempts'] = 2
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(macro,'CuaMcp') as client_class:
                client = client_class.return_value
                client.observe.side_effect = ['英雄 背包 野外', '动画中', '领主档案']
                macro.execute({'log_dir':directory},workflow,'02-open-profile')
                self.assertEqual(1,client.js.call_count)

    def test_disabled_button_skips_claim_without_sending_input(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow is needed for optional local color checks')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'button.png'
            Image.new('RGB',(20,20),(100,100,100)).save(path)
            condition = {'all':['探险'], 'green_regions':[{'bounds':[0,0,20,20],'max':0.08}]}
            workflow = {'reference_size':[20,20], 'steps':[
                {'name':'claim','action':'click','point':[10,10],
                 'before':['挂机收益'],'after':['获得奖励'],'skip_if':condition}]}
            with patch.object(macro,'CuaMcp') as client_class:
                client = client_class.return_value
                client.observe.return_value = macro.Observation('探险',path)
                macro.execute({'log_dir':directory},workflow,'all')
                client.js.assert_not_called()
            Image.new('RGB',(20,20),(20,190,40)).save(path)
            with self.assertRaises(RuntimeError):
                macro.require_text(macro.Observation('探险',path),condition)

    def test_invalid_skip_condition_is_rejected_before_any_input(self):
        workflow = self.workflow()
        workflow['steps'][1]['skip_if'] = {'none':['anything']}
        with self.assertRaises(ValueError):
            macro.validate_workflow(workflow)

    def test_audio_failure_falls_back_to_visual_without_repeating_click(self):
        workflow=self.workflow();workflow['steps'][1]['audio_event']='profile-open'
        with tempfile.TemporaryDirectory() as directory:
            config={'log_dir':directory,'audio_capture':{'binary':'capture'},'target':{'bundle_id':'game'},
                    'audio_feedback':{'profile-open':{'template':'missing.wav'}}}
            with patch.object(macro,'CuaMcp') as cls, patch('audio_feedback.AudioCapture') as capture, patch('audio_feedback.classify',side_effect=OSError('missing template')):
                capture.return_value.stop.return_value={'usable_audio':True,'wav':'sample.wav'}
                client=cls.return_value;client.observe.side_effect=['英雄 背包 野外','领主档案']
                macro.execute(config,workflow,'02-open-profile')
                self.assertEqual(1,client.js.call_count)
                self.assertEqual(2,client.observe.call_count)

    def test_rejects_click_without_visual_completion(self):
        workflow = self.workflow()
        del workflow['steps'][1]['after']
        with self.assertRaises(ValueError):
            macro.validate_workflow(workflow)

    def test_rejects_out_of_window_point(self):
        workflow = self.workflow()
        workflow['steps'][1]['point'] = [788,65]
        with self.assertRaises(ValueError):
            macro.validate_workflow(workflow)

    def test_export_keeps_steps_editable_and_uses_no_native_clicks(self):
        with tempfile.TemporaryDirectory(prefix='macro test ') as directory:
            output = Path(directory)/'sample.macro'
            macro.export_macro(Path(directory)/'config.json',Path(__file__).parent/'wos-profile.json',output)
            content = output.read_text()
            self.assertEqual(4,len([line for line in content.splitlines() if line.startswith('shell ')]))
            self.assertIn('04-return-city',content)
            self.assertNotIn('\nclick ',content)

    def test_failed_ocr_sends_no_click_and_logs_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'log_dir':directory}
            with patch.object(macro,'CuaMcp') as client_class:
                client = client_class.return_value
                client.observe.return_value = 'Unexpected dialog'
                with self.assertRaises(RuntimeError):
                    macro.execute(config,self.workflow(),'02-open-profile')
                client.js.assert_not_called()
                client.close.assert_called_once()
            reports = list(Path(directory).glob('*/result.json'))
            self.assertEqual('failed',json.loads(reports[0].read_text())['status'])

    def test_busy_coordinator_prevents_backend_start(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'log_dir':directory,'guard_command':['coordination','status']}
            with patch.object(macro.subprocess,'check_output',return_value='{"active":{"role":"other"}}'), patch.object(macro,'CuaMcp') as client:
                with self.assertRaises(RuntimeError):
                    macro.execute(config,self.workflow(),'01-check-city')
                client.assert_not_called()

    def test_worker_reuses_backend_without_starting_or_closing_it_per_step(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as directory:
            backend = MagicMock()
            backend.observe.return_value = '英雄 背包 野外'
            config = {'log_dir':directory}
            macro.execute(config,self.workflow(),'01-check-city',backend=backend)
            macro.execute(config,self.workflow(),'01-check-city',backend=backend)
            self.assertEqual(2,backend.observe.call_count)
            backend.start.assert_not_called()
            backend.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
