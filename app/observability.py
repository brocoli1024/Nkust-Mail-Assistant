"""Bounded, aggregate telemetry. Never pass request bodies or exception text here."""
from datetime import datetime, timezone
import json
import logging
from threading import Lock

logger = logging.getLogger('nkust.operations')
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def emit(event, **fields):
    logger.info(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                            'event': event, **fields}, ensure_ascii=True))


class HttpMetrics:
    """Single-process counters since startup; external monitoring retains history."""
    def __init__(self):
        self.lock = Lock()
        self.requests = self.errors = 0
        self.duration_ms = 0.0

    def record(self, status, elapsed_ms):
        with self.lock:
            self.requests += 1
            self.errors += int(status >= 500)
            self.duration_ms += elapsed_ms

    def snapshot(self):
        with self.lock:
            return {'requests': self.requests, 'server_errors': self.errors,
                    'duration_ms_sum': round(self.duration_ms, 3),
                    'mean_duration_ms': round(self.duration_ms / max(self.requests, 1), 3),
                    'error_rate': self.errors / max(self.requests, 1)}
