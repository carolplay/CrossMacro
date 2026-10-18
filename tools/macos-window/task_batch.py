"""Compose fixed window tasks with bounded, declared exits; no model fallback."""
import json
import time
from pathlib import Path

import window_macro as macro
import check_run


def fatal(error):
    if isinstance(error, (macro.FatalExecutionError, TimeoutError, OSError, KeyboardInterrupt)):
        return True
    text = str(error).lower()
    return any(word in text for word in ('mac is locked', 'automatic unlock', 'rejected due to',
        'permission denied', 'access denied', 'mcp closed', 'mcp operation failed', 'mcp timed out',
        'mcp operation deadline', 'active executor', 'identity mismatch', 'window size changed',
        'user changed', 're-query the latest state'))


def matches(observation, condition):
    try:
        macro.require_text(observation, condition)
        return True
    except RuntimeError:
        return False


def restore_anchor(config, workflow, backend):
    """Only declared page-specific exits; unknown pages never receive input."""
    contract = workflow.get('task_contract', {})
    anchor = contract.get('anchor')
    if not anchor:
        return {'status': 'unrecovered', 'reason': 'No declared anchor'}
    folder = Path(config['log_dir']) / ('anchor-' + str(time.time_ns()))
    folder.mkdir(parents=True)
    for index in range(contract.get('max_exit_steps', 4) + 1):
        observed = backend.observe(folder, str(index), workflow['reference_size'])
        for read_attempt in range(3):
            # Re-read transient OCR/animations, never click an unknown page.
            if any(word in str(observed) for word in ('另一台设备', '重新连接', '重新登录')):
                raise macro.FatalExecutionError('Session lost during anchor recovery')
            if matches(observed, anchor):
                return {'status': 'restored', 'exit_steps': index, 'evidence': str(folder)}
            exits = [step for step in contract.get('exits', []) if matches(observed, step['before'])]
            if len(exits) == 1:
                break
            if read_attempt == 2:
                return {'status': 'unrecovered', 'reason': 'Unknown or ambiguous exit page', 'evidence': str(folder)}
            observed = backend.observe(folder, str(index)+'-retry-'+str(read_attempt), workflow['reference_size'])
        if index == contract.get('max_exit_steps', 4):
            break
        step = exits[0]
        if step.get('verify_identity'):
            try:
                macro.require_text(observed, config['identity_text'])
            except RuntimeError as exc:
                raise macro.FatalExecutionError('Identity mismatch during recovery') from exc
        # The normal executor re-observes and re-checks immediately before input.
        macro.execute(config, {'reference_size': workflow['reference_size'], 'steps': [step]}, 'all', backend=backend)
    return {'status': 'unrecovered', 'reason': 'Exit step budget exhausted', 'evidence': str(folder)}


def run_batch(config, tasks, backend):
    started = time.time()
    result = {'run_mode': 'macro_only_record_deviations', 'agent_fallback': False,
              'started_unix': started, 'runtime_model_calls': 0, 'tasks': []}
    for index, (name, workflow) in enumerate(tasks):
        begin = time.time()
        entry = {'task': name}
        try:
            macro.execute(config, workflow, 'all', backend=backend)
            entry['status'] = 'passed'
            entry['anchor'] = restore_anchor(config, workflow, backend)
        except (Exception, KeyboardInterrupt) as exc:
            entry.update(status='deviation', error=str(exc))
            if fatal(exc):
                entry.update(status='fatal', anchor={'status': 'not_attempted'})
            else:
                try:
                    entry['anchor'] = restore_anchor(config, workflow, backend)
                except (Exception, KeyboardInterrupt) as recovery_error:
                    entry['anchor'] = {'status': 'unrecovered', 'reason': str(recovery_error)}
                    if fatal(recovery_error):
                        entry['status'] = 'fatal'
        entry['elapsed_seconds'] = time.time() - begin
        result['tasks'].append(entry)
        if entry['status'] == 'fatal' or entry['anchor']['status'] != 'restored':
            result['tasks'].extend({'task': other, 'status': 'not_executed', 'reason': 'Fatal failure or anchor not restored'}
                                   for other, _ in tasks[index + 1:])
            break
    result['ended_unix'] = time.time()
    result['elapsed_seconds'] = result['ended_unix'] - started
    result['status'] = 'passed' if all(t['status'] == 'passed' for t in result['tasks']) else 'completed_with_deviations'
    reports = list(Path(config['log_dir']).glob('*/result.json'))
    result['audit'] = check_run.check(reports)
    # Anchor observations are saved outside execute's per-step result folders.
    result['anchor_screenshots'] = sum(len(list(p.glob('*.jpg'))) + len(list(p.glob('*.png')))
                                       for p in Path(config['log_dir']).glob('anchor-*'))
    result['anchor_ocr_calls'] = sum(len(list(p.rglob('*-ocr.json'))) for p in Path(config['log_dir']).glob('anchor-*'))
    Path(config['log_dir'], 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result
