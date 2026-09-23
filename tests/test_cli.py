import json
from pathlib import Path
from unittest.mock import Mock, patch

from app.cli import main
from app.services.gmail_service import GmailSetupRequired

SAMPLE = str(Path(__file__).parent / 'fixtures' / 'nkust_mail_sample.html')


def test_ai_models_does_not_access_mail_or_database(capsys):
    provider = Mock(name='provider')
    provider.name = 'iai'
    provider.list_models.return_value = ['exact-model-id']
    with patch('app.cli.IAIProvider', return_value=provider) as factory, \
         patch('app.cli.GmailService.connect') as gmail, patch('app.cli.Database') as database:
        assert main(['ai-models']) == 0
        assert factory.call_args.kwargs == {'require_model': False}
        gmail.assert_not_called()
        database.assert_not_called()
    assert json.loads(capsys.readouterr().out)['models'] == ['exact-model-id']


def test_ai_models_missing_key(capsys):
    from app.config import Settings
    with patch('app.cli.Settings.load', return_value=Settings(ai_api_key='')):
        assert main(['ai-models']) == 1
    assert 'AI_KEY_MISSING' in capsys.readouterr().err


def test_ai_check_only_uses_synthetic_text(capsys):
    from app.services.ai_analyzer import ValidatedAnalysis
    from app.schemas.analysis import AnalysisOutput
    from test_ai_analyzer import answer
    provider = Mock()
    provider.name, provider.model = 'iai', 'test-model'
    with patch('app.cli.IAIProvider', return_value=provider), \
         patch('app.cli.analyze', return_value=ValidatedAnalysis(AnalysisOutput(**answer()))) as analyze, \
         patch('app.cli.Database') as database, patch('app.cli.GmailService.connect') as gmail:
        assert main(['ai-check']) == 0
        assert analyze.call_args.kwargs['original_text'].startswith('測試獎勵金')
        database.assert_not_called()
        gmail.assert_not_called()
    assert json.loads(capsys.readouterr().out)['result']['deadline'] == '2026-10-08'


def test_offline_cli(capsys):
    assert main(['parse', SAMPLE, '--received-at', '2026-09-19']) == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output['announcements']) == 3
    assert output['announcements'][1]['event_date'] == '2026-10-21'


def test_bad_file_exit_code(tmp_path, capsys):
    path = tmp_path / 'bad.html'
    path.write_text('<p>unknown</p>', encoding='utf-8')
    assert main(['parse', str(path)]) == 1
    assert 'TABLE_NOT_FOUND' in capsys.readouterr().err


def test_missing_setup_is_actionable(capsys):
    with patch('app.cli.GmailService.connect', side_effect=GmailSetupRequired('OAUTH_SETUP_REQUIRED: see README')):
        assert main(['gmail']) == 1
    assert 'OAUTH_SETUP_REQUIRED' in capsys.readouterr().err


def test_per_message_failure_not_silent(capsys):
    service = Mock()
    service.list_message_ids.return_value = ['a']
    from app.services.email_parser import DecodedEmail
    from datetime import datetime, timezone
    service.read_message.return_value = DecodedEmail('a', '', '', datetime(2026, 9, 19, tzinfo=timezone.utc), '<p>bad</p>', None)
    with patch('app.cli.GmailService.connect', return_value=service):
        assert main(['gmail', '--limit', '1']) == 1
    output = json.loads(capsys.readouterr().out)
    assert output['emails'] == []
    assert 'TABLE_NOT_FOUND' in output['errors'][0]['error']


def test_sync_cli_persists_and_skips(tmp_path, capsys):
    from app.config import Settings
    from app.services.email_parser import DecodedEmail
    from datetime import datetime, timezone
    gmail = Mock()
    gmail.list_message_ids.return_value = ['sample']
    gmail.read_message.return_value = DecodedEmail(
        'sample', 'sender@example.invalid', 'sample', datetime(2026, 9, 19, tzinfo=timezone.utc),
        Path(SAMPLE).read_text(encoding='utf-8'), None)
    with patch('app.cli.Settings.load', return_value=Settings(database_path=tmp_path / 'test.db')), \
         patch('app.cli.GmailService.connect', return_value=gmail):
        assert main(['sync', '--limit', '1']) == 0
        first = json.loads(capsys.readouterr().out)
        assert first['processed'] == 1
        assert main(['sync', '--limit', '1']) == 0
        second = json.loads(capsys.readouterr().out)
        assert second['skipped'] == 1
        assert first['database_counts'] == second['database_counts']
