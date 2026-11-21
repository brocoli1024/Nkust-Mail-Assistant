"""Public minimal health checks; protected aggregate operational status."""
from datetime import datetime, timezone
import hmac
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.database.schema import REQUIRED_REVISION
from app.observability import emit

router = APIRouter()


def probe_engine(url):
    # Separate pool and bounded driver/query timeouts keep probes independent.
    args = {'connect_timeout': 2, 'options': '-c statement_timeout=2000'} if url.get_backend_name() == 'postgresql' else {'timeout': 2}
    return create_engine(url, poolclass=NullPool, connect_args=args, hide_parameters=True)


@router.get('/health/live')
def live():
    return {'status': 'alive'}


@router.get('/health/ready')
def ready(request: Request):
    try:
        with request.app.state.health_engine.connect() as connection:
            revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
    except Exception:
        emit('readiness_failed', error_type='database_unavailable')
        return JSONResponse({'status': 'not_ready'}, status_code=503)
    if revision != REQUIRED_REVISION:
        emit('readiness_failed', error_type='schema_mismatch')
        return JSONResponse({'status': 'not_ready'}, status_code=503)
    return {'status': 'ready'}


@router.get('/health/status')
def status(request: Request):
    token = os.environ.get('MONITORING_TOKEN', '')
    if len(token) < 32:
        raise HTTPException(404)
    supplied = request.headers.get('authorization', '')
    if not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401)
    with request.app.state.health_engine.connect() as connection:
        counts = dict(connection.execute(text(
            'SELECT status, COUNT(*) FROM public_sync_runs GROUP BY status')).all())
        last = connection.scalar(text(
            "SELECT last_success_at FROM public_source_states WHERE source_key = 'nkust-latest'"))
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    if last and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return {'http': request.app.state.http_metrics.snapshot(),
            'sync': {'runs': counts, 'last_success_at': last.isoformat() if last else None,
                     'age_seconds': max(0, (datetime.now(timezone.utc) - last).total_seconds()) if last else None}}
