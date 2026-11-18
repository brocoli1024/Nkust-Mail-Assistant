"""Authenticated fixed-target source diagnostics for scheduler comparisons."""
import hmac
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.services.source_diagnostics import collect

router = APIRouter()
_lock = threading.Lock()
_last_started = float("-inf")


@router.post("/internal/source-diagnostics/run")
async def diagnose(request: Request):
    global _last_started
    config = request.app.state.discovery_settings
    supplied = request.headers.get("authorization", "")
    if not config.enabled or not config.trigger_secret:
        raise HTTPException(404)
    if len(supplied) > 512 or not hmac.compare_digest(
        supplied.encode(), ("Bearer " + config.trigger_secret).encode()
    ):
        raise HTTPException(401)
    if request.url.query:
        raise HTTPException(422)
    async for chunk in request.stream():
        if chunk:
            raise HTTPException(422)
    with _lock:
        now = time.monotonic()
        if now - _last_started < 300:
            raise HTTPException(429)
        _last_started = now
    return await run_in_threadpool(collect)
