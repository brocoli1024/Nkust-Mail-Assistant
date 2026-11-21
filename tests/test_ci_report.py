"""CI must reject failed tests and silently skipped database coverage."""
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_ci_report.py'
MODULES = ('test_postgresql', 'test_postgresql_account', 'test_public_postgresql')


@pytest.mark.parametrize('problem', ['failure', 'error', 'skipped', 'missing', 'empty', 'invalid'])
def test_report_rejects_incomplete_verification(tmp_path, problem):
    cases = [f'<testcase classname="tests.{name}" name="contract" />' for name in MODULES]
    if problem == 'missing':
        cases.pop()
    elif problem == 'empty':
        cases = []
    else:
        cases[0] = f'<testcase classname="tests.test_postgresql" name="contract"><{problem}/></testcase>'
    report = tmp_path / 'report.xml'
    report.write_text('invalid XML' if problem == 'invalid' else
                      '<testsuites><testsuite>' + ''.join(cases) + '</testsuite></testsuites>')
    result = subprocess.run([sys.executable, str(SCRIPT), str(report)], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'CI_REPORT_REJECTED' in result.stdout


def test_report_accepts_executed_postgresql_contracts(tmp_path):
    report = tmp_path / 'report.xml'
    report.write_text('<testsuites><testsuite>' + ''.join(
        f'<testcase classname="tests.{name}" name="contract" />' for name in MODULES
    ) + '</testsuite></testsuites>')
    result = subprocess.run([sys.executable, str(SCRIPT), str(report)], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'CI_REPORT_OK' in result.stdout
