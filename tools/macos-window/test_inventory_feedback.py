from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import window_macro as macro

class InventoryFeedbackTests(unittest.TestCase):
    def observation(self, value, confidence=1):
        return macro.Observation('PAGE','unused',{'width':100,'height':100,'lines':[
            {'text':str(value),'confidence':confidence,'bounds':[.1,.1,.4,.2]}]})
    def test_lower_confidence_is_explicit_and_ambiguity_still_rejected(self):
        obs=self.observation('700,019',.3)
        with self.assertRaises(RuntimeError):macro.number_in_region(obs,[0,0,80,50])
        self.assertEqual(700019,macro.number_in_region(obs,[0,0,80,50],.3))
        obs.ocr_data['lines']*=2
        with self.assertRaises(RuntimeError):macro.number_in_region(obs,[0,0,80,50],.3)
    def test_reward_requires_positive_delta_and_never_clicks(self):
        region={'name':'reward','bounds':[0,0,80,50]}
        flow={'reference_size':[100,100],'steps':[
            {'name':'baseline','action':'observe','before':['PAGE'],'remember_numbers':[region]},
            {'name':'check','action':'observe','before':['PAGE'],'increased_numbers':[region]}]}
        for value,passed in [(100,False),(99,False),(101,True)]:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as directory:
                client=Mock();client.observe.side_effect=[self.observation(100),self.observation(value)]
                if passed:macro.execute({'log_dir':directory},flow,'all',backend=client)
                else:
                    with self.assertRaisesRegex(RuntimeError,'increase'):macro.execute({'log_dir':directory},flow,'all',backend=client)
                client.js.assert_not_called()
    def test_invalid_confidence_rejected_before_input(self):
        for confidence in [0,.2,True,'0.3',1.1]:
            flow={'reference_size':[100,100],'steps':[{'name':'read','action':'observe','before':['PAGE'],
               'remember_numbers':[{'name':'x','bounds':[0,0,80,50],'min_confidence':confidence}]}]}
            with self.assertRaises(ValueError):macro.validate_workflow(flow)

    def test_navigation_repeat_is_bounded_and_only_arrows(self):
        for key,count,valid in [('Up',4,True),('Up',0,False),('Up',21,False),('Return',4,False),('Up',True,False)]:
            flow={'reference_size':[100,100],'steps':[{'name':'scroll','action':'key','key':key,'key_count':count,'before':['LIST'],'after':['LIST']}]}
            if valid:macro.validate_workflow(flow)
            else:
                with self.assertRaises(ValueError):macro.validate_workflow(flow)

    def test_empty_reward_skips_its_delta_check_without_input(self):
        flow={'reference_size':[100,100],'steps':[
            {'name':'claim','action':'click','point':[10,10],'before':['READY'],'after':['DONE'],'skip_if':['EMPTY']},
            {'name':'delta','action':'observe','before':['DONE'],'skip_if_step_skipped':'claim',
             'increased_numbers':[{'name':'reward','bounds':[0,0,80,50]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.return_value='EMPTY'
            result=macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called()
        flow['steps'][1]['skip_if_step_skipped']='future-step'
        with self.assertRaises(ValueError):macro.validate_workflow(flow)

    def test_declared_completion_ends_before_another_game_input(self):
        flow={'reference_size':[100,100],'steps':[
            {'name':'next','action':'click','point':[10,10],'before':['READY'],'after':['DONE'],'finish_if':['EMPTY']}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.return_value='EMPTY'
            result=macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called()
            import json
            saved=json.loads(next(Path(directory).glob('*/result.json')).read_text())
            self.assertTrue(saved['steps'][0]['finished_early'])

    def test_reward_animation_retries_observation_without_repeating_click(self):
        region={'name':'reward','bounds':[0,0,80,50]}
        flow={'reference_size':[100,100],'steps':[
            {'name':'baseline','action':'observe','before':['PAGE'],'remember_numbers':[region]},
            {'name':'check','action':'observe','before':['PAGE'],'increased_numbers':[region],'observe_attempts':3}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=[self.observation(100),self.observation(100),self.observation(100),self.observation(105)]
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called();self.assertEqual(4,client.observe.call_count)
            import json
            d=json.loads(next(Path(directory).glob('*/result.json')).read_text())
            self.assertEqual(5,d['steps'][-1]['increased_numbers']['reward']['increase'])

    def test_red_indicator_requires_calibrated_pixels(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'frame.png';im=Image.new('RGB',(100,100),'white')
            for x in range(20,30):
                for y in range(20,30):im.putpixel((x,y),(250,20,20))
            im.save(p);obs=macro.Observation('SHOP',p)
            macro.require_text(obs,{'all':['SHOP'],'red_regions':[{'bounds':[20,20,30,30],'min':.8}]})
            with self.assertRaises(RuntimeError):macro.require_text(obs,{'all':['SHOP'],'red_regions':[{'bounds':[50,50,60,60],'min':.2}]})

    def test_multiple_queue_timers_require_both_positive_regions(self):
        data={'width':100,'height':100,'lines':[
            {'text':'00:10:00','confidence':1,'bounds':[.1,.1,.3,.1]},
            {'text':'00:20:00','confidence':1,'bounds':[.1,.6,.3,.1]}]}
        obs=macro.Observation('QUEUES 00:10:00 00:20:00','unused',data)
        condition={'all':['QUEUES'],'timer_regions':[{'bounds':[0,0,60,40],'min':1},{'bounds':[0,50,60,90],'min':1}]}
        macro.require_text(obs,condition)
        obs.ocr_data['lines'].pop()
        with self.assertRaises(RuntimeError):macro.require_text(obs,condition)

    def test_regex_target_selects_first_only_when_declared(self):
        data={'width':100,'height':100,'lines':[
            {'text':'5/6','confidence':1,'bounds':[.1,.6,.2,.1]},
            {'text':'3/6','confidence':1,'bounds':[.4,.2,.2,.1]}]}
        obs=macro.Observation('SCIENCE','unused',data)
        spec={'text':'[0-9]+/[0-9]+','regex':True,'bounds':[0,0,100,100],'min_confidence':.5}
        with self.assertRaises(RuntimeError):macro.resolve_point({'text_target':spec},obs,[100,100])
        spec['select']='top-left'
        self.assertEqual([50,25],macro.resolve_point({'text_target':spec},obs,[100,100]))
