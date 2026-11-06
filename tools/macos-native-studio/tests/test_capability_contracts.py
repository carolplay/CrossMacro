import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capability_contracts import ContractRegistry, digest


def document():
    return {'registry_id': 'fixture-game', 'registry_version': '1.0.0',
            'pages': {'city': {'all': ['CITY']}, 'root': {'all': ['ROOT'], 'none': ['REWARD']}},
            'exits': {'back': {'name': 'back', 'action': 'click', 'point': [5, 5],
                               'before': {'$page': 'root'}, 'after': {'$page': 'city'}}}}


class ContractTests(unittest.TestCase):
    def test_nested_expansion_keeps_authored_and_registry_unchanged(self):
        source = document(); original = copy.deepcopy(source); registry = ContractRegistry(source)
        authored = {'action_id': 'fixture', 'task_contract': {'anchor': {'$page': 'city'}, 'exits': [{'$exit': 'back'}]}}
        compiled = registry.workflow(authored)
        self.assertEqual({'all': ['ROOT'], 'none': ['REWARD']}, compiled['task_contract']['exits'][0]['before'])
        self.assertEqual(digest(authored), compiled['contract_compilation']['authored_sha256'])
        compiled['task_contract']['anchor']['all'].append('changed')
        self.assertEqual(original, source)
        self.assertEqual({'$page': 'city'}, authored['task_contract']['anchor'])
        self.assertEqual({'all': ['CITY']}, registry.resolve({'$page': 'city'}))

    def test_unused_cycle_and_unknown_reference_rejected_on_load(self):
        for value in ({'$page': 'cycle'}, {'$page': 'missing'}):
            source = document(); source['pages']['cycle'] = value
            with self.assertRaises(ValueError):
                ContractRegistry(source)

    def test_reference_override_and_cross_kind_mismatch_are_rejected(self):
        registry = ContractRegistry(document())
        for ref in ({'$page': 'city', 'none': []}, {'$exit': 'city'}, {'$page': []}):
            with self.assertRaises(ValueError):
                registry.resolve(ref)

    def test_registry_edit_changes_compiled_identity_without_mutating_old_snapshot(self):
        source = document(); old = ContractRegistry(source).workflow({'before': {'$page': 'city'}})
        source['registry_version'] = '1.0.1'; source['pages']['city']['none'] = ['MODAL']
        new = ContractRegistry(source).workflow({'before': {'$page': 'city'}})
        self.assertNotEqual(digest(old), digest(new))
        self.assertNotIn('none', old['before'])
        with self.assertRaises(ValueError):
            ContractRegistry(source).workflow(old)

    def test_expansion_validates_as_existing_engine_workflow(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'macos-window'))
        from window_macro import validate_workflow
        registry = ContractRegistry(document())
        flow = {'reference_size': [100, 100], 'steps': [{'$exit': 'back'}],
                'task_contract': {'anchor': {'$page': 'city'}, 'exits': [{'$exit': 'back'}]}}
        validate_workflow(registry.workflow(flow))


if __name__ == '__main__':
    unittest.main()
