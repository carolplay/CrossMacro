"""Resolve game-owned page/exit references before a batch; no device access."""
import copy
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


class ContractRegistry:
    def __init__(self, document):
        if not isinstance(document, dict) or set(document) != {'registry_id', 'registry_version', 'pages', 'exits'}:
            raise ValueError('Expected a versioned page/exit registry')
        if not all(isinstance(document[k], str) and document[k] for k in ('registry_id', 'registry_version')):
            raise ValueError('Registry identity required')
        if not all(isinstance(document[k], dict) for k in ('pages', 'exits')):
            raise ValueError('pages/exits must be mappings')
        for kind in ('pages', 'exits'):
            if not all(isinstance(k, str) and k and isinstance(v, dict) for k, v in document[kind].items()):
                raise ValueError('Named condition/exit objects required')
        self.document = copy.deepcopy(document)
        # Validate even currently unused references; no latent cycles in a frozen registry.
        for kind in ('pages', 'exits'):
            marker = '$page' if kind == 'pages' else '$exit'
            for name in document[kind]:
                self.resolve({marker: name})

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def identity(self):
        return {k: self.document[k] for k in ('registry_id', 'registry_version')} | {'sha256': digest(self.document)}

    def resolve(self, value):
        count = [0]
        def expand(item, stack):
            count[0] += 1
            if count[0] > 10000 or len(stack) > 64:
                raise ValueError('Contract expansion limit exceeded')
            if isinstance(item, list):
                return [expand(v, stack) for v in item]
            if not isinstance(item, dict):
                return copy.deepcopy(item)
            markers = set(item) & {'$page', '$exit'}
            if markers:
                if len(item) != 1:
                    raise ValueError('References cannot override contract fields')
                marker = next(iter(markers)); name = item[marker]
                if not isinstance(name, str):
                    raise ValueError('Reference name must be a string')
                kind = 'pages' if marker == '$page' else 'exits'
                key = (kind, name)
                if key in stack:
                    raise ValueError('Contract reference cycle')
                if name not in self.document[kind]:
                    raise ValueError('Unknown contract reference')
                return expand(self.document[kind][name], stack + [key])
            return {k: expand(v, stack) for k, v in item.items()}
        return expand(value, [])

    def workflow(self, authored):
        if 'contract_compilation' in authored:
            raise ValueError('Compile authored workflows exactly once')
        compiled = self.resolve(authored)
        compiled['contract_compilation'] = {'registry': self.identity(), 'authored_sha256': digest(authored)}
        return compiled
