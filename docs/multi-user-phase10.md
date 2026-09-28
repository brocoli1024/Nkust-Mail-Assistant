# Phase 10 — PWA

## Goal

Make the deployed website installable on a phone while keeping Gmail messages, announcements, and OAuth responses out of the PWA offline cache.

## Files

- `app/web.py`: serve the manifest, root-scoped service worker, and public offline page; allow same-origin PWA resources in Content Security Policy.
- `app/templates/web/`: add manifest and icons to account pages, online status notices, and installation guidance in Settings.
- `app/static/web/`: add the service worker, registration script, manifest, offline page, and 192/512/180-pixel icons.
- `tests/test_pwa.py` and `tests/pwa_worker_check.cjs`: verify assets, response headers, and service worker cache boundaries.

## Privacy boundary

The service worker precaches only `/offline`, the public stylesheet and font, and four public icons. Account pages use the network and show the offline notice if unavailable. The worker ignores OAuth callbacks, API calls, and POST requests. The server continues to send `Cache-Control: no-store` on all responses.

No push notifications, background synchronization, or offline copies of private content are included.

## Verification

Run `.venv/Scripts/python.exe -m pytest -q` on Windows. A small Node.js simulation of the service worker runs as part of pytest when Node.js is available.
