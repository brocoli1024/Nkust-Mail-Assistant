"""Installability and privacy boundaries for the account PWA."""
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from tests.test_sessions import login, web
from tests.test_auth import oauth


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_offline_notice_and_icons(web):
    client, _, _, _ = web
    manifest_response = client.get('/manifest.webmanifest')
    assert manifest_response.status_code == 200
    assert manifest_response.headers['content-type'].startswith('application/manifest+json')
    assert manifest_response.headers['cache-control'] == 'no-store'
    manifest = manifest_response.json()
    assert manifest['start_url'] == manifest['scope'] == '/'
    assert manifest['display'] == 'standalone'
    assert manifest['theme_color'] == '#1d191a'

    offline = client.get('/offline')
    assert offline.status_code == 200
    assert '目前沒有網路' in offline.text
    assert '郵件與公告內容' in offline.text
    assert 'account.css?v=editorial-1' in offline.text
    assert client.get('/assets/icon.svg').status_code == 200
    assert client.get('/assets/fonts/Manrope.ttf').status_code == 200

    for path, expected_size in (
        ('/assets/icon-192.png', 192),
        ('/assets/icon-512.png', 512),
        ('/assets/apple-touch-icon.png', 180),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', response.content[16:24]) == (expected_size, expected_size)


def test_pwa_assets_and_account_pages_keep_private_headers(web):
    client, _, _, _ = web
    login_page = client.get('/login')
    assert login_page.status_code == 200
    assert 'href="/manifest.webmanifest"' in login_page.text
    assert 'src="/assets/pwa.js"' in login_page.text
    assert 'account.css?v=editorial-1' in login_page.text
    assert login_page.headers['cache-control'] == 'no-store'
    csp = login_page.headers['content-security-policy']
    for directive in ("script-src 'self'", "worker-src 'self'", "connect-src 'self'",
                      "manifest-src 'self'", "img-src 'self'"):
        assert directive in csp

    worker = client.get('/sw.js')
    assert worker.status_code == 200
    assert worker.headers['content-type'].startswith('application/javascript')
    assert worker.headers['cache-control'] == 'no-store'
    assert "const PUBLIC_FILES" in worker.text

    login(client)
    for path in ('/dashboard', '/settings', '/announcements'):
        page = client.get(path)
        assert page.status_code == 200
        assert page.headers['cache-control'] == 'no-store'
        assert 'href="/manifest.webmanifest"' in page.text


def test_service_worker_never_caches_private_responses():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is not installed; browser worker simulation unavailable')
    result = subprocess.run(
        [node, str(ROOT / 'tests' / 'pwa_worker_check.cjs')],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
