"""Cross-worker per-user sync leases, renewed and fenced on every write."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sync_leases',
                    sa.Column('user_id', sa.Integer(), autoincrement=False, nullable=False),
                    sa.Column('owner', sa.String(64), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.PrimaryKeyConstraint('user_id', name='pk_sync_leases'),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_sync_leases_user_id_users'))


def downgrade():
    op.drop_table('sync_leases')
