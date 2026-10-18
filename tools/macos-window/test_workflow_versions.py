import unittest
from workflow_versions import workflow_identity, suite_identity


class VersionTests(unittest.TestCase):
    def test_content_hash_catches_changes_without_version_bump(self):
        first = {'action_id':'vip', 'action_version':'0.1.0', 'steps':[]}
        second = {**first, 'task_contract':{'anchor':['CITY']}}
        self.assertEqual(workflow_identity(first), workflow_identity(dict(reversed(list(first.items())))))
        self.assertNotEqual(workflow_identity(first)['sha256'], workflow_identity(second)['sha256'])

    def test_manifest_distinguishes_order_and_keeps_unversioned_truthful(self):
        tasks = [('a', {'steps':[]}), ('b', {'steps':[{'name':'claim'}]})]
        self.assertNotEqual(suite_identity(tasks)['manifest_sha256'],
                            suite_identity(tasks[::-1])['manifest_sha256'])
        self.assertEqual('unversioned', suite_identity(tasks)['actions'][0]['action_version'])
