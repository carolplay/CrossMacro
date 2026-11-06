import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import task_batch
import window_macro as macro


def flow():
    return {'reference_size': [100, 100], 'steps': [
        {'name': 'claim', 'action': 'click', 'point': [10, 10], 'before': ['FREE'], 'after': ['CITY']}],
        'task_contract': {'anchor': ['CITY'], 'max_exit_steps': 1, 'recovery_timeout_seconds': 30,
                          'exits': [{'name': 'close', 'action': 'click', 'point': [5, 5], 'before': ['VIP'], 'after': ['CITY']}]}}


class WorkflowBudgetTests(unittest.TestCase):
    def test_budget_expired_during_observation_sends_no_input(self):
        clock = [0]
        backend = Mock()
        def observe(*args):
            clock[0] = 200
            return 'FREE'
        backend.observe.side_effect = observe
        with tempfile.TemporaryDirectory() as directory, patch.object(macro.time, 'monotonic', side_effect=lambda: clock[0]):
            with self.assertRaises(macro.WorkflowBudgetExceeded):
                macro.execute({'log_dir': directory}, flow(), 'all', backend=backend)
        backend.js.assert_not_called()
        backend.click.assert_not_called()

    def test_budget_failure_fresh_known_exit_continues_and_keeps_deviation(self):
        backend = Mock(); backend.deadline = -1
        observed_deadlines = []
        pages = iter(['VIP', 'CITY', 'CITY'])
        def observe(*args):
            observed_deadlines.append(backend.deadline)
            return next(pages)
        backend.observe.side_effect = observe
        with tempfile.TemporaryDirectory() as directory, patch.object(macro, 'execute', side_effect=[macro.WorkflowBudgetExceeded('budget'), None, None]) as execute:
            result = task_batch.run_batch({'log_dir': directory}, [('first', flow()), ('next', flow())], backend)
        self.assertEqual(['deviation', 'passed'], [t['status'] for t in result['tasks']])
        self.assertEqual('WorkflowBudgetExceeded', result['tasks'][0]['error_type'])
        self.assertTrue(all(d > 0 for d in observed_deadlines))
        self.assertEqual('close', execute.call_args_list[1].args[1]['steps'][0]['name'])
        self.assertLessEqual(execute.call_args_list[1].kwargs['absolute_deadline'], time.monotonic() + 30)

    def test_unknown_page_after_budget_never_gets_an_exit_click(self):
        backend = Mock(); backend.observe.return_value = 'UNKNOWN'
        with tempfile.TemporaryDirectory() as directory, patch.object(macro, 'execute', side_effect=macro.WorkflowBudgetExceeded('budget')) as execute:
            result = task_batch.run_batch({'log_dir': directory}, [('first', flow()), ('next', flow())], backend)
        self.assertEqual(['deviation', 'not_executed'], [t['status'] for t in result['tasks']])
        self.assertEqual(1, execute.call_count)

    def test_recovery_permission_refusal_is_fatal_without_input(self):
        backend = Mock(); backend.observe.side_effect = PermissionError('permission denied')
        with tempfile.TemporaryDirectory() as directory, patch.object(macro, 'execute', side_effect=macro.WorkflowBudgetExceeded('budget')) as execute:
            result = task_batch.run_batch({'log_dir': directory}, [('first', flow()), ('next', flow())], backend)
        self.assertEqual(['fatal', 'not_executed'], [t['status'] for t in result['tasks']])
        self.assertEqual(1, execute.call_count)

    def test_transport_timeout_is_still_fatal_without_recovery(self):
        backend = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.object(macro, 'execute', side_effect=TimeoutError('Native operation deadline exceeded')):
            result = task_batch.run_batch({'log_dir': directory}, [('first', flow()), ('next', flow())], backend)
        self.assertEqual(['fatal', 'not_executed'], [t['status'] for t in result['tasks']])
        backend.observe.assert_not_called()

    def test_exit_execution_cannot_extend_absolute_recovery_budget(self):
        backend = Mock(); backend.observe.return_value = 'FREE'
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(macro.WorkflowBudgetExceeded):
                macro.execute({'log_dir': directory}, flow(), 'all', backend=backend, absolute_deadline=time.monotonic() - 1)
        backend.observe.assert_not_called()
        backend.js.assert_not_called()

    def test_recovery_budget_is_not_restarted_after_anchor_failure(self):
        backend = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.object(macro, 'execute'), patch.object(task_batch, 'restore_anchor', side_effect=macro.WorkflowBudgetExceeded('exit budget')) as restore:
            result = task_batch.run_batch({'log_dir': directory}, [('first', flow()), ('next', flow())], backend)
        self.assertEqual(['deviation', 'not_executed'], [t['status'] for t in result['tasks']])
        self.assertEqual(1, restore.call_count)

    def test_invalid_recovery_budget_rejected_offline(self):
        for budget in (0, 121, True, '60'):
            item = flow(); item['task_contract']['recovery_timeout_seconds'] = budget
            with self.assertRaises(ValueError):
                macro.validate_workflow(item)


if __name__ == '__main__':
    unittest.main()
