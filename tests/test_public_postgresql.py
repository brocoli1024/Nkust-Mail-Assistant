"""Opt-in public data contracts on independent PostgreSQL disposable schemas."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from tests.test_postgresql import database
from tests import test_public_sync as sync_contracts
from tests import test_public_database as db_contracts
from tests import test_public_history as history_contracts
from app.services.public_sync import SourceLease
from app.services.public_source import PublicSourceError


@pytest.mark.parametrize('contract',[
    db_contracts.test_public_rows_have_no_user_dependency,
    db_contracts.test_public_identity_is_source_and_url_not_title,
    db_contracts.test_migration_preserves_private_users_and_has_complete_metadata,
    sync_contracts.test_sync_repeat_update_and_source_failure,
    sync_contracts.test_empty_and_partial_sources_are_not_marked_success,
    sync_contracts.test_lease_blocks_concurrency_expires_and_rejects_stale_writer,
    history_contracts.test_backfill_resumes_only_after_committed_page,
    history_contracts.test_repeated_page_and_malformed_end_do_not_mark_complete,
    history_contracts.test_page_budget_preserves_richer_rss_and_can_resume,
    history_contracts.test_same_listing_and_rss_content_is_unchanged_in_any_database_timezone,
],ids=lambda f:f.__name__)
def test_public_contracts_on_postgresql(database,contract):
    contract(database)


@pytest.mark.parametrize('split',[False,True])
def test_repeated_history_page_across_postgresql_batches(database,split):
    history_contracts.test_nonadjacent_repeated_last_page_is_rejected_across_batches(database,split)


def test_public_source_lease_only_one_concurrent_owner(database):
    db,_=database
    ready=Barrier(2)
    leases=[]
    def claim():
        lease=SourceLease(db)
        ready.wait(timeout=5)
        try:
            lease.acquire()
            leases.append(lease)
            return 'acquired'
        except PublicSourceError as e:
            return str(e)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _:claim(),range(2)))==['PUBLIC_SYNC_BUSY','acquired']
    finally:
        for lease in leases: lease.release()
