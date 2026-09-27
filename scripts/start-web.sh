#!/bin/sh
set -eu

# A single free Render instance runs the schema upgrade before accepting traffic.
python -m alembic upgrade head
python -m app.deployment_check
exec python -m uvicorn app.web:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log --no-proxy-headers
