from app.config import GMAIL_SCOPES, Settings


def test_scope_is_readonly():
    assert GMAIL_SCOPES == ("https://www.googleapis.com/auth/gmail.readonly",)


def test_query_can_be_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("GMAIL_QUERY", raising=False)
    config = tmp_path / ".env"
    config.write_text("GMAIL_QUERY=from:example.invalid\n", encoding="utf-8")
    assert Settings.load(config).gmail_query == "from:example.invalid"
    monkeypatch.setenv("GMAIL_QUERY", "subject:公告")
    assert Settings.load(config).gmail_query == "subject:公告"
