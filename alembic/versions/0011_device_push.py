"""Add private anonymous push storage. No existing rows are modified."""
from alembic import op
from app.push.models import PushDevice,PushReminder,PushOperation,PushLease,PushRateBucket
revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None
TABLES=(PushDevice.__table__,PushReminder.__table__,PushOperation.__table__,PushLease.__table__,PushRateBucket.__table__)
def upgrade():
    for table in TABLES:table.create(op.get_bind())
    op.bulk_insert(PushLease.__table__,[{'name':'mutations'},{'name':'dispatcher'}])
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':
        # Keep public sync and default PUBLIC grants out of sensitive tables.
        for table in TABLES:
            op.execute('REVOKE ALL ON TABLE '+table.name+' FROM PUBLIC')
        for table in TABLES:
            op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE "+table.name+" FROM nkust_public_sync; END IF; END $$")
def downgrade():
    for table in reversed(TABLES):table.drop(op.get_bind())
