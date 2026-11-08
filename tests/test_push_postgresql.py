import pytest
from tests.test_postgresql import database
from tests import test_push_devices as contracts

@pytest.mark.parametrize('contract',[contracts.test_device_isolation_and_redaction,contracts.test_endpoint_cannot_be_claimed_by_new_device,contracts.test_0011_preserves_0010_and_public_role_denied],ids=lambda f:f.__name__)
def test_push_on_postgresql(database,contract):contract(database)
