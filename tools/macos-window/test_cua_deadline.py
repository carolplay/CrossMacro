import queue,time,unittest
from unittest.mock import Mock
import window_macro as m
from task_batch import fatal
class CuaAdmissionDeadline(unittest.TestCase):
 def backend(self,deadline):
  b=m.CuaMcp.__new__(m.CuaMcp);b.deadline=deadline;b.next_id=0;b.messages=Mock();b.errors=[];b.send=Mock();return b
 def test_expired_click_request_never_reaches_transport(self):
  b=self.backend(time.monotonic()-1)
  with self.assertRaises(m.WorkflowBudgetExceeded):b.request('tools/call',{'name':'js','arguments':{'code':'await target.click([10,10]);'}})
  b.send.assert_not_called();b.messages.get.assert_not_called();self.assertEqual(b.next_id,0)
 def test_timeout_after_send_still_stops_batch(self):
  b=self.backend(time.monotonic()+10);b.messages.get.side_effect=queue.Empty
  try:b.request('tools/call',{'name':'js','arguments':{'code':'await target.click([10,10]);'}})
  except TimeoutError as exc:self.assertTrue(fatal(exc))
  else:self.fail('Expected unknown-effect transport timeout')
  b.send.assert_called_once()
if __name__=='__main__':unittest.main()
