import os
import subprocess
import sys


def test_strict_ci_rejects_skipped_database_tests():
    env = {**os.environ, 'STRICT_TESTS': '1'}
    env.pop('TEST_DATABASE_URL', None)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q',
                             'tests/test_workspaces.py::test_missing_workspace'],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert '1 skipped' in result.stdout
