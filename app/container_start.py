"""Explicit container entry point; synthetic demo never enables Google access."""
import os
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

from cryptography.fernet import Fernet


def configure_demo(env):
    url = env.get('DATABASE_URL', 'sqlite:////app/data/demo.db')
    parsed = urlsplit(url)
    if url != 'sqlite:////app/data/demo.db' and not (
            parsed.scheme == 'postgresql+psycopg' and parsed.hostname == 'db'
            and parsed.port == 5432 and parsed.path == '/nkust_demo' and parsed.username == 'demo'
            and not parsed.query and not parsed.fragment):
        raise ValueError('Demo permits only its isolated database')
    env['DATABASE_URL'] = url
    env['GOOGLE_CLIENT_ID'] = env['GOOGLE_CLIENT_SECRET'] = 'synthetic-demo'
    env['GMAIL_CREDENTIALS_PATH'] = '/nonexistent/credentials.json'
    env['GMAIL_TOKEN_PATH'] = '/nonexistent/token.json'
    env['TOKEN_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    env['SESSION_SECRET'] = secrets.token_urlsafe(48)
    env.setdefault('MONITORING_TOKEN', secrets.token_urlsafe(32))
    env.setdefault('APP_BASE_URL', 'http://localhost')
    env['GOOGLE_REDIRECT_URI'] = env['APP_BASE_URL'].rstrip('/') + '/auth/google/callback'


def main():
    if os.environ.get('DEMO_MODE') == '1':
        configure_demo(os.environ)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True)
    if os.environ.get('DEMO_MODE') != '1':
        subprocess.run([sys.executable, '-m', 'app.deployment_check'], check=True)
    os.execvp(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.web:app',
              '--host', '0.0.0.0', '--port', os.environ.get('PORT', '8000'),
              '--workers', '1', '--no-access-log', '--no-proxy-headers'])


if __name__ == '__main__':
    main()
