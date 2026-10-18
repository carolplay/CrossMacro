import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import task_batch as batch
import window_macro as macro

class BatchTests(unittest.TestCase):
    def test_lab_button_ocr_failure_recovers_and_runs_following_task(self):
        flow=json.loads((Path(__file__).parent/'wos-crystal-half-price.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            backend=Mock();backend.observe.side_effect=[
                '今日剩余次数：8 本周超级提炼次数：68 超级提炼I次',
                '英雄 背包 野外','CITY']
            with patch.object(macro,'execute',side_effect=[RuntimeError('button OCR failure'),None,None]) as execute:
                result=batch.run_batch({'log_dir':directory},[('refined',flow),('next',self.flow())],backend)
            self.assertEqual(['deviation','passed'],[t['status'] for t in result['tasks']])
            self.assertEqual('exit-lab',execute.call_args_list[1].args[1]['steps'][0]['name'])

    def test_inactive_vip_alternative_skips_without_click(self):
        flow={'reference_size':[100,100], 'steps':[{'name':'claim','action':'click',
              'point':[10,10],'before':['FREE'],'after':['DONE'],
              'skip_if_any':[{'all':['VIP','COOLDOWN']},{'all':['VIP','INACTIVE']}]}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.return_value='VIP INACTIVE'
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called()

    def test_cropped_counter_ignores_icon_fused_into_full_window_ocr(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'counter.png';Image.new('RGB',(100,100)).save(path)
            observation=macro.Observation('PAGE count88',path,{'width':100,'height':100,'lines':[]},
                                          {'binary':'fixture','language':'en-US'})
            output=Mock(stdout=json.dumps({'lines':[{'text':'count:8','confidence':1}]}))
            condition={'all':['PAGE'],'text_regions':[{'bounds':[0,0,50,30],
                       'pattern':'count:8','crop_ocr':True}]}
            with patch.object(macro.subprocess,'run',return_value=output) as ocr:
                macro.require_text(observation,condition)
                condition['text_regions'][0]['pattern']='count:7'
                with self.assertRaises(RuntimeError):macro.require_text(observation,condition)
            self.assertEqual(1,ocr.call_count)

    def flow(self):
        return {'reference_size':[100,100], 'steps':[], 'task_contract':{'anchor':['CITY'], 'max_exit_steps':2,
            'exits':[{'name':'close','action':'click','point':[10,10],'before':['VIP'],'after':['CITY']}]}}

    def test_business_failure_restores_anchor_and_executes_next_task(self):
        with tempfile.TemporaryDirectory() as directory:
            backend=Mock();backend.observe.side_effect=['VIP','CITY','CITY']
            with patch.object(macro,'execute',side_effect=[RuntimeError('unsupported branch'),None,None]) as execute:
                r=batch.run_batch({'log_dir':directory},[('first',self.flow()),('next',self.flow())],backend)
            self.assertEqual(['deviation','passed'],[t['status'] for t in r['tasks']])
            self.assertEqual(3,execute.call_count)
            self.assertEqual('close',execute.call_args_list[1].args[1]['steps'][0]['name'])
            self.assertEqual('unversioned/exit/close',execute.call_args_list[1].args[1]['action_id'])

    def test_city_overview_must_close_before_anchor_is_restored(self):
        flow=json.loads((Path(__file__).parent/'wos-training-lancer.json').read_text())
        self.assertFalse(batch.matches('英雄 背包 野外 日常 部队训练 盾兵 矛兵 射手',flow['task_contract']['anchor']))
        with tempfile.TemporaryDirectory() as directory:
            backend=Mock();backend.observe.side_effect=['英雄 背包 野外 日常 部队训练 盾兵 矛兵 射手','英雄 背包 野外']
            with patch.object(macro,'execute') as execute:
                result=batch.restore_anchor({'log_dir':directory},flow,backend)
            self.assertEqual('restored',result['status'])
            self.assertEqual(1,result['exit_steps'])
            self.assertEqual('exit-city-overview',execute.call_args.args[1]['steps'][0]['name'])

    def test_conditional_click_rechecks_skip_without_sending_input(self):
        flow={'reference_size':[100,100], 'steps':[{'name':'claim', 'action':'click',
             'point':[10,10], 'before':['FREE'], 'after':['DONE'], 'skip_if':['COOLDOWN'], 'observe_attempts':3}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['animation','COOLDOWN']
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called()
            self.assertEqual(2,client.observe.call_count)

    def test_wrong_identity_stops_without_attempting_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            backend=Mock()
            with patch.object(macro,'execute',side_effect=macro.FatalExecutionError('Identity mismatch')) as execute:
                r=batch.run_batch({'log_dir':directory},[('first',self.flow()),('next',self.flow())],backend)
            self.assertEqual(['fatal','not_executed'],[t['status'] for t in r['tasks']])
            self.assertEqual(2,len(r['versions']['actions']))
            self.assertEqual(r['versions']['actions'][1]['sha256'],r['tasks'][1]['workflow']['sha256'])
            backend.observe.assert_not_called();self.assertEqual(1,execute.call_count)

    def test_unknown_page_stops_without_recovery_click(self):
        with tempfile.TemporaryDirectory() as directory:
            backend=Mock();backend.observe.return_value='UNKNOWN'
            with patch.object(macro,'execute',side_effect=RuntimeError('business')) as execute:
                r=batch.run_batch({'log_dir':directory},[('first',self.flow()),('next',self.flow())],backend)
            self.assertEqual('unrecovered',r['tasks'][0]['anchor']['status'])
            self.assertEqual('not_executed',r['tasks'][1]['status']);self.assertEqual(1,execute.call_count)

    def test_locked_runtime_is_fatal(self):
        self.assertTrue(batch.fatal(RuntimeError('The Mac is locked and automatic unlock could not unlock it')))
        self.assertFalse(batch.fatal(RuntimeError('Expected exactly one readable HH:MM:SS timer')))
        self.assertTrue(batch.fatal(RuntimeError('This Computer Use request cannot be associated with a ChatGPT thread')))

    def test_observe_retry_waits_out_reward_animation_without_clicking(self):
        flow={'reference_size':[100,100], 'steps':[{'name':'check', 'action':'observe',
             'before':['COOLDOWN'], 'observe_attempts':3}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['reward animation', 'COOLDOWN']
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            self.assertEqual(2,client.observe.call_count)
            client.js.assert_not_called()

    def test_inventory_snapshot_rejects_paid_change_before_further_input(self):
        region=[0,0,100,100]
        def observed(value):
            return macro.Observation('PAGE', 'unused', {'width':100,'height':100,'lines':[
                {'text':str(value),'confidence':1,'bounds':[.1,.1,.2,.1]}]})
        flow={'reference_size':[100,100], 'steps':[
            {'name':'remember','action':'observe','before':['PAGE'], 'remember_numbers':[{'name':'keys','bounds':region}]},
            {'name':'verify','action':'observe','before':['PAGE'], 'unchanged_numbers':[{'name':'keys','bounds':region}]}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=[observed(111),observed(110)]
            with self.assertRaises(macro.FatalExecutionError):macro.execute({'log_dir':directory},flow,'all',backend=client)
            client.js.assert_not_called()

    def test_inventory_does_not_guess_when_two_numbers_are_in_region(self):
        data={'width':100,'height':100,'lines':[
            {'text':'111','confidence':1,'bounds':[.1,.1,.1,.1]},
            {'text':'222','confidence':1,'bounds':[.4,.1,.1,.1]}]}
        with self.assertRaises(RuntimeError):macro.number_in_region(macro.Observation('PAGE','unused',data),[0,0,100,100])

    def test_inventory_accepts_adjacent_plus_but_not_other_text(self):
        data={'width':100,'height':100,'lines':[{'text':'12,345+','confidence':.5,'bounds':[.1,.1,.3,.1]}]}
        self.assertEqual(12345,macro.number_in_region(macro.Observation('PAGE','unused',data),[0,0,100,100]))
        data['lines'][0]['text']='12,345 paid'
        with self.assertRaises(RuntimeError):macro.number_in_region(macro.Observation('PAGE','unused',data),[0,0,100,100])
        macro.require_text('高級招募 史诗招募',['高级招募','史诗招募'])

    def test_zero_donation_count_does_not_match_twenty(self):
        condition={'all':['DONATION'],'text_regions':[{'bounds':[0,0,100,100],'pattern':r'(?:次数:)?0/25'}]}
        for value, valid in [('次数：0/25',True),('次数：20/25',False)]:
            data={'width':100,'height':100,'lines':[{'text':value,'confidence':1,'bounds':[.1,.1,.3,.1]}]}
            observation=macro.Observation('DONATION','unused',data)
            if valid:macro.require_text(observation,condition)
            else:
                with self.assertRaises(RuntimeError):macro.require_text(observation,condition)

    def test_green_marker_requires_unique_component(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'markers.png';image=Image.new('RGB',(100,100),'black');draw=ImageDraw.Draw(image)
            draw.rectangle([10,10,22,22],fill=(0,220,0));image.save(path)
            step={'green_target':{'bounds':[0,0,100,100],'offset':[5,5]}}
            observation=macro.Observation('TECH',path)
            self.assertEqual([21,21],macro.resolve_point(step,observation,[100,100]))
            draw.rectangle([60,10,72,22],fill=(0,220,0));image.save(path)
            with self.assertRaises(RuntimeError):macro.resolve_point(step,observation,[100,100])

    def test_recovery_profile_requires_matching_identity_before_click(self):
        with tempfile.TemporaryDirectory() as directory:
            flow=self.flow();flow['task_contract']['exits'][0].update(before=['PROFILE'],verify_identity=True)
            backend=Mock();backend.observe.return_value='PROFILE ID:wrong'
            with patch.object(macro,'execute') as execute:
                with self.assertRaises(macro.FatalExecutionError):batch.restore_anchor({'log_dir':directory,'identity_text':['ID:right']},flow,backend)
                execute.assert_not_called()

if __name__=='__main__':unittest.main()
