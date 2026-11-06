import json,tempfile,time,threading,unittest
from pathlib import Path
from current_turn_backend import CurrentTurnBackend
from window_macro import FatalExecutionError,WorkflowBudgetExceeded

class CurrentTurnTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.b=CurrentTurnBackend({'current_turn_bridge':str(self.root/'pipe'),'log_dir':str(self.root/'log'),'target':{'app_path':'/test/WOS.app'}})
 def tearDown(self):self.b.close();self.temp.cleanup()
 def responder(self,handler):
  def work():
   p=self.b.root/'request.json'
   for _ in range(200):
    if p.exists():break
    time.sleep(.005)
   req=json.loads(p.read_text());p.unlink();reply=handler(req);tmp=self.b.root/'response.new';tmp.write_text(json.dumps({'id':req['id'],**reply}));tmp.replace(self.b.root/'response.json')
  t=threading.Thread(target=work);t.start();return t
 def test_typed_click_has_no_js_or_caller_identity(self):
  seen=[];t=self.responder(lambda r:(seen.append(r) or {'ok':True}));self.b.click([12,34]);t.join();self.assertEqual(seen[0]['operation'],'click');self.assertEqual(seen[0]['parameters'],{'point':[12,34]});self.assertNotIn('identity',json.dumps(seen))
 def test_repeated_keys_are_individual_bounded_requests(self):
  from unittest.mock import Mock
  self.b._request=Mock(return_value={'ok':True});self.b.key('Up',count=3,duration_ms=80)
  self.assertEqual(self.b._request.call_count,3)
  self.assertTrue(all(c.kwargs['count']==1 for c in self.b._request.call_args_list))
 def test_expired_not_sent(self):
  self.b.deadline=time.monotonic()-1
  with self.assertRaises(WorkflowBudgetExceeded):self.b.click([1,2])
  self.assertFalse((self.b.root/'request.json').exists())
 def test_timeout_stops_no_replay(self):
  self.b.deadline=time.monotonic()+.03
  with self.assertRaises(TimeoutError):self.b.click([1,2])
  with self.assertRaises(FatalExecutionError):self.b.click([1,2])
  self.assertEqual(self.b.next_id,1)
 def test_denial_latches(self):
  t=self.responder(lambda r:{'ok':False,'error':'platform denied'})
  with self.assertRaises(FatalExecutionError):self.b.start()
  t.join()
  with self.assertRaises(FatalExecutionError):self.b.key('Escape')
 def test_screenshot_consumed_without_retention(self):
  def reply(r):(self.b.root/('frame-%s.bin'%r['id'])).write_bytes(b'\x89PNGtest');return {'ok':True}
  t=self.responder(reply);self.assertEqual(self.b.original_screenshot_bytes(),b'\x89PNGtest');t.join();self.assertFalse(list(self.b.root.glob('*.bin')))
 def test_arbitrary_javascript_rejected(self):
  with self.assertRaises(ValueError):self.b.js('process.exit()')
 def test_wrong_response_id_stops(self):
  (self.b.root/'response.json').write_text('{"id":999,"ok":true}')
  with self.assertRaises(FatalExecutionError):self.b.click([1,2])
 def test_close_keeps_only_metadata(self):
  (self.b.root/'frame-8.bin').write_bytes(b'x');self.b.close();self.assertFalse(list(self.b.root.glob('*.bin')));self.assertTrue((self.b.root/'closed.json').exists())
if __name__=='__main__':unittest.main()
