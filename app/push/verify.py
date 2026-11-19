"""Fail-closed independent local PostgreSQL verifier. Never use DATABASE_URL."""
import os,sys
from sqlalchemy.engine import make_url

def validate_test_target(raw,marker):
    try:
        url=make_url(raw)
        if url.query or marker!='yes' or url.get_backend_name()!='postgresql' or url.host not in ('localhost','127.0.0.1','::1') or not (url.database or '').startswith('nkust_disposable'):raise ValueError()
        production=os.environ.get('DATABASE_URL')
        if production:
            p=make_url(production)
            if (p.host,p.port,p.database)==(url.host,url.port,url.database):raise ValueError()
        return url
    except Exception:raise ValueError('PUSH_TEST_TARGET_REFUSED') from None

class NoSkip:
    skipped=0
    def pytest_runtest_logreport(self,report):
        if report.skipped:self.skipped+=1
    def pytest_sessionfinish(self,session,exitstatus):
        if self.skipped:session.exitstatus=1

def main():
    try:
        target=validate_test_target(os.environ.get('NKUST_TEST_POSTGRES_URL',''),os.environ.get('NKUST_PUSH_TEST_DISPOSABLE',''))
        limited=os.environ.get('NKUST_TEST_PUBLIC_SYNC_URL')
        if limited:
            other=validate_test_target(limited,'yes')
            if (target.host,target.port,target.database)!=(other.host,other.port,other.database) or other.username!='nkust_public_sync':raise ValueError()
    except ValueError:
        print('PUSH_TEST_TARGET_REFUSED: explicit disposable loopback PostgreSQL target required.');return 2
    # libpq environment must not override an explicitly verified loopback target.
    for name in tuple(os.environ):
        if name.upper().startswith('PG'):os.environ.pop(name,None)
    import pytest
    plugin=NoSkip()
    targets=['tests/test_push_postgresql.py','tests/test_postgresql.py'] if '--push-only' in sys.argv else []
    base=os.environ.get('NKUST_PUSH_TEST_TEMP','.superpowers/sdd/2026-11-08-device-push/pytest-independent')
    result=pytest.main([*targets,'-q','--tb=short','--basetemp='+base],plugins=[plugin])
    print('PUSH_TEST_SKIPPED='+str(plugin.skipped))
    return int(result)
if __name__=='__main__':raise SystemExit(main())
