"""Choose only an explicitly validated viewport at backend startup.

This does not resize a window or infer a scale from arbitrary live pixels.
The caller must verify the returned entry condition before adopting the profile.
"""
import copy
import viewport_calibration


def candidate(config, reference, observed_size, locked=False):
    if locked:
        return None
    matches = []
    for item in config.get('validated_viewport_profiles', []):
        if item.get('native_size') != observed_size:
            continue
        profile = copy.deepcopy(item)
        condition = profile.pop('entry_condition', None)
        if not profile.get('validated_anchors') or not isinstance(condition, dict) or not condition.get('all'):
            raise ValueError('Viewport profile requires validation evidence and an entry condition')
        viewport_calibration.calibration({'viewport_calibration': profile}, reference)
        matches.append((profile, condition))
    if len(matches) > 1:
        raise ValueError('Ambiguous validated viewport profiles')
    return matches[0] if matches else None
