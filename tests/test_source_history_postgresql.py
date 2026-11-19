"""Opt-in contracts on disposable PostgreSQL schemas."""
import pytest
from tests.test_postgresql import database
from tests import test_source_versions as contracts
@pytest.mark.parametrize('contract',[contracts.test_public_versions_keep_a_b_a_and_unchanged,contracts.test_private_reparse_retains_original_and_isolates_cascade],ids=lambda f:f.__name__)
def test_source_versions_postgresql(database,contract):contract(database)
