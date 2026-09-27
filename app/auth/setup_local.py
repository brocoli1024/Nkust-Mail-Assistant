"""Idempotently add missing local values without printing any secrets."""
import os
import secrets

from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key

from app.auth.config import OAuthSettings
from app.config import ROOT
from app.database.multi_user import validate_database_url


def main():
    path = ROOT / '.env'
    values = {**dotenv_values(path), **os.environ}
    key = values.get('TOKEN_ENCRYPTION_KEY') or Fernet.generate_key().decode('ascii')
    config = OAuthSettings(values.get('GOOGLE_CLIENT_ID', ''), values.get('GOOGLE_CLIENT_SECRET', ''),
                           values.get('GOOGLE_REDIRECT_URI', ''), values.get('APP_BASE_URL', ''), key).validate()
    url = values.get('DATABASE_URL') or 'sqlite:///data/nkust_multi_user.db'
    validate_database_url(url, legacy_path=values.get('DATABASE_PATH') or 'data/nkust_mail.db')
    if not values.get('TOKEN_ENCRYPTION_KEY'):
        set_key(str(path), 'TOKEN_ENCRYPTION_KEY', config.encryption_key)
    if not values.get('DATABASE_URL'):
        set_key(str(path), 'DATABASE_URL', url)
    if not values.get('SESSION_SECRET'):
        set_key(str(path), 'SESSION_SECRET', secrets.token_urlsafe(48))
    print('Local OAuth settings validated; missing database URL/key added. No secrets displayed.')


if __name__ == '__main__':
    main()
