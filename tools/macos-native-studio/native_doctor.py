"""Read-only diagnostics for the app that actually owns native permissions."""
from pathlib import Path
import fcntl
import os
import plistlib
import stat
import subprocess


def unavailable(error):
    """A stopped or inaccessible App is a diagnostic result, not readiness."""
    return {'ready_for_test_window': False, 'blockers': ['native_app_unavailable'],
            'next_steps': ['打开Macro Studio后重新检查；不自动启动其他执行后端'],
            'error_type': type(error).__name__, 'read_only': True,
            'permission_requested': False, 'input_sent': False,
            'wos_accepted': False, 'lock_screen_supported': False}


def probe_device_lock(path):
    """Probe the existing regular lock without creating or changing any file."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise PermissionError('Expected current-user regular lock file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'checked': True, 'free_at_check': False}
        fcntl.flock(fd, fcntl.LOCK_UN)
        return {'checked': True, 'free_at_check': True,
                'note': 'Diagnostic snapshot only; begin must acquire the real lock again.'}
    except OSError as exc:
        return {'checked': False, 'error_type': type(exc).__name__}
    finally:
        if fd is not None:
            os.close(fd)


def diagnose(status, expected_lock=None):
    blockers = []
    steps = []
    for key, action in [
        ('screen_recording', '在macOS隐私设置中为Macro Studio开启屏幕录制'),
        ('accessibility', '在macOS隐私设置中为Macro Studio开启辅助功能'),
        ('on_console', '返回当前Mac登录的桌面会话'),
        ('session_available', '唤醒并解锁Mac后刷新App状态'),
    ]:
        if status.get(key) is not True:
            blockers.append(key + '_not_ready')
            steps.append(action)
    if status.get('screen_locked_diagnostic') is not False:
        blockers.append('screen_locked_or_unknown')
        steps.append('手动解锁；首版不支持锁屏执行')
    if status.get('cua_dependency') is not False:
        blockers.append('native_capability_unknown')
    if not status.get('input_enabled'):
        blockers.append('input_not_enabled')
        steps.append('在Macro Studio打开测试窗口并点允许本次输入')
    if status.get('run_id'):
        blockers.append('executor_already_active')
    if expected_lock and Path(status.get('lock_file', '')).resolve() != Path(expected_lock).resolve():
        blockers.append('shared_lock_mismatch')
        steps.append('将App配置指向既有唯一执行锁；不要另建生产锁')
    return {'ready_for_test_window': not blockers, 'blockers': blockers,
            'next_steps': list(dict.fromkeys(steps)),
            'app_path': status.get('app_path'), 'bundle_id': status.get('bundle_id'),
            'running_version': status.get('version'), 'status': status,
            'read_only': True, 'permission_requested': False, 'input_sent': False,
            'wos_accepted': False, 'lock_screen_supported': False}


def signing_identity(app_path):
    """Inspect the installed bundle; do not sign it or change TCC records."""
    app = Path(app_path)
    with (app/'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    verify = subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(app)],
                            capture_output=True, text=True, timeout=15)
    show = subprocess.run(['/usr/bin/codesign', '--display', '--verbose=4', str(app)],
                          capture_output=True, text=True, timeout=15)
    requirement = subprocess.run(['/usr/bin/codesign', '--display', '-r', '-', str(app)],
                                capture_output=True, text=True, timeout=15)
    fields = {}
    for line in (show.stdout+'\n'+show.stderr).splitlines():
        key, sep, value = line.partition('=')
        if sep and key in {'Identifier', 'TeamIdentifier', 'CDHash', 'Signature', 'CodeDirectory'}:
            fields[key] = value
    adhoc = fields.get('Signature') == 'adhoc' or 'adhoc' in fields.get('CodeDirectory', '')
    return {'bundle_version': info.get('CFBundleShortVersionString'),
            'bundle_id': info.get('CFBundleIdentifier'), 'signature_verified': verify.returncode == 0,
            'verification_error': (verify.stdout+verify.stderr).strip() if verify.returncode else None,
            'designated_requirement': next((line.strip() for line in (requirement.stdout+'\n'+requirement.stderr).splitlines() if line.strip().startswith('designated =>')), None),
            'signing': fields, 'adhoc': adhoc,
            'permission_persistence': 'unverified_across_rebuilds' if adhoc else 'requires_restart_and_update_acceptance'}


def attach_signing_diagnostics(report, identity):
    """An installed but untrusted/stale bundle cannot be reported ready."""
    report['installed_identity'] = identity
    if identity.get('signature_verified') is not True:
        report['blockers'].append('installed_signature_not_verified')
        report['next_steps'].append('先解决签名验证，不安装或启动输入；保留原错误，不更改验证规则')
    if identity.get('bundle_version') != report.get('running_version'):
        report['restart_required'] = True
        report['blockers'].append('running_installed_version_mismatch')
    report['ready_for_test_window'] = not report['blockers']
    return report
