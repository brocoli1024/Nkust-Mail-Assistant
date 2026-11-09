"""Minimum application schema accepted by the web service and preflight."""
REQUIRED_REVISION = '0011'

# 0011 only adds private push tables; public source table contracts remain identical.
PUBLIC_MAINTENANCE_REVISIONS = frozenset(('0010', '0011'))
