import json
import tempfile
import unittest
from pathlib import Path
from daily_operations import reserve,confirm

class DailyOperationTests(unittest.TestCase):
    def test_pending_and_confirmed_operations_both_prevent_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'identity_text':['actor-a'],'daily_state_file':str(Path(directory)/'daily.json')}
            token=reserve(config,'half-price','2026-01-01')
            with self.assertRaises(RuntimeError):reserve(config,'half-price','2026-01-01')
            confirm(token)
            self.assertEqual('confirmed',json.loads(Path(token[0]).read_text())[token[1]]['status'])
            with self.assertRaises(RuntimeError):reserve(config,'half-price','2026-01-01')

    def test_other_role_and_next_game_day_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'identity_text':['actor-a'],'daily_state_file':str(Path(directory)/'daily.json')}
            reserve(config,'half-price','2026-01-01')
            reserve(config,'half-price','2026-01-02')
            config['identity_text']=['actor-b'];reserve(config,'half-price','2026-01-01')
            self.assertEqual(3,len(json.loads(Path(config['daily_state_file']).read_text())))

    def test_missing_ledger_or_identity_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):reserve({},'half-price')

if __name__=='__main__':unittest.main()
