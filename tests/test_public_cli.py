import json
from dataclasses import replace
from tests.test_multi_user_database import database
from tests.test_public_source import feed,item
from app.config import Settings
from app.public_cli import main


def test_cli_uses_only_multiplayer_database_and_safe_counts(database, monkeypatch,capsys):
    db,_=database
    monkeypatch.setattr('app.public_cli.Settings.load',lambda:Settings(database_url=db.engine.url))
    monkeypatch.setattr('app.public_cli.fetch_feed',lambda:feed(item()))
    assert main(['sync'])==0
    output=json.loads(capsys.readouterr().out)
    assert output['added']==1 and output['status']=='success'
    monkeypatch.setattr('app.public_cli.fetch_feed',lambda:feed())
    assert main(['sync'])==1


def test_cli_failure_does_not_print_secrets(monkeypatch,capsys):
    def fail(): raise RuntimeError('PRIVATE-MARKER')
    monkeypatch.setattr('app.public_cli.Settings.load',fail)
    assert main(['sync'])==1
    assert 'PRIVATE-MARKER' not in capsys.readouterr().out
