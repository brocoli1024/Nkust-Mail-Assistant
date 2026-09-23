"""Local configuration. OAuth scope is intentionally not configurable."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)


@dataclass(frozen=True)
class Settings:
    gmail_query: str = "from:mailoffice@nkust.edu.tw"
    credentials_path: Path = ROOT / "credentials.json"
    token_path: Path = ROOT / "token.json"
    timeout_seconds: int = 30
    database_path: Path = ROOT / 'data' / 'nkust_mail.db'
    ai_provider: str = 'iai'
    ai_base_url: str = 'https://www.iai.nkust.edu.tw/aihub/v1'
    ai_api_key: str = field(default='', repr=False)
    ai_model: str = ''
    ai_timeout_seconds: int = 90
    scrape_allowed_hosts: tuple[str, ...] = ('officemail.nkust.edu.tw',)

    @classmethod
    def load(cls, env_file: Path | None = None):
        values = {**dotenv_values(env_file or ROOT / ".env"), **os.environ}
        def path(key, default):
            value = Path(values.get(key) or default).expanduser()
            return value if value.is_absolute() else ROOT / value
        query = values.get("GMAIL_QUERY") or cls.gmail_query
        timeout = int(values.get("GMAIL_TIMEOUT_SECONDS") or 30)
        if not query.strip() or timeout <= 0:
            raise ValueError("Gmail query must not be blank; timeout must be positive")
        return cls(query, path("GMAIL_CREDENTIALS_PATH", "credentials.json"),
                   path("GMAIL_TOKEN_PATH", "token.json"), timeout,
                   path("DATABASE_PATH", "data/nkust_mail.db"),
                   values.get('AI_PROVIDER') or 'iai',
                   values.get('AI_BASE_URL') or cls.ai_base_url,
                   values.get('AI_API_KEY') or '', values.get('AI_MODEL') or '',
                   int(values.get('AI_TIMEOUT_SECONDS') or 90),
                   tuple(h.strip().lower() for h in (values.get('SCRAPE_ALLOWED_HOSTS') or 'officemail.nkust.edu.tw').split(',') if h.strip()))
