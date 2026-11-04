"""Private office discovery progress and retry candidates."""
from alembic import op
import sqlalchemy as sa
revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None
def upgrade():
 op.create_table('office_discovery_state',sa.Column('user_id',sa.Integer(),primary_key=True,autoincrement=False),sa.Column('google_user_id',sa.String(255),nullable=False),sa.Column('window_start',sa.DateTime(timezone=True)),sa.Column('window_end',sa.DateTime(timezone=True)),sa.Column('window_complete',sa.Boolean(),nullable=False),sa.Column('page_token',sa.Text()),sa.Column('last_complete_scan_at',sa.DateTime(timezone=True)),sa.Column('last_status',sa.String(32),nullable=False),sa.Column('last_error_code',sa.String(64)),sa.Column('lease_owner',sa.String(64)),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),sa.Column('next_allowed_at',sa.DateTime(timezone=True)),sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'))
 op.create_table('office_discovery_candidates',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),nullable=False),sa.Column('canonical_url',sa.String(4096),nullable=False),sa.Column('discovered_at',sa.DateTime(timezone=True),nullable=False),sa.Column('status',sa.String(32),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('next_retry_at',sa.DateTime(timezone=True)),sa.Column('error_code',sa.String(64)),sa.ForeignKeyConstraint(['user_id'],['users.id'],ondelete='CASCADE'),sa.UniqueConstraint('user_id','canonical_url'),sa.CheckConstraint("status IN ('pending','retry','published','rejected')",name='status'),sa.CheckConstraint('attempts >= 0',name='attempts'))
 op.create_index('ix_office_discovery_candidates_user_id','office_discovery_candidates',['user_id'])
def downgrade():
 op.drop_table('office_discovery_candidates');op.drop_table('office_discovery_state')
