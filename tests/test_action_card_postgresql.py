"""Run the same ownership/reparse/append contracts only on an opt-in test DB."""
import pytest
from tests.test_postgresql import database
from tests import test_action_card_corrections as contracts

@pytest.mark.parametrize('contract',[
    contracts.test_save_reset_preserves_original_and_is_read_only,
    contracts.test_owner_identity_and_version_conflicts,
    contracts.test_reparse_preserves_history_without_applying_to_reused_id,
    contracts.test_snapshot_owner_foreign_key,
    contracts.test_two_writers_never_silently_overwrite,
    contracts.test_complete_patch_can_keep_unedited_materials,
],ids=lambda c:c.__name__)
def test_private_card_contracts(database,contract):
    contract(database)
