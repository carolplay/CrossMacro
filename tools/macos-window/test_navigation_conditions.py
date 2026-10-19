import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
import window_macro as macro

class NavigationConditionsTests(unittest.TestCase):
    def test_scoped_menu_excludes_background_text_but_rejects_local_forbidden_text(self):
        bounds=[20,20,80,70]
        obs=macro.Observation('CITY Rally',Path('unused.png'),{}, {'binary':'unused','language':'zh-Hans'})
        obs.timer_regions[('page',*bounds)]=['Recommended strength','Attack']
        condition={'all':['Recommended strength','Attack'],'none':['Rally','Scout'],
                   'page_text_regions':[bounds],'page_text_only':True}
        macro.validate_condition(condition,[100,100])
        macro.require_text(obs,condition)
        with self.assertRaises(RuntimeError):
            macro.require_text(obs,{**condition,'page_text_only':False})
        obs.timer_regions[('page',*bounds)].append('Scout')
        with self.assertRaises(RuntimeError):
            macro.require_text(obs,condition)

    def test_scoped_menu_requires_a_bounded_region(self):
        with self.assertRaises(ValueError):
            macro.validate_condition({'all':['PAGE'],'page_text_only':True},[100,100])

    def test_only_bounded_arrows_are_allowed(self):
        step={'name':'scroll','action':'key','key':'Up','duration_ms':600,'before':['PAGE'],'after':['PAGE']}
        flow={'reference_size':[100,100],'steps':[step]}
        macro.validate_workflow(flow)
        for key in ['Return','super+a','a']:
            step['key']=key
            with self.assertRaises(ValueError):macro.validate_workflow(flow)
        step['key']='Up';step['duration_ms']=5000
        with self.assertRaises(ValueError):macro.validate_workflow(flow)

    def test_arrow_sends_one_input_then_verifies(self):
        flow={'reference_size':[100,100],'steps':[{'name':'scroll','action':'key','key':'Up','before':['PAGE'],'after':['TARGET'],'observe_attempts':2}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['PAGE','loading','TARGET']
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            self.assertEqual(1,client.js.call_count)
            self.assertIn('pressKey',client.js.call_args.args[0])
            self.assertEqual(3,client.observe.call_count)

    def test_repeated_navigation_waits_for_state_inside_each_gesture(self):
        flow={'reference_size':[100,100],'steps':[{'name':'scroll','action':'key','key':'Up','key_count':5,'before':['PAGE'],'after':['TARGET']}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['PAGE','TARGET']
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            payload=client.js.call_args.args[0]
            self.assertIn('i<5',payload)
            self.assertRegex(payload,r'for.*\{.*pressKey.*getAXState\(\{emit:false\}\).*\}')
            self.assertEqual(1,client.js.call_count)
            self.assertEqual(2,client.observe.call_count)

    def test_visible_target_skips_arrow(self):
        flow={'reference_size':[100,100],'steps':[{'name':'scroll','action':'key','key':'Up','before':['PAGE'],'after':['PAGE'],'skip_if':['TARGET']}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.return_value='PAGE TARGET'
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called()

    def test_white_badge_rejects_dark_background(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'badge.png'
            condition={'all':['CITY'],'white_regions':[{'bounds':[0,0,10,10],'min':.6}]}
            Image.new('RGB',(10,10),'white').save(path)
            macro.require_text(macro.Observation('CITY',path),condition)
            Image.new('RGB',(10,10),(90,95,105)).save(path)
            with self.assertRaises(RuntimeError):macro.require_text(macro.Observation('CITY',path),condition)

if __name__=='__main__':unittest.main()
