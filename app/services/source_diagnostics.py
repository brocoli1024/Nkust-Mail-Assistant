"""Bounded probes of fixed public school endpoints; reports contain no page content."""
import http.client
import ipaddress
import queue
import socket
import ssl
import threading
import time
from datetime import datetime, timezone

TARGETS = {
    "feed": ("www.nkust.edu.tw", "/p/503-1000-1001.php"),
    "office": ("officemail.nkust.edu.tw", "/"),
}
PHASES = {"dns", "tcp", "tls", "headers", "body"}
ERRORS = {"timeout", "dns", "certificate", "tls", "connection", "protocol", "network", "other"}


def _resolve(host):
    result = queue.Queue(maxsize=1)

    def lookup():
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except Exception as exc:
            result.put(exc)

    threading.Thread(target=lookup, daemon=True).start()
    try:
        records = result.get(timeout=5)
    except queue.Empty:
        raise TimeoutError() from None
    if isinstance(records, Exception):
        raise records
    addresses = sorted({item[4][0] for item in records})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise OSError()
    return addresses[:2]


def _error(exc):
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, socket.gaierror):
        return "dns"
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "certificate"
    if isinstance(exc, ssl.SSLError):
        return "tls"
    if isinstance(exc, ConnectionError):
        return "connection"
    if isinstance(exc, http.client.HTTPException):
        return "protocol"
    if isinstance(exc, OSError):
        return "network"
    return "other"


def probe_address(host, path, address):
    report = {"ip": address, "timings_ms": {}}
    sock = response = None
    phase = "tcp"
    started = time.monotonic()
    deadline = started + 10

    def elapsed():
        return round((time.monotonic() - started) * 1000)

    def remaining():
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError()
        return min(5, budget)

    try:
        sock = socket.create_connection((address, 443), remaining())
        report["timings_ms"]["tcp"] = elapsed()
        phase = "tls"
        sock.settimeout(remaining())
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        report["timings_ms"]["tls"] = elapsed()
        phase = "headers"
        sock.settimeout(remaining())
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
            "User-Agent: NKUST-Mail-Assistant/1.0\r\n"
            "Accept-Encoding: identity\r\nConnection: close\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = http.client.HTTPResponse(sock)
        response.begin()
        report["http_status"] = response.status
        report["timings_ms"]["headers"] = elapsed()
        phase = "body"
        sock.settimeout(remaining())
        report["sample_bytes"] = len(response.read1(1024))
        report["timings_ms"]["body"] = elapsed()
        report["status"] = "success"
    except Exception as exc:
        report.update(status="failed", phase=phase, error=_error(exc))
    finally:
        if response is not None:
            response.close()
        if sock is not None:
            sock.close()
    report["elapsed_ms"] = elapsed()
    return report


def collect():
    targets = {}
    for name, (host, path) in TARGETS.items():
        started = time.monotonic()
        try:
            addresses = _resolve(host)
            dns_ms = round((time.monotonic() - started) * 1000)
            targets[name] = {
                "dns_ms": dns_ms,
                "attempts": [probe_address(host, path, address) for address in addresses],
            }
        except Exception as exc:
            targets[name] = {"phase": "dns", "error": _error(exc), "status": "failed"}
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "targets": targets}
