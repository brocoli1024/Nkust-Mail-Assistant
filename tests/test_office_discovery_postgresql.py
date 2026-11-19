from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from tests.test_postgresql import database
from tests.test_office_discovery_state import test_candidates_and_cursor_commit_together_with_cooldown as candidate_contract,test_expired_worker_identity_reuse_and_cascade as identity_contract,NOW,OWNER
from app.database.office_discovery import DiscoveryRepository
from app.core.office_discovery import DiscoveryError

def test_private_discovery_progress_on_postgresql(database):candidate_contract(database)
def test_private_discovery_identity_on_postgresql(database):identity_contract(database)
def test_only_one_postgresql_discovery_worker_acquires(database):
 db,_=database;barrier=Barrier(2)
 def attempt(_):
  barrier.wait()
  try:return bool(DiscoveryRepository(db,OWNER).acquire(NOW))
  except DiscoveryError:return False
 with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(attempt,range(2)))==1

def test_discovery_publication_and_resume_on_postgresql(database):
 from tests.test_office_discovery import test_owner_mail_only_discovers_and_publication_uses_anonymous_page
 test_owner_mail_only_discovers_and_publication_uses_anonymous_page(database)

def test_discovery_publication_identity_race_on_postgresql(database):
 from tests.test_office_discovery import test_owner_deleted_during_public_fetch_cannot_publish
 test_owner_deleted_during_public_fetch_cannot_publish(database)
