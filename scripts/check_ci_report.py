"""Fail closed when PostgreSQL coverage is missing, skipped, or unsuccessful."""
import sys

from defusedxml import ElementTree


REQUIRED_MODULES = {'test_postgresql', 'test_postgresql_account', 'test_public_postgresql'}


def main(path):
    try:
        cases = list(ElementTree.parse(path).iter('testcase'))
        executed = {case.get('classname', '').split('.')[-1] for case in cases
                    if not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped'))}
        incomplete = any(case.find(tag) is not None for case in cases
                         for tag in ('failure', 'error', 'skipped'))
        if incomplete or not REQUIRED_MODULES <= executed:
            raise ValueError('Incomplete test coverage')
    except Exception:
        print('CI_REPORT_REJECTED: require successful tests, no skips, and all PostgreSQL suites.')
        return 1
    print('CI_REPORT_OK: all required PostgreSQL suites executed; no failures or skips.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
