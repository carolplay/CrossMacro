import tempfile,unittest
from unittest.mock import Mock,patch
import window_macro as macro

class ObservationIntervalTests(unittest.TestCase):
    def flow(self):
        return {'reference_size':[100,100],'execution_timeout_seconds':60,'steps':[{'name':'wait','action':'observe','before':['READY'],'observe_attempts':3,'observe_interval_seconds':5}]}
    def test_external_state_waits_between_reads_without_any_input(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.side_effect=['TRAVELLING','TRAVELLING','READY']
            with patch.object(macro.time,'sleep') as sleep:
                macro.execute({'log_dir':directory},self.flow(),'all',backend=client)
            self.assertEqual([((5,),),((5,),)],[(c.args,) for c in sleep.call_args_list])
            self.assertEqual(3,client.observe.call_count)
            client.js.assert_not_called()
    def test_deadline_stops_before_sleep_or_extra_read(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Mock();client.observe.return_value='TRAVELLING'
            with patch.object(macro.time,'monotonic',side_effect=[100,100,158]),patch.object(macro.time,'sleep') as sleep:
                with self.assertRaises(macro.FatalExecutionError):macro.execute({'log_dir':directory},self.flow(),'all',backend=client)
            sleep.assert_not_called();self.assertEqual(1,client.observe.call_count);client.js.assert_not_called()
    def test_interval_is_bounded_and_observe_only(self):
        for value in [-1,6,True,float('nan')]:
            flow=self.flow();flow['steps'][0]['observe_interval_seconds']=value
            with self.assertRaises(ValueError):macro.validate_workflow(flow)
        flow=self.flow();flow['steps'][0].update(action='click',point=[10,10],after=['DONE'])
        with self.assertRaises(ValueError):macro.validate_workflow(flow)
