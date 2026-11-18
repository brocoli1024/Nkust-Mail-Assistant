"""Compare GitHub and Render against exactly the same two fixed school URLs."""
import json
import os

import requests

from app.services.source_diagnostics import collect, TARGETS, PHASES, ERRORS

ENDPOINT = "https://nkust-mail-assistant.onrender.com/internal/source-diagnostics/run"


def require(condition):
    if not condition:
        raise ValueError('Invalid diagnostic report')


def summarize_remote(value):
    # Reject unexpected structures instead of printing arbitrary endpoint content.
    from datetime import datetime
    import ipaddress

    require(set(value) == {"checked_at", "targets"})
    datetime.fromisoformat(value["checked_at"])
    require(set(value["targets"]) == set(TARGETS))
    for target in value["targets"].values():
        if "attempts" not in target:
            require(set(target) == {"phase", "error", "status"})
            require(target["phase"] == "dns" and target["error"] in ERRORS)
            require(target["status"] == "failed")
            continue
        require(set(target) == {"dns_ms", "attempts"})
        require(type(target["dns_ms"]) is int and 0 <= target["dns_ms"] <= 120000)
        require(1 <= len(target["attempts"]) <= 2)
        for attempt in target["attempts"]:
            require(set(attempt) <= {
                "ip", "timings_ms", "http_status", "sample_bytes", "status",
                "phase", "error", "elapsed_ms",
            })
            require(ipaddress.ip_address(attempt["ip"]).is_global)
            require(attempt["status"] in {"success", "failed"})
            require(attempt.get("phase", "tcp") in PHASES)
            require(attempt.get("error", "other") in ERRORS)
            for key in ("http_status", "sample_bytes", "elapsed_ms"):
                if key in attempt:
                    require(type(attempt[key]) is int and 0 <= attempt[key] <= 120000)
            require(set(attempt["timings_ms"]) <= PHASES)
            require(all(type(v) is int and 0 <= v <= 120000 for v in attempt["timings_ms"].values()))
    return value


def main():
    print("SOURCE_DIAGNOSTICS_GITHUB " + json.dumps(collect()), flush=True)
    secret = os.environ.get("NKUST_OFFICE_DISCOVERY_TRIGGER_SECRET", "")
    if not secret:
        print("SOURCE_DIAGNOSTICS_RENDER_NOT_CONFIGURED", flush=True)
        return
    try:
        with requests.post(
            ENDPOINT, headers={"Authorization": "Bearer " + secret},
            data=b"", allow_redirects=False, timeout=(5, 60), stream=True
        ) as response:
            if response.status_code != 200:
                print("SOURCE_DIAGNOSTICS_RENDER_HTTP_" + str(response.status_code), flush=True)
                return
            data = bytearray()
            for chunk in response.iter_content(1024):
                data.extend(chunk)
                if len(data) > 16384:
                    raise ValueError()
            result = summarize_remote(json.loads(data))
            print("SOURCE_DIAGNOSTICS_RENDER " + json.dumps(result), flush=True)
    except Exception:
        print("SOURCE_DIAGNOSTICS_RENDER_UNAVAILABLE", flush=True)


if __name__ == "__main__":
    main()
