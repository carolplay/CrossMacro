"""Version and content identity captured with every macro execution report."""
import hashlib
import json

SUITE_VERSION = '0.1.7'


def workflow_identity(workflow):
    encoded = json.dumps(workflow, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return {'action_id': workflow.get('action_id', 'unversioned'),
            'action_version': workflow.get('action_version', 'unversioned'),
            'sha256': hashlib.sha256(encoded).hexdigest()}


def suite_identity(tasks):
    actions = [{'task': name, **workflow_identity(flow)} for name, flow in tasks]
    encoded = json.dumps(actions, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {'suite_version': SUITE_VERSION,
            'manifest_sha256': hashlib.sha256(encoded).hexdigest(), 'actions': actions}
