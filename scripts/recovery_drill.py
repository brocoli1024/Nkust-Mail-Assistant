"""Destructive only inside a new, fixed Compose project with synthetic data.

Run from a machine with Docker: python scripts/recovery_drill.py
Never accepts a database URL, service name, production target or credentials.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

from check_health import collect_alerts

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), '-p', 'nkust-recovery']


def monitor_alerts():
    return collect_alerts('http://localhost:8000', 'synthetic-demo-monitoring-token-32-characters')


def docker(*args, **kwargs):
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, check=True, **kwargs)


def http_status(path):
    code = """import urllib.request, urllib.error
try:
    response = urllib.request.urlopen('http://localhost:8000' + PATH, timeout=5)
    print(response.status)
except urllib.error.HTTPError as error:
    print(error.code)
""".replace('PATH', repr(path))
    return int(docker('exec', '-T', 'web', 'python', '-c', code, capture_output=True, text=True).stdout.strip())


def sql(statement):
    return docker('exec', '-T', 'db', 'psql', '-U', 'demo', '-d', 'nkust_demo',
                  '-v', 'ON_ERROR_STOP=1', '-Atc', statement, capture_output=True, text=True).stdout.strip()


def main():
    if docker('ps', '-aq', capture_output=True, text=True).stdout.strip():
        raise RuntimeError('Refusing to modify an existing nkust-recovery project')
    try:
        docker('up', '-d', '--build', '--wait', '--wait-timeout', '180')
        assert http_status('/health/ready') == 200
        sql('CREATE TABLE recovery_marker (value text); INSERT INTO recovery_marker VALUES (\'synthetic-only\')')
        sql("INSERT INTO public_source_states (source_key, last_success_at, next_history_page, history_status) "
            "VALUES ('nkust-latest', CURRENT_TIMESTAMP, 1, 'incomplete')")
        assert monitor_alerts() == [], 'Expected a healthy baseline before stopping PostgreSQL'
        revision = sql('SELECT version_num FROM alembic_version')
        # Backup stays in this ephemeral DB container; no real data or host dump.
        docker('exec', '-T', 'db', 'pg_dump', '-U', 'demo', '-d', 'nkust_demo', '-Fc', '-f', '/tmp/demo.dump')
        started = time.monotonic()
        docker('stop', 'db')
        assert http_status('/health/live') == 200
        assert http_status('/health/ready') == 503
        alerts = monitor_alerts()
        assert alerts == ['MONITOR_UNAVAILABLE']
        print(json.dumps({'event': 'health_alert', 'alerts': alerts}), flush=True)
        docker('start', 'db')
        recovered = False
        for _ in range(30):
            if http_status('/health/ready') == 200:
                recovered = True
                break
            time.sleep(2)
        assert recovered, 'Database did not recover within 60 seconds'
        assert monitor_alerts() == [], 'Expected monitoring alert to clear after recovery'
        recovery_seconds = round(time.monotonic() - started, 2)
        # Restore to a SECOND database and verify both schema and marker.
        docker('exec', '-T', 'db', 'createdb', '-U', 'demo', 'nkust_restore')
        docker('exec', '-T', 'db', 'pg_restore', '-U', 'demo', '-d', 'nkust_restore', '--exit-on-error', '/tmp/demo.dump')
        restored = docker('exec', '-T', 'db', 'psql', '-U', 'demo', '-d', 'nkust_restore',
                          '-Atc', 'SELECT value FROM recovery_marker', capture_output=True, text=True).stdout.strip()
        assert restored == 'synthetic-only'
        restored_revision = docker('exec', '-T', 'db', 'psql', '-U', 'demo', '-d', 'nkust_restore',
                                   '-Atc', 'SELECT version_num FROM alembic_version', capture_output=True, text=True).stdout.strip()
        assert restored_revision == revision
        logs = docker('logs', '--no-color', 'web', capture_output=True, text=True).stdout
        assert '"event": "readiness_failed", "error_type": "database_unavailable"' in logs
        print(json.dumps({'event': 'recovery_drill_passed', 'recovery_seconds': recovery_seconds,
                          'alert_cleared': True, 'backup_restored': True}), flush=True)
    finally:
        docker('down', '--volumes', '--remove-orphans')
    return 0


if __name__ == '__main__':
    sys.exit(main())
