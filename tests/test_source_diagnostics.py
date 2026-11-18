import http.client
from types import SimpleNamespace

import pytest

from app.services import source_diagnostics as diagnostics
from app.api import source_diagnostics as api


@pytest.mark.parametrize("phase", ["tcp", "tls", "headers", "body"])
def test_probe_reports_failed_phase_and_closes_socket(monkeypatch, phase):
    closed = []
    class Sock:
        def settimeout(self, value): pass
        def close(self): closed.append(True)
        def sendall(self, data): pass
    sock = Sock()
    def connect(*args):
        if phase == "tcp": raise TimeoutError("private")
        return sock
    def wrap(*args, **kwargs):
        if phase == "tls": raise TimeoutError("private")
        return sock
    class Response:
        status = 200
        def __init__(self, sock): pass
        def begin(self):
            if phase == "headers": raise TimeoutError("private")
        def read1(self, count):
            if phase == "body": raise TimeoutError("private")
            return b"data"
        def close(self): pass
    monkeypatch.setattr(diagnostics.socket, "create_connection", connect)
    monkeypatch.setattr(diagnostics.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap))
    monkeypatch.setattr(http.client, "HTTPResponse", Response)
    report = diagnostics.probe_address("www.nkust.edu.tw", "/", "1.1.1.1")
    assert report["phase"] == phase and report["error"] == "timeout"
    assert "private" not in str(report)
    assert bool(closed) == (phase != "tcp")


def test_collect_checks_two_addresses_for_each_fixed_target(monkeypatch):
    calls = []
    monkeypatch.setattr(diagnostics, "_resolve", lambda host: ["1.1.1.1", "8.8.8.8"])
    def probe(host, path, address):
        calls.append((host, path, address))
        return {"status": "success"}
    monkeypatch.setattr(diagnostics, "probe_address", probe)
    assert set(diagnostics.collect()["targets"]) == {"feed", "office"}
    assert len(calls) == 4
    assert calls[0][:2] == diagnostics.TARGETS["feed"]


def test_endpoint_requires_auth_rejects_input_and_throttles(monkeypatch):
    def invoke(coroutine):
        with pytest.raises(StopIteration) as stopped:
            coroutine.send(None)
        return stopped.value.value
    from fastapi import HTTPException
    from starlette.requests import Request
    app = SimpleNamespace(state=SimpleNamespace(discovery_settings=SimpleNamespace(
        enabled=True, trigger_secret="fixture")))
    monkeypatch.setattr(api, "_last_started", float("-inf"))
    async def collect_in_thread(fn):
        return {"targets": {}}
    monkeypatch.setattr(api, "run_in_threadpool", collect_in_thread)
    def request(auth="", query=b"", body=b""):
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        return Request({"type": "http", "method": "POST", "scheme": "http",
            "server": ("test", 80), "path": "/", "query_string": query,
            "headers": [(b"authorization", auth.encode())], "app": app}, receive)
    for req, status in [(request(), 401),
            (request("Bearer fixture", query=b"url=private"), 422),
            (request("Bearer fixture", body=b"x"), 422)]:
        with pytest.raises(HTTPException) as caught:
            invoke(api.diagnose(req))
        assert caught.value.status_code == status
    assert invoke(api.diagnose(request("Bearer fixture"))) == {"targets": {}}
    with pytest.raises(HTTPException) as caught:
        invoke(api.diagnose(request("Bearer fixture")))
    assert caught.value.status_code == 429


def test_pipeline_diagnostic_failure_preserves_sync_result(monkeypatch, capsys):
    import subprocess
    from scripts.refresh_public_sources import main
    monkeypatch.delenv("NKUST_OFFICE_DISCOVERY_TRIGGER_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[-1] == "scripts.diagnose_public_sources":
            raise subprocess.TimeoutExpired(command, 120)
        return subprocess.CompletedProcess(command, int("sync" in command), stdout="", stderr="")
    assert main(run=run) == 1
    assert calls[-1][-1] == "scripts.diagnose_public_sources"
    assert "SOURCE_DIAGNOSTICS_INCOMPLETE" in capsys.readouterr().out

def test_dns_rejects_nonpublic_addresses(monkeypatch):
    monkeypatch.setattr(diagnostics.socket, "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(OSError):
        diagnostics._resolve("www.nkust.edu.tw")


def test_remote_report_rejects_unexpected_data():
    from scripts.diagnose_public_sources import summarize_remote
    with pytest.raises(ValueError):
        summarize_remote({"private": "must not be printed"})
    report = {"checked_at": "2026-11-19T00:00:00+00:00", "targets": {
        name: {"phase": "dns", "error": "timeout", "status": "failed"}
        for name in diagnostics.TARGETS}}
    assert summarize_remote(report) == report
