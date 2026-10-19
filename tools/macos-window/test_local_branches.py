from pathlib import Path
import json,tempfile,unittest
from unittest.mock import Mock,patch
import window_macro as macro
class LocalBranchesTests(unittest.TestCase):
    def test_skipped_branch_has_no_observations_or_inputs_and_next_branch_is_fresh(self):
        flow={'reference_size':[100,100],'steps':[
            {'name':'choose','action':'click','point':[10,10],'before':['READY'],'after':['DONE'],'skip_if':['EMPTY']},
            {'name':'disabled-click','action':'click','point':[20,20],'before':['INNER'],'after':['DONE'],'skip_if_step_skipped':'choose'},
            {'name':'disabled-check','action':'observe','before':['DONE'],'skip_if_step_skipped':'choose'},
            {'name':'next','action':'click','point':[30,30],'before':['NEXT_READY'],'after':['FINISHED']}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['EMPTY','NEXT_READY','FINISHED']
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            self.assertEqual(3,client.observe.call_count)
            self.assertEqual(1,client.js.call_count)
            self.assertIn('[30, 30]',client.js.call_args.args[0])
            report=json.loads(next(Path(directory).glob('*/result.json')).read_text())
            self.assertEqual([True,True,True],[s['skipped'] for s in report['steps'][:3]])
    def test_long_workflow_budget_is_explicit_and_bounded(self):
        flow={'reference_size':[100,100],'execution_timeout_seconds':1800,'steps':[{'name':'read','action':'observe','before':['PAGE']}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.return_value='PAGE'
            with patch.object(macro.time,'monotonic',return_value=100):macro.execute({'log_dir':directory},flow,'all',backend=client)
            self.assertEqual(1900,client.deadline)
        flow['execution_timeout_seconds']=1801
        with self.assertRaises(ValueError):macro.validate_workflow(flow)
    def test_repeat_isolates_skip_dependencies_and_finishes_on_fresh_empty_observation(self):
        flow={'reference_size':[100,100],'execution_timeout_seconds':60,'repeat_from':'empty','steps':[
            {'name':'empty','action':'observe','before':['MAP'],'finish_if':['EMPTY']},
            {'name':'choose','action':'observe','before':['MAP'],'skip_if':['ABSENT']},
            {'name':'claim','action':'click','point':[10,10],'before':['MAP'],'after':['DONE'],'skip_if_step_skipped':'choose'}]}
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['MAP','ABSENT','MAP','MAP','MAP','DONE','EMPTY']
            macro.execute({'log_dir':directory},flow,'all',backend=client)
            self.assertEqual(1,client.js.call_count)
            report=json.loads(next(Path(directory).glob('*/result.json')).read_text())
            self.assertTrue(report['steps'][2]['skipped'])
            self.assertEqual('round-2-claim',report['steps'][5]['name'])
            self.assertTrue(report['steps'][-1]['finished_early'])
    def test_repeat_requires_explicit_watchdog_and_completion_anchor(self):
        flow={'reference_size':[100,100],'repeat_from':'read','steps':[{'name':'read','action':'observe','before':['MAP']}]}
        with self.assertRaises(ValueError):macro.validate_workflow(flow)
        flow['execution_timeout_seconds']=60
        with self.assertRaises(ValueError):macro.validate_workflow(flow)
