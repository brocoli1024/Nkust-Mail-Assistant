"""Read-only monitoring. Exit 1 emits a safe alert suitable for Actions notifications."""
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def evaluate(data, max_age):
    alerts = []
    age = data['sync']['age_seconds']
    if age is None:
        alerts.append('SYNC_NEVER_SUCCEEDED')
    elif age > max_age:
        alerts.append('SYNC_STALE')
    http = data['http']
    # Counters are per process since startup, not a sliding time window.
    if http['requests'] >= 20 and http['error_rate'] > 0.05:
        alerts.append('HTTP_ERROR_RATE')
    return alerts


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def collect_alerts(base, token):
    """Check the service without forwarding credentials across redirects."""
    try:
        opener = build_opener(NoRedirect)
        with opener.open(base + '/health/ready', timeout=10) as response:
            if response.status != 200:
                return ['MONITOR_UNAVAILABLE']
        request = Request(base + '/health/status', headers={'Authorization': 'Bearer ' + token})
        with opener.open(request, timeout=10) as response:
            return evaluate(json.load(response), 10800)
    except Exception:
        return ['MONITOR_UNAVAILABLE']


def main():
    try:
        base = os.environ['MONITOR_BASE_URL'].rstrip('/')
        parsed = urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise ValueError()
        token = os.environ['MONITORING_TOKEN']
        if len(token) < 32:
            raise ValueError()
        alerts = collect_alerts(base, token)
    except Exception:
        alerts = ['MONITOR_UNAVAILABLE']
    print(json.dumps({'event': 'health_alert' if alerts else 'health_ok', 'alerts': alerts}))
    return int(bool(alerts))


if __name__ == '__main__':
    sys.exit(main())
