"""Run disposable PostgreSQL integration tests without saving a connection string.

Interactive local use only. Paste the Neon direct connection string at the hidden
prompt. It is passed to a child process through its environment, never argv/logs.
"""
import getpass
import os
import subprocess
import sys
from urllib.parse import urlsplit


def main():
    print('Paste the direct Neon test-branch connection string. Input is hidden.')
    try:
        raw = getpass.getpass('Test database URL: ').strip()
        parsed = urlsplit(raw)
        if (parsed.scheme not in ('postgresql', 'postgresql+psycopg') or
                not parsed.hostname or not parsed.hostname.endswith('.neon.tech') or
                not parsed.password or parsed.path != '/neondb' or
                'sslmode=require' not in parsed.query):
            print('TEST_URL_INVALID: use this branch’s direct Neon connection string.')
            return 2
        env = dict(os.environ)
        env['NKUST_TEST_POSTGRES_URL'] = raw
        result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_postgresql.py', '-q',
                                 '--tb=short'], env=env, check=False)
        return result.returncode
    except (EOFError, KeyboardInterrupt):
        print('\nTEST_CANCELLED')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
