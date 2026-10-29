"""The same todo contracts against an explicitly supplied disposable PostgreSQL DB."""
import pytest
from tests.test_postgresql import database
from tests import test_todos as contracts

@pytest.mark.parametrize('contract',[contracts.test_explicit_add_complete_snooze_remove_readd,
    contracts.test_owner_identity_cascade_and_reparse,contracts.test_correction_version_cannot_be_silently_added,
    contracts.test_two_todo_writers_have_one_winner],ids=lambda f:f.__name__)
def test_private_todo_postgresql(database,contract):contract(database)
