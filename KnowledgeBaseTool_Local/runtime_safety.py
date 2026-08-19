"""Shared runtime boundaries for test databases and external writes."""

import os
import sys
import tempfile


def env_flag(name):
    return str(os.environ.get(name) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def is_test_process():
    if env_flag('KMATRIX_TESTING') or os.environ.get('PYTEST_CURRENT_TEST'):
        return True
    executable = os.path.basename(str(sys.argv[0] or '')).lower()
    if executable in {'pytest', 'py.test', 'unittest'} or executable.startswith('test_') or executable.endswith('_test.py'):
        return True
    return any(
        name in {'pytest', 'unittest'} or name.startswith(('pytest.', 'unittest.'))
        for name in sys.modules
    )


def path_is_within(path, directory):
    try:
        return os.path.commonpath([
            os.path.realpath(os.path.abspath(path)),
            os.path.realpath(os.path.abspath(directory)),
        ]) == os.path.realpath(os.path.abspath(directory))
    except ValueError:
        return False


def is_temporary_path(path):
    return path_is_within(path, tempfile.gettempdir())


def validate_test_sqlite_path(path, base_dir):
    candidate = os.path.abspath(os.path.expanduser(str(path)))
    instance_dir = os.path.join(os.path.abspath(base_dir), 'instance')
    if path_is_within(candidate, instance_dir):
        raise RuntimeError(
            '测试进程禁止使用 KnowledgeBaseTool_Local/instance 下的 SQLite；'
            '请将数据库路径指向系统临时目录。'
        )
    if not is_temporary_path(candidate):
        raise RuntimeError(
            '测试进程只允许使用系统临时目录下的 SQLite；'
            '请移除自定义路径，让测试自动创建隔离数据库。'
        )
    return candidate


def resolve_test_sqlite_path(base_dir, configured=None):
    configured = str(configured if configured is not None else os.environ.get('KMATRIX_SQLITE_PATH') or '').strip()
    if configured:
        return validate_test_sqlite_path(configured, base_dir)
    test_dir = os.path.join(tempfile.gettempdir(), f'kmatrix-tests-{os.getpid()}')
    candidate = os.path.join(test_dir, 'data.db')
    os.environ['KMATRIX_SQLITE_PATH'] = candidate
    return candidate


def assert_external_write_allowed(operation):
    if is_test_process() and not env_flag('KMATRIX_ALLOW_LIVE_WRITE_TESTS'):
        raise RuntimeError(
            f'测试进程已阻止真实外部写入：{operation}。'
            '如需人工运行在线写入测试，请显式设置 KMATRIX_ALLOW_LIVE_WRITE_TESTS=1。'
        )
